"""Domain repository interfaces.

This module provides focused repository interfaces following the Interface Segregation Principle.
The original SharePointRepository is now a composite interface for backward compatibility.
"""

from src.domain.repositories.list_repository import IListRepository
from src.domain.repositories.page_repository import IPageRepository
from src.domain.repositories.library_repository import (
    ILibraryRepository,
    ILibraryCRUDRepository,
    ILibraryFileRepository,
    ILibraryVersioningRepository,
)
from src.domain.repositories.site_repository import (
    ISiteRepository,
    ISiteCRUDRepository,
    ISiteMemberRepository,
    ISiteCustomizationRepository,
    ISiteAnalyticsRepository,
)
from src.domain.repositories.permission_repository import IPermissionRepository
from src.domain.repositories.enterprise_repository import IEnterpriseRepository



class SharePointRepository(
    IListRepository,
    IPageRepository,
    ILibraryRepository,
    ISiteRepository,
    IPermissionRepository,
    IEnterpriseRepository
):
    """
    Composite repository interface for SharePoint operations.
    
    This interface combines all focused repository interfaces for backward compatibility.
    New code should prefer using focused interfaces directly:
    - IListRepository: List and list item operations
    - IPageRepository: Page operations
    - ILibraryRepository: Document library and file operations
    - ISiteRepository: Site operations
    - IPermissionRepository: Permission and group operations
    - IEnterpriseRepository: Content types, term sets, and views
    """
    pass


# Export all interfaces
__all__ = [
    'SharePointRepository',
    'IListRepository',
    'IPageRepository',
    'ILibraryRepository',
    'ILibraryCRUDRepository',
    'ILibraryFileRepository',
    'ILibraryVersioningRepository',
    'ISiteRepository',
    'ISiteCRUDRepository',
    'ISiteMemberRepository',
    'ISiteCustomizationRepository',
    'ISiteAnalyticsRepository',
    'IPermissionRepository',
]
