"""
In-Process Caching Layer

Thread-safe TTL cache for reducing database load. Uses an LRU eviction
strategy with configurable TTL per cache region.

Regions:
  - merchant     : merchant profile data (TTL 5 min)
  - analytics    : analytics queries (TTL 2 min)
  - subscriptions: subscription data (TTL 3 min)
  - wallets      : wallet lists (TTL 5 min)
  - exchange     : exchange rates (TTL 60 s) — already handled by PriceCache
  - general      : catch-all (TTL 60 s)
"""

import threading
import time
import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)

# Default TTLs in seconds per region
REGION_TTL = {
    "merchant": 300,
    "analytics": 120,
    "subscriptions": 180,
    "wallets": 300,
    "payments": 60,
    "general": 60,
}

MAX_ENTRIES_PER_REGION = 1024


# Redis client (optional, for distributed caching)
_redis_client = None


def get_redis_client():
    """
    Get Redis client for distributed caching.
    Returns None if Redis is not available.
    """
    global _redis_client
    if _redis_client is None:
        try:
            import redis
            from app.core.config import settings
            
            # Try to connect to Redis if configured
            redis_url = getattr(settings, 'REDIS_URL', None)
            if redis_url:
                _redis_client = redis.from_url(redis_url, decode_responses=False)
                # Test connection
                _redis_client.ping()
                logger.info("Redis client initialized successfully")
            else:
                logger.info("Redis URL not configured, using memory cache only")
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            _redis_client = None
    return _redis_client


class _CacheRegion:
    """Thread-safe LRU cache region with TTL expiration."""

    def __init__(self, ttl: int, max_entries: int = MAX_ENTRIES_PER_REGION):
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._ttl = ttl
        self._max = max_entries
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                self.misses += 1
                return None
            value, expires_at = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                self.misses += 1
                return None
            # Move to end (most-recently used)
            self._store.move_to_end(key)
            self.hits += 1
            return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        expires_at = time.monotonic() + (ttl if ttl is not None else self._ttl)
        with self._lock:
            if key in self._store:
                del self._store[key]
            self._store[key] = (value, expires_at)
            # Evict oldest if over limit
            while len(self._store) > self._max:
                self._store.popitem(last=False)

    def delete(self, key: str):
        with self._lock:
            self._store.pop(key, None)

    def clear(self):
        with self._lock:
            self._store.clear()

    def delete_pattern(self, prefix: str):
        """Delete all keys starting with *prefix*."""
        with self._lock:
            keys = [k for k in self._store if k.startswith(prefix)]
            for k in keys:
                del self._store[k]

    @property
    def size(self) -> int:
        return len(self._store)


class Cache:
    """Application-wide cache backed by per-region LRU stores."""

    def __init__(self):
        self._regions: dict[str, _CacheRegion] = {}
        for name, ttl in REGION_TTL.items():
            self._regions[name] = _CacheRegion(ttl=ttl)

    def _region(self, region: str) -> _CacheRegion:
        if region not in self._regions:
            self._regions[region] = _CacheRegion(ttl=REGION_TTL.get(region, 60))
        return self._regions[region]

    # ---- public API ----

    def get(self, key: str, region: str = "general") -> Optional[Any]:
        return self._region(region).get(key)

    def set(self, key: str, value: Any, region: str = "general", ttl: Optional[int] = None):
        self._region(region).set(key, value, ttl)

    def delete(self, key: str, region: str = "general"):
        self._region(region).delete(key)

    def invalidate(self, region: str):
        """Clear an entire region."""
        self._region(region).clear()

    def invalidate_prefix(self, prefix: str, region: str = "general"):
        """Remove all keys with a given prefix inside a region."""
        self._region(region).delete_pattern(prefix)

    def invalidate_all(self):
        for r in self._regions.values():
            r.clear()

    def stats(self) -> dict:
        return {
            name: {"size": r.size, "hits": r.hits, "misses": r.misses}
            for name, r in self._regions.items()
        }


# Singleton instance — import this everywhere
cache = Cache()


def make_cache_key(*parts) -> str:
    """Build a deterministic cache key from arbitrary parts."""
    raw = ":".join(str(p) for p in parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]
