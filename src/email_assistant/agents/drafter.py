"""Email draft generation agent built on PydanticAI."""
from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from langfuse import observe

from ..business.models import DraftingPreferences, Email
from .utils import _format_thread

INSTRUCTIONS = """
You write helpful reply drafts for incoming emails. Do not add placeholders or extra comments, your draft will be sent directly.
Assume the last message in the thread is the one that needs a response.
If a "User writing preferences" section is provided, incorporate every preference faithfully.
Reply with JSON containing only these keys:
{
  "to": string of comma-separated recipients (this should include the sender of the email you're responding to),
  "subject": subject line for the reply,
  "body": body text of the reply email
}
Keep the tone polite and concise unless instructed otherwise by the preferences.
""".strip()


def _build_agent_input(
    thread: Sequence[Email],
    preferences: DraftingPreferences | None,
) -> str:
    thread_block = _format_thread(thread)
    if preferences is None or preferences.is_empty():
        return thread_block

    preference_lines = preferences.to_prompt_lines()
    if not preference_lines:
        return thread_block

    preferences_block = "\n".join(f"- {line}" for line in preference_lines)
    return f"{thread_block}\n\nUser writing preferences:\n{preferences_block}"


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
    def draft(
        self,
        thread: Sequence[Email],
        *,
        preferences: DraftingPreferences | None = None,
    ) -> EmailDraft:
        prompt = _build_agent_input(thread, preferences)
        return self._agent.run_sync(prompt).output

    @observe()
    async def draft_async(
        self,
        thread: Sequence[Email],
        *,
        preferences: DraftingPreferences | None = None,
    ) -> EmailDraft:
        prompt = _build_agent_input(thread, preferences)
        return (await self._agent.run(prompt)).output
