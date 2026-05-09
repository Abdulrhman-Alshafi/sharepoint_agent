"""File operations use case for document library file management."""

from typing import List, Dict, Any, Optional
from src.domain.repositories import ILibraryRepository
from src.domain.entities.core import SPPermissionMask
from src.domain.entities.document import LibraryItem
from src.domain.exceptions import PermissionDeniedException
from src.infrastructure.services.document_parser import DocumentParserService
from src.infrastructure.services.document_index import DocumentIndexService
from src.infrastructure.external_services.document_intelligence import DocumentIntelligenceService


class FileOperationsUseCase:
    """Use case for file upload, download, delete, and metadata operations."""

    def __init__(
        self,
        drive_repository,
        permission_repository,
        document_parser: DocumentParserService,
        document_index: DocumentIndexService,
        document_intelligence: DocumentIntelligenceService
    ):
        self.drive_repository = drive_repository
        self.permission_repository = permission_repository
        self.document_parser = document_parser
        self.document_index = document_index
        self.document_intelligence = document_intelligence

    async def upload_file(
        self,
        library_id: str,
        file_name: str,
        file_content: bytes,
        metadata: Optional[Dict[str, Any]] = None,
        auto_parse: bool = True,
        auto_extract_entities: bool = True,
        user_login: str = "",
    ) -> Dict[str, Any]:
        """Upload a file to a document library with automatic parsing and indexing."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to upload files.")
        if self.permission_repository:
            has_perms = await self.permission_repository.check_user_permission(user_login, SPPermissionMask.ADD_LIST_ITEMS)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have permission to upload files to this library.")
        
        # Step 1: Upload file to SharePoint
        library_item = await self.drive_repository.upload_file(
            library_id,
            file_name,
            file_content,
            metadata
        )
        
        result = {
            "file_id": library_item.item_id,
            "file_name": library_item.name,
            "size": library_item.size,
            "library_id": library_id,
            "drive_id": library_item.drive_id,
            "web_url": library_item.web_url,
            "parsed": False,
            "indexed": False,
            "entities_extracted": False
        }
        
        # Step 2: Parse document if enabled and file is parseable
        if auto_parse and library_item.is_parseable:
            try:
                file_type = f".{library_item.file_type}" if library_item.file_type else ".unknown"
                parsed_doc = await self.document_parser.parse_document(
                    file_content, file_name, file_type
                )
                
                result["parsed"] = not bool(parsed_doc.error)
                result["parse_error"] = parsed_doc.error
                result["word_count"] = parsed_doc.word_count
                result["table_count"] = parsed_doc.table_count
                
                # Step 3: Extract entities if enabled
                if auto_extract_entities and parsed_doc.text and not parsed_doc.error:
                    try:
                        entities = await self.document_intelligence.extract_entities(parsed_doc)
                        parsed_doc.entities = entities.dict()
                        result["entities_extracted"] = True
                        result["entity_summary"] = {
                            "monetary_amounts": len(entities.monetary_amounts),
                            "people": len(entities.people),
                            "dates": len(entities.dates),
                            "categories": entities.categories
                        }
                    except Exception as e:
                        result["entity_extraction_error"] = str(e)
                
                # Step 4: Index the parsed document
                try:
                    indexed = await self.document_index.index_document(
                        library_item.item_id,
                        library_id,
                        library_item.drive_id,
                        parsed_doc,
                        file_content
                    )
                    result["indexed"] = indexed
                except Exception as e:
                    result["indexing_error"] = str(e)
                    
            except Exception as e:
                result["parse_error"] = str(e)
        
        return result

    async def get_library_files(
        self, library_id: str, include_indexed_info: bool = True, user_login: str = ""
    ) -> List[Dict[str, Any]]:
        """Get all files from a document library."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to list files.")
        if self.permission_repository:
            has_perms = await self.permission_repository.check_user_permission(user_login, SPPermissionMask.VIEW_LIST_ITEMS)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have permission to view files in this library.")
        
        items = await self.drive_repository.get_library_items(library_id)
        
        files = []
        for item in items:
            file_info = {
                "file_id": item.item_id,
                "name": item.name,
                "size": item.size,
                "size_mb": item.size_mb,
                "created": item.created_datetime.isoformat() if item.created_datetime else None,
                "modified": item.modified_datetime.isoformat() if item.modified_datetime else None,
                "created_by": item.created_by,
                "modified_by": item.modified_by,
                "web_url": item.web_url,
                "file_type": item.file_type,
                "is_parseable": item.is_parseable,
                "drive_id": item.drive_id
            }
            
            # Add indexed status if requested
            if include_indexed_info:
                indexed_doc = await self.document_index.get_indexed_document(item.item_id)
                file_info["indexed"] = bool(indexed_doc)
                if indexed_doc:
                    file_info["word_count"] = indexed_doc.get("word_count")
                    file_info["table_count"] = indexed_doc.get("table_count")
                    file_info["last_indexed"] = indexed_doc.get("last_indexed")
            
            files.append(file_info)
        
        return files

    async def download_file(self, file_id: str, drive_id: str, user_login: str = "") -> bytes:
        """Download file content."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to download files.")
        if self.permission_repository:
            has_perms = await self.permission_repository.check_user_permission(user_login, SPPermissionMask.VIEW_LIST_ITEMS)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have permission to download files from this library.")
        return await self.drive_repository.download_file(file_id, drive_id)

    async def delete_file(
        self, file_id: str, drive_id: str, remove_from_index: bool = True, user_login: str = ""
    ) -> bool:
        """Delete a file from a document library."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to delete files.")
        if self.permission_repository:
            has_perms = await self.permission_repository.check_user_permission(user_login, SPPermissionMask.ADD_LIST_ITEMS)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have permission to delete files from this library.")
        # Delete from SharePoint
        success = await self.drive_repository.delete_file(file_id, drive_id)
        
        # Remove from index if requested
        if success and remove_from_index:
            await self.document_index.delete_document(file_id)
        
        return success

    async def update_file_metadata(
        self, file_id: str, drive_id: str, metadata: Dict[str, Any], user_login: str = ""
    ) -> Dict[str, Any]:
        """Update file metadata."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to update file metadata.")
        if self.permission_repository:
            has_perms = await self.permission_repository.check_user_permission(user_login, SPPermissionMask.EDIT_LIST_ITEMS)
            if not has_perms:
                raise PermissionDeniedException(f"User '{user_login}' does not have permission to edit files in this library.")
        library_item = await self.drive_repository.update_file_metadata(
            file_id, drive_id, metadata
        )
        
        return {
            "file_id": library_item.item_id,
            "name": library_item.name,
            "size": library_item.size,
            "updated": True
        }

    async def reindex_file(self, file_id: str, drive_id: str, library_id: str) -> Dict[str, Any]:
        """Re-parse and re-index a file.
        
        Args:
            file_id: ID of the file
            drive_id: ID of the drive
            library_id: ID of the library
            
        Returns:
            Indexing result
        """
        # Download file
        file_content = await self.drive_repository.download_file(file_id, drive_id)
        
        # Get file info to determine type
        items = await self.drive_repository.get_library_items(library_id)
        file_item = next((item for item in items if item.item_id == file_id), None)
        
        if not file_item:
            return {"success": False, "error": "File not found"}
        
        # Parse document
        file_type = f".{file_item.file_type}" if file_item.file_type else ".unknown"
        parsed_doc = await self.document_parser.parse_document(
            file_content, file_item.name, file_type
        )
        
        # Extract entities
        if parsed_doc.text and not parsed_doc.error:
            entities = await self.document_intelligence.extract_entities(parsed_doc)
            parsed_doc.entities = entities.dict()
        
        # Index
        indexed = await self.document_index.index_document(
            file_id, library_id, drive_id, parsed_doc, file_content
        )
        
        return {
            "success": indexed,
            "word_count": parsed_doc.word_count,
            "table_count": parsed_doc.table_count,
            "error": parsed_doc.error
        }
