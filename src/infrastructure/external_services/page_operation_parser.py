"""AI service for parsing page operation requests."""

import logging
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field
from src.infrastructure.external_services.ai_client_factory import get_instructor_client

logger = logging.getLogger(__name__)


class PageOperation(BaseModel):
    """Structured representation of a page operation."""
    operation: Literal[
        "create", "get", "list", "publish", "unpublish", "copy", "delete",
        "promote_news", "update", "checkout", "checkin", "versions",
        "restore_version", "share", "analytics", "schedule"
    ] = Field(
        description=(
            "Type of operation: create, get, list, publish, unpublish, copy, delete, "
            "promote_news, update, checkout, checkin, versions, restore_version, share, "
            "analytics, or schedule"
        )
    )
    page_title: Optional[str] = Field(
        default=None,
        description="Title of the page"
    )
    page_name: Optional[str] = Field(
        default=None,
        description="URL-safe name of the page (usually ends with .aspx)"
    )
    content: Optional[str] = Field(
        default=None,
        description="Content or description for the page (used for create/update)"
    )
    content_sections: Optional[List[str]] = Field(
        default=None,
        description="List of content sections/webpart descriptions for rich page creation"
    )
    layout: Optional[Literal[
        "article", "home", "singleWebPartApp",
        "two-column", "three-column", "one-third-left", "one-third-right"
    ]] = Field(
        default="article",
        description="Page layout type"
    )
    promote_as_news: Optional[bool] = Field(
        default=False,
        description="Whether to promote this page as a news item"
    )
    new_title: Optional[str] = Field(
        default=None,
        description="New title for copy operation"
    )
    version_id: Optional[str] = Field(
        default=None,
        description="Version ID for restore_version operation"
    )
    target_page_title: Optional[str] = Field(
        default=None,
        description="Target page title for copy operation destination"
    )
    target_site_name: Optional[str] = Field(
        default=None,
        description="Name of a different site to create the page on (cross-site page creation)"
    )
    scheduled_datetime: Optional[str] = Field(
        default=None,
        description="ISO 8601 datetime string for scheduling page publish (schedule operation)"
    )


class PageOperationParserService:
    """Parse natural language requests for page operations using AI."""

    PAGE_OPERATION_PROMPT = (
        "You are a SharePoint page operation parser. Extract structured information from user requests "
        "about SharePoint page operations.\n\n"
        "Operation types:\n"
        "- 'create': Creating a new page\n"
        "- 'get': Getting details of a specific page\n"
        "- 'list': Listing all pages\n"
        "- 'publish': Publishing a draft page\n"
        "- 'unpublish': Unpublishing/demoting a page back to draft\n"
        "- 'copy': Copying an existing page to a new one\n"
        "- 'delete': Deleting a page\n"
        "- 'promote_news': Promoting a page as a news article\n"
        "- 'update': Updating/editing the content of an existing page\n"
        "- 'checkout': Checking out a page for exclusive editing\n"
        "- 'checkin': Checking in a page after editing\n"
        "- 'versions': Listing all versions of a page\n"
        "- 'restore_version': Restoring a page to a specific version\n"
        "- 'share': Getting a shareable link for a page\n"
        "- 'analytics': Viewing page analytics (views, visitors)\n"
        "- 'schedule': Scheduling a page to publish at a future date/time\n\n"
        "Layout types: article, home, singleWebPartApp, two-column, three-column, one-third-left, one-third-right\n\n"
        "Extract:\n"
        "1. The operation type\n"
        "2. The page title or name\n"
        "3. Content/description if creating or updating a page\n"
        "4. Layout type (default: article)\n"
        "5. Whether to promote as news\n"
        "6. version_id if restoring a specific version\n"
        "7. new_title if copying a page\n"
        "8. target_site_name if creating a page on a different site\n"
        "9. scheduled_datetime in ISO 8601 format if scheduling (convert natural language dates)\n"
        "10. content_sections: list of webpart descriptions (e.g. 'hero banner', 'quick links to Jira and GitHub', 'news feed')\n\n"
        "Examples:\n"
        "- 'Create a new page called Welcome Team'\n"
        "  → operation='create', page_title='Welcome Team', layout='article'\n"
        "- 'Create a welcome page for Engineering with a hero and quick links to Jira and GitHub'\n"
        "  → operation='create', page_title='Welcome Engineering', content_sections=['hero banner: Welcome to Engineering', 'quick links: Jira, GitHub']\n"
        "- 'Create a page called Policies on the HR site'\n"
        "  → operation='create', page_title='Policies', target_site_name='HR'\n"
        "- 'Show me all pages'\n"
        "  → operation='list'\n"
        "- 'Publish the Q4 Results page'\n"
        "  → operation='publish', page_title='Q4 Results'\n"
        "- 'Unpublish the Welcome page'\n"
        "  → operation='unpublish', page_title='Welcome'\n"
        "- 'Copy Homepage to New Homepage'\n"
        "  → operation='copy', page_title='Homepage', new_title='New Homepage'\n"
        "- 'Promote Company News as a news article'\n"
        "  → operation='promote_news', page_title='Company News', promote_as_news=True\n"
        "- 'Delete the old announcement page'\n"
        "  → operation='delete', page_title='old announcement'\n"
        "- 'Update the About page with our new mission statement: We build great software'\n"
        "  → operation='update', page_title='About', content='We build great software'\n"
        "- 'Checkout the Policies page'\n"
        "  → operation='checkout', page_title='Policies'\n"
        "- 'Check in the Policies page'\n"
        "  → operation='checkin', page_title='Policies'\n"
        "- 'Show versions of the Home page'\n"
        "  → operation='versions', page_title='Home'\n"
        "- 'Restore version 3 of the Policies page'\n"
        "  → operation='restore_version', page_title='Policies', version_id='3'\n"
        "- 'Share a link to the Team page'\n"
        "  → operation='share', page_title='Team'\n"
        "- 'Show analytics for the Home page'\n"
        "  → operation='analytics', page_title='Home'\n"
        "- 'Schedule the Welcome page to publish next Monday at 9am'\n"
        "  → operation='schedule', page_title='Welcome', scheduled_datetime='2026-04-27T09:00:00Z'\n"
    )

    @staticmethod
    async def parse_page_operation(message: str) -> Optional[PageOperation]:
        """Parse a natural language message into a structured page operation.
        
        Args:
            message: User's natural language request
            
        Returns:
            PageOperation object or None if parsing fails
        """
        import inspect
        try:
            client, model = get_instructor_client()

            result = client.chat.completions.create(
                model=model,
                response_model=PageOperation,
                messages=[
                    {
                        "role": "system",
                        "content": PageOperationParserService.PAGE_OPERATION_PROMPT
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
            logger.error(f"Error parsing page operation: {e}")
            return None

    @staticmethod
    async def detect_page_operation_intent(message: str) -> bool:
        """Detect if a message is requesting a page operation."""
        from src.detection.operations.page_operation_detector import detect_page_operation_intent
        return bool(detect_page_operation_intent(message))
