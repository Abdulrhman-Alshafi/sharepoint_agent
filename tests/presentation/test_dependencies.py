"""Tests for FastAPI get_current_user dependency."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException

from src.domain.exceptions import AuthenticationException


# ── DEV MODE tests ────────────────────────────────────────────────────────────

class TestGetCurrentUserDevMode:
    @pytest.mark.asyncio
    async def test_dev_mode_no_token_returns_default_user(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = True
            mock_settings.ENVIRONMENT = "development"
            mock_settings.API_KEY = ""
            from src.presentation.api.dependencies import get_current_user
            result = await get_current_user(request=MagicMock(), token=None)
        assert result == "dev-user@localhost.local"

    @pytest.mark.asyncio
    async def test_dev_mode_production_env_raises_500(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = True
            mock_settings.ENVIRONMENT = "production"
            from src.presentation.api.dependencies import get_current_user
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request=MagicMock(), token=None)
            assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_dev_mode_api_key_matches(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = True
            mock_settings.ENVIRONMENT = "development"
            mock_settings.API_KEY = "my-secret-key"
            from src.presentation.api.dependencies import get_current_user
            result = await get_current_user(request=MagicMock(), token="my-secret-key")
        assert result == "api-key-user@localhost.local"


# ── PRODUCTION MODE tests ─────────────────────────────────────────────────────

class TestGetCurrentUserProductionMode:
    @pytest.mark.asyncio
    async def test_production_no_token_raises_401(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = False
            mock_settings.API_KEY = ""
            from src.presentation.api.dependencies import get_current_user
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request=MagicMock(), token=None)
            assert exc.value.status_code == 401

    @pytest.mark.asyncio
    async def test_production_api_key_matches(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = False
            mock_settings.API_KEY = "prod-api-key"
            from src.presentation.api.dependencies import get_current_user
            result = await get_current_user(request=MagicMock(), token="prod-api-key")
        assert result == "api-key-user@localhost.local"

    @pytest.mark.asyncio
    async def test_production_valid_jwt_returns_identity(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings, \
             patch("src.presentation.api.dependencies._token_validator") as mock_validator:
            mock_settings.DEV_MODE = False
            mock_settings.API_KEY = ""
            from unittest.mock import AsyncMock
            mock_validator.validate_token = AsyncMock(return_value={"upn": "alice@contoso.com"})
            mock_validator.extract_user_identity.return_value = "alice@contoso.com"
            from src.presentation.api.dependencies import get_current_user
            result = await get_current_user(request=MagicMock(), token="valid.jwt.token")
        assert result == "alice@contoso.com"

    @pytest.mark.asyncio
    async def test_production_invalid_jwt_raises_401(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings, \
             patch("src.presentation.api.dependencies._token_validator") as mock_validator:
            mock_settings.DEV_MODE = False
            mock_settings.API_KEY = ""
            mock_validator.validate_token.side_effect = AuthenticationException("bad token")
            from src.presentation.api.dependencies import get_current_user
            with pytest.raises(HTTPException) as exc:
                await get_current_user(request=MagicMock(), token="bad.jwt")
            assert exc.value.status_code == 401
