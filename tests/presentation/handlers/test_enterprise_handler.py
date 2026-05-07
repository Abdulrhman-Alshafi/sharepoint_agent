"""Tests for enterprise_handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleEnterpriseOperations:
    @pytest.mark.asyncio
    async def test_unrecognized_message_returns_guidance(self):
        mock_repo = MagicMock()
        mock_repo.graph_client = MagicMock()
        mock_repo.rest_client = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.enterprise_operation_parser.EnterpriseOperationParserService.parse_enterprise_operation",
                   return_value=None):
            from src.presentation.api.handlers.enterprise_handler import handle_enterprise_operations
            result = await handle_enterprise_operations(
                message="do something enterprise",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)

    @pytest.mark.asyncio
    async def test_returns_chat_response(self):
        mock_repo = MagicMock()
        mock_repo.graph_client = MagicMock()
        mock_repo.rest_client = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.enterprise_operation_parser.EnterpriseOperationParserService.parse_enterprise_operation",
                   return_value=None):
            from src.presentation.api.handlers.enterprise_handler import handle_enterprise_operations
            result = await handle_enterprise_operations(
                message="content types",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "chat"
