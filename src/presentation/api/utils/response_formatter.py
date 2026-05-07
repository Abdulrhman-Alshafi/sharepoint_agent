"""Utility for formatting success messages after provisioning."""


def get_list_suggested_actions(list_title: str, list_url: str = None) -> list:
    """Return smart call-to-action suggestions after a list is created."""
    actions = [
        f"Add an item to '{list_title}'",
        f"Add more columns to '{list_title}'",
        f"Create a filtered view for '{list_title}'",
        f"Show me all items in '{list_title}'",
    ]
    return actions


def format_provisioning_success_message(spec, dto) -> str:
    """Format a user-friendly success message after provisioning.
    
    Args:
        spec: ResourceSpecification from gathering (can be None for direct provision)
        dto: ProvisionResourcesResponseDTO from provisioning
        
    Returns:
        Formatted success message
    """
    from src.domain.entities.conversation import ResourceType
    
    resource_type = spec.resource_type if spec else None
    
    msg = ""
    if (resource_type == ResourceType.SITE or not spec) and hasattr(dto, "created_sites") and dto.created_sites:
        site_info = dto.created_sites[0]
        site_title = site_info.get("displayName", site_info.get("name", "your site"))
        
        msg = f"✅ **Successfully started provisioning '{site_title}' site!**\n\n"
        msg += "Note: Site creation sometimes takes a few moments to fully resolve."
        
        link = site_info.get("webUrl") or site_info.get("resource_link")
        if link:
            msg += f"\n\n🔗 You can access your new site here: [{link}]({link})"
            
    elif (resource_type == ResourceType.LIST or not spec) and dto.created_lists:
        list_info = dto.created_lists[0]
        list_title = list_info.get("displayName", "your list")
        
        msg = f"✅ **Successfully created '{list_title}' list!**\n\n"
        
        # Show description if provided
        description = list_info.get("description") or (spec.collected_fields.get("description") if spec else None)
        if description:
            msg += f"📝 **Purpose:** {description}\n\n"
        
        # Show columns that were created
        if dto.blueprint.lists and dto.blueprint.lists[0].columns:
            columns = dto.blueprint.lists[0].columns
            msg += f"📋 **Columns created:** {len(columns)}\n"
            for col in columns:  # Show all columns
                required_mark = "✓" if col.required else "○"
                msg += f"  {required_mark} **{col.name}** ({col.type})\n"
        
        msg += f"\n🔗 You can access your list using the link below."
        
        # Add security notice for sensitive lists
        if any(word in list_title.lower() for word in ["salary", "salaries", "payroll", "compensation"]):
            msg += f"\n\n⚠️ **Security Note:** This list contains sensitive employee data. Please configure permissions immediately to restrict access to authorized personnel only."
            
    elif (resource_type == ResourceType.PAGE or not spec) and dto.created_pages:
        _pg = dto.created_pages[0]
        page_title = _pg.get("name") or _pg.get("title") or _pg.get("displayName") or "your page"
        msg = f"✅ **Successfully created '{page_title}' page!**\n\n🔗 You can access your page using the link below."
    
    elif (resource_type == ResourceType.LIBRARY or not spec) and dto.created_document_libraries:
        lib_title = dto.created_document_libraries[0].get("displayName", "your library")
        msg = f"✅ **Successfully created '{lib_title}' document library!**\n\n🔗 You can access your library using the link below."

    elif getattr(dto, "deleted_document_libraries", []):
        deleted_libs = dto.deleted_document_libraries
        if len(deleted_libs) == 1:
            lib_title = deleted_libs[0].get("displayName", "the library")
            msg = f"✅ **Successfully deleted '{lib_title}' document library.**"
        else:
            names = ", ".join(f"'{d.get('displayName', 'library')}' " for d in deleted_libs)
            msg = f"✅ **Successfully deleted {len(deleted_libs)} document libraries:** {names}"

    else:
        # Fallback for other resource types or complex blueprints
        created_count = len(getattr(dto, "created_sites", [])) + len(dto.created_lists) + len(dto.created_pages) + len(dto.created_document_libraries)
        deleted_count = len(getattr(dto, "deleted_document_libraries", []))
        if created_count == 0 and deleted_count == 0:
            if dto.warnings:
                warning_text = "\n".join(f"- {w}" for w in dto.warnings)
                msg = f"❌ **Failed to create resources.**\n\nErrors encountered:\n{warning_text}"
            else:
                msg = "❌ **Failed to create resources due to an unknown API error.**"
        elif created_count == 1:
            msg = f"✅ **Successfully created your resource!**"
        else:
            msg = f"✅ **Successfully created {created_count} resources!**"
            
    if dto.warnings and "❌" not in msg:
        warning_text = "\n".join(f"- {w}" for w in dto.warnings)
        msg += f"\n\n⚠️ **Warnings during creation:**\n{warning_text}"
        
    return msg
