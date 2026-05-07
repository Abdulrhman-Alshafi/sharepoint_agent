"""Tests for LibraryAnalysisUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.use_cases.library_analysis_use_case import LibraryAnalysisUseCase


def _make_uc():
    repo = AsyncMock()
    doc_index = AsyncMock()
    doc_parser = AsyncMock()
    doc_intelligence = AsyncMock()
    lib_intelligence = AsyncMock()
    uc = LibraryAnalysisUseCase(
        sharepoint_repository=repo,
        document_index=doc_index,
        document_parser=doc_parser,
        document_intelligence=doc_intelligence,
        library_intelligence=lib_intelligence,
    )
    return uc, repo, doc_index, doc_parser, doc_intelligence, lib_intelligence


def _mock_summary(lib_name="Contracts"):
    s = MagicMock()
    s.library_name = lib_name
    s.library_id = "lib-1"
    s.total_files = 10
    s.file_type_distribution = {"pdf": 5, "docx": 5}
    s.total_size_mb = 25.0
    s.main_themes = ["contracts", "agreements"]
    s.summary = "A library of legal documents"
    s.indexed_files = 8
    s.key_statistics = {}
    return s


class TestSummarizeLibrary:
    @pytest.mark.asyncio
    async def test_summarize_returns_dict_with_library_name(self):
        uc, repo, index, _, __, lib_intel = _make_uc()
        repo.get_library_items.return_value = []
        index.get_library_documents.return_value = []
        index.get_library_stats.return_value = {}
        lib_intel.summarize_library.return_value = _mock_summary("Contracts")

        result = await uc.summarize_library("lib-1", "Contracts")
        assert result["library_name"] == "Contracts"

    @pytest.mark.asyncio
    async def test_summarize_includes_total_files(self):
        uc, repo, index, _, __, lib_intel = _make_uc()
        repo.get_library_items.return_value = []
        index.get_library_documents.return_value = []
        index.get_library_stats.return_value = {}
        lib_intel.summarize_library.return_value = _mock_summary()

        result = await uc.summarize_library("lib-1", "Docs")
        assert result["total_files"] == 10

    @pytest.mark.asyncio
    async def test_summarize_includes_main_themes(self):
        uc, repo, index, _, __, lib_intel = _make_uc()
        repo.get_library_items.return_value = []
        index.get_library_documents.return_value = []
        index.get_library_stats.return_value = {}
        lib_intel.summarize_library.return_value = _mock_summary()

        result = await uc.summarize_library("lib-1", "Contracts")
        assert "main_themes" in result

    @pytest.mark.asyncio
    async def test_summarize_calls_library_intelligence(self):
        uc, repo, index, _, __, lib_intel = _make_uc()
        repo.get_library_items.return_value = []
        index.get_library_documents.return_value = []
        index.get_library_stats.return_value = {}
        lib_intel.summarize_library.return_value = _mock_summary()

        await uc.summarize_library("lib-1", "Docs")
        lib_intel.summarize_library.assert_awaited_once()


class TestCompareLibraries:
    @pytest.mark.asyncio
    async def test_compare_requires_at_least_two_libraries(self):
        uc, _, __, ___, ____, _____ = _make_uc()
        with pytest.raises(ValueError, match="At least 2"):
            await uc.compare_libraries(["only-one"])

    @pytest.mark.asyncio
    async def test_compare_with_empty_list_raises(self):
        uc, _, __, ___, ____, _____ = _make_uc()
        with pytest.raises(ValueError):
            await uc.compare_libraries([])
