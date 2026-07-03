import os
import json
from datetime import datetime
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")
USE_POSTGRES = bool(DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
else:
    import sqlite3

SQLITE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "jarvis.db")


@contextmanager
def get_db():
    if USE_POSTGRES:
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        conn.autocommit = False
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()


def _fetchall(cursor) -> list:
    rows = cursor.fetchall()
    if USE_POSTGRES:
        return [dict(r) for r in rows]
    return [dict(r) for r in rows]


def _placeholder(n: int = 1) -> str:
    return "%s" if USE_POSTGRES else "?"


def _serial() -> str:
    return "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"


def _now() -> str:
    return "NOW()" if USE_POSTGRES else "datetime('now')"


def init_db():
    serial = _serial()
    now = _now()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS emails (
                id {serial},
                message_id TEXT UNIQUE,
                sender TEXT,
                subject TEXT,
                body TEXT,
                summary TEXT,
                draft_reply TEXT,
                status TEXT DEFAULT 'pending',
                received_at TEXT,
                created_at TEXT DEFAULT ({now})
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS tasks (
                id {serial},
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT DEFAULT 'CETTE SEMAINE',
                source TEXT,
                done INTEGER DEFAULT 0,
                due_date TEXT,
                created_at TEXT DEFAULT ({now})
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS spam_senders (
                id {serial},
                email TEXT UNIQUE,
                name TEXT,
                reason TEXT,
                added_at TEXT DEFAULT ({now})
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT ({now})
            )
        """)


# --- Emails ---

def save_email(data: dict):
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(f"""
                INSERT INTO emails
                    (message_id, sender, subject, body, summary, draft_reply, status, received_at)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p})
                ON CONFLICT (message_id) DO UPDATE SET
                    summary = EXCLUDED.summary,
                    draft_reply = EXCLUDED.draft_reply,
                    status = EXCLUDED.status
            """, (
                data.get("message_id", ""),
                data.get("sender", ""),
                data.get("subject", ""),
                data.get("body", ""),
                data.get("summary", ""),
                data.get("draft_reply", ""),
                data.get("status", "pending"),
                data.get("received_at", datetime.now().isoformat()),
            ))
        else:
            conn.execute(f"""
                INSERT OR REPLACE INTO emails
                    (message_id, sender, subject, body, summary, draft_reply, status, received_at)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p})
            """, (
                data.get("message_id", ""),
                data.get("sender", ""),
                data.get("subject", ""),
                data.get("body", ""),
                data.get("summary", ""),
                data.get("draft_reply", ""),
                data.get("status", "pending"),
                data.get("received_at", datetime.now().isoformat()),
            ))


def get_emails_by_status(status: str) -> list:
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT * FROM emails WHERE status = {p} ORDER BY received_at DESC",
            (status,)
        )
        return _fetchall(cur)


def update_email_status(message_id: str, status: str):
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            f"UPDATE emails SET status = {p} WHERE message_id = {p}",
            (status, message_id)
        )


def count_emails() -> dict:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) as c FROM emails WHERE status='spam'")
        spam = cur.fetchone()
        cur.execute("SELECT COUNT(*) as c FROM emails WHERE status='auto'")
        auto = cur.fetchone()
        cur.execute("SELECT COUNT(*) as c FROM emails WHERE status='pending'")
        pending = cur.fetchone()
        def val(r):
            if isinstance(r, dict): return r["c"]
            return r[0]
        return {"spam": val(spam), "auto": val(auto), "pending": val(pending)}


# --- Tasks ---

def save_task(data: dict) -> int:
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO tasks (title, description, priority, source, due_date)
            VALUES ({p},{p},{p},{p},{p})
        """, (
            data.get("title", ""),
            data.get("description", ""),
            data.get("priority", "CETTE SEMAINE"),
            data.get("source", ""),
            data.get("due_date", ""),
        ))
        if USE_POSTGRES:
            cur.execute("SELECT lastval()")
            return cur.fetchone()["lastval"]
        return cur.lastrowid


def get_tasks(done: int = 0) -> list:
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"""
            SELECT * FROM tasks WHERE done = {p}
            ORDER BY
                CASE priority
                    WHEN 'URGENT' THEN 1
                    WHEN 'AUJOURD''HUI' THEN 2
                    ELSE 3
                END,
                created_at DESC
        """, (done,))
        return _fetchall(cur)


def mark_task_done(task_id: int):
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"UPDATE tasks SET done = 1 WHERE id = {p}", (task_id,))


def clear_tasks():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM tasks WHERE done = 0")


# --- Spam senders ---

def add_spam_sender(email: str, name: str = "", reason: str = ""):
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO spam_senders (email, name, reason) VALUES ({p},{p},{p}) ON CONFLICT (email) DO NOTHING",
                (email, name, reason)
            )
        else:
            conn.execute(
                f"INSERT OR IGNORE INTO spam_senders (email, name, reason) VALUES ({p},{p},{p})",
                (email, name, reason)
            )


def is_known_spam(email: str) -> bool:
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT 1 FROM spam_senders WHERE email = {p}", (email,))
        return cur.fetchone() is not None


def get_spam_senders() -> list:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM spam_senders ORDER BY added_at DESC")
        return _fetchall(cur)


# --- Preferences ---

def set_preference(key: str, value: str):
    p = _placeholder()
    now = _now()
    with get_db() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                f"INSERT INTO preferences (key, value, updated_at) VALUES ({p},{p},{now}) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = {now}",
                (key, value)
            )
        else:
            conn.execute(
                f"INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES ({p},{p},{now})",
                (key, value)
            )


def get_preference(key: str, default: str = "") -> str:
    p = _placeholder()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(f"SELECT value FROM preferences WHERE key = {p}", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        return row["value"] if isinstance(row, dict) else row[0]
