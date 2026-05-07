"""Tests for library_handler."""

import pytest
from unittest.mock import MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleLibraryOperations:
    @pytest.mark.asyncio
    async def test_unrecognized_returns_guidance(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService.parse_library_operation",
                   return_value=None):
            from src.presentation.api.handlers.library_handler import handle_library_operations
            result = await handle_library_operations(
                message="do something with library",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "chat"

    @pytest.mark.asyncio
    async def test_returns_chat_response(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService.parse_library_operation",
                   return_value=None):
            from src.presentation.api.handlers.library_handler import handle_library_operations
            result = await handle_library_operations(
                message="create library Reports",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
