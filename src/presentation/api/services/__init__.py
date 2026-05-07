"""Reusable pure-logic services for the presentation layer.

These services contain NO FastAPI dependencies and can be used by any
orchestrator or controller. They encapsulate domain-agnostic logic such as
conversation state management, file upload validation, library matching, and
clarification resolution.
"""

from src.presentation.api.services.conversation_state import ConversationStateService, conversation_state

__all__ = [
    "ConversationStateService",
    "conversation_state",
]
