"""Tests for QueryDataUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.use_cases.query_data_use_case import QueryDataUseCase
from src.application.commands import DataQueryCommand
from src.application.dtos import DataQueryResponseDTO


def _make_query_result(**kwargs):
    defaults = dict(
        answer="42",
        data_summary="summary",
        source_list=["list1"],
        resource_link="http://sp",
        suggested_actions=["action1"],
        source_site_name="",
        source_site_url="",
        source_resource_type="",
    )
    defaults.update(kwargs)
    result = MagicMock()
    for k, v in defaults.items():
        setattr(result, k, v)
    return result


class TestQueryDataUseCase:
    def _make_use_case(self):
        svc = AsyncMock()
        return QueryDataUseCase(svc), svc

    @pytest.mark.asyncio
    async def test_execute_calls_answer_question(self):
        uc, svc = self._make_use_case()
        svc.answer_question.return_value = _make_query_result()
        await uc.execute(DataQueryCommand(question="What is the status?"))
        svc.answer_question.assert_awaited_once_with("What is the status?", site_ids=None)

    @pytest.mark.asyncio
    async def test_returns_dto_with_answer(self):
        uc, svc = self._make_use_case()
        svc.answer_question.return_value = _make_query_result(answer="The answer")
        result = await uc.execute(DataQueryCommand(question="q"))
        assert isinstance(result, DataQueryResponseDTO)
        assert result.answer == "The answer"

    @pytest.mark.asyncio
    async def test_dto_includes_source_list(self):
        uc, svc = self._make_use_case()
        svc.answer_question.return_value = _make_query_result(source_list=["Tasks"])
        result = await uc.execute(DataQueryCommand(question="q"))
        assert result.source_list == ["Tasks"]

    @pytest.mark.asyncio
    async def test_dto_includes_resource_link(self):
        uc, svc = self._make_use_case()
        svc.answer_question.return_value = _make_query_result(resource_link="http://sp/list")
        result = await uc.execute(DataQueryCommand(question="q"))
        assert result.resource_link == "http://sp/list"

    # ------------------------------------------------------------------ #
    # New tests: cross-resource discovery, site context, graph fallback   #
    # ------------------------------------------------------------------ #

    @pytest.mark.asyncio
    async def test_site_ids_forwarded_to_answer_question(self):
        """site_ids from the command must be forwarded to answer_question."""
        uc, svc = self._make_use_case()
        svc.answer_question.return_value = _make_query_result()
        site_ids = ["site1", "site2"]
        await uc.execute(DataQueryCommand(question="q", site_ids=site_ids))
        svc.answer_question.assert_awaited_once_with("q", site_ids=site_ids)

    @pytest.mark.asyncio
    async def test_site_context_in_response(self):
        """DataQueryResult.source_site_name/url/type must appear in the DTO."""
        uc, svc = self._make_use_case()
        svc.answer_question.return_value = _make_query_result(
            source_site_name="Marketing",
            source_site_url="https://tenant.sharepoint.com/sites/marketing",
            source_resource_type="list",
        )
        result = await uc.execute(DataQueryCommand(question="q"))
        assert result.source_site_name == "Marketing"
        assert result.source_site_url == "https://tenant.sharepoint.com/sites/marketing"
        assert result.source_resource_type == "list"

    @pytest.mark.asyncio
    async def test_cross_resource_discovery_site_ids_none_by_default(self):
        """When no site_ids given the command defaults to None (discover all sites)."""
        cmd = DataQueryCommand(question="What is the Q3 plan?")
        assert cmd.site_ids is None
