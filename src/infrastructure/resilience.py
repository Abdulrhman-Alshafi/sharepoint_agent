"""Lightweight circuit breaker and async retry utilities.

These are designed for wrapping calls to external services (Graph API, AI
providers, SharePoint REST) to prevent cascading failures and to retry
transient errors automatically.
"""

import asyncio
import functools
import logging
import time
import threading
from enum import Enum
from typing import Any, Callable, Optional, Set, Tuple, Type

from src.domain.exceptions import (
    CircuitBreakerOpenError,
    ExternalServiceUnavailableError,
    ExternalTimeoutError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


# ── Circuit Breaker ───────────────────────────────────────────────────────────


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation — requests pass through
    OPEN = "open"            # Too many failures — requests are blocked
    HALF_OPEN = "half_open"  # Recovery probe — one request allowed through


class CircuitBreaker:
    """Thread-safe circuit breaker (closed → open → half-open → closed).

    Usage::

        graph_cb = CircuitBreaker("Graph API", failure_threshold=5, recovery_timeout=30)

        async def call_graph():
            graph_cb.check()  # raises CircuitBreakerOpenError if open
            try:
                result = await do_graph_call()
                graph_cb.record_success()
                return result
            except Exception as e:
                graph_cb.record_failure()
                raise

    Or use the ``@with_circuit_breaker`` decorator for convenience.
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 30,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Auto-transition to half-open after recovery timeout
                if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        "Circuit breaker [%s] → HALF_OPEN (recovery probe)",
                        self.service_name,
                    )
            return self._state

    def check(self) -> None:
        """Raise :class:`CircuitBreakerOpenError` if the circuit is open."""
        state = self.state  # triggers auto-transition check
        if state == CircuitState.OPEN:
            raise CircuitBreakerOpenError(
                service=self.service_name,
                recovery_seconds=self.recovery_timeout,
            )

    def record_success(self) -> None:
        """Record a successful call — resets the breaker to CLOSED."""
        with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.CLOSED):
                self._failure_count = 0
                if self._state != CircuitState.CLOSED:
                    logger.info(
                        "Circuit breaker [%s] → CLOSED (recovered)",
                        self.service_name,
                    )
                self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed call — may trip the breaker to OPEN."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                # Half-open probe failed → back to OPEN
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker [%s] → OPEN (half-open probe failed)",
                    self.service_name,
                )
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker [%s] → OPEN after %d consecutive failures",
                    self.service_name,
                    self._failure_count,
                )

    def reset(self) -> None:
        """Manually reset the circuit breaker (e.g. after config change)."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0


# ── Singleton breakers for major external services ────────────────────────────

graph_breaker = CircuitBreaker("Graph API", failure_threshold=10, recovery_timeout=15)
ai_breaker = CircuitBreaker("AI Provider", failure_threshold=3, recovery_timeout=60)


# ── Retry decorator ──────────────────────────────────────────────────────────


def with_retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_max: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (
        RateLimitError,
        ExternalServiceUnavailableError,
        ExternalTimeoutError,
    ),
    service_name: str = "external service",
) -> Callable:
    """Async decorator for retrying transient failures with exponential backoff.

    Usage::

        @with_retry(max_attempts=3, service_name="Graph API")
        async def get_sites():
            ...

    Args:
        max_attempts: Total number of attempts (including the first).
        backoff_base: Base delay in seconds for exponential backoff.
        backoff_max: Maximum delay cap in seconds.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        service_name: Used in log messages.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as exc:
                    last_exc = exc
                    if attempt == max_attempts:
                        logger.error(
                            "[%s] All %d attempts exhausted: %s",
                            service_name,
                            max_attempts,
                            exc,
                        )
                        raise
                    # Exponential backoff with jitter
                    delay = min(backoff_base * (2 ** (attempt - 1)), backoff_max)
                    # If we got a retry_after hint, use it
                    if hasattr(exc, "retry_after") and exc.retry_after:
                        delay = max(delay, exc.retry_after)
                    logger.warning(
                        "[%s] Attempt %d/%d failed (%s), retrying in %.1fs…",
                        service_name,
                        attempt,
                        max_attempts,
                        exc.__class__.__name__,
                        delay,
                    )
                    await asyncio.sleep(delay)
            # Should not reach here, but just in case
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
