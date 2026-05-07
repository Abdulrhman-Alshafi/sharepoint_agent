"""Tests for AuthenticationService."""

import pytest
from unittest.mock import MagicMock, patch, Mock

from src.infrastructure.services.authentication_service import AuthenticationService
from src.domain.exceptions import SharePointProvisioningException


def _make_service_and_app():
    """Create an AuthenticationService with mocked app attribute directly."""
    with patch("src.infrastructure.services.authentication_service.settings") as mock_settings, \
         patch("src.infrastructure.services.authentication_service.msal") as mock_msal:
        mock_settings.TENANT_ID = "tenant-id"
        mock_settings.CLIENT_ID = "client-id"
        mock_settings.CLIENT_SECRET = "client-secret"

        mock_inner_app = MagicMock()
        mock_msal.ConfidentialClientApplication.return_value = mock_inner_app

        svc = AuthenticationService()
    # After context exit, svc.app is still the mock object (captured by reference)
    return svc, mock_inner_app


class TestAuthenticationServiceGraphToken:
    @pytest.mark.asyncio
    async def test_get_graph_access_token_returns_token(self):
        svc, mock_app = _make_service_and_app()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {"access_token": "graph-token-123"}
        token = await svc.get_graph_access_token()
        assert token == "graph-token-123"

    @pytest.mark.asyncio
    async def test_get_graph_access_token_raises_on_failure(self):
        svc, mock_app = _make_service_and_app()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {
            "error": "invalid_client",
            "error_description": "Invalid credentials",
        }
        with pytest.raises(SharePointProvisioningException):
            await svc.get_graph_access_token()

    @pytest.mark.asyncio
    async def test_get_graph_headers_contains_authorization(self):
        svc, mock_app = _make_service_and_app()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {"access_token": "tok"}
        headers = await svc.get_graph_headers()
        assert "Authorization" in headers
        assert "tok" in headers["Authorization"]


class TestAuthenticationServiceRestToken:
    @pytest.mark.asyncio
    async def test_get_rest_access_token_returns_token(self):
        svc, mock_app = _make_service_and_app()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {"access_token": "rest-tok"}
        token = await svc.get_rest_access_token("https://contoso.sharepoint.com/sites/Proj")
        assert token == "rest-tok"

    @pytest.mark.asyncio
    async def test_get_rest_access_token_raises_on_failure(self):
        svc, mock_app = _make_service_and_app()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {
            "error": "access_denied",
            "error_description": "Access denied",
        }
        with pytest.raises(SharePointProvisioningException):
            await svc.get_rest_access_token("https://contoso.sharepoint.com/sites/Proj")

    @pytest.mark.asyncio
    async def test_get_rest_headers_contains_authorization(self):
        svc, mock_app = _make_service_and_app()
        mock_app.acquire_token_silent.return_value = None
        mock_app.acquire_token_for_client.return_value = {"access_token": "rest-tok"}
        headers = await svc.get_rest_headers("https://contoso.sharepoint.com/sites/Proj")
        assert "Authorization" in headers
