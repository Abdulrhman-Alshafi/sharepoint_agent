"""OntologyExpander — promotes frequently-seen phrases to the custom ontology.

Token-cost focus:
  * No AI calls — reads from ConceptMemory SQLite, promotes to a custom
    ontology SQLite, and calls ConceptMapper.load_custom_ontology() in-process.
  * After expansion, ConceptMapper handles new phrases without any API calls.
  * Should be called once at startup (FastAPI lifespan) and periodically
    (e.g., every 6 hours via asyncio.Task), but NOT on every request.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

_DB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "document_index")
)
_CUSTOM_ONTOLOGY_DB = os.path.join(_DB_DIR, "custom_ontology.db")

# A phrase must appear at least this many times before promotion
_PROMOTION_THRESHOLD = 5


def _init_custom_ontology_db() -> None:
    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_CUSTOM_ONTOLOGY_DB)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS custom_ontology (
                phrase     TEXT PRIMARY KEY,
                concepts   TEXT NOT NULL,  -- JSON list
                promoted_at REAL NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


_init_custom_ontology_db()


class OntologyExpander:
    """Reads high-frequency phrases from ConceptMemory and promotes them.

    Usage::

        # At startup
        expander = OntologyExpander()
        await expander.expand()

        # Periodic refresh (call from an asyncio.Task)
        await expander.expand()
    """

    async def expand(self) -> int:
        """Load high-frequency phrases, promote them, reload ConceptMapper.

        Returns the number of new phrases promoted this run.
        """
        from src.infrastructure.services.concept_memory import ConceptMemory
        from src.infrastructure.services.concept_mapper import ConceptMapper

        # Load phrases that have been seen >= threshold times
        memory = ConceptMemory()
        high_freq: List[dict] = await memory.get_high_frequency_phrases(
            min_freq=_PROMOTION_THRESHOLD
        )
        if not high_freq:
            logger.debug("OntologyExpander: no high-frequency phrases to promote")
            return 0

        # Build dict of {phrase: concepts_list}
        new_entries: Dict[str, Tuple[List[str], None]] = {}
        for item in high_freq:
            phrase = item.get("phrase", "").strip().lower()
            concepts = item.get("mapped_concepts", [])
            if phrase and concepts:
                new_entries[phrase] = (concepts, None)  # no resource_hint inferred

        if not new_entries:
            return 0

        # Persist to custom_ontology.db
        promoted_count = self._persist(new_entries)

        # Load all custom ontology into ConceptMapper (in-process hot reload)
        all_custom = self._load_all_custom()
        ConceptMapper.load_custom_ontology(all_custom)

        logger.info(
            "OntologyExpander: promoted %d new phrases, total custom entries=%d",
            promoted_count,
            len(all_custom),
        )
        return promoted_count

    def _persist(self, entries: Dict[str, Tuple[List[str], None]]) -> int:
        """Write new entries to custom_ontology.db.  Returns count of inserted rows."""
        import json
        now = time.time()
        new_count = 0
        conn = sqlite3.connect(_CUSTOM_ONTOLOGY_DB)
        try:
            for phrase, (concepts, _hint) in entries.items():
                cursor = conn.execute(
                    "SELECT phrase FROM custom_ontology WHERE phrase = ?", (phrase,)
                )
                if cursor.fetchone() is None:
                    conn.execute(
                        "INSERT INTO custom_ontology (phrase, concepts, promoted_at) VALUES (?, ?, ?)",
                        (phrase, json.dumps(concepts), now),
                    )
                    new_count += 1
            conn.commit()
        finally:
            conn.close()
        return new_count

    def _load_all_custom(self) -> Dict[str, List[str]]:
        """Load all rows from custom_ontology.db as {phrase: concepts_list}."""
        import json
        conn = sqlite3.connect(_CUSTOM_ONTOLOGY_DB)
        try:
            rows = conn.execute(
                "SELECT phrase, concepts FROM custom_ontology"
            ).fetchall()
        finally:
            conn.close()
        return {row[0]: json.loads(row[1]) for row in rows}

    def get_stats(self) -> dict:
        """Return basic stats about the custom ontology."""
        conn = sqlite3.connect(_CUSTOM_ONTOLOGY_DB)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM custom_ontology"
            ).fetchone()[0]
            recent = conn.execute(
                "SELECT phrase, promoted_at FROM custom_ontology "
                "ORDER BY promoted_at DESC LIMIT 5"
            ).fetchall()
        finally:
            conn.close()
        return {
            "total_custom_entries": count,
            "recent_promotions": [{"phrase": r[0], "promoted_at": r[1]} for r in recent],
        }
