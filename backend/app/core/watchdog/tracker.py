"""进度追踪器 — 检测 Agent 运行中的卡死和循环。

检测两种故障模式：
1. 状态卡死：连续 N 次状态指纹相同
2. 动作重复：连续 N 次工具调用相同
"""
from __future__ import annotations

import hashlib
import json
from collections import deque
from typing import Any, Dict


def _sha1(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


class ProgressTracker:
    """追踪状态指纹和动作，检测循环。"""

    def __init__(self, maxlen: int = 10):
        self.maxlen = maxlen
        self.state_hashes: deque[str] = deque(maxlen=maxlen)
        self.actions: deque[str] = deque(maxlen=maxlen)

    def record_state(self, state: Any) -> None:
        self.state_hashes.append(_sha1(state))

    def record_action(self, action: Any) -> None:
        self.actions.append(_sha1(action))

    def is_state_stuck(self, threshold: int = 4) -> bool:
        if len(self.state_hashes) < threshold:
            return False
        tail = list(self.state_hashes)[-threshold:]
        return len(set(tail)) == 1

    def is_action_repeating(self, threshold: int = 3) -> bool:
        if len(self.actions) < threshold:
            return False
        tail = list(self.actions)[-threshold:]
        return len(set(tail)) == 1

    def snapshot(self) -> Dict[str, Any]:
        return {
            "state_hashes": list(self.state_hashes),
            "actions": list(self.actions),
            "state_stuck": self.is_state_stuck(),
            "action_repeating": self.is_action_repeating(),
        }
