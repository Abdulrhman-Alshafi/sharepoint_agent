"""Context normalization layer.

Single canonical function replacing scattered fallback logic across
service.py, page_mixin.py, and smart_resource_discovery.py.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class NormalizedContext:
    site_id:      str
    site_url:     str
    page_id:      Optional[str]
    page_url:     Optional[str]
    page_title:   Optional[str]
    context_hash: str   # sha256(site_id + (page_id or ""))[:16]


def normalize_context(context) -> NormalizedContext:
    """Derive a canonical NormalizedContext from a RequestContext (or None)."""
    site_id  = context.site.id.strip() if context and context.site and context.site.id else ""
    site_url = context.site.url or "" if context and context.site else ""
    page_url = (context.page.url or "").rstrip("/") if context and context.page else None
    page_id  = (context.page.id or "").strip() if context and context.page else None
    if not page_id and page_url:
        page_id = _extract_page_id_from_url(page_url)
    page_title = context.page.title if context and context.page else None
    h = hashlib.sha256(f"{site_id}{page_id or ''}".encode()).hexdigest()[:16]
    return NormalizedContext(site_id, site_url, page_id or None, page_url, page_title, h)


def normalize_context_from_fields(
    context_site_id: Optional[str],
    page_id: Optional[str],
    page_url: Optional[str],
    page_title: Optional[str],
    site_url: str = "",
) -> NormalizedContext:
    """Build a NormalizedContext directly from individual fields (service.py callers)."""
    sid = (context_site_id or "").strip()
    pid = (page_id or "").strip() or None
    purl = (page_url or "").rstrip("/") or None
    if not pid and purl:
        pid = _extract_page_id_from_url(purl)
    h = hashlib.sha256(f"{sid}{pid or ''}".encode()).hexdigest()[:16]
    return NormalizedContext(sid, site_url, pid, purl, page_title, h)


def _extract_page_id_from_url(url: str) -> Optional[str]:
    """Last-resort: extract slug from .aspx URL if no GUID is available.

    Special cases:
    - Site root URL (no .aspx segment, or just a trailing slash) → returns "ROOT_HOME".
    - Home.aspx → also returns "ROOT_HOME".
    """
    path = url.rstrip("/").lower()
    if path.endswith("/home") or path.endswith("/home.aspx") or path.endswith("/sitepages/home.aspx"):
        return "ROOT_HOME"
    # No .aspx at all → site root URL
    if ".aspx" not in path:
        return "ROOT_HOME"
    m = re.search(r"/([^/]+)\.aspx", url, re.IGNORECASE)
    return m.group(1) if m else None
