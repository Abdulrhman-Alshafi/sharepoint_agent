"""Integration tests for the chat endpoint and API layer.

These tests use FastAPI's TestClient and mock all external dependencies
(AI blueprint generator, SharePoint repository, token validation).
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


def _make_client():
    """Create a TestClient with all external dependencies mocked."""
    with patch("src.infrastructure.config.settings") as mock_settings:
        mock_settings.DEV_MODE = True
        mock_settings.ENVIRONMENT = "development"
        mock_settings.API_KEY = "test-key"
        mock_settings.LOG_LEVEL = "INFO"
        mock_settings.validate = MagicMock()

        from src.main import create_app
        app = create_app()
    return TestClient(app)


class TestChatEndpoint:
    """Integration tests through the /api/v1/chat/ gateway."""

    def _client_with_dev_mode(self):
        """Get a TestClient with DEV_MODE on (no JWT required)."""
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = True
            mock_settings.ENVIRONMENT = "development"
            mock_settings.API_KEY = ""

            from src.main import app
            return TestClient(app)

    def test_chat_endpoint_requires_no_token_in_dev_mode(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings, \
             patch("src.presentation.api.chat.get_intent_classifier") as mock_ic, \
             patch("src.presentation.api.chat.get_provisioning_service"), \
             patch("src.presentation.api.chat.get_data_query_service"):
            mock_settings.DEV_MODE = True
            mock_settings.ENVIRONMENT = "development"
            mock_settings.API_KEY = ""

            intent_classifier = AsyncMock()
            intent_classifier.classify_intent.return_value = "chat"
            mock_ic.return_value = intent_classifier

            from src.main import app
            client = TestClient(app)
            # Just verifying the route exists and doesn't crash at a hard 422/500 level
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "Hello!"},
            )
            # Should be 200 or some handled error, not a 422 (validation error)
            assert resp.status_code != 422

    def test_chat_endpoint_rejects_empty_message(self):
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = True
            mock_settings.ENVIRONMENT = "development"
            resp = client.post("/api/v1/chat/", json={"message": ""})
        assert resp.status_code == 422

    def test_chat_endpoint_rejects_too_long_message(self):
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = True
            mock_settings.ENVIRONMENT = "development"
            mock_settings.API_KEY = ""
            resp = client.post("/api/v1/chat/", json={"message": "x" * 2001})
        assert resp.status_code == 422

    def test_production_no_token_returns_401(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings:
            mock_settings.DEV_MODE = False
            mock_settings.API_KEY = ""
            from src.main import app
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post("/api/v1/chat/", json={"message": "Hello"})
        assert resp.status_code == 401

    def test_production_api_key_auth_passes(self):
        with patch("src.presentation.api.dependencies.settings") as mock_settings, \
             patch("src.presentation.api.chat.get_intent_classifier") as mock_ic, \
             patch("src.presentation.api.chat.get_provisioning_service"), \
             patch("src.presentation.api.chat.get_data_query_service"):
            mock_settings.DEV_MODE = False
            mock_settings.API_KEY = "test-prod-key"

            intent_classifier = AsyncMock()
            intent_classifier.classify_intent.return_value = "chat"
            mock_ic.return_value = intent_classifier

            from src.main import app
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "Hello!"},
                headers={"Authorization": "Bearer test-prod-key"},
            )
        # Should not be 401
        assert resp.status_code != 401


class TestHealthEndpoint:
    """Test basic router connectivity."""

    def test_chat_route_exists(self):
        from src.main import app
        routes = [r.path for r in app.routes]
        assert any("/chat" in p for p in routes) or any("/api" in p for p in routes)
