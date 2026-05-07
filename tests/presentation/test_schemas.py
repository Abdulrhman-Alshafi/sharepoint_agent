"""Tests for ChatRequest and ChatResponse schemas."""

import pytest
from pydantic import ValidationError

from src.presentation.api.schemas.chat_schemas import ChatRequest, ChatResponse


class TestChatRequest:
    def test_valid_message(self):
        req = ChatRequest(message="Create a list")
        assert req.message == "Create a list"

    def test_empty_message_fails_validation(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_message_exceeding_max_length_fails(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="A" * 2001)

    def test_message_at_max_length_passes(self):
        req = ChatRequest(message="A" * 2000)
        assert len(req.message) == 2000

    def test_optional_fields_default_to_none(self):
        req = ChatRequest(message="Hello")
        assert req.history is None
        assert req.session_id is None
        assert req.site_id is None

    def test_session_id_accepted(self):
        req = ChatRequest(message="Hi", session_id="abc-123")
        assert req.session_id == "abc-123"


class TestChatResponse:
    def test_minimal_valid_response(self):
        resp = ChatResponse(intent="chat", reply="Hello!")
        assert resp.intent == "chat"
        assert resp.reply == "Hello!"

    def test_valid_intent_values(self):
        for intent in ["query", "provision", "chat", "analyze", "update", "delete"]:
            resp = ChatResponse(intent=intent, reply="ok")
            assert resp.intent == intent

    def test_invalid_intent_fails(self):
        with pytest.raises(ValidationError):
            ChatResponse(intent="unknown_intent", reply="ok")

    def test_optional_extras_default_to_none(self):
        resp = ChatResponse(intent="chat", reply="ok")
        assert resp.resource_links is None
        assert resp.warnings is None
        assert resp.blueprint is None

    def test_warnings_list_accepted(self):
        resp = ChatResponse(intent="provision", reply="Done", warnings=["warn1", "warn2"])
        assert resp.warnings == ["warn1", "warn2"]

    def test_requires_confirmation_accepted(self):
        resp = ChatResponse(intent="delete", reply="Are you sure?", requires_confirmation=True)
        assert resp.requires_confirmation is True

    def test_provision_response_with_blueprint(self):
        resp = ChatResponse(
            intent="provision",
            reply="Created",
            blueprint={"lists": [], "pages": []},
            resource_links=["http://sp/list"]
        )
        assert resp.blueprint == {"lists": [], "pages": []}
        assert resp.resource_links == ["http://sp/list"]

    def test_analysis_response_structure(self):
        resp = ChatResponse(
            intent="analyze",
            reply="Here's the analysis",
            analysis={"summary": "good structure"}
        )
        assert resp.analysis["summary"] == "good structure"
