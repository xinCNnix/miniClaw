"""ToT 模块公共工具函数。

从 thought_generator.py 和 thought_evaluator.py 提取的重复函数。
两个文件各有 _content_similarity 和 _tool_calls_signature 的完全相同副本，
违反 CLAUDE.md 的代码复用规则（"相同代码出现 2 次 → 必须提取为公共函数"）。
"""
from typing import Any, Dict, List, Optional


def content_similarity(content1: str, content2: str) -> float:
    """计算两个字符串的 Jaccard 词集相似度 (0-1)。

    按空格分词，计算交集/并集比例。
    任一字符串为空返回 0.0。
    """
    words1 = set(content1.split())
    words2 = set(content2.split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def tool_calls_signature(tool_calls: Optional[List[Dict[str, Any]]]) -> tuple:
    """构建 tool_calls 的可哈希签名元组，用于去重比较。

    按 name 排序后提取 (name, path, query) 元组。
    返回空元组 () 如果输入为空。
    """
    if not tool_calls:
        return ()
    sorted_calls = sorted(tool_calls, key=lambda tc: tc.get("name", ""))
    parts = []
    for tc in sorted_calls:
        name = tc.get("name", "")
        args = tc.get("args", {})
        path_val = args.get("path", "")
        query_val = args.get("query", "")
        parts.append((name, path_val, query_val))
    return tuple(parts)
