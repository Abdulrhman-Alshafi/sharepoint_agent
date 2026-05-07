from unittest.mock import AsyncMock

import pytest

from src.application.use_cases.delete_resource_use_case import DeleteResourceUseCase


@pytest.mark.asyncio
async def test_library_delete_uses_site_id_when_calling_repository():
    repo = AsyncMock()
    repo.check_user_permission = AsyncMock(return_value=True)
    repo.delete_document_library = AsyncMock(return_value=True)

    use_case = DeleteResourceUseCase(repo)

    result = await use_case.execute(
        resource_type="library",
        site_id="site-123",
        resource_id="lib-456",
        resource_name="Docs",
        confirmed=True,
        user_login_name="user@contoso.com",
    )

    assert result["success"] is True
    repo.delete_document_library.assert_awaited_once_with("lib-456", site_id="site-123")
