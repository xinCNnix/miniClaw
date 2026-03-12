"""
Core Module

This module contains the core functionality of the miniClaw Agent system.

Components:
- Agent Manager: Creates and manages LangChain Agents
- LLM Provider: Multi-LLM support (OpenAI/DeepSeek/Qwen/Ollama)
- Tool Registry: Manages available tools
"""

from .agent import (
    AgentManager,
    create_agent_manager,
)

from .llm import (
    create_llm,
    get_default_llm,
    get_available_providers,
    validate_provider_config,
)

from .tools import (
    ToolRegistry,
    tool_registry,
    get_tool_registry,
    get_registered_tools,
    validate_all_tools,
)

__all__ = [
    # Agent
    "AgentManager",
    "create_agent_manager",

    # LLM
    "create_llm",
    "get_default_llm",
    "get_available_providers",
    "validate_provider_config",

    # Tools
    "ToolRegistry",
    "tool_registry",
    "get_tool_registry",
    "get_registered_tools",
    "validate_all_tools",
]
