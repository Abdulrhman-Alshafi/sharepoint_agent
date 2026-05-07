import pytest
from unittest.mock import MagicMock, patch
import httpx

from src.infrastructure.services.base_api_client import BaseAPIClient
from src.infrastructure.services.authentication_service import AuthenticationService


class TestBaseAPIClientInit:
    def test_stores_auth_service(self):
        auth = MagicMock()
        with patch.object(BaseAPIClient, "_build_client", return_value=MagicMock()):
            client = BaseAPIClient(auth, "s1")
            assert client.auth_service == auth

    def test_stores_site_id(self):
        with patch.object(BaseAPIClient, "_build_client", return_value=MagicMock()):
            client = BaseAPIClient(MagicMock(), "s1")
            assert client.site_id == "s1"

class TestBuildClient:
    def test_returns_async_client(self):
        auth = MagicMock()
        client = BaseAPIClient.__new__(BaseAPIClient)
        client.auth_service = auth
        client.site_id = "s1"
        session = client._build_client()
        assert isinstance(session, httpx.AsyncClient)
        assert session.timeout.connect == 60.0

