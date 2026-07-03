import os
import base64
from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _get_creds() -> Credentials:
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("GOOGLE_REFRESH_TOKEN"),
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        token_uri="https://oauth2.googleapis.com/token",
        scopes=SCOPES,
    )
    # Force refresh to get a valid access token
    creds.refresh(Request())
    return creds


def _extract_body(payload: dict) -> str:
    """Recursively extract plain text body from a Gmail message payload."""
    mime = payload.get("mimeType", "")

    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

    if mime.startswith("multipart/"):
        for part in payload.get("parts", []):
            text = _extract_body(part)
            if text:
                return text

    # HTML fallback
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            raw = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            # Very light HTML strip
            import re
            return re.sub(r"<[^>]+>", " ", raw)

    return ""


def fetch_emails(hours_back: int = 24, max_results: int = 30) -> list:
    """Return list of unread emails from the last `hours_back` hours."""
    creds = _get_creds()
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)

    since_ts = int(
        (datetime.now(timezone.utc) - timedelta(hours=hours_back)).timestamp()
    )
    query = f"in:inbox is:unread after:{since_ts}"

    result = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()

    raw_messages = result.get("messages", [])
    emails = []

    for msg in raw_messages:
        detail = service.users().messages().get(
            userId="me", messageId=msg["id"], format="full"
        ).execute()

        headers = {
            h["name"].lower(): h["value"]
            for h in detail.get("payload", {}).get("headers", [])
        }

        body = _extract_body(detail.get("payload", {}))

        emails.append({
            "id": msg["id"],
            "sender": headers.get("from", ""),
            "subject": headers.get("subject", "(sans sujet)"),
            "body": body[:3000],
            "date": headers.get("date", ""),
        })

    return emails


def fetch_calendar_events(days_ahead: int = 7) -> list:
    """Return upcoming events from Google Calendar."""
    creds = _get_creds()
    service = build("calendar", "v3", credentials=creds, cache_discovery=False)

    now = datetime.now(timezone.utc)
    time_min = now.isoformat()
    time_max = (now + timedelta(days=days_ahead)).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=20,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = []
    for ev in events_result.get("items", []):
        start = ev.get("start", {})
        date_str = start.get("date") or start.get("dateTime", "")
        time_str = start.get("dateTime", "")[11:16] if "T" in start.get("dateTime", "") else ""
        events.append({
            "title": ev.get("summary", "(sans titre)"),
            "date": date_str[:10],
            "time": time_str,
        })

    return events


def google_creds_configured() -> bool:
    return all([
        os.getenv("GOOGLE_CLIENT_ID"),
        os.getenv("GOOGLE_CLIENT_SECRET"),
        os.getenv("GOOGLE_REFRESH_TOKEN"),
    ])
