"""AI blueprint generator using Gemini."""

from src.domain.entities import (
    ProvisioningBlueprint, SPSite, SPList, SPPage, CustomWebPartCode,
    DocumentLibrary, SharePointGroup, PermissionLevel,
    PromptValidationResult,
    TermSet, ContentType, SPView, WorkflowScaffold
)
from src.domain.value_objects import SPColumn, WebPart
from src.domain.services import BlueprintGeneratorService
from src.domain.exceptions import BlueprintGenerationException
from src.infrastructure.external_services.ai_client_factory import get_instructor_client
from src.infrastructure.schemas.validation_schemas import ValidationModel
from src.infrastructure.schemas.blueprint_schemas import ProvisioningBlueprintModel
from src.infrastructure.logging import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "You are a React expert, Microsoft 365 architect, and SharePoint provisioning specialist. "
    "Translate business needs into precise technical provisioning blueprints. "
    "Set the appropriate 'action' (CREATE, UPDATE, DELETE) for each resource. "
    "IMPORTANT: JSON keys MUST exactly match the requested schema (snake_case). \n\n"
    "CRITICAL - LISTS & COLUMNS: Every SharePoint list in the 'lists' array MUST have at least one column defined in the 'columns' array. "
    "If the user doesn't specify columns, infer appropriate columns based on the list purpose. "
    "For example: Task list → Title, Description, Status, Priority, Due Date. "
    "Contact list → Title, Email, Phone, Department. "
    "NEVER create a list with an empty 'columns' array.\n\n"
    "PERSON & GROUP COLUMNS (CRITICAL): When a column represents a person, employee, assignee, "
    "manager, owner, contact, team member, or any human — you MUST set its type to 'personOrGroup'. "
    "NEVER use 'text' for columns that hold people's names. "
    "Examples: Employee → personOrGroup, Assigned To → personOrGroup, Manager → personOrGroup, "
    "Nominated By → personOrGroup, Reviewer → personOrGroup.\n"
    "For 'personOrGroup' columns in seed_data, use the person's EMAIL ADDRESS as the value "
    "(e.g., 'ahmed@company.com'). If real tenant users are provided below, use ONLY those emails.\n\n"
    "NEW SITES: When a user asks to 'create a site', 'workspace', or 'intranet', populate the 'sites' array. "
    "Each site needs a 'title', 'name' (url slug), 'description', and 'template' (either 'sts' for Team site or 'sitepagepublishing' for Communication site). \n\n"
    "PAGES & WEBPARTS: Every site MUST include at least 2-3 pages in the 'pages' array. "
    "Each page MUST have at least 1 webpart. Use a Hero webpart on home pages, Text webparts for content pages. "
    "Always set webpart 'type' to one of: Text, Hero, Image, QuickLinks, News, People, List, DocumentLibrary, Events. "
    "Never leave the 'webparts' array empty on any page.\n\n"
    "DOCUMENT LIBRARIES: When any request involves file storage, uploads, documents, or attachments, "
    "use 'document_libraries' (not 'lists'). A document library uses template 'documentLibrary'. \n\n"
    "FOLDER CREATION IN LIBRARIES: When the user specifies folders to create (e.g., 'create HR, Finance, Legal folders'), "
    "you MUST populate the library's seed_data array with folder entries. Each folder entry MUST have: "
    "{'type': 'folder_path', 'name': 'FolderName'} or for nested paths {'type': 'folder_path', 'name': 'Parent/Child/Nested'}. "
    "Examples:\n"
    "  - User says 'create HR and Finance folders' → seed_data: [{'type': 'folder_path', 'name': 'HR'}, {'type': 'folder_path', 'name': 'Finance'}]\n"
    "  - User says 'create Projects/2026/Q1' → seed_data: [{'type': 'folder_path', 'name': 'Projects/2026/Q1'}]\n"
    "Always include folder entries in seed_data so they are created during provisioning.\n\n"
    "SHAREPOINT GROUPS & PERMISSIONS: When role-based access is needed (e.g., 'only HR can upload', "
    "'managers can edit'), you MUST populate 'groups'. Each group entry must specify: "
    "'name' (e.g., 'HR Members'), 'permission_level' (one of: 'Read', 'Contribute', 'Edit', 'Full Control'), "
    "and 'target_library_title'. Always create at minimum TWO groups for libraries: one with 'Contribute' "
    "for uploaders, and one with 'Read' for viewers. \n\n"
    "ENTERPRISE ARCHITECTURE: \n"
    "1. Managed Metadata: Use 'term_sets' for global enterprise dictionaries (e.g., 'Departments'). \n"
    "2. Content Types: Use 'content_types' for reusable document schemas (e.g., 'Policy Document'). \n"
    "3. Seed Data: If the user asks to add items, tasks, or 'populate' the list, you MUST heavily populate the 'seed_data' array with appropriate sample JSON objects matching the list's schema. \n"
    "4. Custom UI: When a user asks for a 'custom' UI, generate a single-file React component and its SCSS."
)

VALIDATION_PROMPT = (
    "You are a SharePoint governance and compliance validator. "
    "Analyze the following provisioning request and determine if it is valid for a professional enterprise environment.\n\n"
    "CHECK THE FOLLOWING:\n"
    "1. Are all resource names reasonable? Short or generic names like 'Doc', 'Files', 'HR', 'Reports' are PERFECTLY ACCEPTABLE. "
    "Only reject names that are clearly gibberish (e.g., 'asdfgh', 'xxxxx'), offensive, or completely unrelated to work.\n"
    "2. Are permission levels appropriate? If 'Full Control' is requested, set risk_level='high' and add a warning. "
    "If 'Contribute' or 'Edit' is requested for sensitive resources, set risk_level='medium'.\n"
    "3. Does the request make business sense for a SharePoint/M365 environment? "
    "Reject requests that are clearly off-topic (ordering food, playing games, etc).\n\n"
    "RULES:\n"
    "- Be PERMISSIVE. Set is_valid=true for virtually all legitimate enterprise requests. Users can name resources however they want.\n"
    "- Set is_valid=false ONLY if the request is clearly nonsensical, off-topic, or offensive. Short or simple names are NEVER a reason to reject a request.\n"
    "- IMPORTANT: Short follow-up commands like 'add data to it', 'update it', or 'yes' MUST be considered valid (is_valid=true) rather than rejected as unclear, since they rely on previous conversational context.\n"
    "- Set is_valid=true for anything that is a legitimate enterprise request, even if risky.\n"
    "- For risky but valid requests, set is_valid=true but provide warnings explaining the risk and asking if the user is sure.\n"
    "- Always provide a clear rejection_reason if is_valid=false.\n"
    "- CRITICAL: A word like 'salary', 'HR', 'payroll', 'finance' is a RESOURCE NAME (library or list name), NOT sensitive data. "
    "Deleting or modifying a LIBRARY named 'Salary' is a standard LOW-to-MEDIUM risk operation — it is NOT high-risk merely because of the name. "
    "Only flag as high-risk if the action itself is destructive AND irreversible, e.g. permanently deleting many records with no recycle bin."
)



class GeminiAIBlueprintGenerator(BlueprintGeneratorService):
    """Implementation of blueprint generator using flexible AI."""

    def __init__(self):
        try:
            self.client, self.model = get_instructor_client()
        except Exception as e:
            raise BlueprintGenerationException(f"Failed to initialize AI client: {str(e)}")

    async def validate_prompt(self, prompt: str) -> PromptValidationResult:
        """Validate a user prompt before generating a blueprint."""
        try:
            kwargs = {
                "messages": [{"role": "user", "content": f"{VALIDATION_PROMPT}\n\nUser Request: {prompt}"}],
                "response_model": ValidationModel,
            }
            if self.model:  # Only pass model for non-Gemini providers
                kwargs["model"] = self.model
            response = self.client.chat.completions.create(**kwargs)

            return PromptValidationResult(
                is_valid=response.is_valid,
                risk_level=response.risk_level,
                warnings=response.warnings,
                rejection_reason=response.rejection_reason,
            )
        except Exception as e:
            logger.error("Prompt validation AI call failed: %s", e, exc_info=True)
            return PromptValidationResult(is_valid=False, risk_level="low", rejection_reason="Validation service unavailable")

    async def generate_blueprint(self, prompt: str, tenant_users: list = None) -> ProvisioningBlueprint:
        """Generate a provisioning blueprint using Gemini AI.
        
        Args:
            prompt: User request text
            tenant_users: Optional list of real tenant user dicts
                          [{"displayName": ..., "email": ...}, ...]
        """
        try:
            # Build prompt with optional tenant user context
            full_prompt = SYSTEM_PROMPT
            if tenant_users:
                from src.infrastructure.services.tenant_users_service import TenantUsersService
                user_context = TenantUsersService.format_for_prompt(tenant_users)
                if user_context:
                    full_prompt += (
                        f"\n\nTENANT USER DIRECTORY:\n{user_context}\n"
                        "IMPORTANT: For any 'personOrGroup' column in seed_data, "
                        "use ONLY the email addresses from the list above. "
                        "Do NOT invent or fabricate user names or emails."
                    )
            
            kwargs = {
                "messages": [
                    {"role": "user", "content": f"{full_prompt}\n\nUser Request: {prompt}"}
                ],
                "response_model": ProvisioningBlueprintModel,
            }
            if self.model:  # Only pass model for non-Gemini providers
                kwargs["model"] = self.model
            response = self.client.chat.completions.create(**kwargs)

            sites = [
                SPSite(
                    title=site.title,
                    description=site.description,
                    name=site.name,
                    template=site.template,
                    owner_email=site.owner_email,
                    action=site.action
                )
                for site in response.sites
            ]

            lists = []
            for lst in response.lists:
                # Validate columns before creating SPList
                columns_data = [
                    SPColumn(
                        name=col.name, type=col.type, required=col.required,
                        choices=col.choices, lookup_list=col.lookup_list, term_set_id=col.term_set_id
                    )
                    for col in lst.columns
                ]
                
                # Skip lists with no columns if action is CREATE/UPDATE, or raise descriptive error
                if lst.action != "DELETE" and len(columns_data) == 0:
                    logger.warning(f"AI generated list '{lst.title}' with no columns. Full list data: {lst.model_dump()}")
                    raise BlueprintGenerationException(
                        f"AI generated list '{lst.title}' without any columns. "
                        f"Please provide more details about what columns/fields this list should have. "
                        f"For example: 'Create a task list with Title, Description, Due Date, and Priority columns'"
                    )
                
                lists.append(SPList(
                    title=lst.title,
                    description=lst.description,
                    columns=columns_data,
                    content_types=getattr(lst, 'content_types', []),
                    seed_data=getattr(lst, 'seed_data', []),
                    template=getattr(lst, 'template', 'genericList'),
                    action=lst.action
                ))

            pages = [
                SPPage(
                    title=pg.title,
                    webparts=[
                        WebPart(type=wp.type, properties=wp.properties, id=wp.id)
                        for wp in pg.webparts
                    ],
                    action=pg.action
                )
                for pg in response.pages
            ]

            custom_components = [
                CustomWebPartCode(
                    component_name=component.component_name,
                    tsx_content=component.tsx_content,
                    scss_content=component.scss_content
                )
                for component in response.custom_components
            ]

            document_libraries = [
                DocumentLibrary(
                    title=lib.title,
                    description=lib.description,
                    content_types=lib.content_types,
                    seed_data=lib.seed_data,
                    action=lib.action
                )
                for lib in response.document_libraries
            ]

            groups = [
                SharePointGroup(
                    name=grp.name,
                    description=grp.description,
                    permission_level=PermissionLevel(grp.permission_level)
                    if grp.permission_level in [p.value for p in PermissionLevel]
                    else PermissionLevel.READ,
                    target_library_title=grp.target_library_title,
                    action=grp.action
                )
                for grp in response.groups
            ]


            term_sets = [
                TermSet(name=ts.name, terms=ts.terms, group_name=ts.group_name, action=ts.action)
                for ts in response.term_sets
            ]

            content_types = [
                ContentType(name=ct.name, description=ct.description, parent_type=ct.parent_type, columns=ct.columns, action=ct.action)
                for ct in response.content_types
            ]

            views = [
                SPView(title=v.title, target_list_title=v.target_list_title, columns=v.columns, row_limit=v.row_limit, query=v.query, action=v.action)
                for v in response.views
            ]

            workflows = [
                WorkflowScaffold(name=wf.name, trigger_type=wf.trigger_type, target_list_title=wf.target_list_title, actions=wf.actions, action=wf.action)
                for wf in response.workflows
            ]

            return ProvisioningBlueprint(
                reasoning=response.reasoning,
                sites=sites,
                lists=lists,
                pages=pages,
                custom_components=custom_components,
                document_libraries=document_libraries,
                groups=groups,
                term_sets=term_sets,
                content_types=content_types,
                views=views,
                workflows=workflows,
            )
        except Exception as e:
            raise BlueprintGenerationException(f"Failed to generate blueprint: {str(e)}")
