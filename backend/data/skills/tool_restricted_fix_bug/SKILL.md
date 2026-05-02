---
name: tool_restricted_fix_bug
description: [Tool restricted] Fix bug in parser — Solve without code execution
confidence: 0.9120000000000001
status: stable
tags: ["rule_distilled", "simulated", "tool_restriction"]
source: dream
---

# tool_restricted_fix_bug

## Trigger
When task involves: no code execution

## Steps
1. Use search_kb — Analyzing task: [Tool restricted] Fix bug in parser — Solve without code executi
2. Use read_file — Processing step 2/5 for tool_restriction variant
3. Use python_repl — Processing step 3/5 for tool_restriction variant
4. Use search_kb — Processing step 4/5 for tool_restriction variant
5. Use read_file — Synthesizing results into final answer

## Verification
- Verify step 1 completed
- Verify step 2 completed
- Verify step 3 completed
- Verify step 4 completed
- Verify step 5 completed

## Anti-patterns
- Skip verification
- Assume success without checking

## Examples
- [Tool restricted] Fix bug in parser — Solve without code execution
