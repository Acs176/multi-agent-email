# src/models.py
from typing import List, Optional, Dict, Any
import datetime
from pydantic import BaseModel, Field


class Email(BaseModel):
    mail_id: str
    external_id: Optional[str] = None
    thread_id: str
    from_name: Optional[str] = None
    from_email: str
    to: List[str] = Field(default_factory=list)
    cc: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    body: str
    received_at: datetime.datetime = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )


class Action(BaseModel):
    action_id: str
    mail_id: Optional[str] = None
    type: str
    status: str
    payload: Dict[str, Any]
    result: Optional[Dict[str, Any]] = None


class Summary(BaseModel):
    summary_id: str
    thread_id: str
    text: str

class ActionPreference(BaseModel):
    preference_id: str
    recipient_email: str
    preference_key: str
    preference_value: str
    source_action_id: Optional[str] = None

class GeneralPreference(BaseModel):
    preference_key: str
    preference_value: str
