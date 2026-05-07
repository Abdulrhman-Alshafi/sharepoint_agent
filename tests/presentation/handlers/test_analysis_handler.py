"""Tests for analysis_handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleAnalysisOperations:
    @pytest.mark.asyncio
    async def test_site_analysis_returns_chat_response(self):
        mock_repo = MagicMock()
        mock_repo.graph_client = MagicMock()
        mock_repo.rest_client = MagicMock()

        mock_analysis = MagicMock()
        mock_analysis.content_types = []
        mock_analysis.lists_found = []
        mock_analysis.pages_found = []
        mock_analysis.libraries_found = []
        mock_analysis.summary = "Site analysis complete"

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.services.sharepoint.list_service.ListService"), \
             patch("src.infrastructure.services.sharepoint.page_service.PageService"), \
             patch("src.infrastructure.services.sharepoint.library_service.LibraryService"), \
             patch("src.infrastructure.services.content_analyzer.ContentAnalyzerService") as mock_ca_cls:

            mock_ca = AsyncMock()
            mock_ca.analyze_site.return_value = mock_analysis
            mock_ca_cls.return_value = mock_ca

            from src.presentation.api.handlers.analysis_handler import handle_analysis_operations
            result = await handle_analysis_operations(
                message="analyze this site",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "analyze"

    @pytest.mark.asyncio
    async def test_page_keywords_return_guidance(self):
        mock_repo = MagicMock()
        mock_repo.graph_client = MagicMock()
        mock_repo.rest_client = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.services.sharepoint.list_service.ListService"), \
             patch("src.infrastructure.services.sharepoint.page_service.PageService"), \
             patch("src.infrastructure.services.sharepoint.library_service.LibraryService"), \
             patch("src.infrastructure.services.content_analyzer.ContentAnalyzerService"):

            from src.presentation.api.handlers.analysis_handler import handle_analysis_operations
            result = await handle_analysis_operations(
                message="analyze this page",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)
