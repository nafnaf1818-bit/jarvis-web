import os
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from dotenv import load_dotenv
import memory
import ai_agent

load_dotenv()

app = Flask(__name__)
CORS(app)

memory.init_db()


def _process_emails_and_tasks(emails_raw: list, calendar_events: list) -> dict:
    """Shared logic: classify emails, extract tasks, save everything."""
    processed = {"classified": 0, "tasks_created": 0, "errors": []}

    for mail in emails_raw:
        try:
            result = ai_agent.classify_email(
                sender=mail.get("sender", ""),
                subject=mail.get("subject", ""),
                body=mail.get("body", ""),
            )
            memory.save_email({
                "message_id": mail.get("id", mail.get("message_id", mail.get("subject", "no-id"))),
                "sender": mail.get("sender", ""),
                "subject": mail.get("subject", ""),
                "body": mail.get("body", ""),
                "summary": result["summary"],
                "draft_reply": result["draft_reply"],
                "status": result["status"],
                "received_at": mail.get("date", mail.get("received_at", "")),
            })
            processed["classified"] += 1
        except Exception as e:
            processed["errors"].append(str(e))

    pending_emails = memory.get_emails_by_status("pending")
    if pending_emails or calendar_events:
        try:
            memory.clear_tasks()
            tasks = ai_agent.extract_tasks(pending_emails, calendar_events)
            for t in tasks:
                memory.save_task(t)
            processed["tasks_created"] = len(tasks)
        except Exception as e:
            processed["errors"].append(f"tasks: {e}")

    return processed


# ---------------------------------------------------------------------------
# Pages HTML
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    emails = memory.get_emails_by_status("pending")
    counts = memory.count_emails()
    import google_client
    google_ok = google_client.google_creds_configured()
    return render_template("index.html", emails=emails, counts=counts, google_ok=google_ok)


@app.route("/todo")
def todo():
    tasks = memory.get_tasks(done=0)
    import google_client
    google_ok = google_client.google_creds_configured()
    return render_template("todo.html", tasks=tasks, google_ok=google_ok)


# ---------------------------------------------------------------------------
# API — Sync Google (remplace n8n)
# ---------------------------------------------------------------------------

@app.route("/api/sync", methods=["POST"])
def sync():
    """Fetch directly from Gmail + Google Calendar, classify, save."""
    import google_client

    if not google_client.google_creds_configured():
        return jsonify({"ok": False, "error": "Identifiants Google non configurés"}), 400

    try:
        emails_raw = google_client.fetch_emails(hours_back=24, max_results=30)
        calendar_events = google_client.fetch_calendar_events(days_ahead=7)
    except Exception as e:
        return jsonify({"ok": False, "error": f"Erreur Google API : {e}"}), 500

    processed = _process_emails_and_tasks(emails_raw, calendar_events)
    counts = memory.count_emails()
    return jsonify({"ok": True, "counts": counts, **processed}), 200


# ---------------------------------------------------------------------------
# API — Webhook n8n (conservé pour compatibilité)
# ---------------------------------------------------------------------------

@app.route("/api/webhook", methods=["POST"])
def webhook():
    """Receive data from n8n or any external source."""
    data = request.get_json(silent=True) or {}
    emails_raw = data.get("emails", [])
    calendar_events = data.get("calendar", [])
    processed = _process_emails_and_tasks(emails_raw, calendar_events)
    return jsonify({"ok": True, **processed}), 200


# ---------------------------------------------------------------------------
# API — Divers
# ---------------------------------------------------------------------------

@app.route("/api/todo", methods=["GET"])
def api_todo():
    return jsonify(memory.get_tasks(done=0))


@app.route("/api/retrier", methods=["POST"])
def retrier():
    """Re-classify emails already in DB."""
    emails = memory.get_emails_by_status("pending")
    for mail in emails:
        result = ai_agent.classify_email(
            sender=mail["sender"],
            subject=mail["subject"],
            body=mail["body"],
        )
        memory.update_email_status(mail["message_id"], result["status"])
        memory.save_email({**mail, **result})
    return jsonify({"ok": True, "counts": memory.count_emails()})


@app.route("/api/email/<message_id>/status", methods=["POST"])
def update_email(message_id):
    body = request.get_json(silent=True) or {}
    memory.update_email_status(message_id, body.get("status", "pending"))
    return jsonify({"ok": True})


@app.route("/api/task/<int:task_id>/done", methods=["POST"])
def mark_done(task_id):
    memory.mark_task_done(task_id)
    return jsonify({"ok": True})


@app.route("/api/stats", methods=["GET"])
def stats():
    counts = memory.count_emails()
    return jsonify({"emails": counts, "tasks_pending": len(memory.get_tasks(done=0))})


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3005))
    app.run(host="0.0.0.0", port=port, debug=False)
