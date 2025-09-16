from ..business.models import Email

def _format_email(email: Email) -> str:
    to_addresses = ", ".join(email.to) if email.to else "(not provided)"
    cc_addresses = ", ".join(email.cc) if email.cc else "(none)"
    subject = email.subject or "(no subject)"
    sender = f"{email.from_name} <{email.from_email}>" if email.from_name else email.from_email
    return (
        "Classify this email.\n"
        f"From: {sender}\n"
        f"To: {to_addresses}\n"
        f"Cc: {cc_addresses}\n"
        f"Subject: {subject}\n"
        f"Body:\n{email.body}\n"
    )