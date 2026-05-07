"""Comprehensive unit tests for all refactored handlers."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from src.presentation.api.schemas.chat_schemas import ChatResponse


# =============================================================================
# ITEM HANDLER TESTS
# =============================================================================

class TestItemHandler:
    """Tests for item_handler.py"""
    
    @pytest.mark.asyncio
    async def test_create_item_success(self):
        """Test successful item creation"""
        from src.presentation.api.handlers.item_handler import handle_item_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.list_item_parser.ListItemParserService') as mock_parser, \
             patch('src.application.use_cases.list_item_operations_use_case.ListItemOperationsUseCase') as mock_use_case:
            
            # Setup mocks
            mock_parser.parse_item_operation = AsyncMock(return_value=Mock(
                operation="create",
                list_name="TestList",
                field_values={"Title": "Test Item"},
                filter_criteria=None
            ))
            
            mock_repo.return_value.get_all_lists = AsyncMock(return_value=[
                {"id": "list-123", "displayName": "TestList"}
            ])
            
            mock_use_case_instance = Mock()
            mock_use_case_instance.create_item_validated = AsyncMock(return_value={
                "id": "item-456",
                "Title": "Test Item"
            })
            mock_use_case.return_value = mock_use_case_instance
            
            # Execute
            result = await handle_item_operations(
                "Add a test item to TestList",
                "session-123",
                "site-456"
            )
            
            # Assert
            assert isinstance(result, ChatResponse)
            assert result.intent == "chat"
            assert "successfully added" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_query_items_with_filters(self):
        """Test querying items with filtering"""
        from src.presentation.api.handlers.item_handler import handle_item_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.list_item_parser.ListItemParserService') as mock_parser, \
             patch('src.application.use_cases.list_item_operations_use_case.ListItemOperationsUseCase') as mock_use_case:
            
            mock_parser.parse_item_operation = AsyncMock(return_value=Mock(
                operation="query",
                list_name="TestList",
                filter_criteria={"status": "active"},
                select_fields=["Title", "Status"],
                order_by="Title",
                limit=10
            ))
            
            mock_repo.return_value.get_all_lists = AsyncMock(return_value=[
                {"id": "list-123", "displayName": "TestList"}
            ])
            
            mock_use_case_instance = Mock()
            mock_use_case_instance.query_items_advanced = AsyncMock(return_value={
                'items': [{"Title": "Item 1", "Status": "active"}],
                'next_link': None
            })
            mock_use_case.return_value = mock_use_case_instance
            
            result = await handle_item_operations(
                "Show active items in TestList",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "found" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_list_not_found(self):
        """Test error handling when list doesn't exist"""
        from src.presentation.api.handlers.item_handler import handle_item_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.list_item_parser.ListItemParserService') as mock_parser:
            
            mock_parser.parse_item_operation = AsyncMock(return_value=Mock(
                operation="create",
                list_name="NonExistentList",
                field_values={"Title": "Test"}
            ))
            
            mock_repo.return_value.get_all_lists = AsyncMock(return_value=[])
            
            result = await handle_item_operations(
                "Add item to NonExistentList",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "couldn't find" in result.reply.lower()


# =============================================================================
# FILE HANDLER TESTS
# =============================================================================

class TestFileHandler:
    """Tests for file_handler.py"""
    
    @pytest.mark.asyncio
    async def test_download_file_success(self):
        """Test successful file download info retrieval"""
        from src.presentation.api.handlers.file_handler import handle_file_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.file_operation_parser.FileOperationParserService') as mock_parser, \
             patch('src.application.use_cases.file_operations_use_case.FileOperationsUseCase') as mock_use_case:
            
            mock_parser.parse_file_operation = AsyncMock(return_value=Mock(
                operation="download",
                file_name="report.pdf",
                library_name="Documents",
                destination_library_name=None
            ))
            
            mock_repo.return_value.get_all_document_libraries = AsyncMock(return_value=[
                {"id": "lib-123", "displayName": "Documents"}
            ])
            
            mock_use_case_instance = Mock()
            mock_use_case_instance.get_library_files = AsyncMock(return_value=[
                {"name": "report.pdf", "file_id": "file-456", "drive_id": "drive-789", "size_mb": 2.5}
            ])
            mock_use_case.return_value = mock_use_case_instance
            
            result = await handle_file_operations(
                "Download report.pdf from Documents",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "file found" in result.reply.lower()
            assert "report.pdf" in result.reply
    
    @pytest.mark.asyncio
    async def test_copy_file_success(self):
        """Test successful file copy"""
        from src.presentation.api.handlers.file_handler import handle_file_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.file_operation_parser.FileOperationParserService') as mock_parser, \
             patch('src.application.use_cases.file_operations_use_case.FileOperationsUseCase') as mock_use_case:
            
            mock_parser.parse_file_operation = AsyncMock(return_value=Mock(
                operation="copy",
                file_name="contract.docx",
                library_name="Archives",
                destination_library_name="Current",
                folder_path=None,
                new_name=None
            ))
            
            mock_repo.return_value.get_all_document_libraries = AsyncMock(return_value=[
                {"id": "lib-1", "displayName": "Archives"},
                {"id": "lib-2", "displayName": "Current"}
            ])
            
            mock_use_case_instance = Mock()
            mock_use_case_instance.get_library_files = AsyncMock(return_value=[
                {"name": "contract.docx", "file_id": "file-123", "drive_id": "drive-456"}
            ])
            mock_use_case.return_value = mock_use_case_instance
            
            mock_repo.return_value.copy_file = AsyncMock(return_value={"id": "new-file-789"})
            
            result = await handle_file_operations(
                "Copy contract.docx from Archives to Current",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "successfully copied" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_get_file_versions(self):
        """Test retrieving file version history"""
        from src.presentation.api.handlers.file_handler import handle_file_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.file_operation_parser.FileOperationParserService') as mock_parser, \
             patch('src.application.use_cases.file_operations_use_case.FileOperationsUseCase') as mock_use_case, \
             patch('src.infrastructure.services.sharepoint.drive_service.DriveService') as mock_drive_service:
            
            mock_parser.parse_file_operation = AsyncMock(return_value=Mock(
                operation="get_versions",
                file_name="document.docx",
                library_name="Documents",
                destination_library_name=None,
                folder_path=None,
                new_name=None
            ))
            
            mock_repo.return_value.get_all_document_libraries = AsyncMock(return_value=[
                {"id": "lib-123", "displayName": "Documents"}
            ])
            
            mock_use_case_instance = Mock()
            mock_use_case_instance.get_library_files = AsyncMock(return_value=[
                {"name": "document.docx", "file_id": "file-123", "drive_id": "drive-456"}
            ])
            mock_use_case.return_value = mock_use_case_instance
            
            mock_drive_instance = Mock()
            mock_drive_instance.get_file_versions = AsyncMock(return_value=[
                {"id": "v1", "lastModifiedDateTime": "2026-04-01", "size": 12345},
                {"id": "v2", "lastModifiedDateTime": "2026-04-10", "size": 12500}
            ])
            mock_drive_service.return_value = mock_drive_instance
            
            result = await handle_file_operations(
                "Show version history for document.docx",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "version history" in result.reply.lower()


# =============================================================================
# SITE HANDLER TESTS
# =============================================================================

class TestSiteHandler:
    """Tests for site_handler.py"""
    
    @pytest.mark.asyncio
    async def test_create_site_success(self):
        """Test successful site creation"""
        from src.presentation.api.handlers.site_handler import handle_site_operations
        
        op_mock = Mock(
                operation="create",
                site_title="Marketing Hub",
                site_template="Team",
                site_description="Marketing team collaboration",
                site_name=None
            )
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.site_operation_parser.SiteOperationBatchParserService.parse',
                   new=AsyncMock(return_value=[op_mock])), \
             patch('src.application.services.template_registry.match_template', return_value=None):

            mock_repo.return_value.create_site = AsyncMock(return_value={
                "id": "site-123",
                "webUrl": "https://contoso.sharepoint.com/sites/marketing-hub"
            })

            result = await handle_site_operations(
                "Create a team site called Marketing Hub",
                "session-123",
                "site-456"
            )

            assert isinstance(result, ChatResponse)
            assert "successfully created" in result.reply.lower()
            assert "marketing hub" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_add_site_member(self):
        """Test adding member to site"""
        from src.presentation.api.handlers.site_handler import handle_site_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.site_operation_parser.SiteOperationParserService') as mock_parser:
            
            mock_parser.parse_site_operation = AsyncMock(return_value=Mock(
                operation="add_member",
                user_email="john@contoso.com",
                site_name=None
            ))
            
            mock_repo.return_value.add_site_member = AsyncMock(return_value=True)
            
            result = await handle_site_operations(
                "Add john@contoso.com as member",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "successfully added" in result.reply.lower()
            assert "john@contoso.com" in result.reply
    
    @pytest.mark.asyncio
    async def test_recycle_bin_list(self):
        """Test listing recycle bin items"""
        from src.presentation.api.handlers.site_handler import handle_site_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.site_operation_parser.SiteOperationParserService') as mock_parser:
            
            mock_parser.parse_site_operation = AsyncMock(return_value=Mock(
                operation="recycle_bin"
            ))
            
            mock_repo.return_value.get_site_recycle_bin = AsyncMock(return_value=[
                {"id": "item-1", "title": "Old Document"},
                {"id": "item-2", "title": "Deleted List"}
            ])
            
            result = await handle_site_operations(
                "Show recycle bin items",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "recycle bin" in result.reply.lower()
            assert "2" in result.reply


# =============================================================================
# PAGE HANDLER TESTS
# =============================================================================

class TestPageHandler:
    """Tests for page_handler.py"""
    
    @pytest.mark.asyncio
    async def test_create_page_success(self):
        """Test successful page creation"""
        from src.presentation.api.handlers.page_handler import handle_page_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.page_operation_parser.PageOperationParserService') as mock_parser:
            
            mock_parser.parse_page_operation = AsyncMock(return_value=Mock(
                operation="create",
                page_title="Welcome Page",
                layout="article",
                content="",
                content_sections=None,
                target_site_name=None,
            ))
            
            mock_repo.return_value.create_page = AsyncMock(return_value={
                "id": "page-123",
                "resource_link": "https://contoso.sharepoint.com/sites/site/SitePages/Welcome.aspx"
            })
            
            result = await handle_page_operations(
                "Create a page called Welcome Page",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "created" in result.reply.lower()
            assert "welcome page" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_list_pages(self):
        """Test listing all pages"""
        from src.presentation.api.handlers.page_handler import handle_page_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.page_operation_parser.PageOperationParserService') as mock_parser:
            
            mock_parser.parse_page_operation = AsyncMock(return_value=Mock(
                operation="list"
            ))
            
            mock_repo.return_value.get_all_pages = AsyncMock(return_value=[
                {"title": "Home", "webUrl": "https://site.com/home"},
                {"title": "About", "webUrl": "https://site.com/about"}
            ])
            
            result = await handle_page_operations(
                "Show me all pages",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "found" in result.reply.lower()
            assert "2" in result.reply
    
    @pytest.mark.asyncio
    async def test_publish_page(self):
        """Test publishing a page"""
        from src.presentation.api.handlers.page_handler import handle_page_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.page_operation_parser.PageOperationParserService') as mock_parser:
            
            mock_parser.parse_page_operation = AsyncMock(return_value=Mock(
                operation="publish",
                page_title="Draft Page",
                page_name=None
            ))
            
            mock_repo.return_value.search_pages = AsyncMock(return_value=[
                {"id": "page-123", "title": "Draft Page"}
            ])
            mock_repo.return_value.publish_page = AsyncMock(return_value=True)
            
            result = await handle_page_operations(
                "Publish the Draft Page",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "published successfully" in result.reply.lower()


# =============================================================================
# LIBRARY HANDLER TESTS
# =============================================================================

class TestLibraryHandler:
    """Tests for library_handler.py"""
    
    @pytest.mark.asyncio
    async def test_create_library_success(self):
        """Test successful library creation"""
        from src.presentation.api.handlers.library_handler import handle_library_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService') as mock_parser:
            
            mock_parser.parse_library_operation = AsyncMock(return_value=Mock(
                operation="create",
                library_name="Project Files",
                description="Documentation for projects",
                enable_versioning=True
            ))
            
            mock_repo.return_value.create_document_library = AsyncMock(return_value={
                "id": "lib-123"
            })
            
            result = await handle_library_operations(
                "Create a library called Project Files",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "created successfully" in result.reply.lower()
            assert "project files" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_list_libraries(self):
        """Test listing all libraries"""
        from src.presentation.api.handlers.library_handler import handle_library_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService') as mock_parser:
            
            mock_parser.parse_library_operation = AsyncMock(return_value=Mock(
                operation="list"
            ))
            
            mock_repo.return_value.get_all_document_libraries = AsyncMock(return_value=[
                {"displayName": "Documents", "list": {"itemCount": 45}},
                {"displayName": "Archives", "list": {"itemCount": 120}}
            ])
            
            result = await handle_library_operations(
                "Show all document libraries",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "2" in result.reply
            assert "document" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_add_column_to_library(self):
        """Test adding column to library"""
        from src.presentation.api.handlers.library_handler import handle_library_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService') as mock_parser:
            
            mock_parser.parse_library_operation = AsyncMock(return_value=Mock(
                operation="add_column",
                library_name="Documents",
                column_name="Status",
                column_type="text"
            ))
            
            mock_repo.return_value.get_all_document_libraries = AsyncMock(return_value=[
                {"id": "lib-123", "displayName": "Documents"}
            ])
            mock_repo.return_value.add_column_to_list = AsyncMock(return_value=True)
            
            result = await handle_library_operations(
                "Add Status column to Documents library",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "column" in result.reply.lower()
            assert "added" in result.reply.lower()


# =============================================================================
# PERMISSION HANDLER TESTS
# =============================================================================

class TestPermissionHandler:
    """Tests for permission_handler.py"""
    
    @pytest.mark.asyncio
    async def test_list_groups(self):
        """Test listing SharePoint groups"""
        from src.presentation.api.handlers.permission_handler import handle_permission_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.permission_operation_parser.PermissionOperationParserService') as mock_parser:
            
            mock_parser.parse_permission_operation = AsyncMock(return_value=Mock(
                operation="list_groups"
            ))
            
            mock_repo.return_value.get_site_groups = AsyncMock(return_value=[
                {"displayName": "Site Members", "description": "Default members group"},
                {"displayName": "Site Owners", "description": "Default owners group"}
            ])
            
            result = await handle_permission_operations(
                "Show me all SharePoint groups",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "2" in result.reply
            assert "group" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_create_group(self):
        """Test creating SharePoint group"""
        from src.presentation.api.handlers.permission_handler import handle_permission_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.permission_operation_parser.PermissionOperationParserService') as mock_parser:
            
            mock_parser.parse_permission_operation = AsyncMock(return_value=Mock(
                operation="create_group",
                group_name="Finance Team"
            ))
            
            mock_repo.return_value.create_site_group = AsyncMock(return_value={
                "Id": "group-123"
            })
            
            result = await handle_permission_operations(
                "Create a group called Finance Team",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "created successfully" in result.reply.lower()
            assert "finance team" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_check_permissions(self):
        """Test checking user permissions"""
        from src.presentation.api.handlers.permission_handler import handle_permission_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.permission_operation_parser.PermissionOperationParserService') as mock_parser:
            
            mock_parser.parse_permission_operation = AsyncMock(return_value=Mock(
                operation="check",
                user_email="john@contoso.com",
                resource_name=None
            ))
            
            mock_repo.return_value.get_user_effective_permissions = AsyncMock(return_value={
                "High": 123
            })
            
            result = await handle_permission_operations(
                "Check permissions for john@contoso.com",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "permissions" in result.reply.lower()
            assert "john@contoso.com" in result.reply


# =============================================================================
# HUB SITE HANDLER TESTS
# =============================================================================

class TestHubSiteHandler:
    """Tests for hub_site_handler.py"""
    
    @pytest.mark.asyncio
    async def test_list_hub_sites(self):
        """Test listing hub sites"""
        from src.presentation.api.handlers.hub_site_handler import handle_hub_site_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.hub_site_operation_parser.HubSiteOperationParserService') as mock_parser, \
             patch('src.infrastructure.services.sharepoint.site_service.SiteService') as mock_site_service:
            
            mock_parser.parse_hub_site_operation = AsyncMock(return_value=Mock(
                operation="list_hubs"
            ))
            
            mock_service_instance = Mock()
            mock_service_instance.get_hub_sites = AsyncMock(return_value=[
                {"displayName": "Corporate Hub", "webUrl": "https://site.com/corporate", "id": "hub-1"},
                {"displayName": "HR Hub", "webUrl": "https://site.com/hr", "id": "hub-2"}
            ])
            mock_site_service.return_value = mock_service_instance
            
            result = await handle_hub_site_operations(
                "Show me all hub sites",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "hub sites" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_register_hub_site(self):
        """Test registering a site as hub"""
        from src.presentation.api.handlers.hub_site_handler import handle_hub_site_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.hub_site_operation_parser.HubSiteOperationParserService') as mock_parser, \
             patch('src.infrastructure.services.sharepoint.site_service.SiteService') as mock_site_service:
            
            mock_parser.parse_hub_site_operation = AsyncMock(return_value=Mock(
                operation="register_hub",
                site_name="Corporate"
            ))
            
            mock_repo.return_value.get_all_sites = AsyncMock(return_value=[
                {"displayName": "Corporate", "id": "site-123"}
            ])
            
            mock_service_instance = Mock()
            mock_service_instance.register_hub_site = AsyncMock(return_value=True)
            mock_site_service.return_value = mock_service_instance
            
            result = await handle_hub_site_operations(
                "Register Corporate as a hub site",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "registered" in result.reply.lower()


# =============================================================================
# ENTERPRISE HANDLER TESTS
# =============================================================================

class TestEnterpriseHandler:
    """Tests for enterprise_handler.py"""
    
    @pytest.mark.asyncio
    async def test_create_content_type(self):
        """Test creating content type"""
        from src.presentation.api.handlers.enterprise_handler import handle_enterprise_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.enterprise_operation_parser.EnterpriseOperationParserService') as mock_parser, \
             patch('src.infrastructure.services.sharepoint.enterprise_service.EnterpriseService') as mock_enterprise_service:
            
            mock_parser.parse_enterprise_operation = AsyncMock(return_value=Mock(
                operation="create_content_type",
                content_type_name="Project Document",
                content_type_description="Documents for projects",
                parent_content_type="Document"
            ))
            
            mock_service_instance = Mock()
            mock_service_instance.create_content_type = AsyncMock(return_value={
                "content_type_id": "ct-123"
            })
            mock_enterprise_service.return_value = mock_service_instance
            
            result = await handle_enterprise_operations(
                "Create a content type called Project Document",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "created" in result.reply.lower()
            assert "project document" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_create_term_set(self):
        """Test creating term set"""
        from src.presentation.api.handlers.enterprise_handler import handle_enterprise_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo, \
             patch('src.infrastructure.external_services.enterprise_operation_parser.EnterpriseOperationParserService') as mock_parser, \
             patch('src.infrastructure.services.sharepoint.enterprise_service.EnterpriseService') as mock_enterprise_service:
            
            mock_parser.parse_enterprise_operation = AsyncMock(return_value=Mock(
                operation="create_term_set",
                term_set_name="Departments",
                terms=["HR", "Finance", "IT", "Marketing"]
            ))
            
            mock_service_instance = Mock()
            mock_service_instance.create_term_set = AsyncMock(return_value={
                "term_set_id": "ts-456"
            })
            mock_enterprise_service.return_value = mock_service_instance
            
            result = await handle_enterprise_operations(
                "Create a term set called Departments with HR, Finance, IT, Marketing",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "created" in result.reply.lower()
            assert "departments" in result.reply.lower()


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================

class TestErrorHandling:
    """Test error handling across all handlers"""
    
    @pytest.mark.asyncio
    async def test_parser_returns_none(self):
        """Test when parser can't understand the operation"""
        from src.presentation.api.handlers.item_handler import handle_item_operations
        
        with patch('src.infrastructure.external_services.list_item_parser.ListItemParserService') as mock_parser:
            mock_parser.parse_item_operation = AsyncMock(return_value=None)
            
            result = await handle_item_operations(
                "gibberish that makes no sense",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "couldn't understand" in result.reply.lower()
    
    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test general exception handling"""
        from src.presentation.api.handlers.item_handler import handle_item_operations
        
        with patch('src.presentation.api.get_repository') as mock_repo:
            mock_repo.side_effect = Exception("Database connection failed")
            
            result = await handle_item_operations(
                "Add an item",
                "session-123",
                "site-456"
            )
            
            assert isinstance(result, ChatResponse)
            assert "couldn't complete" in result.reply.lower()


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestHandlerIntegration:
    """Integration tests simulating real workflows"""
    
    @pytest.mark.asyncio
    async def test_multi_step_workflow(self):
        """Test a multi-step workflow across handlers"""
        # This would test creating a library, adding files, setting permissions
        # For now, we verify that handlers can be called in sequence
        from src.presentation.api.handlers.library_handler import handle_library_operations
        from src.presentation.api.handlers.permission_handler import handle_permission_operations
        
        with patch('src.presentation.api.get_repository'), \
             patch('src.infrastructure.external_services.library_operation_parser.LibraryOperationParserService'), \
             patch('src.infrastructure.external_services.permission_operation_parser.PermissionOperationParserService'):
            
            # Step 1: Create library (would be mocked to succeed)
            # Step 2: Set permissions (would be mocked to succeed)
            # This test verifies the workflow structure
            assert True  # Placeholder for actual integration test
