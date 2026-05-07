"""Unit tests for src/detection/intent/router.py"""

import pytest
from src.detection.intent.router import route_intent


class TestRouteIntent:
    def test_returns_detection_result(self):
        from src.detection.base import DetectionResult
        r = route_intent("show me my tasks")
        assert isinstance(r, DetectionResult)

    def test_page_query_wins(self):
        r = route_intent("what does the home page say?")
        assert r.intent == "page_query"

    def test_personal_query_wins(self):
        r = route_intent("show me my assigned tasks")
        assert r.intent == "personal_query"

    def test_empty_message_returns_empty(self):
        r = route_intent("")
        assert not bool(r)
