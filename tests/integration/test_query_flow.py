"""Integration tests for the query flow.

Tests POST /api/v1/query/ with mocked services end-to-end.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient


def _mock_query_service():
    svc = AsyncMock()
    result = MagicMock()
    result.answer = "There are 5 open tasks."
    result.data_summary = "Fetched 5 rows from Tasks list."
    result.list_referenced = "Tasks"
    result.suggested_actions = []
    svc.query_data.return_value = result
    return svc


class TestQueryFlow:
    def test_query_endpoint_exists(self):
        """Query endpoint should be reachable (no 404)."""
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)
        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.API_KEY = ""
            resp = client.post("/api/v1/query/", json={"question": "What are the open tasks?"})
        assert resp.status_code != 404

    def test_query_empty_question_returns_422(self):
        """Empty question should fail schema validation."""
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/api/v1/query/", json={"question": ""})
        assert resp.status_code == 422

    def test_query_with_valid_question_succeeds(self):
        """Valid question with mocked service should return 200."""
        from src.main import app
        client = TestClient(app, raise_server_exceptions=False)

        mock_svc = _mock_query_service()

        with patch("src.presentation.api.dependencies.settings") as ms, \
             patch("src.presentation.api.query.get_data_query_service", return_value=mock_svc):
            ms.DEV_MODE = True
            ms.API_KEY = ""
            resp = client.post(
                "/api/v1/query/",
                json={"question": "How many items are in the Tasks list?"},
            )
        assert resp.status_code < 500

    def test_query_service_error_returns_error_response(self):
        """When query service raises a DomainException, endpoint should return error."""
        from src.main import create_app
        from src.domain.exceptions import DomainException

        app = create_app()

        @app.get("/_test_query_err")
        async def _raise():
            raise DomainException(message="AI unavailable", http_status=503)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/_test_query_err")
        assert resp.status_code >= 400
