"""Unit tests for src/detection/intent/update_detector.py"""

import pytest
from src.detection.intent.update_detector import detect_update_intent


class TestDetectUpdateIntent:
    def test_record_update(self):
        r = detect_update_intent("update the salary for John in the list")
        assert bool(r)

    def test_schema_update_returns_result(self):
        r = detect_update_intent("rename the Title column")
        assert bool(r)
        assert r.intent == "update"

    def test_no_update_signal(self):
        r = detect_update_intent("show me all pages")
        assert not bool(r)
