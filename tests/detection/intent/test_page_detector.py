"""Unit tests for src/detection/intent/page_detector.py"""

import pytest
from src.detection.intent.page_detector import detect_page_intent


class TestDetectPageIntent:
    def test_explicit_phrase_match(self):
        r = detect_page_intent("what does the home page say?")
        assert bool(r)
        assert r.intent == "page_query"
        assert r.score >= 0.9

    def test_page_query_about_content(self):
        r = detect_page_intent("tell me about the news page content")
        assert bool(r)
        assert r.intent == "page_query"

    def test_unrelated_message_returns_empty(self):
        r = detect_page_intent("create a new document library")
        assert not bool(r)

    def test_returns_detection_result_type(self):
        from src.detection.base import DetectionResult
        r = detect_page_intent("any query")
        assert isinstance(r, DetectionResult)
