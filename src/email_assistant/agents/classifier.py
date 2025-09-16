"""Minimal email classification agent built on PydanticAI."""
from __future__ import annotations

from typing import Any, Dict, Sequence

from pydantic import BaseModel, Field
from pydantic_ai import Agent
import uuid
from langfuse import observe

from ..business.models import Email
from .utils import _format_thread

INSTRUCTIONS = """
You estimate how an email should be triaged.
Reply with JSON containing these keys only:
{
  "needs_summary": number 0-1,
  "needs_draft": number 0-1,
  "needs_schedule": number 0-1
}
Each value is the probability the action is useful.
Use these guidelines:
- needs_summary: likelihood the email thread benefits from a concise recap (too long subject or too many message turns).
- needs_draft: likelihood the recipient must answer soon and would appreciate a suggested reply.
- needs_schedule: likelihood there is a meeting or time-sensitive event to add to the calendar.
Consider subject, body, sender, recipients, and timing for your reasoning.
""".strip()


class EmailClassification(BaseModel):
    needs_summary: float = Field(..., ge=0.0, le=1.0)
    needs_draft: float = Field(..., ge=0.0, le=1.0)
    needs_schedule: float = Field(..., ge=0.0, le=1.0)

    def as_dict(self) -> Dict[str, float]:
        return self.model_dump()


class EmailClassifierAgent:
    """Thin wrapper around a PydanticAI agent for email triage."""

    def __init__(self, model: Any, decision_threshold: float = 0.5) -> None:
        if not 0.0 <= decision_threshold <= 1.0:
            raise ValueError("decision_threshold must be between 0 and 1")
        self._threshold = decision_threshold
        self._agent = Agent(
            model=model,
            instructions=INSTRUCTIONS,
            output_type=EmailClassification,
            instrument=True,
        )
    
    @observe()
    def classify(self, thread: Sequence[Email]) -> EmailClassification:
        """Classify an email conversation thread."""
        return self._agent.run_sync(_format_thread(thread)).output

    @observe()
    async def classify_async(self, thread: Sequence[Email]) -> EmailClassification:
        """Asynchronously classify an email conversation thread."""
        return (await self._agent.run(_format_thread(thread))).output

    def decisions(self, classification: EmailClassification) -> Dict[str, bool]:
        data = classification.as_dict()
        return {key: value >= self._threshold for key, value in data.items()}


