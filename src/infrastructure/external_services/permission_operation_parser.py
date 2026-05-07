"""AI service for parsing permission management operation requests."""

import logging
from typing import Optional, Literal, List
from pydantic import BaseModel, Field
from src.infrastructure.external_services.ai_client_factory import get_instructor_client

logger = logging.getLogger(__name__)


class PermissionOperation(BaseModel):
    """Structured representation of a permission operation."""
    operation: Literal["grant", "revoke", "check", "list_groups", "create_group", "list_permissions"] = Field(
        description="Type of operation: grant, revoke, check, list_groups, create_group, list_permissions"
    )
    user_email: Optional[str] = Field(
        default=None,
        description="Email address of the user"
    )
    group_name: Optional[str] = Field(
        default=None,
        description="Name of the SharePoint group"
    )
    resource_name: Optional[str] = Field(
        default=None,
        description="Name of the list/library/site to manage permissions for"
    )
    permission_level: Optional[Literal["read", "contribute", "edit", "full_control", "owner"]] = Field(
        default=None,
        description="Permission level to grant: read, contribute, edit, full_control, or owner"
    )
    resource_type: Optional[Literal["list", "library", "site"]] = Field(
        default="site",
        description="Type of resource: list, library, or site"
    )


class PermissionOperationParserService:
    """Parse natural language requests for permission operations using AI."""

    PERMISSION_OPERATION_PROMPT = (
        "You are a SharePoint permission management parser. Extract structured information from user requests "
        "to grant permissions, check access, create groups, or manage SharePoint security.\n\n"
        "Operation types:\n"
        "- 'grant': Grant permissions to a user or group\n"
        "- 'revoke': Revoke/remove permissions from a user or group\n"
        "- 'check': Check what permissions a user has\n"
        "- 'list_groups': List all SharePoint groups\n"
        "- 'create_group': Create a new SharePoint group\n"
        "- 'list_permissions': List all permissions for a resource\n\n"
        "Permission levels:\n"
        "- 'read': Can view items\n"
        "- 'contribute': Can add, edit own items\n"
        "- 'edit': Can add, edit, delete all items\n"
        "- 'full_control': Full control\n"
        "- 'owner': Site owner\n\n"
        "Extract:\n"
        "1. The operation type\n"
        "2. User email if applicable\n"
        "3. Group name if applicable\n"
        "4. Resource name (list/library/site name)\n"
        "5. Permission level\n"
        "6. Resource type (list, library, or site)\n\n"
        "Examples:\n"
        "- 'Grant john@company.com edit access to the Documents library'\n"
        "  → operation='grant', user_email='john@company.com', resource_name='Documents', permission_level='edit', resource_type='library'\n"
        "- 'Check what permissions sarah@company.com has'\n"
        "  → operation='check', user_email='sarah@company.com'\n"
        "- 'Show me all SharePoint groups'\n"
        "  → operation='list_groups'\n"
        "- 'Create a group called Finance Team'\n"
        "  → operation='create_group', group_name='Finance Team'\n"
        "- 'Remove mike@company.com from the HR Documents library'\n"
        "  → operation='revoke', user_email='mike@company.com', resource_name='HR Documents', resource_type='library'\n"
        "- 'Who has access to the Project Files library?'\n"
        "  → operation='list_permissions', resource_name='Project Files', resource_type='library'\n"
    )

    @staticmethod
    async def parse_permission_operation(message: str) -> Optional[PermissionOperation]:
        """Parse a natural language message into a structured permission operation.
        
        Args:
            message: User's natural language request
            
        Returns:
            PermissionOperation object or None if parsing fails
        """
        try:
            client, model = get_instructor_client()
            
            response = client.chat.completions.create(
                model=model,
                response_model=PermissionOperation,
                messages=[
                    {
                        "role": "system",
                        "content": PermissionOperationParserService.PERMISSION_OPERATION_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Parse this request: {message}"
                    }
                ],
                temperature=0.1,
                max_retries=2
            )
            
            return response
        except Exception as e:
            logger.error(f"Error parsing permission operation: {e}")
            return None

    @staticmethod
    async def detect_permission_operation_intent(message: str) -> bool:
        """Detect if a message is requesting a permission operation.
        
        Args:
            message: User's message
            
        Returns:
            True if permission operation intent detected
        """
        permission_keywords = [
            "grant access", "give access", "grant permission", "give permission",
            "remove access", "revoke access", "revoke permission",
            "check permission", "check access", "what permission", "what access",
            "who has access", "list permissions", "show permissions",
            "create group", "new group", "add group",
            "show groups", "list groups", "sharepoint group",
            "read access", "edit access", "full control", "owner access",
            "contribute access", "can edit", "can view"
        ]
        return any(kw in message.lower() for kw in permission_keywords)
