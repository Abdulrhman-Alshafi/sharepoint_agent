"""EmbeddingService — wraps Gemini text-embedding-004 for semantic retrieval.

Token-cost focus:
  * Embeddings are cached by SHA-256 of the input text in SQLite.
  * A cache hit costs 0 API tokens.
  * Batch API calls (up to 20 texts per call) reduce per-text overhead.
  * The cache is shared across all services (section_index, webpart_index, etc.).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import List, Optional

import aiosqlite

logger = logging.getLogger(__name__)

_DB_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "document_index")
)
_DB_PATH = os.path.join(_DB_DIR, "embedding_cache.db")
_BATCH_SIZE = 20  # Gemini embed batch limit


def _init_database() -> None:
    import sqlite3

    os.makedirs(_DB_DIR, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS embedding_cache (
                text_hash  TEXT PRIMARY KEY,
                embedding  TEXT NOT NULL,  -- JSON float array
                model      TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


_init_database()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingService:
    """Async embedding service backed by Gemini text-embedding-004.

    Falls back gracefully when no API key is configured — returns empty
    vectors so the rest of the pipeline degrades to keyword-only scoring.
    """

    MODEL = "models/text-embedding-004"

    def __init__(self) -> None:
        self._client = None  # lazy-loaded
        self._model_available: Optional[bool] = None

    def _get_client(self):
        """Lazy-load the Gemini client using the already-configured API key."""
        if self._client is not None:
            return self._client
        try:
            import google.generativeai as genai  # type: ignore
            from src.infrastructure.config import settings
            if not settings.GEMINI_API_KEY:
                logger.warning("EmbeddingService: GEMINI_API_KEY not set, embeddings disabled")
                self._model_available = False
                return None
            genai.configure(api_key=settings.GEMINI_API_KEY)
            self._client = genai
            self._model_available = True
            return self._client
        except Exception as exc:
            logger.warning("EmbeddingService: could not load Gemini client: %s", exc)
            self._model_available = False
            return None

    # ─────────────────────────────────────────────────────────────────────────
    # Cache helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def _cache_get(self, text_hash: str) -> Optional[List[float]]:
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                async with db.execute(
                    "SELECT embedding FROM embedding_cache WHERE text_hash = ?",
                    (text_hash,),
                ) as cursor:
                    row = await cursor.fetchone()
            if row:
                return json.loads(row[0])
            return None
        except Exception:
            return None

    async def _cache_set(self, text_hash: str, embedding: List[float]) -> None:
        try:
            async with aiosqlite.connect(_DB_PATH) as db:
                await db.execute(
                    """
                    INSERT OR REPLACE INTO embedding_cache
                        (text_hash, embedding, model, created_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (text_hash, json.dumps(embedding), self.MODEL, time.time()),
                )
                await db.commit()
        except Exception as exc:
            logger.debug("EmbeddingService._cache_set failed: %s", exc)

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    async def embed_text(self, text: str) -> List[float]:
        """Embed a single text string.  Returns [] on failure (degrades gracefully)."""
        if not text or not text.strip():
            return []
        h = _sha256(text)
        cached = await self._cache_get(h)
        if cached is not None:
            return cached

        client = self._get_client()
        if client is None:
            return []

        try:
            result = client.embed_content(model=self.MODEL, content=text)
            embedding = result["embedding"]
            await self._cache_set(h, embedding)
            return embedding
        except Exception as exc:
            logger.warning("EmbeddingService.embed_text failed: %s", exc)
            return []

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of texts, using cache and batching to minimise API calls."""
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        # Check cache first
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = []
                continue
            h = _sha256(text)
            cached = await self._cache_get(h)
            if cached is not None:
                results[i] = cached
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            client = self._get_client()
            if client is not None:
                # Process in batches
                for batch_start in range(0, len(uncached_texts), _BATCH_SIZE):
                    batch = uncached_texts[batch_start: batch_start + _BATCH_SIZE]
                    batch_idxs = uncached_indices[batch_start: batch_start + _BATCH_SIZE]
                    try:
                        batch_result = client.embed_content(model=self.MODEL, content=batch)
                        embeddings = batch_result.get("embedding", [])
                        # Gemini returns list-of-list for batch input
                        if embeddings and isinstance(embeddings[0], (int, float)):
                            embeddings = [embeddings]  # single text returned as flat list
                        for j, emb in enumerate(embeddings):
                            idx = batch_idxs[j]
                            results[idx] = emb
                            await self._cache_set(_sha256(uncached_texts[batch_start + j]), emb)
                    except Exception as exc:
                        logger.warning("EmbeddingService.embed_batch failed for batch: %s", exc)
                        for idx in batch_idxs:
                            results[idx] = []
            else:
                for idx in uncached_indices:
                    results[idx] = []

        return [r if r is not None else [] for r in results]

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Cosine similarity between two vectors.  Returns 0.0 on failure."""
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)
