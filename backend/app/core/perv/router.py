"""PERV 硬规则路由器 - 默认 direct_answer + 硬规则触发 PERV

根据任务风险等级选择不同执行路径:
- direct_answer: 简单问答、社交问候，直接用普通 Agent（0 token）
- plan_execute (低风险): PEVR 但跳过 Verifier
- plan_execute (中风险): PEVR + Summarizer 压缩后进 Verifier
- plan_execute_verify (高风险): 完整 PEVR 原始数据流程

路由策略（0 token 消耗，纯规则）:
1. 高风险关键词 → plan_execute_verify
2. PERV 触发硬规则（动作短语/结构性特征/超长输入）→ plan_execute
3. 社交/问候精确匹配 → direct_answer
4. 无匹配 → direct_answer（默认）
"""

import hashlib
import logging
import re
import time
from collections import OrderedDict
from typing import Optional

from app.core.perv.state import RouteDecision

logger = logging.getLogger(__name__)

# ── 高风险关键词 ──────────────────────────────────────────────

_HIGH_RISK_KEYWORDS = [
    # 金融/法律
    "转账", "支付", "银行卡", "合同", "起诉", "律师", "汇款", "退款",
    # 医疗
    "处方", "剂量", "诊断", "手术", "用药", "病历",
    # 危险命令
    "rm -rf", "drop table", "delete database", "format disk",
    "shutdown", "mkfs", "dd if=",
]

# ── PERV 触发：动作短语 ──────────────────────────────────────

_PERV_TRIGGER_PHRASES = [
    # 代码执行
    "运行代码", "执行代码", "跑一下", "运行一下", "执行一下",
    "run code", "execute code",
    # 文件操作
    "读取文件", "打开文件", "保存文件", "写文件", "创建文件", "查看文件",
    "read file", "write file", "save file",
    # 网络/下载
    "下载论文", "下载文件", "爬取", "抓取",
    "download", "scrape", "crawl",
    # 搜索
    "搜索一下", "搜索知识库", "帮我搜索", "查找资料",
    "search for", "look up",
    # 代码生成
    "帮我写代码", "写个函数", "写个脚本", "帮我写个",
    "write code", "write a function",
    # 多步骤
    "帮我一步步", "分步骤", "step by step",
    # 终端
    "终端执行", "运行命令", "执行命令",
    # 数据处理
    "分析数据", "处理数据", "解析数据",
    "analyze data", "process data",
]

# ── PERV 触发：结构性特征正则 ────────────────────────────────

_PERV_TRIGGER_PATTERNS = [
    re.compile(r"https?://\S+"),          # URL
    re.compile(r"www\.\S+\.\w+"),         # www.xxx.com
    re.compile(r"```"),                    # 代码块
    re.compile(r"\.\w{1,4}$"),            # 文件扩展名 (.py, .csv)
    re.compile(r"(?:^|\s)/[\w/.]+"),      # Unix 路径
    re.compile(r"[A-Z]:\\[\w\\]+"),       # Windows 路径
]

# ── PERV 触发：超长输入阈值 ──────────────────────────────────

_PERV_LONG_INPUT_THRESHOLD = 200  # 超过200字触发PERV

# ── 社交/问候精确匹配 ────────────────────────────────────────

_SOCIAL_EXACT_MATCHES = {
    "你好", "您好", "嗨", "早上好", "下午好", "晚上好",
    "你好啊", "在吗", "在不在",
    "hello", "hi", "hey", "good morning", "good evening",
    "谢谢", "感谢", "多谢", "thanks", "thank you", "thx",
    "再见", "拜拜", "bye", "goodbye", "晚安",
    "好的", "嗯", "嗯嗯", "哦", "哦哦", "ok", "okay", "sure",
    "是的", "对的", "没错",
    "继续", "go on", "continue",
    "很好", "不错", "great", "nice", "good",
}


# ── 路由缓存 ─────────────────────────────────────────────────

class RouteCache:
    """LRU + TTL 路由缓存。只缓存 PERV 触发结果。"""

    def __init__(self, max_size: int = 256, ttl_seconds: int = 1800):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, tuple] = OrderedDict()

    def get(self, user_input: str):
        """返回缓存的 RouteDecision 或 None。"""
        key = hashlib.md5(user_input.strip().lower().encode()).hexdigest()
        if key in self._cache:
            decision, ts = self._cache[key]
            if time.monotonic() - ts < self._ttl:
                self._cache.move_to_end(key)  # LRU
                return decision
            else:
                del self._cache[key]  # TTL 过期
        return None

    def put(self, user_input: str, decision):
        """缓存 PERV 触发结果。direct_answer 不缓存。"""
        if decision.get("mode") == "direct_answer":
            return
        key = hashlib.md5(user_input.strip().lower().encode()).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
        self._cache[key] = (decision, time.monotonic())
        # LRU 淘汰
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)


_route_cache: Optional[RouteCache] = None


def _get_route_cache() -> RouteCache:
    """获取路由缓存单例。"""
    global _route_cache
    if _route_cache is None:
        try:
            from app.config import get_settings
            settings = get_settings()
            _route_cache = RouteCache(
                max_size=getattr(settings, "perv_router_cache_max_size", 256),
                ttl_seconds=getattr(settings, "perv_router_cache_ttl", 1800),
            )
        except Exception:
            _route_cache = RouteCache()
    return _route_cache


# ── 硬规则路由 ───────────────────────────────────────────────

def hard_rule_router(user_input: str) -> Optional[RouteDecision]:
    """三阶段硬规则路由（0 token，<1ms）。

    阶段 1: 高风险关键词 → plan_execute_verify
    阶段 2: PERV 触发硬规则（动作短语/结构性特征/超长输入）→ plan_execute
    阶段 3: 社交/问候精确匹配 → direct_answer
    无匹配 → 返回 None（由 route() 默认为 direct_answer）

    Args:
        user_input: 用户输入文本。

    Returns:
        RouteDecision 或 None。
    """
    text = user_input.strip()
    text_lower = text.lower()

    # ── 阶段 1: 高风险关键词检测 ──
    for kw in _HIGH_RISK_KEYWORDS:
        if kw in text_lower:
            return RouteDecision(
                mode="plan_execute_verify",
                risk="high",
                reason=f"high_risk_keyword:{kw}",
                max_steps=8,
                allow_tools=True,
                source="rule",
            )

    # ── 阶段 2: PERV 触发硬规则 ──

    # 2a. 动作短语匹配
    for phrase in _PERV_TRIGGER_PHRASES:
        if phrase in text_lower:
            return RouteDecision(
                mode="plan_execute",
                risk="medium",
                reason=f"trigger_phrase:{phrase}",
                max_steps=6,
                allow_tools=True,
                source="rule",
            )

    # 2b. 结构性特征正则匹配
    for pattern in _PERV_TRIGGER_PATTERNS:
        if pattern.search(text):
            return RouteDecision(
                mode="plan_execute",
                risk="medium",
                reason=f"trigger_pattern:{pattern.pattern}",
                max_steps=6,
                allow_tools=True,
                source="rule",
            )

    # 2c. 超长输入
    if len(text) > _PERV_LONG_INPUT_THRESHOLD:
        return RouteDecision(
            mode="plan_execute",
            risk="medium",
            reason="long_input",
            max_steps=6,
            allow_tools=True,
            source="rule",
        )

    # ── 阶段 3: 社交/问候精确匹配 ──
    if text_lower in _SOCIAL_EXACT_MATCHES:
        return RouteDecision(
            mode="direct_answer",
            risk="low",
            reason="social_greeting",
            max_steps=1,
            allow_tools=True,
            source="rule",
        )

    # 无匹配 → 由 route() 默认为 direct_answer
    return None


# ── 路由入口 ─────────────────────────────────────────────────

async def route(user_input: str, llm=None) -> RouteDecision:
    """优化后的路由入口。默认 direct_answer，硬规则触发才进 PERV。

    Args:
        user_input: 用户输入文本。
        llm: 保留参数（向后兼容），不再使用。

    Returns:
        RouteDecision。
    """
    start = time.monotonic()

    try:
        from app.config import get_settings
        settings = get_settings()

        # 路由器被禁用 → 返回 plan_execute_verify
        if not getattr(settings, "perv_router_enabled", True):
            logger.debug("PERV router disabled, using default route")
            return RouteDecision(
                mode="plan_execute_verify",
                risk="medium",
                reason="router_disabled",
                max_steps=getattr(settings, "planner_max_steps", 8),
                allow_tools=True,
                source="rule",
            )

        # 1. 缓存检查
        if getattr(settings, "perv_router_cache_enabled", True):
            cache = _get_route_cache()
            cached = cache.get(user_input)
            if cached is not None:
                elapsed = (time.monotonic() - start) * 1000
                logger.info("Route cache hit: mode=%s (%.1fms)", cached["mode"], elapsed)
                return cached

        # 2. 硬规则匹配（0 token，<1ms）
        decision = hard_rule_router(user_input)

        if decision is None:
            # 3. 无硬规则匹配 → 默认 direct_answer
            decision = RouteDecision(
                mode="direct_answer",
                risk="low",
                reason="default_no_trigger",
                max_steps=1,
                allow_tools=True,
                source="rule",
            )

        # 4. 缓存写入（只缓存 PERV 触发）
        if getattr(settings, "perv_router_cache_enabled", True):
            cache = _get_route_cache()
            cache.put(user_input, decision)

        elapsed = (time.monotonic() - start) * 1000
        logger.info("Route: mode=%s risk=%s reason=%s (%.1fms)",
                    decision["mode"], decision["risk"], decision["reason"], elapsed)
        return decision

    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        logger.error("Router error (%.1fms): %s", elapsed, e, exc_info=True)
        return RouteDecision(
            mode="direct_answer",
            risk="low",
            reason=f"error:{type(e).__name__}",
            max_steps=1,
            allow_tools=True,
            source="rule",
        )


# ── Backward-compatible aliases ──────────────────────────────────────

# rule_router was renamed to hard_rule_router
rule_router = hard_rule_router


def llm_router(user_input: str, llm=None):
    """Deprecated: LLM routing was removed. Returns None (no LLM routing step)."""
    return None
