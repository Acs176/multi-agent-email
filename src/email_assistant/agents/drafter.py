"""Email draft generation agent built on PydanticAI."""
from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from langfuse import observe

from ..business.models import Email
from .utils import _format_thread

INSTRUCTIONS = """
You write helpful reply drafts for incoming emails.
Assume the last message in the thread is the one that needs a response.
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
            instrument=True,
        )
    @observe()
    def draft(self, thread: Sequence[Email]) -> EmailDraft:
        return self._agent.run_sync(_format_thread(thread)).output
    @observe()
    async def draft_async(self, thread: Sequence[Email]) -> EmailDraft:
        return (await self._agent.run(_format_thread(thread))).output
