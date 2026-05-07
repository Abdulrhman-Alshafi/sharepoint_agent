"""AI service for parsing file operation requests."""

from typing import Optional, Literal, Dict, Any
from pydantic import BaseModel, Field
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


class FileOperation(BaseModel):
    """Structured representation of a file operation."""
    operation: Literal[
        "upload", "download", "copy", "move", "delete",
        "get_versions", "restore_version", "checkout", "checkin",
        "create_folder", "delete_folder", "list_folder",
        "create_share_link"
    ] = Field(
        description=(
            "Type of operation: upload, download, copy, move, delete, "
            "get_versions, restore_version, checkout, checkin, "
            "create_folder, delete_folder, list_folder, create_share_link"
        )
    )
    file_name: Optional[str] = Field(
        default=None,
        description="Name of the file to operate on"
    )
    library_name: Optional[str] = Field(
        default=None,
        description="Name of the source document library"
    )
    destination_library_name: Optional[str] = Field(
        default=None,
        description="Name of the destination document library (for copy/move operations)"
    )
    folder_path: Optional[str] = Field(
        default=None,
        description="Folder path within the library or folder name for folder operations"
    )
    folder_name: Optional[str] = Field(
        default=None,
        description="Name of the folder for folder operations"
    )
    new_name: Optional[str] = Field(
        default=None,
        description="New name for the file (for move/copy operations)"
    )
    version_id: Optional[str] = Field(
        default=None,
        description="Version ID for restore_version operation"
    )
    checkin_comment: Optional[str] = Field(
        default=None,
        description="Comment for checkin operation"
    )
    share_type: Optional[Literal["view", "edit"]] = Field(
        default="view",
        description="Permission type for sharing link: view or edit"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Metadata to attach to the file"
    )


class FileOperationParserService:
    """Parse natural language requests for file operations using AI."""

    FILE_OPERATION_PROMPT = (
        "You are a SharePoint file operation parser. Extract structured information from user requests "
        "for file and folder operations in document libraries.\n\n"
        "Operation types:\n"
        "- 'upload': Uploading a new file to a library\n"
        "- 'download': Downloading a file from a library\n"
        "- 'copy': Copying a file to another location\n"
        "- 'move': Moving a file to another location\n"
        "- 'delete': Deleting a file from a library\n"
        "- 'get_versions': Get version history of a file\n"
        "- 'restore_version': Restore a file to a previous version\n"
        "- 'checkout': Check out a file for editing\n"
        "- 'checkin': Check in a file after editing\n"
        "- 'create_folder': Create a new folder in a library\n"
        "- 'delete_folder': Delete a folder from a library\n"
        "- 'list_folder': List contents of a folder\n"
        "- 'create_share_link': Create a sharing link for a file\n\n"
        "Extract:\n"
        "1. The operation type\n"
        "2. The file or folder name\n"
        "3. The library name (infer from context)\n"
        "4. For copy/move: destination library name\n"
        "5. Folder path if specified\n"
        "6. Version ID for restore operations\n"
        "7. Share type (view/edit) for sharing operations\n\n"
        "Examples:\n"
        "- 'Upload report.pdf to the Documents library'\n"
        "  → operation='upload', file_name='report.pdf', library_name='Documents'\n"
        "- 'Download budget.xlsx from HR Documents'\n"
        "  → operation='download', file_name='budget.xlsx', library_name='HR Documents'\n"
        "- 'Show me the version history of contract.docx in Legal'\n"
        "  → operation='get_versions', file_name='contract.docx', library_name='Legal'\n"
        "- 'Check out proposal.docx from Shared Documents for editing'\n"
        "  → operation='checkout', file_name='proposal.docx', library_name='Shared Documents'\n"
        "- 'Check in report.docx with comment Updated Q4 data'\n"
        "  → operation='checkin', file_name='report.docx', checkin_comment='Updated Q4 data'\n"
        "- 'Create a folder called Q4 Reports in Documents'\n"
        "  → operation='create_folder', folder_name='Q4 Reports', library_name='Documents'\n"
        "- 'Create a view link for budget.xlsx in Finance'\n"
        "  → operation='create_share_link', file_name='budget.xlsx', library_name='Finance', share_type='view'\n"
    )

    @staticmethod
    async def parse_file_operation(message: str) -> Optional[FileOperation]:
        """Parse a natural language message into a structured file operation.
        
        Args:
            message: User's natural language request
            
        Returns:
            FileOperation object or None if parsing fails
        """
        import inspect
        try:
            client, model = get_instructor_client()

            result = client.chat.completions.create(
                model=model,
                response_model=FileOperation,
                messages=[
                    {
                        "role": "system",
                        "content": FileOperationParserService.FILE_OPERATION_PROMPT
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
            logger.error("Error parsing file operation: %s", e)
            return None

    @staticmethod
    async def detect_file_operation_intent(message: str) -> bool:
        """Detect if a message is requesting a file operation."""
        from src.detection.operations.file_operation_detector import detect_file_operation_intent
        return bool(detect_file_operation_intent(message))
