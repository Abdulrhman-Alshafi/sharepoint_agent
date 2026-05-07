"""Mixin providing metadata and site query handlers for AIDataQueryService."""

import logging

from src.domain.entities import DataQueryResult
from src.infrastructure.external_services.query.helpers import parse_site_info
from src.infrastructure.external_services.query_intelligence import (
    ResourceTypeDetector,
    KeywordFilter,
    QueryAnalyzer,
    format_resource_list,
)
from src.infrastructure.schemas.query_schemas import RouterResponse, ResourceType
from src.infrastructure.config import settings

logger = logging.getLogger(__name__)


class MetadataQueryMixin:
    """Handlers for metadata_count, filtered_meta, full_meta, site info, and all-sites queries.

    Requires *self* to provide:
        self.sharepoint_repository
    """

    async def _handle_metadata_count(
        self,
        question: str,
        all_lists: list,
        route: RouterResponse,
        site_name: str = None,
        site_id: str = None,
        site_url: str = None,
    ) -> DataQueryResult:
        """Handle metadata count queries (how many pages, lists, etc.)."""
        count_target = QueryAnalyzer.extract_count_target(question)
        site_context = f" in the **{site_name}** site" if site_name else ""
        _hint = (
            "\n\n"
            "💡 If you didn't find the list or library you're looking for, "
            "let me know which site it's in and I'll search there for you."
        )

        if count_target == "libraries":
            classified = ResourceTypeDetector.classify_lists_by_type(all_lists)
            count = len(classified["libraries"])
            label = "document libraries" if count != 1 else "document library"
            answer = f"There are **{count}** {label}{site_context}."
            if count > 0:
                answer += f"\n\n{format_resource_list(classified['libraries'], 'libraries', include_description=False)}"
            answer += _hint
            return DataQueryResult(
                answer=answer,
                data_summary={"count": count, "type": "libraries"},
                suggested_actions=[
                    "Show me all libraries with descriptions",
                    "Create a new document library",
                    "Show me all lists",
                ],
            )

        elif count_target == "lists":
            classified = ResourceTypeDetector.classify_lists_by_type(all_lists)
            count = len(classified["lists"])
            label = "lists" if count != 1 else "list"
            answer = f"There are **{count}** custom {label}{site_context}."
            if count > 0:
                answer += f"\n\n{format_resource_list(classified['lists'], 'lists', include_description=False)}"
            answer += _hint
            return DataQueryResult(
                answer=answer,
                data_summary={"count": count, "type": "lists"},
                suggested_actions=[
                    "Show me all lists with descriptions",
                    "Create a new list",
                    "Show me all libraries",
                ],
            )

        elif count_target == "pages":
            try:
                pages = await self.sharepoint_repository.get_all_pages(site_id=site_id)
                count = len(pages)
                label = "pages" if count != 1 else "page"
                answer = f"There are **{count}** {label}{site_context}."
                if count > 0:
                    answer += "\n\n" + "\n".join(
                        f"- **{p.get('title', p.get('name', 'Untitled'))}**" for p in pages
                    )
                return DataQueryResult(
                    answer=answer,
                    data_summary={"count": count, "type": "pages"},
                    suggested_actions=[
                        "Show me details for the Home page",
                        "Create a new page",
                        "Show me all lists",
                    ],
                )
            except Exception as exc:
                logger.error("Failed to query pages count: %s", exc)
                return DataQueryResult(
                    answer="I encountered an error counting pages from your site.",
                    suggested_actions=["Try again", "How many lists do I have?"],
                )

        else:
            # General count — show everything
            classified = ResourceTypeDetector.classify_lists_by_type(all_lists)
            total = len(all_lists)
            libs_count = len(classified["libraries"])
            lists_count = len(classified["lists"])
            answer = (
                f"In your SharePoint site{site_context}:\n"
                f"• **{libs_count}** document libraries\n"
                f"• **{lists_count}** custom lists\n"
                f"• **{total}** total"
                + _hint
            )
            return DataQueryResult(
                answer=answer,
                data_summary={"total": total, "libraries": libs_count, "lists": lists_count},
                suggested_actions=[
                    "Show me all libraries",
                    "Show me all lists",
                    "Create a new list or library",
                ],
            )

    async def _handle_filtered_meta(
        self,
        question: str,
        all_lists: list,
        route: RouterResponse,
        site_name: str = None,
        site_url: str = None,
        site_id: str = None,
    ) -> DataQueryResult:
        """Handle filtered meta queries (e.g., 'show all libraries', 'HR lists')."""
        classified = ResourceTypeDetector.classify_lists_by_type(all_lists)
        site_context = f" in the **{site_name}** site" if site_name else ""

        if route.resource_type == ResourceType.LIBRARY:
            resources = classified["libraries"]
            resource_name = "document libraries" if len(resources) != 1 else "document library"
        elif route.resource_type == ResourceType.LIST:
            resources = classified["lists"]
            resource_name = "lists" if len(resources) != 1 else "list"
        else:
            resources = all_lists
            resource_name = "lists and libraries"

        # Skip keyword filtering when we are already scoped to the target site.
        # e.g. "show all lists in the HR site" resolves the HR site first, so
        # filter_keywords=["hr"] would wrongly discard lists whose names don't
        # contain "hr". If the site name already satisfies the keywords, omit
        # the extra filter.
        _skip_keyword_filter = False
        _q_lower = (question or "").lower()
        _default_site_alias_in_q = any(
            phrase in _q_lower
            for phrase in (
                "main site",
                "default site",
                "current site",
                "this site",
                "main list",
                "default list",
                "current list",
                "this list",
            )
        )
        if site_name and route.filter_keywords:
            _site_lower = site_name.lower()
            _skip_keyword_filter = all(
                kw.lower() in _site_lower or _site_lower in kw.lower()
                for kw in route.filter_keywords
            )
        # When user says "main/default/current site/list", treat that as site scope,
        # not a resource-name keyword filter.
        if route.filter_keywords and _default_site_alias_in_q:
            _skip_keyword_filter = True

        if route.filter_keywords and not _skip_keyword_filter:
            resources = KeywordFilter.filter_by_keywords(resources, route.filter_keywords)
            filter_desc = f" related to {', '.join(route.filter_keywords)}"
        else:
            filter_desc = ""

        def _fmt_resource(r: dict) -> str:
            title = r.get("displayName", r.get("name", "Unknown"))
            web_url = r.get("webUrl", "")
            description = r.get("description", "")
            line = f"- **{title}**"
            if site_name and site_url:
                site_link = f"[{site_name}]({site_url})"
                rtype_label = resource_name[:-1] if resource_name.endswith("s") else resource_name
                line += f" — {rtype_label} in site {site_link}"
            if web_url:
                line += f" | [Open]({web_url})"
            if description:
                line += f"\n  {description}"
            return line

        _hint = (
            "\n\n"
            "💡 If you didn't find the list or library you're looking for, "
            "let me know which site it's in and I'll search there for you."
        )

        if not resources:
            answer = f"I couldn't find any {resource_name}{filter_desc}{site_context}." + _hint
            suggested_actions = ["Show me all lists", "Create a new list or library"]
        else:
            answer = f"Found **{len(resources)}** {resource_name}{filter_desc}{site_context}:\n\n"
            answer += "\n".join(_fmt_resource(r) for r in resources)
            answer += _hint
            # Build up to 3 suggested actions from the discovered resources
            _action_resources = resources[:3]
            suggested_actions = [
                f"Show me items in {r.get('displayName', r.get('name', ''))}"
                for r in _action_resources
            ]
            if len(suggested_actions) < 3:
                suggested_actions.append("Show me all resources")

        return DataQueryResult(
            answer=answer,
            data_summary={"count": len(resources), "filtered": bool(route.filter_keywords)},
            suggested_actions=suggested_actions,
        )

    async def _handle_full_meta(
        self,
        all_lists: list,
        route: RouterResponse,
        site_name: str = None,
        site_url: str = None,
        site_id: str = None,
    ) -> DataQueryResult:
        """Handle full meta queries (show everything — lists, libraries, and pages)."""
        classified = ResourceTypeDetector.classify_lists_by_type(all_lists)
        custom_lists = classified.get("lists", [])
        libraries = classified.get("libraries", [])
        site_context = f" in the **{site_name}** site" if site_name else " in your SharePoint site"

        def _fmt_item(lst: dict, kind: str) -> str:
            title = lst.get("displayName") or lst.get("name") or "Unknown"
            desc = lst.get("description", "")
            web_url = lst.get("webUrl", "")
            line = f"• **{title}** — {kind}"
            if site_name and site_url:
                line += f" in site [{site_name}]({site_url})"
            if web_url:
                line += f" | [Open]({web_url})"
            if desc:
                line += f"\n  {desc}"
            return line

        sections = []
        if libraries:
            sections.append(
                f"**Document Libraries ({len(libraries)}):**\n"
                + "\n".join(_fmt_item(l, "library") for l in libraries)
            )
        if custom_lists:
            sections.append(
                f"**Custom Lists ({len(custom_lists)}):**\n"
                + "\n".join(_fmt_item(l, "list") for l in custom_lists)
            )

        # Fetch pages if we have a site_id
        pages = []
        if site_id:
            try:
                pages = await self.sharepoint_repository.get_all_pages(site_id=site_id)
            except Exception as _pe:
                logger.debug("Could not fetch pages for full meta: %s", _pe)
        if pages:
            def _fmt_page(p: dict) -> str:
                title = p.get("title") or p.get("name") or "Untitled"
                web_url = p.get("webUrl", "")
                line = f"• **{title}** — page"
                if site_name and site_url:
                    line += f" in site [{site_name}]({site_url})"
                if web_url:
                    line += f" | [Open]({web_url})"
                return line
            sections.append(
                f"**Pages ({len(pages)}):**\n"
                + "\n".join(_fmt_page(p) for p in pages)
            )

        total = len(custom_lists) + len(libraries) + len(pages)
        _hint = (
            "\n\n"
            "💡 If you didn't find the list or library you're looking for, "
            "let me know which site it's in and I'll search there for you."
        )
        answer = (
            f"I found **{total}** resources{site_context}:\n\n"
            + "\n\n".join(sections)
            + "\n\nYou can ask me about specific data in any of these!"
            + _hint
        )

        # Suggested actions: one per discovered list/library (up to 3)
        _action_items = (custom_lists + libraries)[:3]
        suggested_actions = [
            f"Show me items in {r.get('displayName', r.get('name', ''))}"
            for r in _action_items
        ]
        if not suggested_actions:
            suggested_actions = ["Create a new list", "Show me document libraries"]
        elif len(suggested_actions) < 3:
            suggested_actions.append("Show me only document libraries")

        return DataQueryResult(
            answer=answer,
            data_summary={"total": total, "lists": len(custom_lists), "libraries": len(libraries), "pages": len(pages)},
            suggested_actions=suggested_actions,
        )

    async def _handle_site_info_query(self, question: str) -> DataQueryResult:
        """Handle queries about the current site information."""
        site_info = parse_site_info(settings.SITE_ID)
        site_name = site_info["name"]
        hostname = site_info["hostname"]
        site_url = site_info["url"]
        answer = (
            f"You're currently working on the **{site_name}** SharePoint site.\n\n"
            f"📍 Site URL: {site_url}\n"
            f"🌐 Hostname: {hostname}\n\n"
            "I can help you explore and manage lists, libraries, and data within this site!"
        )
        return DataQueryResult(
            answer=answer,
            data_summary={"site_name": site_name, "hostname": hostname},
            resource_link=site_url,
            suggested_actions=[
                "Show me all libraries",
                "Show me all lists",
                "What lists do I have?",
            ],
        )

    async def _handle_all_sites_query(self) -> DataQueryResult:
        """Handle queries asking for all sites in the organization."""
        try:
            all_sites = await self.sharepoint_repository.get_all_sites()
            if not all_sites:
                return DataQueryResult(
                    answer=(
                        "I couldn't retrieve sites from your organization. This might be due to "
                        "permissions. However, you're currently working on the configured site."
                    ),
                    suggested_actions=[
                        "What is the name of this site?",
                        "Show me all libraries",
                        "Show me all lists",
                    ],
                )

            current_site_id = settings.SITE_ID
            sites_list = []
            for site in all_sites:
                site_name = site.get("displayName") or site.get("name", "Unknown")
                site_url = site.get("webUrl", "")
                site_id = site.get("id", "")
                if site_id in current_site_id:
                    sites_list.append(f"• **{site_name}** ⭐ (Current site)\n  🔗 {site_url}")
                else:
                    sites_list.append(f"• **{site_name}**\n  🔗 {site_url}")

            sites_formatted = "\n\n".join(sites_list[:20])
            answer = f"I found **{len(all_sites)}** SharePoint site(s) in your organization:\n\n{sites_formatted}"
            if len(all_sites) > 20:
                answer += f"\n\n... and {len(all_sites) - 20} more sites."
            answer += "\n\n⭐ You're currently configured to work with the marked site."

            return DataQueryResult(
                answer=answer,
                data_summary={"total_sites": len(all_sites)},
                suggested_actions=[
                    "What is the name of the current site?",
                    "Show me all libraries in this site",
                    "Show me all lists in this site",
                ],
            )
        except Exception as exc:
            logger.error("Failed to get all sites: %s", exc)
            return DataQueryResult(
                answer=(
                    "I encountered an error retrieving sites from your organization. "
                    "This might be due to permissions or API limitations."
                ),
                suggested_actions=[
                    "What is the name of this site?",
                    "Show me all libraries",
                    "Show me all lists",
                ],
            )
