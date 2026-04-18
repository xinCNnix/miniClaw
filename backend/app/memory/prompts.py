"""
Prompts Module - System Prompt Management

This module handles the 8 System Prompt components and their assembly:
1. SKILLS_SNAPSHOT - Dynamic skill list
2. SOUL - Agent personality
3. IDENTITY - Self-identity
4. USER - User profile (from USER.md, human-readable reference)
5. AGENTS - Behavioral guidelines & skill protocol
6. WIKI_MEMORY - Wiki long-term memory (page-level RAG)
7. CONVERSATION_CONTEXT - Current session context (extracted from conversation)
8. SEMANTIC_HISTORY - Relevant historical conversation segments (from semantic search)
"""

import os
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Optional

from app.config import get_settings
from app.skills.bootstrap import bootstrap_skills

logger = logging.getLogger(__name__)


class PromptComponent:
    """A single System Prompt component."""

    def __init__(
        self,
        name: str,
        content: str,
        file_path: Optional[str] = None,
    ):
        """
        Initialize a prompt component.

        Args:
            name: Component name
            content: Component content
            file_path: Path to file (if loaded from file)
        """
        self.name = name
        self.content = content
        self.file_path = file_path

    def length(self) -> int:
        """Get content length in characters."""
        return len(self.content)

    def truncate(self, max_length: int, marker: str = "...[truncated]") -> str:
        """
        Truncate content to max length.

        Args:
            max_length: Maximum length
            marker: Truncation marker

        Returns:
            Truncated content
        """
        if len(self.content) <= max_length:
            return self.content

        truncated = self.content[:max_length - len(marker)]
        return truncated + marker


class SystemPromptBuilder:
    """
    Builder for constructing System Prompts from components.

    The System Prompt consists of 7 components (in order):
    1. SKILLS_SNAPSHOT - Dynamic skill list
    2. SOUL - Agent personality
    3. IDENTITY - Self-identity
    4. USER - User profile (from USER.md, human-readable reference)
    5. AGENTS - Behavioral guidelines & skill protocol
    6. WIKI_MEMORY - Wiki long-term memory (page-level RAG)
    7. CONVERSATION_CONTEXT - Current session context
    8. SEMANTIC_HISTORY - Semantic search results (historical conversation segments)

    Note: MEMORY.md file is for human reference only, not used in system prompt.
    """

    # Component file names (only for file-based components)
    COMPONENT_FILES = {
        "SKILLS_SNAPSHOT": "SKILLS_SNAPSHOT.md",
        "SOUL": "SOUL.md",
        "IDENTITY": "IDENTITY.md",
        "USER": "USER.md",
        "AGENTS": "AGENTS.md",
        # MEMORY.md is excluded - it's for human reference only
    }

    def __init__(self):
        """Initialize the System Prompt builder."""
        settings = get_settings()
        self.workspace_dir = Path(settings.workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        self.components: Dict[str, PromptComponent] = {}
        self._prompt_cache: Dict[str, str] = {}  # Cache for built prompts
        self._initialize_default_components()

    def _initialize_default_components(self) -> None:
        """Create default component files if they don't exist."""
        defaults = {
            "SOUL.md": self._get_default_soul(),
            "IDENTITY.md": self._get_default_identity(),
            "USER.md": self._get_default_user(),
            "AGENTS.md": self._get_default_agents(),
            # MEMORY.md is excluded - created by long_term_updater for human reference
        }

        for filename, content in defaults.items():
            file_path = self.workspace_dir / filename
            if not file_path.exists():
                file_path.write_text(content, encoding="utf-8")

    def _generate_cache_key(self, session_data: Optional[Dict]) -> str:
        """
        Generate cache key based on session data.

        Args:
            session_data: Session data dict

        Returns:
            Cache key string
        """
        import json

        settings = get_settings()

        # If caching is disabled, always return a unique key
        if not settings.enable_prompt_cache:
            return f"nocache_{os.urandom(8).hex()}"

        if not session_data:
            return "default"

        # Generate hash from relevant session data fields
        key_parts = []

        # User context (can be dict or string)
        user_context = session_data.get("user_context", "")
        if user_context:
            # Convert dict to JSON string for hashing
            if isinstance(user_context, dict):
                user_context_str = json.dumps(user_context, sort_keys=True)
            else:
                user_context_str = str(user_context)
            key_parts.append(f"user:{hashlib.md5(user_context_str.encode()).hexdigest()}")

        # Conversation context (hash by content, not full content)
        conv_context = session_data.get("conversation_context", "")
        if conv_context:
            conv_hash = hashlib.md5(str(conv_context).encode()).hexdigest()[:16]
            key_parts.append(f"conv:{conv_hash}")

        # Semantic history (hash by content)
        semantic_hist = session_data.get("semantic_history", "")
        if semantic_hist:
            sem_hash = hashlib.md5(str(semantic_hist).encode()).hexdigest()[:16]
            key_parts.append(f"sem:{sem_hash}")

        return "|".join(key_parts) if key_parts else "default"

    def load_component(self, name: str) -> PromptComponent:
        """
        Load a component from file or return cached version.

        Args:
            name: Component name

        Returns:
            PromptComponent instance
        """
        if name in self.components:
            return self.components[name]

        # Handle SKILLS_SNAPSHOT specially (dynamic)
        if name == "SKILLS_SNAPSHOT":
            content = self._generate_skills_snapshot()
            component = PromptComponent(name, content)
            self.components[name] = component
            return component

        # Load from file
        file_path = self.workspace_dir / self.COMPONENT_FILES.get(name, f"{name}.md")

        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            component = PromptComponent(name, content, str(file_path))
        else:
            # Create empty component
            component = PromptComponent(name, f"# {name}\n# No content yet")

        self.components[name] = component
        return component

    def build_system_prompt(
        self,
        session_data: Optional[Dict] = None,
        max_length: Optional[int] = None,
    ) -> str:
        """
        Build complete System Prompt from components.

        Args:
            session_data: Optional session data to customize prompt
            max_length: Optional maximum length for prompt

        Returns:
            Complete System Prompt

        Examples:
            >>> builder = SystemPromptBuilder()
            >>> prompt = builder.build_system_prompt()
            >>> print(prompt)
        """
        # Add current date to session_data for injection
        from datetime import datetime
        if session_data is None:
            session_data = {}

        # Inject current date/time
        current_time = datetime.now()
        session_data["current_date"] = current_time.strftime("%Y-%m-%d")
        session_data["current_datetime"] = current_time.strftime("%Y-%m-%d %H:%M:%S %Z")
        session_data["current_year"] = current_time.year
        session_data["current_month"] = current_time.strftime("%B")

        logger.debug(f"Injected current date into system prompt: {session_data['current_date']}")

        # Check cache first
        cache_key = self._generate_cache_key(session_data)
        settings = get_settings()

        if settings.enable_prompt_cache and cache_key in self._prompt_cache:
            cached_prompt = self._prompt_cache[cache_key]

            # Check if truncation is needed
            if max_length and len(cached_prompt) > max_length:
                cached_prompt = self._truncate_prompt(
                    cached_prompt,
                    max_length,
                    settings.truncation_marker
                )

            return cached_prompt

        # Build prompt from components
        component_order = [
            "SKILLS_SNAPSHOT",
            "SOUL",
            "IDENTITY",
            "USER",
            "AGENTS",
            "WIKI_MEMORY",           # Wiki long-term memory (page-level RAG)
            "CONVERSATION_CONTEXT",  # Current session context
            "SEMANTIC_HISTORY",      # Semantic search results
        ]

        parts = []
        for name in component_order:
            component = self.load_component(name)

            # Customize component with session data if needed
            content = self._customize_component(component, session_data)

            parts.append(content)

        # Join with separators
        full_prompt = "\n\n---\n\n".join(parts)

        # Smart truncation if needed
        if max_length:
            full_prompt = self._truncate_prompt(
                full_prompt,
                max_length,
                settings.truncation_marker
            )
        elif settings.enable_smart_truncation:
            # Use configured max prompt tokens
            full_prompt = self._smart_truncate_with_budget(
                full_prompt,
                settings.max_prompt_tokens
            )

        # Cache the result if enabled
        if settings.enable_prompt_cache:
            self._prompt_cache[cache_key] = full_prompt

            # Limit cache size to prevent memory issues
            if len(self._prompt_cache) > 100:
                # Remove oldest entries (first 20)
                keys_to_remove = list(self._prompt_cache.keys())[:20]
                for key in keys_to_remove:
                    del self._prompt_cache[key]

        return full_prompt

    def _customize_component(
        self,
        component: PromptComponent,
        session_data: Optional[Dict],
    ) -> str:
        """
        Customize component content based on session data.

        Args:
            component: Component to customize
            session_data: Session data

        Returns:
            Customized content
        """
        if not session_data:
            return component.content

        content = component.content
        component_name = component.name

        # Add current date/time to AGENTS component (most visible place)
        if component_name == "AGENTS":
            current_date = session_data.get("current_date", "")
            current_datetime = session_data.get("current_datetime", "")
            current_year = session_data.get("current_year", "")

            if current_date:
                content += f"\n\n## Current Date/Time\n"
                content += f"- **Today's Date**: {current_date}\n"
                content += f"- **Current Time**: {current_datetime}\n"
                content += f"- **Year**: {current_year}\n"
                content += f"\n⚠️ **IMPORTANT**: Always consider the current date when answering questions about 'latest', 'recent', or 'up-to-date' information."

            # ── 复杂度分类指令（嵌入 Tier 3 回复）──
            content += "\n\n## 任务复杂度分类\n"
            content += "在你回复的第一行，必须输出任务复杂度标签：\n"
            content += "- 简单问题 → 第一行输出 `[SIMPLE]`，然后正常回复\n"
            content += "- 复杂问题 → 第一行输出 `[COMPLEX]`，然后正常回复\n\n"
            content += "**简单问题**（标签 [SIMPLE]）：闲聊、问候、常识问答、翻译、简单解释、概念定义、数学计算、纯文本回答即可的问题\n\n"
            content += "**复杂问题**（标签 [COMPLEX]）：编写代码/程序、画图/绘图/图表、文件读写操作、多步骤任务、数据分析、网络请求、需要调用工具或技能的任务、需要运行代码验证的任务\n\n"
            content += "**示例**：\n"
            content += "- 用户: '你好' → `[SIMPLE]` 你好！\n"
            content += "- 用户: '什么是红黑树' → `[SIMPLE]` 红黑树是一种自平衡二叉搜索树...\n"
            content += "- 用户: '编写一个红黑树并画图' → `[COMPLEX]` 好的，我来编写...\n"
            content += "- 用户: '画一个余弦曲线' → `[COMPLEX]` 好的，我来画图...\n"
            content += "- 用户: '帮我分析这份数据' → `[COMPLEX]` 好的，我来分析...\n"

        # Customize USER component with session data
        elif component_name == "USER":
            user_context = session_data.get("user_context", "")
            if user_context:
                content += f"\n\n# Current User Context\n{user_context}"
            # Add note that USER.md is human-readable reference
            content += "\n\n⚠️ *Note: This is a user profile for reference. The USER.md file in workspace is maintained for human readability.*"

        # Handle CONVERSATION_CONTEXT component (new)
        elif component_name == "WIKI_MEMORY":
            wiki_memory_context = session_data.get("wiki_memory_context", "")
            if wiki_memory_context:
                content = "# Wiki Long-Term Memory\n\n"
                content += wiki_memory_context
                content += "\n\n---\n\n"
                content += "The above Wiki pages contain curated knowledge from past conversations.\n"
                content += "Use them as authoritative references when answering questions.\n"
            else:
                content = "# Wiki Long-Term Memory\n\n*(No relevant Wiki pages found)*"

        # Handle CONVERSATION_CONTEXT component (new)
        elif component_name == "CONVERSATION_CONTEXT":
            conversation_context = session_data.get("conversation_context", "")
            if conversation_context:
                content = conversation_context
            else:
                content = "# Current Session Context\n\n*(No current session context available)*"

        # Handle SEMANTIC_HISTORY component (new)
        elif component_name == "SEMANTIC_HISTORY":
            semantic_history = session_data.get("semantic_history", "")
            if semantic_history:
                content = "# 📜 Relevant Historical Conversation Segments\n\n"
                content += semantic_history
                content += "\n\n---\n\n"
                content += "⚠️ **Important**: These are historical conversation segments for reference only:\n"
                content += "- Use them to understand how the user expressed similar needs\n"
                content += "- Do NOT assume you need to 'continue' or 'supplement' historical conversations\n"
                content += "- The current user message is your ONLY instruction\n"
            else:
                content = "# Semantic Search History\n\n*(No relevant historical conversations found)*"

        return content

    def _truncate_prompt(
        self,
        prompt: str,
        max_length: int,
        marker: str,
    ) -> str:
        """
        Truncate prompt to max length.

        Args:
            prompt: Full prompt
            max_length: Maximum length
            marker: Truncation marker

        Returns:
            Truncated prompt
        """
        if len(prompt) <= max_length:
            return prompt

        # Try to truncate at component boundary
        parts = prompt.split("\n\n---\n\n")
        truncated_parts = []
        current_length = 0

        for part in parts:
            part_length = len(part) + 5  # Include separator

            if current_length + part_length > max_length:
                # Don't add this part
                truncated_parts.append(marker)
                break

            truncated_parts.append(part)
            current_length += part_length

        return "\n\n---\n\n".join(truncated_parts)

    def _smart_truncate_with_budget(
        self,
        prompt: str,
        max_tokens: int,
    ) -> str:
        """
        Smart truncation with token budget allocation.

        Prioritizes:
        1. SKILLS_SNAPSHOT (keep完整 - critical for tool usage)
        2. AGENTS (core behavioral guidelines)
        3. WIKI_MEMORY (curated long-term knowledge)
        4. CONVERSATION_CONTEXT (recent conversation)
        5. SEMANTIC_HISTORY (historical relevance)
        6. USER, SOUL, IDENTITY (can be heavily truncated)

        Args:
            prompt: Full prompt
            max_tokens: Maximum tokens (approximately 1 token = 3-4 chars)

        Returns:
            Truncated prompt
        """
        # Convert tokens to approximate character limit
        max_chars = max_tokens * 4

        if len(prompt) <= max_chars:
            return prompt

        # Split into components
        parts = prompt.split("\n\n---\n\n")
        component_names = [
            "SKILLS_SNAPSHOT",
            "SOUL",
            "IDENTITY",
            "USER",
            "AGENTS",
            "WIKI_MEMORY",
            "CONVERSATION_CONTEXT",
            "SEMANTIC_HISTORY",
        ]

        # Get token budget from config
        settings = get_settings()
        budget = settings.prompt_token_budget

        # Build result with budget-aware truncation
        result_parts = []
        current_length = 0

        for idx, (part, name) in enumerate(zip(parts, component_names)):
            # Get budget for this component
            component_budget = budget.get(name, 1000) * 4  # Convert to chars

            # Truncate if needed
            if len(part) > component_budget:
                # Keep first part of component
                truncated = part[:component_budget - 30] + "\n\n...[truncated]"
                result_parts.append(truncated)
                current_length += len(truncated)
            else:
                result_parts.append(part)
                current_length += len(part)

            # Add separator (except for last part)
            if idx < len(parts) - 1:
                current_length += 5

        return "\n\n---\n\n".join(result_parts)

    def _generate_skills_snapshot(self) -> str:
        """Generate SKILLS_SNAPSHOT.md content in enhanced Markdown format."""
        try:
            bootstrap = bootstrap_skills()
            bootstrap.scan_skills()
            skills = bootstrap.skills

            if not skills:
                return "# Available Skills\n\n*No skills loaded yet*"

            # Build enhanced Markdown format
            lines = [
                "# Available Skills\n",
                f"*Total skills: {len(skills)}*\n",
                "**Important**: To use a skill, you MUST first read its SKILL.md file using `read_file` tool.\n",
            ]

            for skill_name, skill in skills.items():
                lines.append(f"\n## {skill_name}")
                lines.append(f"- **Description**: {skill.description}")
                lines.append(f"- **Location**: `{skill.location}`")

                # Add usage hints based on skill name
                if skill_name == "get_weather":
                    lines.append("- **When to use**: User asks about weather, temperature, or conditions")
                    lines.append("- **Example queries**:")
                    lines.append('  - "北京天气怎么样？"')
                    lines.append('  - "查询上海的天气"')
                elif skill_name == "find-skill":
                    lines.append("- **When to use**: User wants to find other skills")
                elif skill_name == "arxiv-search":
                    lines.append("- **When to use**: User asks about academic papers")

                lines.append(f"\n  **How to use**: `read_file(path=\"{skill.location}/SKILL.md\")`")

            return "\n".join(lines)

        except Exception as e:
            # If skills not available, return empty snapshot
            return "# Available Skills\n\n*No skills loaded yet*\n\nError: " + str(e)

    def update_component(self, name: str, content: str) -> None:
        """
        Update a component's content.

        Args:
            name: Component name
            content: New content

        Raises:
            ValueError: If component name is invalid
        """
        if name == "SKILLS_SNAPSHOT":
            raise ValueError("Cannot update SKILLS_SNAPSHOT directly. It is auto-generated.")

        file_path = self.workspace_dir / self.COMPONENT_FILES.get(name, f"{name}.md")

        # Update file
        file_path.write_text(content, encoding="utf-8")

        # Clear cache
        if name in self.components:
            del self.components[name]

    def get_component_info(self) -> List[Dict[str, any]]:
        """
        Get information about all components.

        Returns:
            List of component info dicts
        """
        info = []

        for name in self.COMPONENT_FILES.keys():
            component = self.load_component(name)
            info.append({
                "name": name,
                "length": component.length(),
                "file_path": component.file_path,
            })

        return info

    # Default component templates

    def _get_default_soul(self) -> str:
        """Get default SOUL component content."""
        return """# Your Soul

You are OpenClaw, an AI agent with curiosity and creativity.

## Core Traits
- Curious: Always eager to learn and explore
- Creative: Think outside the box
- Helpful: Assist users to the best of your ability
- Transparent: Explain your thinking process
- Humble: Admit when you don't know something

## Personality
- Friendly and approachable
- Professional yet conversational
- Thoughtful and thorough

## Purpose
Your purpose is to assist users by using your available tools and skills effectively.
"""

    def _get_default_identity(self) -> str:
        """Get default IDENTITY component content."""
        return """# Your Identity

You are a coding assistant with access to powerful tools.

## Capabilities
- Execute shell commands (terminal)
- Run Python code (python_repl)
- Fetch web content (fetch_url)
- Read local files (read_file)
- Search knowledge base (search_knowledge_base)
- Use various skills via Instruction-following

## Role
You help users with:
- Software development tasks
- Data analysis and processing
- System administration
- Information retrieval
- And much more!

## Constraints
- Always use tools when appropriate
- Explain your actions clearly
- Ask for clarification when needed
- Stay within your defined capabilities
"""

    def _get_default_user(self) -> str:
        """Get default USER component content."""
        return """# User Context

## User Preferences
- Prefers clear and concise explanations
- Values honesty and transparency
- Appreciates step-by-step breakdowns

## Communication Style
- Direct and to the point
- Avoid excessive jargon
- Provide examples when helpful

---

*Note: This section should be customized based on actual user data.*
"""

    def _get_default_agents(self) -> str:
        """Get default AGENTS component content (concise version)."""
        return """# 核心行为准则

## 对话连续性
- **优先使用 CONVERSATION_CONTEXT** - 查看下方的"Recent Conversation"了解对话历史
- **理解对话流程** - 如果用户延续之前的话题，基于上下文回应
- **话题切换检测** - 当用户明显切换话题时，开始新任务（忽略不相关的历史）

## 短期记忆使用规则
1. **CONVERSATION_CONTEXT** 显示了最近的对话轮次
2. **连续对话** - 如果用户问"那...呢？"或继续讨论，使用上下文理解
3. **新话题** - 如果用户问完全不同的问题，视为新任务
4. **参数提取** - 始终从**当前消息**提取具体参数（如城市名、文件名）

## 示例场景

### 场景1：对话延续
```
CONVERSATION_CONTEXT:
  Turn 1: User: "北京天气怎么样？" → Assistant: "北京今天晴天..."

当前消息: "那上海呢？"
✅ 正确: 查询上海天气（理解用户继续问天气）
❌ 错误: 询问"上海什么？"
```

### 场景2：话题切换
```
CONVERSATION_CONTEXT:
  Turn 1: User: "北京天气" → Assistant: "..."

当前消息: "帮我搜索arxiv关于transformer的论文"
✅ 正确: 视为新任务，搜索论文（话题已切换）
❌ 错误: 继续讨论天气
```

## 技能使用协议
1. 使用技能前必须 `read_file` 读取 SKILL.md
2. 理解后执行实际命令
3. **参数从当前消息提取**（不使用历史值）
"""


def build_system_prompt(
    session_data: Optional[Dict] = None,
    max_length: Optional[int] = None,
) -> str:
    """
    Build complete System Prompt.

    Args:
        session_data: Optional session data
        max_length: Optional max prompt length

    Returns:
        Complete System Prompt

    Examples:
        >>> from app.memory.prompts import build_system_prompt
        >>> prompt = build_system_prompt()
        >>> print(prompt)
    """
    builder = SystemPromptBuilder()
    return builder.build_system_prompt(session_data, max_length)
