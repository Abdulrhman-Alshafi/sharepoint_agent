"""SQLite-backed cache for SharePoint list items.

Caches serialised list items to avoid a Graph API round-trip on every query.
Staleness is determined by a 15-minute TTL (lists change more frequently than
pages) combined with an optional item-count sanity check.

Mirrors the pattern established by DocumentIndexService and WebPartIndexService.
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

_TTL_SECONDS = 900  # 15 minutes


class ListItemIndexService:
    """Cache service for SharePoint list items.

    Args:
        db_path: Path to the SQLite database file.
    """

    def __init__(self, db_path: str = "data/document_index/list_items.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    # ─────────────────────────────────────────────────────────────────────────
    # Schema initialisation
    # ─────────────────────────────────────────────────────────────────────────

    def _init_database(self) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS list_items (
                list_id      TEXT PRIMARY KEY,
                site_id      TEXT NOT NULL,
                list_name    TEXT,
                items_json   TEXT,
                item_count   INTEGER DEFAULT 0,
                checksum     TEXT,
                last_indexed REAL NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_li_site_id ON list_items(site_id)"
        )
        conn.commit()
        conn.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _checksum(items: List[Dict[str, Any]]) -> str:
        serialized = json.dumps(items, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_dict(row) -> Dict[str, Any]:
        raw_json = row[3]
        try:
            items = json.loads(raw_json) if raw_json else []
        except (json.JSONDecodeError, TypeError):
            items = []
        return {
            "list_id": row[0],
            "site_id": row[1],
            "list_name": row[2],
            "items": items,
            "item_count": row[4],
            "checksum": row[5],
            "last_indexed": row[6],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def index_list(
        self,
        list_id: str,
        site_id: str,
        list_name: str,
        items: List[Dict[str, Any]],
    ) -> bool:
        """Insert or update a list's cached items.

        Args:
            list_id: SharePoint list ID.
            site_id: SharePoint site ID.
            list_name: Human-readable list name.
            items: List of item field dicts (already unwrapped from ``fields``).

        Returns:
            True on success, False on error.
        """
        try:
            items_json = json.dumps(items, ensure_ascii=False)
            checksum = self._checksum(items)
            now = time.time()
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO list_items
                        (list_id, site_id, list_name, items_json,
                         item_count, checksum, last_indexed)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(list_id) DO UPDATE SET
                        site_id      = excluded.site_id,
                        list_name    = excluded.list_name,
                        items_json   = excluded.items_json,
                        item_count   = excluded.item_count,
                        checksum     = excluded.checksum,
                        last_indexed = excluded.last_indexed
                    """,
                    (list_id, site_id, list_name, items_json, len(items), checksum, now),
                )
                await db.commit()
            return True
        except Exception as exc:
            logger.error("ListItemIndex.index_list failed for %s: %s", list_id, exc)
            return False

    async def get_indexed_list(self, list_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached items for a list.

        Args:
            list_id: SharePoint list ID.

        Returns:
            Dict with ``items`` key (list of field dicts) or None if not cached.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT list_id, site_id, list_name, items_json, "
                    "item_count, checksum, last_indexed "
                    "FROM list_items WHERE list_id = ?",
                    (list_id,),
                ) as cursor:
                    row = await cursor.fetchone()
            return self._row_to_dict(row) if row else None
        except Exception as exc:
            logger.error("ListItemIndex.get_indexed_list failed: %s", exc)
            return None

    async def search_items(
        self, query: str, list_id: Optional[str] = None, site_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """LIKE-search across cached list names and serialised items JSON.

        Args:
            query: Search term.
            list_id: Optional filter to a single list.
            site_id: Optional filter to a single site.

        Returns:
            Matching list cache entries (including their ``items`` list).
        """
        try:
            pattern = f"%{query}%"
            async with aiosqlite.connect(self.db_path) as db:
                if list_id:
                    sql = (
                        "SELECT list_id, site_id, list_name, items_json, "
                        "item_count, checksum, last_indexed "
                        "FROM list_items WHERE list_id = ? "
                        "AND (list_name LIKE ? OR items_json LIKE ?)"
                    )
                    params = (list_id, pattern, pattern)
                elif site_id:
                    sql = (
                        "SELECT list_id, site_id, list_name, items_json, "
                        "item_count, checksum, last_indexed "
                        "FROM list_items WHERE site_id = ? "
                        "AND (list_name LIKE ? OR items_json LIKE ?)"
                    )
                    params = (site_id, pattern, pattern)
                else:
                    sql = (
                        "SELECT list_id, site_id, list_name, items_json, "
                        "item_count, checksum, last_indexed "
                        "FROM list_items WHERE list_name LIKE ? OR items_json LIKE ?"
                    )
                    params = (pattern, pattern)
                async with db.execute(sql, params) as cursor:
                    rows = await cursor.fetchall()
            return [self._row_to_dict(r) for r in rows]
        except Exception as exc:
            logger.error("ListItemIndex.search_items failed: %s", exc)
            return []

    async def is_list_stale(
        self, list_id: str, current_item_count: Optional[int] = None
    ) -> bool:
        """Check whether the cached entry for a list needs refreshing.

        A list is stale when:
        * It is not in the cache, OR
        * Its ``last_indexed`` is older than ``_TTL_SECONDS``, OR
        * ``current_item_count`` is provided and differs from stored count.

        Args:
            list_id: SharePoint list ID.
            current_item_count: Optional live item count to compare.

        Returns:
            True if the cache entry is absent or outdated.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                async with db.execute(
                    "SELECT item_count, last_indexed FROM list_items WHERE list_id = ?",
                    (list_id,),
                ) as cursor:
                    row = await cursor.fetchone()
            if not row:
                return True
            stored_count, last_indexed = row[0], row[1]
            if time.time() - (last_indexed or 0) > _TTL_SECONDS:
                return True
            if current_item_count is not None and current_item_count != stored_count:
                return True
            return False
        except Exception as exc:
            logger.error("ListItemIndex.is_list_stale failed: %s", exc)
            return True

    async def delete_list(self, list_id: str) -> bool:
        """Remove a list's cached entry.

        Args:
            list_id: SharePoint list ID.

        Returns:
            True on success.
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM list_items WHERE list_id = ?", (list_id,)
                )
                await db.commit()
            return True
        except Exception as exc:
            logger.error("ListItemIndex.delete_list failed: %s", exc)
            return False
