"""AI service for parsing list item operation requests."""

from typing import Dict, Any, Optional, Literal, List
from pydantic import BaseModel, Field, field_validator
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class ListItemOperation(BaseModel):
    """Structured representation of a list item operation."""
    operation: Literal["create", "update", "delete", "query", "attach", "view"] = Field(
        description="Type of operation: create, update, delete, query, attach (for attachments), or view (for custom views)"
    )
    list_name: str = Field(description="Name of the SharePoint list")
    field_values: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary of field names to values for create/update operations"
    )
    quantity: int = Field(
        default=1,
        description="Number of items to create. Parsed from phrases like 'add 3 items', 'create 5 records'."
    )
    auto_generate: bool = Field(
        default=False,
        description="True when the user asks the AI to generate/make up the data instead of providing it themselves. "
                    "Triggered by phrases like 'you decide', 'you add it', 'make something up', 'generate sample data', "
                    "'add X items' without specifying field values, etc."
    )
    item_id: Optional[str] = Field(
        default=None,
        description="Specific item ID to target for update/delete. Parsed from phrases like "
                    "'id 5', 'item 3', 'with id 0', 'the one with id 12'."
    )
    bulk: bool = Field(
        default=False,
        description="True when user wants to operate on ALL matching items (not just one). "
                    "Triggered by words like 'all', 'every', 'each', 'all the done items', 'all items where status is X'."
    )
    filter_criteria: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Criteria for finding items (for update/delete/query operations)"
    )
    item_description: Optional[str] = Field(
        default=None,
        description="Natural language description of the item or operation"
    )
    # Advanced query options
    select_fields: Optional[List[str]] = Field(
        default=None,
        description="List of specific fields to return in query results"
    )
    order_by: Optional[str] = Field(
        default=None,
        description="Field name to sort by (e.g., 'Created desc', 'Title asc')"
    )
    limit: Optional[int] = Field(
        default=None,
        description="Maximum number of results to return"
    )
    # Attachment operation details
    attachment_operation: Optional[Literal["add", "list", "delete"]] = Field(
        default=None,
        description="Type of attachment operation (when operation='attach')"
    )
    file_name: Optional[str] = Field(
        default=None,
        description="Name of the attachment file"
    )
    # View operation details
    view_name: Optional[str] = Field(
        default=None,
        description="Name of the view to create/modify/delete"
    )
    view_fields: Optional[List[str]] = Field(
        default=None,
        description="List of fields to include in the view"
    )

    @field_validator("attachment_operation", mode="before")
    @classmethod
    def normalize_attachment_operation(cls, value: Any) -> Any:
        """Convert empty/invalid attachment_operation values to None.

        The AI can emit attachment_operation='' even when operation is not
        'attach'. That should not fail parsing for normal create/update/query
        item requests.
        """
        if value is None:
            return None
        if isinstance(value, str):
            v = value.strip().lower()
            if not v:
                return None
            if v in {"add", "list", "delete"}:
                return v
            return None
        return None


class ListItemParserService:
    """Parse natural language requests for list item operations using AI."""

    ITEM_OPERATION_PROMPT = (
        "You are a SharePoint list item operation parser. Extract structured information from user requests "
        "to create, update, delete, query list items, manage attachments, or create views.\n\n"
        "Operation types:\n"
        "- 'create': Adding a new record/item to a list\n"
        "- 'update': Modifying an existing record/item\n"
        "- 'delete': Removing a record/item\n"
        "- 'query': Searching for or listing items\n"
        "- 'attach': Managing attachments (add, list, or delete)\n"
        "- 'view': Creating or managing custom list views\n\n"
        "Extract:\n"
        "1. The operation type\n"
        "2. The list name (infer from context, e.g., 'salary' -> 'Salaries' list)\n"
        "3. Field values for create/update (e.g., Name='John', Salary=5000). Leave empty dict if none provided.\n"
        "4. quantity: number of items to create (default 1). Parse from 'add 3 items', 'create 5 records', etc.\n"
        "5. auto_generate: set True when user wants AI to invent/generate the data — phrases like:\n"
        "   'you add it', 'you decide', 'make something up', 'generate sample', 'add N items' (with no field values),\n"
        "   'you come up with', 'fill it in', 'I don't know', 'surprise me', 'add data to it' (no values given).\n"
        "6. item_id: extract specific ID from 'id 5', 'item 3', 'with id 0', 'the one with id 12', 'delete comment 0'.\n"
        "7. bulk: set True when user says 'all', 'every', 'each' to target ALL matching items, e.g.:\n"
        "   'delete all done items', 'update all tasks to in progress', 'remove every completed record'.\n"
        "8. Filter criteria for update/delete/query (e.g., find by Name='John')\n"
        "9. Advanced query options:\n"
        "   - select_fields: Specific fields to return (e.g., ['Title', 'Status'])\n"
        "   - order_by: Sort field and direction (e.g., 'Created desc', 'Title asc')\n"
        "   - limit: Maximum number of results\n"
        "10. For attachments: attachment_operation ('add', 'list', or 'delete') and file_name\n"
        "11. For views: view_name and view_fields\n\n"
        "Examples:\n"
        "- 'Add a salary record for John with 5000 for March 2024'\n"
        "  → operation='create', list_name='Salaries', field_values={'Employee': 'John', 'Salary': 5000, 'Month': 'March 2024'}\n"
        "- 'Update Abdulrahman Alshafi salary to 5500 in March'\n"
        "  → operation='update', list_name='Salaries', filter_criteria={'Employee': 'Abdulrahman Alshafi', 'Month': 'March'}, field_values={'Salary': 5500}\n"
        "- 'Show all salaries above 4000, sorted by salary descending'\n"
        "  → operation='query', list_name='Salaries', filter_criteria={'Salary': {'$gt': 4000}}, order_by='Salary desc'\n"
        "- 'Show the top 10 tasks ordered by due date'\n"
        "  → operation='query', list_name='Tasks', order_by='DueDate asc', limit=10\n"
        "- 'Show employee names and salaries for March'\n"
        "  → operation='query', list_name='Salaries', select_fields=['Employee', 'Salary'], filter_criteria={'Month': 'March'}\n"
        "- 'Attach invoice.pdf to item 5 in the Expenses list'\n"
        "  → operation='attach', list_name='Expenses', attachment_operation='add', file_name='invoice.pdf', filter_criteria={'id': 5}\n"
        "- 'List attachments for the task titled Project Review'\n"
        "  → operation='attach', list_name='Tasks', attachment_operation='list', filter_criteria={'Title': 'Project Review'}\n"
        "- 'Create a view showing active tasks with title and due date'\n"
        "  → operation='view', list_name='Tasks', view_name='Active Tasks', view_fields=['Title', 'DueDate'], filter_criteria={'Status': 'Active'}\n"
        "- 'Delete all done items in the Milestones list'\n"
        "  → operation='delete', list_name='Milestones', filter_criteria={'Status': 'Done'}, bulk=True\n"
        "- 'Update all the done tasks to In Progress'\n"
        "  → operation='update', list_name='Tasks', filter_criteria={'Status': 'Done'}, field_values={'Status': 'In Progress'}, bulk=True\n"
        "- 'Delete the item with id 0'\n"
        "  → operation='delete', list_name=(infer from context), item_id='0'\n"
        "- 'Delete comment 5 from the Milestones list'\n"
        "  → operation='delete', list_name='Milestones', item_id='5'\n"
        "- 'Add 3 items to the Tasks list'\n"
        "  → operation='create', list_name='Tasks', quantity=3, auto_generate=True\n"
    )

    @staticmethod
    async def parse_item_operation(message: str, list_context: Optional[str] = None) -> Optional[ListItemOperation]:
        """Parse a natural language message into a structured item operation.

        Args:
            message:      User's natural language request.
            list_context: Optional structured context block describing the target
                          list (name + column names). When provided it is prepended
                          to the user message so the AI can map natural-language
                          field references to actual SharePoint column names.

        Returns:
            ListItemOperation object or None if parsing fails
        """
        import inspect
        try:
            client, model = get_instructor_client()

            user_content = f"Parse this request: {message}"
            if list_context:
                user_content = f"{list_context}\n\n{user_content}"

            result = client.chat.completions.create(
                model=model,
                response_model=ListItemOperation,
                messages=[
                    {
                        "role": "system",
                        "content": ListItemParserService.ITEM_OPERATION_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],
                temperature=0.1,
                max_retries=2
            )
            # Handle both sync and async instructor clients
            if inspect.isawaitable(result):
                result = await result
            return result
        except Exception as e:
            logger.error("Error parsing item operation: %s", e)
            return None

    @staticmethod
    def build_odata_filter(filter_criteria: Dict[str, Any]) -> str:
        """Build an OData $filter query from filter criteria.
        
        Args:
            filter_criteria: Dictionary of field names to values or comparison operators
            
        Returns:
            OData $filter query string
        """
        # Built-in Graph listItem properties that must NOT be prefixed with "fields/"
        _BUILTIN_PROPS = frozenset({
            "id", "createdDateTime", "lastModifiedDateTime", "webUrl",
            "createdBy", "lastModifiedBy", "contentType", "eTag",
        })

        def _field(name: str) -> str:
            """Prefix custom fields with 'fields/' as required by the Graph API OData filter."""
            return name if name in _BUILTIN_PROPS else f"fields/{name}"

        filters = []

        for field, value in filter_criteria.items():
            f = _field(field)
            if isinstance(value, dict):
                # Handle comparison operators
                if '$gt' in value:
                    filters.append(f"{f} gt {value['$gt']}")
                elif '$lt' in value:
                    filters.append(f"{f} lt {value['$lt']}")
                elif '$gte' in value:
                    filters.append(f"{f} ge {value['$gte']}")
                elif '$lte' in value:
                    filters.append(f"{f} le {value['$lte']}")
                elif '$ne' in value:
                    escaped = str(value['$ne']).replace("'", "''")
                    filters.append(f"{f} ne '{escaped}'")
            elif isinstance(value, str):
                escaped = value.replace("'", "''")
                filters.append(f"{f} eq '{escaped}'")
            elif isinstance(value, bool):
                filters.append(f"{f} eq {str(value).lower()}")
            else:
                filters.append(f"{f} eq {value}")

        return " and ".join(filters)

    @staticmethod
    async def detect_item_operation_intent(message: str) -> bool:
        """Detect if a message is about list item operations."""
        from src.detection.operations.list_item_operation_detector import detect_list_item_operation_intent
        return bool(detect_list_item_operation_intent(message))
