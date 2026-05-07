"""Unit tests for src/detection/routing/page_content_router.py"""

import pytest
from src.detection.routing.page_content_router import detect_page_content_upgrade


class TestDetectPageContentUpgrade:
    def test_page_content_upgrade_detected(self):
        r = detect_page_content_upgrade("what is on the home page")
        assert bool(r)
        assert r.intent == "page_content_upgrade"

    def test_unrelated_returns_empty(self):
        r = detect_page_content_upgrade("create a new library")
        assert not bool(r)
