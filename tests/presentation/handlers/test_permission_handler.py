"""Tests for permission_handler."""

import pytest
from unittest.mock import MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandlePermissionOperations:
    @pytest.mark.asyncio
    async def test_unrecognized_returns_guidance(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.permission_operation_parser.PermissionOperationParserService.parse_permission_operation",
                   return_value=None):
            from src.presentation.api.handlers.permission_handler import handle_permission_operations
            result = await handle_permission_operations(
                message="something about permissions",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "chat"

    @pytest.mark.asyncio
    async def test_returns_chat_response(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.permission_operation_parser.PermissionOperationParserService.parse_permission_operation",
                   return_value=None):
            from src.presentation.api.handlers.permission_handler import handle_permission_operations
            result = await handle_permission_operations(
                message="grant read access to john",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
