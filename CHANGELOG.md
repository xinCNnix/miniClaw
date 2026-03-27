# 变更日志 (CHANGELOG)

本文档记录 miniClaw 项目的所有重要变更。

---

## 2026-03-27 - v0.2.0: 架构升级与流式优化

本次更新为重大架构升级，引入模块化 Agent 组件、事件驱动流式架构、反思评估框架和自学习系统。

### 架构重构

**Agent 组件化拆分：**
- 将 Agent 执行逻辑拆分为 6 个独立模块 (`backend/app/core/agent_components/`)
  - `tool_assembler.py` - 工具调用组装，处理流式 JSON 增量合并
  - `tool_execution.py` - 工具执行策略（串行/并行）
  - `round_executor.py` - 单轮工具调用执行与事件生成
  - `stream_coordinator.py` - LLM 流式响应协调
  - `stopping_checker.py` - 智能停止机制
  - `error_tracker.py` - 错误追踪与恢复建议

**依赖注入容器：**
- `backend/app/core/container.py` - 轻量级 DI 容器，支持延迟初始化和单例管理
- `backend/app/core/interfaces.py` - Protocol 接口定义（LLMProvider, EmbeddingProvider, VectorStore 等）

**结构化错误处理：**
- `backend/app/core/exceptions.py` - 自定义异常层级（MiniClawError, AgentError, ToolExecutionError, LLMError 等）
- `backend/app/core/error_context.py` - 结构化错误日志，含调用栈、局部变量、错误签名
- `backend/app/core/callback_handler.py` - LangChain 回调处理器，轨迹追踪

### 流式响应架构

**事件驱动流式系统 (`backend/app/core/streaming/`)：**
- `events.py` - 事件类型定义（StreamEventType 枚举）
- `event_bus.py` - 异步事件总线（发布-订阅模式）
- `chunk_parser.py` - LLM 响应分块解析
- `response_aggregator.py` - 流式响应聚合
- `error_handler.py` - 流式错误处理
- `tool_executor.py` - 流式上下文中的工具执行
- `stream_coordinator.py` - 流式操作协调器

**调试支持：**
- `backend/app/core/streaming_debug_logger.py` - 流式调试日志，含性能计时和分块分析

### 反思评估系统

**统一评估框架 (`backend/app/core/reflection/`)：**
- `evaluator.py` - UnifiedEvaluator，区分微观评估（执行时）和宏观评估（执行后）
- `trigger.py` - ReflectionTrigger，避免微观和宏观触发重叠

### 自学习系统

**模式提取与学习 (`backend/app/memory/auto_learning/`)：**
- `extractor.py` - 从执行轨迹中提取模式
- `nn.py` - PatternNN 神经网络
- `memory.py` - 模式记忆存储与检索
- `graph_builder.py` - LangGraph 模式学习流程构建
- `nodes.py` - LangGraph 节点
- `streaming.py` - 流式模式提取
- `advanced/` - RL 强化学习模块（轨迹编码、策略头、奖励模型）
- `reflection/` - 反思驱动学习（策略映射、奖励模型）

**记忆模型：**
- `backend/app/memory/models.py` - Pattern, Trajectory, TrainingMetrics, RLExperience 模型

### ToT 缓存

- `backend/app/core/tot/cache.py` - TTL 工具结果缓存（默认 5 分钟），避免重复调用
- `backend/app/core/tracking_context.py` - 请求追踪上下文，关联同一请求的所有日志

### 前端改进

**公共组件 (`frontend/components/common/`)：**
- `ErrorBoundary.tsx` - React 错误边界，含重试机制
- `ToastContext.tsx` + `ToastProvider.tsx` - Toast 通知系统
- `Providers.tsx` - 应用级 Provider 封装

**Hook：**
- `frontend/hooks/useToast.tsx` - Toast 通知 Hook，支持 success/error/info/warning 类型

### 新增文件清单

**后端核心 (18 个文件)：**
- `backend/app/core/agent_components/` (6 个文件)
- `backend/app/core/callback_handler.py`
- `backend/app/core/container.py`
- `backend/app/core/error_context.py`
- `backend/app/core/exceptions.py`
- `backend/app/core/interfaces.py`
- `backend/app/core/reflection/` (3 个文件)
- `backend/app/core/streaming/` (7 个文件)
- `backend/app/core/streaming_debug_logger.py`
- `backend/app/core/tot/cache.py`
- `backend/app/core/tracking_context.py`

**记忆模块 (17 个文件)：**
- `backend/app/memory/models.py`
- `backend/app/memory/auto_learning/` (16 个文件)

**前端 (5 个文件)：**
- `frontend/components/common/` (4 个文件)
- `frontend/hooks/useToast.tsx`

### 配置与工具

- `backend/check_config.py` - 配置检查工具
- `.env.example` - 环境变量模板

### Skills 中文字体修复

修复 3 个绘图技能在中文环境下标题/文字显示为方框的问题：

**diagram-plotter：**
- 根因：DOT 代码仅在 `node`/`edge` 上设置 `fontname`，图级别标题（`label`）使用 Graphviz 默认字体
- 修复：新增 `detect_chinese_font()` 自动检测系统中文字体（Windows/macOS/Linux），图级别统一设置 `fontname`

**chart-plotter：**
- 根因：`plot_simple.py` 硬编码字体列表 `['SimHei', ...]`，无自动检测
- 修复：新增 `_detect_chinese_font()` 扫描系统字体目录，通过 `fm.fontManager.addfont()` 注册

**doc-creator：**
- 根因：XLSX/PPTX 输出未设置 CJK 字体，中文内容可能显示异常
- 修复：XLSX 标题和表头、PPTX 标题和内容页均使用 `_get_system_cjk_font()`

### 修改文件

- `backend/data/skills/diagram-plotter/scripts/diagram_plotter.py`
- `backend/data/skills/chart-plotter/scripts/plot_simple.py`
- `backend/data/skills/doc-creator/scripts/doc_creator.py`

### 向后兼容性

- 所有新功能通过配置开关控制
- 现有 API 端点保持不变
- Agent 基础接口兼容，内部实现重构

---

## 2025-03-20 - v0.1.0: Tree of Thoughts (ToT) 推理系统

### 功能概述

实现了完整的 Tree of Thoughts 推理系统，提供三种推理模式和深度研究能力。

**核心特性：**

1. **三种推理模式**
   - Heuristic (⚡): 快速启发式推理，适合简单任务
   - Analytical (🔬): 平衡的分析推理，适合中等复杂度
   - Exhaustive (🌌): 深度穷举推理，适合复杂任务

2. **智能停止机制**
   - 移植自 smart_stopping.py 的成熟机制
   - 检测工具调用冗余（3 轮窗口）
   - 检测信息充分性（≥5 个成功工具执行）
   - 检测质量得分饱和（最近 3 层提升 < 0.5）
   - 动态质量阈值调整（范围 [4.0, 8.0]）

3. **工具调用增强**
   - 工具调用验证和重试机制
   - 工具执行结果反馈到下一轮思考
   - 工具结果缓存（TTL 5 分钟）
   - 统计缓存命中率

4. **路径选择优化**
   - Beam Search 替代贪心算法
   - 综合评分：评估得分 (50%) + 工具成功率 (30%) + 信息多样性 (15%) + 路径长度惩罚 (5%)
   - 回溯机制（失败率 > 50% 或得分停滞时触发）

5. **研究模式**
   - 多阶段研究流程（规划→收集→分析→综合）
   - 知识库 + arXiv + 网络来源集成
   - 证据合成和交叉引用分析
   - 流式研究进度推送

### 新增文件

**ToT 核心模块：**
- `backend/app/core/tot/__init__.py`
- `backend/app/core/tot/state.py` - ToT 状态管理
- `backend/app/core/tot/router.py` - ToT 模式路由
- `backend/app/core/tot/graph_builder.py` - ToT 图构建
- `backend/app/core/tot/streaming.py` - ToT 流式处理
- `backend/app/core/tot/research_agent.py` - 研究模式代理
- `backend/app/core/tot/cache.py` - 工具结果缓存

**ToT 节点：**
- `backend/app/core/tot/nodes/__init__.py`
- `backend/app/core/tot/nodes/thought_generator.py` - 思考生成
- `backend/app/core/tot/nodes/thought_evaluator.py` - 思考评估
- `backend/app/core/tot/nodes/thought_executor.py` - 思考执行
- `backend/app/core/tot/nodes/termination_checker.py` - 终止检查

**ToT 研究模块：**
- `backend/app/core/tot/research/__init__.py`
- `backend/app/core/tot/research/nodes.py` - 研究节点

**性能和追踪：**
- `backend/app/core/performance_tracker.py` - 性能追踪器
- `backend/app/core/tracking_context.py` - 请求追踪上下文

**前端组件：**
- `frontend/components/chat/thought-tree.tsx` - 思考树可视化
- `frontend/components/chat/research-progress.tsx` - 研究进度显示

**文档：**
- `docs/TOT_IMPROVEMENT_PLAN.md` - ToT 改进计划

### 修改文件

**后端核心：**
- `backend/app/core/agent.py` - 集成 ToT 推理
- `backend/app/core/smart_stopping.py` - 移植到 ToT
- `backend/app/api/chat.py` - 支持 ToT 流式响应
- `backend/app/config.py` - 添加 ToT 配置项

**前端：**
- `frontend/components/chat/MessageBubble.tsx` - 显示 ToT 推理过程
- `frontend/hooks/useChat.ts` - 处理 ToT SSE 事件

### 配置项

```python
# ========== ToT 工具调用配置 ==========
tot_enable_tool_validation: bool = True
tot_max_tool_retries: int = 2

# ========== ToT 智能停止配置 ==========
tot_enable_smart_stopping: bool = True
tot_redundancy_window: int = 3
tot_sufficiency_interval: int = 5
tot_min_successful_tools: int = 5
tot_score_plateau_threshold: float = 0.5

# ========== ToT 动态阈值配置 ==========
tot_enable_dynamic_threshold: bool = True
tot_base_threshold: float = 6.0
tot_min_threshold: float = 4.0
tot_max_threshold: float = 8.0

# ========== ToT 路径选择配置 ==========
tot_enable_beam_search: bool = True
tot_beam_width: int = 3
tot_path_score_weights: dict = {
    "eval_score": 0.5,
    "tool_success": 0.3,
    "diversity": 0.15,
    "length_penalty": 0.05
}
tot_enable_backtracking: bool = True
tot_backtrack_failure_threshold: float = 0.5
tot_backtrack_plateau_threshold: float = 0.3

# ========== ToT 缓存配置 ==========
tot_enable_cache: bool = True
tot_cache_ttl: int = 300
```

### 性能影响

**预期收益：**
- 工具调用可靠性提升到 95% 以上
- 平均推理深度降低 20-30%
- 研究质量提升（评分提高 0.5-1.0 分）
- 缓存命中率 > 30%

**资源开销：**
- 缓存内存：约 10-50MB（取决于工具结果数量）
- 性能追踪：约 5MB
- 监控线程：每个执行实例约 1MB

### 向后兼容性

- 所有新功能通过配置开关控制
- 默认配置保持现有行为
- ToT 模式需要显式启用
- 不影响普通 Agent 模式

### 已知限制

1. ToT 模式消耗更多 tokens（需要更多 LLM 调用）
2. 复杂任务可能需要较长时间
3. 缓存在单次会话内有效（不支持持久化）
4. 回溯机制可能增加推理时间

### 后续优化方向

1. 支持缓存持久化（跨会话复用）
2. 前端可视化增强（高亮最佳路径）
3. 性能优化（并行思考生成）
4. 支持更多推理策略（A*、蒙特卡洛等）

---

## 2025-03-07 - 新增：完整的 E2E 测试框架

### 问题描述
之前的测试存在严重缺陷：
- 只有 Mock 测试，无法发现真实场景的 Bug
- 测试覆盖不足，缺少工具调用测试
- 单元测试和集成测试"通过"但实际运行失败

### 解决方案
创建完整的端到端（E2E）测试框架，使用 Playwright 进行真实场景测试。

**新增目录结构：**
```
tests/
├── e2e/                    # Playwright E2E 测试
│   ├── basic-chat.spec.ts
│   ├── tool-calling.spec.ts
│   └── session-management.spec.ts
├── fixtures/               # 测试数据和工具
│   ├── test-server.ts     # 后端启动/停止管理
│   └── test-data.ts       # 测试数据和场景
├── utils/                  # 测试工具函数
│   ├── helpers.ts         # 辅助函数
│   └── assertions.ts      # 自定义断言
├── run-e2e.sh             # Linux/Mac 测试运行脚本
├── run-e2e.bat            # Windows 测试运行脚本
└── README.md              # 测试文档
```

### 测试覆盖场景

**1. 基础对话测试 (basic-chat.spec.ts)**
- 简单文本对话
- SSE 流式响应验证
- 键盘快捷键（Enter/Shift+Enter）
- 对话历史管理
- 错误处理

**2. 工具调用测试 (tool-calling.spec.ts)** ⭐ 重点
- 单个工具调用（read_file, write_file, terminal, python_repl）
- 多工具连续调用
- 并发工具调用
- **OpenAI API 消息序列标准验证** ← 能发现之前的严重 bug
- **字段名验证（arguments vs args）** ← 能发现之前的 bug
- 工具错误处理
- 工具调用上下文持久化

**3. 会话管理测试 (session-management.spec.ts)**
- 创建新会话
- 切换会话
- 删除会话
- 会话数据持久化
- 会话元数据更新

### 核心功能

**测试工具函数：**
```typescript
// 发送消息并等待响应
await sendChatMessage(page, '读取 README.md')

// 等待工具调用
await waitForToolCalls(page, 1)

// 验证工具被调用
await expectToolCalled(page, 'read_file', {
  withArgs: true,
  argsMatch: /README/
})

// 验证 OpenAI API 标准符合性
await expectOpenAICompliantSequence(page)
```

**自定义断言：**
- `expectToolCalled()` - 验证工具被调用
- `expectOpenAICompliantSequence()` - 验证 OpenAI API 标准
- `expectSSEEventOrder()` - 验证 SSE 事件顺序
- `expectSuccessfulResponse()` - 验证成功响应

### 使用方式

**自动运行（推荐）：**
```bash
# Linux/Mac
chmod +x tests/run-e2e.sh
./tests/run-e2e.sh

# Windows
tests\run-e2e.bat
```

**手动运行：**
```bash
# 1. 启动后端
cd backend && uvicorn app.main:app --port 8002 --reload

# 2. 启动前端
cd frontend && npm run dev

# 3. 运行测试
cd frontend
npm run test:e2e
```

**运行特定测试：**
```bash
npx playwright test tool-calling
npx playwright test basic-chat
```

**调试模式：**
```bash
npx playwright test --debug
```

**查看报告：**
```bash
npx playwright show-report
```

### 与之前测试的对比

| 特性 | 之前的 Mock 测试 | 新的 E2E 测试 |
|------|----------------|--------------|
| 前后端交互 | ❌ 假的后端 | ✅ 真实后端 |
| LLM 调用 | ❌ Mock 数据 | ✅ 真实 LLM |
| 工具执行 | ❌ 假的工具 | ✅ 真实工具 |
| SSE 流式 | ❌ 未测试 | ✅ 完整测试 |
| Bug 发现能力 | ❌ 低 | ✅ 高 |
| 测试覆盖 | 简单场景 | 完整用户流程 |

### 能发现的 Bug 类型

通过这套 E2E 测试，可以发现：

1. ✅ **字段名不匹配** - `args` vs `arguments`
2. ✅ **消息序列错误** - 缺少带 `tool_calls` 的 AIMessage
3. ✅ **SSE 事件顺序** - thinking_start → tool_call → tool_output
4. ✅ **前后端数据格式不一致**
5. ✅ **工具执行失败** - 路径错误、权限问题
6. ✅ **会话数据丢失** - 持久化问题

### 修改的文件

**新增：**
- `tests/` - 完整测试目录
- `tests/e2e/*.spec.ts` - 3 个测试套件
- `tests/fixtures/*.ts` - 测试工具和数据
- `tests/utils/*.ts` - 辅助函数和断言
- `tests/run-e2e.sh` - Linux/Mac 运行脚本
- `tests/run-e2e.bat` - Windows 运行脚本
- `tests/README.md` - 测试文档

**修改：**
- `frontend/playwright.config.ts` - 更新测试目录路径

### 经验教训

**测试质量的重要性：**
- Mock 测试通过了 ≠ 没有bug
- 必须测试真实场景，不只是组件渲染
- E2E 测试是发现系统性问题的关键
- 工具调用是 Agent 的核心能力，必须充分测试

**OpenAI API 标准的重要性：**
- 所有主流 LLM 提供商都遵循此标准
- 消息格式必须严格符合要求
- E2E 测试能验证标准符合性

### 下一步改进

**可选的增强功能：**
1. 添加视觉回归测试
2. 添加性能测试
3. 集成到 CI/CD（GitHub Actions）
4. 添加测试覆盖率报告
5. 支持多 LLM 提供商的测试

---

## 2025-03-07 - Bug 修复：工具调用消息序列不符合 OpenAI API 标准

### 问题描述
使用任何 LLM 提供商进行工具调用时都会报错：
```
<400> InternalError.Algo.InvalidParameter: messages with role "tool" must be
a response to a preceeding message with "tool_calls".
```

### 根本原因
**违反 OpenAI API 标准**：在工具调用流程中，缺少带 `tool_calls` 的 assistant 消息。

**OpenAI API 要求的消息序列：**
```json
[
  {"role": "user", "content": "查询天气"},
  {"role": "assistant", "tool_calls": [...]},  ← 缺少这条！
  {"role": "tool", "tool_call_id": "...", "content": "..."},
  {"role": "assistant", "content": "今天晴天"}
]
```

**实际发送的序列：**
```json
[
  {"role": "user", "content": "查询天气"},
  {"role": "tool", "content": "..."}  ❌ 错误！前面没有带 tool_calls 的消息
]
```

### 影响范围
这是一个**系统性 Bug**，影响：
- ✅ 所有 LLM 提供商（OpenAI, 通义千问, DeepSeek, Claude, Gemini, Ollama 等）
- ✅ 所有使用工具调用的场景
- ✅ Agent 的 4 个方法：`invoke()`, `ainvoke()`, `stream()`, `astream()`

### 修复方案
**修改文件：**
- `backend/app/core/agent.py` - 4 个方法

**修复内容：**
在每个方法的工具调用处理中，添加带 `tool_calls` 的 AIMessage 到对话历史：

```python
# 修复前
if hasattr(response, 'tool_calls') and response.tool_calls:
    for tool_call in response.tool_calls:
        tool_output = self._execute_tool(...)
        lc_messages.append(ToolMessage(...))  # ❌ 缺少前面的 AIMessage

# 修复后
if hasattr(response, 'tool_calls') and response.tool_calls:
    lc_messages.append(response)  # ✅ 先添加带 tool_calls 的 AIMessage

    for tool_call in response.tool_calls:
        tool_output = self._execute_tool(...)
        lc_messages.append(ToolMessage(...))
```

**修复位置：**
1. `invoke()` 方法 - line 77-90
2. `ainvoke()` 方法 - line 116-127
3. `stream()` 方法 - line 154-189
4. `astream()` 方法 - line 240-272

### 为什么之前没发现？
1. **测试覆盖不足** - 没有测试工具调用场景
2. **历史数据都是简单对话** - 会话文件中没有工具调用记录
3. **Mock 数据不完整** - `test-utils.tsx` 缺少 `tool_call` 事件

### 经验教训
**测试质量问题的严重后果：**
- 测试通过了 ≠ 代码正确
- 需要测试**真实场景**，不只是快乐路径
- 工具调用是 Agent 的核心能力，必须充分测试

**OpenAI API 标准的重要性：**
- 所有主流 LLM 提供商都遵循此标准
- 消息格式必须严格符合要求
- 缺少任何必需字段都会导致错误

### 相关修复
- 同时修复了字段名不一致问题（`args` → `arguments`）
- 见上一个 bug 修复记录

---

## 2025-03-07 - Bug 修复：工具调用字段名不匹配

### 问题描述
Agent 调用工具时前端报错：
```
1 validation error for ChatEvent
tool_calls.0.args
  Field required [type=missing, input_value={'id': 'call_086c2433e2a0...'}]
```

### 根本原因
字段名三层不一致：
- **LangChain 标准**：`arguments` ✅
- **前端代码** (`useChat.ts:125`)：`toolCall.arguments` ✅
- **后端 Pydantic 模型** (`models/chat.py:72`)：`args` ❌

### 修复方案
**修改文件：**
- `backend/app/models/chat.py:72` - 将 `args` 改为 `arguments`

**修改内容：**
```python
# 之前
class ToolCall(BaseModel):
    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Tool name")
    args: dict = Field(..., description="Tool arguments")  # ❌

# 之后
class ToolCall(BaseModel):
    id: str = Field(..., description="Tool call ID")
    name: str = Field(..., description="Tool name")
    arguments: dict = Field(..., description="Tool arguments")  # ✅
```

### 影响
- ✅ Agent 工具调用现在正常工作
- ✅ 与 LangChain/OpenAI Function Calling 标准一致
- ✅ 前后端数据格式统一

### 经验教训
**测试质量问题：**
- 现有测试没有覆盖 `tool_call` 事件的 SSE 流
- Mock 数据 (`test-utils.tsx`) 只包含简单对话，缺少工具调用场景
- **测试通过了 ≠ 没有 bug**

**测试改进建议：**
```typescript
// 应该在 mockSSEEvents 中添加工具调用事件
export const mockSSEEventsWithToolCall = [
  'data: {"type":"thinking_start"}\n\n',
  'data: {"type":"tool_call","tool_calls":[{"id":"123","name":"read_file","arguments":{"path":"test.md"}}]}\n\n',
  'data: {"type":"done"}\n\n',
]
```

---

## 2025-03-07 - 启动脚本改进（健康检查）

### 问题描述
前端在启动时立即调用后端 API，但此时后端可能还在初始化中，导致 "Failed to fetch" 错误。

**原因：**
- 原启动脚本使用固定 3 秒延迟
- 后端首次启动需要安装依赖、加载模型等，时间不确定
- 前端的 `useEffect` 在组件挂载时立即调用 API

### 解决方案
改进启动脚本，添加健康检查机制，确保后端真正就绪后再启动前端。

**修改文件：**
- `start.bat` - Windows 启动脚本
- `start.sh` - Linux/Mac 启动脚本

**改进内容：**

1. **健康检查循环**
   - 每 2 秒检查一次后端 `/health` 端点
   - 最多等待 60 秒（30 次尝试）
   - 显示等待进度

2. **Windows 版本 (`start.bat`)**
   ```batch
   :wait_for_backend
   curl -s http://localhost:8002/health >nul 2>&1
   if %errorlevel% equ 0 (
       echo [OK] Backend is ready!
       goto :start_frontend
   )
   ```

3. **Linux/Mac 版本 (`start.sh`)**
   ```bash
   while [ $count -lt $max_attempts ]; do
       if curl -s http://localhost:8002/health > /dev/null 2>&1; then
           echo "[OK] Backend is ready!"
           break
       fi
       sleep 2
   done
   ```

4. **超时保护**
   - 超过 60 秒未启动成功则报错退出
   - 避免无限等待

5. **分步骤提示**
   - Step 1/3: 启动后端
   - Step 2/3: 等待后端就绪
   - Step 3/3: 启动前端

**效果：**
- ✅ 消除前端启动时的 API 调用失败
- ✅ 用户友好的进度提示
- ✅ 明确的错误提示
- ✅ 适配不同机器的启动速度

---

## 2025-03-07 - 安全增强与工具扩展

### 安全性改进

#### 1. API Key 混淆加密存储

**问题：** 用户使用环境变量存储 API key，容易被 Agent 工具通过提示词注入等方式泄露。

**解决方案：** 实现了基于设备指纹的混淆加密存储方案。

**新增文件：**
- `backend/app/core/obfuscation.py` - 混淆加密核心模块
  - 使用 SHA256 基于机器特征生成混淆密钥
  - XOR + Base64 编码存储
  - 版本化存储格式（v1:data:checksum）

**修改文件：**
- `backend/app/config.py` - 支持从加密文件加载 API key
  - 启动时自动解密到环境变量
  - 环境变量优先级更高

**安全效果：**
- ✅ Agent 工具（read_file、terminal）无法读取明文
- ✅ 防止提示词注入泄露
- ✅ 换电脑后密钥自动失效

---

#### 2. 域名白名单机制

**新增文件：**
- `backend/app/core/trusted_domains.py` - 域名白名单配置
  - 预置 6 家可信 LLM 服务商域名
  - 提供 `is_trusted_domain()` 检查函数

**预置可信域名：**
```python
- api.openai.com - OpenAI
- dashscope.aliyuncs.com, api.aliyun.com - 通义千问
- api.deepseek.com - DeepSeek
- api.anthropic.com - Claude
- generativelanguage.googleapis.com - Google Gemini
- localhost, 127.0.0.1 - 本地开发
```

**新增 API：**
- `POST /api/config/save` - 保存 API key 配置（自动混淆加密）
- `GET /api/config/status` - 查询配置状态
- `DELETE /api/config/{provider}` - 删除提供商配置
- `POST /api/config/check-domain` - 检查域名是否可信

**前端集成：**
- 更新 `frontend/components/layout/SettingsDialog.tsx`
- 新增功能：
  - 已配置提供商列表显示
  - 保存 API key 到加密存储
  - 非白名单域名确认对话框
  - 删除配置功能
- 更新 `frontend/lib/api.ts` - 添加配置相关 API 调用方法

---

#### 3. 错误消息过滤

**修改文件：**
- `backend/app/main.py`

**新增功能：**
- `_sanitize_error_message()` 函数
  - 过滤 API key（sk-xxx, sk-ant-xxx 等）
  - 过滤 Bearer tokens
  - 过滤 URL 中的 key 参数

**效果：**
- 即使 debug 模式，错误响应也不泄露敏感信息

---

#### 4. .gitignore 更新

**修改文件：**
- `.gitignore`

**新增规则：**
```gitignore
# 敏感配置文件
.env
.env.local
.env.*.local

# 加密凭证文件
data/credentials.encrypted
data/credentials.json
*.key
```

---

### 工具扩展

#### 5. write_file 工具

**新增文件：**
- `backend/app/tools/write_file.py` - 安全的文件写入工具

**功能：**
- 支持覆盖模式（overwrite）和追加模式（append）
- 自动创建父目录
- 文件大小检查（无硬性限制）
- 敏感文件保护（无法覆盖 .env、credentials.encrypted 等）
- 写入后验证

**安全特性：**
- 路径限制（项目目录内）
- 路径遍历防护
- 二进制文件阻止

**修改文件：**
- `backend/app/tools/__init__.py` - 注册新工具

**工具数量变化：** 5 个 → **6 个**

**完整工具列表：**
1. read_file - 读取文件
2. write_file - 写入文件（新增）
3. terminal - 执行命令
4. python_repl - 执行 Python 代码
5. fetch_url - 获取网页内容
6. search_kb - 搜索知识库

---

### Python REPL 大幅增强

#### 问题
原 python_repl 工具功能受限：
- 无法写入文件
- 固定的 30 秒超时
- 硬编码的内存限制
- 无法生成复杂文件（PPT、Excel 等）

#### 解决方案：方案 F - 动态内存限制 + 实时监控

**重写文件：**
- `backend/app/tools/python_repl.py` - 完全重写

**新增功能：**

**1. 文件 I/O 支持**
- 在受控目录内可以读写文件
- 覆盖了原 write_file 的功能，但更强大（可以直接在 Python 中操作）

**允许的目录：**
- 项目根目录（默认）
- 用户配置的额外目录（`ALLOWED_WRITE_DIRS`）

**安全保护：**
- 无法访问敏感文件（.env、credentials.encrypted）
- 路径遍历防护
- 二进制文件阻止

**2. 三种执行模式**

| 模式 | 超时 | 内存 | 操作限制 | 适用场景 |
|-----|------|------|---------|---------|
| safe | 60秒 | 20% 可用内存 | 100万次 | 测试、探索 |
| standard | 5分钟 | 50% 可用内存 | 1000万次 | 日常使用（默认） |
| free | 30分钟 | 80% 可用内存 | 无限 | 大型任务 |

**3. 动态内存限制**
```
基于可用内存自动计算：
- 16GB 机器（8GB 可用）：standard = 4GB 限制
- 64GB 机器（32GB 可用）：standard = 16GB 限制
```

**4. 操作计数（防止死循环）**
- 使用 sys.settrace 计数代码执行行数
- 超过限制自动中断
- safe: 100万次、standard: 1000万次、free: 无限

**5. 实时监控线程**
- 定期检查执行时间和内存使用
- 超过阈值时显示警告
- 用户可随时中断

**新增 API：**
- `POST /api/python_repl/stop` - 停止执行
- `GET /api/python_repl/status` - 查询执行状态
- `GET /api/python_repl/resources` - 查询系统资源
- `GET /api/python_repl/config` - 查询配置
- `POST /api/python_repl/update_dirs` - 更新允许的目录

**新增依赖：**
- `requirements.txt` - 添加 `psutil>=5.9.0`（系统监控）

**配置项（backend/app/config.py）：**
```python
allowed_write_dirs: list[str]  # 额外的可写入目录
python_execution_mode: Literal["safe", "standard", "free"]
python_safe_timeout: int = 60
python_standard_timeout: int = 300
python_free_timeout: int = 1800
python_safe_memory_ratio: float = 0.2
python_standard_memory_ratio: float = 0.5
python_free_memory_ratio: float = 0.8
python_safe_max_operations: int = 1_000_000
python_standard_max_operations: int = 10_000_000
python_free_max_operations: int = 0  # 0 = unlimited
python_monitor_interval: int = 5
python_warning_threshold: float = 0.7
```

---

### 文档更新

**新增文档：**
- `docs/API_KEY_OBFUSCATION.md` - API key 加密方案说明
- `docs/TOOLS_UPDATE.md` - 工具列表更新说明
- `docs/PYTHON_REPL_ENHANCEMENT.md` - Python REPL 增强功能说明
- `backend/.env.example` - 完整的配置示例

**修改文件：**
- `frontend/lib/api.ts` - 添加配置 API 调用方法
- `frontend/components/layout/SettingsDialog.tsx` - 集成加密配置功能

---

## 架构设计原则

### Tools vs Skills 职责划分

```
┌─────────────────────────────────────┐
│  用户需求（生成 PPT/Excel/PDF/图片） │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  Skills 系统处理                     │
│  - generate_ppt                      │
│  - generate_excel                    │
│  - generate_report                   │
└────────────┬────────────────────────┘
             │
             ▼
┌─────────────────────────────────────┐
│  基础工具（Tools）提供原子能力       │
│  - read_file: 读文件                │
│  - write_file: 写文件               │
│  - python_repl: 执行代码            │
│  - terminal: 执行命令               │
│  - fetch_url: 获取网页               │
│  - search_kb: 搜索知识库            │
└─────────────────────────────────────┘
```

**核心原则：**
- Tools = 基础能力（保持简洁，不随意增加）
- Skills = 业务逻辑（无限扩展，通过组合基础工具实现）

---

## API 端点变更

### 新增端点

#### 配置管理（/api/config）
- `POST /api/config/save` - 保存 LLM 配置（混淆加密）
- `GET /api/config/status` - 查询配置状态
- `DELETE /api/config/{provider}` - 删除提供商配置
- `POST /api/config/check-domain` - 检查域名是否可信

#### Python REPL 控制（/api/python_repl）
- `POST /api/python_repl/stop` - 停止执行
- `GET /api/python_repl/status` - 查询执行状态
- `GET /api/python_repl/resources` - 查询系统资源
- `GET /api/python_repl/config` - 查询配置
- `POST /api/python_repl/update_dirs` - 更新允许的目录

---

## 安全性总结

### 多层防护机制

| 威胁类型 | 防护措施 | 状态 |
|---------|---------|------|
| Agent read_file 读取敏感文件 | 路径限制 + 敏感文件屏蔽 | ✅ |
| Agent terminal cat .env | 命令级别阻止 | ✅ |
| 提示词注入读取 key | 存储文件为混淆密文 | ✅ |
| API key 通过错误消息泄露 | 错误消息过滤 | ✅ |
| 恶意域名劫持 | 域名白名单 + 用户确认 | ✅ |
| 路径遍历攻击 | 路径解析限制 | ✅ |
| 死循环耗尽 CPU | 超时 + 操作计数 | ✅ |
| 内存溢出 | 动态内存限制 + 监控 | ✅ |
| 写入系统文件 | 目录白名单 + 敏感文件保护 | ✅ |

### 用户数据保护

| 保护措施 | 说明 |
|---------|------|
| 混淆加密存储 | API key 使用设备指纹加密 |
| 工具权限控制 | Agent 无法读取敏感文件 |
| 域名验证 | 非白名单域名需用户确认 |
| 错误过滤 | 错误消息自动过滤敏感信息 |
| Git 保护 | 加密文件已在 .gitignore 中 |

---

## 向后兼容性

### 破坏性变更

**无破坏性变更。**

所有变更向后兼容：
- ✅ 环境变量优先级更高（兼容现有 .env 配置）
- ✅ 新增功能为可选（默认不启用）
- ✅ 原 API 端点保持不变

### 迁移路径

**从 .env 迁移到加密存储（可选）：**
```
# 步骤 1：备份 .env
cp .env .env.backup

# 步骤 2：在前端设置页面输入 API key
# 系统会自动加密存储

# 步骤 3：确认加密存储工作后，删除 .env 中的 key
# 或者保留 .env 作为备用
```

---

## 配置示例

### 完整的 .env 配置

```bash
# ===== LLM 配置 =====
LLM_PROVIDER=qwen
# QWEN_API_KEY=sk-your-key（建议通过前端界面配置）

# ===== Python REPL 配置 =====
PYTHON_EXECUTION_MODE=standard

# 额外的可写入目录（可选）
# ALLOWED_WRITE_DIRS=["C:/Users/YourName/Documents", "D:/Workspace"]

# ===== 调试模式 =====
DEBUG=false
```

---

## 使用示例

### 生成 Excel 报告

```python
# Agent 使用 free 模式生成大型 Excel
python_repl: mode=free, code="""
import pandas as pd

# 生成 100万行数据
data = {
    'id': range(1000000),
    'value': range(1000000)
}

df = pd.DataFrame(data)
df.to_excel('large_report.xlsx')

print(f'生成完成：{len(df)} 行')
"""
```

### 生成 PPT 演示文稿

```python
# Agent 生成 PPT
python_repl: mode=free, code="""
from pptx import Presentation

prs = Presentation()
slide = prs.slides.add_slide(prs.slide_layouts[0])
slide.shapes.title.text = '项目总结'
prs.save('presentation.pptx')
print('PPT 生成完成')
"""
```

### 批量文件处理

```python
# Agent 批量处理文件
python_repl: mode=standard, code="""
import os
from pathlib import Path

# 处理所有 txt 文件
for file in Path('data').glob('*.txt'):
    with open(file, 'r') as f:
        content = f.read()

    # 处理内容
    processed = content.upper()

    # 保存结果
    output_file = Path('output') / f"{file.stem}_processed.txt"
    output_file.write_text(processed)

print(f'处理完成：{len(list(Path('data').glob('*.txt')))} 个文件')
"""
```

---

## 性能影响

### 内存开销
- psutil 库：~5MB
- 监控线程：每个执行实例 ~1MB
- 总开销：可忽略

### 启动时间
- 无明显影响

### 执行性能
- 操作计数：~1-2% 性能开销
- 内存监控：线程检查间隔 5 秒，开销极低

---

## 已知限制

### 1. 操作计数性能
- 启用操作计数会有轻微性能影响（~1-2%）
- free 模式下无限制，性能最优

### 2. Windows 信号处理
- Windows 不支持 SIGALRM，使用监控线程替代
- 功能完全相同，无影响

### 3. 文件 I/O 限制
- 只能在项目目录和用户配置的目录内操作
- 需要提前配置 `ALLOWED_WRITE_DIRS`

---

## 后续优化方向

### 可能的改进
1. 前端实时显示执行进度（SSE 推送）
2. 执行历史记录和重放
3. Python 代码自动保存和恢复
4. 集成 Jupyter Notebook 支持

### 待讨论
1. 是否需要代码模板功能
2. 是否需要协作功能（多用户共享命名空间）
3. 是否需要更多编程语言支持（JavaScript、R 等）

---

## 总结

本次更新实现了：

✅ **安全性大幅提升**
- API key 混淆加密存储
- 多层防护机制
- 域名白名单验证

✅ **功能大幅增强**
- 新增 write_file 工具
- Python REPL 支持文件 I/O
- 三种执行模式适应不同场景

✅ **架构更加清晰**
- Tools = 基础能力（6 个，不随意增加）
- Skills = 业务逻辑（无限扩展）

✅ **用户体验优化**
- 前端设置界面集成
- 实时监控和中断
- 自适应机器配置

**miniClaw 现在拥有完整的文件处理能力和强大的 Python 运行环境，可以通过 Skills 扩展出无限可能！**

---

*最后更新：2026-03-27*
