"""AI service for parsing enterprise SharePoint operation requests (content types, term sets)."""

from typing import Optional, Literal, List
from pydantic import BaseModel, Field
from src.infrastructure.external_services.ai_client_factory import get_instructor_client


class EnterpriseOperation(BaseModel):
    """Structured representation of an enterprise SharePoint operation."""
    operation: Literal[
        "create_content_type", "list_content_types",
        "create_term_set", "list_term_sets",
        "create_view", "list_views"
    ] = Field(
        description=(
            "Type of operation: create_content_type, list_content_types, "
            "create_term_set, list_term_sets, create_view, list_views"
        )
    )
    content_type_name: Optional[str] = Field(
        default=None,
        description="Name of the content type to create"
    )
    content_type_description: Optional[str] = Field(
        default=None,
        description="Description of the content type"
    )
    parent_content_type: Optional[str] = Field(
        default="Item",
        description="Parent content type (e.g., 'Item', 'Document')"
    )
    term_set_name: Optional[str] = Field(
        default=None,
        description="Name of the term set to create"
    )
    terms: Optional[List[str]] = Field(
        default=None,
        description="List of terms to add to the term set"
    )
    view_name: Optional[str] = Field(
        default=None,
        description="Name of the view to create"
    )
    list_name: Optional[str] = Field(
        default=None,
        description="Name of the list for view operations"
    )
    view_fields: Optional[List[str]] = Field(
        default=None,
        description="Fields to include in the view"
    )


class EnterpriseOperationParserService:
    """Parse natural language requests for enterprise SharePoint operations using AI."""

    ENTERPRISE_OPERATION_PROMPT = (
        "You are a SharePoint enterprise operations parser. Extract structured information from user requests "
        "about content types, term sets (managed metadata), and views.\n\n"
        "Operation types:\n"
        "- 'create_content_type': Create a new content type\n"
        "- 'list_content_types': List all content types in the site\n"
        "- 'create_term_set': Create a new managed metadata term set\n"
        "- 'list_term_sets': List all term sets\n"
        "- 'create_view': Create a new list view\n"
        "- 'list_views': List all views for a list\n\n"
        "Extract:\n"
        "1. The operation type\n"
        "2. For content types: name, description, parent type\n"
        "3. For term sets: name, list of terms\n"
        "4. For views: name, list name, fields to display\n\n"
        "Examples:\n"
        "- 'Create a content type called Project Document based on Document'\n"
        "  → operation='create_content_type', content_type_name='Project Document', parent_content_type='Document'\n"
        "- 'Show me all content types'\n"
        "  → operation='list_content_types'\n"
        "- 'Create a term set called Departments with terms HR, Finance, IT, Marketing'\n"
        "  → operation='create_term_set', term_set_name='Departments', terms=['HR', 'Finance', 'IT', 'Marketing']\n"
        "- 'List all term sets'\n"
        "  → operation='list_term_sets'\n"
        "- 'Create a view called Active Tasks for the Tasks list showing Title, Status, DueDate'\n"
        "  → operation='create_view', view_name='Active Tasks', list_name='Tasks', view_fields=['Title', 'Status', 'DueDate']\n"
    )

    @staticmethod
    async def parse_enterprise_operation(message: str) -> Optional[EnterpriseOperation]:
        """Parse a natural language message into a structured enterprise operation.
        
        Args:
            message: User's natural language request
            
        Returns:
            EnterpriseOperation object or None if parsing fails
        """
        try:
            client, model = get_instructor_client()

            kwargs = {
                "messages": [
                    {"role": "system", "content": EnterpriseOperationParserService.ENTERPRISE_OPERATION_PROMPT},
                    {"role": "user", "content": message},
                ],
                "response_model": EnterpriseOperation,
                "max_retries": 2,
                "temperature": 0.1,
            }
            if model:
                kwargs["model"] = model

            operation = client.chat.completions.create(**kwargs)
            return operation
        except Exception as e:
            from src.infrastructure.config import logger
            logger.warning(f"Failed to parse enterprise operation: {e}")
            return None

    @staticmethod
    async def detect_enterprise_operation_intent(message: str) -> bool:
        """Quickly detect if message is about enterprise operations.
        
        Args:
            message: User's message
            
        Returns:
            True if message appears to be about enterprise operations
        """
        message_lower = message.lower()
        enterprise_keywords = [
            "content type", "create content type", "list content types",
            "term set", "managed metadata", "taxonomy", "create term set",
            "create view", "list view", "add view", "new view",
            "term store", "metadata terms"
        ]
        
        return any(keyword in message_lower for keyword in enterprise_keywords)
