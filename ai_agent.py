import os
import json
from openai import OpenAI
from memory import is_known_spam, add_spam_sender

MODEL = "gpt-4o-mini"
_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def _chat(messages: list, temperature: float = 0.3) -> str:
    response = _get_client().chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
    )
    return response.choices[0].message.content.strip()


def classify_email(sender: str, subject: str, body: str) -> dict:
    """Returns {status, summary, draft_reply} for a given email."""
    if is_known_spam(sender):
        return {"status": "spam", "summary": "Expéditeur spam connu.", "draft_reply": ""}

    prompt = f"""Tu es JARVIS, l'assistant IA personnel. Analyse cet email et réponds en JSON strict.

Expéditeur: {sender}
Sujet: {subject}
Corps (premiers 1500 caractères): {body[:1500]}

Retourne UNIQUEMENT ce JSON (pas de markdown, pas de texte autour) :
{{
  "status": "spam" | "auto" | "pending",
  "summary": "résumé en 1 ligne max 120 caractères",
  "draft_reply": "brouillon de réponse en français si status=pending, sinon chaîne vide",
  "is_new_spam_sender": true | false
}}

Règles :
- spam = newsletters, pub, notifications auto sans action requise
- auto = accusés de réception, confirmations où une réponse automatique suffit
- pending = emails nécessitant une vraie décision ou réponse personnelle
- Pour pending, écris un brouillon de réponse professionnel et chaleureux en français"""

    try:
        raw = _chat([{"role": "user", "content": prompt}])
        data = json.loads(raw)
        if data.get("is_new_spam_sender") and data.get("status") == "spam":
            add_spam_sender(sender, reason="Détecté par IA")
        return {
            "status": data.get("status", "pending"),
            "summary": data.get("summary", ""),
            "draft_reply": data.get("draft_reply", ""),
        }
    except (json.JSONDecodeError, Exception):
        return {"status": "pending", "summary": "Analyse impossible.", "draft_reply": ""}


def extract_tasks(emails: list, calendar_events: list) -> list:
    """Extract tasks from emails and calendar events. Returns list of task dicts."""
    emails_text = "\n".join(
        f"- De: {e.get('sender','')} | Sujet: {e.get('subject','')} | Résumé: {e.get('summary','')}"
        for e in emails[:20]
    )
    events_text = "\n".join(
        f"- {ev.get('title','')} le {ev.get('date','')} à {ev.get('time','')}"
        for ev in calendar_events[:20]
    )

    prompt = f"""Tu es JARVIS. À partir des emails et événements agenda ci-dessous, génère une liste de tâches pour aujourd'hui.

EMAILS RÉCENTS :
{emails_text or "Aucun email."}

ÉVÉNEMENTS AGENDA :
{events_text or "Aucun événement."}

Retourne UNIQUEMENT un tableau JSON (pas de markdown) :
[
  {{
    "title": "titre court de la tâche",
    "description": "détails optionnels",
    "priority": "URGENT" | "AUJOURD'HUI" | "CETTE SEMAINE",
    "source": "email" | "agenda" | "ia",
    "due_date": "YYYY-MM-DD ou chaîne vide"
  }}
]

Règles de priorité :
- URGENT = deadline aujourd'hui, demande explicite urgente, réunion dans moins de 2h
- AUJOURD'HUI = à faire aujourd'hui mais pas urgence critique
- CETTE SEMAINE = important mais peut attendre quelques jours"""

    try:
        raw = _chat([{"role": "user", "content": prompt}], temperature=0.2)
        tasks = json.loads(raw)
        return tasks if isinstance(tasks, list) else []
    except Exception:
        return []


def generate_auto_reply(sender: str, subject: str, body: str) -> str:
    """Generate a short automatic reply for auto-classified emails."""
    prompt = f"""Tu es JARVIS. Génère un accusé de réception court et professionnel en français pour cet email.

De: {sender}
Sujet: {subject}

Réponse courte (2-3 phrases max), ton professionnel mais chaleureux."""
    try:
        return _chat([{"role": "user", "content": prompt}])
    except Exception:
        return "Bien reçu, merci."
