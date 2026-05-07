"""Library provisioner for SharePoint document libraries."""

from typing import List, Tuple, Dict, Any, Optional
from src.domain.entities import ProvisioningBlueprint, ActionType
from src.domain.repositories import ILibraryRepository
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class LibraryProvisioner:
    """Handles provisioning of SharePoint document libraries."""

    def __init__(self, repository: ILibraryRepository):
        """Initialize library provisioner.
        
        Args:
            repository: Library repository for document library operations
        """
        self.repository = repository

    async def provision(self, blueprint: ProvisioningBlueprint, site_id: Optional[str] = None) -> Tuple[List[Dict[str, Any]], Dict[str, str], List[str], List[str]]:
        """Provision all document libraries from the blueprint.
        
        Args:
            blueprint: Provisioning blueprint containing document libraries
            site_id: Optional SharePoint site ID to target
            
        Returns:
            Tuple of (created_libs, title_to_id_map, resource_links, warnings)
        """
        created_libs = []
        deleted_libs = []
        updated_count = 0
        deleted_count = 0
        lib_title_to_id = {}
        resource_links = []
        warnings = []

        for library in blueprint.document_libraries:
            try:
                if library.action == ActionType.CREATE:
                    result = await self.repository.create_document_library(library, site_id=site_id)
                    created_libs.append(result)
                    lib_id = result.get("id", "")
                    if lib_id:
                        lib_title_to_id[library.title] = lib_id
                    resource_links.append(result.get("resource_link", ""))

                    # Seed folders and files if provided
                    if library.seed_data and lib_id:
                        folder_entries = [
                            item for item in library.seed_data
                            if isinstance(item, dict) and item.get("type") in ("folder", "folder_path")
                        ]
                        list_item_entries = [
                            item for item in library.seed_data
                            if isinstance(item, dict) and item.get("type") not in ("folder", "folder_path")
                        ]

                        for folder_entry in folder_entries:
                            folder_name = folder_entry.get("name") or folder_entry.get("folder")
                            parent_path = folder_entry.get("parent_folder_path") or folder_entry.get("path")
                            if folder_name:
                                try:
                                    await self.repository.create_folder(
                                        lib_id, folder_name, parent_path
                                    )
                                    logger.info(
                                        "Created seed folder '%s' in library '%s'",
                                        folder_name, library.title,
                                    )
                                except Exception as folder_err:
                                    warning_msg = (
                                        f"Could not create seed folder '{folder_name}' "
                                        f"in library '{library.title}': {folder_err}"
                                    )
                                    logger.warning("%s", warning_msg)
                                    warnings.append(warning_msg)

                        if list_item_entries:
                            await self.repository.seed_list_data(lib_id, list_item_entries)
                
                elif library.action == ActionType.UPDATE:
                    # Update library metadata
                    if not library.library_id:
                        # Try to find by title if ID not provided
                        all_libs = await self.repository.get_all_document_libraries()
                        matched_lib = next(
                            (lib for lib in all_libs if lib.get('displayName') == library.title),
                            None
                        )
                        if matched_lib:
                            library.library_id = matched_lib.get('id')
                    
                    if library.library_id:
                        result = await self.repository.update_document_library(
                            library.library_id,
                            {
                                'title': library.title,
                                'description': library.description
                            }
                        )
                        updated_count += 1
                        resource_links.append(result.get("webUrl", ""))
                
                elif library.action == ActionType.DELETE:
                    # Delete library
                    if not library.library_id:
                        # Try to find by title if ID not provided
                        all_libs = await self.repository.get_all_document_libraries()
                        matched_lib = next(
                            (lib for lib in all_libs if lib.get('displayName') == library.title),
                            None
                        )
                        if matched_lib:
                            library.library_id = matched_lib.get('id')
                    
                    if library.library_id:
                        success = await self.repository.delete_document_library(
                            library.library_id
                        )
                        if success:
                            deleted_count += 1
                            deleted_libs.append({"displayName": library.title, "id": library.library_id})
                        
            except SharePointProvisioningException as e:
                warning_msg = f"Failed to provision library '{library.title}': {str(e)}"
                logger.warning("%s", warning_msg)
                warnings.append(warning_msg)
                continue

        # Return created libs
        logger.info("Library provisioning complete: %d created, %d updated, %d deleted", len(created_libs), updated_count, deleted_count)
        return created_libs, deleted_libs, lib_title_to_id, resource_links, warnings
