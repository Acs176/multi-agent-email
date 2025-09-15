# src/storage/db.py
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List
import json
from datetime import datetime

DB_PATH = "./assistant.db"

class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        cursor.executescript(
            """
            CREATE TABLE IF NOT EXISTS emails (
                mail_id TEXT PRIMARY KEY,
                external_id TEXT,
                thread_id TEXT,
                from_name TEXT,
                from_email TEXT,
                "to" JSON,
                "cc" JSON,
                subject TEXT,
                body TEXT,
                received_at TIMESTAMP,
                raw JSON
            );

            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY,
                mail_id TEXT,
                type TEXT NOT NULL CHECK (type IN ('send_email','create_event')),
                status TEXT NOT NULL CHECK (status IN ('pending','confirmed','rejected','modified','executed','failed')),
                payload JSON NOT NULL,
                result JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (mail_id) REFERENCES emails(mail_id)
            );

            CREATE TABLE IF NOT EXISTS summaries (
                summary_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        self.conn.commit()

    # ---------- Insert helpers ----------
    def insert_email(self, mail: Dict[str, Any]):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO emails (mail_id, external_id, thread_id, from_name, from_email, "to", "cc", subject, body, received_at, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mail["mail_id"],
                mail.get("external_id"),
                mail.get("thread_id"),
                mail.get("from_name"),
                mail.get("from_email"),
                json.dumps(mail.get("to", [])),
                json.dumps(mail.get("cc", [])),
                mail.get("subject"),
                mail.get("body"),
                mail.get("received_at", datetime.utcnow().isoformat()),
                json.dumps(mail.get("raw", {})),
            ),
        )
        self.conn.commit()

    def insert_action(self, action: Dict[str, Any]):
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO actions (action_id, mail_id, type, status, payload, result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                action["action_id"],
                action.get("mail_id"),
                action["type"],
                action["status"],
                json.dumps(action["payload"]),
                json.dumps(action.get("result")),
            ),
        )
        self.conn.commit()

    def insert_summary(self, summary: Dict[str, Any]):
        cursor = self.conn.cursor()

        # Check if the thread exists in emails
        cursor.execute(
            "SELECT 1 FROM emails WHERE thread_id = ? LIMIT 1",
            (summary["thread_id"],),
        )
        exists = cursor.fetchone()
        if not exists:
            raise ValueError(f"Thread {summary['thread_id']} does not exist in emails")

        cursor.execute(
            """
            INSERT INTO summaries (summary_id, thread_id, text)
            VALUES (?, ?, ?)
            """,
            (
                summary["summary_id"],
                summary["thread_id"],
                summary["text"],
            ),
        )
        self.conn.commit()

    # ---------- Fetch helpers ----------
    def fetch_email(self, mail_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM emails WHERE mail_id = ?", (mail_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,))
        row = cursor.fetchone()
        if row:
            d = dict(row)
            d["payload"] = json.loads(d["payload"])
            d["result"] = json.loads(d["result"]) if d["result"] else None
            return d
        return None

    def fetch_actions_for_email(self, mail_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM actions WHERE mail_id = ?", (mail_id,))
        rows = cursor.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["payload"] = json.loads(d["payload"])
            d["result"] = json.loads(d["result"]) if d["result"] else None
            results.append(d)
        return results

    def fetch_summary(self, summary_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM summaries WHERE summary_id = ?", (summary_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def fetch_summaries_for_thread(self, thread_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM summaries WHERE thread_id = ?", (thread_id,))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
