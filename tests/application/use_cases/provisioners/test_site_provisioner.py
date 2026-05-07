"""Tests for SiteProvisioner (dedicated file)."""

import pytest
from unittest.mock import AsyncMock

from src.application.use_cases.provisioners.site_provisioner import SiteProvisioner
from src.domain.entities.core import ProvisioningBlueprint, SPSite, ActionType
from src.domain.exceptions import SharePointProvisioningException


def _bp(sites=None):
    if sites is None:
        sites = [SPSite(title="Default", description="", action=ActionType.CREATE)]
    return ProvisioningBlueprint(
        reasoning="t", lists=[], pages=[], custom_components=[],
        document_libraries=[], groups=[], sites=sites,
        term_sets=[], content_types=[], views=[], workflows=[],
    )


class TestSiteProvisioner:
    @pytest.mark.asyncio
    async def test_create_site_called(self):
        repo = AsyncMock()
        repo.create_site.return_value = {"webUrl": "https://contoso.sharepoint.com/sites/Proj"}
        p = SiteProvisioner(repo)
        created, links, warnings = await p.provision(_bp())
        repo.create_site.assert_awaited_once()
        assert len(created) == 1
        assert "https://contoso.sharepoint.com/sites/Proj" in links
        assert warnings == []

    @pytest.mark.asyncio
    async def test_create_without_weburl_adds_warning(self):
        repo = AsyncMock()
        repo.create_site.return_value = {}
        p = SiteProvisioner(repo)
        _, links, warnings = await p.provision(_bp())
        assert links == []
        assert len(warnings) == 1

    @pytest.mark.asyncio
    async def test_delete_action_skipped_with_warning(self):
        repo = AsyncMock()
        p = SiteProvisioner(repo)
        site = SPSite(title="OldSite", description="", action=ActionType.DELETE)
        _, _, warnings = await p.provision(_bp([site]))
        repo.create_site.assert_not_awaited()
        assert len(warnings) == 1 and "OldSite" in warnings[0]

    @pytest.mark.asyncio
    async def test_create_error_becomes_warning(self):
        repo = AsyncMock()
        repo.create_site.side_effect = SharePointProvisioningException("quota exceeded")
        p = SiteProvisioner(repo)
        created, _, warnings = await p.provision(_bp())
        assert created == []
        assert len(warnings) == 1 and "Default" in warnings[0]

    @pytest.mark.asyncio
    async def test_multiple_sites_all_provisioned(self):
        repo = AsyncMock()
        repo.create_site.side_effect = [
            {"webUrl": "https://sp.com/sites/A"},
            {"webUrl": "https://sp.com/sites/B"},
        ]
        p = SiteProvisioner(repo)
        sites = [
            SPSite(title="SiteA", description="", action=ActionType.CREATE),
            SPSite(title="SiteB", description="", action=ActionType.CREATE),
        ]
        created, links, warnings = await p.provision(_bp(sites))
        assert len(created) == 2 and len(links) == 2
