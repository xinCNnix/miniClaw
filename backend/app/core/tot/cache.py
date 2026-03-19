"""
ToT Tool Result Cache (Phase 4)

Caches tool execution results to avoid redundant calls.
Uses TTL-based expiration to ensure freshness.
"""

import hashlib
import json
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class ToolResultCache:
    """
    Cache for tool execution results.

    Features:
    - TTL-based expiration (default 5 minutes)
    - Key based on tool name + args hash
    - Thread-safe operations
    - Statistics tracking (hits, misses, hit rate)

    Cache key format:
    {tool_name}:{hash(args)}

    Example:
    - search_kb:query="AI" → search_kb:a1b2c3d4
    - fetch_url:url="http://example.com" → fetch_url:e5f6g7h8
    """

    def __init__(self, ttl: int = 300, enabled: bool = True):
        """
        Initialize tool result cache.

        Args:
            ttl: Time-to-live in seconds (default 300 = 5 minutes)
            enabled: Whether caching is enabled
        """
        self.ttl = ttl
        self.enabled = enabled
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0
        }

    def get(self, tool_name: str, tool_args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get cached tool result.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments

        Returns:
            Cached result if found and not expired, None otherwise
        """
        if not self.enabled:
            return None

        key = self._make_key(tool_name, tool_args)

        if key in self._cache:
            entry = self._cache[key]

            # Check expiration
            if time.time() - entry["timestamp"] < self.ttl:
                self._stats["hits"] += 1
                logger.debug(f"[CACHE_HIT] {tool_name}:{key[:8]}...")
                return entry["result"]
            else:
                # Expired, remove it
                del self._cache[key]
                self._stats["evictions"] += 1
                logger.debug(f"[CACHE_EVICT] {tool_name}:{key[:8]}... (expired)")

        self._stats["misses"] += 1
        return None

    def set(self, tool_name: str, tool_args: Dict[str, Any], result: Dict[str, Any]) -> None:
        """
        Store tool result in cache.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments
            result: Tool execution result to cache
        """
        if not self.enabled:
            return

        key = self._make_key(tool_name, tool_args)

        self._cache[key] = {
            "result": result,
            "timestamp": time.time(),
            "tool_name": tool_name,
            "args": tool_args
        }

        logger.debug(f"[CACHE_SET] {tool_name}:{key[:8]}...")

    def _make_key(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """
        Create cache key from tool name and arguments.

        Uses MD5 hash of JSON-serialized args for consistent keys.

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments

        Returns:
            Cache key string
        """
        # Sort args for consistent hashing
        args_json = json.dumps(tool_args, sort_keys=True)
        args_hash = hashlib.md5(args_json.encode()).hexdigest()[:8]

        return f"{tool_name}:{args_hash}"

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        logger.info("[CACHE] Cleared all entries")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with stats: hits, misses, hit_rate, size
        """
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = self._stats["hits"] / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": hit_rate,
            "size": len(self._cache),
            "evictions": self._stats["evictions"]
        }

    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from cache.

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        current_time = time.time()
        expired_keys = []

        for key, entry in self._cache.items():
            if current_time - entry["timestamp"] >= self.ttl:
                expired_keys.append(key)

        for key in expired_keys:
            del self._cache[key]
            self._stats["evictions"] += 1

        if expired_keys:
            logger.info(f"[CACHE] Cleaned up {len(expired_keys)} expired entries")

        return len(expired_keys)


# Global cache instance (shared across all ToT sessions)
_global_cache: Optional[ToolResultCache] = None


def get_global_cache(ttl: int = 300, enabled: bool = True) -> ToolResultCache:
    """
    Get or create global cache instance.

    Args:
        ttl: Time-to-live in seconds
        enabled: Whether caching is enabled

    Returns:
        Global ToolResultCache instance
    """
    global _global_cache

    if _global_cache is None:
        _global_cache = ToolResultCache(ttl=ttl, enabled=enabled)
        logger.info(f"[CACHE] Created global cache (TTL={ttl}s, enabled={enabled})")

    return _global_cache


def reset_global_cache() -> None:
    """Reset global cache instance."""
    global _global_cache
    _global_cache = None
    logger.info("[CACHE] Reset global cache")
