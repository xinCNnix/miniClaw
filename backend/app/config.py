"""
miniClaw Configuration Module

This module handles all configuration management using environment variables,
obfuscated storage, and pydantic-settings for type safety and validation.
"""

from functools import lru_cache
from typing import List, Dict, Any, Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "miniClaw"
    app_version: str = "0.1.0"
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8002
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:3002",
        "http://127.0.0.1:3003",
        "http://localhost:8000",  # Alternative frontend port
        "http://127.0.0.1:8000",
    ]

    # LLM Configuration
    llm_provider: Literal["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"] = "qwen"

    # OpenAI
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = Field(default="", env="OPENAI_MODEL")  # 留空由用户配置，避免硬编码过时模型
    openai_base_url: str = "https://api.openai.com/v1"

    # DeepSeek
    deepseek_api_key: str = Field(default="", env="DEEPSEEK_API_KEY")
    deepseek_model: str = Field(default="", env="DEEPSEEK_MODEL")  # 留空由用户配置
    deepseek_base_url: str = "https://api.deepseek.com"

    # Qwen (通义千问)
    qwen_api_key: str = Field(default="", env="QWEN_API_KEY")
    qwen_model: str = Field(default="", env="QWEN_MODEL")  # 留空由用户配置
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # Ollama (Local)
    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = Field(default="", env="OLLAMA_MODEL")  # 留空由用户配置

    # Claude (Anthropic) - Using OpenAI-compatible mode
    claude_api_key: str = Field(default="", env="CLAUDE_API_KEY")
    claude_model: str = Field(default="", env="CLAUDE_MODEL")  # 留空由用户配置
    claude_base_url: str = Field(default="https://api.anthropic.com", env="CLAUDE_BASE_URL")

    # Gemini (Google)
    gemini_api_key: str = Field(default="", env="GEMINI_API_KEY")
    gemini_model: str = Field(default="", env="GEMINI_MODEL")  # 留空由用户配置
    gemini_base_url: str = "https://generativelanguage.googleapis.com"

    # Custom OpenAI-compatible API
    custom_api_key: str = Field(default="", env="CUSTOM_API_KEY")
    custom_model: str = Field(default="", env="CUSTOM_MODEL")
    custom_base_url: str = Field(default="", env="CUSTOM_BASE_URL")

    # LangSmith Tracing (Optional)
    # ⚠️ 警告：启用 tracing 会将 API Key 和对话内容上传到 LangSmith 服务器
    # 仅在开发和调试时启用，生产环境务必保持为 false
    langchain_api_key: str = Field(default="", env="LANGCHAIN_API_KEY")
    langchain_tracing_v2: bool = False
    langchain_project: str = "mini-openclaw"

    # File Paths
    base_dir: str = "."
    data_dir: str = "data"
    knowledge_base_dir: str = "data/knowledge_base"
    sessions_dir: str = "data/sessions"
    skills_dir: str = "data/skills"
    vector_store_dir: str = "data/vector_store"
    workspace_dir: str = "workspace"

    # Tool Security
    terminal_root_dir: str = "."  # Restrict terminal commands to this directory
    terminal_blocked_commands: list[str] = [
        # Unix/Linux dangerous commands
        "rm -rf /",
        "rm -rf /.*",
        "rm -rf /*",
        "mkfs",
        "dd if=/dev/zero",
        "dd if=/dev/random",
        "dd if=/dev/urandom",
        ":(){ :|:& };:",  # Fork bomb
        "bomb() { bomb|bomb& }",
        "fork() { fork & }",
        "chmod 000",
        "chmod -r 000",
        "chmod -r 000 /",
        "chmod -r 000 /etc",
        "chmod -r 777 /etc",
        "chmod -r 777 /etc/shadow",
        "chown -r root:root",

        # Windows dangerous commands
        "format",  # Format disk
        "format c:",  # Format C: drive
        "format d:",  # Format D: drive
        "del /f /s /q",  # Force delete all files
        "del /f /q c:\\",  # Delete all files on C:
        "erase /f /s /q",  # Same as del
        "rd /s /q",  # Remove directory recursively
        "rmdir /s /q",  # Same as rd
        "shutdown /s",  # Shutdown computer
        "shutdown /r",  # Restart computer
        "shutdown /p",  # Shutdown without timeout
        "reg delete",  # Delete registry keys
        "reg delete hkey_local_machine",  # Delete system registry
        "taskkill /f",  # Force kill process
        "taskkill /f /im",  # Force kill by image name
        "bcdedit /delete",  # Delete boot entry
        "diskpart",  # Disk partition tool
        "fdisk",  # Disk partitioning (also on Windows)
        "chkdsk /f",  # Check disk with fix (can modify data)
        "sfc /scannow",  # System file checker (modifies system)
        "bootrec /fixmbr",  # Fix MBR (dangerous)
        "bootrec /fixboot",  # Fix boot sector (dangerous)

        # Cross-platform dangerous patterns
        "mv /",  # Move root directory
        "mv /*",  # Move all from root
        "cp /",  # Copy from root
        "cp /* /dev/null",  # Copy all to null
        "move /",  # Windows move command
        "move /*",  # Windows move all from root
    ]
    read_file_root_dir: str = "."  # Restrict file reading to this directory

    # Additional allowed directories for file operations
    allowed_write_dirs: list[str] = Field(
        default=[],
        description="Additional directories where python_repl can write files"
    )

    # Python REPL Configuration
    python_execution_mode: Literal["safe", "standard", "free"] = "standard"
    python_safe_timeout: int = 60
    python_standard_timeout: int = 300
    python_free_timeout: int = 1800
    python_safe_memory_ratio: float = 0.2
    python_standard_memory_ratio: float = 0.5
    python_free_memory_ratio: float = 0.8
    python_safe_max_operations: int = 1_000_000
    python_standard_max_operations: int = 10_000_000
    python_free_max_operations: int = 0  # 0 means unlimited
    python_monitor_interval: int = 5  # seconds
    python_warning_threshold: float = 0.7

    # RAG / Knowledge Base
    enable_rag: bool = True  # Enable RAG by default
    embedding_model: str = "text-embedding-ada-002"
    vector_store_type: Literal["chroma", "simple"] = "chroma"
    hybrid_search_alpha: float = 0.5  # Balance between BM25 and vector search
    retrieval_top_k: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 50
    max_file_size: int = 1024 * 1024 * 1024  # 1GB
    large_file_threshold: int = 100 * 1024 * 1024  # 100MB - require authorization for files larger than this
    allowed_file_types: list[str] = [
        # Text & Documentation
        '.txt', '.md', '.rst', '.log',
        # Web
        '.html', '.htm', '.xml',
        # Documents
        '.pdf', '.docx', '.doc',
        # Spreadsheets
        '.xlsx', '.xls', '.csv', '.json', '.jsonl',
        # Configuration
        '.yaml', '.yml', '.toml', '.ini', '.conf', '.cfg',
        # Code files
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.php', '.rb', '.cs', '.swift', '.kt', '.scala', '.sh', '.bash',
        # Data
        '.sql', '.graphql', '.proto',
        # Special files (no extension)
        'README', 'CHANGELOG', 'LICENSE', 'AUTHORS', 'CONTRIBUTING',
    ]
    max_batch_files: int = 20  # Max files per batch upload
    max_folder_depth: int = 5  # Max folder depth for folder upload
    embedding_fallback: Literal["ollama", "sentence-transformers", "disable"] = "sentence-transformers"

    # Embedding Model Configuration
    embedding_warmup_enabled: bool = True  # Enable startup warmup
    embedding_warmup_timeout: int = 60  # Warmup timeout (seconds)
    embedding_hf_endpoint: str = "https://hf-mirror.com"  # HuggingFace mirror
    embedding_hf_timeout: int = 20  # Single download timeout (seconds)
    embedding_hf_retries: int = 2  # Download retry count

    # Session Management
    session_timeout: int = 3600  # seconds
    max_message_history: int = 100

    # System Prompt
    max_prompt_length: int = 20000  # characters
    truncation_marker: str = "...[truncated]"

    # Agent Execution
    max_tool_rounds: int = 50  # Maximum rounds of tool calling (prevents infinite loops)
    enable_smart_stopping: bool = True  # Enable intelligent tool stopping (redundancy detection + sufficiency evaluation)
    redundancy_detection_window: int = 3  # Window size for detecting redundant tool calls
    sufficiency_evaluation_interval: int = 2  # Evaluate information sufficiency every N rounds

    # Memory System
    enable_memory_extraction: bool = True
    enable_semantic_search: bool = True
    enable_user_profile_learning: bool = True
    enable_long_term_memory: bool = True

    # Memory Extraction
    memory_extraction_interval: int = 5  # Extract every N messages
    memory_min_confidence: float = 0.6  # Minimum confidence for storing memories
    memory_max_conversations: int = 100  # Maximum conversations to keep indexed

    # User Profile
    user_profile_update_interval: int = 10  # Update USER.md every N memory extractions

    # Long-term Memory
    long_term_memory_max_items: int = 50  # Max items per section in MEMORY.md
    long_term_memory_prune_threshold: float = 0.3  # Prune memories below this confidence

    # SQLite Database Storage
    memory_db_path: str = "data/memory.db"  # SQLite database file path
    use_sqlite: bool = True  # Use SQLite for memory storage
    dual_write_mode: bool = False  # Write to both SQLite and JSON (transition period)

    # Markdown File Control
    md_user_max_items: int = 30  # Max items in USER.md
    md_memory_max_items: int = 50  # Max items per section in MEMORY.md
    md_user_include_days: int = 30  # USER.md includes memories from last N days
    md_memory_include_days: int = 90  # MEMORY.md includes memories from last N days
    md_sync_interval: int = 10  # Sync MD files every N memory writes
    md_min_confidence: float = 0.7  # Only include memories with confidence >= this in MD
    md_auto_sync: bool = True  # Automatically sync MD files after memory updates

    # Skills Dependency Management
    enable_skill_dependency_check: bool = True  # Enable skill dependency checking
    auto_install_python_dependencies: bool = True  # Auto-install Python dependencies
    skill_dependency_install_timeout: int = 300  # Max time (seconds) to install dependencies

    # Logging Configuration
    log_level: str = "INFO"  # Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_dir: str = "logs"  # Directory for log files
    log_to_file: bool = True  # Enable file logging
    log_to_console: bool = True  # Enable console logging
    log_max_bytes: int = 10 * 1024 * 1024  # Max log file size (10MB)
    log_backup_count: int = 5  # Number of backup files to keep
    log_format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"  # Log format
    debug_agent: bool = True  # Enable detailed agent execution logging


def _load_obfuscated_config() -> None:
    """
    Load API keys from obfuscated storage and set as environment variables.

    This is called before Settings initialization to populate environment
    variables with deobfuscated API keys.
    """
    try:
        from app.core.obfuscation import KeyObfuscator

        credentials = KeyObfuscator.load_credentials()

        # Set environment variables from obfuscated storage
        for provider, config in credentials.items():
            # Skip internal keys
            if provider.startswith("_"):
                continue

            # Map provider names to environment variable format
            provider_upper = provider.upper()

            if "api_key" in config:
                # Only set if not already in environment (env vars take precedence)
                env_key = f"{provider_upper}_API_KEY"
                if env_key not in os.environ:
                    os.environ[env_key] = config["api_key"]

            if "model" in config and config["model"]:
                env_key = f"{provider_upper}_MODEL"
                if env_key not in os.environ:
                    os.environ[env_key] = config["model"]

            if "base_url" in config and config["base_url"]:
                env_key = f"{provider_upper}_BASE_URL"
                if env_key not in os.environ:
                    os.environ[env_key] = config["base_url"]

        # Restore current provider choice if stored
        if "_current_provider" in credentials:
            provider = credentials["_current_provider"]
            if "LLM_PROVIDER" not in os.environ:
                os.environ["LLM_PROVIDER"] = provider

    except Exception:
        # Silently fail if obfuscated storage is corrupted or inaccessible
        # This allows fallback to environment variables
        pass


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    This function is cached to avoid recreating settings on every call.
    Use this to access settings throughout the application.
    """
    # Load obfuscated config before creating Settings
    _load_obfuscated_config()
    return Settings()


def clear_settings_cache() -> None:
    """
    Clear the cached Settings instance.

    Call this when configuration changes (provider switch, credential update).
    This ensures the next get_settings() call loads fresh configuration.
    """
    get_settings.cache_clear()


def get_settings_uncached() -> Settings:
    """
    Get a fresh Settings instance without using cache.

    Use this when you need the absolute latest configuration,
    such as in API endpoints that display current settings to users.
    """
    _load_obfuscated_config()
    return Settings()


def get_available_providers() -> List[Dict[str, Any]]:
    """
    Get list of all available LLM providers with their info.

    Returns:
        List of provider dictionaries with keys:
        - id: Provider ID (used in config)
        - name: Display name
        - default_model: Default model name
        - requires_api_key: Whether API key is required
        - description: Brief description
    """
    return [
        {
            "id": "openai",
            "name": "OpenAI",
            "default_model": "gpt-4o-mini",
            "requires_api_key": True,
            "description": "OpenAI GPT models (gpt-4o, gpt-4o-mini, etc.)",
        },
        {
            "id": "deepseek",
            "name": "DeepSeek",
            "default_model": "deepseek-chat",
            "requires_api_key": True,
            "description": "DeepSeek AI models (deepseek-chat, deepseek-coder)",
        },
        {
            "id": "qwen",
            "name": "通义千问 (Qwen)",
            "default_model": "qwen-plus",
            "requires_api_key": True,
            "description": "阿里云通义千问模型 (qwen-plus, qwen-turbo)",
        },
        {
            "id": "ollama",
            "name": "Ollama (本地)",
            "default_model": "qwen2.5",
            "requires_api_key": False,
            "description": "本地运行的模型 (需要安装 Ollama)",
        },
        {
            "id": "claude",
            "name": "Claude (Anthropic)",
            "default_model": "claude-3-5-sonnet-20241022",
            "requires_api_key": True,
            "description": "Anthropic Claude models",
        },
        {
            "id": "gemini",
            "name": "Gemini (Google)",
            "default_model": "gemini-pro",
            "requires_api_key": True,
            "description": "Google Gemini models",
        },
        {
            "id": "custom",
            "name": "自定义",
            "default_model": "",
            "requires_api_key": True,
            "description": "自定义 OpenAI 兼容 API",
        },
    ]


# Convenience exports
settings = get_settings()
