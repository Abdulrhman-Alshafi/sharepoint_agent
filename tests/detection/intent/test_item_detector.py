"""Unit tests for src/detection/intent/item_detector.py"""

import pytest
from src.detection.intent.item_detector import detect_item_intent


class TestDetectItemIntent:
    def test_personal_query(self):
        r = detect_item_intent("show me my tasks")
        assert bool(r)
        assert r.intent == "personal_query"

    def test_item_add(self):
        r = detect_item_intent("add a new item to the list")
        assert bool(r)
        assert r.intent == "item_operation"

    def test_unrelated_returns_empty(self):
        r = detect_item_intent("create a site")
        assert not bool(r)
