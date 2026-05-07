"""Tests for AnalyzeContentUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.use_cases.analyze_content_use_case import AnalyzeContentUseCase


def _mock_analysis(resource_name="Tasks"):
    a = MagicMock()
    a.resource_name = resource_name
    a.resource_type = "list"
    a.summary = "A task tracking list"
    a.main_topics = ["tasks", "projects"]
    a.purpose = "Track work items"
    a.audience = "Team members"
    a.components = []
    return a


class TestAnalyzeContentUseCase:
    def _make_uc(self):
        analyzer = AsyncMock()
        return AnalyzeContentUseCase(analyzer), analyzer

    @pytest.mark.asyncio
    async def test_site_analysis_calls_analyze_site(self):
        uc, analyzer = self._make_uc()
        analyzer.analyze_site.return_value = _mock_analysis("My Site")
        result = await uc.execute("site", "site-1")
        analyzer.analyze_site.assert_awaited_once_with("site-1")

    @pytest.mark.asyncio
    async def test_page_analysis_calls_analyze_page(self):
        uc, analyzer = self._make_uc()
        analyzer.analyze_page.return_value = _mock_analysis("Home")
        result = await uc.execute("page", "site-1", resource_id="page-1")
        analyzer.analyze_page.assert_awaited_once_with("site-1", "page-1")

    @pytest.mark.asyncio
    async def test_list_analysis_calls_analyze_list(self):
        uc, analyzer = self._make_uc()
        analyzer.analyze_list.return_value = _mock_analysis("Tasks")
        result = await uc.execute("list", "site-1", resource_id="list-1")
        analyzer.analyze_list.assert_awaited_once_with("site-1", "list-1")

    @pytest.mark.asyncio
    async def test_library_analysis_calls_analyze_list(self):
        uc, analyzer = self._make_uc()
        analyzer.analyze_list.return_value = _mock_analysis("Docs")
        result = await uc.execute("library", "site-1", resource_id="lib-1")
        analyzer.analyze_list.assert_awaited_once_with("site-1", "lib-1")

    @pytest.mark.asyncio
    async def test_page_without_resource_id_raises_value_error(self):
        uc, analyzer = self._make_uc()
        with pytest.raises(ValueError, match="resource_id"):
            await uc.execute("page", "site-1")

    @pytest.mark.asyncio
    async def test_list_without_resource_id_raises_value_error(self):
        uc, analyzer = self._make_uc()
        with pytest.raises(ValueError, match="resource_id"):
            await uc.execute("list", "site-1")

    @pytest.mark.asyncio
    async def test_unknown_resource_type_raises_value_error(self):
        uc, analyzer = self._make_uc()
        with pytest.raises(ValueError, match="Unknown resource type"):
            await uc.execute("dashboard", "site-1", resource_id="x")

    @pytest.mark.asyncio
    async def test_site_lowercase_works(self):
        uc, analyzer = self._make_uc()
        analyzer.analyze_site.return_value = _mock_analysis()
        await uc.execute("SITE", "site-1")
        analyzer.analyze_site.assert_awaited_once()
