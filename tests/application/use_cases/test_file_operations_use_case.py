"""Tests for FileOperationsUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.use_cases.file_operations_use_case import FileOperationsUseCase


def _make_uc():
    repo = AsyncMock()
    parser = AsyncMock()
    index = AsyncMock()
    intelligence = AsyncMock()
    uc = FileOperationsUseCase(
        sharepoint_repository=repo,
        document_parser=parser,
        document_index=index,
        document_intelligence=intelligence,
    )
    return uc, repo, parser, index, intelligence


def _mock_library_item(item_id="item-1", name="report.pdf", is_parseable=True, file_type="pdf"):
    item = MagicMock()
    item.item_id = item_id
    item.name = name
    item.size = 1024
    item.drive_id = "drv-1"
    item.web_url = "http://sp/file"
    item.is_parseable = is_parseable
    item.file_type = file_type
    return item


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_upload_returns_file_id(self):
        uc, repo, parser, index, intel = _make_uc()
        repo.upload_file.return_value = _mock_library_item()
        parsed = MagicMock()
        parsed.error = None
        parsed.text = "some text"
        parsed.word_count = 100
        parsed.table_count = 0
        parser.parse_document.return_value = parsed
        index.index_document.return_value = True
        entities = MagicMock()
        entities.monetary_amounts = []
        entities.people = []
        entities.dates = []
        entities.categories = []
        entities.dict.return_value = {}
        intel.extract_entities.return_value = entities

        result = await uc.upload_file("lib-1", "report.pdf", b"content")
        assert result["file_id"] == "item-1"

    @pytest.mark.asyncio
    async def test_upload_non_parseable_file_skips_parsing(self):
        uc, repo, parser, index, intel = _make_uc()
        repo.upload_file.return_value = _mock_library_item(is_parseable=False)
        result = await uc.upload_file("lib-1", "image.png", b"...png...")
        assert result["parsed"] is False
        parser.parse_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_includes_web_url(self):
        uc, repo, parser, index, intel = _make_uc()
        item = _mock_library_item()
        item.web_url = "http://sp/docs/report.pdf"
        repo.upload_file.return_value = item
        parsed = MagicMock()
        parsed.error = None
        parsed.text = "text"
        parsed.word_count = 5
        parsed.table_count = 0
        parser.parse_document.return_value = parsed
        index.index_document.return_value = True
        entities = MagicMock()
        entities.monetary_amounts = []
        entities.people = []
        entities.dates = []
        entities.categories = []
        entities.dict.return_value = {}
        intel.extract_entities.return_value = entities

        result = await uc.upload_file("lib-1", "report.pdf", b"data")
        assert result["web_url"] == "http://sp/docs/report.pdf"

    @pytest.mark.asyncio
    async def test_upload_with_auto_parse_false_skips_parsing(self):
        uc, repo, parser, index, intel = _make_uc()
        repo.upload_file.return_value = _mock_library_item()
        result = await uc.upload_file("lib-1", "report.pdf", b"data", auto_parse=False)
        parser.parse_document.assert_not_awaited()
        assert result["parsed"] is False


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_delete_returns_true_on_success(self):
        uc, repo, _, __, ___ = _make_uc()
        repo.delete_file.return_value = True
        result = await uc.delete_file("lib-1", "item-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_calls_repo_with_correct_args(self):
        uc, repo, _, __, ___ = _make_uc()
        repo.delete_file.return_value = True
        await uc.delete_file("lib-2", "item-99")
        repo.delete_file.assert_awaited_once_with("lib-2", "item-99")


class TestGetLibraryFiles:
    @pytest.mark.asyncio
    async def test_get_library_files_returns_list(self):
        uc, repo, _, index, ___ = _make_uc()
        # get_library_files calls get_library_items internally
        repo.get_library_items.return_value = []
        index.get_indexed_document.return_value = None
        result = await uc.get_library_files("lib-1")
        assert isinstance(result, list)
