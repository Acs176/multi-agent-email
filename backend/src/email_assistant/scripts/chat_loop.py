from __future__ import annotations

import os
from typing import Dict, List
import asyncio

from dotenv import load_dotenv

from ..agents import EmailConversationAgent, EmailDrafterAgent, EmailSchedulerAgent
from ..logging_utils import logs_handler
from ..storage.db import Database
from pathlib import Path

from ..storage.vector_store import EmailVectorStore
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider


def _build_model() -> OpenAIChatModel:
    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    api_key = os.getenv("OPENAI_API_KEY")
    provider = OpenAIProvider(api_key=api_key) if api_key else OpenAIProvider()
    return OpenAIChatModel(model_name, provider=provider)


async def main() -> None:
    load_dotenv()
    logs_handler.setup_logging("debug")

    model = _build_model()
    index_dir = os.getenv("VECTOR_INDEX_DIR")
    vector_store: EmailVectorStore
    if index_dir:
        index_path = Path(index_dir)
        if index_path.exists():
            vector_store = EmailVectorStore.load(index_path)
            database = Database(vector_store=vector_store, auto_index=False, check_same_thread=False)
        else:
            vector_store = EmailVectorStore()
            database = Database(vector_store=vector_store, check_same_thread=False)
            vector_store.save(index_path)
    else:
        vector_store = EmailVectorStore()
        database = Database(vector_store=vector_store, check_same_thread=False)
    drafter = EmailDrafterAgent(model)
    scheduler = EmailSchedulerAgent(model)
    agent = EmailConversationAgent(
        model=model,
        database=database,
        vector_store=vector_store,
        drafter=drafter,
        scheduler=scheduler,
    )

    messages: List[Dict[str, str]] = []
    print("Type your message or 'exit' to quit.\n")

    try:
        while True:
            try:
                user_text = input("You: ").strip()
            except EOFError:
                print()
                break

            if not user_text:
                continue
            if user_text.lower() in {"exit", "quit"}:
                break

            messages.append({"role": "user", "content": user_text})
            reply = await agent.respond_async(messages)

            print("Assistant:\n" + reply.answer + "\n")
            if reply.references:
                print("References:")
                for ref in reply.references:
                    print(f"  - {ref.mail_id} ({ref.score:.3f}) {ref.snippet}")
                print()
            if reply.draft is not None:
                print("Draft suggestion:")
                print(f"To: {reply.draft.to}")
                print(f"Subject: {reply.draft.subject}")
                print(reply.draft.body)
                print()
            if reply.event is not None:
                print("Proposed event:")
                print(f"Title: {reply.event.title}")
                print(f"When: {reply.event.proposed_time}")
                if reply.event.notes:
                    print(f"Notes: {reply.event.notes}")
                print()

            messages.append({"role": "assistant", "content": reply.answer})
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        database.conn.close()


if __name__ == "__main__":
    asyncio.run(main())
