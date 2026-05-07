"""Tests for UpdateResourceUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.use_cases.update_resource_use_case import UpdateResourceUseCase


class TestUpdateResourceUseCase:
    def _make_uc(self):
        repo = AsyncMock()
        uc = UpdateResourceUseCase(repo)
        return uc, repo

    @pytest.mark.asyncio
    async def test_preview_only_returns_preview_and_confirmation_flag(self):
        uc, repo = self._make_uc()
        mock_preview = MagicMock()
        with patch.object(uc, "_generate_update_preview", new=AsyncMock(return_value=mock_preview)):
            result = await uc.execute("list", "site-1", "list-1", {"description": "new"}, preview_only=True)
        assert result["requires_confirmation"] is True
        assert result["preview"] is mock_preview

    @pytest.mark.asyncio
    async def test_preview_only_does_not_call_execute_update(self):
        uc, repo = self._make_uc()
        with patch.object(uc, "_generate_update_preview", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_execute_update", new=AsyncMock()) as mock_exec:
            await uc.execute("list", "s", "l", {}, preview_only=True)
        mock_exec.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirmed_update_calls_execute_update(self):
        uc, repo = self._make_uc()
        mock_result = {"id": "list-1"}
        with patch.object(uc, "_generate_update_preview", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_execute_update", new=AsyncMock(return_value=mock_result)) as mock_exec:
            result = await uc.execute("list", "s", "l", {}, preview_only=False)
        mock_exec.assert_awaited_once()
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_execute_update_failure_returns_false_success(self):
        uc, repo = self._make_uc()
        with patch.object(uc, "_generate_update_preview", new=AsyncMock(return_value=MagicMock())), \
             patch.object(uc, "_execute_update", new=AsyncMock(return_value=None)):
            result = await uc.execute("list", "s", "l", {}, preview_only=False)
        assert result["success"] is False
