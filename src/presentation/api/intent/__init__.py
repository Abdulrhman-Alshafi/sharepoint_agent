"""Modular intent detection system.

Breaks the monolithic ``_detect_enhanced_intent()`` from chat.py into
focused, testable modules — one per intent domain.

Usage::

    from src.presentation.api.intent import detect_enhanced_intent

    intent = detect_enhanced_intent("delete the Announcements list")
    # → "delete"
"""

from src.presentation.api.intent.intent_router import detect_enhanced_intent

__all__ = ["detect_enhanced_intent"]
