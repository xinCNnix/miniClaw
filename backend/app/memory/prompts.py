"""
Prompts Module - System Prompt Management

This module handles the 7 System Prompt components and their assembly:
1. SKILLS_SNAPSHOT - Dynamic skill list
2. SOUL - Agent personality
3. IDENTITY - Self-identity
4. USER - User profile (from USER.md, human-readable reference)
5. AGENTS - Behavioral guidelines & skill protocol
6. CONVERSATION_CONTEXT - Current session context (extracted from conversation)
7. SEMANTIC_HISTORY - Relevant historical conversation segments (from semantic search)
"""

import os
from pathlib import Path
from typing import List, Dict, Optional

from app.config import get_settings
from app.skills.bootstrap import bootstrap_skills


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
    6. CONVERSATION_CONTEXT - Current session context
    7. SEMANTIC_HISTORY - Semantic search results (historical conversation segments)

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
        # Load components in order
        component_order = [
            "SKILLS_SNAPSHOT",
            "SOUL",
            "IDENTITY",
            "USER",
            "AGENTS",
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

        # Truncate if needed
        if max_length:
            settings = get_settings()
            full_prompt = self._truncate_prompt(
                full_prompt,
                max_length,
                settings.truncation_marker
            )

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

        # Customize USER component with session data
        if component_name == "USER":
            user_context = session_data.get("user_context", "")
            if user_context:
                content += f"\n\n# Current User Context\n{user_context}"
            # Add note that USER.md is human-readable reference
            content += "\n\n⚠️ *Note: This is a user profile for reference. The USER.md file in workspace is maintained for human readability.*"

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

## 当前消息优先
- 最新用户消息是唯一指令来源
- 话题切换 = 立即开始新任务
- 不受历史对话影响

## 技能使用协议
1. 使用技能前必须 `read_file` 读取 SKILL.md
2. 理解后执行实际命令
3. 从当前消息提取参数，不使用历史值

## 示例：天气查询
```
用户："上海天气"
1. read_file("data/skills/get_weather/SKILL.md")
2. terminal("curl -s 'wttr.in/Shanghai?format=j1'")
3. 解析并展示结果
```

## 关键原则
- 从当前消息提取城市名（如"上海"）
- 不使用历史对话中的城市（如"北京"）
- 每次查询都是独立的
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
