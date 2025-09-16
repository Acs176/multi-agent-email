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
        thread_id="thread-001",
        from_name="Alice",
        from_email="alice@example.com",
        to=["me@example.com"],
        subject="Project Update",
        body="""
        Hello Adrian, 

Hope all is well. 

We are happy to proceed forward with the recruitment process, the next step is a test (attached). 

Deadline: 22nd September 2025

Best of luck!

        """,
    )

    result = orchestrator.process_new_email(sample_email)
    print("Classification:", result["classification"])
    print("Summary:", result["summary"])
    print("Proposed actions:")
    for action in result["proposed_actions"]:
        print(" -", action)


if __name__ == "__main__":
    main()
