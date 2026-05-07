"""Service for reading web part content from SharePoint pages.

Uses the Microsoft Graph API canvasLayout expansion to extract text content
from page web parts (Text, RTE, Events, List, News, and custom web parts).
"""

import asyncio
import json
import logging
import re
from html import unescape
from typing import Any, Dict, List, Optional

try:
    from bs4 import BeautifulSoup as _BS4
    _HAS_BS4 = True
except ImportError:  # pragma: no cover
    _HAS_BS4 = False

from src.infrastructure.services.query_resilience import with_retry

logger = logging.getLogger(__name__)

# Concurrency limit: at most 5 pages fetched in parallel to avoid throttling
_FETCH_SEMAPHORE_LIMIT = 5

# ─────────────────────────────────────────────────────────────────────────────
# Technical / display-config prop names that carry NO user-meaningful content.
# Skipped during extraction so the LLM never sees things like
# "refreshes every 60 units" or "10 posts per page".
# ─────────────────────────────────────────────────────────────────────────────
_TECHNICAL_PROP_BLOCKLIST: frozenset = frozenset({
    # Timing / refresh
    "refreshinterval", "refreshaftersecs", "pollinginterval", "pollintervalinms",
    "cachetimeout", "cacheduration", "cachettl",
    # Pagination / layout counts
    "postsperpage", "maxpostsperpage", "maxitems", "numberofitems", "itemstoshow",
    "itemsperpage",
    "pagesize", "rowsperpage", "columns", "columncount", "numberofcolumns",
    "webpartheightkey", "height", "width",
    # Positional / zone metadata
    "layoutindex", "zoneid", "zoneindex", "order", "sectionindex",
    "columnspan", "rowspan", "emphasis",
    # UI toggles
    "pagingenabled", "showfilters", "showsearch", "showcommandbar", "hidecommandbar",
    "showwebparttitle", "showviewduplicateitem", "showsorticon", "enablesearch",
    "showsortdropdown", "hidewebpartwhemempty", "hidewebpartwhenenempty",
    "showtimeline", "showdragdrop", "showselectall", "isreadonly",
    "isdefaultfilterready", "isdefaultsearchcriteriaready",
    "showpaging", "showviewselector", "inplaceview",
    # Internal system identifiers (GUIDs / URLs)
    "version", "dataproviderid", "layoutid", "layouttype", "querytype",
    "webid", "siteid", "viewid", "defaultviewid", "selectedview", "viewxml",
    "weburl", "siteurl", "baseurl", "spfxcomponentid",
    # Filter machinery
    "filtervalue", "filtertype", "filtername", "filteroperator",
    "defaultfilter", "defaultsearchcriteria",
    # Accent / theme colours (not user content)
    "accentcolor", "themecolor", "backgroundcolor", "textcolor", "iconcolor",
})

# Prop key fragments that signal user-facing content and should ALWAYS be
# emitted (even for purely numeric values).
_CONTENT_KEY_FRAGMENTS: tuple = (
    "title", "description", "text", "name", "content", "body", "heading",
    "label", "caption", "subject", "message", "summary", "note",
    "date", "time", "start", "end", "due",
    "location", "place", "url", "link",
)

# Regex that matches a bare SharePoint GUID (value-only, not meaningful text)
_GUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# Custom SPFx web part component-ID → SharePoint list names.
# These web parts use hardcoded list names (never stored as a GUID prop) so
# the deep GUID scanner above will never find their data source.
# Map key = lowercase webPartType (component UUID from manifest).
# ─────────────────────────────────────────────────────────────────────────────
_WEBPART_COMPONENT_LIST_MAP: Dict[str, List[str]] = {
    # Recognition Wall — KudosPosts (kudos feed) + EmployeeOfMonth
    "a1b2c3d4-e5f6-7890-abcd-ef1234567890": ["KudosPosts", "EmployeeOfMonth"],
    # Announcements Hub — OPAnnouncements
    "b7a3e1d4-5c8f-4a2b-9d6e-1f0a2b3c4d5e": ["OPAnnouncements"],
    # Polls & Surveys — PollsQuestions (vote tallies stored separately)
    "b2c3d4e5-f6a7-8901-bcde-f12345678901": ["PollsQuestions"],
    # CV Recommendation — CVRecommendations
    "c4d7e2a1-8f3b-4e9c-b5a2-d1e6f0c3b8a7": ["CVRecommendations"],
    # Help Desk Devices (staff) — HelpDeskDevices + requests
    "b8b5fdf2-8eb4-40fe-b5cc-4ff211d4d291": ["HelpDeskDevices", "HelpDeskDeviceRequests"],
    # User Devices (employee self-service) — same lists
    "e4f8d50c-b26a-4d76-80f0-802513f5ccec": ["HelpDeskDevices", "HelpDeskDeviceRequests"],
}


class WebPartReaderService:
    """Reads and extracts text content from SharePoint page web parts.

    Args:
        graph_client: Authenticated Microsoft Graph API client.
    """

    def __init__(self, graph_client):
        self.graph_client = graph_client

    async def get_page_webparts(self, site_id: str, page_id: str) -> List[Dict[str, Any]]:
        """Fetch and return raw web parts for a single page.

        Calls ``GET /sites/{site_id}/pages/{page_id}?$expand=canvasLayout``
        and flattens the horizontalSections → columns → webparts structure
        into a flat list.

        Args:
            site_id: SharePoint site ID.
            page_id: SharePoint page ID.

        Returns:
            List of raw web part dicts from the Graph API response,
            or an empty list on failure (non-fatal).
        """
        endpoint = (
            f"/sites/{site_id}/pages/{page_id}/microsoft.graph.sitePage"
            "?$select=id,title,webUrl,canvasLayout&$expand=canvasLayout"
        )
        try:
            data = await with_retry(
                lambda: self.graph_client.get(endpoint),
                max_attempts=2,
                delay=1.0,
                label=f"get_page_webparts page={page_id}",
            )
        except Exception as exc:
            logger.warning("Failed to fetch web parts for page %s: %s", page_id, exc)
            return []

        canvas = data.get("canvasLayout") or {}
        webparts: List[Dict[str, Any]] = []

        # Horizontal sections → columns → webparts
        for section in canvas.get("horizontalSections") or []:
            for column in section.get("columns") or []:
                for wp in column.get("webparts") or []:
                    webparts.append(wp)

        # Vertical section → webparts (right-side column layout)
        vertical = canvas.get("verticalSection") or {}
        for wp in vertical.get("webparts") or []:
            webparts.append(wp)

        logger.info("Page %s: found %d web part(s) in canvasLayout", page_id, len(webparts))
        return webparts

    async def get_all_pages_with_content(
        self, site_id: str, pages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Fetch web part content for a list of pages with bounded concurrency.

        Args:
            site_id: SharePoint site ID.
            pages: List of page metadata dicts (must contain 'id', 'title').

        Returns:
            List of dicts: ``{page_id, page_title, page_url, webparts: [...], extracted_text}``.
        """
        semaphore = asyncio.Semaphore(_FETCH_SEMAPHORE_LIMIT)

        async def _fetch_one(page: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            page_id = page.get("id") or page.get("eTag", "").strip('"')
            page_title = page.get("title") or page.get("name") or "Untitled"
            page_url = page.get("webUrl", "")
            if not page_id:
                return None
            async with semaphore:
                wps = await self.get_page_webparts(site_id, page_id)
            texts = [self._extract_text_from_webpart(wp) for wp in wps]
            extracted = "\n\n".join(t for t in texts if t)
            return {
                "page_id": page_id,
                "page_title": page_title,
                "page_url": page_url,
                "webparts": wps,
                "extracted_text": extracted,
            }

        tasks = [_fetch_one(p) for p in pages]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        output = []
        for r in results:
            if isinstance(r, Exception):
                logger.warning("Page content fetch raised: %s", r)
            elif r is not None:
                output.append(r)
        return output

    def _extract_text_from_webpart(self, wp_data: Dict[str, Any]) -> str:
        """Extract plain text from a single web part dict.

        Schema-agnostic: instead of hard-coding specific property key names
        (which break whenever a web part's schema changes), this method emits
        a human-readable type label followed by every non-empty scalar property
        as ``key: value``.  The LLM interprets the values from the property
        names and the type context — no mapping maintenance required.

        Handles:
        * ``innerHtml`` web parts → strip HTML and return
        * All others → ``[TypeLabel]`` + ``key: value`` for every non-empty prop
          (HTML is stripped from any string value automatically)

        Never raises — all paths are try/except with JSON fallback.
        """
        try:
            inner = wp_data.get("innerHtml") or ""
            if inner:
                return self._strip_html(inner)

            data = wp_data.get("data") or {}
            props = data.get("webPartProperties") or data.get("properties") or {}
            # webPartType is at the TOP level of the web part object, not inside data
            wp_type = (
                (wp_data.get("webPartType") or data.get("webPartType") or "")
                .lower()
                .replace("-", "")
                .replace("_", "")
            )

            if not props and not wp_type:
                return ""

            lines: List[str] = []
            type_label = self._human_type_label(wp_type)
            if type_label:
                lines.append(f"[{type_label}]")

            if isinstance(props, dict):
                for k, v in props.items():
                    # Skip technical / display-config props — they have no
                    # informational value for users ("refreshes every 60 units",
                    # "10 posts per page", etc.).
                    if k.lower() in _TECHNICAL_PROP_BLOCKLIST:
                        continue
                    if isinstance(v, str) and v:
                        # Skip bare GUID values (internal list/view/web IDs)
                        if _GUID_RE.match(v.strip()):
                            continue
                        # Strip HTML from all string values so RTE content,
                        # descriptions, etc. are always readable
                        clean = self._strip_html(v)
                        if clean:
                            lines.append(f"{k}: {clean}")
                    elif isinstance(v, bool):
                        # bool before int/float — bool is a subclass of int
                        # Only emit True booleans that look like meaningful flags
                        # (skip pure UI-toggle props already covered by blocklist)
                        if v:
                            lines.append(f"{k}: {v}")
                    elif isinstance(v, (int, float)) and v is not None:
                        # Only emit numeric values for keys that look like
                        # user-facing content (dates, counts that are meaningful,
                        # etc.).  Pure layout integers (zone IDs, indices) are
                        # already blocked above; remaining ones are gated here.
                        k_lower = k.lower()
                        if any(frag in k_lower for frag in _CONTENT_KEY_FRAGMENTS):
                            lines.append(f"{k}: {v}")
                    elif isinstance(v, dict) and v:
                        # Nested objects (e.g. date/time objects like
                        # {"dateTime": "2026-06-01T...", "timeZone": "UTC"})
                        # — flatten one level so the LLM can read the values
                        flat_parts = []
                        for ik, iv in v.items():
                            if isinstance(iv, (str, int, float, bool)) and iv not in ("", None):
                                flat_parts.append(f"{ik}={iv}")
                        if flat_parts:
                            lines.append(f"{k}: {', '.join(flat_parts)}")
                        else:
                            try:
                                serialized = json.dumps(v, ensure_ascii=False)
                                if len(serialized) <= 300:
                                    lines.append(f"{k}: {serialized}")
                            except Exception:
                                pass
                    elif isinstance(v, list) and v:
                        try:
                            serialized = json.dumps(v, ensure_ascii=False)
                            if len(serialized) <= 300:
                                lines.append(f"{k}: {serialized}")
                        except Exception:
                            pass
            elif props:
                lines.append(json.dumps(props, ensure_ascii=False)[:500])

            return "\n".join(lines) if lines else ""

        except Exception as exc:
            logger.debug("_extract_text_from_webpart failed for %s: %s", wp_data, exc)
            try:
                return json.dumps(wp_data, ensure_ascii=False)[:300]
            except Exception:
                return ""

    @staticmethod
    def _human_type_label(wp_type: str) -> str:
        """Map a normalised webPartType string to a human-readable category label."""
        if "countdown" in wp_type:
            return "Countdown Timer"
        if "rte" in wp_type or "text" in wp_type:
            return "Text / Rich Content"
        if "event" in wp_type:
            return "Events"
        if "news" in wp_type:
            return "News"
        if "list" in wp_type:
            return "List"
        if "hero" in wp_type:
            return "Hero"
        if "image" in wp_type:
            return "Image"
        if "document" in wp_type or "library" in wp_type:
            return "Document Library"
        return wp_type or ""

    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags and decode entities to plain text.

        Uses BeautifulSoup when available (handles nested tags, <script>/<style>
        blocks, and malformed HTML).  Falls back to a regex stripper so the
        service still works without the optional dependency.
        """
        if not html:
            return ""
        if _HAS_BS4:
            try:
                soup = _BS4(html, "html.parser")
                # Drop script / style blocks entirely — their text is never useful
                for tag in soup(["script", "style"]):
                    tag.decompose()
                text = soup.get_text(separator=" ")
                return re.sub(r"\s+", " ", unescape(text)).strip()
            except Exception:
                pass  # fall through to regex path
        # Fallback: regex strip (less robust but zero-dep)
        text = re.sub(r"<[^>]+>", " ", html)
        text = unescape(text)
        return re.sub(r"\s+", " ", text).strip()

    # ─────────────────────────────────────────────────────────────────────────
    # List-data enrichment: resolve a web part's list reference and fetch items
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_list_id_from_wp(wp_data: Dict[str, Any]) -> Optional[str]:
        """Return the SharePoint list/library GUID referenced by a web part, or None.

        Searches the common property keys used by Microsoft first-party web parts
        that render list/library data (Announcements, News, Highlighted Content,
        Events, Document Library, List web parts, etc.)
        """
        data = wp_data.get("data") or {}
        props = data.get("webPartProperties") or data.get("properties") or {}
        if not isinstance(props, dict):
            return None

        for key in (
            "listId", "selectedListId", "sourceListId",
            "listGuid", "listWebId", "listIdentifier", "dataSourceId",
        ):
            val = props.get(key)
            if val and isinstance(val, str) and _GUID_RE.match(val.strip()):
                return val

        # News / Highlighted Content: sources array → each source may have listId
        for sources_key in ("sources", "dataProviders", "filters"):
            sources = props.get(sources_key)
            if isinstance(sources, list):
                for src in sources:
                    if isinstance(src, dict):
                        for k in ("listId", "sourceListId", "selectedListId", "dataSourceId"):
                            v = src.get(k)
                            if v and isinstance(v, str) and _GUID_RE.match(v.strip()):
                                return v

        # Fallback: deep-scan all prop values for GUIDs stored under arbitrary keys.
        # Custom SPFx web parts sometimes store a list GUID under a non-standard
        # key (e.g. 'selectedList', 'dataSource').  We run ONE conservative pass:
        #   Pass 1 — only accept GUIDs whose key name contains 'list'.
        # We deliberately skip the old "accept any GUID" Pass 2 because
        # SharePoint objects are saturated with non-list GUIDs (view IDs,
        # component IDs, etc.) and false positives cause worse bugs than misses.
        # Web parts whose lists are hardcoded in service classes are covered
        # instead by _WEBPART_COMPONENT_LIST_MAP above.
        # Keys that are known to be non-list GUIDs are skipped in this pass.
        _NON_LIST_GUID_KEYS = {
            "webid", "siteid", "viewid", "defaultviewid", "uniqueid",
            "id", "spfxcomponentid", "dataproviderid",
        }

        def _deep_scan(obj: dict, prefer_list_key: bool) -> Optional[str]:
            for k, v in obj.items():
                k_lower = k.lower()
                if k_lower in _NON_LIST_GUID_KEYS:
                    continue
                has_list_in_key = "list" in k_lower
                if prefer_list_key and not has_list_in_key:
                    continue
                if isinstance(v, str) and _GUID_RE.match(v.strip()):
                    return v
                if isinstance(v, dict):
                    r = _deep_scan(v, prefer_list_key)
                    if r:
                        return r
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict):
                            r = _deep_scan(item, prefer_list_key)
                            if r:
                                return r
            return None

        # Only run the conservative pass (keys with 'list' in their name)
        found = _deep_scan(props, prefer_list_key=True)
        return found  # None if nothing safe was found

    async def enrich_webparts_with_list_items(
        self,
        site_id: str,
        webparts: List[Dict[str, Any]],
        max_items_per_wp: int = 20,
        max_chars_per_item: int = 300,
        max_total_chars: int = 8_000,
    ) -> Dict[str, str]:
        """For each web part that references a list, fetch up to *max_items_per_wp*
        items and return a mapping ``{list_id: enriched_text_block}``.

        Two resolution strategies:
        1. GUID — `_extract_list_id_from_wp` finds a list GUID directly in props.
        2. Name — the component-ID map or a `listName`/`libraryName` prop gives a
           list display/internal name; we resolve it to a GUID via the Graph API.

        The returned dict is keyed by list GUID so the caller can substitute or
        append the live data alongside the web part's static text.
        Errors are silently ignored per web part so one broken reference does not
        fail the whole page.
        """
        enriched: Dict[str, str] = {}
        seen_list_ids: set = set()
        _total_chars = 0  # global cap across all lists on this page

        # ── Build a name→id cache lazily (one Graph call per site) ───────────
        _name_to_id_cache: Optional[Dict[str, str]] = None

        async def _resolve_list_name(name: str) -> Optional[str]:
            nonlocal _name_to_id_cache
            if _name_to_id_cache is None:
                try:
                    resp = await with_retry(
                        lambda: self.graph_client.get(
                            f"/sites/{site_id}/lists?$select=id,displayName,name&$top=500"
                        ),
                        max_attempts=2,
                        delay=0.5,
                        label="enrich_webpart list_name_cache",
                    )
                    _name_to_id_cache = {}
                    for lst in resp.get("value") or []:
                        _name_to_id_cache[lst.get("displayName", "").lower()] = lst.get("id", "")
                        _name_to_id_cache[lst.get("name", "").lower()] = lst.get("id", "")
                except Exception as exc:
                    logger.debug("enrich_webparts: name→id cache failed: %s", exc)
                    _name_to_id_cache = {}
            return _name_to_id_cache.get(name.lower())

        # ── Collect (list_id, wp_index) pairs to enrich ───────────────────────
        async def _get_list_id_for_wp(wp: Dict[str, Any]) -> Optional[str]:
            # Strategy 1: GUID in props
            lid = self._extract_list_id_from_wp(wp)
            if lid:
                return lid

            # Strategy 2: component ID → known list names
            raw_component_id = (
                wp.get("webPartType")
                or (wp.get("data") or {}).get("webPartType")
                or ""
            ).lower()
            known_names = _WEBPART_COMPONENT_LIST_MAP.get(raw_component_id)
            if known_names:
                for lname in known_names:
                    lid = await _resolve_list_name(lname)
                    if lid:
                        return lid
            elif raw_component_id and raw_component_id not in _WEBPART_COMPONENT_LIST_MAP:
                logger.debug(
                    "enrich_webparts: unknown component ID %s — consider adding to "
                    "_WEBPART_COMPONENT_LIST_MAP if it reads list data",
                    raw_component_id,
                )

            # Strategy 3: explicit listName / libraryName prop (configurable web parts)
            data = wp.get("data") or {}
            props = data.get("webPartProperties") or data.get("properties") or {}
            if isinstance(props, dict):
                for prop_key in ("listName", "libraryName", "listTitle", "spListName"):
                    name_val = props.get(prop_key)
                    if name_val and isinstance(name_val, str) and not _GUID_RE.match(name_val.strip()):
                        lid = await _resolve_list_name(name_val)
                        if lid:
                            return lid
            return None

        for wp in webparts:
            if _total_chars >= max_total_chars:
                logger.debug(
                    "enrich_webparts: reached total char cap (%d) — skipping remaining web parts",
                    max_total_chars,
                )
                break
            list_id = await _get_list_id_for_wp(wp)
            if not list_id or list_id in seen_list_ids:
                continue
            seen_list_ids.add(list_id)

            try:
                endpoint = (
                    f"/sites/{site_id}/lists/{list_id}/items"
                    f"?$expand=fields&$top={max_items_per_wp}"
                    f"&$select=id,fields"
                )
                resp = await with_retry(
                    lambda ep=endpoint: self.graph_client.get(ep),
                    max_attempts=2,
                    delay=0.5,
                    label=f"enrich_webpart list={list_id}",
                )
                items = resp.get("value") or []
                if not items:
                    continue

                lines: List[str] = []
                for item in items:
                    fields = item.get("fields") or {}
                    title = (
                        fields.get("Title") or fields.get("Name") or
                        fields.get("Subject") or fields.get("LinkTitle") or ""
                    )
                    body = (
                        fields.get("Body") or fields.get("Description") or
                        fields.get("Comments") or fields.get("Note") or ""
                    )
                    body = self._strip_html(body)
                    author = fields.get("Author") or ""
                    date_val = (
                        fields.get("Created") or fields.get("Modified") or
                        fields.get("EventDate") or fields.get("StartDate") or ""
                    )
                    parts_item = []
                    if title:
                        parts_item.append(f"**{title}**")
                    if body:
                        parts_item.append(body[:max_chars_per_item])
                    if author:
                        parts_item.append(f"by {author}")
                    if date_val:
                        parts_item.append(f"[{str(date_val)[:10]}]")
                    # Include extra fields not already captured
                    _skip_keys = {
                        "Title", "Name", "Subject", "LinkTitle", "Body",
                        "Description", "Comments", "Note", "Author",
                        "AuthorLookupId", "Created", "Modified",
                        "EventDate", "StartDate", "id", "ID",
                        "@odata.etag", "ContentType", "Modified0",
                        "Created0", "AuthorId", "EditorId",
                        "_UIVersionString", "Attachments", "Edit",
                        "LinkTitleNoMenu", "_ModerationStatus",
                    }
                    for k, v in fields.items():
                        if k in _skip_keys or k.startswith("_") or k.startswith("OData"):
                            continue
                        if isinstance(v, (str, int, float, bool)) and v not in ("", None):
                            parts_item.append(f"{k}: {v}")
                    if parts_item:
                        lines.append("- " + " | ".join(str(p) for p in parts_item))

                if lines:
                    block = "\n".join(lines)
                    # Hard-cap this list's block to keep total output bounded
                    remaining = max_total_chars - _total_chars
                    if len(block) > remaining:
                        block = block[:remaining].rsplit("\n", 1)[0]  # don't split mid-line
                    enriched[list_id] = block
                    _total_chars += len(block)
                    logger.info(
                        "Enriched list %s with %d item(s) (%d chars; total %d/%d)",
                        list_id, len(lines), len(block), _total_chars, max_total_chars,
                    )
            except Exception as exc:
                logger.debug(
                    "enrich_webparts_with_list_items: list %s failed: %s", list_id, exc
                )

        return enriched

    def get_section_metadata(self, wp_data: Dict[str, Any]) -> Dict[str, str]:
        """Extract section_title and webpart_type for Phase 2 SectionIndex.

        Returns a dict with keys ``section_title`` and ``webpart_type``.
        These are used by SectionIndexService when indexing individual web parts.
        """
        data = wp_data.get("data") or {}
        props = data.get("webPartProperties") or data.get("properties") or {}
        raw_type = (data.get("webPartType") or "").lower().replace("-", "").replace("_", "")

        # Infer human-readable webpart_type
        if "rte" in raw_type or "text" in raw_type:
            webpart_type = "text"
        elif "event" in raw_type:
            webpart_type = "events"
        elif "news" in raw_type:
            webpart_type = "news"
        elif "list" in raw_type:
            webpart_type = "list"
        elif "hero" in raw_type:
            webpart_type = "hero"
        else:
            webpart_type = "custom"

        # Section title: use explicit title prop first, then first heading from extracted text
        title = (
            props.get("title")
            or props.get("webTitle")
            or props.get("listTitle")
            or ""
        )
        if not title:
            # Heuristic: first non-empty line of extracted text (max 80 chars)
            extracted = self._extract_text_from_webpart(wp_data)
            first_line = extracted.split("\n")[0][:80].strip() if extracted else ""
            title = first_line

        return {"section_title": title, "webpart_type": webpart_type}
