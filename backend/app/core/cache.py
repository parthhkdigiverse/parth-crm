# backend/app/core/cache.py
"""
Simple in-memory TTL cache to reduce repeated MongoDB round-trips.
Especially useful for quasi-static data like Users and Areas.
"""
import asyncio
import time
from typing import Any, Optional
from functools import wraps

_cache: dict[str, tuple[Any, float]] = {}

def _get(key: str) -> Optional[Any]:
    entry = _cache.get(key)
    if entry:
        value, expires_at = entry
        if time.monotonic() < expires_at:
            return value
        del _cache[key]
    return None

def _set(key: str, value: Any, ttl_seconds: int):
    _cache[key] = (value, time.monotonic() + ttl_seconds)

def invalidate(prefix: str = ""):
    """Invalidate all cache entries whose key starts with prefix."""
    to_delete = [k for k in _cache if k.startswith(prefix)]
    for k in to_delete:
        del _cache[k]

def invalidate_all():
    _cache.clear()

def cached(key: str, ttl_seconds: int = 120):
    """
    Decorator for async functions. Caches the result under `key` for `ttl_seconds`.
    Use for expensive, rarely-changing DB reads (e.g., all users, all areas).
    
    Usage:
        @cached("all_users", ttl_seconds=120)
        async def fetch_all_users():
            return await User.find_all().to_list()
    """
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            result = _get(key)
            if result is not None:
                return result
            result = await fn(*args, **kwargs)
            _set(key, result, ttl_seconds)
            return result
        return wrapper
    return decorator


async def get_or_set(key: str, coroutine_factory, ttl_seconds: int = 120):
    """
    Fetch from cache, or call coroutine_factory() to hydrate.
    
    Usage:
        users = await get_or_set("all_users", lambda: User.find_all().to_list(), ttl=120)
    """
    result = _get(key)
    if result is not None:
        return result
    result = await coroutine_factory()
    _set(key, result, ttl_seconds)
    return result
