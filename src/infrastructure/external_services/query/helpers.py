"""Module-level helper functions for the AI data query service."""

import logging

logger = logging.getLogger(__name__)


def parse_site_info(site_id: str) -> dict:
    """Parse site information from SharePoint SITE_ID.

    SITE_ID format: hostname,siteCollectionId,siteId
    Example: optimumpartnersjo.sharepoint.com,40da0f40-...,3d3f2838-...

    Returns a dict with keys: name, hostname, url.
    """
    if not site_id:
        return {"name": "Unknown", "hostname": "Unknown", "url": "Unknown"}

    try:
        parts = site_id.split(",")
        if len(parts) >= 1:
            hostname = parts[0]
            site_name = hostname.split(".")[0] if "." in hostname else hostname
            site_url = f"https://{hostname}"
            return {"name": site_name, "hostname": hostname, "url": site_url}
    except Exception as exc:
        logger.warning("Failed to parse SITE_ID: %s", exc)

    return {"name": "Unknown", "hostname": "Unknown", "url": "Unknown"}


def find_list_by_name(question: str, list_summaries: list) -> dict | None:
    """Deterministic pre-match: return the list whose name appears in *question*.

    Matching priority:
    1. Exact word-boundary match
    2. Substring match
    When multiple matches exist at the same priority, prefer the longest name.
    """
    question_lower = question.lower()
    exact_matches: list[dict] = []
    substring_matches: list[dict] = []

    for lst in list_summaries:
        name = lst.get("name", "")
        if not name:
            continue
        name_lower = name.lower()
        if name_lower not in question_lower:
            continue

        idx = question_lower.find(name_lower)
        before_ok = idx == 0 or not question_lower[idx - 1].isalnum()
        after_idx = idx + len(name_lower)
        after_ok = after_idx >= len(question_lower) or not question_lower[after_idx].isalnum()

        if before_ok and after_ok:
            exact_matches.append(lst)
        else:
            substring_matches.append(lst)

    for pool in (exact_matches, substring_matches):
        if len(pool) == 1:
            return pool[0]
        if len(pool) > 1:
            pool.sort(key=lambda x: len(x.get("name", "")), reverse=True)
            return pool[0]

    return None
