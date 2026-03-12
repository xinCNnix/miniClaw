# miniClaw Quick Start Guide

## 快速开始

### 1. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

编辑 `.env` 文件，添加你的 API 密钥：

```bash
# 使用通义千问（推荐用于测试）
LLM_PROVIDER=qwen
QWEN_API_KEY=your-qwen-api-key-here
QWEN_MODEL=qwen-plus
```

### 2. 启动系统

#### Windows 用户
双击运行 `start.bat`

#### Linux/Mac 用户
```bash
chmod +x start.sh
./start.sh
```

#### 使用 Docker（推荐）
```bash
docker-compose up -d
```

### 3. 访问应用

- 前端界面：http://localhost:3000
- 后端 API：http://localhost:8002
- API 文档：http://localhost:8002/docs

---

## 核心功能

### 5 个核心工具

1. **terminal** - 安全执行 Shell 命令
2. **python_repl** - 执行 Python 代码
3. **fetch_url** - 获取和清理网页内容
4. **read_file** - 读取本地文件
5. **search_kb** - 知识库搜索（RAG）

### Skills 系统

- 位置：`backend/data/skills/`
- 预置 Skills：
  - `get_weather` - 获取天气信息
  - `find_skill` - 查找其他 Skills

### 文件即记忆

- 对话记录存储在：`backend/data/sessions/`
- 系统提示词组件：`backend/data/workspace/`

---

## 常见问题

### Q: 如何获取 Qwen API 密钥？
A: 访问 https://dashscope.aliyun.com/ 注册并创建 API Key

### Q: 支持哪些 LLM？
A:
- Qwen（通义千问）- 默认推荐
- OpenAI (GPT-4)
- DeepSeek
- Ollama（本地）

### Q: 如何添加自定义 Skill？
A: 在 `backend/data/skills/` 下创建新文件夹，添加 `SKILL.md` 文件

---

## 开发指南

### 后端开发
```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
uvicorn app.main:app --port 8002 --reload
```

### 前端开发
```bash
cd frontend
npm run dev
```

### 运行测试
```bash
# 后端测试
cd backend
pytest

# 前端测试
cd frontend
npm test
```

---

## 更多信息

- 完整文档：`docs/ARCHITECTURE.md`
- API 文档：`docs/API.md`
- 部署指南：`docs/DEPLOYMENT.md`
- 开发计划：`DEVELOPMENT_PLAN.md`
