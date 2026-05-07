"""Constants for SharePoint operations."""


class SharePointConstants:
    """Constants used across SharePoint repository operations."""

    # Graph API batch operations
    MAX_BATCH_SIZE = 20
    MAX_PAGES_TO_FETCH = 20  # For paginated list items (~10,000 items max)
    ITEMS_PER_PAGE = 500
    
    # Canvas control types
    TEXT_WEBPART_CONTROL_TYPE = 4
    CLIENT_WEBPART_CONTROL_TYPE = 3
    
    # SharePoint metadata types
    SITE_PAGE_METADATA_TYPE = "SP.Publishing.SitePage"
    GROUP_METADATA_TYPE = "SP.Group"
    
    # Document library template
    DOCUMENT_LIBRARY_TEMPLATE = "documentLibrary"
    DOCUMENT_LIBRARY_TEMPLATE_ID = 101  # 101 = Document Library; 1 = Generic List
    
    # Permission levels
    PERMISSION_LEVELS = {
        "read": "Read",
        "contribute": "Contribute",
        "edit": "Edit",
        "full control": "Full Control"
    }
    
    # Protected column names (cannot be deleted)
    PROTECTED_COLUMNS = {
        "title", "id", "created", "modified",
        "author", "editor", "attachments"
    }
    
    # Session timeout for conversation state
    CONVERSATION_STATE_TTL_MINUTES = 30
