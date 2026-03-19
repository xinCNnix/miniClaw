# Agent 主动性和反思机制增强计划

## 背景

miniClaw 项目的 Agent 目前缺乏主动性和反思能力，具体表现为：
- **被动响应**：完全依赖用户触发，不会主动发现问题或提出建议
- **无自我审查**：输出生成后不检查质量
- **无主动提问**：遇到模糊指令不会主动澄清
- **无元认知**：不思考"为什么这样做"以及是否有更好的方法

本计划通过三个阶段逐步增强 Agent 的主动性和反思能力，同时保持架构一致性和向后兼容性。

## 现有可复用组件

经代码探索发现以下可复用的机制：

1. **评估框架** (`backend/app/core/tot/nodes/thought_evaluator.py`)
   - 多维度评分系统（相关性40%、可行性40%、新颖性20%）
   - LLM 评分解析（支持 JSON 和正则回退）
   - 质量阈值判断（6.0分）

2. **触发机制** (`backend/app/core/smart_stopping.py`)
   - 规则触发模式（简单问候、冗余检测、充分性评估）
   - 配置化窗口和间隔
   - 与 agent loop 的集成点

3. **记忆系统** (`backend/app/memory/`)
   - MemoryDB 已有 `confidence` 和 `importance_score` 字段
   - 自动学习管道（extractor, long_term_updater）

4. **配置管理** (`backend/app/config.py`)
   - 环境变量驱动
   - Feature toggles 支持渐进式推出

## Phase 1: 快速增强 (1-2周)

### 1.1 输出质量反思检查点

**目标**：在响应生成后自动评估质量，捕获低质量输出。

**实现**：

创建 `backend/app/core/reflection/output_evaluator.py`：

```python
class OutputQualityEvaluator:
    """评估 agent 响应质量的多维度评分器"""

    # 评分标准（复用 thought_evaluator 模式）
    # - Relevance (40%): 是否直接回答用户问题
    # - Completeness (30%): 回答是否全面
    # - Accuracy (20%): 是否有事实错误
    # - Clarity (10%): 表述是否清晰

    def __init__(
        self,
        llm: BaseChatModel,
        quality_threshold: float = 6.5,
        enable_auto_reflection: bool = True
    )

    async def evaluate_output(
        self,
        user_query: str,
        agent_response: str,
        tool_results: list,
        round_count: int
    ) -> Dict[str, Any]
```

**集成点**：`backend/app/core/agent.py:376`（最终响应生成后）

```python
# 在 astream() 方法中，响应生成后添加：

if settings.enable_output_reflection:
    evaluator = OutputQualityEvaluator(llm=self.llm, ...)
    evaluation = await evaluator.evaluate_output(...)

    yield {
        "type": "reflection",
        "quality_score": evaluation["overall_score"],
        "should_regenerate": evaluation["should_regenerate"]
    }

    # 可选：低质量时自动重新生成
    if evaluation["should_regenerate"] and round_count < max_tool_rounds - 1:
        # 添加反思作为反馈，继续下一轮
        continue
```

**配置** (`config.py`)：
```python
enable_output_reflection: bool = True
output_quality_threshold: float = 6.5
enable_auto_reflection_regenerate: bool = False  # 保守默认值
reflection_max_regen_rounds: int = 1
```

### 1.2 主动提问触发器

**目标**：检测模糊查询并主动提出澄清问题。

**实现**：

创建 `backend/app/core/reflection/proactive_trigger.py`：

```python
class ProactiveQuestionTrigger:
    """检测模糊查询并触发主动提问"""

    AMBIGUITY_PATTERNS = [
        r"这个|那个|它",  # 无上下文的指示代词
        r"怎么.*",  # 开放式"如何"问题
        r"帮我.*",  # 泛化的"帮助"请求
    ]

    def should_ask_question(
        self,
        user_query: str,
        context: Dict,
        round_count: int
    ) -> tuple[bool, str, List[str]]
```

**集成点**：`backend/app/core/agent.py:283`（工具执行循环前）

```python
# 在 astream() 方法开始处添加：

if settings.enable_proactive_questions:
    trigger = ProactiveQuestionTrigger(...)
    should_ask, reason, questions = trigger.should_ask_question(...)

    if should_ask:
        yield {
            "type": "proactive_question",
            "reason": reason,
            "questions": questions
        }

        # 生成澄清响应
        # ... 返回 done
```

**配置** (`config.py`)：
```python
enable_proactive_questions: bool = True
proactive_ambiguity_detection: bool = True
proactive_gap_detection: bool = True
proactive_min_confidence: float = 0.6
```

### Phase 1 测试

- `backend/tests/test_reflection/test_output_evaluator.py`
- `backend/tests/test_reflection/test_proactive_trigger.py`

## Phase 2: 架构升级 (3-4周)

### 2.1 元认知层接口

**目标**：设计清晰的元认知操作接口。

**实现**：

创建 `backend/app/core/metacognition/interface.py`：

```python
class MetacognitiveOperation(ABC):
    """元认知操作基类"""

    @abstractmethod
    async def execute(self, state: Dict, context: Dict) -> Dict:
        """执行元认知操作"""

    @abstractmethod
    def should_trigger(self, state: Dict) -> bool:
        """判断是否应触发"""


class MetacognitionLayer:
    """编排多个元认知操作"""

    async def process(
        self,
        state: Dict[str, Any],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]
```

**具体操作**：

创建 `backend/app/core/metacognition/operations/`：

- `reflection_operation.py` - 反思操作（每N轮或失败时触发）
- `planning_operation.py` - 规划操作（复杂查询开始时触发）

**集成**：修改 `backend/app/core/agent.py`

```python
class AgentManager:
    def __init__(self, ...):
        # 初始化元认知层
        if settings.enable_metacognition_layer:
            operations = [
                ReflectionOperation(...),
                PlanningOperation(...)
            ]
            self.metacognition = MetacognitionLayer(...)

    async def astream(self, messages, system_prompt):
        # 每轮后执行元认知检查
        if self.metacognition:
            state = {...}  # 收集状态
            results = await self.metacognition.process(state, context)

            # 发送元认知事件
            for result in results:
                yield {"type": "metacognition", "operation": result["type"], ...}
```

**配置**：
```python
enable_metacognition_layer: bool = True
metacognition_operations: list = ["reflection", "planning"]
reflection_interval: int = 3
planning_complexity_threshold: float = 0.7
```

### 2.2 ToT 反思节点

**目标**：在 ToT 图中添加反思节点。

**实现**：

创建 `backend/app/core/tot/nodes/reflection_node.py`：

```python
async def reflection_node(state: ToTState) -> ToTState:
    """反思当前推理路径并建议改进"""

    # 评估当前最佳路径
    # 识别弱点或缺陷
    # 建议新的思考方向
    # 更新推理追踪
```

**集成**：修改 `backend/app/core/tot/graph_builder.py`

```python
# 添加反思节点到图
graph.add_node("reflect", reflection_node)
graph.add_edge("evaluate_thoughts", "reflect")
graph.add_edge("reflect", "should_terminate")
```

**配置**：
```python
enable_tot_reflection: bool = True
tot_reflection_depth: int = 2  # 每N层深度反思一次
```

### 2.3 增强记忆系统

**目标**：存储和检索反思以实现长期学习。

**实现**：

创建 `backend/app/memory/reflection_store.py`：

```python
class ReflectionStore:
    """存储和检索 agent 反思"""

    def store_reflection(
        self,
        session_id: str,
        trigger_type: str,
        insights: List[Dict],
        user_query: str = "",
        action_taken: str = None
    ) -> str

    def get_similar_reflections(
        self,
        user_query: str,
        trigger_type: str = None,
        limit: int = 5
    ) -> List[Dict]
```

**数据库模式**：
```sql
CREATE TABLE reflections (
    reflection_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    trigger_type TEXT NOT NULL,
    insights TEXT NOT NULL,  -- JSON
    action_taken TEXT,
    effectiveness REAL,
    user_query TEXT
);
```

**集成**：在反思操作后存储

```python
# 在 agent.py 反思操作后
if settings.enable_reflection_learning:
    reflection_store = ReflectionStore()
    reflection_id = reflection_store.store_reflection(...)
    yield {"type": "reflection_stored", "reflection_id": reflection_id}
```

**配置**：
```python
enable_reflection_learning: bool = True
reflection_store_path: str = "data/reflections.db"
```

### Phase 2 测试

- `backend/tests/test_metacognition/test_reflection_operation.py`
- `backend/tests/test_metacognition/test_planning_operation.py`
- `backend/tests/test_tot/test_reflection_node.py`
- `backend/tests/test_memory/test_reflection_store.py`

## Phase 3: 高级特性 (4-5周)

### 3.1 多轮自我辩论

**目标**：通过自我辩论评估竞争方案。

**实现**：

创建 `backend/app/core/metacognition/operations/debate_operation.py`：

```python
class SelfDebateOperation(MetacognitiveOperation):
    """通过自我辩论评估竞争方案"""

    async def execute(self, state, context):
        # 1. 生成2-3个竞争方案
        approaches = await self._generate_approaches(...)

        # 2. 辩论优劣
        debate_result = await self._debate_approaches(...)

        # 3. 选择胜者
        return {
            "type": "self_debate",
            "approaches": approaches,
            "selected_approach": debate_result["winner"]
        }
```

**触发条件**：包含 "compare", "best", "should", "recommend", "vs" 等关键词的查询。

**配置**：
```python
enable_self_debate: bool = True
self_debate_min_approaches: int = 2
self_debate_max_approaches: int = 3
```

### 3.2 主动规划系统

**目标**：预测用户需求并提前规划。

**实现**：

创建 `backend/app/core/metacognition/proactive_planner.py`：

```python
class ProactivePlanner:
    """预测用户需求并生成主动建议"""

    async def generate_proactive_suggestions(
        self,
        user_query: str,
        agent_response: str,
        context: Dict
    ) -> List[Dict]:
        """预测后续问题并建议相关主题/工具"""

        # 1. 预测后续问题
        follow_ups = await self._predict_follow_ups(...)

        # 2. 建议相关主题/技能
        related = await self._suggest_related(...)

        return follow_ups + related
```

**集成**：响应生成后

```python
# 在 agent.py 最终响应后
if settings.enable_proactive_planning:
    suggestions = await planner.generate_proactive_suggestions(...)
    yield {"type": "proactive_suggestions", "suggestions": suggestions}
```

**配置**：
```python
enable_proactive_planning: bool = True
proactive_max_suggestions: int = 3
```

### 3.3 错误学习机制

**目标**：从错误中学习以防止未来失败。

**实现**：

创建 `backend/app/core/metacognition/error_learning.py`：

```python
class ErrorLearningSystem:
    """从错误中学习以改进未来性能"""

    async def learn_from_error(
        self,
        error: Exception,
        context: Dict
    ) -> Dict:
        """分析错误并提取学习"""

        # 1. 分析错误根因
        analysis = await self._analyze_error(error, context)

        # 2. 检查模式
        is_pattern = await self._check_pattern(analysis)

        # 3. 生成预防策略
        if is_pattern:
            prevention = await self._generate_prevention(analysis)

        # 4. 存储学习
        await self._store_learning(analysis)
```

**集成**：异常处理中

```python
# 在 agent.py 工具执行异常处理中
try:
    # ... 工具执行 ...
except Exception as e:
    if settings.enable_error_learning:
        learning = await error_learner.learn_from_error(e, context)
        yield {"type": "error_learning", "learning": learning}
```

**配置**：
```python
enable_error_learning: bool = True
error_pattern_threshold: int = 2  # 最少出现次数才算模式
```

### Phase 3 测试

- `backend/tests/test_metacognition/test_debate_operation.py`
- `backend/tests/test_metacognition/test_proactive_planner.py`
- `backend/tests/test_metacognition/test_error_learning.py`
- `backend/tests/test_integration/test_error_learning_loop.py`

## 关键文件清单

### 新增文件

**Phase 1**：
- `backend/app/core/reflection/__init__.py`
- `backend/app/core/reflection/output_evaluator.py`
- `backend/app/core/reflection/proactive_trigger.py`
- `backend/tests/test_reflection/`

**Phase 2**：
- `backend/app/core/metacognition/__init__.py`
- `backend/app/core/metacognition/interface.py`
- `backend/app/core/metacognition/operations/__init__.py`
- `backend/app/core/metacognition/operations/reflection_operation.py`
- `backend/app/core/metacognition/operations/planning_operation.py`
- `backend/app/core/tot/nodes/reflection_node.py`
- `backend/app/memory/reflection_store.py`
- `backend/tests/test_metacognition/`

**Phase 3**：
- `backend/app/core/metacognition/operations/debate_operation.py`
- `backend/app/core/metacognition/proactive_planner.py`
- `backend/app/core/metacognition/error_learning.py`

### 修改文件

- `backend/app/core/agent.py` - 主要集成点
- `backend/app/core/tot/graph_builder.py` - 添加反思节点
- `backend/app/config.py` - 添加所有新配置
- `frontend/types/chat.ts` - 添加新事件类型
- `frontend/components/chat/` - 新增UI组件（可选）

## 性能优化策略

1. **批量反思**：不评估每个输出，使用采样
2. **缓存**：缓存相似查询的反思结果
3. **异步执行**：并行运行独立的反思操作
4. **智能触发**：基于规则仅在必要时触发

```python
# 反思缓存示例
class ReflectionCache:
    def get(self, key: str) -> Optional[Any]
    def set(self, key: str, value: Any)
    @staticmethod
    def generate_key(user_query: str, agent_response: str, operation_type: str) -> str
```

## 前端集成

### 新事件类型 (`frontend/types/chat.ts`)

```typescript
type ChatEvent =
  | { type: "reflection"; quality_score: number; should_regenerate: boolean }
  | { type: "proactive_question"; reason: string; questions: string[] }
  | { type: "metacognition"; operation: string; data: any }
  | { type: "proactive_suggestions"; suggestions: Suggestion[] }
  | { type: "error_learning"; learning: any };
```

### 可选UI组件

- `reflection-indicator.tsx` - 显示反思状态
- `proactive-question.tsx` - 显示澄清问题
- `suggestion-card.tsx` - 显示主动建议
- `metacognition-trace.tsx` - 可视化元认知过程

## 实施时间线

**Phase 1** (Week 1-2)：快速增强
- Day 1-3: 输出质量评估器
- Day 4-5: 主动提问触发器
- Day 6-7: 集成测试
- Day 8-10: Bug修复和优化

**Phase 2** (Week 3-6)：架构升级
- Week 3: 元认知层接口
- Week 4: 反思和规划操作
- Week 5: ToT反思节点
- Week 6: 增强记忆系统

**Phase 3** (Week 7-11)：高级特性
- Week 7-8: 多轮自我辩论
- Week 9: 主动规划系统
- Week 10: 错误学习机制
- Week 11: 集成和E2E测试

## 推出策略

1. **Feature Flags**：所有功能通过配置开关控制
2. **渐进启用**：从 Phase 1 开始，监控指标
3. **A/B测试**：对比反思版和非反思版 agent
4. **性能监控**：跟踪 LLM 调用次数、延迟、质量
5. **用户反馈**：收集主动行为的定性反馈

## 成功指标

### 质量指标
- 输出质量评分提升（目标：+15%）
- 用户满意度（目标：+20%）
- 错误率降低（目标：-30%）

### 性能指标
- 额外 LLM 调用（目标：< 2次/请求）
- 延迟影响（目标：< 20%增长）
- 内存使用（目标：< 100MB 额外）

### 行为指标
- 主动提问准确率（目标：> 70%相关）
- 反思重新生成有效性（目标：> 60%改进）
- 错误预防率（目标：> 40%复发错误被阻止）

## 验证方式

### 单元测试
```bash
cd backend
pytest tests/test_reflection/ -v
pytest tests/test_metacognition/ -v
```

### 集成测试
```bash
pytest tests/test_integration/test_reflection_pipeline.py -v
pytest tests/test_integration/test_metacognition.py -v
```

### 手动验证
1. 启动后端：`cd backend && uvicorn app.main:app --port 8002 --reload`
2. 启动前端：`cd frontend && npm run dev`
3. 测试场景：
   - 模糊查询 → 应触发主动提问
   - 简单问候 → 不应调用工具
   - 复杂查询 → 应启用 ToT 并显示反思
   - 工具失败 → 应显示错误学习

### 日志验证
检查 `backend/logs/agent.log` 中的反思标记：
```
[REFLECTION] Output quality: 6.80, should_regenerate: False
[PROACTIVE] Asking clarifying question: 检测到查询中存在不明确的指代
[METACOGNITION] Executing ReflectionOperation
```

## 风险缓解

1. **过度反思**：通过配置限制反思频率和深度
2. **性能下降**：实施智能缓存和批量处理
3. **用户困惑**：添加UI提示解释主动行为
4. **LLM成本**：监控使用量，设置配额限制

## 回滚计划

每个 Phase 独立可控，可通过配置禁用：

```python
# 快速回滚所有新功能
enable_output_reflection: bool = False
enable_proactive_questions: bool = False
enable_metacognition_layer: bool = False
enable_tot_reflection: bool = False
enable_self_debate: bool = False
enable_proactive_planning: bool = False
enable_error_learning: bool = False
```
