"""Tests for site_handler."""

import pytest
from unittest.mock import MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleSiteOperations:
    @pytest.mark.asyncio
    async def test_unrecognized_returns_guidance(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.site_operation_parser.SiteOperationParserService.parse_site_operation",
                   return_value=None):
            from src.presentation.api.handlers.site_handler import handle_site_operations
            result = await handle_site_operations(
                message="something about sites",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "chat"

    @pytest.mark.asyncio
    async def test_returns_chat_response_for_create(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.site_operation_parser.SiteOperationParserService.parse_site_operation",
                   return_value=None):
            from src.presentation.api.handlers.site_handler import handle_site_operations
            result = await handle_site_operations(
                message="create a new team site called Marketing",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
