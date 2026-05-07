"""AI service for parsing site operation requests."""

from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class SiteOperation(BaseModel):
    """Structured representation of a site operation."""
    operation: Literal["create", "delete", "update_theme", "add_member", "add_owner",
                       "remove_member", "navigation", "recycle_bin", "empty_recycle_bin",
                       "restore_item", "get_storage", "get_analytics"] = Field(
        description="Type of site operation"
    )
    site_name: Optional[str] = Field(
        default=None,
        description="Name of the site to operate on"
    )
    site_title: Optional[str] = Field(
        default=None,
        description="Display title for the site (for create operations)"
    )
    site_description: Optional[str] = Field(
        default=None,
        description="Description of the site (for create operations)"
    )
    site_template: Optional[Literal["Team", "Communication"]] = Field(
        default="Team",
        description="Site template type (Team or Communication)"
    )
    user_email: Optional[str] = Field(
        default=None,
        description="Email of user to add/remove as member or owner"
    )
    theme_settings: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Theme settings for the site (colors, logo, etc.)"
    )
    navigation_type: Optional[Literal["top", "quick"]] = Field(
        default="top",
        description="Navigation type: 'top' for top navigation bar, 'quick' for quick launch"
    )
    navigation_items: Optional[List[Dict[str, str]]] = Field(
        default=None,
        description="List of navigation items with Title and Url"
    )
    recycle_bin_item_id: Optional[str] = Field(
        default=None,
        description="ID of item to restore from recycle bin"
    )


class SiteOperationParserService:
    """Parse natural language requests for site operations using AI."""

    SITE_OPERATION_PROMPT = (
        "You are a SharePoint site operation parser. Extract structured information from user requests "
        "to create, delete, update sites, manage members, navigation, and recycle bin.\n\n"
        "Operation types:\n"
        "- 'create': Creating a new SharePoint site\n"
        "- 'delete': Deleting a site\n"
        "- 'update_theme': Updating site theme/appearance\n"
        "- 'add_member': Adding a member to a site\n"
        "- 'add_owner': Adding an owner to a site\n"
        "- 'remove_member': Removing a user from site\n"
        "- 'navigation': Managing site navigation\n"
        "- 'recycle_bin': Viewing recycle bin items\n"
        "- 'empty_recycle_bin': Emptying the recycle bin\n"
        "- 'restore_item': Restoring an item from recycle bin\n"
        "- 'get_storage': Getting site storage information\n"
        "- 'get_analytics': Getting site analytics\n\n"
        "Extract:\n"
        "1. The operation type\n"
        "2. Site name/title\n"
        "3. For create: site description, template (Team or Communication)\n"
        "4. For member operations: user email\n"
        "5. For navigation: navigation_type ('top' or 'quick') and navigation_items\n"
        "6. For recycle bin: item_id if restoring specific item\n\n"
        "Examples:\n"
        "- 'Create a new team site called Marketing'\n"
        "  → operation='create', site_title='Marketing', site_template='Team'\n"
        "- 'Add john@company.com as a member of the HR site'\n"
        "  → operation='add_member', site_name='HR', user_email='john@company.com'\n"
        "- 'Add jane@company.com as owner of Marketing site'\n"
        "  → operation='add_owner', site_name='Marketing', user_email='jane@company.com'\n"
        "- 'Empty the recycle bin'\n"
        "  → operation='empty_recycle_bin'\n"
        "- 'Show recycle bin items'\n"
        "  → operation='recycle_bin'\n"
        "- 'Update top navigation with Home and About links'\n"
        "  → operation='navigation', navigation_type='top', navigation_items=[{'Title': 'Home', 'Url': '/'}, {'Title': 'About', 'Url': '/about'}]\n"
    )

    @staticmethod
    async def parse_site_operation(message: str) -> Optional[SiteOperation]:
        """Parse a natural language message into a structured site operation.
        
        Args:
            message: User's natural language request
            
        Returns:
            SiteOperation object or None if parsing fails
        """
        import inspect
        try:
            client, model = get_instructor_client()

            result = client.chat.completions.create(
                model=model,
                response_model=SiteOperation,
                messages=[
                    {
                        "role": "system",
                        "content": SiteOperationParserService.SITE_OPERATION_PROMPT
                    },
                    {
                        "role": "user",
                        "content": f"Parse this request: {message}"
                    }
                ],
                temperature=0.1,
                max_retries=2
            )
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as e:
            logger.error("Error parsing site operation: %s", e)
            return None


class BatchSiteOperations(BaseModel):
    """Container for multiple site operations extracted from one message."""
    operations: List[SiteOperation] = Field(
        description="List of site operations to perform. Use multiple entries when the user asks "
                    "to do several things at once (e.g. 'create A and B, then add X as member')."
    )


class SiteOperationBatchParserService:
    """Parse one message into potentially multiple site operations."""

    BATCH_PROMPT = (
        SiteOperationParserService.SITE_OPERATION_PROMPT
        + "\n\nIMPORTANT: The user may request MULTIPLE operations in one message "
        "(e.g. 'Create a Marketing site and a Sales site'). "
        "Return ALL operations in the 'operations' list. "
        "If there is only one operation, still return it inside the list."
    )

    @staticmethod
    async def parse(message: str) -> List[SiteOperation]:
        """Return a list of SiteOperations (≥1) for the given message."""
        import inspect
        try:
            client, model = get_instructor_client()
            response = client.chat.completions.create(
                model=model,
                response_model=BatchSiteOperations,
                messages=[
                    {"role": "system", "content": SiteOperationBatchParserService.BATCH_PROMPT},
                    {"role": "user", "content": f"Parse this request: {message}"},
                ],
                temperature=0.1,
                max_retries=2,
            )
            if inspect.isawaitable(response):
                response = await response
            return response.operations
        except Exception as e:
            logger.error("Error parsing batch site operations: %s", e)
            # Fallback to single-operation parse
            single = await SiteOperationParserService.parse_site_operation(message)
            return [single] if single else []

    @staticmethod
    async def detect_site_operation_intent(message: str) -> bool:
        """Detect if a message is requesting a site operation."""
        from src.detection.operations.site_operation_detector import detect_site_operation_intent
        return bool(detect_site_operation_intent(message))
