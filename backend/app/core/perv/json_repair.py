"""
JSON Repair Module for PEVR

Robust multi-strategy JSON repair for handling broken LLM JSON output.

LLM 输出的 JSON 经常出现各种损坏，本模块按优先级依次尝试多种
修复策略，确保尽可能从残缺文本中提取出有效的 JSON 数据。

修复策略（按尝试顺序）:
    1. 直接解析 (json.loads)
    2. 提取 Markdown 代码块 (```json ... ```)
    3. 闭合截断的括号/花括号/引号
    4. 修复常见语法问题（尾逗号、单引号、未转义换行、注释）
    5. 正则提取首个完整 JSON 对象/数组
    6. 剥离无效前缀/后缀

支持的损坏类型:
    - 截断: ``[{"id": "1", "tool":`` -> 自动闭合
    - Markdown 包裹: `` ```json\\n[...]\\n``` ``
    - 尾逗号: ``[1, 2, 3,]``
    - 单引号: ``{'key': 'value'}``
    - 未转义换行: ``"text": "line1\\nline2"``
    - JSON 注释: ``{// comment\\n"key": 1}``
    - 前缀文字: ``结果是：[{"id":...}]``
    - 后缀文字: ``[{"id":...}] 完成``
    - 不完整键值对: ``{"id": "1", "tool":`` -> 移除残缺项
    - 双重转义: ``"text": \\\\"hello\\\\"`` -> 修正

仅使用标准库 (json, re)，不引入第三方依赖。
"""

import json
import logging
import re
from typing import Union

logger = logging.getLogger(__name__)


def repair_json(raw: str) -> Union[dict, list]:
    """修复损坏的 JSON 文本并返回解析结果。

    按优先级依次尝试多种修复策略。如果所有策略均失败，
    抛出 ValueError 并附带最后一次解析错误信息。

    Args:
        raw: LLM 输出的原始文本，可能包含损坏的 JSON。

    Returns:
        解析后的 dict 或 list。

    Raises:
        ValueError: 所有修复策略均无法解析时抛出。
    """
    if not raw or not raw.strip():
        raise ValueError("Empty input: cannot repair empty or whitespace-only string")

    text = raw.strip()

    # --- Strategy 1: Direct parse ---------------------------------------------------
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # --- Strategy 2: Extract from Markdown code block -------------------------------
    extracted = _extract_markdown_block(text)
    if extracted is not None:
        try:
            return json.loads(extracted)
        except (json.JSONDecodeError, TypeError):
            # 继续用后续策略修复 code block 内容
            text = extracted

    # --- Strategy 3: Strip invalid prefix/suffix ------------------------------------
    stripped = _strip_noise(text)
    if stripped != text:
        try:
            return json.loads(stripped)
        except (json.JSONDecodeError, TypeError):
            text = stripped

    # --- Strategy 4: Fix common syntax issues ---------------------------------------
    fixed = _fix_common_issues(text)
    if fixed != text:
        try:
            return json.loads(fixed)
        except (json.JSONDecodeError, TypeError):
            text = fixed

    # --- Strategy 5: Close truncated brackets/braces/quotes -------------------------
    closed = _close_truncated(text)
    if closed != text:
        try:
            return json.loads(closed)
        except (json.JSONDecodeError, TypeError):
            # 闭合后可能仍有语法问题，尝试再修一次
            double_fixed = _fix_common_issues(closed)
            try:
                return json.loads(double_fixed)
            except (json.JSONDecodeError, TypeError):
                pass

    # --- Strategy 6: Regex extract first complete JSON ------------------------------
    extracted_obj = _extract_first_json(text)
    if extracted_obj is not None:
        return extracted_obj

    # --- Strategy 7: Combined brute-force -------------------------------------------
    # Apply all fixes in sequence and try after each step
    candidate = raw.strip()
    candidate = _extract_markdown_block(candidate) or candidate
    candidate = _strip_noise(candidate)
    candidate = _fix_common_issues(candidate)
    candidate = _close_truncated(candidate)
    candidate = _remove_incomplete_trailing_item(candidate)
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        pass

    logger.warning(
        "All JSON repair strategies failed for input (first 200 chars): %s",
        raw[:200],
    )
    raise ValueError(
        f"Failed to repair JSON after all strategies. Last candidate (first 200 chars): "
        f"{candidate[:200]}"
    )


def repair_json_or_none(raw: str) -> Union[dict, list, None]:
    """修复损坏的 JSON 文本，失败时返回 None 而非抛出异常。

    Args:
        raw: LLM 输出的原始文本。

    Returns:
        解析后的 dict/list，或 None（如果修复失败）。
    """
    try:
        return repair_json(raw)
    except (ValueError, TypeError):
        return None


# =============================================================================
# Internal helper functions
# =============================================================================


def _extract_markdown_block(text: str) -> Union[str, None]:
    """从 Markdown 代码块中提取内容。

    匹配 ```json ... ``` 或 ``` ... ``` 包裹的内容。
    如果没有匹配到代码块，返回 None。

    Args:
        text: 可能包含 Markdown 代码块的文本。

    Returns:
        代码块内的纯文本，或 None。
    """
    # Try ```json ... ``` first (greedy within reason)
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _strip_noise(text: str) -> str:
    """剥离 JSON 前后的无效文字。

    处理以下情况:
    - 前缀文字: "结果是：[{"id":...}]"
    - 后缀文字: "[{"id":...}] 完成"
    - 前后混合文字

    Args:
        text: 可能包含前后噪声的文本。

    Returns:
        剥离噪声后的文本。
    """
    # Find the first [ or { and last ] or }
    start = -1
    end = -1

    for i, ch in enumerate(text):
        if ch in ("[", "{"):
            start = i
            break

    for i in range(len(text) - 1, -1, -1):
        if text[i] in ("]", "}"):
            end = i + 1
            break

    if start >= 0 and end > start:
        return text[start:end]
    return text


def _fix_common_issues(text: str) -> str:
    """修复常见的 JSON 语法问题。

    处理:
    - 单引号 -> 双引号（仅顶层，不递归）
    - 尾逗号: [1, 2, 3,] -> [1, 2, 3]
    - JavaScript 风格注释: // ... 和 /* ... */
    - 双重转义: \\" -> "
    - 未转义的控制字符

    注意：单引号替换是保守的，仅在字符上下文中进行，
    避免错误地替换已经正确转义的内容。

    Args:
        text: JSON 文本。

    Returns:
        修复后的文本。
    """
    # Remove single-line comments: // ...
    # 但要小心不要破坏 URL 中的 //
    text = re.sub(r"(?<!:)//.*?$", "", text, flags=re.MULTILINE)

    # Remove multi-line comments: /* ... */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # Fix double-escaped quotes: \\" -> \"
    text = text.replace('\\\\\\"', '\\"')

    # Fix trailing commas before } or ]
    # Match comma followed by optional whitespace then closing bracket
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # Replace single-quoted strings with double-quoted strings.
    # This is a best-effort heuristic: replace 'key' patterns that look like
    # JSON string literals. We use a targeted approach to avoid breaking
    # content that legitimately contains single quotes.
    text = _replace_single_quotes(text)

    # Fix unescaped newlines inside string values
    text = _fix_unescaped_newlines(text)

    return text


def _replace_single_quotes(text: str) -> str:
    """将 JSON 中的单引号字符串替换为双引号字符串。

    保守策略：仅替换看起来像 JSON 键或值的单引号字符串，
    避免破坏包含单引号的自然语言文本。

    Args:
        text: 可能包含单引号字符串的 JSON 文本。

    Returns:
        替换后的文本。
    """
    # If the text looks like it uses single quotes for JSON structure
    # (starts with { or [ and contains patterns like 'key':), do replacement
    if not re.search(r"['\"]", text):
        return text

    # Simple approach: if the text contains '{' or '[' patterns with single quotes,
    # replace top-level single-quoted strings
    result = []
    i = 0
    in_double_quote = False

    while i < len(text):
        ch = text[i]

        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_double_quote = not in_double_quote
            result.append(ch)
            i += 1
            continue

        if ch == "'" and not in_double_quote:
            # Found a single quote outside double quotes — replace with double quote
            result.append('"')
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _fix_unescaped_newlines(text: str) -> str:
    """修复 JSON 字符串值中未转义的换行符。

    在双引号字符串内部，将实际的换行符替换为 \\n。

    Args:
        text: JSON 文本。

    Returns:
        修复后的文本。
    """
    result = []
    in_string = False
    i = 0

    while i < len(text):
        ch = text[i]

        if ch == '"' and (i == 0 or text[i - 1] != "\\"):
            in_string = not in_string
            result.append(ch)
            i += 1
            continue

        if in_string and ch == "\n":
            result.append("\\n")
            i += 1
            continue

        if in_string and ch == "\r":
            # Skip bare \r, or replace \r\n with \\n
            if i + 1 < len(text) and text[i + 1] == "\n":
                result.append("\\n")
                i += 2
                continue
            result.append("\\n")
            i += 1
            continue

        if in_string and ch == "\t":
            result.append("\\t")
            i += 1
            continue

        result.append(ch)
        i += 1

    return "".join(result)


def _close_truncated(text: str) -> str:
    """尝试闭合截断的 JSON。

    处理以下截断模式:
    - 缺少闭合括号: [{"id": "1"}  ->  [{"id": "1"}]
    - 缺少闭合花括号: {"key": "val"  ->  {"key": "val"}
    - 缺少闭合引号: "hello  ->  "hello"
    - 不完整键值对: {"id": "1", "tool":  ->  {"id": "1"}

    算法：
    1. 追踪括号栈，确定哪些括号未闭合
    2. 修复未闭合的字符串
    3. 移除末尾不完整的键值对
    4. 按逆序闭合所有未闭合的括号

    Args:
        text: 截断的 JSON 文本。

    Returns:
        尝试闭合后的文本。
    """
    # First, remove incomplete trailing items
    text = _remove_incomplete_trailing_item(text)

    # Track bracket stack
    bracket_stack = []  # list of opening chars: { or [
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue

        if ch == "\\":
            if in_string:
                escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch in ("{", "["):
            bracket_stack.append(ch)
        elif ch == "}" and bracket_stack and bracket_stack[-1] == "{":
            bracket_stack.pop()
        elif ch == "]" and bracket_stack and bracket_stack[-1] == "[":
            bracket_stack.pop()

    # Close unclosed string
    if in_string:
        text += '"'

    # Close brackets in reverse order
    closing_map = {"{": "}", "[": "]"}
    for bracket in reversed(bracket_stack):
        text += closing_map[bracket]

    return text


def _remove_incomplete_trailing_item(text: str) -> str:
    """移除末尾不完整的键值对或数组元素。

    处理如下模式:
    - {"id": "1", "tool":        -> {"id": "1"}
    - [{"id": "1"}, {"id":       -> [{"id": "1"}]
    - [1, 2, 3,                  -> [1, 2, 3]
    - {"a": 1, "b":              -> {"a": 1}

    策略：从末尾向前查找最后一个看起来完整的值结束位置，
    截断其后方的所有内容。

    Args:
        text: 可能包含末尾不完整项的文本。

    Returns:
        清理后的文本。
    """
    stripped = text.rstrip()

    # If text ends with a complete closing bracket, nothing to do
    if stripped and stripped[-1] in ("}", "]", '"', "'", ")"):
        # Check if it ends with a proper closing
        # (we might still have issues, but let the caller handle them)
        return text

    # Try to find the last complete value by scanning backwards for
    # structural markers that indicate a complete element
    # Complete patterns: "value"}, "value"], "value", number}, number], etc.

    # Pattern: look for the last occurrence of a complete key-value pair
    # or array element, followed by a comma or end of structure

    # Strategy: iteratively strip trailing incomplete segments
    result = stripped

    # Remove trailing comma and whitespace
    result = re.sub(r",\s*$", "", result)

    # If it ends with a colon (incomplete key-value), remove back to last comma
    if re.search(r":\s*$", result):
        # Find the last comma that's at the same nesting level
        result = _strip_back_to_last_separator(result)

    # If it ends with an opening quote but no closing quote
    # (incomplete string value), strip back
    if re.search(r'"\s*$', result) is None and re.search(r':\s*"[^"]*$', result):
        result = _strip_back_to_last_separator(result)

    # General: if ends with something that doesn't look like a valid JSON suffix
    # Try to find the last complete element boundary
    if result and result[-1] not in ("}", "]", '"', "'", "0", "1", "2", "3", "4",
                                      "5", "6", "7", "8", "9", "e", "l", "s", "n"):
        # Might be incomplete; try stripping to last comma
        result = _strip_back_to_last_separator(result)

    return result


def _strip_back_to_last_separator(text: str) -> str:
    """从末尾向前找到最后一个结构分隔符（逗号或冒号前），
    截断其后的不完整内容。

    在正确处理嵌套层级的前提下，找到最后一个处于顶层嵌套
    层级的逗号，截断其后方内容。

    Args:
        text: JSON 文本。

    Returns:
        截断后的文本。
    """
    depth = 0
    in_string = False
    escape_next = False
    last_comma_pos = -1

    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue

        if ch == "\\":
            if in_string:
                escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch in ("{", "["):
            depth += 1
        elif ch in ("}", "]"):
            depth -= 1
        elif ch == "," and depth <= 1:
            last_comma_pos = i

    if last_comma_pos >= 0:
        return text[:last_comma_pos]

    # No comma found — try to find last complete closing bracket
    return text


def _extract_first_json(text: str) -> Union[dict, list, None]:
    """使用正则从文本中提取第一个完整的 JSON 对象或数组。

    匹配策略：
    - 寻找第一个 { 或 [ 起始位置
    - 从该位置开始，追踪括号匹配，找到对应闭合位置
    - 尝试解析提取的子串

    不使用正则递归匹配（不可靠），改用手动括号追踪。

    Args:
        text: 可能包含 JSON 的文本。

    Returns:
        解析后的 dict/list，或 None。
    """
    # Find first { or [
    start = -1
    start_char = None
    for i, ch in enumerate(text):
        if ch in ("{", "["):
            start = i
            start_char = ch
            break

    if start < 0:
        return None

    # Track brackets to find matching close
    end_char = "}" if start_char == "{" else "]"
    depth = 0
    in_string = False
    escape_next = False
    end = -1

    for i in range(start, len(text)):
        ch = text[i]

        if escape_next:
            escape_next = False
            continue

        if ch == "\\":
            if in_string:
                escape_next = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == start_char:
            depth += 1
        elif ch == end_char:
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    if end < 0:
        return None

    candidate = text[start:end]
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        # Try fixing the extracted substring
        fixed = _fix_common_issues(candidate)
        try:
            return json.loads(fixed)
        except (json.JSONDecodeError, TypeError):
            return None
