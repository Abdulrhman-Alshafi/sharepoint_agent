"""Tests for ProvisionResourcesUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.use_cases.provision_resources_use_case import ProvisionResourcesUseCase
from src.application.commands import ProvisionResourcesCommand
from src.application.dtos import ProvisionResourcesResponseDTO
from src.domain.exceptions import InvalidBlueprintException, HighRiskBlueprintException


def _make_blueprint():
    from src.domain.entities.core import ProvisioningBlueprint, SPSite, ActionType
    return ProvisioningBlueprint(
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


def _make_use_case():
    """Build ProvisionResourcesUseCase with all dependencies mocked."""
    bp_gen = AsyncMock()
    repo = AsyncMock()
    uc = ProvisionResourcesUseCase(blueprint_generator=bp_gen, sharepoint_repository=repo)
    return uc, bp_gen, repo


class TestProvisionResourcesUseCaseExecute:
    @pytest.mark.asyncio
    async def test_execute_returns_response_dto(self):
        uc, bp_gen, repo = _make_use_case()
        bp = _make_blueprint()

        bp_gen.validate_prompt = AsyncMock()
        bp_gen.generate_blueprint = AsyncMock(return_value=bp)

        with patch.object(uc, "_validate_prompt", new=AsyncMock()), \
             patch.object(uc, "_generate_blueprint", new=AsyncMock(return_value=bp)), \
             patch.object(uc, "_correct_blueprint_collisions", new=AsyncMock()), \
             patch.object(uc.enterprise_provisioner, "provision_term_sets", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "provision_content_types", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "provision_views", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "scaffold_workflows", new=AsyncMock(return_value=[])), \
             patch.object(uc.site_provisioner, "provision", new=AsyncMock(return_value=([], [], []))), \
             patch.object(uc.list_provisioner, "provision", new=AsyncMock(return_value=([], [], []))), \
             patch.object(uc.page_provisioner, "provision", new=AsyncMock(return_value=([], [], []))), \
             patch.object(uc.library_provisioner, "provision", new=AsyncMock(return_value=([], {}, [], []))), \
             patch.object(uc.group_provisioner, "provision", new=AsyncMock(return_value=([], []))):
            cmd = ProvisionResourcesCommand(prompt="Create a task list")
            result = await uc.execute(cmd, skip_high_risk_check=True, skip_collision_check=True)

        assert isinstance(result, ProvisionResourcesResponseDTO)

    @pytest.mark.asyncio
    async def test_execute_collects_warnings_from_provisioners(self):
        uc, bp_gen, repo = _make_use_case()
        bp = _make_blueprint()

        with patch.object(uc, "_validate_prompt", new=AsyncMock()), \
             patch.object(uc, "_generate_blueprint", new=AsyncMock(return_value=bp)), \
             patch.object(uc, "_correct_blueprint_collisions", new=AsyncMock()), \
             patch.object(uc.enterprise_provisioner, "provision_term_sets", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "provision_content_types", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "provision_views", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "scaffold_workflows", new=AsyncMock(return_value=[])), \
             patch.object(uc.site_provisioner, "provision", new=AsyncMock(return_value=([], [], ["site warning"]))), \
             patch.object(uc.list_provisioner, "provision", new=AsyncMock(return_value=([], [], ["list warning"]))), \
             patch.object(uc.page_provisioner, "provision", new=AsyncMock(return_value=([], [], []))), \
             patch.object(uc.library_provisioner, "provision", new=AsyncMock(return_value=([], {}, [], []))), \
             patch.object(uc.group_provisioner, "provision", new=AsyncMock(return_value=([], []))):
            cmd = ProvisionResourcesCommand(prompt="build it")
            result = await uc.execute(cmd, skip_high_risk_check=True, skip_collision_check=True)

        assert "site warning" in result.warnings
        assert "list warning" in result.warnings

    @pytest.mark.asyncio
    async def test_execute_skips_collision_check_when_flag_set(self):
        uc, bp_gen, repo = _make_use_case()
        bp = _make_blueprint()

        with patch.object(uc, "_validate_prompt", new=AsyncMock()), \
             patch.object(uc, "_generate_blueprint", new=AsyncMock(return_value=bp)), \
             patch.object(uc, "_correct_blueprint_collisions", new=AsyncMock()) as mock_collision, \
             patch.object(uc.enterprise_provisioner, "provision_term_sets", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "provision_content_types", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "provision_views", new=AsyncMock(return_value=[])), \
             patch.object(uc.enterprise_provisioner, "scaffold_workflows", new=AsyncMock(return_value=[])), \
             patch.object(uc.site_provisioner, "provision", new=AsyncMock(return_value=([], [], []))), \
             patch.object(uc.list_provisioner, "provision", new=AsyncMock(return_value=([], [], []))), \
             patch.object(uc.page_provisioner, "provision", new=AsyncMock(return_value=([], [], []))), \
             patch.object(uc.library_provisioner, "provision", new=AsyncMock(return_value=([], {}, [], []))), \
             patch.object(uc.group_provisioner, "provision", new=AsyncMock(return_value=([], []))):
            cmd = ProvisionResourcesCommand(prompt="go")
            await uc.execute(cmd, skip_high_risk_check=True, skip_collision_check=True)

        mock_collision.assert_not_awaited()
