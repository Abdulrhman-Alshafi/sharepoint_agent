"""Handler for content analysis operations."""

from src.presentation.api.schemas.chat_schemas import ChatResponse
from src.presentation.api.orchestrators.orchestrator_utils import get_logger, error_response
from src.application.services import ProvisioningApplicationService
from src.domain.exceptions import PermissionDeniedException, AuthenticationException

logger = get_logger(__name__)

_PERMISSION_DENIED_REPLY = (
    "🔒 **Access Denied** — You don't have permission to access this resource. "
    "Please contact your SharePoint administrator if you believe this is an error."
)


async def handle_analysis_operations(message: str, site_id: str, provisioning_service: ProvisioningApplicationService, history: list = None, user_token: str = None, user_login_name: str = "", user_email: str = "") -> ChatResponse:
    """Handle content analysis requests."""
    from src.presentation.api import get_site_repository, get_list_repository, get_page_repository, get_library_repository, get_permission_repository, get_enterprise_repository
    from src.application.use_cases.analyze_content_use_case import AnalyzeContentUseCase
    from src.infrastructure.services.content_analyzer import ContentAnalyzerService
    
    try:
        # Get repository — use OBO (per-user) instance when user token is present
        site_repository = get_site_repository(user_token=user_token)
        list_repository = get_list_repository(user_token=user_token)
        page_repository = get_page_repository(user_token=user_token)
        library_repository = get_library_repository(user_token=user_token)
        permission_repository = get_permission_repository(user_token=user_token)
        enterprise_repository = get_enterprise_repository(user_token=user_token)
        
        # Initialize content analyzer with required dependencies
        from src.infrastructure.services.sharepoint.list_service import ListService
        from src.infrastructure.services.sharepoint.page_service import PageService
        from src.infrastructure.services.sharepoint.library_service import LibraryService
        
        # Get clients from site_repository
        graph_client = site_repository.graph_client
        rest_client = site_repository.rest_client
        
        # Create service instances
        list_service = ListService(graph_client)
        page_service = PageService(rest_client, graph_client)
        library_service = LibraryService(graph_client)
        
        content_analyzer = ContentAnalyzerService(
            graph_client=graph_client,
            rest_client=rest_client,
            list_service=list_service,
            page_service=page_service,
            library_service=library_service
        )
        
        analyze_use_case = AnalyzeContentUseCase(content_analyzer, permission_repository=permission_repository)
        
        user_identity = user_login_name or user_email
        
        # Determine resource type from message
        message_lower = message.lower()
        resource_type = None
        resource_id = None

        # ── Step 1: always try to match a list/library name from the message ──
        # This handles messages like "more about Events list" or
        # "more about SalaryDocuments" where the resource name is explicit.
        all_lists = await list_repository.get_all_lists(site_id)
        non_hidden = [lst for lst in all_lists if not lst.get("list", {}).get("hidden", False)]

        best_match = None
        best_len = 0
        for lst in non_hidden:
            display = lst.get("displayName", "").lower()
            if display and display in message_lower and len(display) > best_len:
                best_match = lst
                best_len = len(display)

        if best_match:
            # Detect whether this is a document library or a regular list
            template = best_match.get("list", {}).get("template", "")
            resource_type = "library" if template == "documentLibrary" else "list"
            resource_id = best_match.get("id")

        # ── Step 2: fall back to resource-type keywords if no name match ──
        if not resource_type:
            if "site" in message_lower:
                resource_type = "site"
            elif "page" in message_lower:
                resource_type = "page"
                return ChatResponse(
                    intent="analyze",
                    reply="To analyze a specific page, please provide the page name or URL."
                )
            elif "list" in message_lower or "library" in message_lower or "librari" in message_lower:
                resource_type = "list"
                # No name match — ask the user which list
                list_names = [lst.get("displayName", "Unknown") for lst in non_hidden[:10]]
                return ChatResponse(
                    intent="analyze",
                    reply=f"Which list would you like me to analyze? Available lists: {', '.join(list_names)}"
                )

        if not resource_type:
            # Last resort: scan conversation history for a known list name
            if history:
                history_text = " ".join(
                    m.get("content", "") for m in history if isinstance(m, dict)
                ).lower()
                for lst in non_hidden:
                    display = lst.get("displayName", "").lower()
                    if display and display in history_text:
                        template = lst.get("list", {}).get("template", "")
                        resource_type = "library" if template == "documentLibrary" else "list"
                        resource_id = lst.get("id")
                        best_match = lst
                        break

        if not resource_type:
            return ChatResponse(
                intent="analyze",
                reply="I can analyze sites, pages, and lists. What would you like me to analyze?"
            )
        
        # Execute analysis
        analysis = await analyze_use_case.execute(resource_type, site_id, resource_id, user_login=user_identity)
        
        # Format response as a natural narrative — structured fields are shown in the card below,
        # so the text reply should only contain the narrative body (no duplicated Purpose etc.)
        if analysis.resource_type in ("list", "library"):
            body = analysis.detailed_description or analysis.summary
            reply = f"Here's what I found in **{analysis.resource_name}**:\n\n{body}"
        else:
            # Sites / pages
            reply = f"**{analysis.resource_name}**\n\n{analysis.summary}"
            if analysis.detailed_description and analysis.detailed_description != analysis.summary:
                reply += f"\n\n{analysis.detailed_description}"
            if analysis.components:
                reply += f"\n\n**Contains {len(analysis.components)} component(s):**"
                for comp in analysis.components[:5]:
                    comp_name = comp.get('name', comp.get('type', 'Unknown'))
                    comp_type = comp.get('type', '')
                    reply += f"\n- {comp_type}: {comp_name}"
                if len(analysis.components) > 5:
                    reply += f"\n- ... and {len(analysis.components) - 5} more"
        
        return ChatResponse(
            intent="analyze",
            reply=reply,
            analysis={
                "resource_type": analysis.resource_type,
                "resource_name": analysis.resource_name,
                "summary": analysis.summary,
                "topics": analysis.main_topics,
                "purpose": analysis.purpose,
                "audience": analysis.audience,
                "confidence": analysis.confidence_score
            },
            suggested_actions=analysis.suggested_actions or [
                f"Show me all files in {analysis.resource_name}" if analysis.resource_type == "library" else f"Show me all items in {analysis.resource_name}",
                f"How many {'files' if analysis.resource_type == 'library' else 'items'} are in {analysis.resource_name}?",
                f"Search inside {analysis.resource_name}",
            ]
        )
    
    except PermissionDeniedException:
        from src.presentation.api.orchestrators.orchestrator_utils import permission_denied_response
        return permission_denied_response()
    except AuthenticationException:
        from src.presentation.api.orchestrators.orchestrator_utils import auth_expired_response
        return auth_expired_response()
    except Exception as e:
        from src.domain.exceptions import DomainException
        from src.presentation.api.orchestrators.orchestrator_utils import domain_error_response
        if isinstance(e, DomainException):
            return domain_error_response(e, intent="analyze")
        return error_response(logger, "analyze", "Sorry, I couldn't analyze that resource: {error}", e,
                              error_category="internal",
                              recovery_hint="Please try again. If this persists, contact your administrator.")
