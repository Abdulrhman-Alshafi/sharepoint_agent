"""Tests for presentation handler utilities."""

import pytest
import logging
from unittest.mock import MagicMock

from src.presentation.api.handlers.handler_utils import error_response
from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestErrorResponse:
    def test_returns_chat_response(self):
        logger = logging.getLogger("test")
        exc = Exception("something broke")
        result = error_response(logger, "chat", "Error occurred", exc)
        assert isinstance(result, ChatResponse)

    def test_intent_is_preserved(self):
        logger = logging.getLogger("test")
        result = error_response(logger, "delete", "Failed", Exception("x"))
        assert result.intent == "delete"

    def test_message_template_plain(self):
        logger = logging.getLogger("test")
        result = error_response(logger, "chat", "Something went wrong", Exception("boom"))
        assert result.reply == "Something went wrong"

    def test_message_template_with_error_placeholder(self):
        logger = logging.getLogger("test")
        result = error_response(logger, "provision", "Failed: {error}", Exception("network"))
        assert "network" in result.reply

    def test_all_valid_intents_work(self):
        logger = logging.getLogger("test")
        for intent in ["query", "provision", "chat", "analyze", "update", "delete"]:
            result = error_response(logger, intent, "oops", Exception("err"))
            assert result.intent == intent
