"""Command-line entry point for the email assistant."""
from __future__ import annotations

import os
import uuid
from langfuse import get_client
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from dotenv import load_dotenv

from .agents import (
    EmailClassifierAgent,
    EmailDrafterAgent,
    EmailSchedulerAgent,
    EmailSummarizerAgent,
    PreferenceExtractionAgent,
)
from .storage.db import Database
from .business.models import Email
from .orchestrator import Orchestrator
from .user_actions import review_actions

Agent.instrument_all()


def main() -> None:
    load_dotenv()

    ## tracing setup
    langfuse = get_client()
    if langfuse.auth_check():
        print("Langfuse client authenticated and ready!")
    else:
        print("Langfuse authentication failed")

    model_name = "gpt-4o"
    api_key = os.getenv("OPENAI_API_KEY")
    model = OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=api_key))

    db = Database()
    orchestrator = Orchestrator(
        classifier=EmailClassifierAgent(model),
        drafter=EmailDrafterAgent(model),
        scheduler=EmailSchedulerAgent(model),
        summarizer=EmailSummarizerAgent(model),
        database=db
    )

    sample_email = Email(
        mail_id=str(uuid.uuid4()),
        thread_id="thread-project-launch",
        from_name="Priya Singh",
        from_email="pm@example.com",
        to=["alice.johnson@example.com", "diego.martinez@example.com"],
        cc=["finance@example.com", "product@example.com"],
        subject="Re: Project Launch - Kickoff Prep",
        body="Looks solid now! Finance confirmed the numbers on slide 6. I suggest we trim slide 9 a bit -- too much detail for kickoff. Otherwise, I think we're ready to present tomorrow. Please let me know if you're available.\n\n- Priya",
    )

    result = orchestrator.process_new_email(sample_email)
    print("Classification:", result["classification"])
    print("Summary:", result["summary"])
    
    preference_extractor = PreferenceExtractionAgent(model)
    review_actions(
        result["proposed_actions"],
        db,
        preference_extractor=preference_extractor,
    )

    print(db.fetch_general_preferences())


if __name__ == "__main__":
    main()
