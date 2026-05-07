"""ConceptMemory — SQLite store for learned phrase→concept mappings.

Records how often a phrase has been mapped to a set of concepts so that
high-frequency mappings can graduate into the permanent custom ontology
(Phase 4).  Uses the same async aiosqlite pattern as WebPartIndexService.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

_DB_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "data", "document_index",
)
_DB_PATH = os.path.abspath(os.path.join(_DB_DIR, "concept_memory.db"))


def _init_database() -> None:
    """Create the SQLite DB and table synchronously (called once at import time)."""
    import sqlite3

    os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS concept_mappings (
                phrase          TEXT PRIMARY KEY,
                mapped_concepts TEXT NOT NULL,
                frequency       INTEGER NOT NULL DEFAULT 1,
                last_seen       REAL    NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


_init_database()


class ConceptMemory:
    """Async interface for concept_memory.db."""

    # ─────────────────────────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────────────────────────

    async def record(self, phrase: str, concepts: List[str]) -> None:
        """Upsert a phrase→concepts mapping and increment its frequency counter.

        Safe to call fire-and-forget (errors are logged, not raised).
        """
        if not phrase or not concepts:
            return
        now = time.time()
        concepts_json = json.dumps(concepts)
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO concept_mappings (phrase, mapped_concepts, frequency, last_seen)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(phrase) DO UPDATE SET
                        mapped_concepts = excluded.mapped_concepts,
                        frequency       = frequency + 1,
                        last_seen       = excluded.last_seen
                    """,
                    (phrase.lower(), concepts_json, now),
                )
                await db.commit()
        except Exception as exc:
            logger.warning("ConceptMemory.record failed: %s", exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Read
    # ─────────────────────────────────────────────────────────────────────────

    async def lookup(
        self,
        phrase: str,
        min_freq: int = 2,
    ) -> Optional[List[str]]:
        """Return learned concepts for *phrase* if it has been seen ≥ min_freq times.

        Returns None when no mapping exists or frequency is too low.
        """
        if not phrase:
            return None
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT mapped_concepts, frequency FROM concept_mappings WHERE phrase = ?",
                    (phrase.lower(),),
                ) as cursor:
                    row = await cursor.fetchone()
            if row and row[1] >= min_freq:
                return json.loads(row[0])
            return None
        except Exception as exc:
            logger.warning("ConceptMemory.lookup failed: %s", exc)
            return None

    async def get_top_mappings(self, limit: int = 50) -> List[dict]:
        """Return the most-used phrase→concept mappings (debug / admin use)."""
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT phrase, mapped_concepts, frequency, last_seen "
                    "FROM concept_mappings ORDER BY frequency DESC LIMIT ?",
                    (limit,),
                ) as cursor:
                    rows = await cursor.fetchall()
            return [
                {
                    "phrase": r[0],
                    "concepts": json.loads(r[1]),
                    "frequency": r[2],
                    "last_seen": r[3],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("ConceptMemory.get_top_mappings failed: %s", exc)
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Phase 4 helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def get_high_frequency_phrases(self, min_freq: int = 5) -> List[dict]:
        """Return phrases seen ≥ min_freq times — used by OntologyExpander."""
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT phrase, mapped_concepts, frequency FROM concept_mappings "
                    "WHERE frequency >= ? ORDER BY frequency DESC",
                    (min_freq,),
                ) as cursor:
                    rows = await cursor.fetchall()
            return [
                {"phrase": r[0], "concepts": json.loads(r[1]), "frequency": r[2]}
                for r in rows
            ]
        except Exception as exc:
            logger.warning("ConceptMemory.get_high_frequency_phrases failed: %s", exc)
            return []

    async def get_vocabulary_stats(self) -> dict:
        """Return summary stats — total phrases, top-10 by frequency."""
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT COUNT(*) FROM concept_mappings"
                ) as cursor:
                    total_row = await cursor.fetchone()
                total = total_row[0] if total_row else 0

                async with db.execute(
                    "SELECT phrase, frequency FROM concept_mappings "
                    "ORDER BY frequency DESC LIMIT 10"
                ) as cursor:
                    top_rows = await cursor.fetchall()

            return {
                "total_phrases": total,
                "top_phrases": [{"phrase": r[0], "frequency": r[1]} for r in top_rows],
            }
        except Exception as exc:
            logger.warning("ConceptMemory.get_vocabulary_stats failed: %s", exc)
            return {"total_phrases": 0, "top_phrases": []}
