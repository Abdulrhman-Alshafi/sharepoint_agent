"""Unit tests for src/detection/routing/resource_type_router.py"""

import pytest
from src.detection.routing.resource_type_router import route_resource_type


class TestRouteResourceType:
    def test_site_detection(self):
        r = route_resource_type("create a new SharePoint site")
        assert bool(r)
        assert r.intent == "SITE"

    def test_page_detection(self):
        r = route_resource_type("add a new page to the intranet")
        assert bool(r)
        assert r.intent == "PAGE"

    def test_library_detection(self):
        r = route_resource_type("create a document library")
        assert bool(r)
        assert r.intent == "LIBRARY"

    def test_list_detection(self):
        r = route_resource_type("create a new list for tasks")
        assert bool(r)
        assert r.intent == "LIST"

    def test_unrelated_returns_empty(self):
        r = route_resource_type("what is the weather today")
        assert not bool(r)
