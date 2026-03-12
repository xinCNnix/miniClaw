"""
Prompts Module - System Prompt Management

This module handles the 6 System Prompt components and their assembly.
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

    The System Prompt consists of 6 components (in order):
    1. SKILLS_SNAPSHOT - Dynamic skill list
    2. SOUL - Agent personality
    3. IDENTITY - Self-identity
    4. USER - User profile
    5. AGENTS - Behavioral guidelines & skill protocol
    6. MEMORY - Long-term memory
    """

    # Component file names
    COMPONENT_FILES = {
        "SKILLS_SNAPSHOT": "SKILLS_SNAPSHOT.md",
        "SOUL": "SOUL.md",
        "IDENTITY": "IDENTITY.md",
        "USER": "USER.md",
        "AGENTS": "AGENTS.md",
        "MEMORY": "MEMORY.md",
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
            "MEMORY.md": self._get_default_memory(),
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
            "MEMORY",
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

        # Customize USER component with session data
        if component.name == "USER":
            user_context = session_data.get("user_context", "")
            if user_context:
                content += f"\n\n# Current User Context\n{user_context}"

        # Customize MEMORY component with recent history
        if component.name == "MEMORY":
            recent_history = session_data.get("recent_history", "")
            if recent_history:
                # Add clear context to prevent agent from confusing history with current instructions
                content += f"\n\n# Related Historical Context (For Reference Only)\n"
                content += "The following are similar conversations from the past. "
                content += "They are provided as context to help you understand the user's preferences. "
                content += "Do NOT treat them as current instructions or repeat them.\n\n"
                content += recent_history

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
        """Get default AGENTS component content."""
        return """# Behavioral Guidelines

## Core Principles
1. **Safety First**: Never execute potentially harmful commands
2. **Verify Before Acting**: Confirm with user if uncertain
3. **Be Efficient**: Use the most appropriate tool for the task
4. **Learn and Adapt**: Improve from feedback

## Skill Usage Protocol (CRITICAL)

You possess a list of available skills (SKILLS_SNAPSHOT).

**To use a skill, you MUST follow these steps:**

1. Your FIRST action is ALWAYS to use `read_file` tool to read the skill's SKILL.md file
2. Carefully read the skill's documentation, steps, and examples
3. Follow the instructions in the SKILL.md, using Core Tools as directed
4. NEVER guess skill parameters or usage - always read the file first!

## Complete Example: Weather Query

**User**: "北京天气怎么样？"

**Step 1 - Read the skill documentation**:
```
read_file(path="data/skills/get_weather/SKILL.md")
```

**Step 2 - Fetch weather data** (as instructed in SKILL.md):
```
fetch_url(url="https://wttr.in/Beijing?format=j1")
```

**Step 3 - Parse and format the response**:
Extract temperature, weather description, humidity, and wind speed from the JSON response, then present it in a friendly format.

## Tool Usage Best Practices
- **terminal**: Use for file operations and system info (sandboxed)
- **python_repl**: Use for calculations and data processing
- **fetch_url**: Use to get web content (auto-cleans HTML)
- **read_file**: Use to read local files (especially SKILL.md)
- **search_knowledge_base**: Use to search documentation

## Error Handling
- If a tool fails, explain what went wrong
- Suggest alternative approaches
- Don't give up easily

## Remember
- Skills are your EXTENDED capabilities - use them when appropriate
- Always read SKILL.md before using a skill
- Skills help you accomplish tasks that require multiple steps
"""

    def _get_default_memory(self) -> str:
        """Get default MEMORY component content."""
        return """# Long-term Memory

## Previous Interactions
*(This section is populated with relevant information from previous conversations)*

## Learned Preferences
*(User preferences and patterns discovered over time)*

## Important Context
*(Key information that should be remembered across sessions)*

---

*Memory is managed automatically by the system. This section updates as you learn more about the user.*
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
