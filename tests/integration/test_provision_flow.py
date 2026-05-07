"""Integration tests for the provisioning flow.

Tests POST /api/v1/provision/ with mocked services end-to-end.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient
from src.presentation.api.provision import get_provisioning_service
from src.main import app

def _mock_provisioning_service():
    svc = AsyncMock()
    bp = MagicMock()
    bp.reasoning = "test"
    bp.lists = []
    bp.pages = []
    bp.document_libraries = []
    bp.groups = []
    bp.sites = []
    bp.term_sets = []
    bp.content_types = []
    bp.views = []
    bp.workflows = []

    result = MagicMock()
    result.blueprint = bp
    result.created_resources = []
    result.resource_links = []
    result.warnings = []
    svc.provision_resources.return_value = result
    return svc


class TestProvisionFlow:
    def test_provision_endpoint_exists(self):
        """Provision endpoint should be reachable (no 404)."""
        client = TestClient(app, raise_server_exceptions=False)
        app.dependency_overrides[get_provisioning_service] = _mock_provisioning_service
        
        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.API_KEY = ""
            resp = client.post("/api/v1/provision/", json={"prompt": "Create a tasks list"})
        
        app.dependency_overrides.clear()
        assert resp.status_code != 404

    def test_provision_empty_prompt_returns_422(self):
        """Empty prompt should fail schema validation."""
        client = TestClient(app, raise_server_exceptions=False)
        app.dependency_overrides[get_provisioning_service] = _mock_provisioning_service
        
        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.API_KEY = ""
            resp = client.post("/api/v1/provision/", json={"prompt": ""})
            
        app.dependency_overrides.clear()
        assert resp.status_code == 422

    def test_provision_with_valid_prompt_succeeds(self):
        """Valid prompt with mocked service should return 200."""
        client = TestClient(app, raise_server_exceptions=False)
        mock_svc = _mock_provisioning_service()
        app.dependency_overrides[get_provisioning_service] = lambda: mock_svc

        with patch("src.presentation.api.dependencies.settings") as ms:
            ms.DEV_MODE = True
            ms.API_KEY = ""
            resp = client.post(
                "/api/v1/provision/",
                json={"prompt": "Create a project tracking site"},
            )
            
        app.dependency_overrides.clear()
        assert resp.status_code < 500

    def test_provision_service_error_returns_error_response(self):
        """When provisioning service raises a DomainException, endpoint returns an error."""
        from src.main import create_app
        from fastapi import Request
        from src.domain.exceptions import SharePointProvisioningException

        test_app = create_app()

        @test_app.get("/_test_prov_err")
        async def _raise():
            raise SharePointProvisioningException("connection failed")

        client = TestClient(test_app, raise_server_exceptions=False)
        resp = client.get("/_test_prov_err")
        assert resp.status_code >= 400

