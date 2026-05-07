"""Tests for DocumentLibrary and LibraryItem domain entities."""

import pytest
from datetime import datetime, timezone
from src.domain.entities.document import DocumentLibrary, LibraryItem
from src.domain.entities.core import ActionType


class TestDocumentLibrary:
    def test_valid_creation(self):
        lib = DocumentLibrary(title="Contracts", description="Legal docs")
        assert lib.title == "Contracts"

    def test_empty_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            DocumentLibrary(title="", description="d")

    def test_whitespace_title_raises(self):
        with pytest.raises(ValueError, match="title cannot be empty"):
            DocumentLibrary(title="   ", description="d")

    def test_to_graph_api_payload(self):
        lib = DocumentLibrary(title="Contracts", description="Legal documents")
        payload = lib.to_graph_api_payload()
        assert payload["displayName"] == "Contracts"
        assert payload["description"] == "Legal documents"
        assert payload["list"]["template"] == "documentLibrary"

    def test_default_action_is_create(self):
        lib = DocumentLibrary(title="T", description="d")
        assert lib.action == ActionType.CREATE

    def test_content_types_default_to_empty(self):
        lib = DocumentLibrary(title="T", description="d")
        assert lib.content_types == []

    def test_seed_data_default_to_empty(self):
        lib = DocumentLibrary(title="T", description="d")
        assert lib.seed_data == []


class TestLibraryItem:
    def _make_item(self, **kwargs):
        defaults = {
            "name": "report.pdf",
            "item_id": "item-001",
            "library_id": "lib-001",
            "drive_id": "drive-001",
            "size": 1048576,  # 1 MB
        }
        defaults.update(kwargs)
        return LibraryItem(**defaults)

    def test_valid_creation(self):
        item = self._make_item()
        assert item.name == "report.pdf"
        assert item.size == 1048576

    def test_empty_name_raises(self):
        with pytest.raises(ValueError, match="name cannot be empty"):
            self._make_item(name="")

    def test_whitespace_name_raises(self):
        with pytest.raises(ValueError, match="name cannot be empty"):
            self._make_item(name="  ")

    def test_negative_size_raises(self):
        with pytest.raises(ValueError, match="size cannot be negative"):
            self._make_item(size=-1)

    def test_zero_size_is_valid(self):
        item = self._make_item(size=0)
        assert item.size == 0

    def test_size_mb_property(self):
        item = self._make_item(size=1048576)
        assert item.size_mb == pytest.approx(1.0)

    def test_size_mb_half_mb(self):
        item = self._make_item(size=524288)
        assert item.size_mb == pytest.approx(0.5)

    def test_size_mb_zero(self):
        item = self._make_item(size=0)
        assert item.size_mb == 0.0

    @pytest.mark.parametrize("ext", [".pdf", ".docx", ".doc", ".xlsx", ".xls", ".txt", ".csv"])
    def test_is_parseable_true_for_parseable_extensions(self, ext):
        item = self._make_item(file_type=ext)
        assert item.is_parseable is True

    @pytest.mark.parametrize("ext", [".png", ".jpg", ".exe", ".zip", ".mp4", ".pptx"])
    def test_is_parseable_false_for_non_parseable(self, ext):
        item = self._make_item(file_type=ext)
        assert item.is_parseable is False

    def test_is_parseable_false_when_file_type_none(self):
        item = self._make_item(file_type=None)
        assert item.is_parseable is False

    def test_is_parseable_case_insensitive(self):
        item = self._make_item(file_type=".PDF")
        assert item.is_parseable is True

    def test_from_graph_api_response_full(self):
        data = {
            "id": "item-123",
            "name": "document.docx",
            "size": 2048,
            "createdDateTime": "2024-01-15T10:00:00Z",
            "lastModifiedDateTime": "2024-06-01T12:30:00Z",
            "createdBy": {"user": {"displayName": "Alice"}},
            "lastModifiedBy": {"user": {"displayName": "Bob"}},
            "webUrl": "https://contoso.sharepoint.com/doc",
            "@microsoft.graph.downloadUrl": "https://download.example.com/doc",
            "file": {"mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        }
        item = LibraryItem.from_graph_api_response(data, library_id="lib-1", drive_id="drv-1")
        assert item.name == "document.docx"
        assert item.item_id == "item-123"
        assert item.size == 2048
        assert item.created_by == "Alice"
        assert item.modified_by == "Bob"
        assert item.web_url == "https://contoso.sharepoint.com/doc"
        assert item.download_url == "https://download.example.com/doc"
        assert isinstance(item.created_datetime, datetime)

    def test_from_graph_api_response_missing_optional_fields(self):
        data = {
            "id": "item-456",
            "name": "notes.txt",
            "size": 512,
        }
        item = LibraryItem.from_graph_api_response(data, library_id="lib-1", drive_id="drv-1")
        assert item.name == "notes.txt"
        assert item.created_datetime is None
        assert item.created_by is None
        assert item.web_url is None
        assert item.download_url is None
