"""
miniClaw Configuration Module

This module handles all configuration management using environment variables,
obfuscated storage, and pydantic-settings for type safety and validation.
"""

from typing import List, Dict, Any, Literal, Optional
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import os
from dataclasses import dataclass


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class LLMConfig:
    """
    单个 LLM 配置（不包含明文 API Key）

    注意：此类用于后端内部使用，包含明文 API Key 仅用于 LLM 初始化
    前端永远不应该接触到明文 Key
    """
    id: str
    provider: str
    name: str
    model: str
    base_url: str
    api_key: str  # 仅在后端内存中使用，不发送到前端

    def to_dict(self, include_api_key: bool = False) -> Dict[str, Any]:
        """转换为字典（前端显示时不包含 API Key）"""
        data = {
            "id": self.id,
            "provider": self.provider,
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
        }

        if include_api_key:
            data["api_key"] = self.api_key
        else:
            # 前端显示：只返回脱敏信息
            data["has_api_key"] = bool(self.api_key)
            data["api_key_preview"] = f"{self.api_key[:8]}***" if self.api_key else ""

        return data


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
    llm_provider: Literal["openai", "deepseek", "qwen", "ollama", "claude", "gemini", "custom"] = Field(default="qwen", env="LLM_PROVIDER")

    # OpenAI
    openai_api_key: str = Field(default="", env="OPENAI_API_KEY")
    openai_model: str = Field(default="", env="OPENAI_MODEL")  # 留空由用户配置，避免硬编码过时模型
    openai_base_url: str = Field(default="https://api.openai.com/v1", env="OPENAI_BASE_URL")

    # DeepSeek
    deepseek_api_key: str = Field(default="", env="DEEPSEEK_API_KEY")
    deepseek_model: str = Field(default="", env="DEEPSEEK_MODEL")  # 留空由用户配置
    deepseek_base_url: str = Field(default="https://api.deepseek.com", env="DEEPSEEK_BASE_URL")

    # Qwen (通义千问)
    qwen_api_key: str = Field(default="", env="QWEN_API_KEY")
    qwen_model: str = Field(default="", env="QWEN_MODEL")  # 留空由用户配置
    qwen_base_url: str = Field(default="https://dashscope.aliyuncs.com/compatible-mode/v1", env="QWEN_BASE_URL")

    # Ollama (Local)
    ollama_base_url: str = Field(default="http://localhost:11434/v1", env="OLLAMA_BASE_URL")
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

    # Tree of Thoughts Configuration
    enable_tot: bool = True
    # Default values (will be overridden by thinking_mode)
    tot_max_depth: int = 2
    tot_branching_factor: int = 3
    tot_quality_threshold: float = 6.0
    tot_auto_enable_keywords: list[str] = [
        "deep research",
        "comprehensive analysis",
        "detailed investigation",
        "thorough review",
        "in-depth study"
    ]
    tot_checkpoint_path: str = "data/tot_checkpoints.db"

    # Deep Research Configuration
    enable_deep_research: bool = True
    research_mode: Literal["heuristic", "analytical", "exhaustive"] = "heuristic"

    # Thinking Mode Configurations
    # heuristic (启发式推理): 3层深度 × 3层宽度 = 约18个节点，兼顾覆盖和深度
    # analytical (分析式推理): 4层深度 × 4层宽度 = 约48个节点，系统性分析
    # exhaustive (穷尽式推理): 8层深度 × 4层宽度 = 约90个节点，深度优先搜索
    # 注：深度比宽度更能逼近最优解，宽度超过3后冗余分支增多、收益递减
    thinking_modes: dict = {
        "heuristic": {
            "depth": 3,  # 原 2 → 3: 增加 1 层深度，成本仅增 50%
            "branching": 3,
            "timeout": 240,  # 原 180 → 240: 配合深度增加适当延长
            "name": "启发式推理 (Heuristic Reasoning)",
            "name_en": "Heuristic Reasoning",
            "description": "快速探索问题核心，适用于时间敏感的查询",
            "icon": "⚡",
            "beam_search": True,  # Global Beam 束搜索，False 退回贪心模式
            "max_tool_steps_per_node": 5,  # 执行节点局部循环最大步数
        },
        "analytical": {
            "depth": 4,
            "branching": 4,
            "timeout": 1800,
            "name": "分析式推理 (Analytical Reasoning)",
            "name_en": "Analytical Reasoning",
            "description": "平衡深度与广度，适用于复杂问题分析",
            "icon": "🔬",
            "beam_search": True,
            "max_tool_steps_per_node": 5,
        },
        "exhaustive": {
            "depth": 8,  # 原 7 → 8: 更深的搜索
            "branching": 4,  # 原 6 → 4: 降低宽度减少冗余分支，省下 token 投入深度
            "timeout": 36000,
            "name": "穷尽式推理 (Exhaustive Reasoning)",
            "name_en": "Exhaustive Reasoning",
            "description": "深度优先穷尽搜索，适用于深度研究",
            "icon": "🌌",
            "beam_search": True,
            "max_tool_steps_per_node": 5,
        }
    }

    research_sources_priority: list[str] = ["knowledge_base", "arxiv", "web"]

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

    # LLM Request Timeout
    llm_request_timeout: int = 120  # 单次 LLM API 调用超时（秒），防止 API 无响应时永久挂起

    # Agent Execution
    max_tool_rounds: int = 50  # Maximum rounds of tool calling (prevents infinite loops)
    enable_smart_stopping: bool = True  # Enable intelligent tool stopping (redundancy detection + sufficiency evaluation)
    redundancy_detection_window: int = 3  # Window size for detecting redundant tool calls
    sufficiency_evaluation_interval: int = 5  # Evaluate information sufficiency every N rounds (increased from 2)

    # Performance Optimization: Caching
    enable_semantic_search_cache: bool = True
    semantic_search_cache_ttl: int = 300  # 5 minutes
    enable_context_cache: bool = True
    context_cache_size: int = 64
    enable_prompt_cache: bool = True

    # Performance Optimization: Parallel Tool Execution
    enable_parallel_tool_execution: bool = True
    enable_auto_fallback: bool = True  # Enable automatic fallback to sequential
    parallel_tool_dependency_detection: bool = True  # Enable dependency detection
    max_concurrent_tools: int = 5  # Maximum concurrent tools in parallel

    # Performance Optimization: Streaming Response
    enable_streaming_response: bool = True  # Enable streaming response for real-time output
    streaming_chunk_size: int = 512  # Characters per chunk

    # Performance Optimization: Prompt Compression
    enable_smart_truncation: bool = True
    max_prompt_tokens: int = 15000  # Reduced from 20000
    prompt_token_budget: dict = {
        "SKILLS_SNAPSHOT": 2000,
        "AGENTS": 1500,
        "WIKI_MEMORY": 1500,
        "CONVERSATION_CONTEXT": 3000,
        "SEMANTIC_HISTORY": 2000,
        "USER": 1000,
        "SOUL": 500,
        "IDENTITY": 500,
    }

    # Memory System
    enable_memory_extraction: bool = True
    enable_semantic_search: bool = True
    enable_user_profile_learning: bool = True
    enable_long_term_memory: bool = True

    # Memory Extraction
    memory_extraction_interval: int = 5  # Extract every N messages
    memory_min_confidence: float = 0.6  # Minimum confidence for storing memories
    memory_max_conversations: int = 100  # Maximum conversations to keep indexed
    memory_extraction_max_retries: int = 2  # Max retries when JSON parsing fails

    # Vector Indexing
    vector_indexing_max_retries: int = 3  # Max retries when embedding model not ready
    vector_indexing_retry_delay: float = 2.0  # Initial retry delay in seconds

    # User Profile
    user_profile_update_interval: int = 10  # Update USER.md every N memory extractions

    # Long-term Memory
    long_term_memory_max_items: int = 50  # Max items per section in MEMORY.md
    long_term_memory_prune_threshold: float = 0.3  # Prune memories below this confidence

    # SQLite Database Storage
    memory_db_path: str = "data/memory.db"  # SQLite database file path
    use_sqlite: bool = True  # Use SQLite for memory storage
    dual_write_mode: bool = True  # Write to both SQLite and JSON (transition period)

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

    # === Reflection System ===
    enable_agent_reflection: bool = True
    agent_reflection_quality_threshold: float = 6.0
    evaluation_cache_enabled: bool = True
    enable_reflection_learning: bool = True

    # === PERV Enhancement ===
    perv_router_enabled: bool = True
    perv_enable_post_learning: bool = True
    perv_enable_pattern_retrieval: bool = True
    perv_enable_strategy_injection: bool = True
    perv_enable_semantic_history: bool = True

    # === Meta Policy & TCA ===
    enable_meta_policy: bool = True
    enable_tca: bool = True

    # TCA model architecture
    tca_embed_dim: int = 384
    tca_hidden_dim: int = 256
    tca_num_heads: int = 4
    tca_num_layers: int = 4
    tca_max_subtasks: int = 5
    tca_learning_rate: float = 5e-4
    tca_training_data_dir: str = "data/complexity_training"
    tca_decompose_threshold: float = 0.5
    tca_model_path: str = "data/complexity_training/tca_model.pth"

    # === Auto Learning ===
    pattern_embedder_model_name: str = "all-MiniLM-L6-v2"
    pattern_storage_path: str = "data/patterns"
    enable_rl_training: bool = True
    rl_target_update_freq: int = 100
    rl_tau: float = 0.005
    rl_transformer_lr: float = 1e-4
    rl_mlp_lr: float = 3e-4
    rl_kl_coef: float = 0.1
    rl_prompt_consistency_coef: float = 0.05
    rl_batch_size: int = 32
    rl_gradient_clip: float = 1.0
    enable_neural_strategy: bool = True
    neural_strategy_auto_transition: bool = True

    # === Memory Retriever ===
    enable_kg: bool = True
    # kg_store_backend: Literal["memory", "neo4j"] = "memory"  # BUG: get_kg_store() checks "sqlite"
    kg_store_backend: Literal["sqlite", "neo4j"] = "sqlite"   # FIXED: match get_kg_store() logic
    kg_max_triples_per_turn: int = 10
    kg_confidence_threshold: float = 0.5
    similarity_threshold: float = 0.7
    similarity_block_threshold: float = 0.95

    # === LLM Wiki ===
    enable_wiki: bool = True
    wiki_pages_dir: str = "data/wiki/pages"
    wiki_max_page_size: int = 5000
    wiki_evidence_required: bool = True
    wiki_write_threshold: float = 0.7

    # === Memory Engine (Phase 2) ===
    enable_memory_engine: bool = False  # Master switch: use LangGraph engine path

    # === EventLog (Phase 2 — 红线1) ===
    enable_event_log: bool = False
    event_log_max_payload_size: int = 10000  # Max payload JSON size in bytes

    # === EntityProfile (Phase 3) ===
    enable_entity_profile: bool = False

    # === Case Memory (Phase 3) ===
    enable_case_memory: bool = False
    case_memory_min_success_score: float = 0.5
    case_memory_max_cases: int = 1000

    # === Procedural Memory (Phase 3) ===
    enable_procedural_memory: bool = False

    # === Decay & Cleanup (Phase 4 — 红线4) ===
    memory_ttl_default_days: int = 90          # Default TTL for memories
    memory_decay_cron_hours: int = 24           # Decay cycle interval
    memory_decay_factor: float = 0.01           # exp(-factor * days_old)
    memory_prune_threshold: float = 0.1         # Vectors below this score get pruned

    # === Session Retention (Phase 4 — 红线4 Session cleanup) ===
    session_retention_days: int = 30            # Session file retention period
    session_archive_on_delete: bool = True      # Archive to EventLog before deletion


def _load_obfuscated_config() -> None:
    """
    Load API keys from obfuscated storage and set as environment variables.

    支持新旧两种配置格式。

    优先级：加密存储 > 环境变量 > 默认值
    """
    try:
        from app.core.obfuscation import KeyObfuscator

        credentials = KeyObfuscator.load_credentials()

        # 检查是否是新格式（多 LLM 支持）
        if "llms" in credentials:
            # 新格式：多 LLM 配置
            current_llm_id = credentials.get("current_llm_id", "qwen-default")
            llms = credentials.get("llms", {})

            # 设置当前 LLM 的环境变量（兼容性）
            if current_llm_id in llms:
                current_llm = llms[current_llm_id]
                provider = current_llm.get("provider", "custom")
                os.environ["LLM_PROVIDER"] = provider

                if "api_key" in current_llm:
                    # 尝试解密
                    encrypted_key = current_llm["api_key"]
                    decrypted = KeyObfuscator.deobfuscate(encrypted_key)
                    api_key = decrypted if decrypted else encrypted_key

                    env_key = f"{provider.upper()}_API_KEY"
                    os.environ[env_key] = api_key

                if "model" in current_llm:
                    env_key = f"{provider.upper()}_MODEL"
                    os.environ[env_key] = current_llm["model"]

                if "base_url" in current_llm:
                    env_key = f"{provider.upper()}_BASE_URL"
                    os.environ[env_key] = current_llm["base_url"]
        else:
            # 旧格式：单一提供商配置（兼容性）
            for provider, config in credentials.items():
                if provider.startswith("_"):
                    continue

                provider_upper = provider.upper()

                if "api_key" in config:
                    env_key = f"{provider_upper}_API_KEY"
                    os.environ[env_key] = config["api_key"]

                if "model" in config and config["model"]:
                    env_key = f"{provider_upper}_MODEL"
                    os.environ[env_key] = config["model"]

                if "base_url" in config and config["base_url"]:
                    env_key = f"{provider_upper}_BASE_URL"
                    os.environ[env_key] = config["base_url"]

            if "_current_provider" in credentials:
                provider = credentials["_current_provider"]
                os.environ["LLM_PROVIDER"] = provider

    except Exception:
        # Silently fail - allows fallback to environment variables
        pass


def get_settings() -> Settings:
    """
    Get settings instance (always fresh, no caching).

    每次调用都重新加载配置，确保前端设置与后端使用一致。
    """
    import logging
    _load_obfuscated_config()
    s = Settings()
    logger = logging.getLogger(__name__)
    logger.info(
        f"[config] Features: reflection={s.enable_agent_reflection}, "
        f"perv_router={s.perv_router_enabled}, meta_policy={s.enable_meta_policy}, "
        f"tca={s.enable_tca}, rl_training={s.enable_rl_training}, "
        f"neural_strategy={s.enable_neural_strategy}, kg={s.enable_kg}"
    )
    return s


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
