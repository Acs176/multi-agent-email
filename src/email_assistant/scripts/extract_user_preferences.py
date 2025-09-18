"""CLI to derive general writing preferences from approved drafts."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Iterable

from dotenv import load_dotenv
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from langfuse import get_client, observe


from ..agents.preferences import PreferenceExtractionAgent
from ..storage.db import Database

DEFAULT_APPROVED_DRAFTS_PATH = Path("./data/approved_drafts.json")
DEFAULT_MODEL_NAME = "gpt-4o"

GENERAL_PREFERENCE_INSTRUCTIONS = """
You analyse a collection of approved email drafts all written by the same user.
Infer the user's general writing preferences that should inform future drafts
across recipients. Only include a field in the output when the drafts give a
confident signal. If there is insufficient evidence for a field, leave it null
rather than guessing.
Fields:
- tone: overall tone preference (e.g. formal, casual)
- greeting: preferred opening (e.g. "Hi team", "Dear {`name}`")
- signature: preferred closing signature (e.g. "Best", "Best Regards")
- length: short description of desired length (e.g. "concise", "detailed")
- extra_field: free-form notes for other reusable patterns
Return strictly valid JSON.
""".strip()

Agent.instrument_all()


def _load_approved_drafts(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    drafts = payload.get("approved_drafts", [])
    return [draft for draft in drafts if draft.get("type") == "send_email"]


def _format_draft(draft: dict[str, Any], index: int) -> str:
    payload = draft.get("payload", {})
    recipients = payload.get("to") or "(no recipients)"
    subject = payload.get("subject") or "(no subject)"
    body = payload.get("body") or ""
    return (
        f"--- Draft {index} ---\n"
        f"Recipients: {recipients}\n"
        f"Subject: {subject}\n"
        f"Body:\n{body.strip()}"
    )


def _build_prompt(drafts: Iterable[dict[str, Any]]) -> str:
    formatted = [_format_draft(draft, index) for index, draft in enumerate(drafts, start=1)]
    drafts_block = "\n\n".join(formatted) if formatted else "No drafts available."
    return (
        "Review the approved drafts below and extract the user's general writing preferences.\n"
        "Focus on patterns consistent across the drafts.\n\n"
        f"Approved drafts:\n{drafts_block}"
    )


def _ensure_api_key() -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Please configure it in the environment or .env file.")
    return api_key

@observe()
def extract_preferences(path: Path, *, model_name: str = DEFAULT_MODEL_NAME) -> dict[str, str]:
    api_key = _ensure_api_key()

    drafts = _load_approved_drafts(path)
    if not drafts:
        print("No approved drafts found.")
        return {}

    prompt = _build_prompt(drafts)

    model = OpenAIChatModel(model_name, provider=OpenAIProvider(api_key=api_key))
    agent = PreferenceExtractionAgent(model, instructions=GENERAL_PREFERENCE_INSTRUCTIONS)
    extraction = agent.run_prompt(prompt)
    preferences = extraction.model_dump(exclude_none=True)
    print(preferences)
    if not preferences:
        print("No general preferences detected.")
        return {}

    db = Database()
    for key, value in preferences.items():
        db.upsert_general_preference(preference_key=key, preference_value=str(value))

    return preferences


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract general writing preferences from approved drafts.")
    parser.add_argument(
        "--approved-drafts",
        type=Path,
        default=DEFAULT_APPROVED_DRAFTS_PATH,
        help=f"Path to the approved drafts dataset (default: {DEFAULT_APPROVED_DRAFTS_PATH})",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL_NAME,
        help=f"OpenAI chat model name (default: {DEFAULT_MODEL_NAME})",
    )
    args = parser.parse_args()
    load_dotenv()
    
    # langfuse setup
    langfuse = get_client()
    if langfuse.auth_check():
        print("Langfuse client authenticated and ready!")
    else:
        print("Langfuse authentication failed")

    preferences = extract_preferences(args.approved_drafts, model_name=args.model)
    if preferences:
        print("Stored general preferences:")
        for key, value in preferences.items():
            print(f" - {key}: {value}")


if __name__ == "__main__":
    main()
