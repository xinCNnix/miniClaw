"""
Core Module

This module contains the core functionality of the miniClaw Agent system.

Components:
- Agent Manager: Creates and manages LangChain Agents
- LLM Provider: Multi-LLM support (OpenAI/DeepSeek/Qwen/Ollama)
- Tool Registry: Manages available tools
- Dream: Offline batch self-replay skill formation system
"""

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

    # Dream
    "run_dream",
    "build_dream_subgraph",
    "DreamConfig",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular dependencies at module load time."""
    _AGENT = {"AgentManager", "create_agent_manager"}
    _LLM = {"create_llm", "get_default_llm", "get_available_providers", "validate_provider_config"}
    _TOOLS = {"ToolRegistry", "tool_registry", "get_tool_registry", "get_registered_tools", "validate_all_tools"}
    _DREAM = {"run_dream", "build_dream_subgraph", "DreamConfig"}

    if name in _AGENT:
        from .agent import AgentManager, create_agent_manager
        return AgentManager if name == "AgentManager" else create_agent_manager
    if name in _LLM:
        from .llm import create_llm, get_default_llm, get_available_providers, validate_provider_config
        return {
            "create_llm": create_llm,
            "get_default_llm": get_default_llm,
            "get_available_providers": get_available_providers,
            "validate_provider_config": validate_provider_config,
        }[name]
    if name in _TOOLS:
        from .tools import ToolRegistry, tool_registry, get_tool_registry, get_registered_tools, validate_all_tools
        return {
            "ToolRegistry": ToolRegistry,
            "tool_registry": tool_registry,
            "get_tool_registry": get_tool_registry,
            "get_registered_tools": get_registered_tools,
            "validate_all_tools": validate_all_tools,
        }[name]
    if name in _DREAM:
        from .dream import run_dream, build_dream_subgraph, DreamConfig
        return {
            "run_dream": run_dream,
            "build_dream_subgraph": build_dream_subgraph,
            "DreamConfig": DreamConfig,
        }[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
