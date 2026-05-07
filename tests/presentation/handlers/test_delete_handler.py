"""Tests for delete_handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleDeleteOperations:
    @pytest.mark.asyncio
    async def test_no_resource_found_returns_guidance(self):
        mock_repo = AsyncMock()
        mock_repo.get_all_lists.return_value = []

        with patch("src.presentation.api.get_repository", return_value=mock_repo):
            from src.presentation.api.handlers.delete_handler import handle_delete_operations
            result = await handle_delete_operations(
                message="delete something",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "delete"
        assert "delete" in result.reply.lower() or "which" in result.reply.lower() or "resource" in result.reply.lower()

    @pytest.mark.asyncio
    async def test_list_found_requires_confirmation(self):
        mock_repo = AsyncMock()
        mock_repo.get_all_lists.return_value = [
            {"id": "list-1", "displayName": "Tasks"}
        ]

        mock_delete_uc = AsyncMock()
        mock_delete_uc.execute.return_value = {
            "requires_confirmation": True,
            "impact": MagicMock(
                target_resource_type="list",
                target_resource_name="Tasks",
                item_count=5,
                dependent_resources=[],
                data_loss_summary="5 items will be lost",
                reversibility="reversible via recycle bin",
                risk_level=MagicMock(value="medium"),
                get_impact_message=MagicMock(return_value="Are you sure?"),
            ),
            "confirmation_text": "yes, delete tasks",
        }

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.application.use_cases.delete_resource_use_case.DeleteResourceUseCase",
                   return_value=mock_delete_uc):
            from src.presentation.api.handlers.delete_handler import handle_delete_operations
            result = await handle_delete_operations(
                message="delete the Tasks list",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)

    @pytest.mark.asyncio
    async def test_returns_chat_response_type(self):
        mock_repo = AsyncMock()
        mock_repo.get_all_lists.return_value = []

        with patch("src.presentation.api.get_repository", return_value=mock_repo):
            from src.presentation.api.handlers.delete_handler import handle_delete_operations
            result = await handle_delete_operations(
                message="delete list",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)
