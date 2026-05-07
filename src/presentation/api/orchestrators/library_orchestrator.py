"""Handler for SharePoint library operations."""

from src.domain.entities.conversation import ResourceType
from src.presentation.api import ServiceContainer
from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response

logger = get_logger(__name__)


async def handle_library_operations(message: str, session_id: str, site_id: str, user_token: str = None, user_login_name: str = "", last_created: tuple = None) -> ChatResponse:
    """Handle library operations (create, list, delete, configure)."""
    from src.presentation.api import get_repository
    from src.infrastructure.external_services.library_operation_parser import LibraryOperationParserService
    
    try:
        repository = get_repository(user_token=user_token)
        
        # Prefer the site where the library was created (from last_created[2]) over the request site
        _lib_site_id = (last_created[2] if (last_created and len(last_created) > 2 and last_created[2]) else None) or site_id
        
        # Parse the operation using AI
        operation = await LibraryOperationParserService.parse_library_operation(message)
        
        if not operation:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the library operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Create a document library called Project Files'\n"
                       "- 'Show me all document libraries'\n"
                       "- 'Add a Status column to the Documents library'\n"
                       "- 'Enable versioning on the HR Documents library'"
            )
        
        # ── LIST OPERATION ──────────────────────────────────
        if operation.operation == "list":
            libraries = await repository.get_all_document_libraries(site_id=_lib_site_id)
            if not libraries:
                return ChatResponse(
                    intent="chat",
                    reply="No document libraries found in this site."
                )
            
            reply = f"📚 Found **{len(libraries)}** document librar{'ies' if len(libraries) != 1 else 'y'}:\n\n"
            for idx, lib in enumerate(libraries[:20], 1):  # Limit to 20
                lib_name = lib.get('displayName', 'Untitled')
                item_count = lib.get('list', {}).get('itemCount', 'Unknown')
                reply += f"{idx}. **{lib_name}** ({item_count} items)\n"
            
            if len(libraries) > 20:
                reply += f"\n... and {len(libraries) - 20} more libraries."
            
            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary={"library_count": len(libraries)}
            )
        
        # ── GET OPERATION ───────────────────────────────────
        elif operation.operation == "get":
            if not operation.library_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a library name.\n\nExample: 'Show me the Documents library'"
                )
            
            # Find the library
            libraries = await repository.get_all_document_libraries(site_id=_lib_site_id)
            matched_lib = next(
                (lib for lib in libraries if operation.library_name.lower() in lib.get('displayName', '').lower()),
                None
            )
            
            if not matched_lib:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Library '{operation.library_name}' not found."
                )
            
            lib_name = matched_lib.get('displayName', 'Unknown')
            item_count = matched_lib.get('list', {}).get('itemCount', 'Unknown')
            lib_id = matched_lib.get('id', 'Unknown')
            created = matched_lib.get('createdDateTime', 'Unknown')
            
            return ChatResponse(
                intent="chat",
                reply=f"📚 Library: **{lib_name}**\n\n"
                       f"📊 Items: {item_count}\n"
                       f"🆔 ID: {lib_id}\n"
                       f"📅 Created: {created}\n",
                data_summary={**matched_lib, "library_name": lib_name, "site_id": site_id}
            )
        
        # ── CREATE OPERATION ────────────────────────────────
        elif operation.operation == "create":
            if not operation.library_name:
                gathering_service = ServiceContainer.get_gathering_service()
                _, first_question = gathering_service.start_gathering(
                    session_id, message, ResourceType.LIBRARY
                )

                if first_question:
                    return ChatResponse(
                        intent="provision",
                        reply=f"Sure! Let me help you set that up.\n\n{first_question.question_text}",
                        requires_input=True,
                        question_prompt=first_question.question_text,
                        field_type=first_question.field_type,
                        field_options=first_question.options,
                        quick_suggestions=first_question.options[:3] if first_question.options else None,
                        session_id=session_id,
                    )

                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a library name.\n\nExample: 'Create a library called Project Files'"
                )
            
            from src.domain.entities.core import SPList
            from src.domain.value_objects import SPColumn
            
            # Create a document library (special type of list)
            new_library = SPList(
                title=operation.library_name,
                description=operation.description or f"Document library for {operation.library_name}",
                template="documentLibrary",  # Special template for document libraries
                columns=[SPColumn(name="Title", type="text", required=False)]  # Document libraries have default columns
            )
            
            result = await repository.create_document_library(new_library, site_id=site_id)

            created_folders = []
            folder_warnings = []
            library_id = result.get("id")
            for raw_path in (operation.folder_paths or []):
                path = (raw_path or "").strip().strip("/")
                if not path:
                    continue
                # Create nested folders in order: A/B/C => A, A/B, A/B/C
                segments = [seg.strip() for seg in path.split("/") if seg.strip()]
                for idx, folder_name in enumerate(segments):
                    parent = "/".join(segments[:idx]) if idx > 0 else "/"
                    try:
                        await repository.create_folder(
                            library_id=library_id,
                            folder_name=folder_name,
                            parent_folder_path=parent,
                            site_id=site_id,
                        )
                        created_folders.append("/".join(segments[: idx + 1]))
                    except Exception as folder_err:
                        msg = f"Could not create folder '{'/'.join(segments[: idx + 1])}': {folder_err}"
                        logger.warning(msg)
                        folder_warnings.append(msg)
                        break
            
            # Configure versioning if specified
            if operation.enable_versioning:
                library_id = result.get('id')
                if library_id:
                    try:
                        # Enable major versioning via PATCH on the list settings endpoint
                        await repository.enable_list_versioning(library_id, site_id)
                        logger.info("Versioning enabled for library '%s'", library_id)
                        versioning_note = "\n✅ Versioning enabled (up to 500 versions)."
                    except Exception as e:
                        logger.warning("Could not enable versioning for library '%s': %s", library_id, e)
                        versioning_note = "\n⚠️ Library created but versioning could not be enabled automatically. Please enable it in the library settings."
                else:
                    versioning_note = ""
            else:
                versioning_note = ""
            
            lib_url = result.get("webUrl") or result.get("resource_link", "")
            folder_note = f"\n📁 Created folders: {', '.join(dict.fromkeys(created_folders))}" if created_folders else ""
            warning_note = f"\n⚠️ Some folders were not created automatically." if folder_warnings else ""
            link_text = f"\n\n🔗 [Open {operation.library_name}]({lib_url})" if lib_url else ""
            return ChatResponse(
                intent="chat",
                reply=f"✅ Document library **{operation.library_name}** created successfully!{folder_note}{warning_note}{link_text}",
                data_summary={**result, "library_name": operation.library_name, "site_id": site_id}
            )
        
        # ── DELETE OPERATION ────────────────────────────────
        elif operation.operation == "delete":
            if not operation.library_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which library to delete.\n\nExample: 'Delete the old archives library'"
                )
            
            libraries = await repository.get_all_document_libraries(site_id=_lib_site_id)
            matched_lib = next(
                (lib for lib in libraries if operation.library_name.lower() in lib.get('displayName', '').lower()),
                None
            )
            
            if not matched_lib:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Library '{operation.library_name}' not found."
                )
            
            library_id = matched_lib.get('id')
            await repository.delete_list(library_id, site_id=site_id)
            
            return ChatResponse(
                intent="chat",
                reply=f"✅ Library **{operation.library_name}** deleted successfully!"
            )
        
        # ── GET SCHEMA OPERATION ────────────────────────────
        elif operation.operation == "get_schema":
            if not operation.library_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a library name.\n\nExample: 'Show me the schema of Documents library'"
                )
            
            libraries = await repository.get_all_document_libraries(site_id=_lib_site_id)
            matched_lib = next(
                (lib for lib in libraries if operation.library_name.lower() in lib.get('displayName', '').lower()),
                None
            )
            
            if not matched_lib:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Library '{operation.library_name}' not found."
                )
            
            library_id = matched_lib.get('id')
            schema = await repository.get_library_schema(library_id, site_id=site_id)
            
            columns = schema.get('columns', [])
            reply = f"📋 Schema for **{operation.library_name}**:\n\n"
            reply += f"**Columns** ({len(columns)}):\n"
            for col in columns[:15]:  # Limit to 15 columns
                col_name = col.get('name', 'Unknown')
                col_type = col.get('type', 'Unknown')
                reply += f"- **{col_name}** ({col_type})\n"
            
            if len(columns) > 15:
                reply += f"\n... and {len(columns) - 15} more columns."
            
            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary={**schema, "library_name": operation.library_name, "site_id": site_id}
            )
        
        # ── ADD COLUMN OPERATION ────────────────────────────
        elif operation.operation == "add_column":
            if not operation.library_name or not operation.column_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both library name and column name.\n\n"
                           "Example: 'Add a Status column to the Project Files library'"
                )
            
            libraries = await repository.get_all_document_libraries(site_id=_lib_site_id)
            matched_lib = next(
                (lib for lib in libraries if operation.library_name.lower() in lib.get('displayName', '').lower()),
                None
            )
            
            if not matched_lib:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Library '{operation.library_name}' not found."
                )
            
            from src.domain.entities.core import SPColumn
            
            # Create column entity
            new_column = SPColumn(
                name=operation.column_name,
                type=operation.column_type or "text",
                required=False
            )
            
            library_id = matched_lib.get('id')
            await repository.add_column_to_list(library_id, new_column, site_id=site_id)
            
            return ChatResponse(
                intent="chat",
                reply=f"✅ Column **{operation.column_name}** added to library **{operation.library_name}**!"
            )
        
        # ── UNSUPPORTED OPERATION ───────────────────────────
        else:
            return ChatResponse(
                intent="chat",
                reply=f"⚠️ Operation '{operation.operation}' is not yet fully implemented.\n\n"
                       f"Supported operations: create, list, get, delete, get_schema, add_column"
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
        return error_response(logger, "chat", "An error occurred with the library operation: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
