"""Caching layer for frequently accessed SharePoint data."""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List, Callable
from functools import wraps

logger = logging.getLogger(__name__)

# Simple in-memory cache with TTL
_cache: Dict[str, tuple[Any, float]] = {}
_cache_lock = asyncio.Lock()
DEFAULT_TTL = 300  # 5 minutes


def cache_with_ttl(ttl: int = DEFAULT_TTL, key_prefix: str = ""):
    """Decorator to cache function results with TTL.
    
    Args:
        ttl: Time to live in seconds
        key_prefix: Prefix for cache key
        
    Returns:
        Decorated function
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Build cache key from function name and arguments
            cache_key = f"{key_prefix}{func.__name__}:{str(args)}:{str(kwargs)}"
            
            async with _cache_lock:
                # Check cache
                if cache_key in _cache:
                    cached_value, expiry_time = _cache[cache_key]
                    if time.time() < expiry_time:
                        logger.debug(f"Cache hit for {cache_key}")
                        return cached_value
                    else:
                        del _cache[cache_key]
            
            # Cache miss - call function outside lock to avoid blocking
            logger.debug(f"Cache miss for {cache_key}")
            result = await func(*args, **kwargs)
            
            async with _cache_lock:
                _cache[cache_key] = (result, time.time() + ttl)
            
            return result
        
        return wrapper
    return decorator


def clear_cache(pattern: Optional[str] = None):
    """Clear cache entries.
    
    Args:
        pattern: Optional pattern to match cache keys. If None, clears all.
    """
    global _cache
    
    if pattern is None:
        _cache.clear()  # in-place clear so existing references stay valid
        logger.info("Cache cleared completely")
    else:
        keys_to_delete = [key for key in _cache.keys() if pattern in key]
        for key in keys_to_delete:
            del _cache[key]
        logger.info(f"Cleared {len(keys_to_delete)} cache entries matching '{pattern}'")


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics.
    
    Returns:
        Dictionary with cache statistics
    """
    total_entries = len(_cache)
    expired_entries = sum(1 for _, expiry in _cache.values() if time.time() >= expiry)
    
    return {
        "total_entries": total_entries,
        "expired_entries": expired_entries,
        "active_entries": total_entries - expired_entries
    }

