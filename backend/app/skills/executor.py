"""
Skills Executor Module

This module handles the execution of Skills following the Instruction-following paradigm.
"""

import re
from typing import Dict, Any, Optional, List
from pathlib import Path

from app.skills.loader import load_skill_content, get_skill_loader
from app.core.tools import get_tool_registry
from app.config import get_settings


class SkillExecutor:
    """
    Executor for Skills using Instruction-following paradigm.

    The Agent doesn't call skills directly as functions. Instead:
    1. Agent reads the SKILL.md file
    2. Agent parses and understands the instructions
    3. Agent executes the instructions using Core Tools
    """

    def __init__(self):
        """Initialize the skill executor."""
        self.tool_registry = get_tool_registry()
        self.loader = get_skill_loader()

    def parse_skill_instructions(self, skill_content: str) -> Dict[str, Any]:
        """
        Parse instructions from SKILL.md content.

        Args:
            skill_content: Full content of SKILL.md

        Returns:
            Dict containing parsed instructions

        The parsed structure includes:
        - name: Skill name
        - description: Skill description
        - steps: List of execution steps
        - examples: List of examples (if any)
        """
        # Split frontmatter and content
        if skill_content.startswith("---"):
            parts = skill_content.split("---", 2)
            if len(parts) >= 3:
                frontmatter_text = parts[1]
                main_content = parts[2].strip()
            else:
                main_content = skill_content
        else:
            main_content = skill_content

        # Parse frontmatter for metadata
        import yaml
        metadata = {}
        if skill_content.startswith("---"):
            try:
                parts = skill_content.split("---", 2)
                if len(parts) >= 2:
                    metadata = yaml.safe_load(parts[1]) or {}
            except:
                pass

        result = {
            "name": metadata.get("name", "unknown"),
            "description": metadata.get("description", ""),
            "content": main_content,
            "steps": self._extract_steps(main_content),
            "examples": self._extract_examples(main_content),
        }

        return result

    def _extract_steps(self, content: str) -> List[Dict[str, str]]:
        """
        Extract execution steps from skill content.

        Args:
            content: Skill content

        Returns:
            List of step dicts

        Steps can be in various formats:
        - Numbered lists (1., 2., 3.)
        - Bullet points with action verbs
        - ## Sections with instructions
        """
        steps = []

        # Try to find numbered steps
        numbered_pattern = r'^(\d+)\.\s+(.+?)$'
        lines = content.split("\n")

        current_step = None
        step_number = 0

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Check for numbered step
            match = re.match(numbered_pattern, line)
            if match:
                if current_step:
                    steps.append(current_step)

                step_number += 1
                current_step = {
                    "number": step_number,
                    "instruction": match.group(2),
                    "raw": line,
                }
            elif current_step:
                # Continuation of current step
                current_step["instruction"] += " " + line

        if current_step:
            steps.append(current_step)

        # If no numbered steps found, try to extract from sections
        if not steps:
            sections = re.split(r'^##+', content, flags=re.MULTILINE)
            for section in sections:
                section = section.strip()
                if section:
                    steps.append({
                        "number": len(steps) + 1,
                        "instruction": section,
                        "raw": section,
                    })

        return steps

    def _extract_examples(self, content: str) -> List[str]:
        """
        Extract examples from skill content.

        Args:
            content: Skill content

        Returns:
            List of example strings
        """
        examples = []

        # Look for code blocks
        code_blocks = re.findall(r'```(?:\w+)?\n(.*?)```', content, re.DOTALL)

        for block in code_blocks:
            if block.strip():
                examples.append(block.strip())

        # Look for "Example:" sections
        example_sections = re.split(r'Example\s*\d*:', content, flags=re.IGNORECASE)

        for section in example_sections[1:]:  # Skip first (before "Example:")
            section = section.strip()
            if section and len(section) < 500:  # Reasonable example length
                examples.append(section)

        return examples

    def execute_skill(
        self,
        skill_name: str,
        user_input: str = "",
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """
        Execute a skill (prepare instructions for Agent).

        Note: This doesn't actually execute the skill. Instead, it prepares
        the instructions that the Agent will follow. The actual execution
        is done by the Agent using Core Tools.

        Args:
            skill_name: Name of the skill to execute
            user_input: User's input/request
            context: Additional context (optional)

        Returns:
            Dict containing:
            - skill_name: Name of the skill
            - instructions: Parsed instructions
            - file_path: Path to SKILL.md
            - ready: Whether skill is ready to use

        Examples:
            >>> executor = SkillExecutor()
            >>> result = executor.execute_skill("get_weather", "北京天气")
            >>> print(result['instructions'])
        """
        # Get skill content
        skill_content = load_skill_content(skill_name)

        if skill_content is None:
            return {
                "skill_name": skill_name,
                "ready": False,
                "error": f"Skill '{skill_name}' not found",
            }

        # Parse instructions
        instructions = self.parse_skill_instructions(skill_content)

        # Get file path
        skill_path = self.loader.get_skill_path(skill_name)

        return {
            "skill_name": skill_name,
            "instructions": instructions,
            "file_path": str(skill_path) if skill_path else None,
            "ready": True,
            "context": context or {},
        }

    def format_skill_for_agent(
        self,
        skill_name: str,
        user_input: str = "",
    ) -> str:
        """
        Format skill information for the Agent.

        This creates a message that tells the Agent how to use the skill.

        Args:
            skill_name: Name of the skill
            user_input: User's input

        Returns:
            Formatted message for Agent

        Examples:
            >>> executor = SkillExecutor()
            >>> message = executor.format_skill_for_agent("get_weather")
            >>> print(message)
        """
        result = self.execute_skill(skill_name, user_input)

        if not result["ready"]:
            return f"Error: {result.get('error', 'Unknown error')}"

        instructions = result["instructions"]
        file_path = result["file_path"]

        # Create message for Agent
        message_parts = [
            f"To use the '{skill_name}' skill, follow these steps:",
            "",
            f"1. First, read the skill documentation:",
            f"   read_file(path=\"{file_path}\")",
            "",
            "2. Understand the instructions in the SKILL.md file",
            "",
            "3. Execute the instructions using available Core Tools:",
            "   - terminal: Execute shell commands",
            "   - python_repl: Run Python code",
            "   - fetch_url: Fetch web content",
            "   - read_file: Read files",
            "   - search_knowledge_base: Search knowledge base",
            "",
            f"4. Use the skill to: {user_input}",
        ]

        return "\n".join(message_parts)

    def validate_skill_execution(
        self,
        skill_name: str,
        available_tools: List[str],
    ) -> tuple[bool, str]:
        """
        Validate if a skill can be executed with available tools.

        Args:
            skill_name: Name of the skill
            available_tools: List of available tool names

        Returns:
            Tuple of (can_execute, message)

        Examples:
            >>> executor = SkillExecutor()
            >>> can_exec, msg = executor.validate_skill_execution(
            ...     "get_weather",
            ...     ["terminal", "fetch_url", "read_file"]
            ... )
            >>> print(f"Can execute: {can_exec}, Message: {msg}")
        """
        skill_content = load_skill_content(skill_name)

        if skill_content is None:
            return False, f"Skill '{skill_name}' not found"

        instructions = self.parse_skill_instructions(skill_content)

        # Check if skill instructions reference tools
        required_tools = set()

        for step in instructions["steps"]:
            instruction = step["instruction"].lower()

            # Check for tool references
            for tool in available_tools:
                if tool in instruction:
                    required_tools.add(tool)

        # Special case: if no tools are mentioned, assume read_file is needed
        # (for reading the SKILL.md itself)
        if not required_tools:
            required_tools.add("read_file")

        return True, f"Skill requires tools: {', '.join(required_tools)}"


def get_skill_executor() -> SkillExecutor:
    """
    Get the global skill executor instance.

    Returns:
        SkillExecutor instance

    Examples:
        >>> from app.skills.executor import get_skill_executor
        >>> executor = get_skill_executor()
        >>> result = executor.execute_skill("get_weather")
    """
    return SkillExecutor()
