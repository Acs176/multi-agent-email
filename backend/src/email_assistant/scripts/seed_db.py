"""Utilities for seeding the assistant database with fixture data."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict

from ..business.models import Action, Email
from ..storage.db import Database

DEFAULT_EMAILS_PATH = "./data/test_emails.json"
DEFAULT_ACTIONS_PATH = "./data/approved_drafts.json"


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def seed_emails(db: Database, dataset_path: Path) -> int:
    payload = _load_json(dataset_path)
    inserted = 0

    for email_data in payload.get("emails", []):
        email = Email(**email_data)
        try:
            db.insert_email(email)
            inserted += 1
        except sqlite3.IntegrityError:
            print(f"Skipping existing email {email.mail_id}")

    return inserted


def seed_actions(db: Database, dataset_path: Path) -> int:
    payload = _load_json(dataset_path)
    inserted = 0

    for action_data in payload.get("approved_drafts", []):
        action = Action(**action_data)
        try:
            db.insert_action(action)
            inserted += 1
        except sqlite3.IntegrityError:
            print(f"Skipping existing action {action.action_id}")

    return inserted


def seed_database(emails_path: Path, actions_path: Path) -> None:
    db = Database()
    email_count = seed_emails(db, emails_path)
    action_count = seed_actions(db, actions_path)
    print(f"Inserted {email_count} emails and {action_count} actions.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the assistant database with fixture data.")
    parser.add_argument(
        "--emails",
        type=Path,
        default=DEFAULT_EMAILS_PATH,
        help=f"Path to the emails dataset (default: {DEFAULT_EMAILS_PATH})",
    )
    parser.add_argument(
        "--actions",
        type=Path,
        default=DEFAULT_ACTIONS_PATH,
        help=f"Path to the approved drafts dataset (default: {DEFAULT_ACTIONS_PATH})",
    )
    args = parser.parse_args()

    seed_database(args.emails, args.actions)


if __name__ == "__main__":
    main()
