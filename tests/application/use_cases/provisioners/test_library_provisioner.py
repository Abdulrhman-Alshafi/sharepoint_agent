"""Tests for LibraryProvisioner (dedicated file)."""

import pytest
from unittest.mock import AsyncMock

from src.application.use_cases.provisioners.library_provisioner import LibraryProvisioner
from src.domain.entities.core import ProvisioningBlueprint, SPSite, ActionType
from src.domain.entities.document import DocumentLibrary
from src.domain.exceptions import SharePointProvisioningException


def _bp(libs=None):
    return ProvisioningBlueprint(
        reasoning="t", lists=[], pages=[], custom_components=[],
        document_libraries=libs or [], groups=[],
        sites=[SPSite(title="S", description="", action=ActionType.CREATE)],
        term_sets=[], content_types=[], views=[], workflows=[],
    )


def _lib(title="Docs", action=ActionType.CREATE, library_id=None):
    lib = DocumentLibrary(title=title, description="desc", action=action)
    if library_id:
        lib.library_id = library_id
    return lib


class TestLibraryProvisioner:
    @pytest.mark.asyncio
    async def test_create_library_called(self):
        repo = AsyncMock()
        repo.create_document_library.return_value = {"id": "lib-1", "title": "Docs", "resource_link": ""}
        p = LibraryProvisioner(repo)
        created, _, _, warnings = await p.provision(_bp([_lib()]))
        repo.create_document_library.assert_awaited_once()
        assert created and warnings == []

    @pytest.mark.asyncio
    async def test_create_populates_title_to_id_map(self):
        repo = AsyncMock()
        repo.create_document_library.return_value = {"id": "lib-99", "resource_link": ""}
        p = LibraryProvisioner(repo)
        _, title_map, _, _ = await p.provision(_bp([_lib(title="Contracts")]))
        assert title_map.get("Contracts") == "lib-99"

    @pytest.mark.asyncio
    async def test_update_library_calls_update(self):
        repo = AsyncMock()
        repo.update_document_library.return_value = {"webUrl": "http://sp"}
        p = LibraryProvisioner(repo)
        lib = _lib(action=ActionType.UPDATE, library_id="lib-id")
        await p.provision(_bp([lib]))
        repo.update_document_library.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_library_calls_delete(self):
        repo = AsyncMock()
        repo.delete_document_library.return_value = True
        p = LibraryProvisioner(repo)
        lib = _lib(action=ActionType.DELETE, library_id="lib-id")
        await p.provision(_bp([lib]))
        repo.delete_document_library.assert_awaited_once_with("lib-id")

    @pytest.mark.asyncio
    async def test_error_becomes_warning(self):
        repo = AsyncMock()
        repo.create_document_library.side_effect = SharePointProvisioningException("fail")
        p = LibraryProvisioner(repo)
        _, _, _, warnings = await p.provision(_bp([_lib()]))
        assert len(warnings) == 1 and "Docs" in warnings[0]

    @pytest.mark.asyncio
    async def test_empty_blueprint_returns_empty(self):
        repo = AsyncMock()
        p = LibraryProvisioner(repo)
        created, title_map, links, warnings = await p.provision(_bp())
        assert created == [] and title_map == {} and warnings == []
