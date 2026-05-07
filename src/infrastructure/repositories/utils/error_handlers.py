"""Error handling utilities for SharePoint operations."""

import functools
import logging
from typing import Callable, Any
from src.domain.exceptions import SharePointProvisioningException

logger = logging.getLogger(__name__)


def handle_sharepoint_errors(operation_name: str = "SharePoint operation") -> Callable:
    """Decorator to handle SharePoint exceptions consistently.
    
    Args:
        operation_name: Name of the operation for error messages
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except SharePointProvisioningException:
                # Re-raise SharePoint exceptions as-is
                raise
            except Exception as e:
                # Wrap other exceptions
                logger.error(f"{operation_name} failed: {str(e)}", exc_info=True)
                raise SharePointProvisioningException(
                    f"Error during {operation_name}: {str(e)}"
                ) from e
        return wrapper
    return decorator
