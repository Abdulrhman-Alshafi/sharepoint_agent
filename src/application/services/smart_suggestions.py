"""Smart contextual suggestions for requirement gathering questions.

Generates intelligent quick-action suggestions for every question in the
multi-turn gathering flow, based on:
  - The resource type being created
  - The specific field being asked about
  - The user's original prompt
  - Previously collected field values
"""

from typing import List, Dict, Any, Optional
from src.domain.entities.conversation import ResourceType


def generate_smart_suggestions(
    resource_type: ResourceType,
    field_name: str,
    original_prompt: str,
    collected_fields: Dict[str, Any],
) -> List[str]:
    """Return 2-4 contextual quick-suggestion strings.

    The caller can pass these straight into ``ChatResponse.quick_suggestions``.
    """
    prompt_lower = original_prompt.lower().strip()

    # Dispatch to per-resource-type generators
    generator = _GENERATORS.get(resource_type)
    if generator:
        suggestions = generator(field_name, prompt_lower, original_prompt, collected_fields)
        if suggestions:
            # Filter out empty/whitespace-only strings
            return [s for s in suggestions if s and s.strip()]

    # Fallback: no suggestions for unknown combos
    return []


# ---------------------------------------------------------------------------
# Per-resource-type generators
# ---------------------------------------------------------------------------

def _extract_subject(prompt_lower: str, resource_words: List[str], original_prompt: str = "") -> str:
    """Try to extract the subject/topic from the prompt.

    E.g. "create a view for Milestones list" → "Milestones"
         "create an HR list" → "HR"

    Uses the *original* (non-lowered) prompt to preserve the user's
    capitalisation (e.g. "HR" stays "HR", not "Hr").
    """
    import re

    # We search the lowered prompt for pattern matching but slice from
    # the original prompt to keep the user's casing.
    orig = original_prompt or prompt_lower

    def _grab_original(match_obj) -> str:
        """Return the matched group from the *original* prompt using the
        span offsets obtained from the lowered prompt."""
        start, end = match_obj.span(1)
        return orig[start:end].strip()

    rw_pattern = "|".join(re.escape(w) for w in resource_words)

    # "for <Subject>" pattern
    m = re.search(r"\b(?:for|about|on)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9 ]*?)(?:\s+(?:" + rw_pattern + r")|\s*$|[.,!?])", prompt_lower, re.IGNORECASE)
    if m:
        subj = _grab_original(m)
        if subj.lower() not in resource_words and len(subj) > 1:
            return subj

    # "called/named <Subject>" pattern
    m = re.search(r"\b(?:called|named|titled?)\s+['\"]?([A-Za-z][A-Za-z0-9 ]+?)['\"]?(?:\s+(?:" + rw_pattern + r")|\s*$|[.,!?])", prompt_lower, re.IGNORECASE)
    if m:
        subj = _grab_original(m)
        if subj.lower() not in resource_words and len(subj) > 1:
            return subj

    # "<Subject> list/library/..." right after create
    m = re.search(r"\bcreate\s+(?:a\s+|an\s+)?(?:new\s+)?([A-Za-z][A-Za-z0-9 ]+?)\s+(?:" + rw_pattern + r")", prompt_lower, re.IGNORECASE)
    if m:
        subj = _grab_original(m)
        stop = {"a", "an", "the", "new", "my", "our"} | set(resource_words)
        if subj.lower() not in stop and len(subj) > 1:
            return subj

    return ""


# ── VIEW ──────────────────────────────────────────────────────────────────

def _view_suggestions(field_name: str, prompt_lower: str, original_prompt: str, collected: Dict[str, Any]) -> List[str]:
    target_list = collected.get("target_list", "")

    if field_name == "title":
        if target_list:
            return [
                f"All {target_list}",
                f"Active {target_list}",
                f"{target_list} Overview",
            ]
        subj = _extract_subject(prompt_lower, ["view", "list"], original_prompt)
        if subj:
            return [f"All {subj}", f"Active {subj}", f"{subj} Overview"]
        return ["All Items", "Active Items", "My Items"]

    if field_name == "target_list":
        # Can't suggest real list names without API access — give common examples
        return ["Tasks", "Milestones", "Issues"]

    if field_name == "columns":
        return ["Title, Status, Due Date", "All columns", "You decide"]

    if field_name == "sort_by":
        return [
            "Created: descending",
            "Title: ascending",
            "Modified: descending",
        ]

    return []


# ── LIST ──────────────────────────────────────────────────────────────────

def _list_suggestions(field_name: str, prompt_lower: str, original_prompt: str, collected: Dict[str, Any]) -> List[str]:
    title = collected.get("title", "")
    subj = title or _extract_subject(prompt_lower, ["list", "tracker", "directory", "registry", "inventory"], original_prompt)

    if field_name == "title":
        if subj:
            return [subj, f"{subj} Tracker", f"{subj} Registry"]
        return ["Project Tracker", "Task List", "Issue Log"]

    if field_name == "description":
        if subj:
            return [
                f"Tracks all {subj.lower()} information",
                f"Central {subj.lower()} management list",
                "",  # blank = skip
            ]
        return ["General purpose tracking list", ""]

    if field_name == "columns":
        # Suggest columns contextualised to the list topic
        topic = (title or subj).lower()
        if any(w in topic for w in ["task", "todo", "to-do", "action"]):
            return ["Title, Status, Priority, Due Date, Assigned To", "You decide"]
        if any(w in topic for w in ["employee", "contact", "people", "staff", "directory"]):
            return ["Title, Email, Phone, Department, Role", "You decide"]
        if any(w in topic for w in ["project", "initiative"]):
            return ["Title, Status, Start Date, End Date, Owner, Budget", "You decide"]
        if any(w in topic for w in ["issue", "bug", "defect", "incident"]):
            return ["Title, Severity, Status, Reported By, Assigned To", "You decide"]
        if any(w in topic for w in ["milestone"]):
            return ["Title, Target Date, Status, Owner, Progress", "You decide"]
        if any(w in topic for w in ["inventory", "asset", "equipment"]):
            return ["Title, Category, Quantity, Location, Status", "You decide"]
        if any(w in topic for w in ["event", "calendar", "meeting"]):
            return ["Title, Date, Time, Location, Organizer", "You decide"]
        if any(w in topic for w in ["expense", "budget", "cost", "finance", "salary"]):
            return ["Title, Amount, Category, Date, Approved By", "You decide"]
        return ["Title, Status, Priority, Due Date", "You decide"]

    if field_name == "column_types":
        cols_raw = collected.get("columns", "")
        if cols_raw and cols_raw != "AI_GENERATED":
            # Try to auto-suggest types for common column names
            suggestions = _infer_column_types(cols_raw)
            if suggestions:
                return [suggestions, "You decide"]
        return ["Status:choice, Priority:choice, Due Date:dateTime", "You decide"]

    if field_name == "add_sample_data":
        return ["Yes, add sample data", "No, I'll add data myself"]

    return []


def _infer_column_types(columns_text: str) -> str:
    """Infer column types from column names."""
    type_map = {
        "status": "choice", "priority": "choice", "category": "choice",
        "severity": "choice", "type": "choice", "department": "choice",
        "role": "choice", "level": "choice",
        "due date": "dateTime", "start date": "dateTime", "end date": "dateTime",
        "target date": "dateTime", "date": "dateTime", "deadline": "dateTime",
        "created": "dateTime", "modified": "dateTime",
        "email": "text", "phone": "text", "name": "text",
        "description": "text", "notes": "text", "comments": "text",
        "amount": "number", "budget": "number", "cost": "number",
        "quantity": "number", "count": "number", "price": "number",
        "progress": "number", "percentage": "number",
        "active": "boolean", "completed": "boolean", "approved": "boolean",
        "is active": "boolean",
    }
    cols = [c.strip() for c in columns_text.split(",") if c.strip()]
    parts = []
    for col in cols:
        col_lower = col.lower()
        if col_lower == "title":
            continue  # Title is built-in
        matched_type = None
        for keyword, col_type in type_map.items():
            if keyword in col_lower:
                matched_type = col_type
                break
        if matched_type:
            parts.append(f"{col}:{matched_type}")
        else:
            parts.append(f"{col}:text")
    return ", ".join(parts) if parts else ""


# ── SITE ──────────────────────────────────────────────────────────────────

def _site_suggestions(field_name: str, prompt_lower: str, original_prompt: str, collected: Dict[str, Any]) -> List[str]:
    title = collected.get("title", "")
    subj = title or _extract_subject(prompt_lower, ["site", "workspace", "intranet", "team", "communication"], original_prompt)

    if field_name == "title":
        if subj:
            return [subj, f"{subj} Hub", f"{subj} Portal"]
        return ["Team Workspace", "Project Hub", "Department Portal"]

    if field_name == "description":
        if subj:
            return [
                f"Central hub for {subj.lower()} collaboration",
                f"{subj} team workspace and resources",
                "",
            ]
        return ["Team collaboration workspace", "Company information portal", ""]

    if field_name == "template":
        return ["Team site (sts)", "Communication site (sitepagepublishing)"]

    if field_name == "owner_email":
        return ["Skip (use default)", ""]

    return []


# ── PAGE ──────────────────────────────────────────────────────────────────

def _page_suggestions(field_name: str, prompt_lower: str, original_prompt: str, collected: Dict[str, Any]) -> List[str]:
    title = collected.get("title", "")
    subj = title or _extract_subject(prompt_lower, ["page", "dashboard", "landing"], original_prompt)

    if field_name == "title":
        if subj:
            return [subj, f"{subj} Dashboard", f"{subj} Overview"]
        return ["Home", "Welcome", "Team Dashboard"]

    if field_name == "content_type":
        return [
            "Text and information",
            "Dashboard with charts",
            "List of links",
            "News and announcements",
            "Team overview",
        ]

    if field_name == "sections":
        topic = (title or subj).lower() if (title or subj) else ""
        if any(w in topic for w in ["home", "welcome", "landing"]):
            return ["You choose", "Hero banner, Quick links, News feed", "Hero banner, Text content, People"]
        if any(w in topic for w in ["team", "member", "staff"]):
            return ["You choose", "Hero banner, People, Quick links", "Hero banner, Text content"]
        if any(w in topic for w in ["news", "announce", "update"]):
            return ["You choose", "Hero banner, News feed, Text content", "Hero banner, Quick links"]
        if any(w in topic for w in ["dashboard", "report", "status"]):
            return ["You choose", "Hero banner, List, Quick links", "Hero banner, Text content"]
        return ["You choose", "Hero banner, Quick links, News feed", "Hero banner, Text content, People"]

    if field_name == "main_content":
        if subj:
            return [
                "Generate it for me",
                f"Welcome to the {subj.lower()} page. Here you'll find all relevant information and resources.",
                f"Overview and key details about {subj.lower()}.",
            ]
        return [
            "Generate it for me",
            "Welcome to our page!",
        ]

    return []


# ── LIBRARY ───────────────────────────────────────────────────────────────

def _library_suggestions(field_name: str, prompt_lower: str, original_prompt: str, collected: Dict[str, Any]) -> List[str]:
    title = collected.get("title", "")
    subj = title or _extract_subject(prompt_lower, ["library", "document", "file", "storage", "repository"], original_prompt)

    if field_name == "title":
        if subj:
            return [subj, f"{subj} Documents", f"{subj} Files"]
        return ["Project Documents", "Shared Files", "Team Resources"]

    if field_name == "description":
        if subj:
            return [
                f"Storage for {subj.lower()} documents and files",
                f"Centralized {subj.lower()} file repository",
                "",
            ]
        return ["General document storage", "Team shared files", ""]

    if field_name == "create_folders":
        return ["Yes, create folders now", "No folders for now"]

    if field_name == "folder_paths":
        if subj:
            return [
                f"{subj}/Policies, {subj}/Templates, {subj}/Archives",
                f"{subj}/2026/Q1\n{subj}/2026/Q2",
            ]
        return [
            "General, Templates, Archive",
            "Projects/2026/Q1, Projects/2026/Q2",
        ]

    return []


# ── GROUP ─────────────────────────────────────────────────────────────────

def _group_suggestions(field_name: str, prompt_lower: str, original_prompt: str, collected: Dict[str, Any]) -> List[str]:
    subj = _extract_subject(prompt_lower, ["group", "permission", "access", "security"], original_prompt)

    if field_name == "name":
        if subj:
            return [f"{subj} Members", f"{subj} Contributors", f"{subj} Viewers"]
        return ["Team Members", "Project Contributors", "Site Viewers"]

    if field_name == "permission_level":
        return [
            "Read (view only)",
            "Contribute (view and add)",
            "Edit (view, add, edit)",
            "Full Control (all permissions)",
        ]

    if field_name == "target_resource":
        return ["Site-wide access", ""]

    return []


# ── CONTENT TYPE ──────────────────────────────────────────────────────────

def _content_type_suggestions(field_name: str, prompt_lower: str, original_prompt: str, collected: Dict[str, Any]) -> List[str]:
    name = collected.get("name", "")
    subj = name or _extract_subject(prompt_lower, ["content type", "document type", "type"], original_prompt)

    if field_name == "name":
        if subj:
            return [subj, f"{subj} Document", f"{subj} Record"]
        return ["Policy Document", "Project Report", "Meeting Notes"]

    if field_name == "description":
        if subj:
            return [
                f"Content type for {subj.lower()} documents",
                f"Standardized {subj.lower()} format",
            ]
        return ["Standard document format", "Reusable content schema"]

    if field_name == "parent_type":
        return ["Item", "Document", "Folder"]

    return []


# ── DISPATCHER ────────────────────────────────────────────────────────────

_GENERATORS = {
    ResourceType.VIEW: _view_suggestions,
    ResourceType.LIST: _list_suggestions,
    ResourceType.SITE: _site_suggestions,
    ResourceType.PAGE: _page_suggestions,
    ResourceType.LIBRARY: _library_suggestions,
    ResourceType.GROUP: _group_suggestions,
    ResourceType.CONTENT_TYPE: _content_type_suggestions,
}
