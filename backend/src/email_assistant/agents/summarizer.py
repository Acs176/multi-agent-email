from typing import Any, Sequence
import os

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from langfuse import observe

from ..business.models import Email
from .utils import _format_thread

INSTRUCTIONS = """
You're an email summarizer. You'll receive an email or thread of emails. 
Summarize the information to the email receiver.
Consider subject, body, sender, recipients, and timing for your reasoning.
Address the user as if you were reading the summary of their email inbox to them.
""".strip()

USER_NAME = os.getenv("USER_NAME", "Adrian")
USER_EMAIL = os.getenv("USER_EMAIL", "example@example.com")

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
    
    # Ensure the summarizer knows who the user is in the conversation
    def _build_input_with_user_info(self, thread) -> str:
        thread_str = _format_thread(thread)
        return f"{thread_str}\n\nUser's data:\nName: {USER_NAME}\nEmail: {USER_EMAIL}"

    @observe()
    def summarize(self, thread: Sequence[Email]) -> EmailSummary:
        return self._agent.run_sync(self._build_input_with_user_info(thread)).output
    @observe()
    async def summarize_async(self, thread: Sequence[Email]) -> EmailSummary:
        return (await self._agent.run(self._build_input_with_user_info(thread))).output
