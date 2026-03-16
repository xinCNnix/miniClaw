"""
快速测试：验证流式输出功能

这个测试验证 Phase 1 的流式输出是否正常工作
"""

import asyncio
import sys
from app.core.agent import create_agent_manager
from app.tools.terminal import TerminalTool

# 修复 Windows 控制台编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


async def test_streaming_output():
    """测试 1: 验证流式文本输出"""
    print("="*70)
    print("测试 1: 流式文本输出")
    print("="*70 + "\n")

    agent = create_agent_manager(
        tools=[TerminalTool()],
        llm_provider="qwen"
    )

    print("[USER] 说你好\n")
    print("[ASSISTANT] ")

    content_count = 0
    async for event in agent.astream(
        messages=[{"role": "user", "content": "说你好"}],
        system_prompt="你是一个友好的助手，请简短回应。"
    ):
        if event["type"] == "content_delta":
            print(event["content"], end="", flush=True)
            content_count += 1

    print(f"\n\n[RESULT] 收到 {content_count} 个内容块")

    if content_count > 0:
        print("✅ 流式输出测试通过！\n")
        return True
    else:
        print("❌ 流式输出测试失败！没有收到内容块\n")
        return False


async def test_tool_call_chunks():
    """测试 2: 验证工具调用片段"""
    print("="*70)
    print("测试 2: 工具调用片段")
    print("="*70 + "\n")

    agent = create_agent_manager(
        tools=[TerminalTool()],
        llm_provider="qwen"
    )

    print("[USER] 列出当前目录的文件\n")
    print("[ASSISTANT] ")

    has_tool_call_chunk = False
    has_tool_args_chunk = False
    has_tool_call = False

    async for event in agent.astream(
        messages=[{"role": "user", "content": "列出当前目录的文件"}],
        system_prompt="使用 terminal 工具执行命令。"
    ):
        event_type = event["type"]

        if event_type == "content_delta":
            print(event["content"], end="", flush=True)

        elif event_type == "tool_call_chunk":
            print(f"\n\n[TOOL CHUNK] 工具: {event['tool_name']}")
            has_tool_call_chunk = True

        elif event_type == "tool_args_chunk":
            print(f"[ARGS CHUNK] {event['args']}", end="")
            has_tool_args_chunk = True

        elif event_type == "tool_call":
            print(f"\n[TOOL CALL] 完整工具调用: {event['tool_calls'][0]['name']}")
            has_tool_call = True

        elif event_type == "tool_output":
            print(f"\n[RESULT] {event['tool_name']}: {event['output'][:100]}...")

    print("\n\n[RESULT] 工具调用片段测试")
    print(f"  - tool_call_chunk: {'✅' if has_tool_call_chunk else '❌'}")
    print(f"  - tool_args_chunk: {'✅' if has_tool_args_chunk else '❌'}")
    print(f"  - tool_call (完整): {'✅' if has_tool_call else '❌'}")

    if has_tool_call_chunk and has_tool_call:
        print("\n✅ 工具调用片段测试通过！\n")
        return True
    else:
        print("\n❌ 工具调用片段测试失败！\n")
        return False


async def test_backward_compatibility():
    """测试 3: 验证向后兼容性"""
    print("="*70)
    print("测试 3: 向后兼容性")
    print("="*70 + "\n")

    agent = create_agent_manager(
        tools=[TerminalTool()],
        llm_provider="qwen"
    )

    print("[USER] 执行命令 pwd\n")

    required_events = [
        "thinking_start",
        "tool_call",      # 原有事件必须保留
        "tool_output",    # 原有事件必须保留
        "done",           # 原有事件必须保留
    ]

    received_events = set()

    async for event in agent.astream(
        messages=[{"role": "user", "content": "执行命令 pwd"}],
        system_prompt="使用 terminal 工具。"
    ):
        received_events.add(event["type"])

        if event["type"] == "content_delta":
            print(event["content"], end="", flush=True)

        elif event["type"] == "tool_call":
            print(f"\n[TOOL] {event['tool_calls'][0]['name']}")

        elif event["type"] == "tool_output":
            print(f"[OUTPUT] {event['output'][:80]}...")

    print("\n\n[RESULT] 向后兼容性检查")
    all_present = True
    for required in required_events:
        present = required in received_events
        print(f"  - {required}: {'✅' if present else '❌'}")
        if not present:
            all_present = False

    if all_present:
        print("\n✅ 向后兼容性测试通过！\n")
        return True
    else:
        print("\n❌ 向后兼容性测试失败！缺少必需事件\n")
        return False


async def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("Agent 流式输出优化 - Phase 1 验证测试")
    print("="*70 + "\n")

    results = []

    # 测试 1: 流式文本输出
    try:
        result = await test_streaming_output()
        results.append(("流式文本输出", result))
    except Exception as e:
        print(f"❌ 测试 1 异常: {e}\n")
        results.append(("流式文本输出", False))

    await asyncio.sleep(1)

    # 测试 2: 工具调用片段
    try:
        result = await test_tool_call_chunks()
        results.append(("工具调用片段", result))
    except Exception as e:
        print(f"❌ 测试 2 异常: {e}\n")
        results.append(("工具调用片段", False))

    await asyncio.sleep(1)

    # 测试 3: 向后兼容性
    try:
        result = await test_backward_compatibility()
        results.append(("向后兼容性", result))
    except Exception as e:
        print(f"❌ 测试 3 异常: {e}\n")
        results.append(("向后兼容性", False))

    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70 + "\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n🎉 所有测试通过！Phase 1 优化成功！")
        print("\n下一步：")
        print("1. 提交代码到 Git")
        print("2. 继续 Phase 2（并发执行）或进行完整测试")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查修改")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
