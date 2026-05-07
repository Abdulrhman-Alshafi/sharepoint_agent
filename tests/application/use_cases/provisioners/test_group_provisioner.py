"""Tests for GroupProvisioner (dedicated file)."""

import pytest
from unittest.mock import AsyncMock

from src.application.use_cases.provisioners.group_provisioner import GroupProvisioner
from src.domain.entities.core import ProvisioningBlueprint, SPSite, ActionType
from src.domain.entities.security import SharePointGroup
from src.domain.exceptions import SharePointProvisioningException


def _bp(groups=None):
    return ProvisioningBlueprint(
        reasoning="t", lists=[], pages=[], custom_components=[],
        document_libraries=[], groups=groups or [],
        sites=[SPSite(title="S", description="", action=ActionType.CREATE)],
        term_sets=[], content_types=[], views=[], workflows=[],
    )


def _group(name="Owners", action=ActionType.CREATE, target_library_title=None):
    return SharePointGroup(name=name, description="d", action=action,
                           target_library_title=target_library_title or "")


class TestGroupProvisioner:
    @pytest.mark.asyncio
    async def test_create_group_called(self):
        repo = AsyncMock()
        repo.create_site_group.return_value = {"id": "g-1"}
        p = GroupProvisioner(repo)
        created, warnings = await p.provision(_bp([_group()]), {})
        repo.create_site_group.assert_awaited_once()
        assert len(created) == 1 and warnings == []

    @pytest.mark.asyncio
    async def test_permission_assigned_when_target_library(self):
        repo = AsyncMock()
        repo.create_site_group.return_value = {"Id": "g-1"}
        repo.assign_library_permission.return_value = True
        p = GroupProvisioner(repo)
        await p.provision(_bp([_group(target_library_title="Docs")]), {"Docs": "lib-1"})
        repo.assign_library_permission.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_missing_library_adds_warning(self):
        repo = AsyncMock()
        repo.create_site_group.return_value = {"id": "g-1"}
        p = GroupProvisioner(repo)
        _, warnings = await p.provision(_bp([_group(target_library_title="Missing")]), {})
        assert len(warnings) == 1

    @pytest.mark.asyncio
    async def test_create_error_becomes_warning(self):
        repo = AsyncMock()
        repo.create_site_group.side_effect = SharePointProvisioningException("err")
        p = GroupProvisioner(repo)
        created, warnings = await p.provision(_bp([_group()]), {})
        assert created == [] and len(warnings) == 1

    @pytest.mark.asyncio
    async def test_permission_error_becomes_warning(self):
        repo = AsyncMock()
        repo.create_site_group.return_value = {"Id": "g-1"}
        repo.assign_library_permission.side_effect = SharePointProvisioningException("perm fail")
        p = GroupProvisioner(repo)
        _, warnings = await p.provision(_bp([_group(target_library_title="Docs")]), {"Docs": "lib-1"})
        assert len(warnings) >= 1

    @pytest.mark.asyncio
    async def test_empty_blueprint_returns_empty(self):
        repo = AsyncMock()
        p = GroupProvisioner(repo)
        created, warnings = await p.provision(_bp(), {})
        assert created == [] and warnings == []
