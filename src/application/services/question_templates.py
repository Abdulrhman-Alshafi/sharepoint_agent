"""Question templates for different SharePoint resource types."""

from typing import Dict, List
from src.domain.entities.conversation import Question, ResourceType


class QuestionTemplates:
    """Pre-defined question flows for each SharePoint resource type."""

    # Site questions
    SITE_QUESTIONS: List[Question] = [
        Question(
            field_name="title",
            question_text="What would you like to call this new SharePoint site?",
            field_type="text",
            required=True,
            validation_hint="Site names should be descriptive (e.g., 'Project Alpha', 'Marketing Intranet')"
        ),
        Question(
            field_name="description",
            question_text="Please provide a brief description of the site's purpose",
            field_type="text",
            required=False,
            options=["Skip, I'll add it later", "Team collaboration hub", "Project management and tracking", "Knowledge base and documentation", "Company news and announcements"],
            default_value=""
        ),
        Question(
            field_name="template",
            question_text="Is this a Team site (for collaboration) or a Communication site (for broadcasting info)?",
            field_type="choice",
            required=True,
            options=["Team site (sts)", "Communication site (sitepagepublishing)"],
            default_value="Team site (sts)"
        ),
    ]

    # List questions
    LIST_QUESTIONS: List[Question] = [
        Question(
            field_name="title",
            question_text="What would you like to name this list?",
            field_type="text",
            required=True,
            validation_hint="List name should be descriptive (e.g., 'Project Tracker', 'Employee Directory')"
        ),
        Question(
            field_name="description",
            question_text="Please provide a brief description of this list's purpose (optional)",
            field_type="text",
            required=False,
            options=["Skip, I'll add it later", "Track team tasks and deadlines", "Store team contact information", "Manage project milestones", "Track inventory items"],
            default_value=""
        ),
        Question(
            field_name="columns",
            question_text="What columns should this list have? Please list them separated by commas (e.g., Title, Status, Priority, Due Date).\n\nOr say **\"you decide\"** and I'll generate the best columns based on the list's purpose.",
            field_type="text",
            required=True,
            options=["You decide", "Title, Status, Priority, Due Date", "Title, Description, Owner, Due Date"],
            validation_hint="Include at least one column besides the default 'Title' column, or say 'you decide'"
        ),
        Question(
            field_name="column_types",
            question_text="For each column, what type should it be? (Reply with format: ColumnName:Type, e.g., Status:choice, Priority:choice, Due Date:dateTime)",
            field_type="text",
            required=False,
            options=["You decide", "Title:text, Status:choice, Priority:choice, Due Date:dateTime", "Title:text, Description:text, Owner:text, Date:dateTime", "Title:text, Category:choice, Status:choice, Priority:number"],
            validation_hint="Available types: text, number, dateTime, choice, boolean"
        ),
        Question(
            field_name="add_sample_data",
            question_text="Would you like me to add sample data to help you get started?",
            field_type="choice",
            required=False,
            options=["Yes, add sample data", "No, I'll add data myself"],
            default_value="No, I'll add data myself"
        ),
        Question(
            field_name="target_site",
            question_text="Where do you want to add this new content?\n\nQuick option: choose **Use current site** to add it to the site you're currently in.",
            field_type="text",
            required=True,
            options=["Use current site"],
            default_value=None
        ),
    ]

    # Page questions
    PAGE_QUESTIONS: List[Question] = [
        Question(
            field_name="title",
            question_text="What should this page be called?",
            field_type="text",
            required=True,
            validation_hint="Page title should be clear and descriptive"
        ),
        Question(
            field_name="target_site",
            question_text="Where do you want to add this new content?\n\nQuick option: choose **Use current site** to add it to the site you're currently in.",
            field_type="text",
            required=True,
            options=["Use current site"],
            default_value=None
        ),
    ]

    # Document Library questions
    LIBRARY_QUESTIONS: List[Question] = [
        Question(
            field_name="title",
            question_text="What should this document library be called?\n\n",
            field_type="text",
            required=True,
            validation_hint="Library name should describe the documents it will contain"
        ),
        Question(
            field_name="description",
            question_text="What types of documents will be stored here?\n\nSay **\"Generate description\"** and I'll write one for you.",
            field_type="text",
            required=False,
            options=["Generate description"],
            default_value=""
        ),
        Question(
            field_name="add_metadata_columns",
            question_text=(
                "Do you want to add metadata columns to this library?\n\n"
                "Choose **Yes, add metadata columns** or **No metadata columns for now**."
            ),
            field_type="choice",
            required=True,
            options=["Yes, add metadata columns", "No metadata columns for now"],
            default_value="No metadata columns for now"
        ),
        Question(
            field_name="metadata_columns",
            question_text=(
                "Which metadata columns should this library have?\n\n"
                "Example: `Document Type, Department, Owner, Review Date`\n"
                "Or say **\"you decide\"** and I'll generate the best metadata columns with AI.\n"
                "Or say **\"skip metadata columns\"** to not add any metadata columns."
            ),
            field_type="text",
            required=False,
            options=["You decide", "Skip metadata columns", "Document Type, Department, Owner, Review Date"],
            default_value=""
        ),
        Question(
            field_name="metadata_column_types",
            question_text=(
                "What data type should each metadata column use?\n\n"
                "Use list-style format: `ColumnName:type` separated by commas.\n"
                "Example: `Document Type:choice, Department:text, Owner:personOrGroup, Review Date:dateTime`\n"
                "Allowed types: `text`, `note`, `number`, `dateTime`, `choice`, `lookup`, `managed_metadata`, `boolean`, `personOrGroup`, `currency`, `hyperlinkOrPicture`, `geolocation`.\n"
                "Or choose **You make them (same as list format)** and I'll infer the best types."
            ),
            field_type="text",
            required=False,
            options=[
                "You make them (same as list format)",
                "Document Type:choice, Department:text, Owner:personOrGroup, Review Date:dateTime",
            ],
            default_value=""
        ),
        Question(
            field_name="create_folders",
            question_text=(
                "Do you want me to create starter folders inside this library?\n\n"
                "Choose **Yes, create folders now** or **No folders for now**."
            ),
            field_type="choice",
            required=True,
            options=["Yes, create folders now", "No folders for now"],
            default_value="No folders for now"
        ),
        Question(
            field_name="folder_paths",
            question_text=(
                "List the folders to create.\n\n"
                "Format options:\n"
                "- Comma separated: `HR, Finance, Legal`\n"
                "- Nested paths with `/`: `Projects/2026/Q1`, `Projects/2026/Q2`\n\n"
                "Say **\"Skip folders\"** to continue without folders."
            ),
            field_type="text",
            required=False,
            default_value="",
            validation_hint="Use commas/new lines; use / for nested folders"
        ),
        Question(
            field_name="target_site",
            question_text="Where do you want to add this new content?\n\nQuick option: choose **Use current site** to add it to the site you're currently in.",
            field_type="text",
            required=True,
            options=["Use current site"],
            default_value=None
        ),
    ]

    # Group questions
    GROUP_QUESTIONS: List[Question] = [
        Question(
            field_name="name",
            question_text="What should this SharePoint group be called?",
            field_type="text",
            required=True,
            validation_hint="Group name should describe the members (e.g., 'HR Team', 'Project Managers')"
        ),
        Question(
            field_name="permission_level",
            question_text="What permission level should this group have?",
            field_type="choice",
            required=True,
            options=["Read (view only)", "Contribute (view and add)", "Edit (view, add, edit)", "Full Control (all permissions)"],
            default_value="Contribute (view and add)"
        ),
        Question(
            field_name="target_resource",
            question_text="Which library or list should this group have access to? (or leave blank for site-wide access)",
            field_type="text",
            required=False,
            default_value=""
        ),
    ]

    # Content Type questions
    CONTENT_TYPE_QUESTIONS: List[Question] = [
        Question(
            field_name="name",
            question_text="What should this content type be called?",
            field_type="text",
            required=True
        ),
        Question(
            field_name="description",
            question_text="What is this content type used for?",
            field_type="text",
            required=True
        ),
        Question(
            field_name="parent_type",
            question_text="What should this content type be based on?",
            field_type="choice",
            required=False,
            options=["Item", "Document", "Folder"],
            default_value="Item"
        ),
    ]

    # View questions
    VIEW_QUESTIONS: List[Question] = [
        Question(
            field_name="title",
            question_text="What should this view be called?",
            field_type="text",
            required=True
        ),
        Question(
            field_name="target_list",
            question_text="Which list should this view be created for?",
            field_type="text",
            required=True
        ),
        Question(
            field_name="columns",
            question_text="Which columns should be displayed? (comma-separated)",
            field_type="text",
            required=True
        ),
        Question(
            field_name="sort_by",
            question_text="How should items be sorted? (e.g., 'Created: descending', 'Title: ascending')",
            field_type="text",
            required=False,
            default_value=""
        ),
    ]

    @classmethod
    def get_questions(cls, resource_type: ResourceType) -> List[Question]:
        """Get questions for a specific resource type.
        
        Args:
            resource_type: The type of SharePoint resource
            
        Returns:
            List of questions for that resource type
        """
        question_map = {
            ResourceType.SITE: cls.SITE_QUESTIONS,
            ResourceType.LIST: cls.LIST_QUESTIONS,
            ResourceType.PAGE: cls.PAGE_QUESTIONS,
            ResourceType.LIBRARY: cls.LIBRARY_QUESTIONS,
            ResourceType.GROUP: cls.GROUP_QUESTIONS,
            ResourceType.CONTENT_TYPE: cls.CONTENT_TYPE_QUESTIONS,
            ResourceType.VIEW: cls.VIEW_QUESTIONS,
        }
        
        return question_map.get(resource_type, [])

    @classmethod
    def get_required_fields(cls, resource_type: ResourceType) -> List[str]:
        """Get list of required field names for a resource type.
        
        Args:
            resource_type: The type of SharePoint resource
            
        Returns:
            List of required field names
        """
        questions = cls.get_questions(resource_type)
        return [q.field_name for q in questions if q.required]
