"""SQLite-backed index for SharePoint page web part content.

Caches extracted plain-text content from page web parts to avoid repeated
Graph API calls on every query. Staleness is determined by a 1-hour TTL
combined with a SHA-256 checksum of the extracted text.

Mirrors the pattern established by DocumentIndexService.
"""

import aiosqlite
import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_TTL_SECONDS = 3600  # 1 hour


class WebPartIndexService:
    """Cache service for SharePoint page web part content.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str = "data/document_index/webparts.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    # ─────────────────────────────────────────────────────────────────────────
    # Schema initialisation (sync, runs once at startup)
    # ─────────────────────────────────────────────────────────────────────────

    def _init_database(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS page_webparts (
                page_id        TEXT PRIMARY KEY,
                site_id        TEXT NOT NULL,
                page_title     TEXT,
                page_url       TEXT,
                extracted_text TEXT,
                webpart_count  INTEGER DEFAULT 0,
                checksum       TEXT,
                last_indexed   REAL NOT NULL,
                embedding      BLOB    -- Phase 2: JSON float array, nullable
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_wp_site_id ON page_webparts(site_id)"
        )
        # Phase 2 migration: add embedding column to existing databases
        existing_cols = [r[1] for r in cursor.execute("PRAGMA table_info(page_webparts)").fetchall()]
        if "embedding" not in existing_cols:
            cursor.execute("ALTER TABLE page_webparts ADD COLUMN embedding BLOB")
        conn.commit()
        conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _checksum(text: str) -> str:
        return hashlib.sha256((text or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        return {
            "page_id": row[0],
            "site_id": row[1],
            "page_title": row[2],
            "page_url": row[3],
            "extracted_text": row[4],
            "webpart_count": row[5],
            "checksum": row[6],
            "last_indexed": row[7],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def index_page(
        self,
        page_id: str,
        site_id: str,
        page_title: str,
        page_url: str,
        extracted_text: str,
        webpart_count: int,
    ) -> bool:
        """Insert or update a page's extracted web part text.

        Args:
            page_id: SharePoint page ID.
            site_id: SharePoint site ID.
            page_title: Human-readable page title.
            page_url: Absolute URL of the page.
            extracted_text: Plain text extracted from all web parts.
            webpart_count: Number of web parts found on the page.

        Returns:
            True on success, False on error.
        """
        try:
            checksum = self._checksum(extracted_text)
            now = time.time()
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO page_webparts
                        (page_id, site_id, page_title, page_url,
                         extracted_text, webpart_count, checksum, last_indexed)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(page_id) DO UPDATE SET
                        site_id        = excluded.site_id,
                        page_title     = excluded.page_title,
                        page_url       = excluded.page_url,
                        extracted_text = excluded.extracted_text,
                        webpart_count  = excluded.webpart_count,
                        checksum       = excluded.checksum,
                        last_indexed   = excluded.last_indexed
                    """,
                    (
                        page_id, site_id, page_title, page_url,
                        extracted_text, webpart_count, checksum, now,
                    ),
                )
                await db.commit()
            return True
        except Exception as exc:
            logger.error("WebPartIndex.index_page failed for %s: %s", page_id, exc)
            return False

    async def get_indexed_page(self, page_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached data for a single page.

        Args:
            page_id: SharePoint page ID.

        Returns:
            Dict with page data or None if not found.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT page_id, site_id, page_title, page_url, "
                    "extracted_text, webpart_count, checksum, last_indexed "
                    "FROM page_webparts WHERE page_id = ?",
                    (page_id,),
                ) as cursor:
                    row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None
        except Exception as exc:
            logger.error("WebPartIndex.get_indexed_page failed: %s", exc)
            return None

    async def get_all_indexed_pages(self, site_id: str) -> List[Dict[str, Any]]:
        """Return all cached pages for a site.

        Args:
            site_id: SharePoint site ID.

        Returns:
            List of page dicts ordered by title.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT page_id, site_id, page_title, page_url, "
                    "extracted_text, webpart_count, checksum, last_indexed "
                    "FROM page_webparts WHERE site_id = ? ORDER BY page_title",
                    (site_id,),
                ) as cursor:
                    rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.error("WebPartIndex.get_all_indexed_pages failed: %s", exc)
            return []

    async def search_pages(
        self, query: str, site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """LIKE-search across cached page titles and extracted text.

        Args:
            query: Search term.
            site_id: Optional site filter.

        Returns:
            Matching page dicts.
        """
        try:
            pattern = f"%{query}%"
            async with aiosqlite.connect(self.db_path) as db:
                if site_id:
                    async with db.execute(
                        "SELECT page_id, site_id, page_title, page_url, "
                        "extracted_text, webpart_count, checksum, last_indexed "
                        "FROM page_webparts "
                        "WHERE site_id = ? AND (page_title LIKE ? OR extracted_text LIKE ?) "
                        "ORDER BY page_title",
                        (site_id, pattern, pattern),
                    ) as cursor:
                        rows = await cursor.fetchall()
                else:
                    async with db.execute(
                        "SELECT page_id, site_id, page_title, page_url, "
                        "extracted_text, webpart_count, checksum, last_indexed "
                        "FROM page_webparts "
                        "WHERE page_title LIKE ? OR extracted_text LIKE ? "
                        "ORDER BY page_title",
                        (pattern, pattern),
                    ) as cursor:
                        rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.error("WebPartIndex.search_pages failed: %s", exc)
            return []

    async def is_page_stale(
        self, page_id: str, current_checksum: Optional[str] = None
    ) -> bool:
        """Check whether the cached entry for a page needs refreshing.

        A page is considered stale when:
        * It is not in the cache, OR
        * Its ``last_indexed`` timestamp is older than ``_TTL_SECONDS``, OR
        * ``current_checksum`` is provided and differs from the stored one.

        Args:
            page_id: SharePoint page ID.
            current_checksum: Optional new checksum to compare against.

        Returns:
            True if the cache entry is absent or outdated.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT checksum, last_indexed, webpart_count FROM page_webparts WHERE page_id = ?",
                    (page_id,),
                ) as cursor:
                    row = await cursor.fetchone()
            if not row:
                return True
            stored_checksum, last_indexed, webpart_count = row[0], row[1], row[2]
            if time.time() - (last_indexed or 0) > _TTL_SECONDS:
                return True
            if current_checksum and current_checksum != stored_checksum:
                return True
            # Re-fetch if previously indexed with no content (e.g. due to API errors)
            if not webpart_count:
                return True
            return False
        except Exception as exc:
            logger.error("WebPartIndex.is_page_stale failed: %s", exc)
            return True  # treat as stale on error so we re-fetch

    async def delete_page(self, page_id: str) -> bool:
        """Remove a page's cached entry.

        Args:
            page_id: SharePoint page ID.

        Returns:
            True on success.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM page_webparts WHERE page_id = ?", (page_id,)
                )
                await db.commit()
            return True
        except Exception as exc:
            logger.error("WebPartIndex.delete_page failed: %s", exc)
            return False
