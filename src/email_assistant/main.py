"""Command-line entry point for the email assistant."""
from .storage.db import Database

def main() -> None:
    db = Database()
    db.insert_email({
        "mail_id": "msg-001",
        "thread_id": "thread-abc",
        "from_name": "Alice",
        "from_email": "alice@example.com",
        "to": ["me@example.com"],
        "cc": [],
        "subject": "Project Update",
        "body": "Let's move the meeting",
        "received_at": "2025-09-15T12:34:56Z",
    })
    db.insert_summary({
        "summary_id": "sum-123",
        "thread_id": "thread-abc",
        "text": "Alice suggested moving the meeting."
    })

    # TEST: This will raise ValueError since thread doesn't exist
    db.insert_summary({
        "summary_id": "sum-999",
        "thread_id": "nonexistent-thread",
        "text": "This should fail."
    })


if __name__ == "__main__":
    main()
