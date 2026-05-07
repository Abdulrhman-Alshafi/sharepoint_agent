"""Tests for PageProvisioner (dedicated file)."""

import pytest
from unittest.mock import AsyncMock

from src.application.use_cases.provisioners.page_provisioner import PageProvisioner
from src.domain.entities.core import ProvisioningBlueprint, SPPage, SPSite, ActionType
from src.domain.value_objects import WebPart
from src.domain.exceptions import SharePointProvisioningException


def _bp(pages=None):
    return ProvisioningBlueprint(
        reasoning="t", lists=[], pages=pages or [],
        custom_components=[], document_libraries=[], groups=[],
        sites=[SPSite(title="S", description="", action=ActionType.CREATE)],
        term_sets=[], content_types=[], views=[], workflows=[],
    )


def _page(title="Home", action=ActionType.CREATE, page_id=None):
    return SPPage(title=title, webparts=[WebPart(type="text", properties={})], action=action, page_id=page_id)


class TestPageProvisioner:
    @pytest.mark.asyncio
    async def test_create_page_called(self):
        repo = AsyncMock()
        repo.create_page.return_value = {"id": "p1", "resource_link": ""}
        p = PageProvisioner(repo)
        created, _, _ = await p.provision(_bp([_page()]))
        repo.create_page.assert_awaited_once()
        assert len(created) == 1

    @pytest.mark.asyncio
    async def test_update_page_called(self):
        repo = AsyncMock()
        repo.update_page_content.return_value = {"id": "p1", "resource_link": ""}
        p = PageProvisioner(repo)
        pg = _page(action=ActionType.UPDATE, page_id="p-id")
        await p.provision(_bp([pg]))
        repo.update_page_content.assert_awaited_once_with("p-id", pg)

    @pytest.mark.asyncio
    async def test_delete_page_called(self):
        repo = AsyncMock()
        p = PageProvisioner(repo)
        await p.provision(_bp([_page(action=ActionType.DELETE, page_id="p-id")]))
        repo.delete_page.assert_awaited_once_with("p-id")

    @pytest.mark.asyncio
    async def test_error_becomes_warning(self):
        repo = AsyncMock()
        repo.create_page.side_effect = SharePointProvisioningException("fail")
        p = PageProvisioner(repo)
        created, _, warnings = await p.provision(_bp([_page()]))
        assert created == [] and "Home" in warnings[0]

    @pytest.mark.asyncio
    async def test_multiple_pages_provisioned(self):
        repo = AsyncMock()
        repo.create_page.return_value = {"id": "p1", "resource_link": ""}
        p = PageProvisioner(repo)
        pages = [_page("A"), _page("B"), _page("C")]
        created, _, _ = await p.provision(_bp(pages))
        assert repo.create_page.await_count == 3
