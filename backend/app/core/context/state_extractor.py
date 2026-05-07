"""StateExtractor — 规则扫描消息流，提取结构化信息。纯确定性逻辑，不调用 LLM。

支持的提取类型：
- 任务列表：checkbox（[x]/[-]/[~]/[ ]）、编号列表、TODO/FIXME 模式
- 文件变更：read_file/write_file 工具调用追踪
- 工具叙述：所有工具调用的一句话摘要
- 决策：决定/选择/采用/不用 等关键词
- 错误：Error/失败/异常 等关键词
- 用户偏好：不要/禁止/必须 等关键词
- 用户意图线索：user 消息的关键内容
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.context.models import ExtractedState, FileChange, Decision, ErrorRecord

logger = logging.getLogger(__name__)

# ── 任务提取正则 ──

# Checkbox 任务标记：- [x] 已完成 / - [ ] 待完成 / - [-] / - [~] 进行中
_RE_CHECKBOX = re.compile(r'- \[([ xX\-~])\]\s*(.+)', re.MULTILINE)
# 编号列表：1. 2. 3. 格式
_RE_NUMBERED = re.compile(r'^\d+\.\s+(.+)', re.MULTILINE)
# TODO/FIXME/待办 模式
_RE_TODO = re.compile(r'(?:TODO|FIXME|待办|待完成)[：:]\s*(.+)', re.MULTILINE)

# ── 决策提取正则 ──

# 决定/选择/采用 关键词
_RE_DECISION_KEYWORDS = re.compile(
    r'(?:决定|选择|采用|决定采用)[了]?\s*(.+?)(?:[，。；\n]|$)',
    re.MULTILINE,
)
# 不用/不使用/避免 关键词（只捕获被拒绝的对象，理由在后续文本中查找）
_RE_REJECTION = re.compile(
    r'(?:不用|不使用|避免|放弃)\s*(\S+?)(?:[，。；\n]|$)',
    re.MULTILINE,
)
# 拒绝理由查找：在"因为/由于"后面查找理由
_RE_REJECTION_RATIONALE = re.compile(
    r'(?:因为|由于)\s*(.+?)(?:[，。；\n]|$)',
    re.MULTILINE,
)
# 因为...所以... 句式
_RE_BECAUSE = re.compile(
    r'因为(.+?)所以(.+?)(?:[，。；\n]|$)',
    re.MULTILINE,
)

# ── 错误提取正则 ──

# Error/错误/失败/异常 关键词
_RE_ERROR = re.compile(
    r'(?:Error|error|错误|失败|异常|bug|Bug|问题)[:：\s]*(.+?)(?:[，。；\n]|$)',
    re.MULTILINE,
)
# 解决/修复/改用 关键词
_RE_SOLUTION = re.compile(
    r'(?:解决|修复|改用|换成|调整为|改回)\s*(.+?)(?:[，。；\n]|$)',
    re.MULTILINE,
)

# ── 用户偏好正则 ──

# 不要/禁止/必须/一定要 等强约束关键词
_RE_USER_PREF = re.compile(
    r'(?:不要|禁止|千万别|绝不能|必须|一定要|只能|务必)\s*(.+?)(?:[，。；\n]|$)',
    re.MULTILINE,
)

# ── 工具相关常量 ──

# 涉及文件操作的工具名称
_TOOL_FILE_OPS = {"read_file", "write_file"}
# 写入类工具（action 标记为 write）
_WRITE_TOOLS = {"write_file", "create_file"}

# 工具名映射（中文叙述模板）
_TOOL_NARRATION_TEMPLATES = {
    "read_file": "读取了 {path}",
    "write_file": "修改了 {path}",
    "terminal": "执行了 {command}",
    "python_repl": "执行了 Python 代码",
    "fetch_url": "获取了 URL 内容",
    "search_kb": "搜索了知识库",
}


class StateExtractor:
    """扫描消息流，提取结构化状态。

    纯规则匹配，不调用 LLM。从 assistant 和 user 消息中
    分别提取任务、文件变更、决策、错误、偏好等信息。
    """

    def extract(self, messages: list[dict]) -> ExtractedState:
        """从消息流中提取所有结构化信息。

        Args:
            messages: 消息列表，每条消息是包含 role 和 content 的 dict。

        Returns:
            ExtractedState 实例，包含所有提取的结构化信息。
        """
        state = ExtractedState()

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "assistant":
                # 从 assistant 消息提取任务列表
                self._extract_tasks_from_assistant(content, state)
                # 从 assistant 的 tool_calls 提取文件变更
                self._extract_file_changes(msg, messages, i, state)
                # 从 tool_calls 生成一句话叙述
                self._extract_tool_narrations(msg, messages, i, state)
                # 从 assistant 消息提取决策
                self._extract_decisions(content, state)
                # 从 assistant 消息提取错误记录
                self._extract_errors(content, state)

            elif role == "user":
                # 从 user 消息提取偏好和约束
                self._extract_user_preferences(content, state)
                # 从 user 消息提取意图线索
                self._extract_user_intent_clues(content, state)

        return state

    def _extract_tasks_from_assistant(self, content: str, state: ExtractedState) -> None:
        """从 assistant 消息中提取任务列表。

        提取三种类型的任务：
        1. Checkbox 任务：- [x] 已完成 / - [-] 进行中 / - [ ] 待完成
        2. 编号列表：仅当包含任务关键词时作为 pending
        3. TODO/FIXME 模式

        Args:
            content: assistant 消息的文本内容。
            state: 用于追加提取结果的 ExtractedState。
        """
        if not isinstance(content, str) or not content:
            return

        # ① Checkbox 任务提取
        for match in _RE_CHECKBOX.finditer(content):
            mark = match.group(1).lower()
            task_text = match.group(2).strip()
            if not task_text:
                continue
            if mark == "x":
                state.tasks_completed.append(task_text)
            elif mark in ("-", "~"):
                state.tasks_in_progress.append(task_text)
            else:
                state.tasks_pending.append(task_text)

        # ② 编号列表提取（仅当没有 checkbox 且包含任务关键词时作为 pending）
        if not _RE_CHECKBOX.search(content):
            task_keywords = ("计划", "任务", "步骤", "待完成", "TODO", "todo", "plan", "step", "task")
            if any(kw in content.lower() for kw in task_keywords):
                for match in _RE_NUMBERED.finditer(content):
                    task_text = match.group(1).strip()
                    if task_text and task_text not in state.tasks_pending:
                        state.tasks_pending.append(task_text)

        # ③ TODO/FIXME 模式提取
        for match in _RE_TODO.finditer(content):
            task_text = match.group(1).strip()
            if task_text and task_text not in state.tasks_pending:
                state.tasks_pending.append(task_text)

    def _extract_file_changes(
        self,
        msg: dict,
        all_messages: list[dict],
        msg_index: int,
        state: ExtractedState,
    ) -> None:
        """从 assistant 的 tool_calls 中提取文件变更。

        扫描 read_file 和 write_file 工具调用，从后续的 tool 消息中
        获取结果内容，提取关键发现（函数名、类名等）。

        Args:
            msg: 当前 assistant 消息。
            all_messages: 完整消息列表。
            msg_index: 当前消息在列表中的索引。
            state: 用于追加提取结果的 ExtractedState。
        """
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            return

        # 构建 tool_call_id → tool result 映射
        tool_results = self._build_tool_result_map(all_messages, msg_index)

        for tc in tool_calls:
            name = tc.get("name", "")
            # 只处理文件操作相关的工具
            if name not in _TOOL_FILE_OPS:
                continue

            args_str = tc.get("arguments", "{}")
            args = self._parse_arguments(args_str)
            path = args.get("path", "")
            if not path:
                continue

            # 判断操作类型：写入工具标记为 write，其他标记为 read
            action = "write" if name in _WRITE_TOOLS else "read"
            tc_id = tc.get("id", "")
            result_content = tool_results.get(tc_id, "")

            # 从工具结果中提取关键发现
            key_findings = self._summarize_file_content(result_content, path)

            state.file_changes.append(FileChange(
                path=path, action=action, key_findings=key_findings,
            ))

    def _extract_tool_narrations(
        self,
        msg: dict,
        all_messages: list[dict],
        msg_index: int,
        state: ExtractedState,
    ) -> None:
        """从 tool_calls 生成一句话叙述。

        为每个工具调用生成简短的中文叙述，包含工具名称、
        操作对象和关键结果。用于压缩后保留工具使用上下文。

        Args:
            msg: 当前 assistant 消息。
            all_messages: 完整消息列表。
            msg_index: 当前消息在列表中的索引。
            state: 用于追加提取结果的 ExtractedState。
        """
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            return

        # 构建 tool_call_id → tool result 映射
        tool_results = self._build_tool_result_map(all_messages, msg_index)

        for tc in tool_calls:
            name = tc.get("name", "")
            args_str = tc.get("arguments", "{}")
            args = self._parse_arguments(args_str)
            tc_id = tc.get("id", "")
            result_content = tool_results.get(tc_id, "")

            # 查找叙述模板，没有则使用默认格式
            template = _TOOL_NARRATION_TEMPLATES.get(name, f"调用了 {name}")

            # 替换模板变量（path, command 等）
            path = args.get("path", "")
            command = args.get("command", "")
            narration = template.format(path=path, command=command)

            # 附加关键结果摘要
            if result_content and name == "terminal":
                # terminal 结果：截断第一行
                narration += f"：{self._truncate_result(result_content)}"
            elif result_content and name == "read_file":
                # read_file 结果：提取函数/类名
                definitions = re.findall(r'(?:def |class )(\w+)', result_content)
                if definitions:
                    narration += f"，发现 {', '.join(definitions[:3])}"

            state.tool_narrations.append(narration)

    def _build_tool_result_map(self, all_messages: list[dict], msg_index: int) -> dict[str, str]:
        """构建 tool_call_id → tool result 内容的映射。

        从当前消息位置向后搜索最多 5 条消息，收集所有 tool 角色的结果。

        Args:
            all_messages: 完整消息列表。
            msg_index: 当前消息索引。

        Returns:
            tool_call_id 到结果内容的映射 dict。
        """
        tool_results: dict[str, str] = {}
        for j in range(msg_index + 1, min(msg_index + 5, len(all_messages))):
            m = all_messages[j]
            if m.get("role") == "tool":
                tc_id = m.get("tool_call_id", "")
                result_content = m.get("content", "")
                if isinstance(result_content, str):
                    tool_results[tc_id] = result_content
        return tool_results

    def _truncate_result(self, content: str, max_len: int = 80) -> str:
        """截断工具结果用于叙述。

        取第一行，超过 max_len 则截断并添加省略号。

        Args:
            content: 工具结果内容。
            max_len: 最大长度。

        Returns:
            截断后的字符串。
        """
        if not isinstance(content, str):
            return ""
        content = content.strip().split('\n')[0]
        if len(content) > max_len:
            return content[:max_len] + "..."
        return content

    def _extract_decisions(self, content: str, state: ExtractedState) -> None:
        """从 assistant 消息中提取决策。

        使用三种模式匹配决策：
        1. 决定/选择/采用 关键词
        2. 不用/不使用/避免 关键词（否定决策）
        3. 因为...所以... 句式（提取理由和结论）

        Args:
            content: assistant 消息的文本内容。
            state: 用于追加提取结果的 ExtractedState。
        """
        if not isinstance(content, str) or not content:
            return

        # 决定/选择/采用 关键词
        for match in _RE_DECISION_KEYWORDS.finditer(content):
            decision_text = match.group(1).strip()
            if decision_text:
                # 在匹配位置之后的文本中查找理由
                rationale = ""
                remaining = content[match.end():]
                rat_match = _RE_REJECTION_RATIONALE.match(remaining)
                if rat_match:
                    rationale = rat_match.group(1).strip()[:200]
                state.decisions.append(Decision(
                    decision=decision_text[:100],
                    rationale=rationale,
                ))

        # 不用/不使用 关键词
        for match in _RE_REJECTION.finditer(content):
            rejected = match.group(1).strip()
            if rejected:
                # 在匹配位置之后的文本中查找理由
                rationale = ""
                remaining = content[match.end():]
                rat_match = _RE_REJECTION_RATIONALE.match(remaining)
                if rat_match:
                    rationale = rat_match.group(1).strip()[:200]
                state.decisions.append(Decision(
                    decision=f"不用{rejected}",
                    rationale=rationale,
                ))

        # 因为...所以... 句式
        for match in _RE_BECAUSE.finditer(content):
            reason = match.group(1).strip()
            result = match.group(2).strip()
            if reason and result:
                state.decisions.append(Decision(
                    decision=result[:100],
                    rationale=reason[:200],
                ))

    def _extract_errors(self, content: str, state: ExtractedState) -> None:
        """从 assistant 消息中提取错误记录。

        检测 Error/错误/失败/异常 等关键词，同时查找
        同一消息中的解决方案（解决/修复/改用 等关键词）。

        Args:
            content: assistant 消息的文本内容。
            state: 用于追加提取结果的 ExtractedState。
        """
        if not isinstance(content, str) or not content:
            return

        for match in _RE_ERROR.finditer(content):
            problem = match.group(1).strip()
            if not problem:
                continue
            # 在同一消息中查找解决方案
            solution = ""
            for sol_match in _RE_SOLUTION.finditer(content):
                solution = sol_match.group(1).strip()
            state.errors.append(ErrorRecord(
                problem=problem[:200],
                solution=solution[:200],
                resolved=bool(solution),
            ))

    def _extract_user_preferences(self, content: str, state: ExtractedState) -> None:
        """从 user 消息中提取偏好。

        检测 不要/禁止/必须/一定要 等强约束关键词，
        保留完整句子上下文以便后续理解。

        Args:
            content: user 消息的文本内容。
            state: 用于追加提取结果的 ExtractedState。
        """
        if not isinstance(content, str) or not content:
            return

        for match in _RE_USER_PREF.finditer(content):
            pref = match.group(1).strip()
            if pref:
                # 保留完整句子上下文
                full_sentence = match.group(0).strip()
                state.user_preferences.append(full_sentence[:150])

    def _extract_user_intent_clues(self, content: str, state: ExtractedState) -> None:
        """从 user 消息中提取意图线索。

        提取所有超过 3 个字符的 user 消息作为意图线索，
        截取前 100 字符保留关键信息。

        Args:
            content: user 消息的文本内容。
            state: 用于追加提取结果的 ExtractedState。
        """
        if not isinstance(content, str):
            return
        if len(content.strip()) < 4:
            return
        # 截取关键片段（前 100 字符）
        clue = content.strip()[:100]
        if clue and clue not in state.user_intent_clues:
            state.user_intent_clues.append(clue)

    def _parse_arguments(self, args_str: str) -> dict[str, Any]:
        """解析 tool_call 的 arguments 字段。

        兼容 JSON 字符串和已解析的 dict 两种格式。

        Args:
            args_str: arguments 字段，可能是 JSON 字符串或 dict。

        Returns:
            解析后的参数 dict。
        """
        if isinstance(args_str, dict):
            return args_str
        try:
            return json.loads(args_str) if args_str else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _summarize_file_content(self, content: str, path: str) -> str:
        """从文件内容中提取关键发现（函数名、类名等）。

        用于在压缩后保留工具结果中的关键信息，
        避免丢失具体的代码结构信息。

        Args:
            content: 工具返回的文件内容。
            path: 文件路径（用于上下文）。

        Returns:
            关键发现的摘要字符串。
        """
        if not content or not isinstance(content, str):
            return ""

        # 提取函数和类定义
        definitions = re.findall(r'(?:def |class |async def )(\w+)', content)
        if definitions:
            return f"发现: {', '.join(definitions[:5])}"

        # 如果内容很短，直接返回
        if len(content) <= 200:
            return content[:200]

        return content[:150] + "..."
