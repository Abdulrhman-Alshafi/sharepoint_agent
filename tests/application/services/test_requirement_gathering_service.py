"""Tests for RequirementGatheringService."""

import pytest
from unittest.mock import MagicMock, patch

from src.domain.entities.conversation import ResourceType


def _make_service():
    with patch("src.application.services.requirement_gathering_service.get_conversation_repository") as mock_repo_fn:
        mock_repo_fn.return_value = MagicMock()
        from src.application.services.requirement_gathering_service import RequirementGatheringService
        svc = RequirementGatheringService()
    return svc


class TestDetectResourceIntent:
    def test_detect_list_intent(self):
        svc = _make_service()
        assert svc.detect_resource_intent("Create a new list for tracking tasks") == ResourceType.LIST

    def test_detect_page_intent(self):
        svc = _make_service()
        assert svc.detect_resource_intent("Create a landing page for HR") == ResourceType.PAGE

    def test_detect_library_intent(self):
        svc = _make_service()
        result = svc.detect_resource_intent("Create a document library for contracts")
        assert result == ResourceType.LIBRARY

    def test_detect_site_intent(self):
        svc = _make_service()
        result = svc.detect_resource_intent("Create a new team site for the marketing department")
        assert result == ResourceType.SITE

    def test_unrecognized_returns_none(self):
        svc = _make_service()
        result = svc.detect_resource_intent("Hello there, what can you do?")
        assert result is None

    def test_case_insensitive(self):
        svc = _make_service()
        result = svc.detect_resource_intent("CREATE A NEW LIST for budget")
        assert result == ResourceType.LIST

    def test_site_page_is_page_not_site(self):
        svc = _make_service()
        result = svc.detect_resource_intent("create a site page for the intranet")
        # "site page" should be a PAGE, not SITE
        assert result == ResourceType.PAGE
