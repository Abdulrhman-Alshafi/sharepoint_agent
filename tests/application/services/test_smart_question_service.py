"""Tests for SmartQuestionService."""

import pytest
from unittest.mock import AsyncMock, patch

from src.application.services.smart_question_service import SmartQuestionService
from src.domain.entities.conversation import ConversationContext, FieldSource, ResourceType


def _service():
    return SmartQuestionService()


class TestSmartQuestionServiceConfig:
    def test_confidence_thresholds(self):
        svc = _service()
        assert svc.confidence_threshold_skip == 0.8
        assert svc.confidence_threshold_confirm == 0.5


class TestDetermineMissingFields:
    def test_completely_missing_fields(self):
        svc = _service()
        result = svc.determine_missing_fields(
            ResourceType.LIST,
            {},
            ["title", "description"],
        )
        assert "title" in result
        assert "description" in result

    def test_high_confidence_fields_not_missing(self):
        svc = _service()
        known = {
            "title": FieldSource(field_name="title", value="My List",
                                  source="user_stated", confidence=0.95)
        }
        result = svc.determine_missing_fields(ResourceType.LIST, known, ["title"])
        assert "title" not in result

    def test_low_confidence_below_confirm_threshold_is_missing(self):
        svc = _service()
        known = {
            "title": FieldSource(field_name="title", value="?",
                                  source="inferred", confidence=0.3)
        }
        result = svc.determine_missing_fields(ResourceType.LIST, known, ["title"])
        assert "title" in result

    def test_medium_confidence_between_thresholds_not_missing(self):
        # confidence 0.6 is between confirm (0.5) and skip (0.8) → not added to missing
        svc = _service()
        known = {
            "title": FieldSource(field_name="title", value="X",
                                  source="inferred", confidence=0.6)
        }
        result = svc.determine_missing_fields(ResourceType.LIST, known, ["title"])
        assert "title" not in result


class TestShouldSkipQuestion:
    def test_skip_when_confidence_high(self):
        svc = _service()
        known = {"title": FieldSource(field_name="title", value="A", source="user_stated", confidence=0.9)}
        assert svc.should_skip_question("title", known) is True

    def test_do_not_skip_when_missing(self):
        svc = _service()
        assert svc.should_skip_question("title", {}) is False

    def test_do_not_skip_when_confidence_below_threshold(self):
        svc = _service()
        known = {"title": FieldSource(field_name="title", value="A", source="inferred", confidence=0.7)}
        assert svc.should_skip_question("title", known) is False


class TestShouldConfirmQuestion:
    def test_confirm_medium_confidence(self):
        svc = _service()
        known = {"title": FieldSource(field_name="title", value="A", source="inferred", confidence=0.6)}
        assert svc.should_confirm_question("title", known) is True

    def test_no_confirm_when_missing(self):
        svc = _service()
        assert svc.should_confirm_question("title", {}) is False


class TestExtractKnownFacts:
    @pytest.mark.asyncio
    async def test_extract_returns_field_sources(self):
        svc = _service()
        mock_extracted = AsyncMock()
        mock_extracted.facts = {"title": "Project Alpha"}
        mock_extracted.confidence_scores = {"title": 0.95}

        with patch.object(svc, "_ai_extract_facts", return_value=mock_extracted):
            result = await svc.extract_known_facts(
                "Create a list called Project Alpha",
                ResourceType.LIST,
            )
        assert "title" in result
        assert result["title"].value == "Project Alpha"
        assert result["title"].confidence == 0.95

    @pytest.mark.asyncio
    async def test_context_facts_merged(self):
        svc = _service()
        mock_extracted = AsyncMock()
        mock_extracted.facts = {}
        mock_extracted.confidence_scores = {}

        ctx = ConversationContext()
        ctx.extracted_facts = {"description": {"value": "From ctx"}}
        ctx.confidence_scores = {"description": 0.7}

        with patch.object(svc, "_ai_extract_facts", return_value=mock_extracted):
            result = await svc.extract_known_facts("hello", ResourceType.LIST, context=ctx)
        assert "description" in result
        assert result["description"].source == "context"
