# miniClaw AI Agent 系统开发计划

## 一、项目概述

**项目名称**：miniClaw - 轻量级、高度透明的 AI Agent 系统

**核心定位**：
- 文件即记忆 (File-first Memory)：使用 Markdown/JSON 文件系统
- 技能即插件 (Skills as Plugins)：文件夹结构管理能力
- 透明可控：完全透明的 System Prompt 和工具调用

**技术栈**：
- 后端：Python 3.10+, FastAPI, LangChain 1.x (create_agent), LlamaIndex
- 前端：Next.js 14+, TypeScript, Shadcn/UI, Monaco Editor
- 存储：本地文件系统
- LLM：多 LLM 支持（OpenAI/DeepSeek/OpenRouter/通义千问等），测试使用 Qwen 模型
- 部署：Docker + 本地运行双模式

---

## 二、完整目录结构

```
miniclaw/
├── backend/                          # 后端 Python 服务
│   ├── app/
│   │   ├── main.py                   # FastAPI 应用入口
│   │   ├── config.py                 # 配置管理
│   │   ├── dependencies.py           # 依赖注入
│   │   │
│   │   ├── core/                     # 核心模块
│   │   │   ├── agent.py              # LangChain Agent 封装
│   │   │   ├── tools.py              # 工具注册和管理
│   │   │   └── llm.py                # LLM 模型初始化
│   │   │
│   │   ├── tools/                    # 5个核心工具
│   │   │   ├── terminal.py           # ShellTool
│   │   │   ├── python_repl.py        # PythonREPLTool
│   │   │   ├── fetch_url.py          # RequestsGetTool + Wrapper
│   │   │   ├── read_file.py          # ReadFileTool
│   │   │   └── search_kb.py          # LlamaIndex RAG
│   │   │
│   │   ├── skills/                   # Skills 系统
│   │   │   ├── bootstrap.py          # SKILLS_SNAPSHOT.md 生成
│   │   │   ├── loader.py             # 动态加载
│   │   │   └── executor.py           # 执行流程
│   │   │
│   │   ├── memory/                   # 对话记忆管理
│   │   │   ├── prompts.py            # System Prompt 组件
│   │   │   ├── session.py            # 会话存储
│   │   │   └── truncation.py         # Token 截断
│   │   │
│   │   ├── api/                      # API 路由
│   │   │   ├── chat.py               # /api/chat SSE 流式
│   │   │   ├── files.py              # /api/files 文件管理
│   │   │   └── sessions.py           # /api/sessions 会话管理
│   │   │
│   │   └── models/                   # Pydantic 模型
│   │       ├── chat.py
│   │       └── files.py
│   │
│   ├── data/                         # 本地数据
│   │   ├── knowledge_base/           # 知识库文件
│   │   ├── sessions/                 # 会话记录 JSON
│   │   ├── skills/                   # Skills 定义
│   │   └── vector_store/             # 向量存储
│   │
│   ├── requirements.txt
│   └── pyproject.toml
│
├── frontend/                         # 前端 Next.js
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   ├── globals.css
│   │   └── chat/
│   │       ├── layout.tsx
│   │       └── page.tsx
│   │
│   ├── components/
│   │   ├── ui/                       # Shadcn/UI 组件
│   │   ├── layout/                   # 布局组件
│   │   │   ├── Sidebar.tsx           # 左侧导航
│   │   │   ├── ChatArea.tsx          # 中间对话
│   │   │   ├── EditorPanel.tsx       # 右侧编辑器
│   │   │   └── IDELayout.tsx         # 三栏容器
│   │   ├── chat/                     # 聊天组件
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── ThinkingChain.tsx
│   │   │   ├── InputBox.tsx
│   │   │   └── SSEEventHandler.tsx
│   │   └── editor/                   # 编辑器组件
│   │       ├── MonacoWrapper.tsx
│   │       └── FileTree.tsx
│   │
│   ├── lib/
│   │   ├── api.ts                    # API 客户端
│   │   ├── sse.ts                    # SSE 解析器
│   │   └── utils.ts
│   │
│   ├── hooks/
│   │   ├── useChat.ts
│   │   ├── useEditor.ts
│   │   └── useSSE.ts
│   │
│   ├── types/
│   │   ├── chat.ts
│   │   └── api.ts
│   │
│   ├── package.json
│   ├── tsconfig.json
│   └── tailwind.config.ts
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── API.md
│   └── DEPLOYMENT.md
│
├── Dockerfile                      # Docker 容器化配置
├── docker-compose.yml              # Docker Compose 编排
├── .env.example                    # 环境变量示例
└── README.md
```

---

## 三、Subagent 工作任务分配

### 阶段 1: 基础设施 (Foundation) - 并行开发

#### Subagent 1: 后端项目初始化
**任务**：
1. 创建 Python 虚拟环境配置文件
2. 编写 `backend/requirements.txt`
3. 编写 `backend/pyproject.toml`
4. 创建完整目录结构

**依赖**：无

**输出文件**：
- `backend/requirements.txt`
- `backend/pyproject.toml`
- `backend/app/` 目录树

**核心依赖列表**：
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
langchain>=0.1.0
langchain-openai>=0.0.5
langchain-community>=0.0.10
langchain-experimental>=0.0.40
llama-index-core>=0.10.0
llama-index-readers-file>=0.1.0
llama-index-retrievers-bm25>=0.1.0
llama-index-embeddings-openai>=0.1.0
llama-index-vector-stores-chroma>=0.1.0
chromadb>=0.4.0
pydantic>=2.5.0
python-multipart>=0.0.6
beautifulsoup4>=4.12.0
html2text>=2020.1.16
```

---

#### Subagent 2: 前端项目初始化
**任务**：
1. 使用 `npx create-next-app@latest` 初始化 Next.js 14 项目
2. 安装 Shadcn/UI 和依赖
3. 配置 Tailwind CSS (Frosty Glass 主题)
4. 创建目录结构

**依赖**：无

**输出文件**：
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/tailwind.config.ts`
- `frontend/app/` 目录树

**核心依赖列表**：
```json
{
  "dependencies": {
    "next": "14.1.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "@monaco-editor/react": "^4.6.0",
    "lucide-react": "^0.300.0"
  },
  "devDependencies": {
    "typescript": "^5.3.0",
    "tailwindcss": "^3.4.0",
    "@types/node": "^20.10.0"
  }
}
```

---

#### Subagent 3: 配置和环境管理
**任务**：
1. 编写 `backend/app/config.py`
2. 编写 `.env.example`
3. 编写项目 README.md
4. 编写架构文档

**依赖**：Subagent 1, 2

**输出文件**：
- `backend/app/config.py`
- `.env.example`
- `README.md`
- `docs/ARCHITECTURE.md`

---

### 阶段 2: 后端核心工具 (Backend Core) - 顺序开发

#### Subagent 4: 实现 5 个核心工具
**任务**：
1. 实现 `tools/terminal.py` - ShellTool
2. 实现 `tools/python_repl.py` - PythonREPLTool
3. 实现 `tools/fetch_url.py` - RequestsGetTool + HTML 清洗
4. 实现 `tools/read_file.py` - ReadFileTool
5. 实现 `tools/search_kb.py` - LlamaIndex 混合检索

**依赖**：Subagent 1

**输出文件**：
- `backend/app/tools/terminal.py`
- `backend/app/tools/python_repl.py`
- `backend/app/tools/fetch_url.py`
- `backend/app/tools/read_file.py`
- `backend/app/tools/search_kb.py`

**关键实现**：
```python
# terminal.py - 使用 langchain_community.tools.ShellTool
# python_repl.py - 使用 langchain_experimental.tools.PythonREPLTool
# fetch_url.py - 使用 langchain_community.tools.RequestsGetTool + BeautifulSoup
# read_file.py - 使用 langchain_community.tools.file_management.ReadFileTool
# search_kb.py - 使用 LlamaIndex Hybrid Search
```

---

#### Subagent 5: LLM 和 Agent 封装
**任务**：
1. 实现 `core/llm.py` - LLM 模型初始化
2. 实现 `core/agent.py` - LangChain create_agent 封装
3. 实现 `core/tools.py` - 工具注册和管理

**依赖**：Subagent 4

**输出文件**：
- `backend/app/core/llm.py`
- `backend/app/core/agent.py`
- `backend/app/core/tools.py`

**关键实现**：
```python
# core/llm.py - 多 LLM 支持
from langchain_openai import ChatOpenAI
from typing import Literal

LLMProvider = Literal["openai", "deepseek", "qwen", "ollama"]

def create_llm(provider: LLMProvider = "qwen"):
    """创建 LLM 实例，支持多个提供商"""
    if provider == "openai":
        return ChatOpenAI(model="gpt-4o-mini")
    elif provider == "deepseek":
        return ChatOpenAI(
            base_url="https://api.deepseek.com",
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            model="deepseek-chat"
        )
    elif provider == "qwen":
        # 通义千问（OpenAI 兼容接口）
        return ChatOpenAI(
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            api_key=os.getenv("QWEN_API_KEY"),
            model="qwen-plus"
        )
    elif provider == "ollama":
        return ChatOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model="qwen:7b"
        )

# core/agent.py - 使用 langchain.agents.create_agent
from langchain.agents import create_agent

def create_openclaw_agent(tools, system_prompt, llm_provider="qwen"):
    model = create_llm(llm_provider)
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt
    )
    return agent
```

---

#### Subagent 6: Skills 系统实现
**任务**：
1. 实现 `skills/bootstrap.py` - SKILLS_SNAPSHOT.md 生成
2. 实现 `skills/loader.py` - Skills 动态加载
3. 实现 `skills/executor.py` - Instruction-following 执行
4. 创建示例 skill：get_weather
5. 创建示例 skill：find_skill (用于查找和发现其他 skills)

**依赖**：Subagent 5

**输出文件**：
- `backend/app/skills/bootstrap.py`
- `backend/app/skills/loader.py`
- `backend/app/skills/executor.py`
- `backend/data/skills/get_weather/SKILL.md`
- `backend/data/skills/find_skill/SKILL.md`

---

#### Subagent 7: 对话记忆管理
**任务**：
1. 实现 `memory/prompts.py` - 6个 System Prompt 组件
2. 实现 `memory/session.py` - 会话存储管理
3. 实现 `memory/truncation.py` - Token 截断策略

**依赖**：Subagent 6

**输出文件**：
- `backend/app/memory/prompts.py`
- `backend/app/memory/session.py`
- `backend/app/memory/truncation.py`

**System Prompt 组件**：
1. SKILLS_SNAPSHOT.md - 动态生成的能力列表
2. SOUL.md - Agent 人格设定
3. IDENTITY.md - 身份和角色
4. USER.md - 用户画像
5. AGENTS.md - 行为准则 & 技能调用协议
6. MEMORY.md - 长期记忆

---

### 阶段 3: API 层 (API Layer) - 顺序开发

#### Subagent 8: FastAPI 路由实现
**任务**：
1. 实现 `api/chat.py` - SSE 流式输出
2. 实现 `api/files.py` - 文件管理接口
3. 实现 `api/sessions.py` - 会话管理接口
4. 实现 `models/` Pydantic 模型

**依赖**：Subagent 7

**输出文件**：
- `backend/app/api/chat.py`
- `backend/app/api/files.py`
- `backend/app/api/sessions.py`
- `backend/app/models/chat.py`
- `backend/app/models/files.py`

**关键实现**：
```python
# chat.py - SSE 流式输出
from fastapi.responses import StreamingResponse

@router.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    async def event_generator():
        async for chunk in agent.stream({"messages": messages}):
            yield f"data: {json.dumps(chunk)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

#### Subagent 9: FastAPI 应用入口
**任务**：
1. 实现 `main.py` - 应用主入口
2. 实现 `dependencies.py` - FastAPI 依赖注入
3. 配置 CORS 和中间件

**依赖**：Subagent 8

**输出文件**：
- `backend/app/main.py`
- `backend/app/dependencies.py`

**服务配置**：
- 端口：8002
- CORS：允许 http://localhost:3000
- 中间件：日志、异常处理

---

### 阶段 4: 前端核心 UI (Frontend Core) - 并行开发

#### Subagent 10: Shadcn/UI 组件集成
**任务**：
1. 安装 Shadcn/UI 基础组件
2. 配置 Frosty Glass 主题
3. 创建 globals.css

**依赖**：Subagent 2

**输出文件**：
- `frontend/components/ui/` (shadcn 组件)
- `frontend/app/globals.css`

**主题配置**：
- 背景：`rgba(255, 255, 255, 0.8)`
- 毛玻璃：`backdrop-filter: blur(20px)`
- 强调色：克莱因蓝 `#002FA7`

---

#### Subagent 11: IDE 布局组件
**任务**：
1. 实现 `layout/Sidebar.tsx` - 左侧导航 + 会话列表
2. 实现 `layout/ChatArea.tsx` - 中间对话流
3. 实现 `layout/EditorPanel.tsx` - 右侧 Monaco Editor
4. 实现 `layout/IDELayout.tsx` - 三栏布局容器

**依赖**：Subagent 10

**输出文件**：
- `frontend/components/layout/Sidebar.tsx`
- `frontend/components/layout/ChatArea.tsx`
- `frontend/components/layout/EditorPanel.tsx`
- `frontend/components/layout/IDELayout.tsx`

---

#### Subagent 12: 聊天组件
**任务**：
1. 实现 `chat/MessageList.tsx` - 消息列表
2. 实现 `chat/MessageBubble.tsx` - 消息气泡
3. 实现 `chat/ThinkingChain.tsx` - 思考链可视化
4. 实现 `chat/InputBox.tsx` - 输入框
5. 实现 `chat/SSEEventHandler.tsx` - SSE 事件处理

**依赖**：Subagent 11

**输出文件**：
- `frontend/components/chat/MessageList.tsx`
- `frontend/components/chat/MessageBubble.tsx`
- `frontend/components/chat/ThinkingChain.tsx`
- `frontend/components/chat/InputBox.tsx`
- `frontend/components/chat/SSEEventHandler.tsx`

---

#### Subagent 13: 编辑器组件
**任务**：
1. 实现 `editor/MonacoWrapper.tsx` - Monaco 封装
2. 实现 `editor/FileTree.tsx` - 文件树
3. 配置 Monaco Light 主题

**依赖**：Subagent 11

**输出文件**：
- `frontend/components/editor/MonacoWrapper.tsx`
- `frontend/components/editor/FileTree.tsx`

---

### 阶段 5: 状态管理和集成 (State & Integration) - 顺序开发

#### Subagent 14: React Hooks 实现
**任务**：
1. 实现 `hooks/useChat.ts` - 聊天状态管理
2. 实现 `hooks/useEditor.ts` - 编辑器状态管理
3. 实现 `hooks/useSSE.ts` - SSE 连接管理

**依赖**：Subagent 12, 13

**输出文件**：
- `frontend/hooks/useChat.ts`
- `frontend/hooks/useEditor.ts`
- `frontend/hooks/useSSE.ts`

---

#### Subagent 15: API 客户端
**任务**：
1. 实现 `lib/api.ts` - API 客户端
2. 实现 `lib/sse.ts` - SSE 解析器
3. 实现 `lib/utils.ts` - 通用工具
4. 定义 `types/` 类型定义

**依赖**：Subagent 14

**输出文件**：
- `frontend/lib/api.ts`
- `frontend/lib/sse.ts`
- `frontend/lib/utils.ts`
- `frontend/types/chat.ts`
- `frontend/types/api.ts`

---

#### Subagent 16: 页面集成
**任务**：
1. 实现 `app/chat/page.tsx` - 主页面
2. 实现 `app/layout.tsx` - 根布局
3. 实现 `contexts/AppContext.tsx` - 应用上下文

**依赖**：Subagent 15

**输出文件**：
- `frontend/app/chat/page.tsx`
- `frontend/app/layout.tsx`
- `frontend/contexts/AppContext.tsx`

---

### 阶段 6: 测试和优化 (Testing & Optimization) - 并行开发

#### Subagent 17: 后端测试（完整测试覆盖）
**任务**：
1. 编写工具单元测试（pytest）
2. 编写 API 集成测试
3. 编写端到端测试
4. 配置测试覆盖率报告（pytest-cov）
5. 设置 CI 自动测试脚本

**依赖**：Subagent 9

**输出文件**：
- `backend/tests/test_tools.py` - 单元测试
- `backend/tests/test_api.py` - API 集成测试
- `backend/tests/test_e2e.py` - 端到端测试
- `backend/tests/conftest.py` - pytest 配置
- `backend/pytest.ini` - pytest 设置
- `backend/.github/workflows/test.yml` - CI 测试工作流

---

#### Subagent 18: 前端测试（完整测试覆盖）
**任务**：
1. 编写组件单元测试（Jest + React Testing Library）
2. 编写 Hooks 测试
3. 编写 E2E 测试（Playwright）
4. 配置测试覆盖率报告
5. 设置 CI 自动测试脚本

**依赖**：Subagent 16

**输出文件**：
- `frontend/components/__tests__/` - 组件测试
- `frontend/hooks/__tests__/` - Hooks 测试
- `frontend/e2e/` - E2E 测试
- `frontend/jest.config.js` - Jest 配置
- `frontend/playwright.config.ts` - Playwright 配置
- `frontend/.github/workflows/test.yml` - CI 测试工作流

---

#### Subagent 19: 文档和部署配置
**任务**：
1. 编写 `docs/API.md` - API 接口文档
2. 编写 `docs/DEPLOYMENT.md` - 部署指南（Docker + 本地运行）
3. 编写 Docker 配置（支持 Docker 和本地运行两种方式）
4. 编写 docker-compose.yml（一键启动完整系统）
5. 配置 GitHub Actions CI/CD（自动化测试和部署）

**依赖**：Subagent 17, 18

**输出文件**：
- `docs/API.md`
- `docs/DEPLOYMENT.md`
- `Dockerfile` - 后端 Docker 配置
- `docker-compose.yml` - 完整系统编排
- `frontend/Dockerfile` - 前端 Docker 配置
- `.github/workflows/ci.yml` - CI/CD 配置

---

## 四、并行开发策略

### 阶段 1 (并行)
```
Subagent 1 (后端初始化) ──┐
Subagent 2 (前端初始化) ──┼──→ Subagent 3 (配置)
Subagent 3 (配置管理) ────┘   (需要等待 1,2 完成)
```

### 阶段 2 (顺序)
```
Subagent 4 (工具) → Subagent 5 (Agent) → Subagent 6 (Skills) → Subagent 7 (记忆)
```

### 阶段 3 (顺序)
```
Subagent 8 (API) → Subagent 9 (Main)
```

### 阶段 4 (并行)
```
Subagent 10 (UI组件) ──┐
Subagent 11 (布局) ────┤
Subagent 12 (聊天) ────┼──→ 阶段 5
Subagent 13 (编辑器) ──┘
```

### 阶段 5 (顺序)
```
Subagent 14 (Hooks) → Subagent 15 (API客户端) → Subagent 16 (页面集成)
```

### 阶段 6 (并行)
```
Subagent 17 (后端测试) ──┐
Subagent 18 (前端测试) ───┼──→ 完成
Subagent 19 (文档部署) ──┘
```

---

## 五、关键实现细节

### 5.1 System Prompt 拼接逻辑

```python
# backend/app/memory/prompts.py

def build_system_prompt(session_data: dict) -> str:
    # 1. 生成 SKILLS_SNAPSHOT
    skills_snapshot = generate_skills_snapshot()

    # 2. 拼接 6 个组件
    components = [
        load_file("workspace/SKILLS_SNAPSHOT.md"),
        load_file("workspace/SOUL.md"),
        load_file("workspace/IDENTITY.md"),
        load_file("workspace/USER.md"),
        load_file("workspace/AGENTS.md"),
        load_file("workspace/MEMORY.md"),
    ]

    # 3. 截断处理
    full_prompt = "\n\n---\n\n".join(components)
    if len(full_prompt) > 20000:
        full_prompt = truncate_prompt(full_prompt, max_tokens=20000)

    return full_prompt
```

### 5.2 Agent Skills 执行流程 (Instruction-following)

```python
# backend/app/skills/executor.py

async def execute_skill(skill_name: str, user_input: str):
    # 1. Agent 调用 read_file 读取 skill 的 SKILL.md
    skill_content = await read_file(f"data/skills/{skill_name}/SKILL.md")

    # 2. Agent 解析 Markdown 中的指令
    instructions = parse_skill_instructions(skill_content)

    # 3. Agent 动态调用 Core Tools 执行指令
    results = []
    for step in instructions:
        tool = get_tool(step.tool_name)
        result = await tool.ainvoke(step.parameters)
        results.append(result)

    # 4. 格式化最终响应
    return format_response(results)
```

### 5.3 SSE 流式输出

```python
# backend/app/api/chat.py

@router.post("/api/chat")
async def chat_endpoint(request: ChatRequest):
    async def event_generator():
        # 发送思考事件
        yield f"data: {json.dumps({'type': 'thinking_start'})}\n\n"

        # 流式调用 Agent
        async for chunk in agent.astream({"messages": request.messages}):
            if chunk.tool_calls:
                yield f"data: {json.dumps({'type': 'tool_call', 'data': chunk.tool_calls})}\n\n"
            if chunk.content:
                yield f"data: {json.dumps({'type': 'content_delta', 'content': chunk.content})}\n\n"

        # 发送完成事件
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## 六、验证和测试

### 后端验证
```bash
# 1. 启动后端服务
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload

# 2. 测试 API
curl -X POST http://localhost:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "Hello"}]}'

# 3. 测试 SSE 流式输出
curl -N http://localhost:8002/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "北京天气"}]}'
```

### 前端验证
```bash
# 1. 启动前端服务
cd frontend
npm install
npm run dev

# 2. 访问 http://localhost:3000
# 3. 验证三栏布局正确显示
# 4. 发送测试消息，验证 SSE 流式输出
# 5. 测试 Monaco Editor 文件编辑功能
```

### 集成测试
1. 创建新会话
2. 发送消息，观察 Agent 思考链
3. 测试工具调用 (terminal, python_repl, fetch_url)
4. 在右侧编辑器中查看/编辑 MEMORY.md
5. 创建新 skill，验证动态加载

---

## 七、关键文件清单

### 后端关键文件
1. `backend/app/core/agent.py` - LangChain create_agent 封装
2. `backend/app/api/chat.py` - SSE 流式输出
3. `backend/app/skills/bootstrap.py` - SKILLS_SNAPSHOT 生成
4. `backend/app/tools/search_kb.py` - LlamaIndex 混合检索
5. `backend/app/memory/prompts.py` - System Prompt 拼接

### 前端关键文件
1. `frontend/components/chat/SSEEventHandler.tsx` - SSE 事件处理
2. `frontend/components/layout/IDELayout.tsx` - 三栏布局
3. `frontend/hooks/useChat.ts` - 聊天状态管理
4. `frontend/lib/api.ts` - API 客户端
5. `frontend/app/chat/page.tsx` - 主页面

---

## 八、LLM 配置说明

### 多 LLM 接口支持

系统预留多个 LLM 提供商接口，通过环境变量配置：

```bash
# .env 文件配置
LLM_PROVIDER=qwen  # 默认使用 Qwen

# OpenAI 配置
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o-mini

# DeepSeek 配置
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

# 通义千问配置（测试用）
QWEN_API_KEY=sk-xxx
QWEN_MODEL=qwen-plus

# Ollama 配置（本地）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen:7b
```

### 测试环境默认配置

测试时使用 **通义千问 Qwen 模型**（OpenAI 兼容接口）：
- 模型：qwen-plus
- Base URL：https://dashscope.aliyuncs.com/compatible-mode/v1
- 性价比高，稳定性好

## 九、Docker 部署说明

### Docker 本地运行

```bash
# 启动完整系统（后端 + 前端）
docker-compose up -d

# 仅启动后端
docker-compose up backend

# 仅启动前端
docker-compose up frontend

# 查看日志
docker-compose logs -f

# 停止系统
docker-compose down
```

### 本地开发运行

```bash
# 后端
cd backend
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload

# 前端
cd frontend
npm install
npm run dev
```

### 两种方式对比

| 方式 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| Docker | 环境隔离、一键启动 | 调试较复杂 | 快速演示、生产部署 |
| 本地运行 | 调试方便、热更新快 | 需要配置环境 | 开发调试 |

## 十、开发顺序建议

1. **Week 1**：阶段 1-2 (基础设施 + 后端核心)
2. **Week 2**：阶段 3-4 (API 层 + 前端 UI)
3. **Week 3**：阶段 5-6 (集成 + 测试 + 文档)

---

## 九、注意事项

1. **LangChain 版本**：必须使用 LangChain 1.x 的 `create_agent` API，严禁使用旧版 `AgentExecutor`
2. **安全性**：terminal 工具必须配置沙箱和命令黑名单
3. **Token 管理**：实现截断策略防止超长 Prompt
4. **SSE 可靠性**：实现错误处理和重连机制
5. **文件权限**：限制 read_file 工具的访问范围

---

## 十、参考资源

- LangChain 1.x 文档：https://python.langchain.com/docs/get_started/introduction
- LlamaIndex 文档：https://docs.llamaindex.ai/
- FastAPI 文档：https://fastapi.tiangolo.com/
- Next.js 14 文档：https://nextjs.org/docs
- Shadcn/UI：https://ui.shadcn.com/
