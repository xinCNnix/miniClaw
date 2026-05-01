/**
 * Internationalization configuration
 */

export const locales = ['zh', 'en'] as const;
export type Locale = (typeof locales)[number];

export const defaultLocale: Locale = 'en';

export const localeNames: Record<Locale, string> = {
  zh: '简体中文',
  en: 'English',
};

/**
 * Get translation for a given key and locale
 */
export function getTranslation(locale: Locale, key: string, params?: Record<string, string | number>): string {
  const translations = locale === 'zh' ? zhTranslations : enTranslations;
  const keys = key.split('.');
  let value: any = translations;

  for (const k of keys) {
    value = value?.[k];
  }

  if (typeof value !== 'string') {
    console.warn(`Translation missing for key: ${key}`);
    return key;
  }

  // Replace parameters in the translation string
  if (params) {
    return value.replace(/\{(\w+)\}/g, (_, paramKey) => params[paramKey]?.toString() || '');
  }

  return value;
}

/**
 * Chinese translations
 */
const zhTranslations = {
  // Settings Dialog
  settings: {
    title: '设置',
    llm_config: 'LLM 配置',
    skills_management: '技能管理',
    save: '保存',
    saving: '保存中...',
    cancel: '取消',
    close: '关闭',
    delete: '删除',
    add_skill: '添加技能',
    no_skills: '暂无技能',
    no_skills_desc: '点击"添加技能"安装新技能',
    skills_installed: '已安装技能',
    skills_installed_desc: '管理 Agent 可用的技能',
    enable: '启用',
    disable: '禁用',
    confirm_delete_skill: '确定要删除技能 "{name}" 吗？',
    config_saved: '配置已保存（已加密存储）',
    config_deleted: '{provider} 配置已删除',
    save_failed: '保存失败: {error}',
    delete_failed: '删除失败',
    enter_api_key: '请输入 API Key',
    configured_providers: '已配置的提供商',
    add_or_update_config: '添加或更新配置',
    configure_api_key: '配置 API Key',
    llm_provider: 'LLM 提供商',
    api_base_url: 'API Base URL',
    api_key: 'API Key',
    model_name: '模型名称',
    model_name_placeholder: '请输入模型名称（从服务商官网获取最新可用模型）',
    model_name_hint: '留空使用默认配置。建议查阅各服务商官网获取最新的可用模型列表。',
    security_protection: '安全保护：',
    security_info_1: '• API key 使用设备指纹混淆加密存储',
    security_info_2: '• Agent 工具（read_file、terminal）无法读取',
    security_info_3: '• 防止提示词注入泄露',
    encrypted_storage: '安全加密存储',
    gemini_format: 'Gemini 格式：AIza...',
    skills_hint: '提示：技能通过 Instruction-following 范式实现。每个技能是一个包含 SKILL.md 的文件夹。Agent 会阅读 SKILL.md 了解如何使用该技能。',
    security_warning: '安全警告',
    domain_warning: '检测到域名 {domain} 不在预置的可信服务商列表中。这不是预置的可信服务商，确认要使用此 API 吗？',
    allow_and_save: '允许并保存',
    claude_openai_mode: 'Claude 使用 OpenAI 兼容模式时，需要兼容的 API 端点',
    custom_api_url: '自定义 OpenAI 兼容 API 的完整 URL',
    provider_groups: {
      domestic: '国内服务商',
      openai_compatible: 'OpenAI 兼容',
      other: '其他服务商',
      local: '本地部署',
    },
    providers: {
      qwen: '通义千问 (Qwen)',
      deepseek: 'DeepSeek',
      openai: 'OpenAI (官方)',
      claude: 'Anthropic Claude (OpenAI 兼容模式)',
      custom: '自定义 OpenAI 兼容 API',
      gemini: 'Google Gemini',
      ollama: 'Ollama',
    },
  },
  // Language Switcher
  language: {
    title: '语言',
    current: '当前语言',
  },
  // Sidebar
  sidebar: {
    new_chat: '新建对话',
    new_conversation: '新对话',
    powered_by: '技术支持：LangChain & LlamaIndex',
  },
  // Tabbed Panel
  tabbed_panel: {
    editor: '编辑器',
    knowledge_base: '知识库',
  },
  // Editor Panel
  editor_panel: {
    title: '文件检查器',
    select_file_hint: '选择文件以查看',
    bytes: '字节',
  },
  // Knowledge Base Panel
  knowledge_base: {
    title: '知识库',
    document_count: '{count} 个文档',
    document_count_singular: '{count} 个文档',
    upload_area_title: '点击或拖拽上传',
    uploading: '正在上传 {filename}...',
    supported_formats: '支持格式：TXT, MD, PDF, DOCX（最大 10MB）',
    no_documents_title: '暂无文档',
    no_documents_hint: '上传文档开始构建您的知识库',
    chunks: '块',
    delete_confirm: '确定要删除文档 "{filename}" 吗？',
    delete_document: '删除文档',
    indexed_hint: '文档已建立索引，支持 RAG 搜索',
    error_unsupported_type: '不支持的文件类型：{ext}',
    error_file_too_large: '文件过大（最大 10MB）',
    error_upload_failed: '上传文档失败',
    error_load_failed: '加载文档失败',
    error_delete_failed: '删除文档失败',
    single_file: '单文件',
    batch_upload: '批量上传',
    folder_upload: '文件夹 (ZIP)',
    large_file_pending: '大文件上传等待中...',
    batch_upload_pending: '批量上传等待中：{count} 个文件',
    batch_upload_title: '点击或拖拽多个文件上传',
    folder_upload_title: '点击或拖拽 ZIP 文件上传文件夹',
    folder_upload_hint: 'ZIP 压缩包（最大 2GB，解压后最多 {max} 个文件）',
    batch_upload_hint: '最多 {max} 个文件，总大小 >100MB 需要授权',
    supported_formats_hint: '{count}+ 种格式支持（最大：1GB）',
    upload_error: '上传错误',
  },
  // Chat
  chat: {
    welcome_title: '欢迎使用 MiNiCLAW',
    welcome_subtitle: '您的可信赖 AI Agent 助手',
    try_asking: '尝试让我：',
    try_terminal: '执行终端命令',
    try_python: '运行 Python 代码',
    try_web: '获取和分析网页',
    try_kb: '搜索知识库',
    try_skills: '使用可用技能',
    type_message: '输入消息...',
    upload_file_title: '上传文件',
    upload_size_warning: '文件 \'{name}\' 大小为 {size}，上传可能较慢。是否继续？',
    upload_confirm: '确认上传',
    upload_cancel: '取消',
  },
  // Research Mode
  research_mode: {
    title: '深度研究模式',
    thinking_mode: '思考模式',
    branching_factor: '分支因子',
    thoughts_per_node: '个思路/节点',
    narrow: '窄',
    wide: '宽',
    search_depth: '搜索深度',
    depth_layers: '层',
    shallow: '浅',
    deep: '深',
    heuristic: {
      name: '启发式推理',
      name_en: 'Heuristic',
      short_desc: '快速探索，时间敏感',
      description: '快速启发式探索，适用于时间敏感的查询。{depth}层深度×{branching}宽度，{time}完成。'
    },
    analytical: {
      name: '分析式推理',
      name_en: 'Analytical',
      short_desc: '系统分析，平衡深度',
      description: '系统性分析，平衡深度与广度。{depth}层深度×{branching}宽度，{time}完成。'
    },
    exhaustive: {
      name: '穷尽式推理',
      name_en: 'Exhaustive',
      short_desc: '极限穷尽，深度研究',
      description: '深度探索所有可能性，适用于复杂研究。{depth}层深度×{branching}宽度，{time}完成。'
    },
    time_estimate: {
      very_fast: '约3-5分钟',
      fast: '约10-30分钟',
      medium: '约30-60分钟',
      slow: '约1-2小时',
      very_slow: '约2-10小时'
    }
  },
  // Deep Planning Mode
  deep_planning: {
    title: '深度规划模式',
  },
  // Thought Tree
  thought_tree: {
    waiting: '等待推理树...',
    step: '步骤 {step}/{total}',
    generating: '生成中...',
    evaluating: '评估中...',
    evaluated: '已评估',
    complete: '已完成',
    pending: '等待中...',
    score: '评分',
    tools: '{count} 个工具',
  },
  // PERV (Plan-Execute-Verify-Reflect)
  perv: {
    phase: {
      routing: '路由决策',
      planning: '规划',
      executing: '执行',
      verifying: '验证',
      replanning: '重新规划',
      done: '完成',
    },
    step_status: {
      success: '成功',
      fail: '失败',
      pending: '等待中',
    },
    verification: {
      pass: '通过',
      fail: '未通过',
      confidence: '置信度',
    },
    retry_count: '重试 {count} 次',
    skills_matched: '{matched}/{compiled} 技能已编译',
    risk_level: '风险等级',
    plan_steps: '{count} 个步骤',
  },
  // Common
  common: {
    loading: '加载中...',
    error: '错误',
    success: '成功',
    confirm: '确认',
    back: '返回',
    submit: '提交',
  },
};

/**
 * English translations
 */
const enTranslations = {
  // Settings Dialog
  settings: {
    title: 'Settings',
    llm_config: 'LLM Configuration',
    skills_management: 'Skills Management',
    save: 'Save',
    saving: 'Saving...',
    cancel: 'Cancel',
    close: 'Close',
    delete: 'Delete',
    add_skill: 'Add Skill',
    no_skills: 'No Skills',
    no_skills_desc: 'Click "Add Skill" to install new skills',
    skills_installed: 'Installed Skills',
    skills_installed_desc: 'Manage skills available to Agent',
    enable: 'Enable',
    disable: 'Disable',
    confirm_delete_skill: 'Are you sure you want to delete skill "{name}"?',
    config_saved: 'Configuration saved (encrypted storage)',
    config_deleted: '{provider} configuration deleted',
    save_failed: 'Save failed: {error}',
    delete_failed: 'Delete failed',
    enter_api_key: 'Please enter API Key',
    configured_providers: 'Configured Providers',
    add_or_update_config: 'Add or Update Configuration',
    configure_api_key: 'Configure API Key',
    llm_provider: 'LLM Provider',
    api_base_url: 'API Base URL',
    api_key: 'API Key',
    model_name: 'Model Name',
    model_name_placeholder: 'Enter model name (get the latest available models from provider website)',
    model_name_hint: 'Leave empty to use default configuration. Check provider websites for latest available model lists.',
    security_protection: 'Security Protection:',
    security_info_1: '• API key stored with device fingerprint obfuscation encryption',
    security_info_2: '• Agent tools (read_file, terminal) cannot read',
    security_info_3: '• Prevent prompt injection leaks',
    encrypted_storage: 'Secure encrypted storage',
    gemini_format: 'Gemini format: AIza...',
    skills_hint: 'Hint: Skills are implemented through Instruction-following paradigm. Each skill is a folder containing SKILL.md. Agent will read SKILL.md to understand how to use the skill.',
    security_warning: 'Security Warning',
    domain_warning: 'Detected domain {domain} is not in the preset trusted provider list. This is not a preset trusted provider. Are you sure you want to use this API?',
    allow_and_save: 'Allow and Save',
    claude_openai_mode: 'Claude requires compatible API endpoint when using OpenAI compatibility mode',
    custom_api_url: 'Full URL of custom OpenAI compatible API',
    provider_groups: {
      domestic: 'Domestic Providers',
      openai_compatible: 'OpenAI Compatible',
      other: 'Other Providers',
      local: 'Local Deployment',
    },
    providers: {
      qwen: 'Qwen (Tongyi Qianwen)',
      deepseek: 'DeepSeek',
      openai: 'OpenAI (Official)',
      claude: 'Anthropic Claude (OpenAI Compatible Mode)',
      custom: 'Custom OpenAI Compatible API',
      gemini: 'Google Gemini',
      ollama: 'Ollama',
    },
  },
  // Language Switcher
  language: {
    title: 'Language',
    current: 'Current Language',
  },
  // Sidebar
  sidebar: {
    new_chat: 'New Chat',
    new_conversation: 'New Conversation',
    powered_by: 'Powered by LangChain & LlamaIndex',
  },
  // Tabbed Panel
  tabbed_panel: {
    editor: 'Editor',
    knowledge_base: 'Knowledge Base',
  },
  // Editor Panel
  editor_panel: {
    title: 'File Inspector',
    select_file_hint: 'Select a file to view',
    bytes: 'bytes',
  },
  // Knowledge Base Panel
  knowledge_base: {
    title: 'Knowledge Base',
    document_count: '{count} document{plural}',
    document_count_singular: '{count} document',
    upload_area_title: 'Click or drag to upload',
    uploading: 'Uploading {filename}...',
    supported_formats: 'Supported: TXT, MD, PDF, DOCX (max 10MB)',
    no_documents_title: 'No documents yet',
    no_documents_hint: 'Upload documents to start building your knowledge base',
    chunks: 'chunks',
    delete_confirm: 'Are you sure you want to delete document "{filename}"?',
    delete_document: 'Delete document',
    indexed_hint: 'Documents are indexed for RAG search',
    error_unsupported_type: 'Unsupported file type: {ext}',
    error_file_too_large: 'File too large (max 10MB)',
    error_upload_failed: 'Failed to upload document',
    error_load_failed: 'Failed to load documents',
    error_delete_failed: 'Failed to delete document',
    single_file: 'Single File',
    batch_upload: 'Batch Upload',
    folder_upload: 'Folder (ZIP)',
    large_file_pending: 'Large file upload pending...',
    batch_upload_pending: 'Batch upload pending: {count} files',
    batch_upload_title: 'Click or drag multiple files to upload',
    folder_upload_title: 'Click or drag ZIP file to upload folder',
    folder_upload_hint: 'ZIP archive (Max 2GB, max {max} files after extraction)',
    batch_upload_hint: 'Max {max} files, total size >100MB requires authorization',
    supported_formats_hint: '{count}+ formats supported (Max: 1GB)',
    upload_error: 'Upload error',
  },
  // Chat
  chat: {
    welcome_title: 'Welcome to MiNiCLAW',
    welcome_subtitle: 'Your transparent AI Agent assistant',
    try_asking: 'Try asking me to:',
    try_terminal: 'Execute terminal commands',
    try_python: 'Run Python code',
    try_web: 'Fetch and analyze web pages',
    try_kb: 'Search the knowledge base',
    try_skills: 'Use available skills',
    type_message: 'Type your message...',
    upload_file_title: 'Upload file',
    upload_size_warning: 'File \'{name}\' is {size}, upload may be slow. Continue?',
    upload_confirm: 'Confirm upload',
    upload_cancel: 'Cancel',
  },
  // Research Mode
  research_mode: {
    title: 'Deep Research Mode',
    thinking_mode: 'Thinking Mode',
    branching_factor: 'Branching Factor',
    thoughts_per_node: 'thoughts/node',
    narrow: 'narrow',
    wide: 'wide',
    search_depth: 'Search Depth',
    depth_layers: 'layers',
    shallow: 'shallow',
    deep: 'deep',
    heuristic: {
      name: 'Heuristic Reasoning',
      name_en: 'Heuristic',
      short_desc: 'Fast exploration, time-sensitive',
      description: 'Fast heuristic exploration for time-sensitive queries. Depth {depth}×Branching {branching}, {time}.'
    },
    analytical: {
      name: 'Analytical Reasoning',
      name_en: 'Analytical',
      short_desc: 'Systematic analysis, balanced depth',
      description: 'Systematic analysis balancing depth and breadth. Depth {depth}×Branching {branching}, {time}.'
    },
    exhaustive: {
      name: 'Exhaustive Reasoning',
      name_en: 'Exhaustive',
      short_desc: 'Exhaustive exploration, deep research',
      description: 'Deep exploration of all possibilities for complex research. Depth {depth}×Branching {branching}, {time}.'
    },
    time_estimate: {
      very_fast: '3-5 minutes',
      fast: '10-30 minutes',
      medium: '30-60 minutes',
      slow: '1-2 hours',
      very_slow: '2-10 hours'
    }
  },
  // Deep Planning Mode
  deep_planning: {
    title: 'Deep Planning Mode',
  },
  // Thought Tree
  thought_tree: {
    waiting: 'Waiting for reasoning tree...',
    step: 'Step {step}/{total}',
    generating: 'Generating...',
    evaluating: 'Evaluating...',
    evaluated: 'Evaluated',
    complete: 'Complete',
    pending: 'Pending...',
    score: 'Score',
    tools: '{count} tools',
  },
  // PERV (Plan-Execute-Verify-Reflect)
  perv: {
    phase: {
      routing: 'Routing',
      planning: 'Planning',
      executing: 'Executing',
      verifying: 'Verifying',
      replanning: 'Replanning',
      done: 'Done',
    },
    step_status: {
      success: 'Success',
      fail: 'Failed',
      pending: 'Pending',
    },
    verification: {
      pass: 'Pass',
      fail: 'Fail',
      confidence: 'Confidence',
    },
    retry_count: 'Retry #{count}',
    skills_matched: '{matched}/{compiled} skills compiled',
    risk_level: 'Risk Level',
    plan_steps: '{count} steps',
  },
  // Common
  common: {
    loading: 'Loading...',
    error: 'Error',
    success: 'Success',
    confirm: 'Confirm',
    back: 'Back',
    submit: 'Submit',
  },
};

/**
 * Translation hook
 */
export function useTranslations(locale: Locale) {
  return {
    t: (key: string, params?: Record<string, string | number>) => getTranslation(locale, key, params),
    locale,
  };
}
