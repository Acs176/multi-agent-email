"""Agent utilities for the email assistant."""
from .classifier import EmailClassifierAgent, EmailClassification
from .summarizer import EmailSummarizerAgent
from .drafter import EmailDrafterAgent, EmailDraft
from .scheduler import EmailSchedulerAgent, ProposedEvent

__all__ = [
    "EmailClassifierAgent",
    "EmailClassification",
    "EmailSummarizerAgent",
    "EmailDrafterAgent",
    "EmailDraft",
    "EmailSchedulerAgent",
    "ProposedEvent",
]
