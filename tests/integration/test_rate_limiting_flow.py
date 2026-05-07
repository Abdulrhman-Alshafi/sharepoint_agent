"""Integration tests for rate limiting flow.

Tests that:
- Rate limits are enforced on endpoints
- Exceeding the limit returns 429
- Rate limiter is properly wired into the app
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


class TestRateLimitingFlow:
    def _make_client(self):
        from src.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_rate_limiter_wired_into_app(self):
        """The app should have a limiter attached to its state."""
        from src.main import create_app
        app = create_app()
        assert hasattr(app.state, "limiter")

    def test_single_request_not_rate_limited(self):
        """A single request should not be rate limited."""
        client = self._make_client()

        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.ENVIRONMENT = "development"
            ms.API_KEY = ""
            resp = client.post(
                "/api/v1/chat/",
                json={"message": "Hello", "session_id": "s1"},
            )
        assert resp.status_code != 429

    def test_rate_limit_exceeded_returns_429(self):
        """Rate limit exception handler should return 429."""
        from src.main import create_app
        from src.infrastructure.rate_limiter import limiter
        from fastapi import Request as FARequest
        from starlette.testclient import TestClient as StarletteClient

        app = create_app()

        @app.get("/_test_rl_count")
        @limiter.limit("1/minute")
        async def _limited(request: FARequest):
            return {"ok": True}

        client = StarletteClient(app, raise_server_exceptions=False)
        # First request should be allowed
        resp1 = client.get("/_test_rl_count", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp1.status_code == 200
        # Second request from same IP should be rate limited
        resp2 = client.get("/_test_rl_count", headers={"X-Forwarded-For": "10.0.0.1"})
        assert resp2.status_code == 429

    def test_rate_limiter_key_func_uses_user_when_available(self):
        """get_user_identifier should prefer user email over IP."""
        from src.infrastructure.rate_limiter import get_user_identifier

        mock_request = MagicMock()
        mock_request.state.current_user = "user@example.com"
        result = get_user_identifier(mock_request)
        assert "user@example.com" in result

    def test_rate_limiter_key_func_falls_back_to_ip(self):
        """get_user_identifier should fall back to IP when no user in state."""
        from src.infrastructure.rate_limiter import get_user_identifier
        from fastapi import Request as FastAPIRequest
        from starlette.datastructures import State

        mock_request = MagicMock()
        mock_state = State()
        mock_request.state = mock_state
        mock_request.client = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers = {}
        result = get_user_identifier(mock_request)
        assert result is not None
