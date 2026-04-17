"""
统一工具 & Skill 输出缓存

独立于 ToT/PERV 的通用缓存机制，支持:
- TTL 过期淘汰
- max_size 最旧条目淘汰
- per-key asyncio.Lock 防缓存击穿
- 工具黑名单排除有副作用的工具
- 分离的 tool/skill 统计
"""

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# 有副作用的工具不缓存
NON_CACHEABLE_TOOLS = frozenset({"terminal", "python_repl", "write_file"})


@dataclass
class _CacheEntry:
    result: Any
    timestamp: float
    entry_type: str  # "tool" or "skill"
    key_hint: str    # 截断的 key 前缀，用于调试日志


@dataclass
class _CacheStats:
    tool_hits: int = 0
    tool_misses: int = 0
    skill_hits: int = 0
    skill_misses: int = 0
    evictions_ttl: int = 0
    evictions_size: int = 0


class ExecutionCache:
    """统一工具 & Skill 输出缓存，独立于 ToT/PERV。

    并发安全:
    - asyncio.Lock 保护内部 dict 和 stats 的读写
    - per-key asyncio.Lock 防止缓存击穿：同一 key 只有一个协程执行，其余等待
    """

    def __init__(
        self,
        enabled: bool = True,
        ttl: int = 300,
        max_size: int = 256,
    ) -> None:
        self.enabled = enabled
        self.ttl = ttl
        self.max_size = max_size

        self._cache: Dict[str, _CacheEntry] = {}
        self._stats = _CacheStats()
        self._lock = asyncio.Lock()
        self._key_locks: Dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Key 生成
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(namespace: str, name: str, args: dict) -> str:
        """生成缓存 key: {namespace}:{name}:{md5(args)[:12]}"""
        try:
            args_json = json.dumps(args, sort_keys=True, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            args_json = str(sorted(args.items()))
        args_hash = hashlib.md5(args_json.encode()).hexdigest()[:12]
        return f"{namespace}:{name}:{args_hash}"

    # ------------------------------------------------------------------
    # Per-key lock (缓存击穿保护)
    # ------------------------------------------------------------------

    def _get_key_lock(self, key: str) -> asyncio.Lock:
        """获取 per-key lock，不存在则创建。"""
        if key not in self._key_locks:
            self._key_locks[key] = asyncio.Lock()
        return self._key_locks[key]

    def _cleanup_key_lock(self, key: str) -> None:
        """key lock 不再需要时清理，防止内存泄漏。"""
        lock = self._key_locks.get(key)
        if lock and not lock.locked():
            del self._key_locks[key]

    # ------------------------------------------------------------------
    # 核心读写
    # ------------------------------------------------------------------

    async def _aget(self, key: str) -> Tuple[Optional[Any], bool]:
        """异步读取缓存。返回 (result_or_None, was_hit)。"""
        if not self.enabled:
            return None, False

        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None, False

            # 检查 TTL
            if time.time() - entry.timestamp >= self.ttl:
                del self._cache[key]
                self._stats.evictions_ttl += 1
                return None, False

            return entry.result, True

    async def _aset(self, key: str, result: Any, entry_type: str) -> None:
        """异步写入缓存。"""
        if not self.enabled:
            return

        async with self._lock:
            # 超过 max_size 时淘汰最旧的条目
            if len(self._cache) >= self.max_size and key not in self._cache:
                oldest_key = min(self._cache, key=lambda k: self._cache[k].timestamp)
                del self._cache[oldest_key]
                self._stats.evictions_size += 1
                logger.debug(f"[ExecutionCache] evicted oldest entry: {oldest_key[:20]}...")

            self._cache[key] = _CacheEntry(
                result=result,
                timestamp=time.time(),
                entry_type=entry_type,
                key_hint=key[:20],
            )

    # ------------------------------------------------------------------
    # Tool 缓存
    # ------------------------------------------------------------------

    async def aget_tool(self, name: str, args: dict) -> Tuple[Optional[Any], bool]:
        """查询工具缓存。返回 (result_or_None, was_hit)。"""
        if name in NON_CACHEABLE_TOOLS:
            return None, False

        key = self._make_key("tool", name, args)
        result, hit = await self._aget(key)

        async with self._lock:
            if hit:
                self._stats.tool_hits += 1
            else:
                self._stats.tool_misses += 1

        if hit:
            logger.debug(f"[ExecutionCache] tool HIT: {name}")

        return result, hit

    async def aset_tool(self, name: str, args: dict, result: Any) -> None:
        """存储工具结果到缓存。"""
        if name in NON_CACHEABLE_TOOLS:
            return

        key = self._make_key("tool", name, args)
        await self._aset(key, result, "tool")

    # ------------------------------------------------------------------
    # Skill 缓存
    # ------------------------------------------------------------------

    async def aget_skill(self, name: str, inputs: dict) -> Tuple[Optional[Any], bool]:
        """查询 skill 缓存。返回 (result_or_None, was_hit)。"""
        key = self._make_key("skill", name, inputs)
        result, hit = await self._aget(key)

        async with self._lock:
            if hit:
                self._stats.skill_hits += 1
            else:
                self._stats.skill_misses += 1

        if hit:
            logger.debug(f"[ExecutionCache] skill HIT: {name}")

        return result, hit

    async def aset_skill(self, name: str, inputs: dict, result: Any) -> None:
        """存储 skill 结果到缓存。"""
        key = self._make_key("skill", name, inputs)
        await self._aset(key, result, "skill")

    # ------------------------------------------------------------------
    # Per-key 执行保护 (防缓存击穿)
    # ------------------------------------------------------------------

    async def aget_or_execute_tool(
        self,
        name: str,
        args: dict,
        execute_fn,
    ) -> Any:
        """查询缓存，未命中则执行 execute_fn 并存入缓存。

        使用 per-key lock 防止同一 key 的并发击穿：
        - 第一个协程获取 lock，执行工具，写入缓存
        - 其余协程等待 lock 释放后，发现缓存已填充，直接返回

        Args:
            name: 工具名
            args: 工具参数
            execute_fn: 异步可调用对象，执行工具并返回结果

        Returns:
            工具执行结果 (来自缓存或实际执行)
        """
        if name in NON_CACHEABLE_TOOLS:
            return await execute_fn()

        # 先快速检查 (不加 key lock)
        cached, hit = await self.aget_tool(name, args)
        if hit:
            return cached

        # 获取 per-key lock
        key = self._make_key("tool", name, args)
        key_lock = self._get_key_lock(key)

        async with key_lock:
            # double-check: 等锁期间可能已被其他协程填充
            cached, hit = await self.aget_tool(name, args)
            if hit:
                self._cleanup_key_lock(key)
                return cached

            # 执行工具
            result = await execute_fn()

            # 存入缓存
            await self.aset_tool(name, args, result)

            self._cleanup_key_lock(key)
            return result

    async def aget_or_execute_skill(
        self,
        name: str,
        inputs: dict,
        execute_fn,
    ) -> Any:
        """查询缓存，未命中则执行 execute_fn 并存入缓存。

        模式同 aget_or_execute_tool。
        """
        # 先快速检查
        cached, hit = await self.aget_skill(name, inputs)
        if hit:
            return cached

        key = self._make_key("skill", name, inputs)
        key_lock = self._get_key_lock(key)

        async with key_lock:
            # double-check
            cached, hit = await self.aget_skill(name, inputs)
            if hit:
                self._cleanup_key_lock(key)
                return cached

            result = await execute_fn()
            await self.aset_skill(name, inputs, result)

            self._cleanup_key_lock(key)
            return result

    # ------------------------------------------------------------------
    # 管理
    # ------------------------------------------------------------------

    async def clear(self) -> None:
        """清空所有缓存。"""
        async with self._lock:
            self._cache.clear()
            self._key_locks.clear()
            logger.info("[ExecutionCache] cleared")

    async def cleanup_expired(self) -> int:
        """清除所有过期条目。返回清除数量。"""
        if not self.enabled:
            return 0

        async with self._lock:
            now = time.time()
            expired_keys = [
                k for k, v in self._cache.items()
                if now - v.timestamp >= self.ttl
            ]
            for k in expired_keys:
                del self._cache[k]
                self._stats.evictions_ttl += 1

            if expired_keys:
                logger.info(f"[ExecutionCache] cleaned up {len(expired_keys)} expired entries")

            return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息。"""
        total_tool = self._stats.tool_hits + self._stats.tool_misses
        total_skill = self._stats.skill_hits + self._stats.skill_misses
        total = total_tool + total_skill

        return {
            "enabled": self.enabled,
            "size": len(self._cache),
            "max_size": self.max_size,
            "ttl": self.ttl,
            "total_hits": self._stats.tool_hits + self._stats.skill_hits,
            "total_misses": self._stats.tool_misses + self._stats.skill_misses,
            "hit_rate": (self._stats.tool_hits + self._stats.skill_hits) / total if total > 0 else 0.0,
            "tool_hits": self._stats.tool_hits,
            "tool_misses": self._stats.tool_misses,
            "tool_hit_rate": self._stats.tool_hits / total_tool if total_tool > 0 else 0.0,
            "skill_hits": self._stats.skill_hits,
            "skill_misses": self._stats.skill_misses,
            "skill_hit_rate": self._stats.skill_hits / total_skill if total_skill > 0 else 0.0,
            "evictions_ttl": self._stats.evictions_ttl,
            "evictions_size": self._stats.evictions_size,
        }


# ------------------------------------------------------------------
# 全局单例
# ------------------------------------------------------------------

_global_cache: Optional[ExecutionCache] = None


def get_global_execution_cache(
    enabled: bool = True,
    ttl: int = 300,
    max_size: int = 256,
) -> ExecutionCache:
    """获取或创建全局 ExecutionCache 单例。"""
    global _global_cache
    if _global_cache is None:
        _global_cache = ExecutionCache(enabled=enabled, ttl=ttl, max_size=max_size)
        logger.info(f"[ExecutionCache] created (ttl={ttl}s, max_size={max_size}, enabled={enabled})")
    return _global_cache


def reset_global_execution_cache() -> None:
    """重置全局 ExecutionCache 单例。"""
    global _global_cache
    _global_cache = None
