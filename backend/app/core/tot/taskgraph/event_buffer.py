"""
TaskGraphEventBuffer — SSE 事件环形缓冲，支持断线重连。

客户端通过 run_id 重新订阅时，从 last_event_index 之后追发缺失事件。
"""
from __future__ import annotations

import logging
from collections import deque
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class TaskGraphEventBuffer:
    """SSE 事件环形缓冲，支持断线重连"""

    def __init__(self, max_events: int = 500):
        self._buffer: deque = deque(maxlen=max_events)
        self._event_index: int = 0
        self._completed: bool = False
        self._final_answer: Optional[str] = None

    def append(self, event: Dict) -> int:
        """追加事件，返回索引"""
        self._event_index += 1
        event["_index"] = self._event_index
        self._buffer.append(event)
        return self._event_index

    def get_since(self, last_index: int) -> List[Dict]:
        """获取 last_index 之后的所有事件（用于重连）"""
        return [e for e in self._buffer if e.get("_index", 0) > last_index]

    def mark_completed(self, final_answer: str) -> None:
        """标记运行完成"""
        self._completed = True
        self._final_answer = final_answer

    def is_completed(self) -> bool:
        return self._completed

    def get_final_answer(self) -> Optional[str]:
        return self._final_answer
