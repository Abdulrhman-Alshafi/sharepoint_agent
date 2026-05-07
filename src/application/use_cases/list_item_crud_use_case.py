"""Use case for SharePoint list item CRUD operations — basic and validated."""

from typing import Dict, Any, List, Optional
from src.domain.repositories import IListRepository
from src.domain.entities.core import SPPermissionMask
from src.domain.exceptions import SharePointProvisioningException, PermissionDeniedException
from src.infrastructure.services.field_validator import FieldValidator, FieldValidationError
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ListItemCRUDUseCase:
    """Handle basic and validated CRUD operations on SharePoint list items."""

    def __init__(self, repository: IListRepository):
        self.repository = repository

    # ── Basic CRUD ───────────────────────────────────────────────────────────

    async def create_item(
        self,
        list_id: str,
        item_data: Dict[str, Any],
        site_id: Optional[str] = None,
        user_login: str = "",
    ) -> Dict[str, Any]:
        """Create a new item in a SharePoint list."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to create list items.")
        has_perms = await self.repository.check_user_permission(user_login, SPPermissionMask.ADD_LIST_ITEMS)
        if not has_perms:
            raise PermissionDeniedException(f"User '{user_login}' does not have permission to add items to this list.")
        try:
            return await self.repository.create_list_item(list_id, item_data, site_id)
        except PermissionDeniedException:
            raise
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to create list item: {e}")

    async def update_item(
        self,
        list_id: str,
        item_id: str,
        item_data: Dict[str, Any],
        site_id: Optional[str] = None,
        user_login: str = "",
    ) -> Dict[str, Any]:
        """Update an existing item in a SharePoint list."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to update list items.")
        has_perms = await self.repository.check_user_permission(user_login, SPPermissionMask.EDIT_LIST_ITEMS)
        if not has_perms:
            raise PermissionDeniedException(f"User '{user_login}' does not have permission to edit items in this list.")
        try:
            return await self.repository.update_list_item(list_id, item_id, item_data, site_id)
        except PermissionDeniedException:
            raise
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to update list item: {e}")

    async def delete_item(
        self,
        list_id: str,
        item_id: str,
        site_id: Optional[str] = None,
        user_login: str = "",
    ) -> bool:
        """Delete an item from a SharePoint list. Returns True on success."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to delete list items.")
        has_perms = await self.repository.check_user_permission(user_login, SPPermissionMask.DELETE_LIST_ITEMS)
        if not has_perms:
            raise PermissionDeniedException(f"User '{user_login}' does not have permission to delete items from this list.")
        try:
            return await self.repository.delete_list_item(list_id, item_id, site_id)
        except PermissionDeniedException:
            raise
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to delete list item: {e}")

    async def query_items(
        self,
        list_id: str,
        filter_query: Optional[str] = None,
        site_id: Optional[str] = None,
        user_login: str = "",
    ) -> List[Dict[str, Any]]:
        """Query items from a SharePoint list with optional OData $filter."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to read list items.")
        has_perms = await self.repository.check_user_permission(user_login, SPPermissionMask.VIEW_LIST_ITEMS)
        if not has_perms:
            raise PermissionDeniedException(f"User '{user_login}' does not have permission to view items in this list.")
        try:
            return await self.repository.query_list_items(list_id, filter_query, site_id)
        except PermissionDeniedException:
            raise
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to query list items: {e}")

    async def find_item_by_field(
        self,
        list_id: str,
        field_name: str,
        field_value: Any,
        site_id: Optional[str] = None,
        user_login: str = "",
    ) -> Optional[Dict[str, Any]]:
        """Return the first item whose *field_name* matches *field_value*, or None."""
        if not user_login:
            raise PermissionDeniedException("No user identity provided. Authentication is required to read list items.")
        has_perms = await self.repository.check_user_permission(user_login, SPPermissionMask.VIEW_LIST_ITEMS)
        if not has_perms:
            raise PermissionDeniedException(f"User '{user_login}' does not have permission to view items in this list.")
        _ALLOWED_FIELD_NAMES = {
            "Title", "Id", "Status", "AssignedTo", "Priority", "DueDate",
            "Description", "Name", "Email", "Category", "Department",
        }
        try:
            if isinstance(field_value, str):
                if field_name not in _ALLOWED_FIELD_NAMES:
                    raise ValueError(f"Field '{field_name}' is not queryable")
                safe_value = field_value.replace("'", "''")
                filter_query = f"{field_name} eq '{safe_value}'"
            elif isinstance(field_value, bool):
                filter_query = f"{field_name} eq {str(field_value).lower()}"
            else:
                filter_query = f"{field_name} eq {field_value}"
            items = await self.repository.query_list_items(list_id, filter_query, site_id)
            return items[0] if items else None
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to find item: {e}")

    # ── Validated CRUD ───────────────────────────────────────────────────────

    async def validate_item_data(
        self,
        list_id: str,
        item_data: Dict[str, Any],
        is_update: bool = False,
        site_id: Optional[str] = None,
    ) -> List[str]:
        """Validate item data against the list schema.

        Returns a list of warning strings.  Raises ``FieldValidationError``
        if validation fails.
        """
        try:
            list_schema = await self.repository.get_list_schema(list_id, site_id)
            return FieldValidator.validate_item_data(item_data, list_schema, is_update)
        except FieldValidationError:
            raise
        except Exception as e:
            raise SharePointProvisioningException(f"Failed to validate item data: {e}")

    async def create_item_validated(
        self,
        list_id: str,
        item_data: Dict[str, Any],
        site_id: Optional[str] = None,
        user_login: str = "",
    ) -> Dict[str, Any]:
        """Create an item after automatic field validation."""
        warnings = await self.validate_item_data(list_id, item_data, is_update=False, site_id=site_id)
        result = await self.create_item(list_id, item_data, site_id, user_login=user_login)
        if warnings:
            result["validation_warnings"] = warnings
        return result

    async def update_item_validated(
        self,
        list_id: str,
        item_id: str,
        item_data: Dict[str, Any],
        site_id: Optional[str] = None,
        user_login: str = "",
    ) -> Dict[str, Any]:
        """Update an item after automatic field validation."""
        warnings = await self.validate_item_data(list_id, item_data, is_update=True, site_id=site_id)
        result = await self.update_item(list_id, item_id, item_data, site_id, user_login=user_login)
        if warnings:
            result["validation_warnings"] = warnings
        return result
