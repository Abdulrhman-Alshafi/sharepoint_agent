"""Structured telemetry logger for query pipeline observability.

Zero new dependencies — uses the standard logging module with JSON
serialisation so any existing log aggregator can ingest the output.

Usage (from answer_question finally block):
    from src.infrastructure.services.query_telemetry import log_query_trace
    log_query_trace(
        site_id=..., page_id=..., intent=...,
        resources_accessed=..., page_hit=...,
        fallback_used=..., latency_ms=...,
    )
"""

import json
import logging
from typing import List, Optional

_tlog = logging.getLogger("query.telemetry")


def log_query_trace(
    site_id:            str,
    page_id:            Optional[str],
    intent:             str,
    resources_accessed: List[str],
    page_hit:           bool,
    fallback_used:      bool,
    latency_ms:         float,
) -> None:
    """Emit one structured JSON log line per query request."""
    _tlog.info(json.dumps({
        "site_id":            site_id,
        "page_id":            page_id,
        "intent":             intent,
        "resources_accessed": resources_accessed,
        "page_hit":           page_hit,
        "fallback_used":      fallback_used,
        "latency_ms":         latency_ms,
    }))
