"""Command-line entry point for the email assistant."""
from .storage.db import Database
from .business.models import Email, Action
import uuid

def main() -> None:
    db = Database()
    # Create and insert an Email
    email = Email(
        mail_id=str(uuid.uuid4()),
        thread_id="thread-001",
        from_name="Alice",
        from_email="alice@example.com",
        to=["me@example.com"],
        subject="Project Update",
        body="Hi, can we move the meeting?",
    )
    db.insert_email(email)
    action = Action(
        action_id=str(uuid.uuid4()),
        mail_id=email.mail_id,
        type="send_email",
        status="pending",
        payload={"to": ["alice@example.com"], "subject": "Re: Project Update", "body": "Sure!"},
    )
    db.insert_action(action)
    fetched_email = db.fetch_email(email.mail_id)
    print(fetched_email)

    fetched_action = db.fetch_action(action.action_id)
    print(fetched_action)


if __name__ == "__main__":
    main()
