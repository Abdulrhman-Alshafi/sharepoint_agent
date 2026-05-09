"""AI service for parsing library (document library) operation requests."""

import logging
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field, field_validator
from src.infrastructure.external_services.ai_client_factory import get_instructor_client

logger = logging.getLogger(__name__)


class LibraryOperation(BaseModel):
    """Structured representation of a library operation."""
    operation: Literal["create", "get", "list", "delete", "add_column", "get_schema", "update_settings", "add_folder", "upload_file"] = Field(
        description="Type of operation: create, get, list, delete, add_column, get_schema, update_settings, add_folder, upload_file"
    )
    library_name: Optional[str] = Field(
        default=None,
        description="Name of the document library"
    )
    description: Optional[str] = Field(
        default=None,
        description="Description for the library"
    )
    enable_versioning: Optional[bool] = Field(
        default=True,
        description="Whether to enable versioning for the library"
    )
    enable_minor_versions: Optional[bool] = Field(
        default=False,
        description="Whether to enable minor versions (draft versions)"
    )
    major_version_limit: Optional[int] = Field(
        default=None,
        description="Maximum number of major versions to keep (null = unlimited)"
    )
    column_name: Optional[str] = Field(
        default=None,
        description="Column name for add_column operation"
    )
    column_type: Optional[Literal["text", "number", "date", "choice", "boolean"]] = Field(
        default=None,
        description="Type of column to add"
    )
    folder_paths: Optional[List[str]] = Field(
        default=None,
        description="Optional folder paths to create in the library. Supports nested paths with '/'."
    )
    folder_name: Optional[str] = Field(
        default=None,
        description="Name of a folder to create or operate on"
    )
    file_path: Optional[str] = Field(
        default=None,
        description="Path to file being uploaded"
    )
    target_folder: Optional[str] = Field(
        default=None,
        description="Target folder path for file upload (if not root)"
    )

    @field_validator("column_type", mode="before")
    @classmethod
    def normalize_column_type(cls, value: Any) -> Any:
        """Convert empty strings to None; normalize type aliases."""
        if not value or (isinstance(value, str) and not value.strip()):
            return None
        if isinstance(value, str):
            normalized = value.strip().lower()
            # Map common aliases
            aliases = {
                "text": "text",
                "string": "text",
                "singleline": "text",
                "number": "number",
                "int": "number",
                "integer": "number",
                "date": "date",
                "datetime": "date",
                "choice": "choice",
                "boolean": "boolean",
                "bool": "boolean",
            }
            return aliases.get(normalized, normalized)
        return value


class LibraryOperationParserService:
    """Parse natural language requests for library operations using AI."""

    LIBRARY_OPERATION_PROMPT = (
        "You are a SharePoint document library operation parser. Extract structured information from user requests "
        "to create, view, configure, or delete document libraries.\n\n"
        "Operation types:\n"
        "- 'create': Creating a new document library\n"
        "- 'get': Getting details of a specific library\n"
        "- 'list': Listing all document libraries\n"
        "- 'delete': Deleting a library\n"
        "- 'add_column': Adding a column to a library\n"
        "- 'get_schema': Getting the structure/schema of a library\n"
        "- 'update_settings': Updating library settings (versioning, etc.)\n\n"
                "- 'add_folder': Adding a folder to an existing library\n"
                "- 'upload_file': Uploading a file to a library (may prompt for folder selection)\n\n"
        "Extract:\n"
        "1. The operation type\n"
        "2. The library name\n"
        "3. Description if creating a library\n"
        "4. Versioning settings (enable_versioning, enable_minor_versions, major_version_limit)\n"
        "5. Column details if adding columns\n\n"
        "6. folder_paths for create requests when folders are mentioned\n\n"
        "Examples:\n"
        "- 'Create a document library called Project Files'\n"
        "  → operation='create', library_name='Project Files', enable_versioning=True\n"
        "- 'Create a library for HR Documents with versioning enabled'\n"
        "  → operation='create', library_name='HR Documents', enable_versioning=True\n"
        "- 'Create a library named Team Files with folders: General, Projects/2026/Q1, Projects/2026/Q2'\n"
        "  → operation='create', library_name='Team Files', folder_paths=['General', 'Projects/2026/Q1', 'Projects/2026/Q2']\n"
        "- 'Show me all document libraries'\n"
        "  → operation='list'\n"
        "- 'Get details of the Documents library'\n"
        "  → operation='get', library_name='Documents'\n"
        "- 'Add a Status column to the Project Files library'\n"
        "  → operation='add_column', library_name='Project Files', column_name='Status', column_type='text'\n"
        "- 'Enable versioning on the Documents library'\n"
        "  → operation='update_settings', library_name='Documents', enable_versioning=True\n"
        "- 'Delete the old archives library'\n"
                    "  → operation='delete', library_name='old archives'\n"
                "- 'Add the HR folder to the Documents library'\n"
                    "  → operation='add_folder', library_name='Documents', folder_name='HR'\n"
                "- 'I want to add the folder Projects/2026 to the Team Files library'\n"
                    "  → operation='add_folder', library_name='Team Files', folder_paths=['Projects/2026']\n"
                "- 'Upload a file to my Documents library'\n"
                    "  → operation='upload_file', library_name='Documents'\n"
    )

    @staticmethod
    async def parse_library_operation(message: str) -> Optional[LibraryOperation]:
        """Parse a natural language message into a structured library operation.
        
        Args:
            message: User's natural language request
            
        Returns:
            LibraryOperation object or None if parsing fails
        """
        try:
            client, model = get_instructor_client()
            
            response = client.chat.completions.create(
                model=model,
                response_model=LibraryOperation,
                messages=[
                    {
                        "role": "system",
                        "content": LibraryOperationParserService.LIBRARY_OPERATION_PROMPT
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
            logger.error(f"Error parsing library operation: {e}")
            return None

    @staticmethod
    async def detect_library_operation_intent(message: str) -> bool:
        """Detect if a message is requesting a library operation."""
        from src.detection.operations.library_operation_detector import detect_library_operation_intent
        return bool(detect_library_operation_intent(message))
