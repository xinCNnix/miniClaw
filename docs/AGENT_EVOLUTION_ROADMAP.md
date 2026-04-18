# miniClaw Agent 中长期演进方案

## Context

本方案旨在为 miniClaw 项目设计一个切实可行、分阶段实施的自我进化能力路线图，整合用户提供的7个核心类的功能：

1. **ReflectionReward** - 反思奖励机制（GRPO + 自我评估）
2. **AdaptiveMemorySystem** - 自适应记忆聚类和组织
3. **EpistemicController** - 认知控制（策略选择）
4. **ReasoningRouter** - 推理路由（问题分配）
5. **SelfCorrectionPlanner** - 自我纠正规划
6. **ReflectiveExperienceLearner** - 反思经验学习
7. **LifelongEvolutionEngine** - 终身学习进化引擎

## 现有架构基础

miniClaw 已具备良好的技术基础：

**✅ 已实现的核心能力**：
- Tree of Thoughts (ToT) 推理系统（`backend/app/core/tot/`）
- 多轮工具调用 + 并发执行（`backend/app/core/agent.py`）
- 流式 SSE 响应
- 双存储记忆系统（SQLite + ChromaDB）
- LLM 驱动的记忆提取
- Research 模式（多源信息整合）

**技术栈**：
- LangChain 1.x + LangGraph
- LlamaIndex (RAG)
- FastAPI + Next.js 14
- Pydantic 2.x

**⚠️ 缺失能力**：
- 强化学习框架
- 性能评估系统
- 用户反馈收集
- 经验回放机制

---

## 演进路线图

### Phase 1: 基础增强（1-2个月）

**目标**：建立评估和反馈基础设施

#### 1.1 性能评估系统（优先级：最高）

**新建文件**：
- `backend/app/core/evaluation/metrics.py` - 评估指标计算
- `backend/app/core/evaluation/evaluator.py` - 离线评估器
- `backend/app/core/evaluation/benchmark.py` - 基准测试套件

**核心功能**：
- 任务完成度评分（基于用户反馈）
- 工具调用效率（执行时间、成功率、冗余率）
- 推理质量（ToT 路径评分）
- 响应质量（LLM-as-a-judge）

**数据模型扩展**：
```python
# 扩展现有数据库模型
class ExecutionRecordDB(Base):
    """每次对话执行的详细记录"""
    id: str
    session_id: str
    user_query: str

    # 推理过程
    reasoning_mode: str  # "simple", "heuristic", "analytical", "exhaustive"
    tot_depth: int
    tot_thoughts_count: int

    # 工具调用
    tools_called: List[str]
    tool_rounds: int
    tool_execution_time: float

    # 结果
    assistant_response: str
    user_feedback: Optional[str]  # "thumbs_up", "thumbs_down", "edited"
    user_correction: Optional[str]

    # 性能指标
    total_time: float
    llm_tokens_used: int
    estimated_cost: float

    timestamp: datetime
```

**验证标准**：
- 所有对话自动记录执行指标
- 前端显示反馈按钮（👍/👎/✏️编辑）
- 每周生成性能报告

#### 1.2 用户反馈收集（优先级：最高）

**前端修改**：
- `frontend/components/chat/MessageList.tsx` - 添加反馈按钮
- 支持用户编辑 Assistant 回复

**后端 API**：
- `backend/app/api/feedback.py` - 反馈提交端点
- `backend/app/api/analytics.py` - 性能分析端点

**验证标准**：
- 用户反馈收集率 > 30%
- 反馈数据实时记录

#### 1.3 经验回放缓冲区（优先级：高）

**新建文件**：
- `backend/app/core/experience/replay_buffer.py` - 经验回放缓冲区
- `backend/app/core/experience/trajectory.py` - 轨迹数据结构

**核心功能**：
- 存储对话轨迹（query → reasoning → tools → response）
- 存储用户反馈和修正
- 优先级采样（高奖励、高错误样本优先）

**数据结构**：
```python
@dataclass
class Trajectory:
    """单次对话的完整轨迹"""
    trajectory_id: str

    # 输入
    user_query: str
    session_context: Dict[str, Any]

    # 推理过程
    reasoning_mode: str
    tot_tree: Optional[ThoughtTree]
    tool_calls: List[ToolCallRecord]

    # 输出
    assistant_response: str

    # 反馈
    user_feedback: Optional[str] = None
    user_correction: Optional[str] = None

    # 元数据
    timestamp: datetime
    reward: Optional[float] = None
```

**存储方案**：
- SQLite 表 `trajectories` 存储结构化数据
- 文件系统 `data/trajectories/` 存储 ToT 树（JSON）

**验证标准**：
- 自动记录所有对话轨迹
- 支持按条件查询
- 提供轨迹可视化接口

---

### Phase 2: 学习机制（3-6个月）

**目标**：实现基于反馈的自我优化

#### 2.1 反思奖励机制（优先级：最高）

**对应组件**：ReflectionReward

**新建文件**：
- `backend/app/core/reflection/reward_calculator.py` - 奖励计算器
- `backend/app/core/reflection/quality_evaluator.py` - 质量评估器

**核心功能**：
- **多维度奖励计算**：
  - 任务完成度（用户反馈）权重 0.7
  - 推理效率（工具调用次数）权重 0.15
  - 响应速度权重 0.05
  - 新颖性（探索新方法）权重 0.1

- **反思式自我评估**：
  - LLM 自我评分："我给自己X分，因为..."
  - 对比用户修正，识别错误模式

- **GRPO 风格奖励**：
  - 对比当前策略与历史平均
  - 计算相对优势：`A(s,a) = Q(s,a) - V(s)`

**奖励函数**：
```python
def calculate_reward(
    user_feedback: Optional[str],
    self_evaluation: float,
    tool_efficiency: float,
    response_time: float,
    novelty_score: float
) -> float:
    """综合奖励计算，返回 [-1, 1]"""

    # 任务完成度
    if user_feedback == "thumbs_up":
        completion_reward = 1.0
    elif user_feedback == "thumbs_down":
        completion_reward = -1.0
    elif user_feedback == "edited":
        completion_reward = 0.3
    else:
        completion_reward = (self_evaluation - 5.0) / 5.0

    # 效率奖励
    efficiency_reward = -log(1 + tool_count) * 0.1

    # 速度奖励
    speed_reward = -min(response_time / 60.0, 1.0) * 0.05

    # 探索奖励
    novelty_reward = novelty_score * 0.1

    # 加权组合
    total_reward = (
        completion_reward * 0.7 +
        efficiency_reward * 0.15 +
        speed_reward * 0.05 +
        novelty_reward * 0.1
    )

    return np.clip(total_reward, -1.0, 1.0)
```

**验证标准**：
- 奖励值分布合理
- 与人工评分相关性 > 0.6
- 能区分好坏案例

#### 2.2 自适应记忆系统（优先级：高）

**对应组件**：AdaptiveMemorySystem

**新建文件**：
- `backend/app/memory/adaptive/cluster_manager.py` - 记忆聚类管理
- `backend/app/memory/adaptive/retrieval_strategy.py` - 自适应检索策略

**核心功能**：
- **动态记忆聚类**：
  - 使用 HDBSCAN 进行语义聚类
  - 自动识别主题（工作、项目、个人偏好）
  - 聚类合并和分裂

- **自适应检索阈值**：
  - 根据查询类型调整相似度阈值
  - 学习哪些记忆对哪些任务有用
  - 优先召回高奖励任务相关的记忆

- **记忆重要性评分**：
  - 基于访问频率、最近访问时间、奖励关联
  - 自动清理低价值记忆

**技术选型**：
- 聚类算法：HDBSCAN
- 嵌入模型：复用现有 RAG 的 embedding
- 存储：扩展现有 ChromaDB，增加聚类标签

**数据模型扩展**：
```python
class MemoryDB(Base):
    # 现有字段...

    # 新增字段
    cluster_id: Optional[str]
    importance_score: float = 0.5
    access_count: int = 0
    last_accessed: datetime
    associated_rewards: List[float] = []
```

**验证标准**：
- 记忆检索召回率提升 10%
- 检索响应时间 < 500ms
- 聚类质量（人工评估）

#### 2.3 认知控制器（优先级：中）

**对应组件**：EpistemicController

**新建文件**：
- `backend/app/core/control/strategy_selector.py` - 策略选择器
- `backend/app/core/control/uncertainty_estimator.py` - 不确定性估计

**核心功能**：
- **任务复杂度动态评估**：
  - 基于历史成功率预估难度
  - 估计自身能力边界
  - 识别需要外部知识的任务

- **推理策略选择**：
  - Simple：简单任务
  - Heuristic：中等复杂度
  - Analytical：复杂任务
  - Exhaustive：研究任务

- **元学习机制**：
  - 记录哪些策略在哪些任务上成功
  - 任务嵌入 + 策略嵌入，学习映射
  - 少样本学习（新任务快速适应）

**实现方式**：
```python
class EpistemicController:
    def select_strategy(
        self,
        user_query: str,
        session_context: Dict,
        historical_performance: Dict
    ) -> str:
        """选择推理策略"""

        # 1. 基础规则（保留现有 ToTRouter 逻辑）
        base_strategy = self._rule_based_classification(user_query)

        # 2. 查询历史性能
        query_embedding = self.embedder.embed(user_query)
        similar_tasks = historical_performance.find_similar(query_embedding, k=5)

        # 3. 如果有足够相似任务，使用经验策略
        if similar_tasks and len(similar_tasks) >= 3:
            best_strategy = self._select_by_reward(similar_tasks)
            return best_strategy

        # 4. 否则，使用基础规则
        return base_strategy
```

**验证标准**：
- 策略选择准确率 > 70%
- 不确定性估计校准

---

### Phase 3: 自我进化（6-12个月）

**目标**：实现闭环自我改进

#### 3.1 推理路由器（优先级：最高）

**对应组件**：ReasoningRouter

**新建文件**：
- `backend/app/core/routing/router.py` - 智能路由器
- `backend/app/core/routing/processor_pool.py` - 处理器池

**核心功能**：
- **多处理器架构**：
  - SimpleProcessor：快速响应
  - ToTProcessor：深度推理
  - ResearchProcessor：研究模式
  - CorrectionProcessor：错误修正

- **动态路由决策**：
  - 基于任务类型、历史性能、资源约束
  - 支持处理器级联
  - 负载均衡

- **A/B 测试框架**：
  - 对相似任务尝试不同处理器
  - 自动收集性能对比
  - 逐步迁移到更优处理器

**架构设计**：
```python
class ReasoningRouter:
    def __init__(self):
        self.processors = {
            "simple": SimpleProcessor(),
            "tot": ToTProcessor(),
            "research": ResearchProcessor(),
            "correction": CorrectionProcessor()
        }
        self.router_model = None  # 可选：训练轻量级路由模型

    async def route(
        self,
        user_query: str,
        session_context: Dict,
        enable_learning: bool = True
    ) -> AsyncIterator[Dict]:
        """智能路由到最佳处理器"""

        # 1. 任务分类
        task_type = self._classify_task(user_query, session_context)

        # 2. 选择处理器
        if enable_learning and self.router_model:
            processor_name = self.router_model.predict(user_query, session_context)
        else:
            processor_name = self._rule_based_route(task_type)

        # 3. 执行并收集指标
        processor = self.processors[processor_name]
        async for event in processor.execute(user_query, session_context):
            yield event

        # 4. 记录性能（用于学习）
        self._record_performance(processor_name, task_type, event.metrics)
```

**验证标准**：
- 路由准确率 > 75%
- 平均响应时间减少 20%
- 任务完成率提升 15%

#### 3.2 自我纠正规划器（优先级：高）

**对应组件**：SelfCorrectionPlanner

**新建文件**：
- `backend/app/core/correction/error_detector.py` - 错误检测器
- `backend/app/core/correction/correction_planner.py` - 纠正规划器

**核心功能**：
- **实时错误检测**：
  - 工具调用失败识别
  - LLM 幻觉检测（与知识库矛盾）
  - 用户反馈分析

- **自动纠正规划**：
  - 诊断错误原因
  - 生成纠正计划
  - 多步纠正（最多 3 轮）

- **学习错误模式**：
  - 聚类常见错误类型
  - 预防性检查
  - 生成错误报告

**验证标准**：
- 自动纠正成功率 > 50%
- 纠正后用户满意度提升 30%
- 平均纠正轮次 < 3

#### 3.3 反思经验学习器（优先级：中）

**对应组件**：ReflectiveExperienceLearner

**新建文件**：
- `backend/app/core/learning/experience_sampler.py` - 经验采样器
- `backend/app/core/learning/reflection_learner.py` - 反思学习器

**核心功能**：
- **经验回放学习**：
  - 采样高价值经验
  - 对比成功和失败案例
  - 更新策略选择模型

- **反思式知识抽取**：
  - LLM 总结成功案例的关键因素
  - 生成"如果-那么"规则
  - 将规则整合到系统提示词

**验证标准**：
- 学习后性能提升 > 5%
- 提取规则质量（人工评估）

#### 3.4 终身进化引擎（优先级：低）

**对应组件**：LifelongEvolutionEngine

**新建文件**：
- `backend/app/core/evolution/evolution_orchestrator.py` - 进化编排器
- `backend/app/core/evolution/version_manager.py` - 版本管理器

**核心功能**：
- **持续学习循环**：
  - 每周自动触发学习
  - 生成新版本
  - A/B 测试

- **安全升级机制**：
  - 金刚测试集
  - 性能回归检测
  - 自动回滚

**验证标准**：
- 自动升级成功率 > 80%
- 无性能回归
- 月度性能提升 > 2%

---

## 技术选型

### 新增 Python 库

**Phase 1**：
```txt
scikit-learn>=1.3.0    # 评估指标
matplotlib>=3.7.0       # 可视化（可选）
```

**Phase 2**：
```txt
hdbscan>=0.8.29         # 密度聚类
umap-learn>=0.5.3       # 降维可视化
```

**Phase 3**：
```txt
xgboost>=2.0.0          # 策略分类器
mlflow>=2.8.0           # 实验跟踪（可选）
```

---

## 实施策略

### 关键路径（必须按顺序）

```
Phase 1.1（性能评估）→ Phase 1.3（经验回放）→ Phase 2.1（反思奖励）→ Phase 2.2（自适应记忆）→ Phase 3.1（推理路由）
```

### 可并行开发

**并行组 1**（可立即开始）：
- Phase 1.2（用户反馈收集）
- Phase 2.2（自适应记忆聚类）

**并行组 2**（Phase 1 完成后）：
- Phase 2.1（反思奖励）
- Phase 2.3（认知控制器）

**并行组 3**（Phase 2 完成后）：
- Phase 3.1（推理路由器）
- Phase 3.2（自我纠正规划器）

---

## 关键文件

实施过程中最关键的 5 个文件：

1. **`backend/app/core/agent.py`**
   - 核心执行逻辑，需要集成所有学习组件
   - 添加性能监控、策略选择、自我纠正

2. **`backend/app/core/tot/router.py`**
   - 扩展为 ReasoningRouter
   - 支持多处理器动态路由

3. **`backend/app/core/tot/nodes/thought_evaluator.py`**
   - 增强为 AdaptiveThoughtEvaluator
   - 使用学习到的权重

4. **`backend/app/memory/extractor.py`**
   - 扩展为 AdaptiveMemorySystem
   - 支持聚类和自适应检索

5. **`backend/app/models/chat.py`**
   - 添加 ExecutionRecord 和 Trajectory 模型
   - 扩展数据库 schema

---

## 验证与里程碑

### Phase 1 验收（2个月）
- ✅ 所有对话记录执行指标
- ✅ 用户反馈收集率 > 30%
- ✅ 经验回放缓冲区 > 1000 条轨迹

### Phase 2 验收（6个月）
- ✅ 奖励与人工评分相关性 > 0.6
- ✅ 记忆检索召回率提升 10%
- ✅ 策略选择准确率 > 70%

### Phase 3 验收（12个月）
- ✅ 路由准确率 > 75%
- ✅ 自动纠正成功率 > 50%
- ✅ 月度性能提升 > 2%

---

## 风险与缓解

### 技术风险

**风险 1**：学习算法收敛慢
- 缓解：预训练策略模型、设置合理超参数、保留规则系统兜底

**风险 2**：LLM-as-a-judge 不稳定
- 缓解：使用多个 LLM ensemble、人工标注金标准、定期校准

### 工程风险

**风险 1**：数据量爆炸
- 缓解：实施数据清理策略、采样策略、考虑分布式存储

**风险 2**：系统复杂度增加
- 缓解：严格模块化设计、完整测试、详细文档

### 产品风险

**风险 1**：用户反馈不足
- 缓解：设计激励机制、减少反馈成本、使用隐式反馈

**风险 2**：自动纠正错误
- 缓解：保守纠正策略、人工审核关键纠正、用户可关闭

---

## 下一步行动

**立即开始**（Week 1-2）：
1. 用户反馈收集（Phase 1.2）
2. 性能评估系统框架（Phase 1.1）

**短期目标**（Month 1-2）：
3. 经验回放缓冲区（Phase 1.3）
4. 基础奖励计算（Phase 2.1 简化版）

**中期目标**（Month 3-6）：
5. 完整反思奖励机制（Phase 2.1）
6. 自适应记忆聚类（Phase 2.2）
7. 认知控制器（Phase 2.3）

**长期目标**（Month 7-12）：
8. 推理路由器（Phase 3.1）
9. 自我纠正规划器（Phase 3.2）
10. 反思经验学习器（Phase 3.3）
11. 终身进化引擎（Phase 3.4）
