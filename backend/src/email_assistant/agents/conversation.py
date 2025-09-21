from __future__ import annotations

from typing import Any, Sequence

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from langfuse import observe

from ..business.models import Email
from ..storage.db import Database
from ..storage.vector_store import EmailVectorStore
from ..logging_utils import logs_handler
from .drafter import EmailDrafterAgent, EmailDraft
from .scheduler import EmailSchedulerAgent, ProposedEvent

logger = logs_handler.get_logger()

INSTRUCTIONS = """
You are the conversational front for the email assistant.
Use the tools provided to look up stored emails, draft replies, or schedule events when helpful.

Available tools:
- search_emails(query: str, limit: int = 5): Retrieve candidate messages with metadata so you can respond to queries or identify the correct mail_id.
- draft_reply(mail_id: str): Generate a reply draft for the conversation identified by mail_id. Call only after you know the precise mail_id.
- schedule_event(mail_id: str): Produce a calendar event proposal based on the thread identified by mail_id. Call only when the relevant mail_id is confirmed.

If you are unsure about the correct mail_id for a follow-up action, call search_emails first to narrow it down before drafting or scheduling.
""".strip()


class ConversationSource(BaseModel):
    mail_id: str = Field(description="Identifier of the email used as a source")
    thread_id: str = Field(description="Thread identifier the email belongs to")
    subject: str | None = Field(default=None, description="Subject line of the email")
    snippet: str = Field(description="Short excerpt from the email body or headers")
    score: float = Field(description="Similarity score between the query and the email")


class ConversationReply(BaseModel):
    answer: str = Field(description="Natural language response to the user")
    references: list[ConversationSource] = Field(default_factory=list)
    draft: EmailDraft | None = Field(default=None, description="Draft email suggested for the user")
    event: ProposedEvent | None = Field(default=None, description="Proposed event generated for the user")


class EmailConversationAgent:
    def __init__(
        self,
        *,
        model: Any,
        database: Database,
        vector_store: EmailVectorStore,
        drafter: EmailDrafterAgent,
        scheduler: EmailSchedulerAgent,
    ) -> None:
        self._db = database
        self._vector_store = vector_store
        self._drafter = drafter
        self._scheduler = scheduler

        logger.info("EmailConversationAgent initialized")

        @observe()
        def search_emails(query: str, limit: int = 5) -> list[dict[str, Any]]:
            logger.info("Tool search_emails invoked (query='%s', limit=%d)", query, limit)
            try:
                records = self._vector_store.search(query, limit)
            except Exception:
                logger.exception("Tool search_emails failed for query '%s'", query)
                raise

            sources: list[ConversationSource] = []
            for record in records:
                sources.append(
                    ConversationSource(
                        mail_id=record['mail_id'],
                        thread_id=record['thread_id'],
                        subject=record.get('subject'),
                        snippet=record.get('snippet', ''),
                        score=record.get('score', 0.0),
                    )
                )
            logger.info("Tool search_emails returning %d sources", len(sources))
            return [source.model_dump() for source in sources]

        @observe()
        async def draft_reply(mail_id: str) -> dict[str, Any]:
            logger.info("Tool draft_reply invoked for mail_id=%s", mail_id)
            try:
                thread = self._db.fetch_thread_by_mail_id(mail_id)
            except Exception:
                logger.exception("Failed to load thread for mail_id=%s", mail_id)
                raise

            if not thread:
                logger.warning("draft_reply could not find thread for mail_id=%s", mail_id)
                return {"status": "not_found", "mail_id": mail_id}

            logger.info("Loaded thread with %d emails for mail_id=%s", len(thread), mail_id)

            try:
                draft = await self._drafter.draft_async(thread)
            except Exception:
                logger.exception("Drafting failed for mail_id=%s", mail_id)
                raise

            latest_email: Email = thread[-1]
            logger.info("Draft ready for mail_id=%s thread_id=%s", mail_id, latest_email.thread_id)
            return {
                "status": "ok",
                "mail_id": mail_id,
                "thread_id": latest_email.thread_id,
                "draft": draft.model_dump(),
            }

        draft_reply.__name__ = "draft_reply"

        @observe()
        async def schedule_event(mail_id: str) -> dict[str, Any]:
            logger.info("Tool scheduler.propose_event invoked for mail_id=%s", mail_id)
            try:
                thread = self._db.fetch_thread_by_mail_id(mail_id)
            except Exception:
                logger.exception("Failed to load thread for mail_id=%s during scheduling", mail_id)
                raise

            if not thread:
                logger.warning("scheduler.propose_event could not find thread for mail_id=%s", mail_id)
                return {"status": "not_found", "mail_id": mail_id}

            logger.info("Loaded thread with %d emails for scheduling mail_id=%s", len(thread), mail_id)

            try:
                event = await self._scheduler.propose_event_async(thread)
            except Exception:
                logger.exception("Scheduling failed for mail_id=%s", mail_id)
                raise

            latest_email: Email = thread[-1]
            logger.info("Proposed event ready for mail_id=%s thread_id=%s", mail_id, latest_email.thread_id)
            return {
                "status": "ok",
                "mail_id": mail_id,
                "thread_id": latest_email.thread_id,
                "event": event.model_dump(),
            }

        schedule_event.__name__ = "schedule_event"

        self._agent = Agent(
            model=model,
            instructions=INSTRUCTIONS,
            output_type=ConversationReply,
            instrument=True,
            tools=[search_emails, draft_reply, schedule_event],
        )

    def _format_messages(self, messages: Sequence[dict[str, str]]) -> str:
        logger.debug("Formatting %d messages for conversation prompt", len(messages))
        lines: list[str] = []
        for message in messages:
            role = (message.get("role") or "user").strip().lower()
            content = (message.get("content") or "").strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
        if not lines:
            logger.error("No non-empty messages provided to EmailConversationAgent")
            raise ValueError("At least one non-empty message is required")
        formatted_prompt = "\n".join(lines)
        logger.debug("Prompt built with %d lines", len(lines))
        return formatted_prompt

    @observe()
    async def respond_async(self, messages: Sequence[dict[str, str]]) -> ConversationReply:
        logger.info("respond_async invoked with %d message(s)", len(messages))
        prompt = self._format_messages(messages)
        try:
            result = await self._agent.run(prompt)
        except Exception:
            logger.exception("Conversation agent run_async failed")
            raise
        output = result.output
        logger.info(
            "respond_async completed (answer_chars=%d, references=%d, draft=%s, event=%s)",
            len(output.answer or ""),
            len(output.references),
            bool(output.draft),
            bool(output.event),
        )
        return output

