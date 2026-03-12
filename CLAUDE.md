# CLAUDE.md — miniClaw 开发规范

## 项目信息
- 项目名称: miniClaw
- 项目类型: AI Agent 系统 (前后端分离)
- 后端语言: Python 3.10+
- 后端框架: FastAPI, LangChain 1.x, LlamaIndex
- 前端语言: TypeScript
- 前端框架: Next.js 14+, Shadcn/UI
- 包管理器:
  - 后端: pip
  - 前端: npm

## 常用命令

### 后端 (Python)
```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 启动开发环境 (端口 8002)
uvicorn app.main:app --port 8002 --reload

# 运行测试
pytest tests/

# 代码检查
ruff check app/
black app/
```

### 前端 (Next.js)
```bash
cd frontend

# 安装依赖
npm install

# 启动开发环境 (端口 3000)
npm run dev

# 构建生产版本
npm run build

# 运行测试
npm test

# E2E 测试
npx playwright test

# 代码检查
npm run lint
```

### Docker
```bash
# 启动完整系统
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止系统
docker-compose down
```

## 命名规范

### 文件命名

#### Python (后端)
- 格式: snake_case (PEP8)
- 类型后缀: 无后缀 / _test.py
- 示例:
  - `agent_manager.py`
  - `skills_bootstrap.py`
  - `test_tools.py`

#### TypeScript/JavaScript (前端)
- 格式: kebab-case (全小写，中划线分隔)
- 类型后缀: .component .hook .util .types .test
- 示例:
  - `message-list.component.tsx`
  - `use-chat.hook.ts`
  - `api.util.ts`
  - `chat.types.ts`

### 文件夹命名
- 格式: kebab-case (全小写，中划线分隔)
- Python: 使用下划线分隔 (PEP8)
- 禁止: 大写字母、空格
- 层级: 最多 4 层深度
- 单文件直接放父目录，不单独建文件夹

## 目录结构

```
miniclaw/
├── backend/                    # 后端 Python 服务
│   ├── app/
│   │   ├── core/              # 核心模块 (禁止依赖业务模块)
│   │   ├── tools/             # 5 个核心工具
│   │   ├── skills/            # Skills 系统
│   │   ├── memory/            # 对话记忆管理
│   │   ├── api/               # API 路由
│   │   └── models/            # Pydantic 模型
│   ├── data/                  # 本地数据存储
│   │   ├── knowledge_base/    # 知识库
│   │   ├── sessions/          # 会话记录
│   │   ├── skills/            # Skills 定义
│   │   └── vector_store/      # 向量存储
│   └── tests/                 # 测试文件
│
├── frontend/                   # 前端 Next.js
│   ├── app/                   # App Router
│   ├── components/            # React 组件
│   │   ├── ui/               # 公共 UI 组件
│   │   ├── layout/           # 布局组件
│   │   ├── chat/             # 聊天组件
│   │   └── editor/           # 编辑器组件
│   ├── lib/                   # 工具库 (禁止依赖业务模块)
│   ├── hooks/                 # React Hooks
│   ├── types/                 # TypeScript 类型
│   └── tests/                 # 测试文件
│
├── docs/                       # 文档
└── tests/                      # E2E 测试
```

## 代码复用

IMPORTANT: 禁止重复实现已有功能

- 相同代码出现 2 次 → 必须提取为公共函数
- 超过 10 行的业务逻辑 → 考虑复用
- 简单条件判断 → 不必过度抽象
- 新建文件前 → 先搜索是否已有类似功能
- 公共模块禁止依赖业务模块，避免循环依赖

### 后端复用规则
- 优先使用 LangChain 原生工具
- 自定义工具放入 `app/tools/`
- 公共函数放入 `app/core/utils.py`

### 前端复用规则
- UI 组件优先使用 Shadcn/UI
- 自定义组件放入 `components/ui/`
- 工具函数放入 `lib/`

## 代码健壮性

### 错误处理
- 异步操作必须有错误处理机制
- 错误分类处理:
  - 验证错误 → 返回字段级详情
  - 业务错误 → 返回用户友好提示
  - 系统错误 → 记录日志，返回通用错误
- 错误向上传播时补充上下文信息

### 输入验证
- 所有外部输入必须验证 (API 参数、用户输入、文件内容)
- 后端使用 Pydantic 验证
- 前端使用 Zod 验证
- 验证失败返回明确错误信息

### 边界检查
- 集合/数组访问前检查索引边界
- 除法前检查除数非零
- 空值检查 (null/undefined/None)
- 类型转换前验证数据有效性
- 资源申请后确保释放 (连接、文件句柄、锁等)

### 后端特定
- Terminal 工具必须配置沙箱和命令黑名单
- read_file 工具必须限制访问范围 (root_dir)
- PythonREPL 必须设置超时控制

### 前端特定
- SSE 连接必须处理断线和重连
- 所有 API 调用必须有超时设置
- 文件上传必须验证类型和大小

## 修改原则

IMPORTANT: 根本解决问题

- 找到 root cause，从根本上解决
- 正面面对问题，不绕过不回避
- 复杂问题先说明根本原因，再讨论方案
- 禁止打补丁、用 hack、投机取巧
- 禁止因为"能跑"就不深究

### 代码清理
- 废弃代码: 确认无引用 → 直接删除
- 重复实现: 统一为一个 → 删除其余
- 死代码: 注释代码块、未使用的变量/函数 → 删除
- 历史遗留: 开发阶段大胆重构，不背历史包袱
- 不保留"以防万一"的代码

### 修改范围
- 只改必要文件，不顺便改无关代码
- 修改前先理解现有代码意图
- 修改后运行相关测试确认无回归

### 兼容性
- 仅对外发布的 API/SDK 需考虑向后兼容
- 内部开发阶段: 该改就改，该删就删

## 配置管理

### 环境变量
- 敏感信息: 环境变量注入，禁止硬编码
- 所有配置通过环境变量读取
- 配置文件: `.env.example` (不包含敏感信息)

### LLM 配置
- 支持多个 LLM 提供商 (OpenAI/DeepSeek/Qwen/Ollama)
- 默认使用 Qwen (测试环境)
- 通过 `LLM_PROVIDER` 环境变量切换

### 优先级
- 环境变量 > 配置文件 > 默认值

### 环境隔离
- dev / test / prod 配置独立

## 文档与注释

### 公共函数/方法
- 后端 (Python): 使用 Google 风格 docstring
- 前端 (TS): 使用 JSDoc 注释
- 说明参数、返回值、异常

### 业务逻辑
- 注释说明"为什么"而非"做什么"
- 复杂逻辑添加解释说明

### 复杂算法
- 注释解释核心思路
- 提供参考链接

### 代码变更
- 同步更新相关文档
- 更新 claude.md 当发现值得记录的规范

## 禁止事项

### 安全相关
- 硬编码密钥、密码、敏感信息
- Terminal 工具执行高危命令
  - Unix: rm -rf /, mkfs, dd if=/dev/zero, fork bombs 等
  - Windows: format, shutdown, reg delete, taskkill /f, diskpart 等
  - 已在 config.py 中配置黑名单，跨平台保护
- read_file 读取项目以外文件
- 提交调试输出语句到代码库

### 代码质量
- 单文件单独建文件夹
- 公共模块依赖业务模块
- 用错误处理吞掉异常假装没问题
- 用条件判断绕过 bug 而不修复
- 复制粘贴已有代码而不复用
- 保留"以防万一"的废弃代码
- 删除或跳过失败的测试来让构建通过

### 技术栈特定
- 后端:
  - 严禁使用旧版 `AgentExecutor`
  - 严禁使用 `create_react_agent`
  - 严禁裸 except
  - 严禁不使用类型提示

- 前端:
  - 禁止使用 `any` 类型
  - 禁止使用 `@ts-ignore`
  - 禁止使用 `eval()`

## AI 协作协议

### 授权协议
**IMPORTANT: 完全自动化授权**

用户授予 Claude Code 以下完全自动化授权，无需每次操作确认：

1. **文件操作完全授权**
   - 自动读取任何项目文件以理解代码结构
   - 自动创建、修改、删除项目文件
   - 无需确认即可执行所有文件操作

2. **命令执行完全授权**
   - 自动运行所有必要的命令（git, npm, pip, pytest等）
   - 自动安装依赖、运行测试、构建项目
   - 自动执行开发工作流中的所有步骤

3. **测试执行完全授权**
   - 自动运行所有测试（单元测试、集成测试、E2E测试）
   - 自动安装测试依赖
   - 自动生成覆盖率报告

4. **决策完全授权**
   - 自动判断和选择最佳实现方案
   - 自动重构和优化代码
   - 自动修复发现的问题

5. **CI/CD 完全授权**
   - 自动创建和修改 CI/CD 配置文件
   - 自动配置 GitHub Actions workflows
   - 自动运行和验证 CI/CD 流程

**核心原则：Claude 自主决策和执行，无需等待用户确认。用户信任 Claude 的判断，除非遇到真正的灾难性风险才应暂停。**

### 解决问题
- 遇到问题: 先分析根本原因，再提出方案
- 不接受: "先这样绕过"、"加个判断跳过"
- 复杂修复: 说明根本原因，等待确认后再动手

### 代码质量
- 发现重复代码: 主动指出并提议合并
- 发现死代码: 主动指出并建议删除
- 发现设计问题: 指出问题本质，提供重构建议

### 工作方式
- 不确定时: 询问确认，不要猜测
- 修改前: 先阅读理解现有代码
- 修改后: 说明改了什么、为什么改
- 发现无关问题: 指出但不"顺便"修复
- 学到项目新知识时: 主动提议更新 claude.md，需用户确认后才执行

### 交付标准
- 完整实现需求，不做简化版/演示版
- 不遗留 TODO 或"后续可以扩展"
- 代码可直接运行，不需要人工补充

### 验证方式
- 完成前必须验证: 运行测试/检查，确认无错误
- 验证失败时: 查看错误、修复、重新验证，循环直到通过
- 不要假设正确: 能验证的就验证，不要说"应该没问题"
- 新代码: 确认有对应测试
- 修改代码: 运行相关测试
- 删除代码: 确认无引用
- 测试中遇到错误则停止测试，分析原因修正错误，然后继续测试

## Python 特定规则

### LangChain 使用
- 必须使用 `create_agent` API (LangChain 1.x)
- 导入方式: `from langchain.agents import create_agent`
- 严禁使用旧版 API

### 代码风格
- 遵循 PEP8
- 使用类型提示 (Type Hints)
- 使用 f-string 格式化
- 禁止裸 except

### 工具实现
- 优先使用 LangChain 原生工具
- 自定义工具继承 `BaseTool`
- 所有工具必须有文档字符串 (description)

### 错误处理
- 使用特定异常捕获
- 禁止 `except:`
- 使用 `logger` 记录错误

## TypeScript 特定规则

### 类型系统
- 启用 strict 模式
- 禁止 `any`，使用 `unknown` + 类型守卫
- 禁止 `@ts-ignore`
- 使用 ES modules (import/export)

### React 组件
- 函数组件 + Hooks
- 使用 TypeScript 接口定义 props
- 避免不必要的 props drilling

### 状态管理
- 使用 Context API 管理全局状态
- 自定义 Hooks 封装复用逻辑
- 避免直接修改状态

## API 接口规范

### 后端 API
- RESTful 设计
- 使用 Pydantic 模型验证输入/输出
- SSE 流式接口使用 `StreamingResponse`
- 统一错误处理中间件

### 前端 API 客户端
- 封装在 `lib/api.ts`
- 统一错误处理
- 支持 SSE 事件解析
- 类型安全的请求/响应

## 测试规范

### 后端测试
- 使用 pytest
- 单元测试: 每个工具和函数
- 集成测试: API 端点
- E2E 测试: 完整对话流程
- 测试覆盖率目标: 80%+

### 前端测试
- 组件测试: React Testing Library
- Hooks 测试: @testing-library/react-hooks
- E2E 测试: Playwright
- 测试覆盖率目标: 70%+

### 测试文件命名
- 后端: `test_*.py` 或 `*_test.py`
- 前端: `*.test.ts` 或 `*.spec.ts`

## Agent Skills 特定规范

### Skills 定义
- 每个技能一个文件夹
- 必须包含 `SKILL.md` 文件
- 使用 Frontmatter 定义元数据
- 遵循 Instruction-following 范式

### SKILL.md 格式
```markdown
---
name: skill_name
description: 简短描述
---

# 技能名称

## 功能描述
详细描述这个技能做什么

## 使用步骤
1. 第一步
2. 第二步

## 示例
提供使用示例
```

### Skills 调用协议
- Agent 必须先 `read_file` 读取 SKILL.md
- 理解指令后再调用 Core Tools
- 禁止直接猜测技能参数

## System Prompt 组成

### 6 个组件 (按顺序)
1. SKILLS_SNAPSHOT.md - 动态生成的能力列表
2. SOUL.md - Agent 核心设定
3. IDENTITY.md - 自我认知
4. USER.md - 用户画像
5. AGENTS.md - 行为准则 & 技能调用协议
6. MEMORY.md - 长期记忆

### 截断策略
- 单文件超过 20k 字符需截断
- 添加 `...[truncated]` 标识

## 部署规范

### Docker
- 后端和前端分别构建镜像
- 使用 docker-compose 编排
- 支持本地开发环境挂载

### 环境变量
- 所有配置通过环境变量
- 提供 `.env.example` 模板
- 敏感信息不提交到代码库

### 本地运行
- 后端: uvicorn 直接运行
- 前端: npm run dev
- 支持热更新

## 格式要求

推荐使用:
- 标题标记（# ## ###）建立层级结构
- 列表符号（-）表示并列项
- 缩进表示层级关系
- 箭头符号（→）表示流程或映射
- 冒号（:）表示键值对
- 代码块仅用于命令示例或配置示例

避免使用:
- 过多的加粗或斜体标记
- 表情符号
- 纯装饰性的分隔线
- 复杂的表格（简单列表更易解析）

原则: 用 Markdown 建立结构帮助 AI 理解，但保持简洁，不过度装饰
