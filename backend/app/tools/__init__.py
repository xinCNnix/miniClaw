"""
Core Tools Module

This module provides the 6 core tools used by the miniClaw Agent.

Available tools:
- terminal: Execute shell commands safely
- python_repl: Execute Python code
- fetch_url: Fetch and clean web content
- read_file: Read local files safely
- write_file: Write content to local files safely
- search_kb: Search knowledge base (RAG)
"""

from .terminal import terminal_tool
from .python_repl import python_repl_tool
from .fetch_url import fetch_url_tool
from .read_file import read_file_tool
from .write_file import write_file_tool
from .search_kb import search_kb_tool

__all__ = [
    "terminal_tool",
    "python_repl_tool",
    "fetch_url_tool",
    "read_file_tool",
    "write_file_tool",
    "search_kb_tool",
]

# List of all tool instances for easy access
CORE_TOOLS = [
    terminal_tool,
    python_repl_tool,
    fetch_url_tool,
    read_file_tool,
    write_file_tool,
    search_kb_tool,
]


def get_all_tools():
    """
    Get all core tools.

    Returns:
        List of tool instances
    """
    return CORE_TOOLS


def get_tool_by_name(name: str):
    """
    Get a specific tool by name.

    Args:
        name: Tool name (terminal, python_repl, fetch_url, read_file, search_kb)

    Returns:
        Tool instance or None if not found
    """
    tool_map = {tool.name: tool for tool in CORE_TOOLS}
    return tool_map.get(name)
