"""Agent utilities for the email assistant."""
from .classifier import EmailClassifierAgent, EmailClassification
from .summarizer import EmailSummarizerAgent
from .drafter import EmailDrafterAgent, EmailDraft
from .scheduler import EmailSchedulerAgent, ProposedEvent
from .preferences import PreferenceExtractionAgent, PreferenceExtraction
from .conversation import EmailConversationAgent, ConversationReply, ConversationSource

__all__ = [
    "EmailClassifierAgent",
    "EmailClassification",
    "EmailSummarizerAgent",
    "EmailDrafterAgent",
    "EmailDraft",
    "EmailSchedulerAgent",
    "ProposedEvent",
    "PreferenceExtractionAgent",
    "PreferenceExtraction",
    "EmailConversationAgent",
    "ConversationReply",
    "ConversationSource",
]
