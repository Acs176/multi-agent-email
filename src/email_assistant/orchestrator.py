"""Coordinates the different agents that act on incoming emails."""
from __future__ import annotations

import uuid
from typing import Any, Dict

from .agents import (
    EmailClassification,
    EmailClassifierAgent,
    EmailDrafterAgent,
    EmailDraft,
    EmailSchedulerAgent,
    EmailSummarizerAgent,
    ProposedEvent,
)
from .business.models import Action, Email, Summary
from .storage.db import Database


class Orchestrator:
    def __init__(
        self,
        *,
        classifier: EmailClassifierAgent,
        drafter: EmailDrafterAgent,
        scheduler: EmailSchedulerAgent,
        summarizer: EmailSummarizerAgent,
        database: Database | None = None,
    ) -> None:
        self.db = database or Database()
        self.classifier = classifier
        self.drafter = drafter
        self.scheduler = scheduler
        self.summarizer = summarizer

    def process_new_email(self, email: Email) -> Dict[str, Any]:
        self.db.insert_email(email)

        classification: EmailClassification = self.classifier.classify(email)
        decisions = self.classifier.decisions(classification)

        proposed_actions = []
        summary_text = None

        if decisions["needs_summary"]:
            summary_text = self.summarizer.summarize(email).summary
            summary = Summary(
                summary_id=str(uuid.uuid4()),
                thread_id=email.thread_id,
                text=summary_text,
            )
            self.db.insert_summary(summary)

        if decisions["needs_draft"]:
            draft: EmailDraft = self.drafter.draft(email)
            action = Action(
                action_id=str(uuid.uuid4()),
                mail_id=email.mail_id,
                type="send_email",
                status="pending",
                payload=draft.model_dump(),
            )
            self.db.insert_action(action)
            proposed_actions.append(action.model_dump())

        if decisions["needs_schedule"]:
            event: ProposedEvent = self.scheduler.propose_event(email)
            action = Action(
                action_id=str(uuid.uuid4()),
                mail_id=email.mail_id,
                type="create_event",
                status="pending",
                payload=event.model_dump(),
            )
            self.db.insert_action(action)
            proposed_actions.append(action.model_dump())

        return {
            "mail_id": email.mail_id,
            "summary": {"text": summary_text} if summary_text else None,
            "proposed_actions": proposed_actions,
            "classification": {
                "probabilities": classification.as_dict(),
                "decisions": decisions,
            },
        }
