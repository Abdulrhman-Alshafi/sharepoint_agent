"""Utility for building provisioning prompts from specifications."""

import re


def _normalize_folder_paths(value) -> list[str]:
    """Normalize folder paths from string/list input into unique clean paths.

    Harmonizes simple singular/plural root variants so mixed inputs like
    "project, project/2026, projects/2026/Q2" resolve to one hierarchy.
    """
    if not value:
        return []

    if isinstance(value, list):
        raw_parts = value
    else:
        raw_parts = re.split(r"[\n,;]+", str(value))

    root_alias: dict[str, str] = {}
    seen = set()
    paths: list[str] = []
    for part in raw_parts:
        p = str(part).strip().strip("/")
        if not p:
            continue
        if p.lower() in {"none", "skip", "skip folders", "n/a"}:
            continue

        segs = [seg.strip() for seg in p.split("/") if seg.strip()]
        if not segs:
            continue

        root = segs[0]
        root_l = root.lower()
        singular = root_l[:-1] if root_l.endswith("s") else root_l
        plural = singular + "s"

        canonical_root = root_alias.get(root_l) or root_alias.get(singular) or root_alias.get(plural)
        if not canonical_root:
            canonical_root = root
            root_alias[root_l] = canonical_root
            root_alias[singular] = canonical_root
            root_alias[plural] = canonical_root

        segs[0] = canonical_root
        normalized_path = "/".join(segs)

        if normalized_path in seen:
            continue
        seen.add(normalized_path)
        paths.append(normalized_path)
    return paths


def _normalize_metadata_columns(value) -> list[str]:
    """Normalize metadata columns input into ordered unique names."""
    if not value:
        return []

    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[\n,;]+", str(value))

    seen = set()
    cols: list[str] = []
    for part in parts:
        name = str(part).strip().strip("`")
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        cols.append(name)
    return cols


def _normalize_metadata_type_pairs(value) -> list[str]:
    """Normalize metadata type pairs into Name:type list format."""
    if not value:
        return []

    if isinstance(value, list):
        parts = value
    else:
        parts = re.split(r"[\n,;]+", str(value))

    aliases = {
        "string": "text",
        "singleline": "text",
        "single line": "text",
        "multiline": "note",
        "multi line": "note",
        "date": "dateTime",
        "datetime": "dateTime",
        "bool": "boolean",
        "yesno": "boolean",
        "person": "personOrGroup",
        "people": "personOrGroup",
        "user": "personOrGroup",
        "url": "hyperlinkOrPicture",
        "link": "hyperlinkOrPicture",
        "term": "managed_metadata",
        "taxonomy": "managed_metadata",
    }

    normalized: list[str] = []
    seen = set()
    for part in parts:
        token = str(part).strip().strip("`")
        if not token:
            continue
        if ":" not in token:
            continue
        name, col_type = token.split(":", 1)
        name = name.strip()
        col_type_raw = col_type.strip()
        if not name or not col_type_raw:
            continue
        col_type_norm = aliases.get(col_type_raw.lower(), col_type_raw)
        key = f"{name.lower()}:{col_type_norm.lower()}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append(f"{name}:{col_type_norm}")
    return normalized


def build_provisioning_prompt_from_spec(spec) -> str:
    """Convert a ResourceSpecification to a provisioning prompt.
    
    Args:
        spec: ResourceSpecification entity with collected fields
        
    Returns:
        Natural language prompt for the provisioning service
    """
    from src.domain.entities.conversation import ResourceType
    
    fields = spec.collected_fields
    resource_type = spec.resource_type
    
    # Build prompt based on resource type
    if resource_type == ResourceType.SITE:
        title = fields.get("title", "Untitled Site")
        description = fields.get("description", "")
        template = fields.get("template", "Team site (sts)")
        owner_email = fields.get("owner_email", "")
        
        prompt = f"I need you to CREATE A BRAND NEW SharePoint site. The site title is '{title}'."
        if description:
            prompt += f" The site purpose is: {description}."
            
        if "Communication" in template or "sitepagepublishing" in template:
            prompt += " Use the 'sitepagepublishing' template."
        else:
            prompt += " Use the 'sts' template."
            
        if owner_email:
            prompt += f" Set the owner email to '{owner_email}'."
        prompt += " Do NOT create any additional pages, lists, or libraries — only the site itself."

        return prompt
        
    elif resource_type == ResourceType.LIST:
        title = fields.get("title", "Untitled List")
        description = fields.get("description", "")
        columns_str = fields.get("columns", "")
        
        # Build a very explicit CREATE prompt to prevent AI from thinking it's an UPDATE
        prompt = f"I need you to CREATE A BRAND NEW SharePoint list. The list name is '{title}'."
        
        if description:
            prompt += f" This list will be used for: {description}."
        
        # Handle columns
        if columns_str and columns_str == "AI_GENERATED":
            # User wants AI to generate appropriate columns
            prompt += f" Please infer and create appropriate columns based on the list name '{title}' and its purpose."
        elif columns_str:
            # User specified explicit columns
            prompt += f" The list must include these columns: {columns_str}."
        else:
            # No columns specified - ask AI to infer
            prompt += f" Please create suitable columns for this '{title}' list based on its purpose."
        
        # Add sample data request if specified
        if fields.get("add_sample_data") and "yes" in str(fields.get("add_sample_data")).lower():
            prompt += " Also populate the list with sample data."
            
        # Make it explicitly clear this is a CREATE action, not UPDATE
        prompt += " IMPORTANT: This is a CREATE operation for a new list. Do not update any existing lists. Set action to CREATE."
        prompt += " Do NOT create any sites, pages, or document libraries — ONLY create the requested list."
            
        return prompt
    
    elif resource_type == ResourceType.PAGE:
        title = fields.get("title", "Untitled Page")
        content_type = fields.get("content_type", "")
        sections = fields.get("sections", "")
        
        prompt = f"I need you to CREATE A BRAND NEW SharePoint page called '{title}'."
        if content_type:
            prompt += f" The page type/purpose is: {content_type}."
        
        # Handle sections
        sections_lower = (sections or "").lower().strip()
        _ai_sections = not sections_lower
        
        if _ai_sections:
            prompt += (
                " Design the best layout with appropriate web parts for this page's purpose."
                " Include a hero banner, relevant content sections, and quick links."
            )
        else:
            prompt += f" The page should include these sections/web parts: {sections}."
            
        prompt += " IMPORTANT: You MUST generate at least one webpart object (type='rte' for text, or suitable types for dashboards) in the webparts array. Set action to CREATE."
        prompt += " Do NOT create any sites, lists, or document libraries — ONLY create the requested page."
        
        return prompt
    
    elif resource_type == ResourceType.LIBRARY:
        title = fields.get("title", "Untitled Library")
        description = fields.get("description", "")
        description_lower = str(description).lower().strip()
        metadata_pref = str(fields.get("add_metadata_columns", "")).lower()
        metadata_columns = fields.get("metadata_columns", "")
        metadata_column_types = fields.get("metadata_column_types", "")
        metadata_column_types_lower = str(metadata_column_types).lower().strip()
        metadata_column_names = _normalize_metadata_columns(metadata_columns)
        metadata_type_pairs = _normalize_metadata_type_pairs(metadata_column_types)
        folder_paths = _normalize_folder_paths(fields.get("folder_paths", ""))
        
        prompt = f"I need you to CREATE A BRAND NEW SharePoint document library. The library name is '{title}'."
        if description and description != "AI_GENERATED_DESCRIPTION":
            prompt += f" Description: {description}."
        elif description_lower in {
            "ai_generated_description",
            "generate description",
            "generate a description",
            "write description",
            "write a description",
            "create description",
            "gentate descrption",
        }:
            prompt += (
                " Generate a concise, professional library description based on the library name"
                " and intended business use."
            )
        
        # Add versioning if specified
        if fields.get("enable_versioning"):
            prompt += " Enable versioning."

        # Add metadata columns request
        if "yes" in metadata_pref:
            if metadata_columns == "SKIP_METADATA_COLUMNS":
                # Explicit user intent: do not add any metadata columns.
                pass
            elif metadata_columns == "AI_GENERATED":
                prompt += (
                    " Please generate suitable library metadata columns based on the library name and description."
                    " Include practical fields like document type, owner, department, and review/expiry dates where relevant."
                    " Output them in document_libraries[].columns with objects shaped as {name, type, required}."
                )
            elif metadata_columns:
                prompt += f" The library must include these metadata columns: {', '.join(metadata_column_names) if metadata_column_names else metadata_columns}."
                if metadata_type_pairs:
                    prompt += (
                        " Use this exact type format for metadata columns (same format as list columns): "
                        f"{', '.join(metadata_type_pairs)}."
                    )
                elif metadata_column_types_lower == "ai_generated" or any(
                    phrase in metadata_column_types_lower
                    for phrase in ["you make them", "you decide", "same as list", "infer types", "generate types"]
                ):
                    prompt += (
                        " Infer the best data type for each metadata column using list-style format Name:type"
                        " (for example Owner:personOrGroup, Review Date:dateTime)."
                    )
                else:
                    prompt += " Infer practical types for the listed metadata columns if the user did not provide types explicitly."

                prompt += " CRITICAL: Populate document_libraries[].columns with objects {name, type, required}."
            else:
                prompt += " Please suggest and add useful metadata columns for this library."
        
        # Add folders to seed_data if specified
        if folder_paths:
            folder_paths_text = ", ".join(folder_paths)
            prompt += (
                f"\n\nIMPORTANT: The user wants these folders created in the library:\n{folder_paths_text}\n"
                "You MUST include these folders in the seed_data array with type='folder_path'. "
                "For example, if user wants 'HR' and 'Finance' folders, create seed_data like:\n"
                '  [\n'
                '    {"type": "folder_path", "name": "HR"},\n'
                '    {"type": "folder_path", "name": "Finance"}\n'
                '  ]\n'
                "For nested paths like 'Projects/2026/Q1', create:\n"
                '  {"type": "folder_path", "name": "Projects/2026/Q1"}\n'
                "Handle nested paths by using '/' as the path separator. "
                "IMPORTANT: parent folders are implicit and must be created automatically "
                "(e.g., Projects/2026/Q1 requires Projects and Projects/2026 to exist)."
            )
        
        prompt += " IMPORTANT: This is a CREATE operation for a new document library. Set action to CREATE."
        prompt += " Do NOT create any sites, lists, or pages — ONLY create the requested document library."
        
        return prompt
    
    else:
        # Fallback for other resource types
        title = fields.get("title", "Untitled Resource")
        return f"Create a {resource_type.value.lower()} called '{title}'"
