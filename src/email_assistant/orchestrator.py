"""Coordinates the different agents that act on incoming emails."""
from __future__ import annotations

import uuid
from itertools import chain
from typing import Any, Dict, Sequence
from langfuse import observe, get_client

from .agents import (
    EmailClassification,
    EmailClassifierAgent,
    EmailDrafterAgent,
    EmailDraft,
    EmailSchedulerAgent,
    EmailSummarizerAgent,
    ProposedEvent,
)
from .business.models import Action, DraftingPreferences, Email, Summary
from .storage.db import Database
from .logging_utils import logs_handler

logger = logs_handler.get_logger()

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

    @observe()
    def process_new_email(self, email: Email) -> Dict[str, Any]:
        langfuse = get_client()
        session_id = uuid.uuid4()
        langfuse.update_current_trace(session_id=f"{session_id}")

        self.db.insert_email(email)
        thread = self.db.fetch_emails_for_thread(email.thread_id)
        print(f"fetched {len(thread)} emails")
        classification: EmailClassification = self.classifier.classify(thread)
        decisions = self.classifier.decisions(classification)

        proposed_actions = []
        summary_text = None

        if decisions["needs_summary"]:
            summary = self.summarizer.summarize(thread)
            summary_text = summary.summary
            summary_record = Summary(
                summary_id=str(uuid.uuid4()),
                thread_id=email.thread_id,
                text=summary_text,
            )
            self.db.insert_summary(summary_record)

        draft_preferences: DraftingPreferences | None = None
        if decisions["needs_draft"]:
            draft_preferences = self._build_drafting_preferences(thread)
            logger.debug(f"Preferences applying to this email: {draft_preferences}")
            draft: EmailDraft = self.drafter.draft(
                thread,
                preferences=draft_preferences,
            )
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
            event: ProposedEvent = self.scheduler.propose_event(thread)
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

    @observe()
    def _build_drafting_preferences(self, thread: Sequence[Email]) -> DraftingPreferences | None:
        general_preferences = self.db.fetch_general_preferences()
        preferences = DraftingPreferences.from_general_preferences(general_preferences)

        recipient_emails = self._infer_reply_recipients(thread)
        logger.debug(f"recipient emails: {recipient_emails}")
        formal_tone_value: str | None = None ## Formal >> casual
        for email_address in recipient_emails:
            recipient_preferences = self.db.fetch_preferences_for_recipient(email_address)
            if not recipient_preferences:
                continue

            logger.debug(f"{email_address} : {recipient_preferences}")
            preferences.apply_action_preferences(recipient_preferences)

            if formal_tone_value is None:
                ## check if this recipient has formal tone preference
                tone_pref = next(
                    (p for p in recipient_preferences if p.preference_key == "tone"),
                    None,
                )
                if tone_pref and "formal" in tone_pref.preference_value.lower():
                    formal_tone_value = tone_pref.preference_value
                    logger.debug(f"Formal tone preference will be applied because of {email_address}")

        if formal_tone_value:
            preferences.tone = formal_tone_value

        return None if preferences.is_empty() else preferences

    @staticmethod
    def _infer_reply_recipients(thread: Sequence[Email]) -> list[str]:
        if not thread:
            return []

        latest = thread[-1]
        sources = chain(
            [latest.from_email] if latest.from_email else [],
            latest.to or [],
            latest.cc or [],
        )

        return list(dict.fromkeys(addr.lower() for addr in sources if addr))
