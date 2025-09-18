"""Preference extraction agent to derive reusable writing preferences."""
from __future__ import annotations

import json
from typing import Any, Dict

from pydantic import BaseModel
from pydantic_ai import Agent
from langfuse import observe


DEFAULT_INSTRUCTIONS = """
You analyse how a user modified an email draft suggested by another agent.
Return structured JSON with any inferred preferences for future drafts to the
same recipient. Only include a field when you can clearly infer a preference.
Fields:
- tone: overall tone preference (e.g. formal, casual)
- greeting: preferred opening (e.g. "Hi team", "Dear Alex")
- signature: preferred closing signature (e.g. "Best", "Thanks, Priya")
- length: short description of desired length (e.g. "concise", "detailed")
- extra_field: free-form notes for other reusable patterns
""".strip()


class PreferenceExtraction(BaseModel):
    tone: str | None = None
    greeting: str | None = None
    signature: str | None = None
    length: str | None = None
    extra_field: str | None = None


class PreferenceExtractionAgent:
    """LLM wrapper that derives writing preferences from structured context."""

    def __init__(self, model: Any, *, instructions: str = DEFAULT_INSTRUCTIONS) -> None:
        self._agent = Agent(
            model=model,
            instructions=instructions,
            output_type=PreferenceExtraction,
            instrument=True,
        )

    @observe()
    def extract(self, *, original_payload: Dict[str, Any], updated_payload: Dict[str, Any]) -> PreferenceExtraction:
        prompt = self._build_prompt(original_payload=original_payload, updated_payload=updated_payload)
        return self._run(prompt)

    def run_prompt(self, prompt: str) -> PreferenceExtraction:
        """Run the underlying agent against a pre-built prompt."""
        return self._run(prompt)

    def _run(self, prompt: str) -> PreferenceExtraction:
        return self._agent.run_sync(prompt).output

    def _build_prompt(self, *, original_payload: Dict[str, Any], updated_payload: Dict[str, Any]) -> str:
        formatted_original = json.dumps(original_payload, indent=2, sort_keys=True)
        formatted_updated = json.dumps(updated_payload, indent=2, sort_keys=True)
        return (
            "The model draft was modified by the user.\n"
            "Original model draft (JSON):\n"
            f"{formatted_original}\n\n"
            "User-modified draft (JSON):\n"
            f"{formatted_updated}\n\n"
            "Identify reusable preferences gleaned from the user's edits."
        )
