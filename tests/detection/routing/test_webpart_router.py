"""Unit tests for src/detection/routing/webpart_router.py"""

import pytest
from src.detection.routing.webpart_router import route_webpart


class TestRouteWebpart:
    def test_hero_detection(self):
        r = route_webpart("add a hero webpart to the page")
        assert bool(r)
        assert r.intent == "Hero"

    def test_news_detection(self):
        r = route_webpart("add a news webpart")
        assert bool(r)
        assert r.intent == "News"

    def test_quick_links_detection(self):
        r = route_webpart("add quick links section")
        assert bool(r)
        assert r.intent == "QuickLinks"

    def test_unrelated_returns_empty(self):
        r = route_webpart("delete the list")
        assert not bool(r)
