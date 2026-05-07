"""Audit trail service — records every resource operation performed by the AI assistant."""

from __future__ import annotations

import asyncio
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.infrastructure.logging import get_logger

logger = get_logger(__name__)


@dataclass
class AuditEntry:
    """Immutable record of an operation performed by the assistant."""

    operation: str          # e.g. "create_page", "delete_site", "provision_blueprint"
    resource_type: str      # "page" | "site" | "list" | "library" | "blueprint"
    resource_name: str
    session_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    result: str = "success"          # "success" | "failure"
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "operation": self.operation,
            "resource_type": self.resource_type,
            "resource_name": self.resource_name,
            "session_id": self.session_id,
            "timestamp": self.timestamp.isoformat(),
            "result": self.result,
            "details": self.details,
        }


class AuditService:
    """In-memory audit log with optional async persisting hook.

    Usage
    -----
    Call ``AuditService.record(...)`` from any handler after every write
    operation.  Entries accumulate in ``_log`` (capped at 10 000) and are also
    emitted to the application logger so they appear in container stdout / log
    aggregators.  The bounded deque prevents unbounded memory growth.
    """

    _log: deque = deque(maxlen=10_000)   # class-level bounded shared log
    _lock: threading.Lock = threading.Lock()

    @classmethod
    def record(
        cls,
        operation: str,
        resource_type: str,
        resource_name: str,
        session_id: str,
        result: str = "success",
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            operation=operation,
            resource_type=resource_type,
            resource_name=resource_name,
            session_id=session_id,
            result=result,
            details=details or {},
        )
        with cls._lock:
            cls._log.append(entry)
        logger.info("[AUDIT] %s", entry.to_dict())
        return entry

    @classmethod
    def get_log(
        cls,
        session_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Return recent audit entries, optionally filtered."""
        entries = cls._log
        if session_id:
            entries = [e for e in entries if e.session_id == session_id]
        if resource_type:
            entries = [e for e in entries if e.resource_type == resource_type]
        return [e.to_dict() for e in entries[-limit:]]

    @classmethod
    def clear(cls) -> None:
        """Clear the in-memory log (useful in tests)."""
        cls._log.clear()
