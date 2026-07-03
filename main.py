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

# ---------------------------------------------------------------------------
# Pages HTML
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    emails = memory.get_emails_by_status("pending")
    counts = memory.count_emails()
    return render_template("index.html", emails=emails, counts=counts)


@app.route("/todo")
def todo():
    tasks = memory.get_tasks(done=0)
    return render_template("todo.html", tasks=tasks)


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

@app.route("/api/webhook", methods=["POST"])
def webhook():
    """Receive data from n8n (Gmail + Google Calendar)."""
    data = request.get_json(silent=True) or {}

    emails_raw = data.get("emails", [])
    calendar_events = data.get("calendar", [])

    processed = {"classified": 0, "tasks_created": 0, "errors": []}

    # --- Classify each email ---
    for mail in emails_raw:
        try:
            result = ai_agent.classify_email(
                sender=mail.get("sender", ""),
                subject=mail.get("subject", ""),
                body=mail.get("body", ""),
            )
            memory.save_email({
                "message_id": mail.get("id", mail.get("subject", "no-id")),
                "sender": mail.get("sender", ""),
                "subject": mail.get("subject", ""),
                "body": mail.get("body", ""),
                "summary": result["summary"],
                "draft_reply": result["draft_reply"],
                "status": result["status"],
                "received_at": mail.get("date", ""),
            })
            processed["classified"] += 1
        except Exception as e:
            processed["errors"].append(str(e))

    # --- Extract tasks ---
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

    return jsonify({"ok": True, **processed}), 200


@app.route("/api/todo", methods=["GET"])
def api_todo():
    tasks = memory.get_tasks(done=0)
    return jsonify(tasks)


@app.route("/api/retrier", methods=["POST"])
def retrier():
    """Re-sort emails already in DB (re-classify pending ones)."""
    emails = memory.get_emails_by_status("pending")
    for mail in emails:
        result = ai_agent.classify_email(
            sender=mail["sender"],
            subject=mail["subject"],
            body=mail["body"],
        )
        memory.update_email_status(mail["message_id"], result["status"])
        memory.save_email({**mail, **result})
    counts = memory.count_emails()
    return jsonify({"ok": True, "counts": counts})


@app.route("/api/email/<message_id>/status", methods=["POST"])
def update_email(message_id):
    body = request.get_json(silent=True) or {}
    status = body.get("status", "pending")
    memory.update_email_status(message_id, status)
    return jsonify({"ok": True})


@app.route("/api/task/<int:task_id>/done", methods=["POST"])
def mark_done(task_id):
    memory.mark_task_done(task_id)
    return jsonify({"ok": True})


@app.route("/api/stats", methods=["GET"])
def stats():
    counts = memory.count_emails()
    tasks = memory.get_tasks(done=0)
    return jsonify({"emails": counts, "tasks_pending": len(tasks)})


# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 3005))
    app.run(host="0.0.0.0", port=port, debug=False)
