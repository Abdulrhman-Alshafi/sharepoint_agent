"""Handler for SharePoint enterprise operations."""

from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response

logger = get_logger(__name__)


async def handle_enterprise_operations(message: str, session_id: str, site_id: str, user_token: str = None, user_login_name: str = "") -> ChatResponse:
    """Handle enterprise SharePoint operations (content types, term sets, views)."""
    from src.presentation.api import get_site_repository, get_list_repository, get_page_repository, get_library_repository, get_permission_repository, get_enterprise_repository
    from src.infrastructure.external_services.enterprise_operation_parser import EnterpriseOperationParserService
    
    try:
        site_repository = get_site_repository(user_token=user_token)
        list_repository = get_list_repository(user_token=user_token)
        page_repository = get_page_repository(user_token=user_token)
        library_repository = get_library_repository(user_token=user_token)
        permission_repository = get_permission_repository(user_token=user_token)
        enterprise_repository = get_enterprise_repository(user_token=user_token)
        
       # Parse the operation using AI
        operation = await EnterpriseOperationParserService.parse_enterprise_operation(message)
        
        if not operation:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the enterprise operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Create a content type called Project Document'\n"
                       "- 'Show me all content types'\n"
                       "- 'Create a term set called Departments with HR, Finance, IT'\n"
                       "- 'Create a view called Active Tasks for the Tasks list'"
            )
        
        # ── LIST CONTENT TYPES ──────────────────────────────
        if operation.operation == "list_content_types":
            from src.infrastructure.services.sharepoint.enterprise_service import EnterpriseService
            
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            enterprise_service = EnterpriseService(graph_client, rest_client) if graph_client and rest_client else EnterpriseService(None, None)
            
            # Note: Would need to add a list_content_types method to EnterpriseService
            return ChatResponse(
                intent="chat",
                reply="📋 **Content Types Listing**\n\n"
                       "⚠️ Content type listing is not yet fully implemented.\n\n"
                       "You can create content types with:\n"
                       "'Create a content type called [Name] based on [Document/Item]'"
            )
        
        # ── CREATE CONTENT TYPE ─────────────────────────────
        elif operation.operation == "create_content_type":
            if not operation.content_type_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a name for the content type.\n\n"
                           "Example: 'Create a content type called Project Document'"
                )
            
            from src.infrastructure.services.sharepoint.enterprise_service import EnterpriseService
            from src.domain.entities import ContentType
            
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            enterprise_service = EnterpriseService(graph_client, rest_client) if graph_client and rest_client else EnterpriseService(None, None)
            
            # Create ContentType entity
            content_type = ContentType(
                name=operation.content_type_name,
                description=operation.content_type_description or "",
                parent_type=operation.parent_content_type or "Item",
                columns=[]
            )
            
            result = await enterprise_service.create_content_type(content_type)
            
            if result:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully created content type **{operation.content_type_name}**!\n\n"
                           f"📋 Based on: {operation.parent_content_type or 'Item'}\n"
                           f"🆔 ID: {result.get('content_type_id', 'N/A')}\n\n"
                           f"💡 You can now use this content type in lists and libraries.",
                    data_summary=result
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to create content type **{operation.content_type_name}**."
                )
        
        # ── LIST TERM SETS ──────────────────────────────────
        elif operation.operation == "list_term_sets":
            return ChatResponse(
                intent="chat",
                reply="📋 **Term Sets Listing**\n\n"
                       "⚠️ Term set listing is not yet fully implemented.\n\n"
                       "You can create term sets with:\n"
                       "'Create a term set called [Name] with terms [term1, term2, term3]'"
            )
        
        # ── CREATE TERM SET ─────────────────────────────────
        elif operation.operation == "create_term_set":
            if not operation.term_set_name or not operation.terms:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the term set name and the terms.\n\n"
                           "Example: 'Create a term set called Departments with HR, Finance, IT, Marketing'"
                )
            
            from src.infrastructure.services.sharepoint.enterprise_service import EnterpriseService
            from src.domain.entities import TermSet
            
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            enterprise_service = EnterpriseService(graph_client, rest_client) if graph_client and rest_client else EnterpriseService(None, None)
            
            # Create TermSet entity
            term_set = TermSet(
                name=operation.term_set_name,
                terms=operation.terms
            )
            
            result = await enterprise_service.create_term_set(term_set)
            
            if result:
                terms_list = ", ".join(operation.terms)
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully created term set **{operation.term_set_name}**!\n\n"
                           f"📌 Terms: {terms_list}\n"
                           f"🆔 ID: {result.get('term_set_id', 'N/A')}\n\n"
                           f"💡 You can now use this term set in managed metadata columns.",
                    data_summary=result
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to create term set **{operation.term_set_name}**.\n\n"
                           "This may require tenant-level admin permissions for the term store."
                )
        
        # ── LIST VIEWS ──────────────────────────────────────
        elif operation.operation == "list_views":
            if not operation.list_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which list to show views for.\n\n"
                  "Example: 'Show me views for the Tasks list'"
                )
            
            # Find the list
            all_lists = await list_repository.get_all_lists(site_id=site_id)
            target_list = None
            for lst in all_lists:
                list_name = lst.get("displayName", "").lower()
                if operation.list_name.lower() in list_name or list_name in operation.list_name.lower():
                    target_list = lst
                    break
            
            if not target_list:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ List '{operation.list_name}' not found."
                )
            
            # Get views (would need to implement in repository)
            return ChatResponse(
                intent="chat",
                reply=f"📋 **Views for {target_list.get('displayName')}**\n\n"
                       "⚠️ View listing is not yet fully implemented.\n\n"
                       "You can create views with:\n"
                       "'Create a view called [Name] for [ListName] showing [Field1, Field2]'"
            )
        
        # ── CREATE VIEW ─────────────────────────────────────
        elif operation.operation == "create_view":
            if not operation.view_name or not operation.list_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the view name and the list name.\n\n"
                           "Example: 'Create a view called Active Tasks for the Tasks list'"
                )
            
            # Find the list
            all_lists = await list_repository.get_all_lists(site_id=site_id)
            target_list = None
            for lst in all_lists:
                list_name = lst.get("displayName", "").lower()
                if operation.list_name.lower() in list_name or list_name in operation.list_name.lower():
                    target_list = lst
                    break
            
            if not target_list:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ List '{operation.list_name}' not found."
                )
            
            from src.infrastructure.services.sharepoint.enterprise_service import EnterpriseService
            from src.domain.entities import SPView
            
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            enterprise_service = EnterpriseService(graph_client, rest_client) if graph_client and rest_client else EnterpriseService(None, None)
            
            # Create SPView entity
            view = SPView(
                title=operation.view_name,
                target_list_title=target_list.get("displayName", ""),
                columns=operation.view_fields or ["Title"],
                query="",
                row_limit=100
            )
            
            result = await enterprise_service.create_view(view)
            
            if result:
                fields_list = ", ".join(operation.view_fields or ["Title"])
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully created view **{operation.view_name}** for list **{target_list.get('displayName')}**!\n\n"
                           f"👁️ Fields: {fields_list}\n\n"
                           f"💡 You can now use this view to filter and organize list data.",
                    data_summary=result
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to create view **{operation.view_name}**."
                )
        
        else:
            return ChatResponse(
                intent="chat",
                reply=f"Unknown enterprise operation: {operation.operation}"
            )
    
    except Exception as e:
        from src.domain.exceptions import PermissionDeniedException, AuthenticationException, DomainException
        from src.presentation.api.orchestrators.orchestrator_utils import (
            domain_error_response, permission_denied_response, auth_expired_response,
        )
        if isinstance(e, PermissionDeniedException):
            return permission_denied_response(session_id=session_id)
        if isinstance(e, AuthenticationException):
            return auth_expired_response(session_id=session_id)
        if isinstance(e, DomainException):
            return domain_error_response(e, intent="chat", session_id=session_id)
        return error_response(logger, "chat", "Sorry, I couldn't complete that enterprise operation: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
