"""
Skills Module

This module provides the Skills system for the miniClaw Agent.

Components:
- Bootstrap: Generates SKILLS_SNAPSHOT.md
- Loader: Loads skills from file system
- Executor: Executes skills using Instruction-following paradigm
"""

from .bootstrap import (
    SkillsBootstrap,
    SkillMetadata,
    bootstrap_skills,
    generate_skills_snapshot,
)

from .loader import (
    SkillLoader,
    get_skill_loader,
    load_skill_content,
)

from .executor import (
    SkillExecutor,
    get_skill_executor,
)

__all__ = [
    # Bootstrap
    "SkillsBootstrap",
    "SkillMetadata",
    "bootstrap_skills",
    "generate_skills_snapshot",

    # Loader
    "SkillLoader",
    "get_skill_loader",
    "load_skill_content",

    # Executor
    "SkillExecutor",
    "get_skill_executor",
]
