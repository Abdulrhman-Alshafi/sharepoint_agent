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
        Question(
            field_name="owner_email",
            question_text="Who should be the primary owner of this site? (Please provide their exact email address)",
            field_type="text",
            required=False,
            default_value="",
            validation_hint="Optional. If left blank, default settings apply based on permissions."
        ),
        Question(
            field_name="site_content",
            question_text="What pages, lists, or libraries should the site include?\n\nSay **\"You choose the best setup\"** and I'll create the ideal structure based on the site's purpose, or list what you want (e.g., 'Home page, Documents library, Tasks list').",
            field_type="text",
            required=False,
            options=["You choose the best setup", "Home page, Documents library, Tasks list", "Just the site, no extras"],
            default_value="You choose the best setup"
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
            question_text="Where do you want to add this new content?",
            field_type="text",
            required=True,
            options=None,
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
            field_name="sections",
            question_text="What sections or web parts should this page include?\n\nSay **\"You choose\"** and I'll design the best layout, or list what you want (e.g., 'Hero banner, Quick links, News feed, People').",
            field_type="text",
            required=False,
            options=["You choose", "Hero banner, Quick links, News feed", "Hero banner, Text content, People"],
            default_value="You choose"
        ),
        Question(
            field_name="main_content",
            question_text="What text or information should appear on this page?\n\nSay **\"Generate it for me\"** and I'll create professional content based on the page's purpose.",
            field_type="text",
            required=False,
            options=["Generate it for me"],
            default_value="Generate it for me",
            validation_hint="Describe the main content or provide the actual text, or let AI generate it"
        ),
        Question(
            field_name="target_site",
            question_text="Where do you want to add this new content?",
            field_type="text",
            required=True,
            options=None,
            default_value=None
        ),
    ]

    # Document Library questions
    LIBRARY_QUESTIONS: List[Question] = [
        Question(
            field_name="title",
            question_text="What should this document library be called?\n\nSay **\"Use a default name\"** and I can suggest one based on your purpose.",
            field_type="text",
            required=True,
            validation_hint="Library name should describe the documents it will contain"
        ),
        Question(
            field_name="description",
            question_text="What types of documents will be stored here?\n\nSay **\"Generate description\"** and I'll write one for you.",
            field_type="text",
            required=False,
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
                "- One per line\n"
                "- Nested paths with `/`: `Projects/2026/Q1`, `Projects/2026/Q2`\n\n"
                "Say **\"Skip folders\"** to continue without folders."
            ),
            field_type="text",
            required=False,
            default_value="",
            validation_hint="Use commas/new lines; use / for nested folders"
        ),
        Question(
            field_name="needs_permissions",
            question_text="Do you need to restrict who can access or upload to this library?",
            field_type="choice",
            required=True,
            options=["Yes, restrict access", "No, everyone can access"],
            default_value="No, everyone can access"
        ),
        Question(
            field_name="permission_groups",
            question_text="Who should have access? Please specify groups and their permission levels (e.g., 'HR Team: Contribute, Managers: Edit')",
            field_type="text",
            required=False,
            validation_hint="Format: GroupName: PermissionLevel (Read/Contribute/Edit/Full Control)"
        ),
        Question(
            field_name="target_site",
            question_text="Where do you want to add this new content?",
            field_type="text",
            required=True,
            options=None,
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
