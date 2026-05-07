import pytest
from unittest.mock import AsyncMock, Mock, patch


@pytest.mark.asyncio
async def test_library_create_without_name_starts_gathering_flow():
    mock_repo = AsyncMock()
    first_question = Mock(
        question_text="What should this document library be called?",
        field_type="text",
        options=["Project Files", "Policies", "Team Docs"],
    )
    mock_gathering = Mock()
    mock_gathering.start_gathering = Mock(return_value=(Mock(), first_question))

    with patch("src.presentation.api.get_repository", return_value=mock_repo), \
         patch("src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService.parse_library_operation", new=AsyncMock(return_value=Mock(operation="create", library_name=None))), \
         patch("src.presentation.api.orchestrators.library_orchestrator.ServiceContainer.get_gathering_service", return_value=mock_gathering):
        from src.presentation.api.orchestrators.library_orchestrator import handle_library_operations

        result = await handle_library_operations(
            message="create a library",
            session_id="session-1",
            site_id="site-1",
        )

    assert result.intent == "provision"
    assert result.requires_input is True
    assert result.question_prompt == "What should this document library be called?"


@pytest.mark.asyncio
async def test_delete_this_resolves_last_created_library_via_document_library_api():
    mock_repo = AsyncMock()
    mock_repo.get_all_document_libraries = AsyncMock(return_value=[
        {"id": "lib-123", "displayName": "theColors"}
    ])
    mock_repo.get_all_lists = AsyncMock(return_value=[])

    mock_delete_use_case = AsyncMock()
    mock_delete_use_case.execute = AsyncMock(return_value={
        "success": True,
        "message": "✅ Library deleted.",
    })

    with patch("src.presentation.api.get_repository", return_value=mock_repo), \
         patch("src.application.use_cases.delete_resource_use_case.DeleteResourceUseCase", return_value=mock_delete_use_case):
        from src.presentation.api.orchestrators.delete_orchestrator import handle_delete_operations

        result = await handle_delete_operations(
            message="delete this",
            session_id="session-1",
            site_id="site-1",
            provisioning_service=AsyncMock(),
            last_created=("theColors", "library", "site-1"),
        )

    assert result.intent == "delete"
    assert "deleted" in result.reply.lower()
    assert mock_repo.get_all_document_libraries.await_count >= 1

    delete_call = mock_delete_use_case.execute.await_args.kwargs
    assert delete_call["resource_type"] == "library"
    assert delete_call["resource_id"] == "lib-123"
    assert delete_call["resource_name"] == "theColors"


@pytest.mark.asyncio
async def test_library_create_with_folder_paths_creates_nested_folders():
    mock_repo = AsyncMock()
    mock_repo.create_document_library = AsyncMock(return_value={
        "id": "lib-123",
        "resource_link": "https://contoso.sharepoint.com/sites/x/Shared%20Documents",
    })
    mock_repo.create_folder = AsyncMock(return_value={"id": "folder-1"})

    with patch("src.presentation.api.get_repository", return_value=mock_repo), \
         patch(
             "src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService.parse_library_operation",
             new=AsyncMock(return_value=Mock(
                 operation="create",
                 library_name="Team Docs",
                 description="",
                 enable_versioning=False,
                 folder_paths=["General", "Projects/2026/Q1"],
             )),
         ):
        from src.presentation.api.orchestrators.library_orchestrator import handle_library_operations

        result = await handle_library_operations(
            message="create a library named Team Docs with folders: General, Projects/2026/Q1",
            session_id="session-1",
            site_id="site-1",
        )

    assert result.intent == "chat"
    assert "created successfully" in result.reply.lower()
    assert "created folders" in result.reply.lower()
    assert mock_repo.create_folder.await_count >= 3
