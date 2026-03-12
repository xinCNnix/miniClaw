"""
Tools Management Module

This module handles tool registration, validation, and management.
"""

from typing import List, Dict, Optional
from langchain_core.tools import BaseTool

from app.tools import CORE_TOOLS, get_tool_by_name


class ToolRegistry:
    """
    Registry for managing available tools.

    This class provides functionality to register, retrieve, and manage tools.
    """

    def __init__(self):
        """Initialize the tool registry."""
        self._tools: Dict[str, BaseTool] = {}
        self._register_core_tools()

    def _register_core_tools(self) -> None:
        """Register the 5 core tools."""
        for tool in CORE_TOOLS:
            self.register_tool(tool)

    def register_tool(self, tool: BaseTool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register

        Raises:
            ValueError: If tool name is already registered
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")

        self._tools[tool.name] = tool

    def unregister_tool(self, name: str) -> None:
        """
        Unregister a tool.

        Args:
            name: Tool name to unregister

        Raises:
            ValueError: If tool is not registered
        """
        if name not in self._tools:
            raise ValueError(f"Tool '{name}' is not registered")

        # Prevent unregistering core tools
        core_tool_names = [tool.name for tool in CORE_TOOLS]
        if name in core_tool_names:
            raise ValueError(f"Cannot unregister core tool '{name}'")

        del self._tools[name]

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None if not found
        """
        return self._tools.get(name)

    def get_all_tools(self) -> List[BaseTool]:
        """
        Get all registered tools.

        Returns:
            List of tool instances
        """
        return list(self._tools.values())

    def get_tool_names(self) -> List[str]:
        """
        Get all registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tools_info(self) -> List[Dict[str, str]]:
        """
        Get information about all tools.

        Returns:
            List of tool info dicts
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self._tools.values()
        ]

    def validate_tools(self) -> Dict[str, bool]:
        """
        Validate all registered tools.

        Returns:
            Dict mapping tool names to validation status
        """
        results = {}

        for name, tool in self._tools.items():
            try:
                # Check if tool has required attributes
                assert hasattr(tool, 'name'), f"Tool '{name}' missing 'name' attribute"
                assert hasattr(tool, 'description'), f"Tool '{name}' missing 'description' attribute"
                assert callable(tool._run), f"Tool '{name}' '_run' is not callable"

                # Try to get args schema
                schema = getattr(tool, 'args_schema', None)
                if schema is None:
                    # Tools should have args_schema for proper validation
                    results[name] = False
                    continue

                results[name] = True

            except Exception as e:
                print(f"Validation failed for tool '{name}': {e}")
                results[name] = False

        return results

    def get_tool_for_langchain(self, name: str) -> Optional[BaseTool]:
        """
        Get a tool formatted for LangChain.

        Args:
            name: Tool name

        Returns:
            Tool instance or None
        """
        tool = self.get_tool(name)

        if tool is None:
            return None

        # Ensure tool is properly configured for LangChain
        # This is where we could add wrappers or transformations if needed
        return tool


# Global tool registry instance
tool_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    """
    Get the global tool registry instance.

    Returns:
        ToolRegistry instance
    """
    return tool_registry


def get_registered_tools() -> List[BaseTool]:
    """
    Get all registered tools from the global registry.

    Returns:
        List of tool instances

    Examples:
        >>> from app.core.tools import get_registered_tools
        >>> tools = get_registered_tools()
        >>> for tool in tools:
        ...     print(f"{tool.name}: {tool.description[:50]}...")
    """
    return tool_registry.get_all_tools()


def validate_all_tools() -> Dict[str, bool]:
    """
    Validate all tools in the global registry.

    Returns:
        Dict mapping tool names to validation status

    Examples:
        >>> from app.core.tools import validate_all_tools
        >>> results = validate_all_tools()
        >>> for tool_name, is_valid in results.items():
        ...     status = "✓" if is_valid else "✗"
        ...     print(f"{status} {tool_name}")
    """
    return tool_registry.validate_tools()
