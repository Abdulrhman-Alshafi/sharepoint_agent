"""Tests for EnterpriseProvisioner (dedicated file)."""

import pytest
from unittest.mock import AsyncMock

from src.application.use_cases.provisioners.enterprise_provisioner import EnterpriseProvisioner
from src.domain.entities.core import ProvisioningBlueprint, SPSite, ActionType
from src.domain.entities.enterprise import TermSet, ContentType, SPView, WorkflowScaffold
from src.domain.exceptions import SharePointProvisioningException


def _bp(**kwargs):
    defaults = dict(
        reasoning="t", lists=[], pages=[], custom_components=[],
        document_libraries=[], groups=[],
        sites=[SPSite(title="S", description="", action=ActionType.CREATE)],
        term_sets=[], content_types=[], views=[], workflows=[],
    )
    defaults.update(kwargs)
    return ProvisioningBlueprint(**defaults)


class TestEnterpriseProvisionerTermSets:
    @pytest.mark.asyncio
    async def test_provision_term_set_create(self):
        repo = AsyncMock()
        repo.create_term_set.return_value = {"id": "ts-1"}
        p = EnterpriseProvisioner(repo)
        result = await p.provision_term_sets(
            _bp(term_sets=[TermSet(name="Colors", terms=["Red", "Blue"])])
        )
        repo.create_term_set.assert_awaited_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_provision_term_set_error_continues(self):
        repo = AsyncMock()
        repo.create_term_set.side_effect = SharePointProvisioningException("fail")
        p = EnterpriseProvisioner(repo)
        result = await p.provision_term_sets(
            _bp(term_sets=[TermSet(name="Colors", terms=["Red"])])
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_provision_term_sets_empty_returns_empty(self):
        repo = AsyncMock()
        p = EnterpriseProvisioner(repo)
        result = await p.provision_term_sets(_bp())
        assert result == []


class TestEnterpriseProvisionerContentTypes:
    @pytest.mark.asyncio
    async def test_provision_content_type_create(self):
        repo = AsyncMock()
        repo.create_content_type.return_value = {"id": "ct-1"}
        p = EnterpriseProvisioner(repo)
        result = await p.provision_content_types(
            _bp(content_types=[ContentType(name="Document", description="d")])
        )
        repo.create_content_type.assert_awaited_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_provision_content_type_error_continues(self):
        repo = AsyncMock()
        repo.create_content_type.side_effect = SharePointProvisioningException("fail")
        p = EnterpriseProvisioner(repo)
        result = await p.provision_content_types(
            _bp(content_types=[ContentType(name="Doc", description="d")])
        )
        assert result == []


class TestEnterpriseProvisionerViews:
    @pytest.mark.asyncio
    async def test_provision_view_create(self):
        repo = AsyncMock()
        repo.create_view.return_value = {"id": "v-1"}
        p = EnterpriseProvisioner(repo)
        result = await p.provision_views(
            _bp(views=[SPView(title="All Items", target_list_title="Tasks", columns=["Title"])])
        )
        repo.create_view.assert_awaited_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_provision_view_error_continues(self):
        repo = AsyncMock()
        repo.create_view.side_effect = SharePointProvisioningException("fail")
        p = EnterpriseProvisioner(repo)
        result = await p.provision_views(
            _bp(views=[SPView(title="V", target_list_title="L", columns=["Title"])])
        )
        assert result == []


class TestEnterpriseProvisionerWorkflows:
    @pytest.mark.asyncio
    async def test_scaffold_workflows_returns_name_dicts(self):
        repo = AsyncMock()
        p = EnterpriseProvisioner(repo)
        result = await p.scaffold_workflows(
            _bp(workflows=[
                WorkflowScaffold(name="Approval", trigger_type="item_created", target_list_title="Tasks"),
                WorkflowScaffold(name="Notification", trigger_type="item_modified", target_list_title="Docs"),
            ])
        )
        names = [r["name"] for r in result]
        assert "Approval" in names and "Notification" in names

    @pytest.mark.asyncio
    async def test_scaffold_workflows_empty(self):
        repo = AsyncMock()
        p = EnterpriseProvisioner(repo)
        result = await p.scaffold_workflows(_bp())
        assert result == []
