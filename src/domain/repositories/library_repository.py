"""Library repository interfaces — split by concern (ISP).

Three focused ABCs are defined here and then combined into the backwards-
compatible ``ILibraryRepository`` union interface::

    ILibraryCRUDRepository       — create / read / update / delete libraries,
                                   schema management, seeding.
    ILibraryFileRepository       — file & folder upload/download/copy/move.
    ILibraryVersioningRepository — versioning, checkout / check-in.

    ILibraryRepository           — union of all three (backwards compat).
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from src.domain.entities import DocumentLibrary
from src.domain.entities.document import LibraryItem


# ══════════════════════════════════════════════════════════════════════════════
# 1. Library CRUD + schema
# ══════════════════════════════════════════════════════════════════════════════

class ILibraryCRUDRepository(ABC):
    """Create, read, update, delete document libraries; manage columns/schema."""

    @abstractmethod
    async def create_document_library(
        self,
        library: DocumentLibrary,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a document library in SharePoint.

        Args:
            library: DocumentLibrary entity to create.
            site_id: Optional site ID override.

        Returns:
            Created library metadata dict.
        """

    @abstractmethod
    async def get_all_document_libraries(
        self, site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return all document libraries on the SharePoint site."""

    @abstractmethod
    async def search_libraries(
        self, query: str, site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Search for document libraries by display name."""

    @abstractmethod
    async def update_document_library(
        self,
        library_id: str,
        metadata: Dict[str, Any],
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update document library settings and metadata."""

    @abstractmethod
    async def delete_document_library(
        self, library_id: str, site_id: Optional[str] = None
    ) -> bool:
        """Delete a document library. Returns True on success."""

    @abstractmethod
    async def seed_list_data(
        self,
        list_id: str,
        seed_data: List[Dict[str, Any]],
    ) -> bool:
        """Seed a document library (list) with initial data items."""

    @abstractmethod
    async def get_library_schema(
        self, library_id: str, site_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get library schema including all columns."""

    @abstractmethod
    async def add_library_column(
        self,
        library_id: str,
        column_name: str,
        column_type: str,
        required: bool = False,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a column to a document library."""


# ══════════════════════════════════════════════════════════════════════════════
# 2. File & folder operations
# ══════════════════════════════════════════════════════════════════════════════

class ILibraryFileRepository(ABC):
    """Upload, download, copy, move files; manage folders."""

    # ── File operations ──────────────────────────────────────

    @abstractmethod
    async def get_library_items(
        self, library_id: str, site_id: Optional[str] = None
    ) -> List[LibraryItem]:
        """Return all files from a document library."""

    @abstractmethod
    async def upload_file(
        self,
        library_id: str,
        file_name: str,
        file_content: bytes,
        metadata: Optional[Dict[str, Any]] = None,
        site_id: Optional[str] = None,
    ) -> LibraryItem:
        """Upload a file to a document library."""

    @abstractmethod
    async def download_file(
        self, library_id: str, file_id: str, site_id: Optional[str] = None
    ) -> bytes:
        """Download a file from a document library. Returns raw bytes."""

    @abstractmethod
    async def update_file_metadata(
        self,
        library_id: str,
        file_id: str,
        metadata: Dict[str, Any],
        site_id: Optional[str] = None,
    ) -> LibraryItem:
        """Update metadata of a file. Returns updated LibraryItem."""

    @abstractmethod
    async def delete_file(
        self, file_id: str, drive_id: str, site_id: Optional[str] = None
    ) -> bool:
        """Delete a file from a library. Returns True on success."""

    @abstractmethod
    async def copy_file(
        self,
        source_library_id: str,
        source_file_id: str,
        destination_library_id: str,
        new_file_name: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> LibraryItem:
        """Copy a file to another library (or within the same library)."""

    @abstractmethod
    async def move_file(
        self,
        source_library_id: str,
        source_file_id: str,
        destination_library_id: str,
        new_file_name: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> LibraryItem:
        """Move a file to another library."""

    # ── Folder operations ────────────────────────────────────

    @abstractmethod
    async def create_folder(
        self,
        library_id: str,
        folder_name: str,
        parent_folder_path: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a folder in a library. Returns folder metadata."""

    @abstractmethod
    async def get_folder_contents(
        self,
        library_id: str,
        folder_path: str,
        site_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return contents of a folder (files and sub-folders)."""

    @abstractmethod
    async def delete_folder(
        self, library_id: str, folder_path: str, site_id: Optional[str] = None
    ) -> bool:
        """Delete a folder and all its contents. Returns True on success."""


# ══════════════════════════════════════════════════════════════════════════════
# 3. Versioning, checkout / check-in
# ══════════════════════════════════════════════════════════════════════════════

class ILibraryVersioningRepository(ABC):
    """File versioning and checkout / check-in operations."""

    @abstractmethod
    async def get_file_versions(
        self, library_id: str, file_id: str, site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Return all versions of a file."""

    @abstractmethod
    async def restore_file_version(
        self,
        library_id: str,
        file_id: str,
        version_id: str,
        site_id: Optional[str] = None,
    ) -> LibraryItem:
        """Restore a specific file version. Returns restored LibraryItem."""

    @abstractmethod
    async def checkout_file(
        self, library_id: str, file_id: str, site_id: Optional[str] = None
    ) -> bool:
        """Check out a file for editing. Returns True on success."""

    @abstractmethod
    async def checkin_file(
        self,
        library_id: str,
        file_id: str,
        comment: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> bool:
        """Check in a file after editing. Returns True on success."""

    @abstractmethod
    async def discard_file_checkout(
        self, library_id: str, file_id: str, site_id: Optional[str] = None
    ) -> bool:
        """Discard file checkout without saving changes. Returns True on success."""


# ══════════════════════════════════════════════════════════════════════════════
# Combined backwards-compatible interface
# ══════════════════════════════════════════════════════════════════════════════

class ILibraryRepository(
    ILibraryCRUDRepository,
    ILibraryFileRepository,
    ILibraryVersioningRepository,
):
    """Full library repository interface (backwards-compatible union).

    Prefer injecting the narrower sub-interfaces where possible:
      - ``ILibraryCRUDRepository``       for provisioning use cases.
      - ``ILibraryFileRepository``       for file-operations use cases.
      - ``ILibraryVersioningRepository`` for versioning / checkout flows.
    """
