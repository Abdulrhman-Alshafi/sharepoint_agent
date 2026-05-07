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


class CachedSharePointRepository:
    """Wrapper to add caching to SharePoint repository methods."""
    
    def __init__(self, repository):
        """Initialize with a SharePoint repository instance.
        
        Args:
            repository: SharePoint repository to wrap with caching
        """
        self.repository = repository
    
    @cache_with_ttl(ttl=300, key_prefix="lists:")
    async def get_all_lists(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all lists with caching."""
        return await self.repository.get_all_lists(site_id=site_id)
    
    @cache_with_ttl(ttl=300, key_prefix="libraries:")
    async def get_all_document_libraries(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all document libraries with caching."""
        return await self.repository.get_all_document_libraries(site_id=site_id)
    
    @cache_with_ttl(ttl=300, key_prefix="pages:")
    async def get_all_pages(self, site_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all pages with caching."""
        return await self.repository.get_all_pages(site_id=site_id)
    
    @cache_with_ttl(ttl=300, key_prefix="site:")
    async def get_site(self, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Get site info with caching."""
        return await self.repository.get_site(site_id=site_id)
    
    @cache_with_ttl(ttl=600, key_prefix="sites:")
    async def get_all_sites(self) -> List[Dict[str, Any]]:
        """Get all sites with caching (10 min TTL)."""
        return await self.repository.get_all_sites()
    
    @cache_with_ttl(ttl=300, key_prefix="schema:")
    async def get_list_schema(self, list_id: str, site_id: Optional[str] = None) -> Dict[str, Any]:
        """Get list schema with caching."""
        return await self.repository.get_list_schema(list_id, site_id=site_id)
    
    # Pass-through methods that should NOT be cached (write operations)
    
    async def create_list(self, *args, **kwargs):
        """Create list - clears list cache."""
        result = await self.repository.create_list(*args, **kwargs)
        clear_cache("lists:")
        return result
    
    async def delete_list(self, *args, **kwargs):
        """Delete list - clears list cache."""
        result = await self.repository.delete_list(*args, **kwargs)
        clear_cache("lists:")
        return result
    
    async def create_page(self, *args, **kwargs):
        """Create page - clears page cache."""
        result = await self.repository.create_page(*args, **kwargs)
        clear_cache("pages:")
        return result
    
    async def delete_page(self, *args, **kwargs):
        """Delete page - clears page cache."""
        result = await self.repository.delete_page(*args, **kwargs)
        clear_cache("pages:")
        return result
    
    # Delegate all other methods to underlying repository
    def __getattr__(self, name):
        """Delegate unknown attributes to underlying repository."""
        return getattr(self.repository, name)
