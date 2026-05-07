"""Integration tests for authentication flow.

Tests that:
- No token in production mode returns 401
- DEV_MODE skips authentication and allows requests
- Valid API key returns 200 in DEV_MODE
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestAuthFlow:
    def test_no_token_in_production_returns_401(self):
        """Without a token in production mode, requests should be rejected."""
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = False
            ms.ENVIRONMENT = "production"
            ms.API_KEY = ""
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "Hello", "session_id": "s1"},
            )
        assert resp.status_code == 401

    def test_dev_mode_no_token_allowed(self):
        """In DEV_MODE, requests without a token should be processed."""
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.ENVIRONMENT = "development"
            ms.API_KEY = ""
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "Hello", "session_id": "s1"},
            )
        # Should not be 401 in DEV_MODE
        assert resp.status_code != 401

    def test_dev_mode_api_key_accepted(self):
        """In DEV_MODE, a matching API key should be accepted."""
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.ENVIRONMENT = "development"
            ms.API_KEY = "test-key-123"
            resp = client.post(
                "/api/v1/chat/",
                headers={"Authorization": "Bearer test-key-123"},
                json={"message": "Hello", "session_id": "s1"},
            )
        assert resp.status_code != 401

    def test_missing_message_returns_422_not_401(self):
        """Schema validation errors should return 422, not 401."""
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)

        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.ENVIRONMENT = "development"
            ms.API_KEY = ""
            resp = client.post("/api/v1/chat/", json={})
        assert resp.status_code == 422
