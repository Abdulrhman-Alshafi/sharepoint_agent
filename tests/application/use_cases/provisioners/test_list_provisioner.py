"""Tests for ListProvisioner (dedicated file)."""

import pytest
from unittest.mock import AsyncMock

from src.application.use_cases.provisioners.list_provisioner import ListProvisioner
from src.domain.entities.core import ProvisioningBlueprint, SPList, SPSite, ActionType
from src.domain.value_objects import SPColumn
from src.domain.exceptions import SharePointProvisioningException


def _bp(lists=None):
    return ProvisioningBlueprint(
        reasoning="t", lists=lists or [],
        pages=[], custom_components=[], document_libraries=[], groups=[],
        sites=[SPSite(title="S", description="", action=ActionType.CREATE)],
        term_sets=[], content_types=[], views=[], workflows=[],
    )


def _list(title="Tasks", action=ActionType.CREATE, list_id=None, seed_data=None):
    col = SPColumn(name="Desc", type="text", required=False)
    lst = SPList(title=title, description="d", columns=[col], action=action, list_id=list_id)
    if seed_data:
        lst.seed_data = seed_data
    return lst


class TestListProvisioner:
    @pytest.mark.asyncio
    async def test_create_calls_repository(self):
        repo = AsyncMock()
        repo.create_list.return_value = {"id": "1", "resource_link": ""}
        p = ListProvisioner(repo)
        await p.provision(_bp([_list()]))
        repo.create_list.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_calls_update_list(self):
        repo = AsyncMock()
        repo.update_list.return_value = {"id": "1", "resource_link": ""}
        p = ListProvisioner(repo)
        lst = _list(action=ActionType.UPDATE, list_id="id-1")
        await p.provision(_bp([lst]))
        repo.update_list.assert_awaited_once_with("id-1", lst)

    @pytest.mark.asyncio
    async def test_delete_calls_delete_list(self):
        repo = AsyncMock()
        p = ListProvisioner(repo)
        await p.provision(_bp([_list(action=ActionType.DELETE, list_id="id-1")]))
        repo.delete_list.assert_awaited_once_with("id-1")

    @pytest.mark.asyncio
    async def test_error_becomes_warning(self):
        repo = AsyncMock()
        repo.create_list.side_effect = SharePointProvisioningException("fail")
        p = ListProvisioner(repo)
        _, _, warnings = await p.provision(_bp([_list()]))
        assert len(warnings) == 1 and "Tasks" in warnings[0]

    @pytest.mark.asyncio
    async def test_seed_data_triggers_seed_call(self):
        repo = AsyncMock()
        repo.create_list.return_value = {"id": "list-99", "resource_link": ""}
        p = ListProvisioner(repo)
        lst = _list(seed_data=[{"Title": "Item"}])
        await p.provision(_bp([lst]))
        repo.seed_list_data.assert_awaited_once_with("list-99", lst.seed_data)

    @pytest.mark.asyncio
    async def test_empty_blueprint_no_calls(self):
        repo = AsyncMock()
        p = ListProvisioner(repo)
        created, links, warnings = await p.provision(_bp())
        assert created == [] and warnings == []
        repo.create_list.assert_not_awaited()
