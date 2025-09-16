"""Email scheduling agent built on PydanticAI."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from ..business.models import Email
from .utils import _format_email

INSTRUCTIONS = """
You help schedule follow-up meetings or tasks triggered by incoming emails.
Reply with JSON using only these keys:
{
  "title": string describing the event,
  "proposed_time": ISO-8601 timestamp for the suggested time,
  "notes": optional string with additional context or next steps
}
If timing is unclear, suggest a reasonable default and explain in notes.
""".strip()


class ProposedEvent(BaseModel):
    title: str = Field(description="Title of the proposed meeting or event")
    proposed_time: str = Field(description="ISO-8601 timestamp for the suggested time")
    notes: str = Field(default="", description="Additional context for the event")


class EmailSchedulerAgent:
    """Wraps a PydanticAI agent that proposes calendar events."""

    def __init__(self, model: Any) -> None:
        self._agent = Agent(
            model=model,
            instructions=INSTRUCTIONS,
            output_type=ProposedEvent,
        )

    def propose_event(self, email: Email) -> ProposedEvent:
        return self._agent.run_sync(_format_email(email)).output

    async def propose_event_async(self, email: Email) -> ProposedEvent:
        return (await self._agent.run(_format_email(email))).output
