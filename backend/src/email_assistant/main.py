"""Command-line entry point for the email assistant."""
from __future__ import annotations

import argparse
import logging
import os

from dotenv import load_dotenv
from langfuse import get_client
from pydantic_ai import Agent

import uvicorn
from .logging_utils import logs_handler


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
    parser = argparse.ArgumentParser(description="Email assistant API runner")
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

    run_api(args.host, args.port, args.reload)
    return


if __name__ == "__main__":
    main()
