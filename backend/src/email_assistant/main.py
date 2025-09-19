"""Command-line entry point for the email assistant."""
from __future__ import annotations

import asyncio

import argparse
import logging
import os
import uuid

from dotenv import load_dotenv
from langfuse import get_client
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
import uvicorn

from .agents import (
    EmailClassifierAgent,
    EmailDrafterAgent,
    EmailSchedulerAgent,
    EmailSummarizerAgent,
    PreferenceExtractionAgent,
)
from .business.models import Email
from .logging_utils import logs_handler
from .orchestrator import Orchestrator
from .storage.db import Database
from .user_actions import review_actions

Agent.instrument_all()

def setup_environment() -> None:
    load_dotenv()
    logs_handler.setup_logging(level=os.getenv("LOG_LEVEL", "debug"))


def check_langfuse(logger: logging.Logger) -> None:
    langfuse = get_client()
    if langfuse.auth_check():
        logger.debug("Langfuse client authenticated and ready!")
    else:
        logger.debug("Langfuse authentication failed")


def build_model() -> OpenAIChatModel:
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    api_key = os.getenv("OPENAI_API_KEY")
    provider = OpenAIProvider(api_key=api_key) if api_key else OpenAIProvider()
    return OpenAIChatModel(model_name, provider=provider)


def run_cli(model: OpenAIChatModel) -> None:
    logger = logs_handler.get_logger()
    db = Database()
    orchestrator = Orchestrator(
        classifier=EmailClassifierAgent(model),
        drafter=EmailDrafterAgent(model),
        scheduler=EmailSchedulerAgent(model),
        summarizer=EmailSummarizerAgent(model),
        database=db,
    )

    sample_email = Email(
        mail_id=str(uuid.uuid4()),
        thread_id="thread-project-launch",
        from_name="Priya Singh",
        from_email="pm@example.com",
        to=["alice.johnson@example.com", "diego.martinez@example.com"],
        cc=["finance@example.com", "product@example.com"],
        subject="Re: Project Launch - Kickoff Prep",
        body=(
            "Looks solid now! Finance confirmed the numbers on slide 6. I suggest we trim "
            "slide 9 a bit -- too much detail for kickoff. Otherwise, I think we're ready to "
            "present tomorrow. Please let me know if you're available. Please respond.\n\n- Priya"
        ),
    )

    result = asyncio.run(orchestrator.process_new_email(sample_email))
    logger.info("Classification: %s", result["classification"])
    logger.info("Summary: %s", result["summary"])

    preference_extractor = PreferenceExtractionAgent(model)
    review_actions(
        result["proposed_actions"],
        db,
        preference_extractor=preference_extractor,
    )

    logger.debug(db.fetch_general_preferences())


def run_api(host: str, port: int, reload: bool) -> None:
    logger = logs_handler.get_logger()
    logger.info("Starting API server at %s:%s (reload=%s)", host, port, reload)
    uvicorn.run(
        "src.email_assistant.api.app:app",
        host=host,
        port=port,
        reload=reload,
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Email assistant runner")
    parser.add_argument(
        "--api",
        action="store_true",
        help="Run the FastAPI server instead of the interactive CLI demo",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("API_HOST", "0.0.0.0"),
        help="Host for the API server",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("API_PORT", "8000")),
        help="Port for the API server",
    )
    parser.add_argument(
        "--reload",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable or disable uvicorn reload when running the API server",
    )

    args = parser.parse_args(argv)

    setup_environment()
    logger = logs_handler.get_logger()
    check_langfuse(logger)

    if args.api:
        run_api(args.host, args.port, args.reload)
        return

    model = build_model()
    run_cli(model)


if __name__ == "__main__":
    main()
