# src/orchestrator.py
import uuid
from typing import Dict, Any

from .storage.db import Database
from .business.models import Email, Summary, Action

class Orchestrator:
    def __init__(self):
        self.db = Database()
        # self.classifier = Classifier()
        # self.summarizer = Summarizer()
        # self.drafter = Drafter()
        # self.scheduler = Scheduler()

    def process_new_email(self, email: Email) -> Dict[str, Any]:
        self.db.insert_email(email)

        # Classify
        labels = self.classifier.classify(email)

        proposed_actions = []
        summary_text = None

        # Summarizer
        if labels["needs_summary"]:
            summary_text = self.summarizer.summarize(email)
            summary = Summary(
                summary_id=str(uuid.uuid4()),
                thread_id=email.thread_id,
                text=summary_text,
            )
            self.db.insert_summary(summary)

        # Drafter
        if labels["needs_draft"]:
            draft = self.drafter.draft(email)
            action = Action(
                action_id=str(uuid.uuid4()),
                mail_id=email.mail_id,
                type="send_email",
                status="pending",
                payload=draft,
            )
            self.db.insert_action(action)
            ## TODO: Check if it works
            proposed_actions.append(action.model_dump())

        # Scheduler
        if labels["needs_schedule"]:
            event = self.scheduler.propose_event(email)
            action = Action(
                action_id=str(uuid.uuid4()),
                mail_id=email.mail_id,
                type="create_event",
                status="pending",
                payload=event,
            )
            self.db.insert_action(action)
            proposed_actions.append(action.model_dump())

        return {
            "mail_id": email.mail_id,
            "summary": {"text": summary_text} if summary_text else None,
            "proposed_actions": proposed_actions
        }
