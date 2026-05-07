"""Utility for resolving vague follow-up messages into standalone questions."""

import logging
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from src.infrastructure.external_services.ai_client_factory import get_instructor_client

logger = logging.getLogger(__name__)

FOLLOWUP_RESOLVER_PROMPT = (
    "You are a message resolver. Your ONLY job is to rewrite a follow-up message "
    "into a standalone, self-contained question or command.\n\n"
    "Rules:\n"
    "1. If the message is ALREADY a clear standalone question or command "
    "(e.g., 'tell me about the Milestones list', 'all the lists', 'show me all sites'), "
    "return it UNCHANGED.\n"
    "2. If it references something vaguely (e.g., 'it', 'that', 'the same one', "
    "'tell me more', 'what about it?'), identify the subject from the USER'S most recent "
    "prior question — NOT from anything mentioned inside an assistant's answer — and rewrite "
    "the message as a specific standalone question.\n"
    "3. CRITICAL: The subject of 'it', 'that', 'this', 'them' is ALWAYS the resource the "
    "USER most recently asked about (in their last user-role message). Ignore all resource "
    "names that appear only inside assistant replies.\n"
    "4. Keep the rewritten message concise and natural.\n"
    "5. Do NOT add extra information or assumptions beyond what the user's own messages provide.\n"
    "6. Preserve the user's intent exactly — just make it self-contained.\n"
    "7. NEVER append 'in SharePoint', 'in Microsoft 365', 'in Office 365', or any platform name "
    "to the rewritten message. These are not site names.\n"
    "8. Only append a site name (e.g., 'in HR site') if the USER explicitly mentioned that "
    "site name in the conversation history.\n\n"
    "Examples:\n"
    "- Last USER message: 'more about Milestones', new message: 'tell me more about the data in it' "
    "→ 'Tell me more about the data in the Milestones list'\n"
    "- Last USER message: 'tell me about the Tasks list', new message: 'how many items?' "
    "→ 'How many items are in the Tasks list?'\n"
    "- Last USER message: 'what lists do I have?', new message: 'tell me more about the first one' "
    "→ 'Tell me more about [first list from user context]'\n"
    "- User says 'what lists do I have?' (no context needed) → 'what lists do I have?'\n"
    "- User says 'all the lists' (no context needed) → 'all the lists'"
)


class _ResolvedMessage(BaseModel):
    resolved_message: str


# Pronouns / references that indicate the message truly depends on prior context
_CONTEXT_DEPENDENT_WORDS = frozenset([
    "it", "that", "this", "them", "those", "these",
    "the other", "the same", "the previous", "the last",
    "more", "again", "also", "else",
    "one",  # e.g. "create a new one named X" needs context to know the resource type
])


def _needs_resolution(message: str) -> bool:
    """Return True only when the message actually depends on prior context."""
    words = set(message.lower().split())
    # Short messages with no context-dependent pronouns can be returned as-is
    return bool(words & _CONTEXT_DEPENDENT_WORDS)


def resolve_followup_message(message: str, history: Optional[List[Dict[str, Any]]]) -> str:
    """Use AI to rewrite vague follow-up messages into standalone questions.
    
    Args:
        message: The user's new message
        history: Recent conversation history
        
    Returns:
        Resolved standalone message
    """
    if not history:
        return message

    # Skip the AI call entirely when the message is already self-contained
    if not _needs_resolution(message):
        logger.debug("Message is self-contained, skipping resolver: '%s'", message)
        return message

    try:
        client, model = get_instructor_client()
        # Pass ONLY user messages to the resolver — assistant replies often mention many
        # resource names (e.g. quoting list contents) and cause the resolver to pick the
        # wrong subject. The resolver only needs to know what the USER asked previously.
        user_messages = [
            msg for msg in history if msg.get('role') == 'user'
        ]
        history_text = "\n".join(
            f"user: {msg.get('content', '')}" for msg in user_messages[-6:]
        )
        prompt = (
            f"{FOLLOWUP_RESOLVER_PROMPT}\n\n"
            f"Conversation History:\n{history_text}\n\n"
            f"User's new message: {message}\n\n"
            f"Rewrite as a standalone message:"
        )
        kwargs = {
            "messages": [{"role": "user", "content": prompt}],
            "response_model": _ResolvedMessage,
        }
        if model:  # Only pass model for non-Gemini providers
            kwargs["model"] = model
        result = client.chat.completions.create(**kwargs)
        resolved = result.resolved_message.strip()
        if resolved:
            logger.info("Follow-up resolved: '%s' → '%s'", message, resolved)
            return resolved
    except Exception as exc:
        logger.warning("Follow-up resolution failed (%s); using original message.", exc)

    return message
