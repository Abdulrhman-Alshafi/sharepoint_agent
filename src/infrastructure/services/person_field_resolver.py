"""Resolve personOrGroup LookupId values in SharePoint list items to display names.

When the Graph API returns list items, person/group columns appear as:
    ``{"EmployeeLookupId": 42}``
This is meaningless to end-users and AI prompts.  This module detects such
fields, resolves the numeric IDs to human-readable display names via the
SharePoint Site User Information List, and rewrites the item dicts so the
AI receives ``{"Employee": "Ahmad Ali"}`` instead.
"""

import logging
from typing import Any, Dict, List, Set

logger = logging.getLogger(__name__)

# Module-level cache:  site_id -> {lookup_id -> display_name}
_user_display_cache: Dict[str, Dict[int, str]] = {}


async def resolve_person_fields(
    items: List[Dict[str, Any]],
    columns: List[Dict[str, Any]],
    graph_client: Any,
    site_id: str,
) -> List[Dict[str, Any]]:
    """Enrich list item dicts by replacing ``LookupId`` person fields with names.

    Args:
        items: Raw field dicts from ``item.get("fields", {})``.
        columns: Column metadata list (from ``get_list_columns``).
        graph_client: A ``GraphAPIClient`` instance (has ``.get()`` method).
        site_id: The Graph site ID (e.g. ``contoso.sharepoint.com,abc,...``).

    Returns:
        The same list of dicts, mutated in-place with person fields resolved.
    """
    if not items or not columns:
        return items

    # 1. Detect personOrGroup columns by column metadata
    person_col_names: Set[str] = set()
    for col in columns:
        if col.get("personOrGroup") is not None:
            person_col_names.add(col.get("name", ""))

    # 2. Also detect LookupId fields heuristically from the items themselves
    #    (handles cases where column metadata is unavailable)
    _LOOKUP_SUFFIX = "LookupId"
    heuristic_person_keys: Set[str] = set()
    for item in items[:5]:  # sample first 5 items
        for key in item:
            if key.endswith(_LOOKUP_SUFFIX):
                base_name = key[: -len(_LOOKUP_SUFFIX)]
                if base_name:
                    heuristic_person_keys.add(base_name)

    # Combine both detection methods
    all_person_keys = person_col_names | heuristic_person_keys
    if not all_person_keys:
        return items  # No person fields detected

    # 3. Collect all unique LookupId values that need resolving
    lookup_ids: Set[int] = set()
    for item in items:
        for base_name in all_person_keys:
            lid_key = f"{base_name}{_LOOKUP_SUFFIX}"
            id_key = f"{base_name}Id"
            for raw in (item.get(lid_key), item.get(id_key), item.get(base_name)):
                lookup_ids |= _collect_lookup_ids(raw)

    id_to_name: Dict[int, str] = {}
    if lookup_ids:
        # 4. Resolve LookupIds to display names
        id_to_name = await _resolve_user_ids(lookup_ids, graph_client, site_id)

    # 5. Rewrite item dicts: normalize person fields to readable names
    for item in items:
        for base_name in all_person_keys:
            lid_key = f"{base_name}{_LOOKUP_SUFFIX}"
            id_key = f"{base_name}Id"

            names = _collect_display_names(item.get(base_name))
            ids = _collect_lookup_ids(item.get(lid_key))
            ids |= _collect_lookup_ids(item.get(id_key))
            ids |= _collect_lookup_ids(item.get(base_name))

            if not names and ids:
                for uid in sorted(ids):
                    names.append(id_to_name.get(uid, f"User #{uid}"))

            if names:
                # Deduplicate while preserving order
                uniq = list(dict.fromkeys([n.strip() for n in names if str(n).strip()]))
                if uniq:
                    item[base_name] = uniq[0] if len(uniq) == 1 else ", ".join(uniq)
                    item.pop(lid_key, None)
                    item.pop(id_key, None)

    logger.info(
        "Resolved %d person field(s) across %d items (columns: %s)",
        len(lookup_ids), len(items), ", ".join(sorted(all_person_keys)),
    )
    return items


def _collect_lookup_ids(value: Any) -> Set[int]:
    """Extract numeric user IDs from common SharePoint person field shapes."""
    ids: Set[int] = set()
    if value is None:
        return ids
    if isinstance(value, (int, float)):
        ids.add(int(value))
        return ids
    if isinstance(value, list):
        for v in value:
            ids |= _collect_lookup_ids(v)
        return ids
    if isinstance(value, dict):
        for key in ("LookupId", "lookupId", "Id", "id", "UserId"):
            raw = value.get(key)
            if isinstance(raw, (int, float)):
                ids.add(int(raw))
        if isinstance(value.get("results"), list):
            ids |= _collect_lookup_ids(value.get("results"))
    return ids


def _collect_display_names(value: Any) -> List[str]:
    """Extract readable names from common SharePoint person field shapes."""
    names: List[str] = []
    if value is None:
        return names
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        for v in value:
            names.extend(_collect_display_names(v))
        return names
    if isinstance(value, dict):
        for key in ("LookupValue", "Title", "displayName", "Name", "name", "EMail", "Email", "UserName", "userPrincipalName"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                names.append(raw.strip())
        if isinstance(value.get("results"), list):
            names.extend(_collect_display_names(value.get("results")))
    return names


async def _resolve_user_ids(
    lookup_ids: Set[int],
    graph_client: Any,
    site_id: str,
) -> Dict[int, str]:
    """Resolve SharePoint User Information List IDs to display names.

    Uses the hidden ``User Information List`` available at every SharePoint site,
    which maps numeric IDs to user profiles.
    """
    # Check cache first
    cached = _user_display_cache.get(site_id, {})
    missing = lookup_ids - set(cached.keys())

    if not missing:
        return {uid: cached[uid] for uid in lookup_ids if uid in cached}

    # Fetch from SharePoint's User Information List via Graph API
    resolved: Dict[int, str] = dict(cached)

    for uid in missing:
        try:
            data = await graph_client.get(
                f"/sites/{site_id}/lists('User Information List')/items/{uid}?$select=id&$expand=fields($select=Title,EMail,Name,UserName)"
            )
            fields = data.get("fields", {})
            display_name = (
                fields.get("Title")
                or fields.get("UserName")
                or fields.get("Name")
                or ""
            )
            if display_name:
                resolved[uid] = display_name
                logger.debug("Resolved LookupId %d → '%s'", uid, display_name)
            else:
                resolved[uid] = f"User #{uid}"
        except Exception as e:
            logger.debug("Could not resolve user LookupId %d: %s", uid, e)
            # Try alternative: direct /users lookup won't work for SP IDs
            # Just mark as unresolved
            resolved[uid] = f"User #{uid}"

    # Update cache
    _user_display_cache[site_id] = resolved
    return {uid: resolved.get(uid, f"User #{uid}") for uid in lookup_ids}


def clear_cache():
    """Clear the user display name cache (useful for testing)."""
    _user_display_cache.clear()
