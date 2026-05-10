"""Mixin providing specific-data and search-fallback handlers for AIDataQueryService."""

import json
import logging
import re
from typing import Any, Dict, List, Optional

from src.domain.entities import DataQueryResult
from src.domain.value_objects.resource_candidate import ResourceCandidate
from src.infrastructure.external_services.query.prompts import QUERY_SYSTEM_PROMPT
from src.infrastructure.schemas.query_schemas import DataQueryResponseModel
from src.infrastructure.services.list_item_index import ListItemIndexService

logger = logging.getLogger(__name__)


class DataQueryMixin:
    """Handlers for specific_data and Graph-search fallback.

    Requires *self* to provide:
        self.list_repository
        self.site_repository
        self.search_service  – SearchService
        self.client, self.model – instructor AI client
        self._last_list_id, self._last_list_name   – context tracking
        self._last_site_id,  self._last_site_name
    """

    async def _handle_specific_data_query(
        self,
        question: str,
        matched_list: dict,
        all_lists: list,
        site_id: str = None,
        site_name: str = None,
        resource_web_url: str = None,
        sibling_resources: Optional[List[ResourceCandidate]] = None,
    ) -> DataQueryResult:
        """Handle queries about data within a specific list."""
        target_list_id = matched_list["id"]
        target_list_name = matched_list["name"]
        target_list_url = (
            next((l.get("webUrl", "") for l in all_lists if l.get("id") == target_list_id), "")
            or resource_web_url
            or ""
        )
        site_context = f" in the **{site_name}** site" if site_name else ""
        # Guard: never expose a bare GUID as a site name in user-facing messages
        import re as _re_dm
        if site_name and _re_dm.match(r"^[0-9a-fA-F]{8}-", site_name):
            site_context = ""
        logger.info(
            "Querying data from list: '%s'%s (id=%s)",
            target_list_name,
            f" in {site_name}" if site_name else "",
            target_list_id,
        )

        user_ctx = _extract_current_user(question)
        question_no_user_tag = _strip_current_user_tag(question)

        items_raw = await self.list_repository.get_list_items(target_list_id, site_id=site_id)
        items = [item.get("fields", {}) for item in items_raw]
        total_items_before_person_filter = len(items)

        # ── Resolve personOrGroup LookupId fields → display names ─────────
        # SharePoint returns person fields as e.g. {"EmployeeLookupId": 42}
        # which is meaningless to the AI.  Resolve to human-readable names.
        try:
            from src.infrastructure.services.person_field_resolver import resolve_person_fields
            _columns = await self.list_repository.get_list_columns(
                target_list_id, site_id=site_id
            )
            items = await resolve_person_fields(
                items, _columns, self.graph_client,
                site_id or self.site_id,
            )
        except Exception as _pf_err:
            logger.debug("Person field resolution skipped (non-fatal): %s", _pf_err)

        # ── Deterministic personal filtering for "my / I gave / I received" ──
        # We keep this in code (not prompt-only) to avoid leaking all records
        # when person/group fields are represented in inconsistent shapes.
        personal_scope = _detect_personal_scope(question_no_user_tag)
        is_kudos_query = "kudo" in question_no_user_tag.lower() or "recognition" in question_no_user_tag.lower()
        if user_ctx:
            logger.info(
                "Query debug: list='%s' user='%s' scope='%s' total_items=%d",
                target_list_name,
                _mask_user_email(user_ctx.get("email", "")),
                personal_scope or "none",
                total_items_before_person_filter,
            )

        if user_ctx and personal_scope:
            user_lookup_ids = await _resolve_user_lookup_ids(
                self.graph_client,
                site_id or self.site_id,
                user_ctx,
            )
            if user_lookup_ids:
                logger.info(
                    "Query debug: list='%s' resolved_user_lookup_ids=%s",
                    target_list_name,
                    sorted(user_lookup_ids),
                )

            filtered, filter_stats = _filter_items_for_user(
                items,
                user_ctx,
                personal_scope,
                user_lookup_ids=user_lookup_ids,
            )
            items = filtered
            logger.info(
                "Query debug: list='%s' personal_filter_applied scope='%s' before=%d after=%d hinted_matches=%d fallback_matches=%d",
                target_list_name,
                personal_scope,
                filter_stats.get("before", 0),
                filter_stats.get("after", 0),
                filter_stats.get("hinted_matches", 0),
                filter_stats.get("fallback_matches", 0),
            )
            if filter_stats.get("diagnostics"):
                logger.info(
                    "Query debug: list='%s' personal_filter_diagnostics=%s",
                    target_list_name,
                    filter_stats.get("diagnostics"),
                )
        elif is_kudos_query:
            logger.info(
                "Query debug: kudos query without personal scope; returning full dataset (count=%d)",
                len(items),
            )

        # ── Cache result for future requests ──────────────────────────
        try:
            _index = ListItemIndexService()
            await _index.index_list(target_list_id, site_id or "", target_list_name, items)
        except Exception:
            pass  # caching failure is non-fatal

        # Save context even for empty lists
        self._last_list_id = target_list_id
        self._last_list_name = target_list_name
        self._last_site_id = site_id
        self._last_site_name = site_name

        if len(items) == 0:
            if user_ctx and personal_scope == "gave":
                return DataQueryResult(
                    answer=(
                        "You haven't given any kudos yet. "
                        "Would you like me to help you create one?"
                    ),
                    data_summary={"items_analyzed": 0, "list_empty": True, "personal_filter": "gave"},
                    source_list=target_list_name,
                    resource_link=target_list_url,
                    suggested_actions=[
                        "Create a new kudos post",
                        "Show me all kudos",
                        "Show me kudos I received",
                    ],
                )
            if user_ctx and personal_scope == "received":
                return DataQueryResult(
                    answer=(
                        "You don't have any kudos received yet. "
                        "Would you like me to show all kudos instead?"
                    ),
                    data_summary={"items_analyzed": 0, "list_empty": True, "personal_filter": "received"},
                    source_list=target_list_name,
                    resource_link=target_list_url,
                    suggested_actions=[
                        "Show me all kudos",
                        "Show me kudos I gave",
                    ],
                )

            # Never expose the internal list name — it may be a camelCase identifier
            # like 'KudosComments' that the user never configured and doesn't recognise.
            return DataQueryResult(
                answer=(
                    "There are currently no items matching your request. "
                    "Would you like me to help you add some data?"
                ),
                data_summary={"items_analyzed": 0, "list_empty": True},
                source_list=target_list_name,
                resource_link=target_list_url,
                suggested_actions=[
                    "Add some sample items",
                    "Show me all available lists",
                    "What else can I help you with?",
                ],
            )

        # ── Narrative formatting for personal kudos queries ─────────────────
        # Personal kudos requests read better as prose, but explicit "show all"
        # requests should still enumerate the actual records.
        is_kudos_query_detailed = "kudo" in question_no_user_tag.lower() or "recognition" in question_no_user_tag.lower()
        if is_kudos_query_detailed and personal_scope:
            narrative_answer = _format_kudos_narrative(
                items,
                personal_scope,
                user_ctx.get("name", "") if user_ctx else "",
            )
            if narrative_answer:
                logger.info(
                    "Query debug: narrative_kudos_mode enabled for list='%s' scope='%s' count=%d",
                    target_list_name,
                    personal_scope or "all",
                    len(items),
                )
                return DataQueryResult(
                    answer=narrative_answer,
                    data_summary={
                        "items_analyzed": len(items),
                        "narrative_mode": True,
                        "scope": personal_scope or "all",
                    },
                    source_list=target_list_name,
                    resource_link=target_list_url,
                    suggested_actions=[
                        "Give me more details",
                        "Show me other queries",
                        "What else can I help?",
                    ],
                )

        if _wants_explicit_listing(question_no_user_tag):
            listing_answer = _build_explicit_item_listing(target_list_name, items)
            if listing_answer:
                logger.info(
                    "Query debug: explicit_listing_mode enabled for list='%s' count=%d",
                    target_list_name,
                    len(items),
                )
                return DataQueryResult(
                    answer=listing_answer,
                    data_summary={
                        "items_analyzed": len(items),
                        "explicit_listing_mode": True,
                    },
                    source_list=target_list_name,
                    resource_link=target_list_url,
                    suggested_actions=[
                        "Show details for item 1",
                        "Filter these results",
                        "Show me my items only",
                    ],
                )

        # ── Document library detection ──────────────────────────────────
        # If the matched "list" is actually a document library, the items
        # only contain file metadata (name, size, modified date) — NOT the
        # content inside the files.  Any specific question about a library's
        # data requires reading the actual files, so we always redirect to
        # _handle_data_extraction_query which downloads and parses them.
        _DOC_LIBRARY_FIELDS = {"FileLeafRef", "File_x0020_Size", "FileSizeDisplay", "DocIcon"}
        is_document_library = any(
            _DOC_LIBRARY_FIELDS & set(item.keys()) for item in items[:3]
        )
        if is_document_library:
            logger.info(
                "Detected document library '%s' — redirecting to data extraction "
                "for file content reading",
                target_list_name,
            )
            return await self._handle_data_extraction_query(
                question, target_list_id, target_list_name
            )

        # ── Top-K filtering: score items by keyword relevance ─────────────
        _keywords = [w for w in question.lower().split() if len(w) > 3]
        _TOP_K = 50
        if _keywords and len(items) > _TOP_K:
            def _item_score(item: dict) -> int:
                item_str = json.dumps(item).lower()
                return sum(1 for kw in _keywords if kw in item_str)
            items = sorted(items, key=_item_score, reverse=True)[:_TOP_K]
            _showing_prefix = f"Showing top {len(items)} of {len(items_raw)} items most relevant to your question.\n\n"
        else:
            _showing_prefix = ""

        # Truncate total context at 12000 chars; siblings trimmed first
        _MAIN_BUDGET = 12000
        _context_str = str(items)
        _sibling_blocks = ""
        if sibling_resources:
            _sib_parts = []
            for _sib in sibling_resources:
                try:
                    _sib_items_raw = await self.list_repository.get_list_items(
                        _sib.resource_id, site_id=_sib.site_id
                    )
                    _sib_items = [i.get("fields", {}) for i in _sib_items_raw]
                    _sib_str = str(_sib_items)[:2000]
                    _sib_parts.append(f"\n\n--- Related list: '{_sib.title}' ---\n{_sib_str}")
                except Exception:
                    pass
            _sibling_blocks = "".join(_sib_parts)

        _total = len(_context_str) + len(_sibling_blocks)
        if _total > _MAIN_BUDGET:
            # trim siblings first
            _available_for_siblings = max(0, _MAIN_BUDGET - len(_context_str))
            _sibling_blocks = _sibling_blocks[:_available_for_siblings]
        if len(_context_str) > _MAIN_BUDGET:
            _context_str = _context_str[:_MAIN_BUDGET] + "..."

        data_prompt = (
            f"{QUERY_SYSTEM_PROMPT}\n\n"
            f"{_showing_prefix}"
            f"Data from list '{target_list_name}':\n{_context_str}"
            f"{_sibling_blocks}\n\n"
            f"User Question: {question_no_user_tag}"
        )
        kwargs = {
            "messages": [{"role": "user", "content": data_prompt}],
            "response_model": DataQueryResponseModel,
        }
        if self.model:
            kwargs["model"] = self.model
        final_response = self.client.chat.completions.create(**kwargs)

        logger.info(
            "Saved query context: list=%s, site=%s", target_list_name, site_name or "default"
        )
        return DataQueryResult(
            answer=final_response.answer,
            data_summary={
                "items_analyzed": len(items),
                "sibling_lists_included": [s.title for s in (sibling_resources or [])],
            },
            source_list=target_list_name,
            resource_link=target_list_url,
            suggested_actions=final_response.suggested_actions,
        )

    async def _handle_graph_search_fallback(self, question: str) -> DataQueryResult:
        """Use Microsoft Graph Search as a fallback when no candidate is confident."""
        try:
            hits = await self.search_service.search_sharepoint(
                question, entity_types=["listItem", "driveItem"]
            )
            if not hits:
                return DataQueryResult(
                    answer="I couldn't find any data related to your question across all SharePoint resources.",
                    suggested_actions=[
                        "Try a different search term",
                        "Show me all lists",
                        "Show me all document libraries",
                    ],
                )

            lines = []
            for hit in hits[:10]:
                resource = hit.get("resource", {})
                name = resource.get("name") or resource.get("fields", {}).get("Title") or "Untitled"
                web_url = resource.get("webUrl", "")
                summary = hit.get("summary", "")
                if web_url:
                    lines.append(
                        f"- **[{name}]({web_url})** — {summary}" if summary else f"- **[{name}]({web_url})**"
                    )
                else:
                    lines.append(f"- **{name}**" + (f" — {summary}" if summary else ""))

            answer = (
                f"I searched across all SharePoint resources and found **{len(hits)}** related result(s):\n\n"
                + "\n".join(lines)
            )
            return DataQueryResult(
                answer=answer,
                data_summary={"search_hits": len(hits)},
                suggested_actions=[
                    "Show me more details about one of these results",
                    "Try a more specific question",
                ],
            )
        except Exception as exc:
            logger.error("Graph Search fallback failed: %s", exc)
            return DataQueryResult(
                answer="I encountered an error searching across SharePoint. Please try rephrasing your question.",
                suggested_actions=["Show me all lists", "Show me all document libraries"],
            )


_CURRENT_USER_RE = re.compile(
    r"^\[Current user:\s*(?P<name>.*?)\s*\(email:\s*(?P<email>[^\)]+)\)\]\s*",
    re.IGNORECASE,
)


def _extract_current_user(question: str) -> Optional[dict]:
    if not question:
        return None
    m = _CURRENT_USER_RE.match(question.strip())
    if not m:
        return None
    name = (m.group("name") or "").strip()
    email = (m.group("email") or "").strip().lower()
    return {"name": name, "email": email}


def _strip_current_user_tag(question: str) -> str:
    if not question:
        return ""
    return _CURRENT_USER_RE.sub("", question.strip()).strip()


def _detect_personal_scope(question: str) -> Optional[str]:
    q = (question or "").lower()
    if not q:
        return None

    gave_patterns = (
        "i gave", "i give", "given by me", "sent by me", "i sent", "i posted",
    )
    received_patterns = (
        "i received", "i have received", "received by me", "sent to me", "for me",
    )

    if any(p in q for p in gave_patterns):
        return "gave"
    if any(p in q for p in received_patterns):
        return "received"

    # Additional first-person phrasing support.
    # This captures natural variants like:
    # - "kudos for me"
    # - "did i receive any kudos"
    # - "was i recognized"
    if re.search(r"\bfor\s+me\b", q):
        return "received"

    if re.search(r"\bi\s+(?:received|receive|get|got|was\s+given|was\s+recognized)\b", q):
        return "received"

    if re.search(r"\bi\s+(?:gave|give|sent|posted|created|submitted)\b", q):
        return "gave"

    # Generic personal possession scope
    if any(tok in q for tok in (" my ", " mine", "assigned to me", "belonging to me", "i created", "i submitted")):
        return "any"

    return None


def _mask_user_email(email: str) -> str:
    raw = (email or "").strip()
    if not raw or "@" not in raw:
        return ""
    local, domain = raw.split("@", 1)
    if len(local) <= 2:
        masked_local = "*" * len(local)
    else:
        masked_local = local[:2] + "***"
    return f"{masked_local}@{domain}"


def _filter_items_for_user(
    items: List[dict],
    user_ctx: dict,
    scope: str,
    user_lookup_ids: Optional[set[int]] = None,
) -> tuple[List[dict], dict]:
    if not items:
        return items, {"before": 0, "after": 0, "hinted_matches": 0, "fallback_matches": 0, "diagnostics": []}

    user_name = (user_ctx.get("name") or "").strip().lower()
    user_email = (user_ctx.get("email") or "").strip().lower()
    email_prefix = user_email.split("@", 1)[0] if "@" in user_email else user_email
    name_parts = [p for p in re.split(r"\s+", user_name) if p]
    user_tokens = set(name_parts)
    if user_email:
        user_tokens.add(user_email)
    if email_prefix:
        user_tokens.add(email_prefix)

    if not user_tokens:
        return items, {"before": len(items), "after": len(items), "hinted_matches": 0, "fallback_matches": 0, "diagnostics": []}

    gave_field_hints = (
        "from", "giver", "givenby", "sentby", "author", "createdby", "submittedby", "postedby", "recognizer",
    )
    received_field_hints = (
        "to", "recipient", "receivedby", "assignee", "owner", "employee", "nominee", "recognized", "recipientname",
    )

    def _matches_user(value: object) -> bool:
        if user_lookup_ids:
            numeric_candidates = _extract_numeric_candidates(value)
            if any(num in user_lookup_ids for num in numeric_candidates):
                return True

        candidates = _extract_text_candidates(value)
        if not candidates:
            return False
        for text in candidates:
            if user_email and user_email in text:
                return True
            if email_prefix and email_prefix in text:
                return True
            if any(tok and tok in text for tok in name_parts):
                return True
        return False

    def _match_on_fields(item: dict, field_hints: tuple[str, ...]) -> bool:
        # First pass: hinted person-direction fields.
        for k, v in item.items():
            key_norm = str(k or "").lower().replace("_", "").replace(" ", "")
            if any(h in key_norm for h in field_hints) and _matches_user(v):
                return True

        # Fallback: any field with user identity.
        if scope == "any":
            return any(_matches_user(v) for v in item.values())
        return False

    filtered: List[dict] = []
    hinted_matches = 0
    diagnostics: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key_hints = gave_field_hints if scope == "gave" else received_field_hints if scope == "received" else ()
        hinted_fields: List[Dict[str, Any]] = []
        for k, v in item.items():
            key_norm = str(k or "").lower().replace("_", "").replace(" ", "")
            if key_hints and any(h in key_norm for h in key_hints):
                hinted_fields.append({
                    "field": k,
                    "value": _mask_value_for_log(v),
                    "matched": _matches_user(v),
                })

        if scope == "gave" and _match_on_fields(item, gave_field_hints):
            filtered.append(item)
            hinted_matches += 1
        elif scope == "received" and _match_on_fields(item, received_field_hints):
            filtered.append(item)
            hinted_matches += 1
        elif scope == "any" and _match_on_fields(item, ()):  # any-field fallback path
            filtered.append(item)
            hinted_matches += 1
        elif len(diagnostics) < 3:
            reason = "no hinted person/group field values matched user"
            if scope in {"gave", "received"} and not hinted_fields:
                reason = "no directional person/group fields found for this item"
            diagnostics.append(
                {
                    "reason": reason,
                    "hinted_fields": hinted_fields,
                }
            )

    # If directional filtering was too strict, gracefully fallback to any-field match.
    fallback_matches = 0
    if not filtered and scope in {"gave", "received"}:
        for item in items:
            if isinstance(item, dict) and any(_matches_user(v) for v in item.values()):
                filtered.append(item)
                fallback_matches += 1

    stats = {
        "before": len(items),
        "after": len(filtered),
        "hinted_matches": hinted_matches,
        "fallback_matches": fallback_matches,
        "diagnostics": diagnostics,
    }
    return filtered, stats


async def _resolve_user_lookup_ids(graph_client: Any, site_id: str, user_ctx: dict) -> set[int]:
    """Resolve the signed-in user to SharePoint User Information List numeric IDs."""
    email = (user_ctx.get("email") or "").strip().lower()
    name = (user_ctx.get("name") or "").strip().lower()
    if not site_id or not (email or name):
        return set()

    try:
        data = await graph_client.get(
            f"/sites/{site_id}/lists('User Information List')/items"
            "?$select=id&$expand=fields($select=Title,EMail,Name,UserName)&$top=500"
        )
    except Exception as e:
        logger.debug("Query debug: failed to resolve user lookup IDs: %s", e)
        return set()

    values = data.get("value", []) if isinstance(data, dict) else []
    resolved: set[int] = set()
    email_prefix = email.split("@", 1)[0] if "@" in email else ""
    name_tokens = [tok for tok in re.split(r"\s+", name) if tok]

    for item in values:
        if not isinstance(item, dict):
            continue
        raw_id = item.get("id")
        try:
            numeric_id = int(raw_id)
        except (TypeError, ValueError):
            continue

        fields = item.get("fields", {}) if isinstance(item.get("fields"), dict) else {}
        candidates = _extract_text_candidates(fields)
        if not candidates:
            continue

        match = False
        for text in candidates:
            if email and email in text:
                match = True
                break
            if email_prefix and email_prefix in text:
                match = True
                break
            if any(tok and tok in text for tok in name_tokens):
                match = True
                break

        if match:
            resolved.add(numeric_id)

    return resolved


def _extract_text_candidates(value: Any) -> List[str]:
    """Flatten likely identity-bearing text from scalar/list/dict values."""
    out: List[str] = []
    if value is None:
        return out

    if isinstance(value, str):
        text = value.strip().lower()
        if text:
            out.append(text)
        return out

    if isinstance(value, (int, float, bool)):
        return out

    if isinstance(value, list):
        for entry in value:
            out.extend(_extract_text_candidates(entry))
        return out

    if isinstance(value, dict):
        preferred_keys = (
            "email", "mail", "upn", "userprincipalname",
            "displayname", "name", "title", "lookupvalue",
            "user", "person", "from", "to", "givenby", "recipient",
        )
        for k, v in value.items():
            key_norm = str(k or "").lower().replace("_", "")
            if any(pk in key_norm for pk in preferred_keys):
                out.extend(_extract_text_candidates(v))
        if not out:
            # Fallback: still inspect nested values in unknown shapes.
            for v in value.values():
                out.extend(_extract_text_candidates(v))
        return out

    return out


def _extract_numeric_candidates(value: Any) -> List[int]:
    """Extract numeric IDs from scalar/list/dict values (e.g., LookupId fields)."""
    out: List[int] = []
    if value is None:
        return out

    if isinstance(value, bool):
        return out

    if isinstance(value, (int, float)):
        out.append(int(value))
        return out

    if isinstance(value, str):
        txt = value.strip()
        if txt.isdigit():
            out.append(int(txt))
        return out

    if isinstance(value, list):
        for entry in value:
            out.extend(_extract_numeric_candidates(entry))
        return out

    if isinstance(value, dict):
        preferred_keys = ("lookupid", "id", "userid", "authorlookupid", "givenbylookupid", "recipientlookupid")
        for k, v in value.items():
            key_norm = str(k or "").lower().replace("_", "")
            if any(pk in key_norm for pk in preferred_keys):
                out.extend(_extract_numeric_candidates(v))
        if not out:
            for v in value.values():
                out.extend(_extract_numeric_candidates(v))
        return out

    return out


def _mask_value_for_log(value: Any) -> str:
    """Mask sensitive values in debug logs while preserving troubleshooting signal."""
    numeric_candidates = _extract_numeric_candidates(value)
    if numeric_candidates:
        return " | ".join(f"#{n}" for n in numeric_candidates[:3])

    candidates = _extract_text_candidates(value)
    if not candidates:
        return ""
    masked = []
    for text in candidates[:3]:
        if "@" in text:
            masked.append(_mask_user_email(text))
        elif len(text) > 2:
            masked.append(text[:2] + "***")
        else:
            masked.append("**")
    return " | ".join(masked)


def _wants_explicit_listing(question: str) -> bool:
    q = (question or "").lower().strip()
    if not q:
        return False

    cues = (
        "show me all",
        "show all",
        "show them",
        "show those",
        "show these",
        "all of them",
        "list them",
        "list those",
        "list these",
        "list all",
        "show every",
        "all kudos",
        "all announcements",
    )
    return any(c in q for c in cues)


def _format_kudos_narrative(items: List[dict], scope: Optional[str], user_name: str = "") -> str:
    """Format kudos as narrative prose instead of tabular listing.
    
    Examples:
    - scope='gave': "You gave 3 kudos to Ahmed, Sara, and Omar."
    - scope='received': "You received 2 kudos from John and Maria."
    - scope=None: "There are 5 kudos given out: Ahmed (2), Sara (2), and Omar (1)."
    """
    if not items:
        return ""
    
    count = len(items)
    
    # Extract recipient/giver names based on scope
    names = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        
        if scope == "gave":
            # Extract who received the kudos
            recipient = _pick_recipient_name(item)
            if recipient:
                names.add(recipient)
        elif scope == "received":
            # Extract who gave the kudos
            giver = _pick_giver_name(item)
            if giver:
                names.add(giver)
        else:
            # For "all", show both givers and recipients (who gave to whom)
            giver = _pick_giver_name(item)
            if giver:
                names.add(giver)
    
    names_list = sorted(names)
    
    if not names_list:
        if scope == "gave":
            return f"You gave {count} kudos."
        elif scope == "received":
            return f"You received {count} kudos."
        else:
            return f"There are {count} kudos."
    
    # Format names as comma-separated with "and" before last item
    if len(names_list) == 1:
        names_str = names_list[0]
    elif len(names_list) == 2:
        names_str = f"{names_list[0]} and {names_list[1]}"
    else:
        names_str = ", ".join(names_list[:-1]) + f", and {names_list[-1]}"
    
    # Build narrative sentence
    if scope == "gave":
        if count == 1:
            return f"You gave **1 kudos** to **{names_str}**."
        else:
            return f"You gave **{count} kudos** to **{names_str}**."
    elif scope == "received":
        if count == 1:
            return f"You received **1 kudos** from **{names_str}**."
        else:
            return f"You received **{count} kudos** from **{names_str}**."
    else:
        # For "all" scope, show distribution
        return f"There are **{count} kudos** given out to: **{names_str}**."


def _pick_giver_name(item: Dict[str, Any]) -> Optional[str]:
    """Extract giver/author name from a kudos item."""
    giver_keys = (
        "GivenBy", "givenby", "Author", "author", "CreatedBy", "createdby",
        "SentBy", "sentby", "From", "from",
    )
    for key in giver_keys:
        value = item.get(key)
        name = _extract_single_name(value)
        if name:
            return name
    
    # Fallback: try to find any field with "giver" or "author"
    for key, value in item.items():
        key_norm = str(key or "").lower().replace("_", "")
        if "giver" in key_norm or "author" in key_norm or "from" in key_norm:
            name = _extract_single_name(value)
            if name:
                return name
    
    return None


def _pick_recipient_name(item: Dict[str, Any]) -> Optional[str]:
    """Extract recipient/to name from a kudos item."""
    recipient_keys = (
        "Recipient", "recipient", "To", "to", "Employee", "employee",
        "SentTo", "sentto",
    )
    for key in recipient_keys:
        value = item.get(key)
        name = _extract_single_name(value)
        if name:
            return name
    
    # Fallback: try to find any field with "recipient" or "to"
    for key, value in item.items():
        key_norm = str(key or "").lower().replace("_", "")
        if "recipient" in key_norm or ("to" in key_norm and "category" not in key_norm):
            name = _extract_single_name(value)
            if name:
                return name
    
    return None


def _extract_single_name(value: Any) -> Optional[str]:
    """Extract a single display name from various value types."""
    if value is None:
        return None
    
    if isinstance(value, str):
        text = value.strip()
        if text and not text.isdigit():
            return text
        return None
    
    if isinstance(value, dict):
        # Look for common display name keys
        for key in ("displayName", "name", "title", "Title"):
            if key in value:
                name = value[key]
                if isinstance(name, str):
                    return name.strip()
    
    if isinstance(value, list) and value:
        # Get first non-None element
        for entry in value:
            name = _extract_single_name(entry)
            if name:
                return name
    
    return None


def _build_explicit_item_listing(list_name: str, items: List[dict], max_items: int = 20) -> str:
    if not items:
        return ""

    shown = items[:max_items]
    header = f"**All {list_name} ({len(items)})**"
    lines: List[str] = [header, ""]

    for idx, item in enumerate(shown, start=1):
        if not isinstance(item, dict):
            continue
        title = _pick_primary_value(item)
        details = _pick_secondary_values(item, limit=3)
        if details:
            lines.append(f"{idx}. {title} — {', '.join(details)}")
        else:
            lines.append(f"{idx}. {title}")

    if len(items) > max_items:
        lines.append("")
        lines.append(f"Showing first {max_items} of {len(items)} records.")

    return "\n".join(lines).strip()


def _pick_primary_value(item: Dict[str, Any]) -> str:
    preferred = (
        "Title", "title", "Name", "name", "Subject", "subject",
        "Announcement", "announcement", "Message", "message",
        "Kudos", "kudos", "Recognition", "recognition",
    )
    for key in preferred:
        value = item.get(key)
        text = _stringify_for_display(value)
        if text:
            return text

    for key, value in item.items():
        if _is_system_field(key):
            continue
        text = _stringify_for_display(value)
        if text:
            return text

    return "(No title)"


def _pick_secondary_values(item: Dict[str, Any], limit: int = 3) -> List[str]:
    result: List[str] = []
    preferred = (
        "GivenBy", "Recipient", "Author", "Created", "Category", "Status",
        "Department", "Date", "DueDate", "Priority",
    )

    for key in preferred:
        if key not in item:
            continue
        text = _stringify_for_display(item.get(key))
        if text:
            result.append(f"{key}: {text}")
        if len(result) >= limit:
            return result

    for key, value in item.items():
        if len(result) >= limit:
            break
        if _is_system_field(key):
            continue
        if any(p in key for p in ("Title", "title", "Name", "name", "Message", "message")):
            continue
        text = _stringify_for_display(value)
        if text:
            result.append(f"{key}: {text}")

    return result


def _stringify_for_display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        return text if len(text) <= 120 else text[:117] + "..."
    if isinstance(value, list):
        parts = [_stringify_for_display(v) for v in value]
        parts = [p for p in parts if p]
        return ", ".join(parts[:3])
    if isinstance(value, dict):
        texts = _extract_text_candidates(value)
        if texts:
            pick = texts[0]
            return pick if len(pick) <= 120 else pick[:117] + "..."
        nums = _extract_numeric_candidates(value)
        if nums:
            return str(nums[0])
    return ""


def _is_system_field(key: str) -> bool:
    k = str(key or "")
    kl = k.lower()
    if not k:
        return True
    if k.startswith("@") or k.startswith("_"):
        return True
    blocked = (
        "lookupid",
        "contenttype",
        "attachments",
        "fileleafref",
        "uiversion",
        "compliance",
        "modified_x0020_by",
        "created_x0020_by",
    )
    return any(b in kl for b in blocked)
