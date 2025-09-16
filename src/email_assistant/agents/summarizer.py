from typing import Any, Sequence

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from langfuse import observe

from ..business.models import Email
from .utils import _format_thread

INSTRUCTIONS = """
You're an email summarizer. You'll receive an email or thread of emails. 
Summarize the information to the email receiver.
Consider subject, body, sender, recipients, and timing for your reasoning.
""".strip()


class EmailSummary(BaseModel):
    summary: str = Field(description="summary of the email/thread")


class EmailSummarizerAgent:
    def __init__(self, model: Any) -> None:
        self._agent = Agent(
            model=model,
            instructions=INSTRUCTIONS,
            output_type=EmailSummary,
            instrument=True,
        )

    @observe()
    def summarize(self, thread: Sequence[Email]) -> EmailSummary:
        return self._agent.run_sync(_format_thread(thread)).output
    @observe()
    async def summarize_async(self, thread: Sequence[Email]) -> EmailSummary:
        return (await self._agent.run(_format_thread(thread))).output
