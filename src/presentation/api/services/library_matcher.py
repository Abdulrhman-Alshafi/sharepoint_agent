"""Library name matching and scoring service.

Pure business logic for matching user messages to SharePoint document
libraries. Used by UploadService and file handlers.

No FastAPI dependencies.
"""

import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Re-exported from detection package for backward compatibility
from src.detection.matching.library_matcher import NOISE_WORDS, score_library_match


def find_best_library(
    message: str,
    libraries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find the best matching library from a user message.

    Args:
        message: The user's message text.
        libraries: List of library dicts with ``displayName`` or ``name`` keys.

    Returns:
        The best matching library dict, or ``None`` if ambiguous or no match.
    """
    if not message or not message.strip():
        return None

    scored: List[tuple] = []
    for lib in libraries:
        lib_name = (lib.get("displayName") or lib.get("name", "")).strip()
        if not lib_name:
            continue
        s = score_library_match(message, lib_name)
        if s > 0:
            scored.append((s, lib))

    if not scored:
        return None

    # Sort by score descending; if top score is shared by >1 lib, return None (ambiguous)
    scored.sort(key=lambda x: x[0], reverse=True)
    if len(scored) >= 2 and scored[0][0] == scored[1][0]:
        return None  # ambiguous
    return scored[0][1]


def extract_named_library(message: str) -> Optional[str]:
    """Return the word(s) after 'to the/a' or 'to' that look like a library name.

    Used for error messages when the named library doesn't match.
    """
    m = re.search(
        r'\b(?:to|into|in)\s+(?:the\s+|a\s+)?([A-Za-z0-9 _-]+?)\s*'
        r'(?:library|folder|document library)?\s*$',
        message, re.IGNORECASE,
    )
    if m:
        candidate = m.group(1).strip()
        if candidate.lower() not in NOISE_WORDS:
            return candidate
    return None


def match_library_from_message(
    message: str,
    libraries: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Match a library from a follow-up message (pending upload resolution).

    Uses exact and partial name matching.
    """
    ml = message.lower()
    exact, partial = [], []
    for lib in libraries:
        name = (lib.get("displayName") or lib.get("name", "")).lower()
        if not name:
            continue
        if name in ml:
            exact.append(lib)
        elif any(w in ml for w in name.split() if len(w) > 2):
            partial.append(lib)
    if len(exact) == 1:
        return exact[0]
    if not exact and len(partial) == 1:
        return partial[0]
    return None
