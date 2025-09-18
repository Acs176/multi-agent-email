# src/models.py
from typing import List, Optional, Dict, Any, Iterable
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

class DraftingPreferences(BaseModel):
    """Aggregated writing preferences applied when drafting replies."""

    tone: str | None = None
    greeting: str | None = None
    signature: str | None = None
    length: str | None = None
    extra_field: str | None = None
    additional: Dict[str, str] = Field(default_factory=dict)

    def apply_preference(self, key: str, value: str) -> None:
        if key in {"tone", "greeting", "signature", "length", "extra_field"}:
            setattr(self, key, value)
            return
        self.additional[key] = value

    def apply_preferences(self, preferences: Dict[str, str]) -> None:
        for key, value in preferences.items():
            self.apply_preference(key, value)

    def apply_action_preferences(self, preferences: Iterable[ActionPreference]) -> None:
        for preference in preferences:
            self.apply_preference(preference.preference_key, preference.preference_value)

    @classmethod
    def from_general_preferences(cls, preferences: Dict[str, str]) -> "DraftingPreferences":
        instance = cls()
        instance.apply_preferences(preferences)
        return instance

    def is_empty(self) -> bool:
        if any(
            getattr(self, field_name) is not None
            for field_name in ("tone", "greeting", "signature", "length", "extra_field")
        ):
            return False
        return not self.additional

    def to_prompt_lines(self) -> list[str]:
        lines: list[str] = []
        for field_name in ("tone", "greeting", "signature", "length", "extra_field"):
            value = getattr(self, field_name)
            if value:
                lines.append(f"{field_name}: {value}")
        for key, value in self.additional.items():
            lines.append(f"{key}: {value}")
        return lines
