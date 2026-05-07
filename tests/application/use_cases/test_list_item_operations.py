"""Tests for ListItemOperationsUseCase."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.application.use_cases.list_item_operations_use_case import ListItemOperationsUseCase
from src.domain.exceptions import SharePointProvisioningException


class TestCreateItem:
    def _make_uc(self):
        repo = AsyncMock()
        return ListItemOperationsUseCase(repo), repo

    @pytest.mark.asyncio
    async def test_create_item_returns_repo_result(self):
        uc, repo = self._make_uc()
        expected = {"id": "item-1", "Title": "First"}
        repo.create_list_item.return_value = expected
        result = await uc.create_item("list-1", {"Title": "First"})
        assert result == expected

    @pytest.mark.asyncio
    async def test_create_item_calls_repo_with_correct_args(self):
        uc, repo = self._make_uc()
        repo.create_list_item.return_value = {"id": "1"}
        await uc.create_item("list-1", {"Title": "T"}, site_id="site-1")
        repo.create_list_item.assert_awaited_once_with("list-1", {"Title": "T"}, "site-1")

    @pytest.mark.asyncio
    async def test_create_item_repo_failure_raises_provisioning_exception(self):
        uc, repo = self._make_uc()
        repo.create_list_item.side_effect = Exception("network error")
        with pytest.raises(SharePointProvisioningException, match="Failed to create"):
            await uc.create_item("list-1", {"Title": "T"})


class TestUpdateItem:
    def _make_uc(self):
        repo = AsyncMock()
        return ListItemOperationsUseCase(repo), repo

    @pytest.mark.asyncio
    async def test_update_item_calls_repo(self):
        uc, repo = self._make_uc()
        repo.update_list_item.return_value = {"id": "item-1"}
        await uc.update_item("list-1", "item-1", {"Status": "Done"})
        repo.update_list_item.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_item_failure_raises(self):
        uc, repo = self._make_uc()
        repo.update_list_item.side_effect = Exception("server error")
        with pytest.raises(SharePointProvisioningException, match="Failed to update"):
            await uc.update_item("list-1", "item-1", {})


class TestDeleteItem:
    def _make_uc(self):
        repo = AsyncMock()
        return ListItemOperationsUseCase(repo), repo

    @pytest.mark.asyncio
    async def test_delete_item_returns_true_on_success(self):
        uc, repo = self._make_uc()
        repo.delete_list_item.return_value = True
        result = await uc.delete_item("list-1", "item-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_item_failure_raises(self):
        uc, repo = self._make_uc()
        repo.delete_list_item.side_effect = Exception("failed")
        with pytest.raises(SharePointProvisioningException):
            await uc.delete_item("list-1", "item-1")
