# miniClaw

> 轻量级、高度透明的 AI Agent 系统

## 项目简介

miniClaw 是一个基于 Python 重构的、轻量级且高度透明的 AI Agent 系统，旨在复刻并优化 OpenClaw（原名 Moltbot/Clawdbot）的核心体验。

### 核心特点

- **文件即记忆 (File-first Memory)**：摒弃不透明的向量数据库，使用 Markdown/JSON 文件系统
- **技能即插件 (Skills as Plugins)**：遵循 Anthropic Agent Skills 范式，文件夹结构管理能力
- **透明可控**：所有 System Prompt 拼接逻辑、工具调用过程完全透明

## 技术栈

### 后端
- **Python 3.10+**
- **FastAPI** - Web 框架
- **LangChain 1.x** - Agent 编排引擎 (使用 `create_agent` API)
- **LlamaIndex** - RAG 混合检索

### 前端
- **Next.js 14+** - React 框架 (App Router)
- **TypeScript** - 类型安全
- **Shadcn/UI** - UI 组件库
- **Monaco Editor** - 代码编辑器
- **Tailwind CSS** - 样式 (Frosty Glass 主题)

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- npm

### 安装

1. **克隆项目**
```bash
git clone <repository-url>
cd miniclaw
```

2. **配置环境变量**
```bash
cp .env.example .env
# 编辑 .env 文件，填入你的 API Keys
```

3. **安装后端依赖**
```bash
cd backend
pip install -r requirements.txt
```

4. **安装前端依赖**
```bash
cd frontend
npm install
```

### 运行

#### 方式 1: 使用启动脚本 (推荐)

**Windows:**
```bash
start.bat
```
会自动打开两个窗口：后端 (8002) 和前端 (3000)

**Linux/macOS:**
```bash
./start.sh
```

#### 方式 2: 手动启动

**需要同时开启两个终端：**

**终端 1 - 启动后端** (端口 8002):
```bash
cd backend
# Windows (如果还没创建虚拟环境)
python -m venv venv
venv\Scripts\activate
# Linux/macOS
# python3 -m venv venv
# source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload
```

**终端 2 - 启动前端** (端口 3000):
```bash
cd frontend
npm install  # 首次运行需要
npm run dev
```

访问 http://localhost:3000

**启动顺序：先启动后端，再启动前端**

#### 方式 2: Docker

```bash
# 启动完整系统
docker-compose up -d

# 查看日志
docker-compose logs -f
```

## 项目结构

```
miniclaw/
├── backend/                # Python 后端
│   ├── app/
│   │   ├── core/          # 核心模块
│   │   ├── tools/         # 5 个核心工具
│   │   ├── skills/        # Skills 系统
│   │   ├── memory/        # 对话记忆管理
│   │   ├── api/           # API 路由
│   │   └── models/        # Pydantic 模型
│   ├── data/              # 本地数据
│   └── requirements.txt
│
├── frontend/              # Next.js 前端
│   ├── app/
│   ├── components/
│   ├── lib/
│   ├── hooks/
│   └── types/
│
├── docs/                  # 文档
├── DEVELOPMENT_PLAN.md    # 开发计划
├── claude.md             # 开发规范
└── README.md             # 本文件
```

## 核心功能

### 5 个核心工具

1. **terminal** - Shell 命令执行 (沙箱化)
2. **python_repl** - Python 代码解释器
3. **fetch_url** - 网页抓取 (自动清洗 HTML)
4. **read_file** - 文件读取
5. **search_knowledge_base** - RAG 混合检索

### Agent Skills 系统

采用 **Instruction-following** 范式：
- Skills 是 Markdown 格式的说明书
- Agent 通过阅读 SKILL.md 学习如何使用工具
- 支持热插拔，拖入即用

### System Prompt 组成

1. SKILLS_SNAPSHOT.md - 能力列表
2. SOUL.md - 核心设定
3. IDENTITY.md - 自我认知
4. USER.md - 用户画像
5. AGENTS.md - 行为准则
6. MEMORY.md - 长期记忆

## API 接口

### 核心对话接口
```http
POST /api/chat
Content-Type: application/json

{
  "message": "查询一下北京的天气",
  "session_id": "main_session",
  "stream": true
}
```

返回 SSE 流式数据。

### 文件管理接口
```http
GET /api/files?path=memory/MEMORY.md
POST /api/files
Body: { "path": "...", "content": "..." }
```

## 测试

### 后端测试
```bash
cd backend
pytest tests/
```

### 前端测试
```bash
cd frontend
npm test              # 单元测试
npx playwright test   # E2E 测试
```

## LLM 配置

支持多个 LLM 提供商，通过环境变量 `LLM_PROVIDER` 切换：

- **qwen** (默认) - 通义千问，测试环境
- **openai** - GPT-4o-mini
- **deepseek** - DeepSeek-chat
- **ollama** - 本地模型

详细配置见 `.env.example`

### Embedding 模型配置

知识库功能使用 embedding 模型进行语义检索。系统支持三种配置方式，按优先级自动选择：

#### 方式 1: 使用 LLM 提供商的 API 嵌入（默认）

如果 LLM 提供商支持嵌入 API，系统将优先使用（无需下载模型）：

| LLM 提供商 | 嵌入模型 | 配置 |
|-----------|---------|------|
| OpenAI | `text-embedding-3-large` | `OPENAI_API_KEY` |
| Qwen | `text-embedding-v3` | `QWEN_API_KEY` |
| DeepSeek | `deepseek-embedding` | `DEEPSEEK_API_KEY` |
| Ollama | `nomic-embed-text` | `OLLAMA_BASE_URL` |

**优点**：无需下载模型，直接调用 API

#### 方式 2: 使用本地 HuggingFace 模型

当 LLM 不支持嵌入或 API 不可用时，系统将自动下载并使用本地模型：

- **默认模型**: `RamManavalan/Qwen3-VL-Embedding-8B-FP8`
- **模型缓存目录**: `backend/models/hub/`
- **自动回退**: HF-Mirror → 官方 HuggingFace

**首次使用知识库功能时会自动下载模型**（约 8GB），国内用户通过 HF-Mirror 下载速度较快。

#### 方式 3: 手动指定模型

编辑 `backend/app/core/rag_engine.py`，修改 `_get_fallback_embedding()` 方法中的 `model_name`：

```python
# 示例：使用其他模型
model_name = "BAAI/bge-large-zh-v1.5"  # 中文嵌入模型
model_name = "sentence-transformers/all-MiniLM-L6-v2"  # 轻量级模型
```

#### 模型缓存目录

```
backend/models/hub/models--<用户名>--<模型名>/snapshots/<commit-hash>/
```

**手动下载模型**：

如果需要离线使用，可以提前下载模型到 `backend/models/` 目录，系统会自动检测并使用缓存。

---

## 开发规范

请参阅 [claude.md](./claude.md) 了解完整的开发规范和 AI 协作协议。

## 文档

- [开发计划](./DEVELOPMENT_PLAN.md) - 完整的开发计划和任务分配
- [开发规范](./claude.md) - 代码规范和最佳实践
- [架构文档](./docs/ARCHITECTURE.md) - 系统架构设计（待创建）
- [API 文档](./docs/API.md) - API 接口文档（待创建）
- [部署指南](./docs/DEPLOYMENT.md) - Docker 和本地部署（待创建）

## 注意事项

⚠️ **安全警告**：
- Terminal 工具已配置沙箱和命令黑名单
- read_file 工具限制在项目目录内
- 请勿在生产环境使用默认 API Keys

⚠️ **技术要求**：
- 必须使用 LangChain 1.x 的 `create_agent` API
- 严禁使用旧版 `AgentExecutor`
- 强制使用 Type Hinting (Python) 和 strict mode (TypeScript)

## 贡献指南

欢迎贡献！请遵循以下流程：

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

请确保遵循 [claude.md](./claude.md) 中的代码规范。

## 许可证

本项目采用 MIT 许可证 - 详见 LICENSE 文件

## 致谢

- OpenClaw 原型项目
- LangChain 团队
- LlamaIndex 团队
- Anthropic Agent Skills 范式

---

**Happy Coding! 🚀**
