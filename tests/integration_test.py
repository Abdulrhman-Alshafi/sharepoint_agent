"""Integration tests for the complete provisioning flow."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from src.main import app
from src.presentation.api import ServiceContainer
from tests.conftest import MockBlueprintGenerator, MockSharePointRepository


@pytest.fixture
def setup_mocks():
    """Setup mocks and inject into service container."""
    blueprint_gen = MockBlueprintGenerator()
    sharepoint_repo = MockSharePointRepository()
    
    # Override services in container
    ServiceContainer._blueprint_generator = blueprint_gen
    ServiceContainer._sharepoint_repository = sharepoint_repo
    ServiceContainer._provisioning_service = None
    
    from tests.conftest import MockIntentClassificationService
    ServiceContainer._intent_classification_service = MockIntentClassificationService()
    
    yield blueprint_gen, sharepoint_repo
    
    ServiceContainer.reset()


def test_provision_endpoint_success(setup_mocks):
    """Test the provision endpoint with successful provisioning."""
    blueprint_gen, sharepoint_repo = setup_mocks
    client = TestClient(app)
    
    response = client.post(
        "/api/v1/provision/",
        json={"prompt": "Create a task list"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "blueprint" in data
    assert "created_lists" in data
    assert "created_pages" in data
    assert "resource_links" in data
    
    # Verify blueprint
    blueprint = data["blueprint"]
    assert "reasoning" in blueprint
    assert "lists" in blueprint
    assert "pages" in blueprint
    
    # Verify lists were created
    assert len(data["created_lists"]) > 0
    assert data["created_lists"][0]["id"] == "list-123"
    assert "http://mock-link" in data["resource_links"]


def test_query_endpoint_success(setup_mocks):
    """Test the data query endpoint."""
    blueprint_gen, sharepoint_repo = setup_mocks
    client = TestClient(app)
    
    # Create a mock data query service
    class MockDataQueryService:
        async def answer_question(self, question: str, site_ids=None):
            from src.domain.entities import DataQueryResult
            return DataQueryResult(
                answer="Mock answer",
                data_summary={"mock": True},
                source_list="Mock Source",
                resource_link="http://mock-query-link",
                suggested_actions=["Do something"]
            )
            
    ServiceContainer._data_query_service = None
    from src.application.services import DataQueryApplicationService
    ServiceContainer._data_query_service = DataQueryApplicationService(MockDataQueryService())
    
    response = client.post(
        "/api/v1/query/",
        json={"question": "What is the status?"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert data["answer"] == "Mock answer"
    assert data["resource_link"] == "http://mock-query-link"
    assert len(data["suggested_actions"]) > 0
    """Test the provision endpoint handles AI generation errors."""
    blueprint_gen, sharepoint_repo = setup_mocks
    client = TestClient(app)
    
    response = client.post(
        "/api/v1/provision/",
        json={"prompt": "error in generation"}
    )
    
    # Should return 422 for domain-level errors
    assert response.status_code in [422, 500]


def test_unified_chat_endpoint_provisioning(setup_mocks):
    """Test the unified /api/v1/chat endpoint routes correctly."""
    blueprint_gen, sharepoint_repo = setup_mocks
    client = TestClient(app)
    
    with patch("src.presentation.api.dependencies.settings") as mock_settings:
        mock_settings.DEV_MODE = True
        mock_settings.ENVIRONMENT = "development"
        mock_settings.API_KEY = ""
        response = client.post(
            "/api/v1/chat/",
            json={"message": "create a new list called test", "history": []}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert "blueprint" in data


def test_unified_chat_endpoint_chat(setup_mocks):
    """Test the unified chat routing to general chat."""
    blueprint_gen, sharepoint_repo = setup_mocks
    client = TestClient(app)
    
    with patch("src.presentation.api.dependencies.settings") as mock_settings:
        mock_settings.DEV_MODE = True
        mock_settings.ENVIRONMENT = "development"
        mock_settings.API_KEY = ""
        response = client.post(
            "/api/v1/chat/",
            json={"message": "hello agent", "history": []}
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "reply" in data
    assert data["intent"] == "chat"




@patch("src.infrastructure.services.graph_api_client.GraphAPIClient.get")
def test_health_check(mock_graph_get):
    """Test the health check endpoint."""
    mock_graph_get.return_value = {"value": "mocked"}
    
    from src.infrastructure.config import settings
    # Ensure minimum required settings for health check to pass
    old_gemini, settings.GEMINI_API_KEY = settings.GEMINI_API_KEY, "test-key"
    old_vertex, settings.VERTEXAI_PROJECT_ID = settings.VERTEXAI_PROJECT_ID, "test-project"
    old_dev_mode, settings.DEV_MODE = settings.DEV_MODE, True
    
    try:
        client = TestClient(app)
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        print("HEALTH CHECK OUTPUT:", data)
        assert data["status"] == "healthy"
    finally:
        settings.GEMINI_API_KEY = old_gemini
        settings.VERTEXAI_PROJECT_ID = old_vertex
        settings.DEV_MODE = old_dev_mode


def test_root_endpoint():
    """Test the root endpoint."""
    client = TestClient(app)
    response = client.get("/")
    
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "version" in data
