"""Handler for SharePoint file operations."""

from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response
from src.domain.exceptions import PermissionDeniedException, AuthenticationException

logger = get_logger(__name__)

_PERMISSION_DENIED_REPLY = (
    "\ud83d\udd12 **Access Denied** \u2014 You don't have permission to access this resource. "
    "Please contact your SharePoint administrator if you believe this is an error."
)


async def handle_file_operations(message: str, session_id: str, site_id: str, user_token: str = None, user_login_name: str = "", last_created: tuple = None) -> ChatResponse:
    """Handle file operations (upload, download, copy, move, delete)."""
    from src.presentation.api import get_drive_repository, get_site_repository, get_list_repository, get_page_repository, get_library_repository, get_permission_repository, get_enterprise_repository
    from src.infrastructure.external_services.file_operation_parser import FileOperationParserService
    from src.application.use_cases.file_operations_use_case import FileOperationsUseCase
    from src.infrastructure.services.document_parser import DocumentParserService
    from src.infrastructure.services.document_index import DocumentIndexService
    from src.infrastructure.external_services.document_intelligence import DocumentIntelligenceService
    
    try:
        # Use OBO (per-user) repository when token is present
        site_repository = get_site_repository(user_token=user_token)
        list_repository = get_list_repository(user_token=user_token)
        page_repository = get_page_repository(user_token=user_token)
        library_repository = get_library_repository(user_token=user_token)
        drive_repository = get_drive_repository(user_token=user_token)
        permission_repository = get_permission_repository(user_token=user_token)
        enterprise_repository = get_enterprise_repository(user_token=user_token)
        parser_service = DocumentParserService()
        index_service = DocumentIndexService()
        intelligence_service = DocumentIntelligenceService()
        file_operations = FileOperationsUseCase(repository, parser_service, index_service, intelligence_service)
        
        # Prefer the site where the library was created (from last_created[2]) over the request site
        _file_site_id = (last_created[2] if (last_created and len(last_created) > 2 and last_created[2]) else None) or site_id
        
        # Parse the operation using AI
        operation = await FileOperationParserService.parse_file_operation(message)
        
        if not operation:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the file operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Download report.pdf from Documents'\n"
                       "- 'Copy invoice.pdf from Archives to Current Documents'\n"
                       "- 'Move contract.docx to the Legal library'\n"
                       "- 'Delete old_report.pdf from Documents'\n\n"
                       "Note: File upload via chat is not yet supported. Use the file upload API endpoint."
            )
        
        # Find the library by name
        all_libraries = await library_repository.get_all_document_libraries(site_id=_file_site_id)
        source_library = None
        dest_library = None
        
        if operation.library_name:
            for lib in all_libraries:
                lib_name = lib.get("displayName", "").lower()
                if operation.library_name.lower() in lib_name or lib_name in operation.library_name.lower():
                    source_library = lib
                    break
        
        if getattr(operation, "destination_library_name", None):
            for lib in all_libraries:
                lib_name = lib.get("displayName", "").lower()
                dest_name = operation.destination_library_name.lower()
                if dest_name in lib_name or lib_name in dest_name:
                    dest_library = lib
                    break
        
        # ── UPLOAD OPERATION ────────────────────────────────
        if operation.operation == "upload":
            return ChatResponse(
                intent="chat",
                reply="⚠️ File upload via chat is not yet supported.\n\n"
                       "Please use the file upload API endpoint:\n"
                       "`POST /api/v1/files/upload`\n\n"
                       "Or upload files directly through the SharePoint interface."
            )
        
        # ── DOWNLOAD OPERATION ──────────────────────────────
        elif operation.operation == "download":
            if not source_library or not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the file name and the library name.\n\n"
                           "Example: 'Download report.pdf from Documents'"
                )
            
            library_id = source_library.get("id")
            
            # Find the file in the library
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'.\n\n"
                           f"Available files: {', '.join([f.get('name', 'Unknown')[:30] for f in files[:5]])}"
                )
            
            # Provide download information
            return ChatResponse(
                intent="chat",
                reply=f"✅ File found: **{target_file.get('name')}**\n\n"
                       f"📁 Library: {source_library.get('displayName')}\n"
                       f"📦 Size: {target_file.get('size_mb', 'Unknown')} MB\n"
                       f"🔗 Web URL: {target_file.get('web_url', 'N/A')}\n\n"
                       f"To download, use the file download API endpoint:\n"
                       f"`GET /api/v1/files/download?file_id={target_file.get('file_id')}&drive_id={target_file.get('drive_id')}`",
                data_summary=target_file
            )
        
        # ── COPY OPERATION ──────────────────────────────────
        elif operation.operation == "copy":
            if not source_library or not dest_library or not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the file name, source library, and destination library.\n\n"
                           "Example: 'Copy invoice.pdf from Archives to Current Documents'"
                )
            
            library_id = source_library.get("id")
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            # Copy the file
            result = await drive_repository.copy_file(
                source_drive_id=target_file.get('drive_id'),
                source_file_id=target_file.get('file_id'),
                destination_drive_id=dest_library.get('id'),
                destination_folder_path=operation.folder_path,
                new_name=operation.new_name
            )
            
            return ChatResponse(
                intent="chat",
                reply=f"✅ Successfully copied **{operation.file_name}** from "
                       f"**{source_library.get('displayName')}** to **{dest_library.get('displayName')}**!",
                data_summary=result
            )
        
        # ── MOVE OPERATION ──────────────────────────────────
        elif operation.operation == "move":
            if not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which file to move."
                )
            
            # Need source library if not specified in context
            if not source_library and not dest_library:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the source library or destination library.\n\n"
                           "Example: 'Move contract.docx from Documents to Legal'"
                )
            
            # Find the file
            if source_library:
                library_id = source_library.get("id")
                files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
                target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
                
                if not target_file:
                    return ChatResponse(
                        intent="chat",
                        reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                    )
                
                # Move the file
                result = await drive_repository.move_file(
                    drive_id=target_file.get('drive_id'),
                    file_id=target_file.get('file_id'),
                    destination_folder_id=dest_library.get('id') if dest_library else None,
                    new_name=operation.new_name
                )
                
                dest_name = dest_library.get('displayName') if dest_library else 'another location'
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully moved **{operation.file_name}** to **{dest_name}**!",
                    data_summary=result
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the source library where the file is currently located."
                )
        
        # ── DELETE OPERATION ────────────────────────────────
        elif operation.operation == "delete":
            if not source_library or not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the file name and the library name.\n\n"
                           "Example: 'Delete old_report.pdf from Documents'"
                )
            
            library_id = source_library.get("id")
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            # Delete the file
            success = await file_operations.delete_file(
                file_id=target_file.get('file_id'),
                drive_id=target_file.get('drive_id'),
                remove_from_index=True,
                user_login=user_login_name
            )
            
            if success:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully deleted **{operation.file_name}** from **{source_library.get('displayName')}**.",
                    session_id=session_id
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to delete **{operation.file_name}**. Please try again.",
                    session_id=session_id
                )
        
        # ── GET FILE VERSIONS ───────────────────────────────
        elif operation.operation == "get_versions":
            if not source_library or not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the file name and the library name.\n\n"
                           "Example: 'Show me the version history of contract.docx in Legal'"
                )
            
            library_id = source_library.get("id")
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            # Get file versions from drive service
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            versions = await drive_service.get_file_versions(
                drive_id=target_file.get('drive_id'),
                file_id=target_file.get('file_id')
            )
            
            if not versions:
                return ChatResponse(
                    intent="chat",
                    reply=f"📋 **{operation.file_name}** has no previous versions (current version only)."
                )
            
            versions_text = f"📋 **Version History for {operation.file_name}**\n\n"
            for idx, version in enumerate(versions[:10], 1):  # Show last 10 versions
                version_id = version.get('id', 'Unknown')
                last_modified = version.get('lastModified', {}).get('dateTime', 'Unknown')
                modified_by = version.get('lastModified', {}).get('user', {}).get('displayName', 'Unknown')
                size = version.get('size', 0) / (1024*1024)  # Convert to MB
                versions_text += f"{idx}. Version `{version_id}` - Modified {last_modified} by {modified_by} ({size:.2f} MB)\n"
            
            versions_text += f"\n💡 To restore a version, say: \"Restore {operation.file_name} to version {{version_id}}\""
            
            return ChatResponse(
                intent="chat",
                reply=versions_text,
                data_summary={"versions": versions, "count": len(versions)}
            )
        
        # ── RESTORE FILE VERSION ────────────────────────────
        elif operation.operation == "restore_version":
            if not source_library or not operation.file_name or not operation.version_id:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the file name, library, and version ID.\n\n"
                           "Example: 'Restore contract.docx in Legal to version 3.0'"
                )
            
            library_id = source_library.get("id")
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            success = await drive_service.restore_file_version(
                drive_id=target_file.get('drive_id'),
                file_id=target_file.get('file_id'),
                version_id=operation.version_id
            )
            
            if success:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully restored **{operation.file_name}** to version `{operation.version_id}`!"
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to restore **{operation.file_name}** to version `{operation.version_id}`."
                )
        
        # ── CHECKOUT FILE ───────────────────────────────────
        elif operation.operation == "checkout":
            if not source_library or not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the file name and the library name.\n\n"
                           "Example: 'Check out proposal.docx from Shared Documents'"
                )
            
            library_id = source_library.get("id")
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            success = await drive_service.checkout_file(
                drive_id=target_file.get('drive_id'),
                file_id=target_file.get('file_id')
            )
            
            if success:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully checked out **{operation.file_name}** for editing.\n\n"
                           f"📝 The file is now locked and only you can edit it.\n"
                           f"💡 Remember to check it back in when you're done: \"Check in {operation.file_name}\""
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to check out **{operation.file_name}**. It may already be checked out by another user."
                )
        
        # ── CHECKIN FILE ────────────────────────────────────
        elif operation.operation == "checkin":
            if not source_library or not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the file name and the library name.\n\n"
                           "Example: 'Check in report.docx with comment Updated Q4 data'"
                )
            
            library_id = source_library.get("id")
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            comment = operation.checkin_comment or "Checked in via AI Agent"
            success = await drive_service.checkin_file(
                drive_id=target_file.get('drive_id'),
                file_id=target_file.get('file_id'),
                comment=comment
            )
            
            if success:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully checked in **{operation.file_name}**!\n\n"
                           f"💬 Comment: \"{comment}\"\n"
                           f"📖 The file is now available for others to edit."
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to check in **{operation.file_name}**."
                )
        
        # ── CREATE FOLDER ───────────────────────────────────
        elif operation.operation == "create_folder":
            if not source_library or not operation.folder_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the folder name and the library name.\n\n"
                           "Example: 'Create a folder called Q4 Reports in Documents'"
                )
            
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            library_id = source_library.get("id")
            result = await drive_service.create_folder(
                drive_id=library_id,
                folder_name=operation.folder_name,
                parent_folder_path=operation.folder_path or "/"
            )
            
            if result:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully created folder **{operation.folder_name}** in **{source_library.get('displayName')}**!",
                    data_summary=result
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to create folder **{operation.folder_name}**."
                )
        
        # ── DELETE FOLDER ───────────────────────────────────
        elif operation.operation == "delete_folder":
            if not source_library or not operation.folder_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the folder name and the library name.\n\n"
                           "Example: 'Delete the Old Reports folder from Documents'"
                )
            
            # Find the folder first
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            library_id = source_library.get("id")
            folder_contents = await drive_service.get_folder_contents(
                drive_id=library_id,
                folder_path=operation.folder_path or "/"
            )
            
            target_folder = None
            for item in folder_contents:
                if item.get('folder') and item.get('name', '').lower() == operation.folder_name.lower():
                    target_folder = item
                    break
            
            if not target_folder:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Folder '{operation.folder_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            success = await drive_service.delete_folder(
                drive_id=library_id,
                folder_id=target_folder.get('id')
            )
            
            if success:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully deleted folder **{operation.folder_name}** from **{source_library.get('displayName')}**."
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to delete folder **{operation.folder_name}**."
                )
        
        # ── LIST FOLDER CONTENTS ────────────────────────────
        elif operation.operation == "list_folder":
            if not source_library:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the library name.\n\n"
                           "Example: 'Show me the files in the Reports folder in Documents'"
                )
            
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            library_id = source_library.get("id")
            folder_path = operation.folder_path or operation.folder_name or "/"
            
            contents = await drive_service.get_folder_contents(
                drive_id=library_id,
                folder_path=folder_path
            )
            
            if not contents:
                return ChatResponse(
                    intent="chat",
                    reply=f"📁 The folder is empty or doesn't exist in **{source_library.get('displayName')}**."
                )
            
            # Separate folders and files
            folders = [item for item in contents if item.get('folder')]
            files = [item for item in contents if not item.get('folder')]
            
            reply_text = f"📁 **Contents of {folder_path}** in **{source_library.get('displayName')}**\n\n"
            
            if folders:
                reply_text += "**Folders:**\n"
                for folder in folders[:20]:
                    reply_text += f"📂 {folder.get('name', 'Unknown')}\n"
            
            if files:
                reply_text += f"\n**Files ({len(files)} total):**\n"
                for file in files[:20]:
                    size_mb = file.get('size', 0) / (1024*1024)
                    reply_text += f"📄 {file.get('name', 'Unknown')} ({size_mb:.2f} MB)\n"
            
            if len(contents) > 20:
                reply_text += f"\n_...and {len(contents) - 20} more items_"
            
            return ChatResponse(
                intent="chat",
                reply=reply_text,
                data_summary=contents
            )
        
        # ── CREATE SHARE LINK ───────────────────────────────
        elif operation.operation == "create_share_link":
            if not source_library or not operation.file_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify both the file name and the library name.\n\n"
                           "Example: 'Create a view link for budget.xlsx in Finance'"
                )
            
            library_id = source_library.get("id")
            files = await file_operations.get_library_files(library_id, include_indexed_info=False, user_login=user_login_name)
            target_file = next((f for f in files if f.get('name', '').lower() == operation.file_name.lower()), None)
            
            if not target_file:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ File '{operation.file_name}' not found in library '{source_library.get('displayName')}'."
                )
            
            from src.infrastructure.services.sharepoint.drive_service import DriveService
            graph_client = getattr(repository, 'graph_client', None)
            rest_client = getattr(repository, 'rest_client', None)
            
            
            drive_service = DriveService(graph_client, rest_client) if graph_client and rest_client else DriveService(None, None)
            
            share_type = operation.share_type or "view"
            result = await drive_service.create_file_share_link(
                drive_id=target_file.get('drive_id'),
                file_id=target_file.get('file_id'),
                link_type=share_type,
                scope="anonymous"  # or "organization" depending on requirements
            )
            
            if result and 'link' in result:
                link_url = result['link'].get('webUrl', 'N/A')
                permission_icon = "👁️" if share_type == "view" else "✏️"
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully created {share_type} link for **{operation.file_name}**!\n\n"
                           f"{permission_icon} Link: {link_url}\n\n"
                           f"🔗 Anyone with this link can {share_type} the file.",
                    data_summary=result
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to create sharing link for **{operation.file_name}**."
                )
        
        else:
            return ChatResponse(
                intent="chat",
                reply=f"Unknown file operation: {operation.operation}"
            )
    
    except PermissionDeniedException:
        from src.presentation.api.orchestrators.orchestrator_utils import permission_denied_response
        return permission_denied_response()
    except AuthenticationException:
        from src.presentation.api.orchestrators.orchestrator_utils import auth_expired_response
        return auth_expired_response()
    except Exception as e:
        from src.domain.exceptions import DomainException
        from src.presentation.api.orchestrators.orchestrator_utils import domain_error_response
        if isinstance(e, DomainException):
            return domain_error_response(e, intent="chat")
        return error_response(logger, "chat", "Sorry, I couldn't complete that file operation: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
