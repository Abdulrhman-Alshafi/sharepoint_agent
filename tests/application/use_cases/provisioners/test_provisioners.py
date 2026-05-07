"""Tests for all provisioners (list, page, library, group, site)."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.domain.entities.core import (
    ProvisioningBlueprint, SPList, SPPage, ActionType, SPSite
)
from src.domain.entities.document import DocumentLibrary
from src.domain.value_objects import SPColumn, WebPart
from src.domain.exceptions import SharePointProvisioningException


# ──────────────── Helpers ────────────────────────────────────────────────────

def _blueprint(**kwargs):
    defaults = dict(
        reasoning="test",
        lists=[],
        pages=[],
        custom_components=[],
        document_libraries=[],
        groups=[],
        sites=[SPSite(title="Default", description="", action=ActionType.CREATE)],
        term_sets=[],
        content_types=[],
        views=[],
        workflows=[],
    )
    defaults.update(kwargs)
    return ProvisioningBlueprint(**defaults)


def _sp_list(title="Tasks", action=ActionType.CREATE, list_id=None):
    col = SPColumn(name="Description", type="text", required=False)
    return SPList(
        title=title,
        description="desc",
        columns=[col],
        action=action,
        list_id=list_id,
    )


def _sp_page(title="Home", action=ActionType.CREATE, page_id=None):
    return SPPage(title=title, webparts=[WebPart(type="text", properties={})], action=action, page_id=page_id)


# ──────────────── ListProvisioner ────────────────────────────────────────────

class TestListProvisioner:
    def _make_provisioner(self):
        from src.application.use_cases.provisioners.list_provisioner import ListProvisioner
        repo = AsyncMock()
        return ListProvisioner(repo), repo

    @pytest.mark.asyncio
    async def test_create_action_calls_create_list(self):
        provisioner, repo = self._make_provisioner()
        repo.create_list.return_value = {"id": "1", "resource_link": "http://link"}
        blueprint = _blueprint(lists=[_sp_list()])
        created, links, warnings = await provisioner.provision(blueprint)
        repo.create_list.assert_awaited_once()
        assert len(created) == 1

    @pytest.mark.asyncio
    async def test_update_action_calls_update_list(self):
        provisioner, repo = self._make_provisioner()
        repo.update_list.return_value = {"id": "1", "resource_link": "http://link"}
        sp_list = _sp_list(action=ActionType.UPDATE, list_id="id-1")
        blueprint = _blueprint(lists=[sp_list])
        await provisioner.provision(blueprint)
        repo.update_list.assert_awaited_once_with("id-1", sp_list)

    @pytest.mark.asyncio
    async def test_delete_action_calls_delete_list(self):
        provisioner, repo = self._make_provisioner()
        sp_list = _sp_list(action=ActionType.DELETE, list_id="id-1")
        blueprint = _blueprint(lists=[sp_list])
        await provisioner.provision(blueprint)
        repo.delete_list.assert_awaited_once_with("id-1")

    @pytest.mark.asyncio
    async def test_provisioning_error_adds_warning(self):
        provisioner, repo = self._make_provisioner()
        repo.create_list.side_effect = SharePointProvisioningException("boom")
        blueprint = _blueprint(lists=[_sp_list()])
        created, links, warnings = await provisioner.provision(blueprint)
        assert created == []
        assert len(warnings) == 1
        assert "Tasks" in warnings[0]

    @pytest.mark.asyncio
    async def test_seed_data_triggers_seed_call(self):
        provisioner, repo = self._make_provisioner()
        repo.create_list.return_value = {"id": "list-99", "resource_link": ""}
        sp_list = _sp_list()
        sp_list.seed_data = [{"Title": "Item 1"}]
        blueprint = _blueprint(lists=[sp_list])
        await provisioner.provision(blueprint)
        repo.seed_list_data.assert_awaited_once_with("list-99", sp_list.seed_data)

    @pytest.mark.asyncio
    async def test_empty_blueprint_returns_empty(self):
        provisioner, repo = self._make_provisioner()
        created, links, warnings = await provisioner.provision(_blueprint())
        assert created == [] and links == [] and warnings == []


# ──────────────── PageProvisioner ────────────────────────────────────────────

class TestPageProvisioner:
    def _make_provisioner(self):
        from src.application.use_cases.provisioners.page_provisioner import PageProvisioner
        repo = AsyncMock()
        return PageProvisioner(repo), repo

    @pytest.mark.asyncio
    async def test_create_page_calls_repository(self):
        provisioner, repo = self._make_provisioner()
        repo.create_page.return_value = {"id": "p1", "resource_link": "http://page"}
        blueprint = _blueprint(pages=[_sp_page()])
        created, links, warnings = await provisioner.provision(blueprint)
        repo.create_page.assert_awaited_once()
        assert len(created) == 1

    @pytest.mark.asyncio
    async def test_update_page_calls_update(self):
        provisioner, repo = self._make_provisioner()
        repo.update_page_content.return_value = {"id": "p1", "resource_link": ""}
        sp_page = _sp_page(action=ActionType.UPDATE, page_id="p-id")
        blueprint = _blueprint(pages=[sp_page])
        await provisioner.provision(blueprint)
        repo.update_page_content.assert_awaited_once_with("p-id", sp_page)

    @pytest.mark.asyncio
    async def test_delete_page_calls_delete(self):
        provisioner, repo = self._make_provisioner()
        sp_page = _sp_page(action=ActionType.DELETE, page_id="p-id")
        blueprint = _blueprint(pages=[sp_page])
        await provisioner.provision(blueprint)
        repo.delete_page.assert_awaited_once_with("p-id")

    @pytest.mark.asyncio
    async def test_provisioning_error_adds_warning_not_raises(self):
        provisioner, repo = self._make_provisioner()
        repo.create_page.side_effect = SharePointProvisioningException("fail")
        blueprint = _blueprint(pages=[_sp_page()])
        created, links, warnings = await provisioner.provision(blueprint)
        assert created == []
        assert len(warnings) == 1


# ──────────────── LibraryProvisioner ─────────────────────────────────────────

class TestLibraryProvisioner:
    def _make_provisioner(self):
        from src.application.use_cases.provisioners.library_provisioner import LibraryProvisioner
        repo = AsyncMock()
        return LibraryProvisioner(repo), repo

    @pytest.mark.asyncio
    async def test_create_library_called_for_create_action(self):
        provisioner, repo = self._make_provisioner()
        repo.create_document_library.return_value = {"id": "lib-1", "title": "Docs", "resource_link": ""}
        lib = DocumentLibrary(title="Docs", description="desc", action=ActionType.CREATE)
        blueprint = _blueprint(document_libraries=[lib])
        _, _, _, warnings = await provisioner.provision(blueprint)
        repo.create_document_library.assert_awaited_once()
        assert warnings == []

    @pytest.mark.asyncio
    async def test_library_error_adds_warning(self):
        provisioner, repo = self._make_provisioner()
        repo.create_document_library.side_effect = SharePointProvisioningException("fail")
        lib = DocumentLibrary(title="Docs", description="desc", action=ActionType.CREATE)
        blueprint = _blueprint(document_libraries=[lib])
        _, _, _, warnings = await provisioner.provision(blueprint)
        assert len(warnings) >= 1
