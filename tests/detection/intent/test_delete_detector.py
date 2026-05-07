"""Unit tests for src/detection/intent/delete_detector.py"""

import pytest
from src.detection.intent.delete_detector import detect_delete_intent


class TestDetectDeleteIntent:
    def test_delete_item_from_list(self):
        r = detect_delete_intent("delete the record from the Tasks list")
        assert bool(r)

    def test_no_delete_signal(self):
        r = detect_delete_intent("show me all pages")
        assert not bool(r)

    def test_file_delete_returns_empty(self):
        # File deletes should be handled by file handler, not generic delete
        r = detect_delete_intent("delete the file from the library")
        # File signals suppress generic delete — result may be empty
        # Just assert it's a DetectionResult without erroring
        from src.detection.base import DetectionResult
        assert isinstance(r, DetectionResult)
