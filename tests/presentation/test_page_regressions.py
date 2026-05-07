import pytest
from unittest.mock import AsyncMock, Mock, patch


@pytest.mark.asyncio
async def test_page_create_without_title_starts_gathering_flow():
    mock_repo = AsyncMock()
    first_question = Mock(
        question_text="What should this page be called?",
        field_type="text",
        options=["Home", "Announcements", "Project Updates"],
    )
    mock_gathering = Mock()
    mock_gathering.start_gathering = Mock(return_value=(Mock(), first_question))

    with patch("src.presentation.api.get_repository", return_value=mock_repo), \
         patch("src.infrastructure.external_services.page_operation_parser.PageOperationParserService.parse_page_operation", new=AsyncMock(return_value=Mock(operation="create", page_title=None))), \
         patch("src.presentation.api.orchestrators.page_orchestrator.ServiceContainer.get_gathering_service", return_value=mock_gathering):
        from src.presentation.api.orchestrators.page_orchestrator import handle_page_operations

        result = await handle_page_operations(
            message="create a page",
            session_id="session-1",
            site_id="site-1",
        )

    assert result.intent == "provision"
    assert result.requires_input is True
    assert result.question_prompt == "What should this page be called?"


@pytest.mark.asyncio
async def test_page_delete_this_uses_last_created_page():
    mock_repo = AsyncMock()
    mock_repo.search_pages = AsyncMock(return_value=[
        {"id": "page-123", "title": "Home"}
    ])
    mock_repo.delete_page = AsyncMock(return_value=True)

    with patch("src.presentation.api.get_repository", return_value=mock_repo), \
         patch("src.infrastructure.external_services.page_operation_parser.PageOperationParserService.parse_page_operation", new=AsyncMock(return_value=Mock(operation="delete", page_title=None, page_name="this"))):
        from src.presentation.api.orchestrators.page_orchestrator import handle_page_operations

        result = await handle_page_operations(
            message="delete this",
            session_id="session-1",
            site_id="site-1",
            last_created=("Home", "page", "site-1"),
        )

    assert result.intent == "chat"
    assert "deleted successfully" in result.reply.lower()
    mock_repo.search_pages.assert_awaited_with("Home", site_id="site-1")
    mock_repo.delete_page.assert_awaited_once_with("page-123", site_id="site-1")
