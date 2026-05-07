"""Tests for handle_sharepoint_errors decorator."""

import pytest
from src.infrastructure.repositories.utils.error_handlers import handle_sharepoint_errors
from src.domain.exceptions import SharePointProvisioningException


class TestHandleSharePointErrors:
    @pytest.mark.asyncio
    async def test_passes_through_on_success(self):
        @handle_sharepoint_errors("Test op")
        async def good_func():
            return "ok"

        result = await good_func()
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_reraises_sharepoint_exception_as_is(self):
        @handle_sharepoint_errors("Test op")
        async def raises_sp():
            raise SharePointProvisioningException("Original error")

        with pytest.raises(SharePointProvisioningException, match="Original error"):
            await raises_sp()

    @pytest.mark.asyncio
    async def test_wraps_generic_exception_in_sharepoint_exception(self):
        @handle_sharepoint_errors("Test op")
        async def raises_generic():
            raise ValueError("Something broke")

        with pytest.raises(SharePointProvisioningException, match="Something broke"):
            await raises_generic()

    @pytest.mark.asyncio
    async def test_wrapped_exception_includes_operation_name(self):
        @handle_sharepoint_errors("My custom operation")
        async def raises_generic():
            raise RuntimeError("timeout")

        with pytest.raises(SharePointProvisioningException) as exc_info:
            await raises_generic()
        assert "My custom operation" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_preserves_function_name(self):
        @handle_sharepoint_errors("Op")
        async def my_function():
            return "result"

        assert my_function.__name__ == "my_function"

    @pytest.mark.asyncio
    async def test_passes_args_to_function(self):
        @handle_sharepoint_errors("Op")
        async def echo(x, y):
            return x + y

        result = await echo(1, 2)
        assert result == 3
