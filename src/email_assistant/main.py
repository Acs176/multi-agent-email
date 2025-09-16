"""Command-line entry point for the email assistant."""
from __future__ import annotations

import uuid
import os

from dotenv import load_dotenv

from .agents import (
    EmailClassifierAgent,
    EmailDrafterAgent,
    EmailSchedulerAgent,
    EmailSummarizerAgent,
)
from .business.models import Email
from .orchestrator import Orchestrator
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


def main() -> None:
    load_dotenv()
    model_name = "gpt-4o"
    api_key = os.getenv("OPENAI_API_KEY")
    model = OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=api_key))

    orchestrator = Orchestrator(
        classifier=EmailClassifierAgent(model),
        drafter=EmailDrafterAgent(model),
        scheduler=EmailSchedulerAgent(model),
        summarizer=EmailSummarizerAgent(model),
    )

    sample_email = Email(
        mail_id=str(uuid.uuid4()),
        thread_id="thread-project-launch",
        from_name="Priya Singh",
        from_email="pm@example.com",
        to=["alice.johnson@example.com", "diego.martinez@example.com"],
        cc=["finance@example.com", "product@example.com"],
        subject="Re: Project Launch - Kickoff Prep",
        body="Looks solid now! Finance confirmed the numbers on slide 6. I suggest we trim slide 9 a bit—too much detail for kickoff. Otherwise, I think we’re ready to present tomorrow.\n\n- Priya",
    )

    result = orchestrator.process_new_email(sample_email)
    print("Classification:", result["classification"])
    print("Summary:", result["summary"])
    print("Proposed actions:")
    for action in result["proposed_actions"]:
        print(" -", action)


if __name__ == "__main__":
    main()
