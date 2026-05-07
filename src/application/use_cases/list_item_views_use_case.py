"""Use case for list item attachments and custom views."""

from typing import Dict, Any, List, Optional
from src.domain.repositories import IListRepository
from src.domain.exceptions import SharePointProvisioningException
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ListItemViewsUseCase:
    """Handle item attachments and custom list views."""

    def __init__(self, repository: IListRepository):
        self.repository = repository

    # ── Attachments ──────────────────────────────────────────────────────────

    async def add_attachment(
        self,
        list_id: str,
        item_id: str,
        file_name: str,
        file_content: bytes,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add an attachment to a list item. Returns attachment metadata."""
        try:
            return await self.repository.add_item_attachment(
                list_id, item_id, file_name, file_content, site_id
            )
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to add attachment: {e}")

    async def get_attachments(
        self,
        list_id: str,
        item_id: str,
        site_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all attachments for a list item."""
        try:
            return await self.repository.get_item_attachments(list_id, item_id, site_id)
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to get attachments: {e}")

    async def delete_attachment(
        self,
        list_id: str,
        item_id: str,
        attachment_id: str,
        site_id: Optional[str] = None,
    ) -> bool:
        """Delete an attachment from a list item. Returns True on success."""
        try:
            return await self.repository.delete_item_attachment(
                list_id, item_id, attachment_id, site_id
            )
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to delete attachment: {e}")

    # ── Views ────────────────────────────────────────────────────────────────

    async def create_view(
        self,
        list_id: str,
        view_name: str,
        view_fields: List[str],
        view_query: Optional[str] = None,
        is_default: bool = False,
        site_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a custom view for a list. Returns view metadata."""
        try:
            return await self.repository.create_list_view(
                list_id, view_name, view_fields, view_query, is_default, site_id
            )
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to create view: {e}")

    async def get_views(
        self,
        list_id: str,
        site_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return all views for a list."""
        try:
            return await self.repository.get_list_views(list_id, site_id)
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to get views: {e}")

    async def delete_view(
        self,
        list_id: str,
        view_id: str,
        site_id: Optional[str] = None,
    ) -> bool:
        """Delete a custom view from a list. Returns True on success."""
        try:
            return await self.repository.delete_list_view(list_id, view_id, site_id)
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to delete view: {e}")
