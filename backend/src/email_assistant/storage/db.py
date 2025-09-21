
# src/storage/db.py
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List
import json
import uuid
import logging
import datetime

from ..business.models import Email, Action, Summary, ActionPreference
from .vector_store import EmailVectorStore

logger = logging.getLogger(__name__)
DB_PATH = Path("assistant.db")


class Database:
    def __init__(
        self,
        db_path: Path | str = DB_PATH,
        *,
        vector_store: EmailVectorStore | None = None,
        auto_index: bool = True,
        check_same_thread: bool | None = None,
    ) -> None:
        connect_kwargs: Dict[str, Any] = {}
        if check_same_thread is not None:
            connect_kwargs["check_same_thread"] = check_same_thread
        self.conn = sqlite3.connect(str(db_path), **connect_kwargs)
        self.conn.row_factory = sqlite3.Row
        self._vector_store = vector_store
        self._auto_index = auto_index
        self._create_tables()
        if self._vector_store is not None and self._auto_index:
            self._initialise_vector_store()

    def _create_tables(self) -> None:
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
                received_at TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS actions (
                action_id TEXT PRIMARY KEY,
                mail_id TEXT,
                type TEXT NOT NULL CHECK (type IN ('send_email','create_event')),
                status TEXT NOT NULL CHECK (status IN ('pending','confirmed','rejected','modified','executed','failed')),
                payload JSON NOT NULL,
                result JSON,
                FOREIGN KEY (mail_id) REFERENCES emails(mail_id)
            );

            CREATE TABLE IF NOT EXISTS action_preferences (
                preference_id TEXT PRIMARY KEY,
                recipient_email TEXT NOT NULL,
                preference_key TEXT NOT NULL,
                preference_value TEXT NOT NULL,
                source_action_id TEXT,
                UNIQUE(recipient_email, preference_key),
                FOREIGN KEY (source_action_id) REFERENCES actions(action_id)
            );

            CREATE TABLE IF NOT EXISTS general_preferences (
                preference_key TEXT PRIMARY KEY,
                preference_value TEXT NOT NULL
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

    def _initialise_vector_store(self) -> None:
        if self._vector_store is None:
            return
        emails = self._load_all_emails()
        self._vector_store.rebuild(emails)

    def _load_all_emails(self) -> List[Email]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM emails ORDER BY received_at ASC")
        rows = cursor.fetchall()
        return [self._row_to_email(row) for row in rows]

    def fetch_all_emails(self) -> List[Email]:
        return self._load_all_emails()

    def insert_email(self, email: Email) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO emails (mail_id, external_id, thread_id, from_name, from_email, "to", "cc", subject, body, received_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                email.mail_id,
                email.external_id,
                email.thread_id,
                email.from_name,
                email.from_email,
                json.dumps(email.to),
                json.dumps(email.cc),
                email.subject,
                email.body,
                email.received_at.isoformat(),
            ),
        )
        self.conn.commit()
        self._notify_vector_store(email)

    def _notify_vector_store(self, email: Email) -> None:
        if self._vector_store is None:
            return
        try:
            self._vector_store.add_email(email)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("Failed to update vector store for %s: %s", email.mail_id, exc)

    def insert_action(self, action: Action) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO actions (action_id, mail_id, type, status, payload, result)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                action.action_id,
                action.mail_id,
                action.type,
                action.status,
                json.dumps(action.payload),
                json.dumps(action.result) if action.result else None,
            ),
        )
        self.conn.commit()

    def update_action(
        self,
        action_id: str,
        *,
        status: str | None = None,
        payload: Dict[str, Any] | None = None,
        result: Dict[str, Any] | None = None,
    ) -> None:
        cursor = self.conn.cursor()
        updates: List[str] = []
        params: List[Any] = []

        if status is not None:
            updates.append("status = ?")
            params.append(status)

        if payload is not None:
            updates.append("payload = ?")
            params.append(json.dumps(payload))

        if result is not None:
            updates.append("result = ?")
            params.append(json.dumps(result))

        if not updates:
            return

        sql = f"UPDATE actions SET {', '.join(updates)} WHERE action_id = ?"
        params.append(action_id)
        cursor.execute(sql, params)
        self.conn.commit()

    def upsert_action_preference(
        self,
        *,
        recipient_email: str,
        preference_key: str,
        preference_value: str,
        source_action_id: Optional[str] = None,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO action_preferences (
                preference_id, recipient_email, preference_key, preference_value, source_action_id
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(recipient_email, preference_key) DO UPDATE SET
                preference_value = excluded.preference_value,
                source_action_id = excluded.source_action_id
            """,
            (
                str(uuid.uuid4()),
                recipient_email.lower(),
                preference_key,
                preference_value,
                source_action_id,
            ),
        )
        self.conn.commit()

    def fetch_preferences_for_recipient(self, recipient_email: str) -> List[ActionPreference]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM action_preferences WHERE recipient_email = ?",
            (recipient_email.lower(),),
        )
        rows = cursor.fetchall()
        return [
            ActionPreference(
                preference_id=row["preference_id"],
                recipient_email=row["recipient_email"],
                preference_key=row["preference_key"],
                preference_value=row["preference_value"],
                source_action_id=row["source_action_id"],
            )
            for row in rows
        ]

    def upsert_general_preference(
        self,
        *,
        preference_key: str,
        preference_value: str,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO general_preferences (preference_key, preference_value)
            VALUES (?, ?)
            ON CONFLICT(preference_key) DO UPDATE SET
                preference_value = excluded.preference_value
            """,
            (
                preference_key,
                preference_value,
            ),
        )
        self.conn.commit()

    def fetch_general_preferences(self) -> Dict[str, str]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT preference_key, preference_value FROM general_preferences")
        return {row["preference_key"]: row["preference_value"] for row in cursor.fetchall()}

    def insert_summary(self, summary: Summary) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT 1 FROM emails WHERE thread_id = ? LIMIT 1",
            (summary.thread_id,),
        )
        exists = cursor.fetchone()
        if not exists:
            raise ValueError(f"Thread {summary.thread_id} does not exist in emails")

        cursor.execute(
            """
            INSERT INTO summaries (summary_id, thread_id, text)
            VALUES (?, ?, ?)
            """,
            (
                summary.summary_id,
                summary.thread_id,
                summary.text,
            ),
        )
        self.conn.commit()

    def fetch_email(self, mail_id: str) -> Optional[Email]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM emails WHERE mail_id = ?", (mail_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_email(row)

    def fetch_emails_for_thread(self, thread_id: str) -> List[Email]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM emails WHERE thread_id = ? ORDER BY received_at ASC",
            (thread_id,),
        )
        rows = cursor.fetchall()
        return [self._row_to_email(row) for row in rows]

    def fetch_thread_by_mail_id(self, mail_id: str) -> List[Email]:
        email = self.fetch_email(mail_id)
        if email is None:
            return []
        return self.fetch_emails_for_thread(email.thread_id)

    def fetch_action(self, action_id: str) -> Optional[Action]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM actions WHERE action_id = ?", (action_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Action(
            action_id=row["action_id"],
            mail_id=row["mail_id"],
            type=row["type"],
            status=row["status"],
            payload=json.loads(row["payload"]),
            result=json.loads(row["result"]) if row["result"] else None,
        )

    def fetch_summary(self, summary_id: str) -> Optional[Summary]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM summaries WHERE summary_id = ?", (summary_id,))
        row = cursor.fetchone()
        if not row:
            return None
        return Summary(
            summary_id=row["summary_id"],
            thread_id=row["thread_id"],
            text=row["text"],
        )

    def fetch_summaries_for_thread(self, thread_id: str) -> List[Summary]:
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM summaries WHERE thread_id = ?", (thread_id,))
        rows = cursor.fetchall()
        return [
            Summary(
                summary_id=row["summary_id"],
                thread_id=row["thread_id"],
                text=row["text"],
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_email(row: sqlite3.Row) -> Email:
        return Email(
            mail_id=row["mail_id"],
            external_id=row["external_id"],
            thread_id=row["thread_id"],
            from_name=row["from_name"],
            from_email=row["from_email"],
            to=json.loads(row["to"]) if row["to"] else [],
            cc=json.loads(row["cc"]) if row["cc"] else [],
            subject=row["subject"],
            body=row["body"],
            received_at=datetime.datetime.fromisoformat(row["received_at"]),
        )
