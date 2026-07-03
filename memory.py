import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager

DB_PATH = "jarvis.db"


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                sender TEXT,
                subject TEXT,
                body TEXT,
                summary TEXT,
                draft_reply TEXT,
                status TEXT DEFAULT 'pending',
                received_at TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                priority TEXT DEFAULT 'CETTE SEMAINE',
                source TEXT,
                done INTEGER DEFAULT 0,
                due_date TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS spam_senders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                name TEXT,
                reason TEXT,
                added_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            );
        """)


# --- Emails ---

def save_email(data: dict):
    with get_db() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO emails
                (message_id, sender, subject, body, summary, draft_reply, status, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM emails WHERE status = ? ORDER BY received_at DESC",
            (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def update_email_status(message_id: str, status: str):
    with get_db() as conn:
        conn.execute(
            "UPDATE emails SET status = ? WHERE message_id = ?",
            (status, message_id)
        )


def count_emails() -> dict:
    with get_db() as conn:
        spam = conn.execute("SELECT COUNT(*) FROM emails WHERE status='spam'").fetchone()[0]
        auto = conn.execute("SELECT COUNT(*) FROM emails WHERE status='auto'").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*) FROM emails WHERE status='pending'").fetchone()[0]
        return {"spam": spam, "auto": auto, "pending": pending}


# --- Tasks ---

def save_task(data: dict) -> int:
    with get_db() as conn:
        cur = conn.execute("""
            INSERT INTO tasks (title, description, priority, source, due_date)
            VALUES (?, ?, ?, ?, ?)
        """, (
            data.get("title", ""),
            data.get("description", ""),
            data.get("priority", "CETTE SEMAINE"),
            data.get("source", ""),
            data.get("due_date", ""),
        ))
        return cur.lastrowid


def get_tasks(done: int = 0) -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE done = ? ORDER BY CASE priority WHEN 'URGENT' THEN 1 WHEN 'AUJOURD''HUI' THEN 2 ELSE 3 END, created_at DESC",
            (done,)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_task_done(task_id: int):
    with get_db() as conn:
        conn.execute("UPDATE tasks SET done = 1 WHERE id = ?", (task_id,))


def clear_tasks():
    with get_db() as conn:
        conn.execute("DELETE FROM tasks WHERE done = 0")


# --- Spam senders ---

def add_spam_sender(email: str, name: str = "", reason: str = ""):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO spam_senders (email, name, reason) VALUES (?, ?, ?)",
            (email, name, reason)
        )


def is_known_spam(email: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT 1 FROM spam_senders WHERE email = ?", (email,)
        ).fetchone()
        return row is not None


def get_spam_senders() -> list:
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM spam_senders ORDER BY added_at DESC").fetchall()
        return [dict(r) for r in rows]


# --- Preferences ---

def set_preference(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO preferences (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, value)
        )


def get_preference(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM preferences WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default
