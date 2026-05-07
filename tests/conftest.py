"""Test infrastructure and fixtures for DDD/Clean Architecture."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from src.main import app
from src.presentation.api import ServiceContainer
from src.domain.entities import ProvisioningBlueprint, SPList, SPPage, ActionType, PromptValidationResult
from src.domain.value_objects import SPColumn, WebPart
from src.domain.services import BlueprintGeneratorService, DataQueryService
from src.domain.services.intent_classification import IntentClassificationService
from src.domain.repositories import SharePointRepository


@pytest.fixture
def client():
    """Provide a FastAPI test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_services():
    """Reset service container before and after each test."""
    ServiceContainer.reset()
    yield
    ServiceContainer.reset()


class MockBlueprintGenerator(BlueprintGeneratorService):
    """Mock blueprint generator for testing."""

    async def validate_prompt(self, prompt: str) -> PromptValidationResult:
        """Mock validation — always approve unless prompt contains 'cat'."""
        if "cat" in prompt.lower():
            return PromptValidationResult(
                is_valid=False,
                risk_level="low",
                rejection_reason="Resource name 'cat' is not enterprise-appropriate."
            )
        return PromptValidationResult(is_valid=True, risk_level="low")

    async def generate_blueprint(self, prompt: str) -> ProvisioningBlueprint:
        if "error" in prompt.lower():
            raise Exception("Mock AI Error")
        
        return ProvisioningBlueprint(
            reasoning="Mocked reasoning",
            lists=[
                SPList(
                    title="New Mock List",
                    description="Mock List Description",
                    columns=[SPColumn(name="Title", type="text", required=True)],
                    action=ActionType.CREATE
                )
            ],
            pages=[
                SPPage(
                    title="Mock Page",
                    webparts=[WebPart(type="Text", properties={"content": "Hello"})],
                    action=ActionType.CREATE
                )
            ]
        )


class MockSharePointRepository(SharePointRepository):
    # Stubs for all abstract methods (auto-generated for test compliance)
    async def add_item_attachment(self, *a, **kw): pass
    async def add_library_column(self, *a, **kw): pass
    async def add_site_member(self, *a, **kw): pass
    async def add_site_owner(self, *a, **kw): pass
    async def batch_delete_files(self, *a, **kw): pass
    async def batch_upload_files(self, *a, **kw): pass
    async def checkin_file(self, *a, **kw): pass
    async def checkin_page(self, *a, **kw): pass
    async def checkout_file(self, *a, **kw): pass
    async def checkout_page(self, *a, **kw): pass
    async def copy_file(self, *a, **kw): pass
    async def copy_page(self, *a, **kw): pass
    async def create_file_share_link(self, *a, **kw): pass
    async def create_folder(self, *a, **kw): pass
    async def create_list_view(self, *a, **kw): pass
    async def create_page_share_link(self, *a, **kw): pass
    async def delete_document_library(self, *a, **kw): pass
    async def delete_folder(self, *a, **kw): pass
    async def delete_item_attachment(self, *a, **kw): pass
    async def delete_list_view(self, *a, **kw): pass
    async def delete_site(self, *a, **kw): pass
    async def discard_page_checkout(self, *a, **kw): pass
    async def empty_recycle_bin(self, *a, **kw): pass
    async def get_all_pages(self, *a, **kw): return []
    async def get_file_by_path(self, *a, **kw): pass
    async def get_file_versions(self, *a, **kw): pass
    async def get_folder_contents(self, *a, **kw): pass
    async def get_item_attachments(self, *a, **kw): pass
    async def get_library_schema(self, *a, **kw): pass
    async def get_list_schema(self, *a, **kw): pass
    async def get_list_views(self, *a, **kw): pass
    async def get_page_by_name(self, *a, **kw): pass
    async def get_page_versions(self, *a, **kw): pass
    async def get_site(self, *a, **kw): pass
    async def get_site_analytics(self, *a, **kw): pass
    async def get_site_by_url(self, *a, **kw): pass
    async def get_site_members(self, *a, **kw): pass
    async def get_site_navigation(self, *a, **kw): return []
    async def get_site_owners(self, *a, **kw): pass
    async def get_site_permissions(self, *a, **kw): pass
    async def get_site_recycle_bin(self, *a, **kw): pass
    async def get_site_storage_info(self, *a, **kw): pass
    async def move_file(self, *a, **kw): pass
    async def promote_page_as_news(self, *a, **kw): pass
    async def publish_page(self, *a, **kw): pass
    async def query_library_files(self, *a, **kw): pass
    async def query_list_items_advanced(self, *a, **kw): pass
    async def remove_site_user(self, *a, **kw): pass
    async def restore_file_version(self, *a, **kw): pass
    async def restore_from_recycle_bin(self, *a, **kw): pass
    async def restore_page_version(self, *a, **kw): pass
    async def search_libraries(self, *a, **kw): pass
    async def search_pages(self, *a, **kw): pass
    async def search_sites(self, *a, **kw): pass
    async def unpublish_page(self, *a, **kw): pass
    async def update_document_library(self, *a, **kw): pass
    async def update_site(self, *a, **kw): pass
    async def update_site_navigation(self, *a, **kw): pass
    async def update_site_theme(self, *a, **kw): pass
    async def create_site(self, *a, **kw): pass
    async def get_all_sites(self, *a, **kw): pass
    async def get_library_items(self, *a, **kw): pass
    async def upload_file(self, *a, **kw): pass
    async def download_file(self, *a, **kw): pass
    async def delete_file(self, *a, **kw): pass
    async def update_file_metadata(self, *a, **kw): pass
    async def get_library_drive_id(self, *a, **kw): pass
    # New focused-interface method stubs
    async def get_list_item(self, *a, **kw): pass
    async def get_list_columns(self, *a, **kw): return []
    async def add_list_column(self, *a, **kw): pass
    async def create_group(self, *a, **kw): pass
    async def get_all_groups(self, *a, **kw): return []
    async def get_group(self, *a, **kw): pass
    async def update_group(self, *a, **kw): pass
    async def delete_group(self, *a, **kw): pass
    async def add_user_to_group(self, *a, **kw): pass
    async def remove_user_from_group(self, *a, **kw): pass
    async def get_group_members(self, *a, **kw): return []
    async def get_list_permissions(self, *a, **kw): pass
    async def get_item_permissions(self, *a, **kw): pass
    async def grant_list_permissions(self, *a, **kw): pass
    async def revoke_list_permissions(self, *a, **kw): pass
    async def break_permission_inheritance(self, *a, **kw): pass
    async def reset_permission_inheritance(self, *a, **kw): pass
    async def get_permission_levels(self, *a, **kw): return []
    async def create_custom_permission_level(self, *a, **kw): pass
    async def get_content_types(self, *a, **kw): return []
    async def get_content_type(self, *a, **kw): pass
    async def update_content_type(self, *a, **kw): pass
    async def delete_content_type(self, *a, **kw): pass
    async def add_content_type_to_list(self, *a, **kw): pass
    async def get_term_sets(self, *a, **kw): return []
    async def get_term_set(self, *a, **kw): pass
    async def add_term_to_set(self, *a, **kw): pass
    async def delete_term_set(self, *a, **kw): pass
    async def get_views(self, *a, **kw): return []
    async def get_view(self, *a, **kw): pass
    async def update_view(self, *a, **kw): pass
    async def delete_view(self, *a, **kw): pass
    async def discard_file_checkout(self, *a, **kw): pass
    async def check_user_permission(self, *a, **kw): return True
    async def get_page_analytics(self, *a, **kw): return {}
    async def schedule_page_publish(self, *a, **kw): return {}
    async def ensure_user_principal_id(self, *a, **kw): return 0
    """Mock SharePoint repository for testing."""
    
    async def create_list(self, sp_list: SPList) -> dict:
        if sp_list.title == "Error List":
            raise Exception("Mock Graph API Error")
        return {"id": "list-123", "name": sp_list.title, "resource_link": "http://mock-link"}

    async def create_page(self, sp_page: SPPage) -> dict:
        return {"id": "page-123", "name": sp_page.title, "resource_link": "http://mock-link"}

    async def get_list(self, list_id: str) -> SPList:
        raise NotImplementedError()

    async def get_page(self, page_id: str) -> SPPage:
        raise NotImplementedError()

    async def delete_list(self, list_id: str) -> bool:
        return True

    async def delete_page(self, page_id: str) -> bool:
        return True
        
    async def get_all_lists(self) -> list:
        return [{"id": "list-123", "displayName": "Mock List", "webUrl": "http://mock-list-123"}]
        
    async def get_list_items(self, list_id: str) -> list:
        return [{"id": "item-1", "fields": {"Title": "Item 1"}}]
        
    async def search_lists(self, query: str) -> list:
        return []
        
    async def update_list(self, list_id: str, sp_list: SPList) -> dict:
        return {"id": list_id, "name": sp_list.title, "resource_link": "http://mock-update"}
        
    async def update_page_content(self, page_id: str, sp_page: SPPage) -> dict:
        return {"id": page_id, "name": sp_page.title, "resource_link": "http://mock-update"}

    async def create_document_library(self, library) -> dict:
        return {"id": "lib-123", "name": library.title, "resource_link": "http://mock-lib"}

    async def get_all_document_libraries(self) -> list:
        return [{"id": "lib-123", "displayName": "Mock Library", "webUrl": "http://mock-lib-123"}]

    async def get_site_groups(self) -> list:
        return [{"Id": 1, "Title": "Mock Group"}]

    async def create_site_group(self, group) -> dict:
        return {"id": "group-123", "name": group.name, "group_id": "1"}

    async def assign_library_permission(self, library_id: str, group_id: str, permission_level: str) -> bool:
        return True

    async def create_content_type(self, content_type) -> dict:
        return {"id": "ct-123", "name": content_type.name}

    async def create_term_set(self, term_set) -> dict:
        return {"id": "ts-123", "name": term_set.name}

    async def create_view(self, view) -> dict:
        return {"id": "view-123", "name": view.title}

    async def seed_list_data(self, list_id: str, seed_data: list) -> bool:
        return True

    # List item operations
    async def create_list_item(self, list_id: str, item_data: dict, site_id: str = None) -> dict:
        return {"id": "item-123", "fields": item_data}

    async def update_list_item(self, list_id: str, item_id: str, item_data: dict, site_id: str = None) -> dict:
        return {"id": item_id, "fields": item_data}

    async def delete_list_item(self, list_id: str, item_id: str, site_id: str = None) -> bool:
        return True

    async def query_list_items(self, list_id: str, filter_query: str = None, site_id: str = None) -> list:
        return [{"id": "item-1", "fields": {"Title": "Test Item"}}]

    # Placeholder methods for other required interface methods
    async def create_site(self, sp_site) -> dict:
        return {"id": "site-123", "name": sp_site.title, "resource_link": "http://mock-site"}

    async def get_all_sites(self) -> list:
        return [{"id": "site-123", "displayName": "Mock Site", "webUrl": "http://mock-site"}]

    async def get_library_items(self, library_id: str, site_id: str = None) -> list:
        return []

    async def upload_file(self, library_id: str, file_name: str, file_content: bytes, metadata: dict = None, site_id: str = None):
        return None

    async def download_file(self, file_id: str, drive_id: str) -> bytes:
        return b""

    async def delete_file(self, file_id: str, drive_id: str) -> bool:
        return True

    async def update_file_metadata(self, file_id: str, drive_id: str, metadata: dict):
        return None

    async def get_library_drive_id(self, library_id: str, site_id: str = None) -> str:
        return "drive-123"


class MockIntentClassificationService(IntentClassificationService):
    """Mock intent classification service for testing."""
    async def classify_intent(self, message: str):
        if "provision" in message.lower() or "create" in message.lower():
            return "provision"
        if "query" in message.lower() or "what" in message.lower():
            return "query"
        return "chat"


@pytest.fixture
def mock_blueprint_generator():
    """Provide a mock blueprint generator."""
    return MockBlueprintGenerator()


@pytest.fixture
def mock_sharepoint_repository():
    """Provide a mock SharePoint repository."""
    return MockSharePointRepository()


@pytest.fixture
def mock_intent_classifier():
    """Provide a mock intent classifier."""
    return MockIntentClassificationService()


@pytest.fixture(autouse=True)
def override_dependencies(mock_blueprint_generator, mock_sharepoint_repository, mock_intent_classifier):
    ServiceContainer.set_blueprint_generator(mock_blueprint_generator)
    ServiceContainer.set_sharepoint_repository(mock_sharepoint_repository)
    ServiceContainer._intent_classification_service = mock_intent_classifier
    yield
    ServiceContainer.reset()
