"""User-facing helpers to review proposed actions."""
from __future__ import annotations

import copy
import json
from typing import Any, Dict, List

from .agents.preferences import PreferenceExtraction, PreferenceExtractionAgent
from .storage.db import Database


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


def approve_action(action: Dict[str, Any], db: Database) -> Dict[str, Any]:
    db.update_action(action["action_id"], status="executed")
    action["status"] = "executed"
    return action


def reject_action(action: Dict[str, Any], db: Database) -> Dict[str, Any]:
    db.update_action(action["action_id"], status="rejected")
    action["status"] = "rejected"
    return action


def modify_action(
    action: Dict[str, Any],
    db: Database,
    updated_payload: Dict[str, Any],
    *,
    original_payload: Dict[str, Any],
    preference_extractor: PreferenceExtractionAgent | None = None,
    apply_to_general_preferences: bool = False,
) -> Dict[str, Any]:
    db.update_action(
        action_id=action["action_id"],
        status="executed",
        payload=updated_payload,
    )
    action["payload"] = updated_payload
    action["status"] = "executed"
    _record_preferences_from_modification(
        action=action,
        db=db,
        original_payload=original_payload,
        updated_payload=updated_payload,
        preference_extractor=preference_extractor,
        apply_to_general_preferences=apply_to_general_preferences,
    )
    return action


def review_actions(
    actions: List[Dict[str, Any]],
    db: Database,
    *,
    preference_extractor: PreferenceExtractionAgent | None = None,
) -> None:
    """Quick CLI loop to approve, modify, or reject proposed actions."""
    if not actions:
        print("No actions to review.")
        return

    for action in actions:
        original_payload = copy.deepcopy(action.get("payload", {}))

        print("\nProposed action:")
        print(json.dumps(action, indent=2))
        while True:
            choice = input("Approve (a), modify (m), reject (r): ").strip().lower()
            if choice in {"a", "approve", "m", "modify", "r", "reject"}:
                break
            print("Invalid choice. Please enter 'a', 'm', or 'r'.")

        if choice.startswith("a"):
            approve_action(action, db)
            print("Action executed (simulated).")
        elif choice.startswith("r"):
            reject_action(action, db)
            print("Action rejected.")
        else:
            updated_payload = _prompt_payload_update(action["payload"])
            apply_to_general = _prompt_apply_to_general()
            modify_action(
                action,
                db,
                updated_payload,
                original_payload=original_payload,
                preference_extractor=preference_extractor,
                apply_to_general_preferences=apply_to_general,
            )
            print("Action modified and executed (simulated).")

    print("\nFinal action statuses:")
    for action in actions:
        print(f" - {action['action_id']}: {action['status']}")


def _record_preferences_from_modification(
    *,
    action: Dict[str, Any],
    db: Database,
    original_payload: Dict[str, Any],
    updated_payload: Dict[str, Any],
    preference_extractor: PreferenceExtractionAgent | None,
    apply_to_general_preferences: bool,
) -> None:
    if action.get("type") != "send_email" or preference_extractor is None:
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
                source_action_id=action["action_id"],
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


