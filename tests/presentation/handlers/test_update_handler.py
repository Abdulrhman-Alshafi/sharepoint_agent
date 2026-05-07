"""Tests for update_handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleUpdateOperations:
    @pytest.mark.asyncio
    async def test_no_resource_found_returns_guidance(self):
        mock_repo = AsyncMock()
        mock_repo.get_all_lists.return_value = []

        with patch("src.presentation.api.get_repository", return_value=mock_repo):
            from src.presentation.api.handlers.update_handler import handle_update_operations
            result = await handle_update_operations(
                message="update something",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "update"
        assert "update" in result.reply.lower() or "which" in result.reply.lower() or "resource" in result.reply.lower()

    @pytest.mark.asyncio
    async def test_returns_chat_response_type(self):
        mock_repo = AsyncMock()
        mock_repo.get_all_lists.return_value = []

        with patch("src.presentation.api.get_repository", return_value=mock_repo):
            from src.presentation.api.handlers.update_handler import handle_update_operations
            result = await handle_update_operations(
                message="update the Announcements list",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)

    @pytest.mark.asyncio
    async def test_list_found_no_modifications_returns_guidance(self):
        mock_repo = AsyncMock()
        mock_repo.get_all_lists.return_value = [
            {"id": "list-1", "displayName": "Tasks"}
        ]

        with patch("src.presentation.api.get_repository", return_value=mock_repo):
            from src.presentation.api.handlers.update_handler import handle_update_operations
            result = await handle_update_operations(
                message="update the tasks list",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
                provisioning_service=AsyncMock(),
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "update"
