"""Tests for file_handler."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.presentation.api.schemas.chat_schemas import ChatResponse


class TestHandleFileOperations:
    @pytest.mark.asyncio
    async def test_unrecognized_operation_returns_guidance(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.file_operation_parser.FileOperationParserService.parse_file_operation",
                   return_value=None), \
             patch("src.infrastructure.services.document_parser.DocumentParserService"), \
             patch("src.infrastructure.services.document_index.DocumentIndexService"), \
             patch("src.infrastructure.external_services.document_intelligence.DocumentIntelligenceService"):
            from src.presentation.api.handlers.file_handler import handle_file_operations
            result = await handle_file_operations(
                message="do something with files",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
        assert result.intent == "chat"

    @pytest.mark.asyncio
    async def test_returns_chat_response(self):
        mock_repo = MagicMock()

        with patch("src.presentation.api.get_repository", return_value=mock_repo), \
             patch("src.infrastructure.external_services.file_operation_parser.FileOperationParserService.parse_file_operation",
                   return_value=None), \
             patch("src.infrastructure.services.document_parser.DocumentParserService"), \
             patch("src.infrastructure.services.document_index.DocumentIndexService"), \
             patch("src.infrastructure.external_services.document_intelligence.DocumentIntelligenceService"):
            from src.presentation.api.handlers.file_handler import handle_file_operations
            result = await handle_file_operations(
                message="download report.pdf",
                session_id="s1",
                site_id="https://contoso.sharepoint.com/sites/test",
            )
        assert isinstance(result, ChatResponse)
