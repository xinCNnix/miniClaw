# miniClaw 系统架构文档

## 一、架构概述

miniClaw 采用前后端分离架构，后端提供纯 API 服务，前端为 IDE 风格的单页应用。

### 架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         Frontend (Next.js)                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                  │
│  │ Sidebar  │  │ ChatArea │  │  Editor  │                  │
│  │ (导航)   │  │ (对话)   │  │(Monaco)  │                  │
│  └──────────┘  └──────────┘  └──────────┘                  │
└───────────────────────────┬─────────────────────────────────┘
                            │ SSE / HTTP
┌───────────────────────────┴─────────────────────────────────┐
│                    Backend (FastAPI)                        │
│  ┌────────────────────────────────────────────────────┐    │
│  │                  API Layer                          │    │
│  │  /api/chat (SSE)  /api/files  /api/sessions       │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │                 Core Layer                         │    │
│  │  Agent Manager | Skills Bootstrap | Memory        │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │                  Tools Layer                       │    │
│  │  terminal | python_repl | fetch_url | read_file   │    │
│  │  search_knowledge_base                             │    │
│  └────────────────────────────────────────────────────┘    │
│  ┌────────────────────────────────────────────────────┐    │
│  │                 LLM Layer                          │    │
│  │  LangChain Agent (create_agent)                   │    │
│  │  Multi-LLM Support (Qwen/OpenAI/DeepSeek)         │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            │
┌───────────────────────────┴─────────────────────────────────┐
│                    Local File System                        │
│  knowledge/ | sessions/ | skills/ | vector_store/           │
└───────────────────────────────────────────────────────────────┘
```

## 二、技术栈架构

### 后端架构

```
┌────────────────────────────────────────┐
│          Application Layer             │
│  FastAPI (port 8002)                   │
│  - RESTful API                         │
│  - SSE Streaming                       │
│  - CORS Middleware                     │
└──────────────┬─────────────────────────┘
               │
┌──────────────┴─────────────────────────┐
│         Business Logic Layer           │
│  ┌──────────────────────────────────┐  │
│  │   Core Modules                   │  │
│  │   - Agent Manager                │  │
│  │   - LLM Provider                 │  │
│  │   - Tool Registry                │  │
│  └──────────────────────────────────┘  │
│  ┌──────────────────────────────────┐  │
│  │   Skills System                  │  │
│  │   - Bootstrap (Snapshot gen)     │  │
│  │   - Loader (Dynamic import)      │  │
│  │   - Executor (Instruction-follow)│  │
│  └──────────────────────────────────┘  │
│  ┌──────────────────────────────────┐  │
│  │   Memory Management              │  │
│  │   - Prompt Builder (6 components)│  │
│  │   - Session Store                │  │
│  │   - Truncation Strategy          │  │
│  └──────────────────────────────────┘  │
└──────────────┬─────────────────────────┘
               │
┌──────────────┴─────────────────────────┐
│          Data Access Layer            │
│  - File System (Markdown/JSON)        │
│  - ChromaDB (Vector Store)            │
└────────────────────────────────────────┘
```

### 前端架构

```
┌────────────────────────────────────────┐
│         Presentation Layer            │
│  ┌──────────┐  ┌──────────┐          │
│  │ Sidebar  │  │ ChatArea │          │
│  │  (导航)  │  │ (对话区) │          │
│  └──────────┘  └──────────┘          │
│  ┌──────────┐                      │
│  │  Editor  │                      │
│  │(Monaco)  │                      │
│  └──────────┘                      │
└──────────────┬───────────────────────┘
               │
┌──────────────┴───────────────────────┐
│         Component Layer              │
│  - Layout Components                 │
│  - Chat Components (SSE handler)     │
│  - Editor Components (Monaco)        │
│  - UI Components (Shadcn/UI)         │
└──────────────┬───────────────────────┘
               │
┌──────────────┴───────────────────────┐
│          State Management            │
│  - Context API (Global state)        │
│  - Custom Hooks (useChat, useEditor) │
│  - Local State (useState)            │
└──────────────┬───────────────────────┘
               │
┌──────────────┴───────────────────────┐
│          Data Layer                  │
│  - API Client (lib/api.ts)           │
│  - SSE Parser (lib/sse.ts)           │
│  - Type Definitions (types/)         │
└────────────────────────────────────────┘
```

## 三、核心模块设计

### 3.1 Agent 核心模块

**职责**：
- 创建和管理 LangChain Agent 实例
- 支持 Multi-LLM 切换
- 工具注册和管理

**关键类**：
```python
class AgentManager:
    def create_agent(tools, system_prompt, llm_provider)
    def stream_chat(messages, session_id)
    def get_available_tools()
```

**技术要点**：
- 使用 `langchain.agents.create_agent` API
- 严禁使用旧版 `AgentExecutor`
- 支持流式输出 (SSE)

### 3.2 Skills 系统

**职责**：
- 扫描 skills 目录生成快照
- 动态加载和执行技能
- 遵循 Instruction-following 范式

**执行流程**：
```
1. Agent 感知 → 发现 available_skills
2. Agent 决策 → 识别需要的 skill
3. Agent 行动 → read_file(SKILL.md)
4. Agent 学习 → 理解指令
5. Agent 执行 → 调用 Core Tools
```

**关键文件**：
- `skills/bootstrap.py` - 生成 SKILLS_SNAPSHOT.md
- `skills/loader.py` - 动态导入
- `skills/executor.py` - 执行引擎

### 3.3 对话记忆管理

**System Prompt 组成** (按顺序)：
```
1. SKILLS_SNAPSHOT.md  ← 动态生成
2. SOUL.md            ← Agent 人格
3. IDENTITY.md        ← 身份认知
4. USER.md            ← 用户画像
5. AGENTS.md          ← 行为准则 (包含技能调用协议)
6. MEMORY.md          ← 长期记忆
```

**会话存储格式**：
```json
{
  "session_id": "uuid",
  "messages": [
    {"type": "user", "content": "..."},
    {"type": "assistant", "content": "..."},
    {"type": "tool", "function_calls": [...]}
  ],
  "created_at": "ISO 8601",
  "updated_at": "ISO 8601"
}
```

### 3.4 5 个核心工具

| 工具名称 | 功能描述 | LangChain 原生 | 安全措施 |
|---------|---------|---------------|---------|
| terminal | Shell 命令执行 | ✅ ShellTool | 沙箱 + 黑名单 |
| python_repl | Python 代码解释器 | ✅ PythonREPLTool | 超时控制 |
| fetch_url | 网页抓取 | ✅ RequestsGetTool | HTML 清洗 |
| read_file | 文件读取 | ✅ ReadFileTool | 路径限制 |
| search_kb | RAG 检索 | ❌ 自定义 | - |

### 3.5 RAG 混合检索

**技术实现**：
- LlamaIndex 作为检索引擎
- BM25 关键词检索
- Vector 向量检索
- Query Fusion 融合策略

**检索流程**：
```
1. 用户查询
2. Query Expansion (生成查询变体)
3. BM25 检索 (top_k=10)
4. Vector 检索 (top_k=10)
5. Reciprocal Rank Fusion (融合)
6. 返回 top_k=5 结果
```

## 四、数据流设计

### 4.1 对话流程

```
User Input (前端)
    │
    ├─→ POST /api/chat
    │       │
    │       ├─→ 1. 构建 System Prompt
    │       │      └─→ 拼接 6 个组件
    │       │
    │       ├─→ 2. 创建/加载 Agent
    │       │      └─→ create_agent()
    │       │
    │       ├─→ 3. 流式调用
    │       │      ├─→ Agent 思考
    │       │      ├─→ Tool Call
    │       │      ├─→ Tool Result
    │       │      └─→ 最终回复
    │       │
    │       └─→ 4. SSE 流式输出
    │              └─→ 事件: thinking, tool_call, content, done
    │
    └─→ 前端 SSE 接收
           ├─→ MessageList (更新对话)
           ├─→ ThinkingChain (显示思考过程)
           └─→ Editor (更新 MEMORY.md)
```

### 4.2 Skills 调用流程

```
User: "查询北京天气"
    │
    ├─→ Agent 感知 (SKILLS_SNAPSHOT)
    │      └─→ 发现 get_weather skill
    │
    ├─→ Agent 决策
    │      └─→ 匹配成功
    │
    ├─→ Tool Call: read_file("./skills/get_weather/SKILL.md")
    │      │
    │      └─→ 读取 Markdown 内容
    │             └─→ "使用 fetch_url 访问天气 API"
    │
    ├─→ Agent 执行指令
    │      └─→ Tool Call: fetch_url("http://api.weather...")
    │
    ├─→ 返回结果
    │      └─→ "北京：晴，15-25度"
    │
    └─→ Agent 回复用户
           └─→ "根据查询结果，北京今天晴..."
```

## 五、安全设计

### 5.1 Terminal 工具安全

**沙箱机制**：
- 限制在 `root_dir` 目录内
- 黑名单拦截高危命令
- 超时控制

**黑名单命令**：
```python
BLOCKED_COMMANDS = [
    "rm -rf /",
    "rm -rf /.*",
    "mkfs",
    "dd if=/dev/zero",
    ":(){ :|:& };:",  # Fork bomb
]
```

### 5.2 文件读取安全

**路径限制**：
- 只能读取 `root_dir` 内的文件
- 路径规范化，防止 `../` 跳转
- 大小限制 (max_file_size=10MB)

### 5.3 API 安全

**输入验证**：
- Pydantic 模型验证
- SQL/命令注入防护
- XSS 防护

**CORS 配置**：
```python
CORS_ORIGINS = ["http://localhost:3000"]
```

## 六、性能优化

### 6.1 后端优化

**策略**：
- 异步处理 (async/await)
- 连接池复用
- 缓存 System Prompt (lru_cache)
- 索引持久化 (ChromaDB)

### 6.2 前端优化

**策略**：
- React.memo 避免重渲染
- useMemo/useCallback 优化
- 虚拟滚动 (MessageList)
- 代码分割 (Next.js 自动)

### 6.3 RAG 优化

**策略**：
- 混合检索 (BM25 + Vector)
- 查询扩展
- 索引缓存
- 分块策略 (chunk_size=512)

## 七、部署架构

### 7.1 本地开发

```
┌─────────────────────┐
│  Frontend (npm)     │
│  Port: 3000         │
└──────────┬──────────┘
           │
           ├─→ API: http://localhost:8002
           └─→ SSE: http://localhost:8002/api/chat

┌─────────────────────┐
│  Backend (uvicorn)  │
│  Port: 8002         │
└─────────────────────┘
```

### 7.2 Docker 部署

```yaml
services:
  backend:
    build: ./backend
    ports: ["8002:8002"]
    volumes: ["./data:/app/data"]

  frontend:
    build: ./frontend
    ports: ["3000:3000"]
    depends_on: ["backend"]
```

## 八、监控和日志

### 8.1 日志策略

**后端**：
- Python logging 模块
- 结构化日志 (JSON)
- 日志级别: DEBUG/INFO/WARNING/ERROR
- 日志轮转 (Daily logs)

**前端**：
- Console API
- 错误上报 (Sentry 可选)

### 8.2 性能监控

**指标**：
- API 响应时间
- Agent 思考时间
- Tool 执行时间
- SSE 连接稳定性

## 九、扩展性设计

### 9.1 添加新工具

```python
# 1. 在 app/tools/ 创建新工具
# 2. 继承 BaseTool
# 3. 在 core/tools.py 注册

from langchain_core.tools import BaseTool

class MyCustomTool(BaseTool):
    name = "my_tool"
    description = "Tool description"

    def _run(self, input: str) -> str:
        # 实现逻辑
        return result
```

### 9.2 添加新 Skill

```bash
# 1. 创建 skill 目录
mkdir -p backend/data/skills/my_skill

# 2. 创建 SKILL.md
cat > SKILL.md << EOF
---
name: my_skill
description: My custom skill
---

# 技能说明

## 使用步骤
1. 步骤一
2. 步骤二
EOF

# 3. 重启后端，自动加载
```

## 十、技术决策记录

### ADR-001: 使用 create_agent 而非 AgentExecutor

**状态**: 已接受

**背景**：
- LangChain 1.0 发布了新的 `create_agent` API
- 旧版 `AgentExecutor` 功能有限且将被废弃

**决策**：
- 必须使用 `create_agent` API
- 理由：更现代、基于 LangGraph、更好的状态管理

**后果**：
- 需要团队学习新 API
- 代码更简洁，维护更容易

### ADR-002: 文件即记忆，不使用向量数据库

**状态**: 已接受

**背景**：
- 传统 RAG 使用向量数据库存储记忆
- 向量数据库不透明，难以理解和调试

**决策**：
- 使用 Markdown/JSON 文件系统
- 向量数据库仅用于知识库检索

**后果**：
- 记忆完全透明，可人工编辑
- 查询性能略低，但可接受

---

*文档版本: 0.1.0*
*最后更新: 2024-03-04*
