"""Tests for exception handlers registered in main.py."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


def _make_client():
    """Import app with patched settings so no real infra needed."""
    with patch("src.infrastructure.config.Settings") as mock_settings_cls:
        env = MagicMock()
        env.ENVIRONMENT = "test"
        env.AZURE_TENANT_ID = "tid"
        env.AZURE_CLIENT_ID = "cid"
        env.AZURE_CLIENT_SECRET = "sec"
        env.SHAREPOINT_SITE_ID = "sid"
        env.OPENAI_API_KEY = "key"
        env.DEV_MODE = True
        mock_settings_cls.return_value = env

        from src.main import create_app
        app = create_app()
        return TestClient(app, raise_server_exceptions=False)


class TestExceptionHandlers:
    def test_domain_exception_returns_json_error(self):
        """A DomainException raised from a route should return JSON with error field."""
        from src.main import create_app
        from fastapi import Request
        from fastapi.responses import JSONResponse
        from src.domain.exceptions import DomainException

        app = create_app()

        @app.get("/_test_domain_exc")
        async def _raise():
            raise DomainException(message="domain error", http_status=400)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/_test_domain_exc")
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data or "message" in data or "detail" in data

    def test_value_error_handler_returns_400(self):
        """A ValueError raised from a route should return 400."""
        from src.main import create_app

        app = create_app()

        @app.get("/_test_value_error")
        async def _raise():
            raise ValueError("bad value")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/_test_value_error")
        assert resp.status_code == 400

    def test_unhandled_exception_returns_500(self):
        """An unexpected exception should return 500."""
        from src.main import create_app

        app = create_app()

        @app.get("/_test_general_exc")
        async def _raise():
            raise RuntimeError("oops")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/_test_general_exc")
        assert resp.status_code == 500
