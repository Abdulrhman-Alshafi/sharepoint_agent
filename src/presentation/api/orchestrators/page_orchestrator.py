"""Handler for SharePoint page operations."""

from typing import List, Any

from src.domain.entities.conversation import ResourceType
from src.presentation.api import ServiceContainer
from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Webpart-type keyword mapping
# Maps lowercase substrings the user might write to webpart_type values.
# ---------------------------------------------------------------------------
_SECTION_TYPE_MAP = {
    "hero":             ("Hero",          {}),
    "banner":           ("Hero",          {}),
    "image":            ("Image",         {}),
    "photo":            ("Image",         {}),
    "quick link":       ("QuickLinks",    {}),
    "quicklink":        ("QuickLinks",    {}),
    "link":             ("QuickLinks",    {}),
    "news":             ("News",          {}),
    "news feed":        ("News",          {}),
    "people":           ("People",        {}),
    "team member":      ("People",        {}),
    "members":          ("People",        {}),
    "list":             ("List",          {}),
    "document library": ("DocumentLibrary", {}),
    "library":          ("DocumentLibrary", {}),
    "events":           ("Events",        {}),
    "calendar":         ("Events",        {}),
}


def _section_to_webpart(section: str) -> Any:
    """Convert a content-section description string to a WebPart value object."""
    from src.domain.value_objects import WebPart

    low = section.lower()
    for keyword, (wtype, extra_props) in _SECTION_TYPE_MAP.items():
        if keyword in low:
            # Extract any inline items after a colon, e.g. "quick links: Jira, GitHub"
            props: dict = {}
            if ":" in section:
                after_colon = section.split(":", 1)[1].strip()
                if wtype == "QuickLinks":
                    items = [s.strip() for s in after_colon.split(",") if s.strip()]
                    props["items"] = [{"title": i, "url": ""} for i in items]
                elif wtype in ("Hero", "Image"):
                    props["title"] = after_colon
                else:
                    props["content"] = after_colon
            props.update(extra_props)
            return WebPart(type=wtype, properties=props, webpart_type=wtype)

    # Default: treat as a plain text section
    return WebPart(type="Text", properties={"content": section}, webpart_type="Text")


def _build_webparts_from_operation(operation: Any, original_message: str) -> List[Any]:
    """Build a list of WebPart objects from a PageOperation.

    Priority:
    1. ``operation.content_sections`` — explict rich sections from the parser
    2. ``operation.content``          — single plain-text content
    3. AI-inferred from message keywords
    4. Fallback: default hero + text pair
    """
    from src.domain.value_objects import WebPart

    # 1. Explicit sections
    sections = getattr(operation, "content_sections", None)
    if sections:
        return [_section_to_webpart(s) for s in sections]

    # 2. Single content string
    if getattr(operation, "content", None):
        return [WebPart(type="Text", properties={"content": operation.content}, webpart_type="Text")]

    # 3. Keyword inference via webpart router
    from src.detection.routing.webpart_router import route_webpart
    inferred: List[Any] = []

    # Check common combinations first (multi-keyword)
    wpart_r = route_webpart(original_message)
    if wpart_r:
        wtype = wpart_r.intent
        if wtype == "Hero":
            inferred.append(WebPart(
                type="Hero",
                properties={"title": operation.page_title or "Welcome"},
                webpart_type="Hero",
            ))
        elif wtype == "QuickLinks":
            inferred.append(WebPart(type="QuickLinks", properties={"items": []}, webpart_type="QuickLinks"))
        elif wtype == "News":
            inferred.append(WebPart(type="News", properties={}, webpart_type="News"))
        elif wtype == "People":
            inferred.append(WebPart(type="People", properties={"personas": []}, webpart_type="People"))

    if inferred:
        # Always prepend a text intro
        inferred.insert(0, WebPart(
            type="Text",
            properties={"content": f"<h2>{operation.page_title}</h2>"},
            webpart_type="Text"
        ))
        return inferred

    # 4. Default: hero + welcome text
    return [
        WebPart(
            type="Hero",
            properties={"title": operation.page_title or "Welcome"},
            webpart_type="Hero"
        ),
        WebPart(
            type="Text",
            properties={"content": f"<h2>Welcome to {operation.page_title}</h2>"},
            webpart_type="Text"
        ),
    ]


async def handle_page_operations(message: str, session_id: str, site_id: str, user_token: str = None, user_login_name: str = "", last_created: tuple = None) -> ChatResponse:
    """Handle page operations (create, publish, list, copy, delete)."""
    from src.presentation.api import get_site_repository, get_list_repository, get_page_repository, get_library_repository, get_permission_repository, get_enterprise_repository
    from src.infrastructure.external_services.page_operation_parser import PageOperationParserService

    try:
        site_repository = get_site_repository(user_token=user_token)
        list_repository = get_list_repository(user_token=user_token)
        page_repository = get_page_repository(user_token=user_token)
        library_repository = get_library_repository(user_token=user_token)
        permission_repository = get_permission_repository(user_token=user_token)
        enterprise_repository = get_enterprise_repository(user_token=user_token)
        
        # Prefer the site where the page was created (from last_created[2]) over the request site
        _page_site_id = (last_created[2] if (last_created and len(last_created) > 2 and last_created[2]) else None) or site_id
        
        # Parse the operation using AI
        operation = await PageOperationParserService.parse_page_operation(message)
        
        if not operation:
            return ChatResponse(
                intent="chat",
                reply="I couldn't understand the page operation. Please try rephrasing.\n\n"
                       "Examples:\n"
                       "- 'Create a new page called Welcome Team'\n"
                       "- 'Show me all pages'\n"
                       "- 'Publish the Q4 Results page'\n"
                       "- 'Delete the old announcement page'"
            )
        
        # ── LIST OPERATION ──────────────────────────────────
        if operation.operation == "list":
            pages = await page_repository.get_all_pages(site_id=_page_site_id)
            if not pages:
                return ChatResponse(
                    intent="chat",
                    reply="No pages found in this site."
                )
            
            reply = f"📄 Found **{len(pages)}** {'page' if len(pages) == 1 else 'pages'}:\n\n"
            for idx, page in enumerate(pages[:20], 1):  # Limit to 20 pages
                page_name = page.get('title') or page.get('name', 'Untitled')
                page_url = page.get('webUrl', '')
                reply += f"{idx}. **{page_name}**"
                if page_url:
                    reply += f" - {page_url}"
                reply += "\n"
            
            if len(pages) > 20:
                reply += f"\n... and {len(pages) - 20} more pages."
            
            return ChatResponse(
                intent="chat",
                reply=reply,
                data_summary={"page_count": len(pages)}
            )
        
        # ── GET OPERATION ───────────────────────────────────
        elif operation.operation == "get":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a page title or name.\n\nExample: 'Show me the HomePage'"
                )
            
            # Search for the page
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            
            if not pages:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Page '{search_term}' not found."
                )
            
            page = pages[0]  # Take first match
            page_name = page.get('title') or page.get('name', 'Untitled')
            page_url = page.get('webUrl', 'N/A')
            last_modified = page.get('lastModifiedDateTime', 'Unknown')
            
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page found: **{page_name}**\n\n"
                       f"🔗 URL: {page_url}\n"
                       f"📅 Last Modified: {last_modified}\n",
                data_summary={**page, "page_name": page_name, "site_id": site_id}
            )
        
        # ── CREATE OPERATION ────────────────────────────────
        elif operation.operation == "create":
            if not operation.page_title:
                gathering_service = ServiceContainer.get_gathering_service()
                _, first_question = gathering_service.start_gathering(
                    session_id, message, ResourceType.PAGE
                )

                if first_question:
                    return ChatResponse(
                        intent="provision",
                        reply=f"Sure! Let me help you set that up.\n\n{first_question.question_text}",
                        requires_input=True,
                        question_prompt=first_question.question_text,
                        field_type=first_question.field_type,
                        field_options=first_question.options,
                        quick_suggestions=first_question.options[:3] if first_question.options else None,
                        session_id=session_id,
                    )

                return ChatResponse(
                    intent="chat",
                    reply="Please specify a page title.\n\nExample: 'Create a new page called Welcome Team'"
                )

            from src.domain.entities.core import SPPage
            from src.domain.value_objects import WebPart

            # ── Cross-site resolution ─────────────────────────
            target_site_id = site_id
            if getattr(operation, "target_site_name", None):
                try:
                    found = await site_repository.search_sites(operation.target_site_name)
                    if found:
                        target_site_id = found[0].get("id", site_id)
                    else:
                        return ChatResponse(
                            intent="chat",
                            reply=f"❌ Could not find site '{operation.target_site_name}'. "
                                   f"Please check the site name and try again."
                        )
                except Exception:
                    pass  # fall back to default site_id

            # ── Build webparts with content generation pipeline ──
            webparts = _build_webparts_from_operation(operation, message)
            
            # Enhance with AI content generation pipeline for richer pages
            try:
                from src.domain.services.page_purpose_detector import PagePurposeDetector
                from src.infrastructure.services.content_template_manager import ContentTemplateManager
                from src.infrastructure.services.page_content_generator import PageContentGenerator
                from src.infrastructure.repositories.utils.webpart_composer import WebPartComposer
                
                purpose_detector = PagePurposeDetector()
                template_manager = ContentTemplateManager()
                content_generator = PageContentGenerator()
                
                # Detect purpose from page title
                purpose, confidence = await purpose_detector.detect_purpose(
                    operation.page_title,
                    getattr(operation, "content", "") or "",
                )
                
                # Get template and generate content
                template = template_manager.get_template(purpose)
                if template:
                    generated_content = await content_generator.generate_page_content(
                        operation.page_title,
                        getattr(operation, "content", "") or "",
                        purpose,
                    )
                    
                    # Compose webparts from template + generated content
                    composed_webparts = WebPartComposer.compose_webparts(
                        template.webparts, generated_content,
                    )
                    if composed_webparts:
                        webparts = composed_webparts
                        logger.info("[PageHandler] Enhanced page '%s' with content generation pipeline (%d webparts)",
                                    operation.page_title, len(webparts))
            except Exception as e:
                logger.warning("[PageHandler] Content generation enhancement failed for '%s': %s. Using basic webparts.",
                               operation.page_title, e)

            # ── Layout ──────────────────────────────────────
            page_layout = getattr(operation, "layout", None) or "article"
            # Multi-column layouts are expressed via canvasLayout sections;
            # the Graph API pageLayout field only accepts: article, home, singleWebPartApp
            graph_layout = page_layout if page_layout in ("article", "home", "singleWebPartApp") else "article"

            new_page = SPPage(
                title=operation.page_title,
                webparts=webparts,
                layout=graph_layout,
            )

            result = await page_repository.create_page(new_page, site_id=target_site_id)

            # Audit the creation
            from src.application.services.audit_service import AuditService
            AuditService.record("create_page", "page", operation.page_title, session_id,
                                details={"layout": graph_layout, "url": result.get("resource_link", "")})

            site_note = f" on **{operation.target_site_name}**" if getattr(operation, "target_site_name", None) else ""
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{operation.page_title}** created{site_note}!\n\n"
                       f"🔗 URL: {result.get('resource_link', 'N/A')}\n\n"
                       f"The page is in draft mode. To publish it, say 'Publish {operation.page_title}'",
                data_summary={**result, "page_name": operation.page_title, "site_id": target_site_id}
            )
        
        # ── PUBLISH OPERATION ───────────────────────────────
        elif operation.operation == "publish":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to publish.\n\nExample: 'Publish the Welcome Team page'"
                )
            
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            
            if not pages:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Page '{search_term}' not found. Please check the page name and try again."
                )
            
            page_id = pages[0].get("id")
            await page_repository.publish_page(page_id, site_id=_page_site_id)
            
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** published successfully!"
            )
        
        # ── DELETE OPERATION ────────────────────────────────
        elif operation.operation == "delete":
            if not operation.page_title and not operation.page_name:
                if last_created and len(last_created) > 1 and last_created[1] == "page" and last_created[0]:
                    operation.page_title = last_created[0]
                else:
                    return ChatResponse(
                        intent="chat",
                        reply="⚠️ Please specify which page to delete.\n\nExample: 'Delete the old announcement page'"
                    )

            search_term = operation.page_title or operation.page_name
            if search_term and search_term.lower() in {"this", "that", "it"}:
                if last_created and len(last_created) > 1 and last_created[1] == "page" and last_created[0]:
                    search_term = last_created[0]
                else:
                    return ChatResponse(
                        intent="chat",
                        reply="⚠️ I’m not sure which page you’d like to delete. Please say the exact page name."
                    )

            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)

            if not pages and last_created and len(last_created) > 1 and last_created[1] == "page" and last_created[0]:
                search_term = last_created[0]
                pages = await page_repository.search_pages(search_term, site_id=_page_site_id)

            if not pages:
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Page '{search_term}' not found. Please check the page name and try again."
                )

            page_id = pages[0].get("id")
            await page_repository.delete_page(page_id, site_id=_page_site_id)
            
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** deleted successfully!"
            )
        
        # ── UNPUBLISH OPERATION ─────────────────────────────
        elif operation.operation == "unpublish":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to unpublish.\n\nExample: 'Unpublish the Welcome page'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            await page_repository.unpublish_page(page_id, site_id=site_id)
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** has been unpublished (set back to draft)."
            )

        # ── CHECKOUT OPERATION ──────────────────────────────
        elif operation.operation == "checkout":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to check out.\n\nExample: 'Checkout the Policies page'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            await page_repository.checkout_page(page_id, site_id=site_id)
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** checked out. You now have exclusive edit access.\n\n"
                       f"Remember to check it back in when done: 'Check in the {search_term} page'"
            )

        # ── CHECKIN OPERATION ───────────────────────────────
        elif operation.operation == "checkin":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to check in.\n\nExample: 'Check in the Policies page'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            await page_repository.checkin_page(page_id, site_id=site_id)
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** checked in successfully."
            )

        # ── COPY OPERATION ──────────────────────────────────
        elif operation.operation == "copy":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to copy.\n\nExample: 'Copy Homepage to New Homepage'"
                )
            search_term = operation.page_title or operation.page_name
            new_title = operation.new_title or operation.target_page_title or f"Copy of {search_term}"
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            result = await page_repository.copy_page(page_id, new_title, site_id=site_id)
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** copied to **{new_title}**!\n\n"
                       f"🔗 URL: {result.get('resource_link', result.get('webUrl', 'N/A'))}",
                data_summary=result
            )

        # ── VERSIONS OPERATION ──────────────────────────────
        elif operation.operation == "versions":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to list versions for.\n\nExample: 'Show versions of the Home page'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            versions = await page_repository.get_page_versions(page_id, site_id=site_id)
            if not versions:
                return ChatResponse(intent="chat", reply=f"📋 No versions found for **{search_term}**.")
            reply = f"📋 **{len(versions)} version(s)** of **{search_term}**:\n\n"
            for v in versions[:20]:
                vid = v.get('id', 'N/A')
                modified = v.get('lastModifiedDateTime', 'Unknown')
                by = v.get('lastModifiedBy', {}).get('user', {}).get('displayName', 'Unknown')
                reply += f"• Version **{vid}** — {modified} by {by}\n"
            if len(versions) > 20:
                reply += f"\n... and {len(versions) - 20} more."
            reply += f"\n\nTo restore: 'Restore version {{id}} of {search_term}'"
            return ChatResponse(intent="chat", reply=reply, data_summary={"versions": versions})

        # ── RESTORE VERSION OPERATION ───────────────────────
        elif operation.operation == "restore_version":
            if not (operation.page_title or operation.page_name):
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the page and version.\n\nExample: 'Restore version 3 of the Policies page'"
                )
            if not operation.version_id:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the version ID to restore.\n\nExample: 'Restore version 3 of the Policies page'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            await page_repository.restore_page_version(page_id, operation.version_id, site_id=site_id)
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** restored to version **{operation.version_id}**."
            )

        # ── SHARE OPERATION ─────────────────────────────────
        elif operation.operation == "share":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to share.\n\nExample: 'Share a link to the Team page'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            result = await page_repository.create_page_share_link(page_id, site_id=site_id)
            link = result.get('link', {}).get('webUrl') or result.get('webUrl', 'N/A')
            return ChatResponse(
                intent="chat",
                reply=f"🔗 Share link for **{search_term}**:\n\n{link}",
                data_summary=result
            )

        # ── PROMOTE AS NEWS OPERATION ───────────────────────
        elif operation.operation == "promote_news":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to promote as news.\n\nExample: 'Promote Company News as a news article'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            await page_repository.promote_page_as_news(page_id, site_id=site_id)
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** has been promoted as a news article and will appear in news feeds."
            )

        # ── UPDATE OPERATION ────────────────────────────────
        elif operation.operation == "update":
            if not operation.page_title and not operation.page_name:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify which page to update.\n\nExample: 'Update the About page with our new mission statement'"
                )
            if not operation.content:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify the new content.\n\nExample: 'Update the About page with: We build great software'"
                )
            search_term = operation.page_title or operation.page_name
            pages = await page_repository.search_pages(search_term, site_id=_page_site_id)
            if not pages:
                return ChatResponse(intent="chat", reply=f"❌ Page '{search_term}' not found.")
            page_id = pages[0].get('id')
            from src.domain.entities.core import SPPage
            from src.domain.value_objects import WebPart
            updated_page = SPPage(
                title=search_term,
                webparts=[WebPart(type="Text", properties={"content": operation.content})]
            )
            await page_repository.update_page_content(page_id, updated_page)
            return ChatResponse(
                intent="chat",
                reply=f"✅ Page **{search_term}** updated successfully!"
            )

        # ── ANALYTICS OPERATION ────────────────────────────────
        elif operation.operation == "analytics":
            search_term = operation.page_title or operation.page_name or ""
            page_id, page_title = await _resolve_page(repository, site_id, search_term)
            if not page_id:
                return ChatResponse(
                    intent="chat",
                    reply=f"⚠️ Could not find page **{search_term}**. Please check the title."
                )
            data = await page_repository.get_page_analytics(page_id, site_id=site_id)
            if not data:
                return ChatResponse(
                    intent="chat",
                    reply=f"📊 Analytics are not available for **{page_title}** yet. "
                           "This may require the page to have been published for at least 24 hours.",
                )
            views = data.get("allTime", {}).get("view", {}).get("actionCount", "N/A")
            unique = data.get("allTime", {}).get("view", {}).get("reactionCount", "N/A")
            return ChatResponse(
                intent="chat",
                reply=(
                    f"📊 **Analytics for: {page_title}**\n\n"
                    f"👁️ Total views: {views}\n"
                    f"👤 Reactions: {unique}\n\n"
                    f"_Data sourced from Microsoft Graph analytics._"
                ),
                data_summary=data,
            )

        # ── SCHEDULE OPERATION ────────────────────────────────
        elif operation.operation == "schedule":
            search_term = operation.page_title or operation.page_name or ""
            scheduled_dt = operation.scheduled_datetime or ""
            page_id, page_title = await _resolve_page(repository, site_id, search_term)
            if not page_id:
                return ChatResponse(
                    intent="chat",
                    reply=f"⚠️ Could not find page **{search_term}**."
                )
            if not scheduled_dt:
                return ChatResponse(
                    intent="chat",
                    reply="⚠️ Please specify a date and time, e.g. 'Schedule the Home page for 2025-09-01T09:00:00Z'."
                )
            result = await page_repository.schedule_page_publish(page_id, scheduled_dt, site_id=site_id)
            if result.get("error"):
                return ChatResponse(
                    intent="chat",
                    reply=f"❌ Could not schedule page: {result['error']}"
                )
            return ChatResponse(
                intent="chat",
                reply=f"🗓️ **{page_title}** is scheduled to publish at `{scheduled_dt}`.",
                data_summary=result,
            )

        # ── UNSUPPORTED OPERATION ───────────────────────────
        else:
            return ChatResponse(
                intent="chat",
                reply=f"⚠️ Operation '{operation.operation}' is not recognised."
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
        return error_response(logger, "chat", "An error occurred with the page operation: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
