from __future__ import annotations

import asyncio
import copy
import os
from typing import Annotated, Any, Dict, Optional, AsyncGenerator

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from langfuse import get_client
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from ..agents import (
    EmailClassifierAgent,
    EmailDrafterAgent,
    EmailSchedulerAgent,
    EmailSummarizerAgent,
    PreferenceExtractionAgent,
)
from ..business.models import Action, Email
from ..logging_utils import logs_handler
from ..orchestrator import Orchestrator
from ..storage.db import Database
from ..user_actions import approve_action, modify_action, reject_action

app = FastAPI(title="Email Assistant API", version="0.1.0")
Agent.instrument_all()


class SummaryPayload(BaseModel):
    text: str


class ClassificationPayload(BaseModel):
    probabilities: Dict[str, float]
    decisions: Dict[str, bool]


class NewEmailResponse(BaseModel):
    mail_id: str
    summary: Optional[SummaryPayload]
    proposed_actions: list[Action]
    classification: ClassificationPayload


class ApproveActionRequest(BaseModel):
    action_id: str
    result: Optional[Dict[str, Any]] = None


class RejectActionRequest(BaseModel):
    action_id: str
    result: Optional[Dict[str, Any]] = None


class ModifyActionRequest(BaseModel):
    action_id: str
    payload: Dict[str, Any]
    record_preferences: bool = True
    apply_to_general_preferences: bool = False
    result: Optional[Dict[str, Any]] = None


async def get_db() -> AsyncGenerator[Database, None]:
    db = Database(check_same_thread=False)
    try:
        yield db
    finally:
        db.conn.close()


def get_orchestrator(
    request: Request, db: Annotated[Database, Depends(get_db)]
) -> Orchestrator:
    state = request.app.state
    return Orchestrator(
        classifier=state.classifier,
        drafter=state.drafter,
        scheduler=state.scheduler,
        summarizer=state.summarizer,
        database=db,
    )


def get_preference_extractor(request: Request) -> PreferenceExtractionAgent | None:
    return getattr(request.app.state, "preference_extractor", None)


@app.on_event("startup")
async def startup() -> None:
    load_dotenv()
    logs_handler.setup_logging(level=os.getenv("LOG_LEVEL", "info"))
    logger = logs_handler.get_logger()

    langfuse = get_client()
    if langfuse.auth_check():
        logger.debug("Langfuse client authenticated and ready!")
    else:
        logger.warning("Langfuse authentication failed")

    model_name = os.getenv("OPENAI_MODEL", "gpt-4o")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY missing; downstream agents may fail to call OpenAI")

    provider = OpenAIProvider(api_key=api_key) if api_key else OpenAIProvider()
    model = OpenAIChatModel(model_name, provider=provider)

    app.state.classifier = EmailClassifierAgent(model)
    app.state.drafter = EmailDrafterAgent(model)
    app.state.scheduler = EmailSchedulerAgent(model)
    app.state.summarizer = EmailSummarizerAgent(model)
    app.state.preference_extractor = PreferenceExtractionAgent(model)


@app.post("/new_email", response_model=NewEmailResponse)
async def create_email(
    email: Email, orchestrator: Annotated[Orchestrator, Depends(get_orchestrator)]
) -> NewEmailResponse:
    result = await asyncio.to_thread(orchestrator.process_new_email, email)
    return NewEmailResponse.model_validate(result)


def _fetch_action_or_404(db: Database, action_id: str) -> Action:
    action = db.fetch_action(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
    return action


def _maybe_update_result(db: Database, action_id: str, result: Dict[str, Any] | None) -> None:
    if result is not None:
        db.update_action(action_id=action_id, result=result)


@app.post("/action/approve", response_model=Action)
async def approve_action_endpoint(
    payload: ApproveActionRequest, db: Annotated[Database, Depends(get_db)]
) -> Action:
    action = _fetch_action_or_404(db, payload.action_id)
    action_dict = action.model_dump()
    updated = approve_action(action_dict, db)
    _maybe_update_result(db, payload.action_id, payload.result)
    if payload.result is not None:
        updated["result"] = payload.result
    return Action.model_validate(updated)


@app.post("/action/reject", response_model=Action)
async def reject_action_endpoint(
    payload: RejectActionRequest, db: Annotated[Database, Depends(get_db)]
) -> Action:
    action = _fetch_action_or_404(db, payload.action_id)
    action_dict = action.model_dump()
    updated = reject_action(action_dict, db)
    _maybe_update_result(db, payload.action_id, payload.result)
    if payload.result is not None:
        updated["result"] = payload.result
    return Action.model_validate(updated)


@app.post("/action/modify", response_model=Action)
async def modify_action_endpoint(
    payload: ModifyActionRequest,
    db: Annotated[Database, Depends(get_db)],
    preference_extractor: Annotated[
        PreferenceExtractionAgent | None, Depends(get_preference_extractor)
    ],
) -> Action:
    action = _fetch_action_or_404(db, payload.action_id)
    original_payload = copy.deepcopy(action.payload)
    action_dict = action.model_dump()

    extractor = preference_extractor if payload.record_preferences else None
    updated = await asyncio.to_thread(
        modify_action,
        action_dict,
        db,
        updated_payload=payload.payload,
        original_payload=original_payload,
        preference_extractor=extractor,
        apply_to_general_preferences=payload.apply_to_general_preferences,
    )
    _maybe_update_result(db, payload.action_id, payload.result)
    if payload.result is not None:
        updated["result"] = payload.result
    return Action.model_validate(updated)

