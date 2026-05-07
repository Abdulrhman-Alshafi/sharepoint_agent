"""Unit tests for all operation detectors."""

import pytest
from src.detection.operations.site_operation_detector import detect_site_operation_intent
from src.detection.operations.page_operation_detector import detect_page_operation_intent
from src.detection.operations.library_operation_detector import detect_library_operation_intent
from src.detection.operations.file_operation_detector import detect_file_operation_intent
from src.detection.operations.list_item_operation_detector import detect_list_item_operation_intent


class TestSiteOperationDetector:
    def test_create_site(self):
        r = detect_site_operation_intent("create site for HR team")
        assert bool(r)
        assert r.intent == "site_operation"

    def test_unrelated_returns_empty(self):
        r = detect_site_operation_intent("show me the news page")
        assert not bool(r)


class TestPageOperationDetector:
    def test_create_page(self):
        r = detect_page_operation_intent("create page called Announcements")
        assert bool(r)
        assert r.intent == "page_operation"

    def test_publish_page(self):
        r = detect_page_operation_intent("publish page now")
        assert bool(r)

    def test_unrelated_returns_empty(self):
        r = detect_page_operation_intent("show me all lists")
        assert not bool(r)


class TestLibraryOperationDetector:
    def test_create_library(self):
        r = detect_library_operation_intent("create library for HR documents")
        assert bool(r)
        assert r.intent == "library_operation"

    def test_show_libraries(self):
        r = detect_library_operation_intent("show all libraries")
        assert bool(r)

    def test_unrelated_returns_empty(self):
        r = detect_library_operation_intent("create a new page")
        assert not bool(r)


class TestFileOperationDetector:
    def test_upload_file(self):
        r = detect_file_operation_intent("upload file to document library")
        assert bool(r)
        assert r.intent == "file_operation"

    def test_delete_file(self):
        r = detect_file_operation_intent("delete file from the library")
        assert bool(r)

    def test_unrelated_returns_empty(self):
        r = detect_file_operation_intent("create a new site")
        assert not bool(r)


class TestListItemOperationDetector:
    def test_add_item(self):
        r = detect_list_item_operation_intent("add a salary record for John")
        assert bool(r)
        assert r.intent == "list_item_operation"

    def test_update_item(self):
        r = detect_list_item_operation_intent("update the salary for employee John")
        assert bool(r)

    def test_delete_item(self):
        r = detect_list_item_operation_intent("delete the record from March")
        assert bool(r)

    def test_list_level_excluded(self):
        r = detect_list_item_operation_intent("create a new list")
        assert not bool(r)

    def test_delete_entire_library_excluded(self):
        r = detect_list_item_operation_intent("delete the entire Tasks document library")
        assert not bool(r)

    def test_add_column_excluded(self):
        r = detect_list_item_operation_intent("add a column to the list")
        assert not bool(r)
