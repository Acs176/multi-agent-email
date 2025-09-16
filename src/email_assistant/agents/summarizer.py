from typing import Any, Dict

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from ..business.models import Email
from .utils import _format_email

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
        )

    def summarize(self, email: Email) -> EmailSummary:
        return self._agent.run_sync(_format_email(email)).output

    async def summarize_async(self, email: Email) -> EmailSummary:
        return (await self._agent.run(_format_email(email))).output