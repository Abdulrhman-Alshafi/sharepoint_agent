"""Resilience utilities for query-layer service calls.

Provides an async retry helper for transient Graph API and network errors.
Uses the same retryable exception set as the main resilience.py decorator but
exposes a plain async function form so it can be used inside methods that
cannot use decorators (e.g. per-item loops).
"""

import asyncio
import logging
from typing import Any, Callable, Awaitable

from src.domain.exceptions import (
    ExternalServiceUnavailableError,
    ExternalTimeoutError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_RETRYABLE = (RateLimitError, ExternalServiceUnavailableError, ExternalTimeoutError)


async def with_retry(
    coro_fn: Callable[[], Awaitable[Any]],
    max_attempts: int = 2,
    delay: float = 1.0,
    label: str = "",
) -> Any:
    """Retry a coroutine on transient failures with linear backoff.

    Args:
        coro_fn: Zero-argument callable that returns a coroutine.
        max_attempts: Maximum number of attempts (default 2).
        delay: Seconds to wait between attempts (doubles on each retry).
        label: Descriptive label used in log messages.

    Returns:
        The return value of the coroutine on success.

    Raises:
        The last exception if all attempts are exhausted.
        Non-retryable exceptions (4xx, auth errors) are re-raised immediately.
    """
    last_exc: Exception | None = None
    wait = delay
    for attempt in range(1, max_attempts + 1):
        try:
            return await coro_fn()
        except _RETRYABLE as exc:
            last_exc = exc
            if attempt == max_attempts:
                logger.error(
                    "[with_retry] %s — all %d attempts exhausted: %s",
                    label or "operation",
                    max_attempts,
                    exc,
                )
                raise
            logger.warning(
                "[with_retry] %s — attempt %d/%d failed (%s), retrying in %.1fs",
                label or "operation",
                attempt,
                max_attempts,
                type(exc).__name__,
                wait,
            )
            await asyncio.sleep(wait)
            wait *= 2  # double backoff
        except Exception:
            # Non-retryable — propagate immediately
            raise
    raise last_exc  # should never reach here
