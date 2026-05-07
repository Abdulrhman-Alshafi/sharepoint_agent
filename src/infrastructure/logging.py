"""Centralized logging configuration with correlation ID support."""

import logging
import sys
from typing import Optional


class CorrelationFilter(logging.Filter):
    """Inject the current request correlation ID into every log record.

    This allows log entries to be traced back to the originating HTTP request,
    even across async task switches.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from src.infrastructure.correlation import get_correlation_id

        record.correlation_id = get_correlation_id() or "-"  # type: ignore[attr-defined]
        return True


def setup_logging(log_level: str = "INFO", environment: str = "production") -> None:
    """
    Configure application-wide logging.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        environment: Retained for call-site compatibility; always \"production\"
    """
    # Convert log level string to logging constant
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    
    # Configure root logger — include correlation_id in every line
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s [%(correlation_id)s] %(name)s %(levelname)s %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout)
        ],
        force=True  # Override any existing configuration
    )

    # Attach the correlation filter to the root handlers so all log records
    # get the correlation_id before being formatted.
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, CorrelationFilter) for f in handler.filters):
            handler.addFilter(CorrelationFilter())
    
    # Set specific log levels for noisy third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    
    # Log the configuration
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured: level={log_level.upper()}, environment={environment}")


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance for a module.
    
    Args:
        name: Logger name (typically __name__ from calling module)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)
