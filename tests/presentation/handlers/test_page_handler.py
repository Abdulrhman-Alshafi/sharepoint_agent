"""Tests for page_handler."""

import pytest
from unittest.mock import MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandlePageOperations:
    @pytest.mark.asyncio
    async def test_unrecognized_returns_guidance(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.page_operation_parser.PageOperationParserService.parse_page_operation",
                   return_value=None):
            from src.presentation.api.handlers.page_handler import handle_page_operations
            result = await handle_page_operations(
                message="something about pages",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "chat"

    @pytest.mark.asyncio
    async def test_returns_chat_response(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.page_operation_parser.PageOperationParserService.parse_page_operation",
                   return_value=None):
            from src.presentation.api.handlers.page_handler import handle_page_operations
            result = await handle_page_operations(
                message="create home page",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
