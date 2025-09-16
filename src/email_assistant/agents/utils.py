from typing import Sequence

from ..business.models import Email


def _format_single_email(email: Email) -> str:
    to_addresses = ", ".join(email.to) if email.to else "(not provided)"
    cc_addresses = ", ".join(email.cc) if email.cc else "(none)"
    subject = email.subject or "(no subject)"
    sender = f"{email.from_name} <{email.from_email}>" if email.from_name else email.from_email
    received_at = email.received_at.isoformat()
    return (
        f"From: {sender}\n"
        f"To: {to_addresses}\n"
        f"Cc: {cc_addresses}\n"
        f"Subject: {subject}\n"
        f"Received: {received_at}\n"
        f"Body:\n{email.body}\n"
    )

def _format_thread(emails: Sequence[Email]) -> str:
    if not emails:
        return "No emails were provided in this thread.\n"

    total = len(emails)
    parts = []
    for index, email in enumerate(emails, start=1):
        label = "Latest message" if total > 1 and index == total else f"Message {index}"
        parts.append(f"--- {label} ---\n" + _format_single_email(email))

    return "\n\n".join(parts)
