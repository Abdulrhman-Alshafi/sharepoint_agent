"""
Tests for SiteService: navigation management, hub site, and site CRUD.
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock
from src.infrastructure.services.sharepoint.site_service import SiteService
from src.domain.entities.core import SPSite


class DummyGraphClient:
    def __init__(self):
        self.calls = []
        self.responses = {}
        self.auth_service = MagicMock()
        self.http = MagicMock()

    async def post(self, endpoint, payload):
        self.calls.append(("post", endpoint, payload))
        return self.responses.get(("post", endpoint), {})

    async def get(self, endpoint):
        self.calls.append(("get", endpoint))
        return self.responses.get(("get", endpoint), {})

    async def patch(self, endpoint, payload):
        self.calls.append(("patch", endpoint, payload))
        return self.responses.get(("patch", endpoint), {})

    async def delete(self, endpoint):
        self.calls.append(("delete", endpoint))
        return self.responses.get(("delete", endpoint), {})

    async def post_beta(self, endpoint, payload):
        self.calls.append(("post_beta", endpoint, payload))
        return self.responses.get(("post_beta", endpoint), {"webUrl": "http://mock-site"})

    async def get_beta(self, endpoint):
        self.calls.append(("get_beta", endpoint))
        return self.responses.get(("get_beta", endpoint), {})


class DummyRESTClient:
    """Minimal REST client stub for navigation tests."""

    def __init__(self, site_url: str = "https://tenant.sharepoint.com/sites/test"):
        self._site_url = site_url
        self.site_id = "tenant.sharepoint.com,abc,def"
        self.auth_service = MagicMock()
        self.auth_service.get_rest_headers.return_value = {"Authorization": "Bearer token"}
        # http is a MagicMock whose async methods are patched below
        self.http = MagicMock()

    async def get_site_url(self) -> str:
        return self._site_url

@pytest.mark.asyncio
async def test_register_hub_site_success():
    client = DummyGraphClient()
    service = SiteService(client)
    result = await service.register_hub_site("site-1")
    assert result is True
    assert ("post", "/sites/site-1/registerHubSite", {}) in client.calls

@pytest.mark.asyncio
async def test_associate_with_hub_site_success():
    client = DummyGraphClient()
    service = SiteService(client)
    result = await service.associate_with_hub_site("site-1", "hub-1")
    assert result is True
    assert ("post", "/sites/site-1/associateWithHubSite", {"hubSiteId": "hub-1"}) in client.calls

@pytest.mark.asyncio
async def test_get_hub_sites_success():
    client = DummyGraphClient()
    client.responses[("get", "/sites?filter=siteCollection/root ne null and isHubSite eq true")] = {"value": [{"id": "hub-1"}]}
    service = SiteService(client)
    result = await service.get_hub_sites()
    assert result == [{"id": "hub-1"}]

@pytest.mark.asyncio
async def test_create_site_success():
    client = DummyGraphClient()
    service = SiteService(client)
    sp_site = SPSite(title="Test Site", name="test-site", description="desc", template="sts", owner_email=None)
    result = await service.create_site(sp_site)
    assert result["resource_link"] == "http://mock-site"
    assert ("post_beta", "/sites", {
        "displayName": "Test Site",
        "name": "test-site",
        "description": "desc",
        "template": "sts"
    }) in client.calls

@pytest.mark.asyncio
async def test_update_site_navigation_success():
    graph_client = DummyGraphClient()
    rest_client = DummyRESTClient()

    # Simulate existing node to delete
    get_resp = MagicMock()
    get_resp.json.return_value = {"d": {"results": [{"Id": 1}]}}
    rest_client.http.get = AsyncMock(return_value=get_resp)
    rest_client.http.delete = AsyncMock(return_value=MagicMock())
    rest_client.http.post = AsyncMock(return_value=MagicMock())

    service = SiteService(graph_client, rest_client)
    nav_items = [{"Title": "Home", "Url": "/home", "IsExternal": True}]
    result = await service.update_site_navigation("tenant.sharepoint.com/sites/test", "top", nav_items)
    assert result is True
    rest_client.http.delete.assert_called()
    rest_client.http.post.assert_called()


@pytest.mark.asyncio
async def test_get_site_navigation_success():
    graph_client = DummyGraphClient()
    rest_client = DummyRESTClient()

    get_resp = MagicMock()
    get_resp.raise_for_status = MagicMock()
    get_resp.json.return_value = {"d": {"results": [{"Title": "Home"}]}}
    rest_client.http.get = AsyncMock(return_value=get_resp)

    service = SiteService(graph_client, rest_client)
    result = await service.get_site_navigation("tenant.sharepoint.com/sites/test", "top")
    assert result == [{"Title": "Home"}]
    rest_client.http.get.assert_called()

