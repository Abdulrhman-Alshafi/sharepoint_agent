"""SectionIndex — SQLite index for individual web-part sections.

Each row represents ONE web part extracted from a SharePoint page.
This gives finer-grained retrieval than the page-level WebPartIndexService:
the LLM context is built from sections, not entire pages.

Token-cost focus:
  * Semantic search loads all stored embeddings for the site in memory — no
    extra API calls for retrieval itself.
  * Embeddings are generated once per section and reused forever (TTL 1h +
    checksum, same policy as WebPartIndexService).
  * If EmbeddingService returns [] (no API key / failure), the service falls
    back silently to keyword LIKE search.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

import aiosqlite

from src.infrastructure.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)

_DB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "document_index")
)
_DB_PATH = os.path.join(_DB_DIR, "sections.db")
_TTL_SECONDS = 3600  # 1 hour


def _init_database() -> None:
    import sqlite3

    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sections (
                section_id    TEXT PRIMARY KEY,
                page_id       TEXT NOT NULL,
                page_title    TEXT,
                site_id       TEXT NOT NULL,
                section_title TEXT,
                webpart_type  TEXT,
                content_text  TEXT,
                embedding     TEXT,   -- JSON float array, NULL until embedded
                checksum      TEXT,
                last_indexed  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_section_page ON sections(page_id);
            CREATE INDEX IF NOT EXISTS idx_section_site ON sections(site_id);
        """)
        conn.commit()
    finally:
        conn.close()


_init_database()


class SectionIndexService:
    """Async interface for the section-level SQLite index."""

    def __init__(self) -> None:
        self._embedder = EmbeddingService()

    # ─────────────────────────────────────────────────────────────────────────
    # Write
    # ─────────────────────────────────────────────────────────────────────────

    async def index_section(
        self,
        section_id: str,
        page_id: str,
        page_title: str,
        site_id: str,
        section_title: str,
        webpart_type: str,
        content_text: str,
        checksum: str,
        embed: bool = True,
    ) -> None:
        """Upsert a section row.  Generates embedding unless *embed=False*."""
        embedding_json: Optional[str] = None
        if embed and content_text:
            emb = await self._embedder.embed_text(content_text[:2000])  # limit chars
            if emb:
                embedding_json = json.dumps(emb)

        now = time.time()
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                await db.execute(
                    """
                    INSERT INTO sections
                        (section_id, page_id, page_title, site_id, section_title,
                         webpart_type, content_text, embedding, checksum, last_indexed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(section_id) DO UPDATE SET
                        page_title    = excluded.page_title,
                        section_title = excluded.section_title,
                        webpart_type  = excluded.webpart_type,
                        content_text  = excluded.content_text,
                        embedding     = excluded.embedding,
                        checksum      = excluded.checksum,
                        last_indexed  = excluded.last_indexed
                    """,
                    (
                        section_id, page_id, page_title, site_id,
                        section_title, webpart_type,
                        content_text, embedding_json, checksum, now,
                    ),
                )
                await db.commit()
        except Exception as exc:
            logger.warning("SectionIndex.index_section failed for %s: %s", section_id, exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Read — semantic
    # ─────────────────────────────────────────────────────────────────────────

    async def search_sections_semantic(
        self,
        query_embedding: List[float],
        site_id: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return top-K sections ranked by cosine similarity to *query_embedding*.

        Falls back to [] when no embeddings are stored yet for this site.
        No extra API calls — all embeddings are loaded from SQLite.
        """
        if not query_embedding:
            return []
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT section_id, page_id, page_title, site_id, section_title, "
                    "webpart_type, content_text, embedding "
                    "FROM sections WHERE site_id = ? AND embedding IS NOT NULL",
                    (site_id,),
                ) as cursor:
                    rows = await cursor.fetchall()
        except Exception as exc:
            logger.warning("SectionIndex.search_sections_semantic failed: %s", exc)
            return []

        scored: List[tuple] = []
        for row in rows:
            try:
                emb = json.loads(row[7])
                score = EmbeddingService.cosine_similarity(query_embedding, emb)
                scored.append((score, row))
            except Exception:
                continue

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {
                "section_id": r[0],
                "page_id": r[1],
                "page_title": r[2],
                "site_id": r[3],
                "section_title": r[4],
                "webpart_type": r[5],
                "content_text": r[6],
                "score": s,
            }
            for s, r in scored[:top_k]
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Read — keyword (fallback)
    # ─────────────────────────────────────────────────────────────────────────

    async def search_sections_keyword(
        self,
        query: str,
        site_id: str,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """Keyword LIKE search — used as fallback when embeddings unavailable."""
        like = f"%{query.lower()}%"
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT section_id, page_id, page_title, site_id, section_title, "
                    "webpart_type, content_text "
                    "FROM sections "
                    "WHERE site_id = ? "
                    "AND (LOWER(content_text) LIKE ? OR LOWER(section_title) LIKE ?) "
                    "LIMIT ?",
                    (site_id, like, like, top_k),
                ) as cursor:
                    rows = await cursor.fetchall()
        except Exception as exc:
            logger.warning("SectionIndex.search_sections_keyword failed: %s", exc)
            return []
        return [
            {
                "section_id": r[0], "page_id": r[1], "page_title": r[2],
                "site_id": r[3], "section_title": r[4], "webpart_type": r[5],
                "content_text": r[6], "score": 0.0,
            }
            for r in rows
        ]

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def get_page_sections(self, page_id: str) -> List[Dict[str, Any]]:
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT section_id, page_title, section_title, webpart_type, "
                    "content_text, last_indexed FROM sections WHERE page_id = ?",
                    (page_id,),
                ) as cursor:
                    rows = await cursor.fetchall()
            return [
                {
                    "section_id": r[0], "page_title": r[1], "section_title": r[2],
                    "webpart_type": r[3], "content_text": r[4], "last_indexed": r[5],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.warning("SectionIndex.get_page_sections failed: %s", exc)
            return []

    async def is_section_stale(self, section_id: str, current_checksum: str) -> bool:
        """True if the section is missing, too old, or its checksum changed."""
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT checksum, last_indexed FROM sections WHERE section_id = ?",
                    (section_id,),
                ) as cursor:
                    row = await cursor.fetchone()
            if not row:
                return True
            stored_checksum, last_indexed = row
            if stored_checksum != current_checksum:
                return True
            age = time.time() - float(last_indexed)
            return age > _TTL_SECONDS
        except Exception:
            return True

    async def delete_page_sections(self, page_id: str) -> None:
        """Remove all sections for a given page (used when page is deleted/stale)."""
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                await db.execute("DELETE FROM sections WHERE page_id = ?", (page_id,))
                await db.commit()
        except Exception as exc:
            logger.warning("SectionIndex.delete_page_sections failed: %s", exc)
