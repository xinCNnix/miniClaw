# Pattern Memory 流式处理使用指南

## 概述

`AgentWithPatternLearning` 类现在支持流式处理，可以实时返回执行过程中的各种事件。

## 基本用法

### 1. 使用 invoke() 方法（非流式）

```python
from langchain_openai import ChatOpenAI
from app.memory.auto_learning.graph_builder import AgentWithPatternLearning
from app.tools import CORE_TOOLS

llm = ChatOpenAI(model="gpt-4")
agent = AgentWithPatternLearning(llm=llm, tools=CORE_TOOLS)

# 非流式执行
result = await agent.invoke("What is the capital of France?")
print(result["final_answer"])
print(result["extracted_pattern"])
print(result["retrieved_patterns"])
```

### 2. 使用 stream() 方法（流式）

```python
from langchain_openai import ChatOpenAI
from app.memory.auto_learning.graph_builder import AgentWithPatternLearning
from app.tools import CORE_TOOLS

llm = ChatOpenAI(model="gpt-4")
agent = AgentWithPatternLearning(llm=llm, tools=CORE_TOOLS)

# 流式执行
async for event in agent.stream("What is the capital of France?"):
    event_type = event["type"]

    if event_type == "start":
        print("开始执行...")

    elif event_type == "patterns_retrieved":
        print(f"检索到 {event['count']} 个模式:")
        for pattern in event['patterns']:
            print(f"  - {pattern}")

    elif event_type == "agent_thinking":
        print("Agent 正在思考...")

    elif event_type == "tool_call":
        print(f"调用了 {event['count']} 个工具:")
        for tc in event['tool_calls']:
            print(f"  - {tc['name']}: {tc['args']}")

    elif event_type == "pattern_extracted":
        if event['pattern']:
            print(f"提取到新模式: {event['pattern']}")
        else:
            print("未提取到新模式")

    elif event_type == "final_answer":
        print(f"最终答案: {event['answer']}")

    elif event_type == "done":
        print("执行完成!")

    elif event_type == "error":
        print(f"发生错误: {event['error']}")
```

## 事件类型

流式处理支持以下事件类型：

| 事件类型 | 说明 | 数据字段 |
|---------|------|---------|
| `start` | 执行开始 | `message` |
| `patterns_retrieved` | 检索到模式 | `patterns`, `count` |
| `agent_thinking` | Agent 思考中 | `message` |
| `tool_call` | 工具调用 | `tool_calls`, `count` |
| `pattern_extracted` | 提取到新模式 | `pattern`, `message` |
| `final_answer` | 最终答案 | `answer` |
| `done` | 执行完成 | `message` |
| `error` | 错误信息 | `error` |

## SSE 集成示例

可以将流式事件转换为 SSE 格式用于 Web API：

```python
import json
from fastapi.responses import StreamingResponse
from app.memory.auto_learning.graph_builder import AgentWithPatternLearning

async def chat_stream_generator(query: str):
    """生成 SSE 流"""

    async for event in agent.stream(query):
        # 转换为 SSE 格式
        sse_data = json.dumps(event, ensure_ascii=False)
        yield f"data: {sse_data}\n\n"

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式聊天端点"""
    return StreamingResponse(
        chat_stream_generator(request.message),
        media_type="text/event-stream",
    )
```

## 测试

运行测试：

```bash
cd backend
pytest tests/memory/test_pattern_streaming.py -v
```

## 实现细节

### 流式处理模块

位置: `app/memory/auto_learning/streaming.py`

核心类: `PatternLearningEventStreamer`

主要方法:
- `stream_node_events()`: 将节点执行转换为流式事件
- `create_final_answer_event()`: 创建最终答案事件
- `create_error_event()`: 创建错误事件
- `create_start_event()`: 创建开始事件
- `create_done_event()`: 创建完成事件

### Graph Builder

位置: `app/memory/auto_learning/graph_builder.py`

新增方法:
- `AgentWithPatternLearning.stream()`: 流式执行任务

## 性能考虑

1. **流式 vs 非流式**: 流式执行会略微增加开销（事件序列化），但提供更好的用户体验
2. **向后兼容**: `invoke()` 方法保持不变，不影响现有代码
3. **事件过滤**: 可以在客户端根据事件类型进行过滤和处理

## 最佳实践

1. **错误处理**: 始终检查 `error` 事件
2. **资源清理**: 使用 `async for` 确保正确清理资源
3. **事件顺序**: 事件按执行顺序发送，不要依赖特定的顺序
4. **兼容性**: 流式和非流式方法返回相同的结果（最终答案一致）

## 相关文档

- [LangGraph Streaming](https://langchain-ai.github.io/langgraph/concepts/low_level/#streaming-events)
- [Tree of Thoughts Streaming](../core/tot/streaming.py)
- [Chat API](../../api/chat.py)
