"""Tests for DeleteResourceUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.use_cases.delete_resource_use_case import DeleteResourceUseCase


class TestDeleteResourceUseCase:
    def _make_uc(self):
        repo = AsyncMock()
        uc = DeleteResourceUseCase(repo)
        return uc, repo

    # ── Unconfirmed deletes return impact analysis ────────────────────────────

    @pytest.mark.asyncio
    async def test_unconfirmed_returns_requires_confirmation(self):
        uc, repo = self._make_uc()
        with patch.object(uc, "_analyze_deletion_impact", new=AsyncMock()) as mock_impact:
            mock_impact.return_value = MagicMock()
            result = await uc.execute("list", "site-1", "list-1", "My List", confirmed=False)
        assert result["requires_confirmation"] is True

    @pytest.mark.asyncio
    async def test_unconfirmed_returns_impact(self):
        uc, repo = self._make_uc()
        mock_impact = MagicMock()
        with patch.object(uc, "_analyze_deletion_impact", new=AsyncMock(return_value=mock_impact)):
            result = await uc.execute("list", "site-1", "list-1", "My List", confirmed=False)
        assert result["impact"] is mock_impact

    @pytest.mark.asyncio
    async def test_confirmation_text_contains_resource_name(self):
        uc, repo = self._make_uc()
        with patch.object(uc, "_analyze_deletion_impact", new=AsyncMock(return_value=MagicMock())):
            result = await uc.execute("list", "s", "l", "Budget List", confirmed=False)
        assert "budget list" in result["confirmation_text"]

    # ── Confirmed deletes execute deletion ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_confirmed_delete_calls_execute_deletion(self):
        uc, repo = self._make_uc()
        with patch.object(uc, "_analyze_deletion_impact", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_execute_deletion", new=AsyncMock(return_value=True)) as mock_exec:
            result = await uc.execute("list", "site-1", "list-1", "Tasks", confirmed=True)
        mock_exec.assert_awaited_once_with("list", "site-1", "list-1")
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_failed_deletion_returns_failure_message(self):
        uc, repo = self._make_uc()
        with patch.object(uc, "_analyze_deletion_impact", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_execute_deletion", new=AsyncMock(return_value=False)):
            result = await uc.execute("list", "s", "l", "Tasks", confirmed=True)
        assert "failed" in result["message"].lower()

    # ── Impact analysis for different resource types ──────────────────────────

    @pytest.mark.asyncio
    async def test_site_deletion_high_risk(self):
        uc, repo = self._make_uc()
        impact = await uc._analyze_deletion_impact("site", "s-1", "site-id", "My Site")
        from src.domain.entities.preview import RiskLevel
        assert impact.risk_level == RiskLevel.HIGH

    @pytest.mark.asyncio
    async def test_page_deletion_data_loss_summary(self):
        uc, repo = self._make_uc()
        impact = await uc._analyze_deletion_impact("page", "s-1", "page-id", "Home")
        assert "recycle bin" in impact.data_loss_summary.lower()

    @pytest.mark.asyncio
    async def test_library_deletion_data_loss_mentions_files(self):
        uc, repo = self._make_uc()
        impact = await uc._analyze_deletion_impact("library", "s-1", "lib-id", "Docs")
        assert "files" in impact.data_loss_summary.lower() or "library" in impact.data_loss_summary.lower()
