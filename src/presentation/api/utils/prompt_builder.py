"""Utility for building provisioning prompts from specifications."""


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
        site_content = fields.get("site_content", "You choose the best setup")
        
        prompt = f"I need you to CREATE A BRAND NEW SharePoint site. The site title is '{title}'."
        if description:
            prompt += f" The site purpose is: {description}."
            
        if "Communication" in template or "sitepagepublishing" in template:
            prompt += " Use the 'sitepagepublishing' template."
        else:
            prompt += " Use the 'sts' template."
            
        if owner_email:
            prompt += f" Set the owner email to '{owner_email}'."
        
        # Handle site content / child resources
        site_content_lower = site_content.lower().strip() if site_content else ""
        _ai_decides = any(phrase in site_content_lower for phrase in [
            "you choose", "you decide", "best setup", "you pick", "ai decide",
            "auto", "recommend", "suggest",
        ])
        _no_extras = any(phrase in site_content_lower for phrase in [
            "just the site", "no extras", "none", "nothing", "only the site",
        ])
        
        if _no_extras:
            prompt += " Do NOT create any additional pages, lists, or libraries — only the site itself."
        elif _ai_decides:
            prompt += (
                f" Also create the best pages, lists, and document libraries for a '{title}' site."
                f" Include a welcoming Home page with a hero banner, quick links, and relevant content."
                f" Add any lists and document libraries that would be useful for this site's purpose."
            )
        else:
            prompt += f" The site should include these resources: {site_content}."
            
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
            
        return prompt
    
    elif resource_type == ResourceType.PAGE:
        title = fields.get("title", "Untitled Page")
        content_type = fields.get("content_type", "")
        sections = fields.get("sections", "")
        main_content = fields.get("main_content", "")
        
        prompt = f"I need you to CREATE A BRAND NEW SharePoint page called '{title}'."
        if content_type:
            prompt += f" The page type/purpose is: {content_type}."
        
        # Handle sections
        sections_lower = (sections or "").lower().strip()
        _ai_sections = any(phrase in sections_lower for phrase in [
            "you choose", "you decide", "ai decide", "auto", "recommend",
        ]) or not sections_lower
        
        if _ai_sections:
            prompt += (
                " Design the best layout with appropriate web parts for this page's purpose."
                " Include a hero banner, relevant content sections, and quick links."
            )
        else:
            prompt += f" The page should include these sections/web parts: {sections}."
        
        # Handle content
        main_content_lower = (main_content or "").lower().strip()
        _ai_content = any(phrase in main_content_lower for phrase in [
            "generate", "you decide", "you choose", "ai", "auto",
        ]) or not main_content_lower
        
        if _ai_content:
            prompt += (
                " Generate professional, engaging content for all sections."
                " Write compelling hero titles, descriptions, and body text."
            )
        else:
            prompt += f" The main content to display is: {main_content}."
            
        prompt += " IMPORTANT: You MUST generate at least one webpart object (type='rte' for text, or suitable types for dashboards) in the webparts array. Set action to CREATE."
        
        return prompt
    
    elif resource_type == ResourceType.LIBRARY:
        title = fields.get("title", "Untitled Library")
        description = fields.get("description", "")
        
        prompt = f"I need you to CREATE A BRAND NEW SharePoint document library. The library name is '{title}'."
        if description:
            prompt += f" Description: {description}."
        
        # Add versioning if specified
        if fields.get("enable_versioning"):
            prompt += " Enable versioning."
        
        # Add permission info
        needs_permissions = fields.get("needs_permissions", "")
        if needs_permissions and "no" in str(needs_permissions).lower():
            prompt += " No special permissions needed - default access for everyone."
        elif fields.get("permission_groups"):
            prompt += f" Permission groups: {fields.get('permission_groups')}."
        
        prompt += " IMPORTANT: This is a CREATE operation for a new document library. Set action to CREATE."
        
        return prompt
    
    else:
        # Fallback for other resource types
        title = fields.get("title", "Untitled Resource")
        return f"Create a {resource_type.value.lower()} called '{title}'"
