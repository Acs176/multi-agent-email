"""Email draft generation agent built on PydanticAI."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from ..business.models import Email
from .utils import _format_email

INSTRUCTIONS = """
You write helpful reply drafts for incoming emails.
Reply with JSON containing only these keys:
{
  "to": string of comma-separated recipients,
  "subject": subject line for the reply,
  "body": body text of the reply email
}
Keep the tone polite and concise.
""".strip()


class EmailDraft(BaseModel):
    to: str = Field(description="Recipients for the drafted reply, comma separated")
    subject: str = Field(description="Subject line for the draft reply")
    body: str = Field(description="Body text of the draft reply")


class EmailDrafterAgent:
    """Wraps a PydanticAI agent that produces reply drafts."""

    def __init__(self, model: Any) -> None:
        self._agent = Agent(
            model=model,
            instructions=INSTRUCTIONS,
            output_type=EmailDraft,
        )

    def draft(self, email: Email) -> EmailDraft:
        return self._agent.run_sync(_format_email(email)).output

    async def draft_async(self, email: Email) -> EmailDraft:
        return (await self._agent.run(_format_email(email))).output
