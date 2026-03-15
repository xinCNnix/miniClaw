# -*- coding: utf-8 -*-
"""
miniClaw Performance Testing Script (Windows Compatible)

This script tests the performance optimizations implemented in miniClaw.
It measures response times, cache effectiveness, and parallel tool execution.

Usage:
    python test_performance_win.py
"""

import asyncio
import time
import json
import statistics
from typing import Dict, List
from pathlib import Path
import sys
import os

# Set UTF-8 encoding for Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.agent import create_agent_manager
from app.tools import CORE_TOOLS
from app.config import get_settings


class PerformanceTest:
    """Performance testing framework."""

    def __init__(self):
        self.settings = get_settings()
        self.results = []

    def print_section(self, title: str):
        """Print a section header."""
        print("\n" + "="*60)
        print(f"  {title}")
        print("="*60 + "\n")

    def print_result(self, test_name: str, duration: float, status: str = "[OK]"):
        """Print a test result."""
        print(f"{status} {test_name}: {duration:.3f}s")
        self.results.append({
            "test": test_name,
            "duration": duration,
            "status": status
        })

    async def test_agent_initialization(self) -> float:
        """Test agent initialization time."""
        self.print_section("Test 1: Agent Initialization")

        start = time.time()
        agent_manager = create_agent_manager(
            tools=CORE_TOOLS,
            llm_provider=self.settings.llm_provider,
        )
        duration = time.time() - start

        self.print_result("Agent initialization", duration)
        return agent_manager

    async def test_simple_qa(self, agent_manager) -> float:
        """Test simple Q&A (no tools)."""
        self.print_section("Test 2: Simple Q&A (No Tools)")

        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Hello, please introduce yourself"}]

        start = time.time()
        events = []
        async for event in agent_manager.astream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            events.append(event)
        duration = time.time() - start

        # Count tool calls
        tool_calls = sum(1 for e in events if e.get("type") == "tool_call")

        self.print_result(f"Simple Q&A response (tool calls: {tool_calls})", duration)
        return duration

    async def test_single_tool(self, agent_manager) -> float:
        """Test single tool call."""
        self.print_section("Test 3: Single Tool Call")

        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "List files in current directory"}]

        start = time.time()
        events = []
        async for event in agent_manager.astream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            events.append(event)
        duration = time.time() - start

        # Count tool calls
        tool_calls = sum(1 for e in events if e.get("type") == "tool_call")

        self.print_result(f"Single tool response (tool calls: {tool_calls})", duration)
        return duration

    async def test_multi_tool(self, agent_manager) -> float:
        """Test multiple tool calls."""
        self.print_section("Test 4: Multiple Tool Calls")

        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "List files in current directory and read README.md"}]

        start = time.time()
        events = []
        async for event in agent_manager.astream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            events.append(event)
        duration = time.time() - start

        # Count tool calls
        tool_calls = sum(1 for e in events if e.get("type") == "tool_call")

        self.print_result(f"Multi-tool response (tool calls: {tool_calls})", duration)
        return duration

    async def test_cache_effectiveness(self, agent_manager) -> Dict:
        """Test cache effectiveness."""
        self.print_section("Test 5: Cache Effectiveness")

        system_prompt = "You are a helpful assistant."
        query = "What is the weather in Beijing?"

        # First call (cache miss)
        messages = [{"role": "user", "content": query}]
        start = time.time()
        events = []
        async for event in agent_manager.astream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            events.append(event)
        first_call_duration = time.time() - start

        # Second call (potential cache hit)
        start = time.time()
        events = []
        async for event in agent_manager.astream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            events.append(event)
        second_call_duration = time.time() - start

        # Third call (cache hit)
        start = time.time()
        events = []
        async for event in agent_manager.astream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            events.append(event)
        third_call_duration = time.time() - start

        print(f"First call (cache miss): {first_call_duration:.3f}s")
        print(f"Second call (possible hit): {second_call_duration:.3f}s")
        print(f"Third call (should hit): {third_call_duration:.3f}s")

        avg_cached = statistics.mean([second_call_duration, third_call_duration])
        speedup = (first_call_duration - avg_cached) / first_call_duration * 100 if first_call_duration > 0 else 0

        print(f"\nCache speedup: {speedup:.1f}%")

        return {
            "first_call": first_call_duration,
            "second_call": second_call_duration,
            "third_call": third_call_duration,
            "speedup": speedup
        }

    async def test_streaming_ttfb(self, agent_manager) -> Dict:
        """Test streaming Time-To-First-Byte."""
        self.print_section("Test 6: Streaming Response TTFB")

        system_prompt = "You are a helpful assistant."
        messages = [{"role": "user", "content": "Write a short poem about AI"}]

        start = time.time()
        first_chunk_time = None
        total_duration = None
        chunk_count = 0

        async for event in agent_manager.astream(
            messages=messages,
            system_prompt=system_prompt,
        ):
            if event.get("type") == "content_delta":
                if first_chunk_time is None:
                    first_chunk_time = time.time() - start
                chunk_count += 1
            elif event.get("type") == "done":
                total_duration = time.time() - start

        if first_chunk_time:
            print(f"Time-To-First-Byte (TTFB): {first_chunk_time:.3f}s")
            self.print_result("Streaming TTFB", first_chunk_time)
        else:
            print("[WARNING] No content stream detected")
            first_chunk_time = 0

        if total_duration:
            print(f"Total response time: {total_duration:.3f}s")
            print(f"Content chunks: {chunk_count}")

        return {
            "ttfb": first_chunk_time,
            "total_duration": total_duration,
            "chunk_count": chunk_count
        }

    async def run_all_tests(self):
        """Run all performance tests."""
        print("\n" + "="*60)
        print("  miniClaw Performance Test Suite")
        print("="*60 + "\n")

        print(f"LLM Provider: {self.settings.llm_provider}")
        print(f"Tool count: {len(CORE_TOOLS)}")
        print(f"Parallel tool execution: {'Enabled' if self.settings.enable_parallel_tool_execution else 'Disabled'}")
        print(f"Streaming response: {'Enabled' if self.settings.enable_streaming_response else 'Disabled'}")
        print(f"Smart truncation: {'Enabled' if self.settings.enable_smart_truncation else 'Disabled'}")

        try:
            # Test 1: Initialization
            agent_manager = await self.test_agent_initialization()

            # Test 2: Simple Q&A
            await self.test_simple_qa(agent_manager)

            # Test 3: Single tool
            await self.test_single_tool(agent_manager)

            # Test 4: Multi-tool
            await self.test_multi_tool(agent_manager)

            # Test 5: Cache effectiveness
            cache_results = await self.test_cache_effectiveness(agent_manager)

            # Test 6: Streaming TTFB
            ttfb_results = await self.test_streaming_ttfb(agent_manager)

            # Summary
            self.print_summary(cache_results, ttfb_results)

        except Exception as e:
            print(f"\n[ERROR] Test failed: {e}")
            import traceback
            traceback.print_exc()

    def print_summary(self, cache_results: Dict, ttfb_results: Dict):
        """Print test summary."""
        self.print_section("Test Summary")

        print("Performance Metrics Summary:\n")

        # Calculate statistics
        durations = [r["duration"] for r in self.results]
        if durations:
            avg_duration = statistics.mean(durations)
            min_duration = min(durations)
            max_duration = max(durations)

            print(f"Average response time: {avg_duration:.3f}s")
            print(f"Fastest response: {min_duration:.3f}s")
            print(f"Slowest response: {max_duration:.3f}s")

        print(f"\nCache speedup: {cache_results.get('speedup', 0):.1f}%")
        print(f"TTFB: {ttfb_results.get('ttfb', 0):.3f}s")

        print("\nPerformance Targets:")
        if len(durations) >= 4:
            print(f"Simple Q&A: {'[PASS] (<1s)' if durations[1] < 1.0 else '[FAIL]'}  (Target: <1s, Actual: {durations[1]:.3f}s)")
            print(f"Single tool: {'[PASS] (<3s)' if durations[2] < 3.0 else '[FAIL]'}  (Target: <3s, Actual: {durations[2]:.3f}s)")
            print(f"Multi-tool: {'[PASS] (<5s)' if durations[3] < 5.0 else '[FAIL]'}  (Target: <5s, Actual: {durations[3]:.3f}s)")

        print("\n[OK] All tests completed!")


async def main():
    """Main entry point."""
    tester = PerformanceTest()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
