"""Library name matching — pure Python, no FastAPI dependencies.

Migrated from ``src/presentation/api/services/library_matcher.py``.
The original consumer imports ``NOISE_WORDS`` and ``score_library_match`` from
that module; both are now sourced here and re-exported from the presentation
layer to keep backward compatibility.
"""

from __future__ import annotations

# Noise words that appear in upload messages but are not part of a library name
NOISE_WORDS: frozenset[str] = frozenset({
    "the", "a", "an", "to", "add", "upload", "move", "put", "into",
    "in", "document", "documents", "file", "files", "library", "folder",
    "please", "my", "our", "this", "these", "that", "those",
})


def score_library_match(message: str, library_name: str) -> int:
    """Score how well *library_name* matches *message*.

    Returns:
        Integer score: 0 = no match, 100 = exact full-name match.
    """
    msg_lower = message.lower()
    lib_lower = library_name.lower()
    lib_words = [w for w in lib_lower.split() if w not in NOISE_WORDS]
    signal_words = [
        w for w in msg_lower.split()
        if w.isalpha() and w not in NOISE_WORDS and len(w) > 1
    ]

    if lib_lower in msg_lower:
        return 100

    if lib_words and all(w in signal_words for w in lib_words):
        return 50 + len(lib_words)

    matches = sum(1 for w in lib_words if w in signal_words)
    if matches:
        return matches * 10

    return 0
