"""Unit tests for src/detection/intent/analyze_detector.py"""

import pytest
from src.detection.intent.analyze_detector import detect_analyze_intent


class TestDetectAnalyzeIntent:
    def test_summarize_page(self):
        r = detect_analyze_intent("summarize the home page")
        assert bool(r)
        assert r.intent in ("analyze", "page_query")

    def test_analyze_document(self):
        r = detect_analyze_intent("analyze the document library")
        assert bool(r)

    def test_unrelated_returns_empty(self):
        r = detect_analyze_intent("create a new site")
        assert not bool(r)
