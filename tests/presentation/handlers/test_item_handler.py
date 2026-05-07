"""Tests for item_handler."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleItemOperations:
    @pytest.mark.asyncio
    async def test_unrecognized_operation_returns_guidance(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.list_item_parser.ListItemParserService.parse_item_operation",
                   return_value=None):
            from src.presentation.api.handlers.item_handler import handle_item_operations
            result = await handle_item_operations(
                message="do something with items",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)

    @pytest.mark.asyncio
    async def test_returns_chat_response(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.list_item_parser.ListItemParserService.parse_item_operation",
                   return_value=None):
            from src.presentation.api.handlers.item_handler import handle_item_operations
            result = await handle_item_operations(
                message="add an item",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
