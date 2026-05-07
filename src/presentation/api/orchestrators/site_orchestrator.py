"""Handler for SharePoint site operations."""

from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import (
    get_logger, error_response,
    PendingAction, store_pending_action, pop_pending_action,
)

logger = get_logger(__name__)


async def _dispatch_site_operation(operation, session_id: str, site_id: str, repository) -> "ChatResponse":
    """Execute a single pre-parsed SiteOperation against the repository."""
    # Re-synthesise a natural-language message so the existing handler can route it
    # via its full if/elif chain without duplicating logic.
    op = operation.operation
    name = operation.site_name or operation.site_title or ""
    email = operation.user_email or ""
    desc = operation.site_description or ""
    template = operation.site_template or "Team"

    synthetic_map = {
        "create": f"Create a {template} site called {name}. {desc}".strip(),
        "delete": f"Delete the site named {name}",
        "update_theme": f"Update theme of site {name}",
        "add_member": f"Add {email} as a member of site {name}",
        "add_owner": f"Add {email} as owner of site {name}",
        "remove_member": f"Remove {email} from site {name}",
        "navigation": f"Update navigation for site {name}",
        "recycle_bin": f"Show recycle bin items for site {name or 'current'}",
        "empty_recycle_bin": f"Empty the recycle bin for site {name or 'current'}",
        "restore_item": f"Restore recycle bin item from site {name}",
        "get_storage": f"Get storage information for site {name}",
        "get_analytics": f"Get analytics for site {name}",
    }
    synthetic = synthetic_map.get(op, f"{op} site {name}")
    return await handle_site_operations(synthetic, session_id, site_id)


async def handle_site_operations(message: str, session_id: str, site_id: str, user_token: str = None, user_login_name: str = "") -> ChatResponse:
    """Handle site operations (create site, add members, navigation, recycle bin, etc.)."""
    from src.presentation.api import get_repository
    from src.infrastructure.external_services.site_operation_parser import (
        SiteOperationParserService, SiteOperationBatchParserService,
    )
    from src.domain.entities.core import SPSite
    import asyncio
    
    try:
        repository = get_repository(user_token=user_token)
        
        # Parse — may return multiple operations for batch requests
        operations = await SiteOperationBatchParserService.parse(message)

        if not operations:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the site operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Create a new team site called Marketing'\n"
                       "- 'Add john@company.com as a member of the HR site'\n"
                       "- 'Show recycle bin items'\n"
                       "- 'Empty the recycle bin'"
            )

        # Batch mode: run each sub-operation and collect results
        if len(operations) > 1:
            tasks = [
                _dispatch_site_operation(op, session_id, site_id, repository)
                for op in operations
            ]
            results: list = await asyncio.gather(*tasks, return_exceptions=True)
            lines = []
            for op, res in zip(operations, results):
                if isinstance(res, Exception):
                    lines.append(f"❌ **{op.operation}** failed: {res}")
                elif isinstance(res, ChatResponse):
                    lines.append(res.reply)
                else:
                    lines.append(str(res))
            return ChatResponse(intent="chat", reply="\n\n---\n\n".join(lines))

        # Single operation
        operation = operations[0]
        if not operation:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the site operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Create a new team site called Marketing'\n"
                       "- 'Add john@company.com as a member of the HR site'\n"
                       "- 'Show recycle bin items'\n"
                       "- 'Empty the recycle bin'"
            )
        
        # ── CREATE SITE ─────────────────────────────────────
        if operation.operation == "create":
            if not operation.site_title:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a title for the new site.\n\n"
                           "Example: 'Create a team site called Marketing'"
                )

            # ── Plain site creation (no template match) ──────
            from src.application.services.governance_service import GovernanceService
            from src.application.services.audit_service import AuditService

            site_name_slug = operation.site_name or operation.site_title.lower().replace(" ", "-")
            gov_violations = GovernanceService.check_site(
                title=operation.site_title,
                name=site_name_slug,
                template=operation.site_template,
            )
            blocking = [v for v in gov_violations if v.is_blocking]
            if blocking:
                AuditService.record("create_site", "site", operation.site_title, session_id,
                                    result="blocked", details={"violations": [v.message for v in blocking]})
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ **Governance policy prevented site creation:**\n\n"
                           + "\n".join(f"- {v.message}" for v in blocking),
                )

            sp_template = "sts" if operation.site_template == "Team" else "sitepagepublishing"
            sp_site = SPSite(
                title=operation.site_title,
                description=operation.site_description or "",
                name=site_name_slug,
                template=sp_template,
                owner_email=""
            )
            
            result = await repository.create_site(sp_site)
            AuditService.record("create_site", "site", operation.site_title, session_id,
                                details={"webUrl": result.get("webUrl", ""), "template": sp_template})

            if result.get("_provisioning"):
                return ChatResponse(
                    intent="chat",
                    reply=f"⏳ **{operation.site_title}** is being provisioned by Microsoft 365.\n\n"
                           f"This typically takes 1-2 minutes. I'm monitoring in the background — "
                           f"the site will be ready shortly.\n\n"
                           f"📝 Type: {operation.site_template} Site",
                    data_summary={**result, "site_name": operation.site_title, "site_id": result.get("id", "")},
                )

            return ChatResponse(
                intent="chat",
                reply=f"✅ Successfully created new site: **{operation.site_title}**!\n\n"
                       f"📝 Type: {operation.site_template} Site\n"
                       f"🔗 Site ID: {result.get('id', 'N/A')}\n"
                       f"🌐 Web URL: {result.get('webUrl', 'N/A')}",
                data_summary={**result, "site_name": operation.site_title, "site_id": result.get("id", "")}
            )
        
        # ── DELETE SITE ─────────────────────────────────────
        elif operation.operation == "delete":
            if not operation.site_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which site to delete."
                )

            all_sites = await repository.get_all_sites()
            target_site = None
            for site in all_sites:
                site_name = site.get("displayName", "").lower()
                if operation.site_name.lower() in site_name or site_name in operation.site_name.lower():
                    target_site = site
                    break

            if not target_site:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Site '{operation.site_name}' not found."
                )

            display_name = target_site.get('displayName', operation.site_name)
            target_site_id = target_site.get('id')

            # Check if user already confirmed this deletion
            pending = pop_pending_action(session_id)
            if pending and pending.action_type == "delete_site" and pending.resource_name == display_name:
                success = await pending.callable()
                if success:
                    return ChatResponse(
                        intent="chat",
                        reply=f"✅ Site **{display_name}** has been permanently deleted.",
                        session_id=session_id
                    )
                else:
                    return ChatResponse(
                        intent="chat",
                        reply="❌ Failed to delete site. Please check permissions and try again.",
                        session_id=session_id
                    )

            # Not yet confirmed — store action and ask
            async def _do_delete_site():
                return await repository.delete_site(target_site_id)

            store_pending_action(session_id, PendingAction(
                action_type="delete_site",
                resource_name=display_name,
                callable=_do_delete_site,
            ))
            return ChatResponse(
                intent="chat",
                reply=(
                    f"⚠️ **Confirm deletion of site: {display_name}**\n\n"
                    f"This will permanently delete the site and ALL its content — "
                    f"pages, libraries, lists, and permissions.\n\n"
                    f"Reply `confirm delete {display_name}` to proceed, "
                    f"or anything else to cancel."
                ),
                session_id=session_id
            )
        
        # ── ADD MEMBER ──────────────────────────────────────
        elif operation.operation == "add_member":
            if not operation.user_email:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the email of the user to add."
                )
            
            # Use current site or find by name
            target_site_id = site_id
            if operation.site_name:
                all_sites = await repository.get_all_sites()
                for site in all_sites:
                    site_name = site.get("displayName", "").lower()
                    if operation.site_name.lower() in site_name or site_name in operation.site_name.lower():
                        target_site_id = site.get("id")
                        break
            
            success = await repository.add_site_member(target_site_id, operation.user_email)
            
            if success:
                site_name = operation.site_name or "the site"
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully added **{operation.user_email}** as a member of **{site_name}**!"
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to add member. Please check the email and permissions."
                )
        
        # ── ADD OWNER ───────────────────────────────────────
        elif operation.operation == "add_owner":
            if not operation.user_email:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the email of the user to add as owner."
                )
            
            target_site_id = site_id
            if operation.site_name:
                all_sites = await repository.get_all_sites()
                for site in all_sites:
                    site_name = site.get("displayName", "").lower()
                    if operation.site_name.lower() in site_name or site_name in operation.site_name.lower():
                        target_site_id = site.get("id")
                        break
            
            success = await repository.add_site_owner(target_site_id, operation.user_email)
            
            if success:
                site_name = operation.site_name or "the site"
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully added **{operation.user_email}** as an owner of **{site_name}**!"
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to add owner. Please check the email and permissions."
                )
        
        # ── UPDATE THEME ────────────────────────────────────
        elif operation.operation == "update_theme":
            if not operation.theme_settings:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify theme settings (colors, logo, etc.).\n\n"
                           "This feature requires detailed theme configuration."
                )
            
            target_site_id = site_id
            success = await repository.update_site_theme(target_site_id, operation.theme_settings)
            
            if success:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully updated site theme!"
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to update theme. Please try again."
                )
        
        # ── NAVIGATION ──────────────────────────────────────
        elif operation.operation == "navigation":
            if not operation.navigation_items:
                # Get current navigation
                nav_items = await repository.get_site_navigation(site_id, operation.navigation_type or "top")
                
                if not nav_items:
                    return ChatResponse(
                        intent="chat",
                        reply=f"📋 No navigation items found for {operation.navigation_type or 'top'} navigation."
                    )
                
                reply = f"**{operation.navigation_type.title() if operation.navigation_type else 'Top'} Navigation Items:**\n\n"
                for i, item in enumerate(nav_items, 1):
                    reply += f"{i}. {item.get('Title', 'Unknown')} → {item.get('Url', '#')}\n"
                
                return ChatResponse(
                    intent="chat",
                    reply=reply,
                    data_summary={"navigation_items": nav_items}
                )
            else:
                # Update navigation
                success = await repository.update_site_navigation(
                    site_id,
                    operation.navigation_type or "top",
                    operation.navigation_items
                )
                
                if success:
                    return ChatResponse(
                        intent="chat",
                        reply=f"✅ Successfully updated {operation.navigation_type or 'top'} navigation!"
                    )
                else:
                    return ChatResponse(
                        intent="chat",
                        reply=f"❌ Failed to update navigation. Please try again."
                    )
        
        # ── RECYCLE BIN ─────────────────────────────────────
        elif operation.operation == "recycle_bin":
            items = await repository.get_site_recycle_bin(site_id)
            
            if not items:
                return ChatResponse(
                    intent="chat",
                    reply="🗑️ The recycle bin is empty."
                )
            
            reply = f"**Recycle Bin Items ({len(items)}):**\n\n"
            for i, item in enumerate(items[:20], 1):
                reply += f"{i}. {item.get('title', 'Unknown')} (ID: {item.get('id', 'N/A')})\n"
            
            if len(items) > 20:
                reply += f"\n... and {len(items) - 20} more items"
            
            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary={"recycle_bin_items": items[:20]}
            )
        
        # ── EMPTY RECYCLE BIN ───────────────────────────────
        elif operation.operation == "empty_recycle_bin":
            # Get item count for the warning message
            try:
                items = await repository.get_site_recycle_bin(site_id)
                item_count = len(items) if items else 0
            except Exception:
                item_count = 0

            # Check if user already confirmed
            pending = pop_pending_action(session_id)
            if pending and pending.action_type == "empty_recycle_bin":
                success = await pending.callable()
                if success:
                    return ChatResponse(
                        intent="chat",
                        reply="✅ Recycle bin emptied — all items permanently deleted.",
                        session_id=session_id
                    )
                else:
                    return ChatResponse(
                        intent="chat",
                        reply="❌ Failed to empty recycle bin. Please try again.",
                        session_id=session_id
                    )

            # Not yet confirmed — store action and ask
            async def _do_empty_bin():
                return await repository.empty_recycle_bin(site_id)

            store_pending_action(session_id, PendingAction(
                action_type="empty_recycle_bin",
                resource_name="recycle bin",
                callable=_do_empty_bin,
            ))
            count_msg = f"**{item_count} item(s)**" if item_count else "all items"
            return ChatResponse(
                intent="chat",
                reply=(
                    f"⚠️ **Confirm: Empty the recycle bin**\n\n"
                    f"This will permanently delete {count_msg} — they cannot be recovered.\n\n"
                    f"Reply `confirm empty recycle bin` to proceed, "
                    f"or anything else to cancel."
                ),
                session_id=session_id
            )
        
        # ── RESTORE ITEM ────────────────────────────────────
        elif operation.operation == "restore_item":
            if not operation.recycle_bin_item_id:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the ID of the item to restore from recycle bin."
                )
            
            success = await repository.restore_from_recycle_bin(site_id, operation.recycle_bin_item_id)
            
            if success:
                return ChatResponse(
                    intent="chat",
                    reply=f"✅ Successfully restored item from recycle bin!",
                    session_id=session_id
                )
            else:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Failed to restore item. Please check the item ID and try again.",
                    session_id=session_id
                )
        
        # ── GET STORAGE ─────────────────────────────────────
        elif operation.operation == "get_storage":
            storage_info = await repository.get_site_storage_info(site_id)
            
            used_gb = storage_info.get("used", 0) / (1024**3)
            total_gb = storage_info.get("total", 0) / (1024**3)
            remaining_gb = storage_info.get("remaining", 0) / (1024**3)
            
            return ChatResponse(
                intent="chat",
                reply=f"📊 **Site Storage Information:**\n\n"
                       f"💾 Used: {used_gb:.2f} GB\n"
                       f"📦 Total: {total_gb:.2f} GB\n"
                       f"✨ Remaining: {remaining_gb:.2f} GB\n"
                       f"📈 State: {storage_info.get('state', 'normal')}",
                data_summary=storage_info
            )
        
        # ── GET ANALYTICS ───────────────────────────────────
        elif operation.operation == "get_analytics":
            analytics = await repository.get_site_analytics(site_id)
            
            return ChatResponse(
                intent="chat",
                reply=f"📈 **Site Analytics:**\n\n"
                       f"👁️ Views: {analytics.get('views', 0)}\n"
                       f"👥 Visitors: {analytics.get('visitors', 0)}\n"
                       f"📅 Period: {analytics.get('period', 'last7days')}",
                data_summary=analytics
            )

        else:
            return ChatResponse(
                intent="chat",
                reply=f"Unknown site operation: {operation.operation}"
            )
    
    except Exception as e:
        from src.domain.exceptions import PermissionDeniedException, AuthenticationException, DomainException
        from src.presentation.api.orchestrators.orchestrator_utils import (
            domain_error_response, permission_denied_response, auth_expired_response,
        )
        if isinstance(e, PermissionDeniedException):
            return permission_denied_response(session_id=session_id)
        if isinstance(e, AuthenticationException):
            return auth_expired_response(session_id=session_id)
        if isinstance(e, DomainException):
            return domain_error_response(e, intent="chat", session_id=session_id)
        return error_response(logger, "chat", "Sorry, I couldn't complete that site operation: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
