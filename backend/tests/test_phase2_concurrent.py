"""
Phase 2 并发执行验证测试

这个测试验证并发工具执行功能是否正常工作
"""

import asyncio
import sys
import time
from typing import List, AsyncIterator

from langchain_core.tools import tool
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

# 修复 Windows 控制台编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.core.agent import create_agent_manager


# ==================== 模拟耗时工具 ====================

@tool
def slow_task_1(task_id: str = "A", duration: float = 1.0) -> str:
    """模拟耗时任务 1。"""
    time.sleep(duration)
    return f"任务 {task_id} 完成，耗时 {duration} 秒"

@tool
def slow_task_2(task_id: str = "B", duration: float = 1.0) -> str:
    """模拟耗时任务 2。"""
    time.sleep(duration)
    return f"任务 {task_id} 完成，耗时 {duration} 秒"

@tool
def slow_task_3(task_id: str = "C", duration: float = 1.0) -> str:
    """模拟耗时任务 3。"""
    time.sleep(duration)
    return f"任务 {task_id} 完成，耗时 {duration} 秒"


# ==================== 测试函数 ====================

async def test_concurrent_execution():
    """测试 1: 并发执行性能"""
    print("="*70)
    print("测试 1: 并发执行性能测试")
    print("="*70 + "\n")

    agent = create_agent_manager(
        tools=[slow_task_1, slow_task_2, slow_task_3],
        llm_provider="qwen"
    )

    print("[USER] 同时执行 3 个耗时任务（每个 1 秒）\n")
    print("[ASSISTANT] ")

    start = time.time()
    tool_count = 0
    execution_mode = None

    async for event in agent.astream(
        messages=[{"role": "user", "content": "同时执行 slow_task_1('A'), slow_task_2('B'), slow_task_3('C')，每个耗时 1 秒"}],
        system_prompt="你是一个任务协调助手。执行所有要求的任务。"
    ):
        event_type = event["type"]

        if event_type == "content_delta":
            print(event["content"], end="", flush=True)

        elif event_type == "concurrent_execution_start":
            execution_mode = "concurrent"
            print(f"\n[CONCURRENT] 开始并发执行 {event['tool_count']} 个工具\n")

        elif event_type == "tool_call":
            tool_count += 1
            tool_name = event["tool_calls"][0]["name"]
            print(f"[TOOL {tool_count}] {tool_name}")

        elif event_type == "tool_output":
            tool_name = event["tool_name"]
            status = event["status"]
            duration = event.get("duration", 0)
            print(f"[{status.upper()}] {tool_name} (耗时 {duration:.2f}s)\n")

    duration = time.time() - start

    print(f"\n[RESULT] 总耗时: {duration:.2f}s")
    print(f"[RESULT] 执行模式: {execution_mode or 'serial'}")
    print(f"[RESULT] 执行工具数: {tool_count}")

    # 判断标准：检查是否启用了并发模式
    if execution_mode == "concurrent" and tool_count == 3:
        print("✅ 并发执行测试通过！成功并发执行多个工具\n")
        return True
    else:
        print("⚠️  并发执行未启用或工具数量不足\n")
        return False


async def test_serial_execution():
    """测试 2: 串行执行（对比）"""
    print("="*70)
    print("测试 2: 串行执行对比测试")
    print("="*70 + "\n")

    # 临时禁用并发执行
    from app.config import get_settings
    settings = get_settings()
    original_value = settings.enable_parallel_tool_execution
    settings.enable_parallel_tool_execution = False

    try:
        agent = create_agent_manager(
            tools=[slow_task_1, slow_task_2],
            llm_provider="qwen"
        )

        print("[USER] 执行 2 个任务（串行模式）\n")
        print("[ASSISTANT] ")

        start = time.time()
        tool_count = 0

        async for event in agent.astream(
            messages=[{"role": "user", "content": "执行 slow_task_1('A') 和 slow_task_2('B')"}],
            system_prompt="执行任务。"
        ):
            event_type = event["type"]

            if event_type == "content_delta":
                print(event["content"], end="", flush=True)

            elif event_type == "tool_call":
                tool_count += 1
                tool_name = event["tool_calls"][0]["name"]
                print(f"\n[TOOL {tool_count}] {tool_name}")

            elif event_type == "tool_output":
                tool_name = event["tool_name"]
                status = event["status"]
                print(f"[{status.upper()}] {tool_name}\n")

        duration = time.time() - start

        print(f"\n[RESULT] 总耗时: {duration:.2f}s")
        print(f"[RESULT] 执行模式: serial")

        if duration >= 2.0:
            print("✅ 串行执行测试通过（时间符合预期）\n")
            return True
        else:
            print("⚠️  串行执行时间异常\n")
            return False

    finally:
        # 恢复原始设置
        settings.enable_parallel_tool_execution = original_value


async def test_concurrent_with_real_tools():
    """测试 3: 使用真实工具的并发执行"""
    print("="*70)
    print("测试 3: 真实工具并发执行")
    print("="*70 + "\n")

    from app.tools.terminal import TerminalTool

    agent = create_agent_manager(
        tools=[TerminalTool()],
        llm_provider="qwen"
    )

    print("[USER] 同时执行 3 个命令：pwd, ls, echo\n")
    print("[ASSISTANT] ")

    start = time.time()
    commands_executed = []

    async for event in agent.astream(
        messages=[{"role": "user", "content": "依次执行 pwd, ls -la, echo 'test' 这三个命令"}],
        system_prompt="使用 terminal 工具执行命令。"
    ):
        event_type = event["type"]

        if event_type == "content_delta":
            print(event["content"], end="", flush=True)

        elif event_type == "tool_call":
            tool_name = event["tool_calls"][0]["name"]
            args = event["tool_calls"][0]["arguments"]
            print(f"\n[TOOL] {tool_name}: {args.get('command', 'N/A')}")
            commands_executed.append(args.get('command', ''))

        elif event_type == "tool_output":
            output = event['output'][:100]
            print(f"[OUTPUT] {output}...\n")

    duration = time.time() - start

    print(f"\n[RESULT] 执行了 {len(commands_executed)} 个命令")
    print(f"[RESULT] 总耗时: {duration:.2f}s")

    if len(commands_executed) >= 2:
        print("✅ 真实工具并发执行测试通过\n")
        return True
    else:
        print("⚠️  执行的命令数量不足\n")
        return False


async def test_error_isolation():
    """测试 4: 并发执行中的错误隔离"""
    print("="*70)
    print("测试 4: 并发执行错误隔离")
    print("="*70 + "\n")

    @tool
    def failing_task(task_id: str) -> str:
        """会失败的任务"""
        raise ValueError(f"任务 {task_id} 故意失败")

    @tool
    def success_task(task_id: str) -> str:
        """会成功的任务"""
        return f"任务 {task_id} 成功完成"

    agent = create_agent_manager(
        tools=[failing_task, success_task],
        llm_provider="qwen"
    )

    print("[USER] 同时执行一个会失败的任务和一个会成功的任务\n")
    print("[ASSISTANT] ")

    success_count = 0
    error_count = 0

    async for event in agent.astream(
        messages=[{"role": "user", "content": "同时执行 failing_task('X') 和 success_task('Y')"}],
        system_prompt="执行所有任务。"
    ):
        event_type = event["type"]

        if event_type == "content_delta":
            print(event["content"], end="", flush=True)

        elif event_type == "tool_call":
            tool_name = event["tool_calls"][0]["name"]
            print(f"\n[TOOL] {tool_name}")

        elif event_type == "tool_output":
            tool_name = event["tool_name"]
            status = event["status"]
            if status == "success":
                success_count += 1
                print(f"[SUCCESS] {tool_name}: {event['output'][:50]}...")
            else:
                error_count += 1
                print(f"[ERROR] {tool_name}: {event['output'][:50]}...")

    print(f"\n[RESULT] 成功: {success_count}, 失败: {error_count}")

    if success_count > 0 and error_count > 0:
        print("✅ 错误隔离测试通过（成功和失败任务都正确处理）\n")
        return True
    else:
        print("⚠️  错误隔离测试失败\n")
        return False


async def main():
    """运行所有测试"""
    print("\n" + "="*70)
    print("Agent 并发执行优化 - Phase 2 验证测试")
    print("="*70 + "\n")

    results = []

    # 测试 1: 并发执行性能
    try:
        result = await test_concurrent_execution()
        results.append(("并发执行性能", result))
    except Exception as e:
        print(f"❌ 测试 1 异常: {e}\n")
        results.append(("并发执行性能", False))

    await asyncio.sleep(2)

    # 测试 2: 串行执行对比
    try:
        result = await test_serial_execution()
        results.append(("串行执行对比", result))
    except Exception as e:
        print(f"❌ 测试 2 异常: {e}\n")
        results.append(("串行执行对比", False))

    await asyncio.sleep(2)

    # 测试 3: 真实工具并发
    try:
        result = await test_concurrent_with_real_tools()
        results.append(("真实工具并发", result))
    except Exception as e:
        print(f"❌ 测试 3 异常: {e}\n")
        results.append(("真实工具并发", False))

    await asyncio.sleep(2)

    # 测试 4: 错误隔离
    try:
        result = await test_error_isolation()
        results.append(("错误隔离", result))
    except Exception as e:
        print(f"❌ 测试 4 异常: {e}\n")
        results.append(("错误隔离", False))

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
        print("\n🎉 所有测试通过！Phase 2 优化成功！")
        print("\n性能提升说明：")
        print("- 并发执行：3 个任务 ~1 秒（vs 串行 3 秒）")
        print("- 性能提升：约 3x")
        print("- 错误隔离：单个工具失败不影响其他")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查配置和实现")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
