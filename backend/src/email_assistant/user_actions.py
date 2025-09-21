"""User-facing helpers to review proposed actions."""
from __future__ import annotations

import copy
import datetime
import json
import logging
import os
import uuid
from typing import Any, Dict, List, Optional, Tuple

from .agents.preferences import PreferenceExtraction, PreferenceExtractionAgent
from .business.models import Email, Action
from .storage.db import Database


logger = logging.getLogger(__name__)


def _prompt_payload_update(default_payload: Dict[str, Any]) -> Dict[str, Any]:
    print("Current payload:")
    print(json.dumps(default_payload, indent=2))
    print("Enter updated payload as JSON (press Enter to keep current):")
    while True:
        user_input = input("> ").strip()
        if not user_input:
            return default_payload
        try:
            payload = json.loads(user_input)
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON: {exc}")
            continue
        if not isinstance(payload, dict):
            print("Payload must be a JSON object.")
            continue
        return payload


def _prompt_apply_to_general() -> bool:
    while True:
        choice = input("Apply extracted preferences to general profile? (y/N): ").strip().lower()
        if choice in {"", "n", "no"}:
            return False
        if choice in {"y", "yes"}:
            return True
        print("Please answer 'y' or 'n'.")


def approve_action(action: Action, db: Database) -> Action:
    db.update_action(action.action_id, status="executed")
    action.status = "executed"
    _store_sent_email(action=action, db=db, payload=action.payload or {})
    return action


def reject_action(action: Action, db: Database) -> Action:
    db.update_action(action.action_id, status="rejected")
    action.status = "rejected"
    return action


def modify_action(
    action: Action,
    db: Database,
    updated_payload: Dict[str, Any],
    *,
    original_payload: Dict[str, Any],
    preference_extractor: PreferenceExtractionAgent | None = None,
    apply_to_general_preferences: bool = False,
) -> Action:
    db.update_action(
        action_id=action.action_id,
        status="executed",
        payload=updated_payload,
    )
    action.payload = updated_payload
    action.status = "executed"
    _store_sent_email(action=action, db=db, payload=updated_payload)
    _record_preferences_from_modification(
        action=action,
        db=db,
        original_payload=original_payload,
        updated_payload=updated_payload,
        preference_extractor=preference_extractor,
        apply_to_general_preferences=apply_to_general_preferences,
    )
    return action

def _normalize_recipients(raw: Any) -> List[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        candidates = raw
    else:
        candidates = str(raw).split(",")
    normalized: List[str] = []
    for candidate in candidates:
        address = str(candidate).strip()
        if address:
            normalized.append(address)
    return normalized

def _resolve_sender_identity() -> Tuple[str, str]:
    name = os.getenv("USER_EMAIL", "example@example.com")
    configured_email = os.getenv("USER_NAME", "Adrian")
    if configured_email:
        return name, configured_email


def _store_sent_email(*, action: Action, db: Database, payload: Dict[str, Any]) -> None:
    if action.type != "send_email":
        return

    payload = payload or {}
    if not isinstance(payload, dict):
        logger.warning("Ignoring non-dict payload for action %s", action.action_id)
        payload = {}

    original_mail_id = action.mail_id
    if not original_mail_id:
        return

    original_email = db.fetch_email(original_mail_id)
    if original_email is None:
        logger.warning(
            "Unable to store sent email for action %s: mail %s not found",
            action.get("action_id"),
            original_mail_id,
        )
        return

    to_recipients = _normalize_recipients(payload.get("to"))
    cc_recipients = _normalize_recipients(payload.get("cc"))
    subject = payload.get("subject")
    body = str(payload.get("body", ""))
    sender_name, sender_email = _resolve_sender_identity()

    sent_email = Email(
        mail_id=str(uuid.uuid4()),
        external_id=None,
        thread_id=original_email.thread_id,
        from_name=sender_name,
        from_email=sender_email,
        to=to_recipients,
        cc=cc_recipients,
        subject=subject,
        body=body,
        received_at=datetime.datetime.now(datetime.timezone.utc),
    )

    try:
        db.insert_email(sent_email)
    except Exception as exc:
        logger.exception("Failed to store sent email for action %s: %s", action.action_id, exc)




def _record_preferences_from_modification(
    *,
    action: Action,
    db: Database,
    original_payload: Dict[str, Any],
    updated_payload: Dict[str, Any],
    preference_extractor: PreferenceExtractionAgent | None,
    apply_to_general_preferences: bool,
) -> None:
    if action.type != "send_email" or preference_extractor is None:
        return

    extraction = _extract_preferences_from_modification(
        original_payload=original_payload,
        updated_payload=updated_payload,
        preference_extractor=preference_extractor,
    )
    preferences = extraction.model_dump(exclude_none=True)
    if not preferences:
        return

    if apply_to_general_preferences:
        for key, value in preferences.items():
            db.upsert_general_preference(
                preference_key=key,
                preference_value=str(value),
            )
        return

    to_recipients = _extract_recipient_emails(updated_payload.get("to"))
    if not to_recipients:
        return

    for recipient in to_recipients:
        for key, value in preferences.items():
            db.upsert_action_preference(
                recipient_email=recipient,
                preference_key=key,
                preference_value=str(value),
                source_action_id=action.action_id,
            )


def _extract_preferences_from_modification(
    *,
    original_payload: Dict[str, Any],
    updated_payload: Dict[str, Any],
    preference_extractor: PreferenceExtractionAgent,
) -> PreferenceExtraction:
    return preference_extractor.extract(
        original_payload=original_payload,
        updated_payload=updated_payload,
    )


def _extract_recipient_emails(raw_recipients: Any) -> List[str]:
    if not raw_recipients:
        return []

    if isinstance(raw_recipients, list):
        candidates = raw_recipients
    else:
        candidates = [piece.strip() for piece in str(raw_recipients).split(",")]

    emails = [candidate.lower() for candidate in candidates if candidate]
    return emails


