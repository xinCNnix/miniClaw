# Changelog

All notable changes to miniClaw will be documented in this file.

---

## 2025-03-15 - Feature: Intelligent Tool Calling Optimization

### Problem Statement
The miniClaw Agent had inefficient tool calling behavior:
- **Simple tasks over-call**: Simple queries might call tools 10+ times before stopping
- **Deep research limited**: Complex research tasks hit the 10-round limit too early
- **No intelligent decision-making**: Unable to autonomously judge when information is sufficient
- **Possible redundant calls**: No mechanism to detect duplicate tool calls

### Solution
Implemented "Solution 3: Redundancy Detection + Information Sufficiency Judgment" for intelligent tool calling optimization.

### Implementation Details

#### Phase 1: Configuration Extensions (`backend/app/config.py`)

**New configuration items:**
```python
# Agent Execution
max_tool_rounds: int = 50  # Increased from 10 to support complex research
enable_smart_stopping: bool = True  # Master switch for intelligent stopping
redundancy_detection_window: int = 3  # Window size for redundancy detection
sufficiency_evaluation_interval: int = 2  # Evaluate sufficiency every N rounds
```

**Configuration impact:**
- `max_tool_rounds`: 10 → 50 (supports deep research tasks)
- `enable_smart_stopping`: True (can be disabled to fallback to original behavior)
- `redundancy_detection_window`: Detects redundant patterns in last 3 rounds
- `sufficiency_evaluation_interval`: Evaluates every 2 rounds (balances performance and intelligence)

---

#### Phase 2: Agent Core Logic (`backend/app/core/agent.py`)

**1. Tracking Variables Initialization**
- Added `recent_tool_calls` list to track tool call history for redundancy detection

**2. Per-Round Detection Logic**
After each tool calling round:
- **Redundancy Detection**: Checks if last N rounds made identical tool calls with similar arguments (>0.8 similarity)
- **Sufficiency Evaluation**: Every 2 rounds, asks LLM to judge if collected information is sufficient
- **Smart Stopping**: Automatically stops and generates response when information is sufficient or redundancy detected

**3. New Methods Added:**

- `_detect_redundancy(recent_tool_calls: list) -> bool`
  - Detects redundant tool calling patterns
  - Checks for identical tool calls across consecutive rounds
  - Validates argument similarity threshold (>0.8)

- `_args_similarity(args1: dict, args2: dict) -> float`
  - Calculates similarity between two tool argument sets
  - Returns 0.0-1.0 similarity score
  - Handles string prefix matching for file paths and URLs

- `_evaluate_sufficiency(lc_messages: list, user_question: str) -> bool`
  - Evaluates if collected information is sufficient to answer user's question
  - Uses LLM (without tools) for intelligent judgment
  - Returns True if should continue tool calling, False if sufficient

- `_format_tool_history(lc_messages: list) -> str`
  - Formats tool call history into readable text
  - Truncates each tool result to 500 chars
  - Provides context for sufficiency evaluation

**4. Event Stream Enhancements:**
New event types for better observability:
- `"type": "warning"` - Redundancy detected
- `"type": "info"` - Information sufficiency reached

---

#### Phase 3: Behavior Guidelines (`backend/workspace/AGENTS.md`)

**New section: "Tool Calling Optimization Strategy"**

**Core principles:**
- **Stop when information is sufficient**: Generate response immediately after collecting core information, don't be "greedy"
- **Avoid redundant calls**: Automatically stop when duplicate tool calls detected
- **Intelligent judgment**: Evaluate every 2 rounds if information is sufficient

**Sufficiency judgment guidelines:**
1. **Pre-call evaluation**: Is this tool call necessary?
2. **Post-call evaluation**: Is current information sufficient to answer the question?
3. **Timely stopping**: Generate response immediately if sufficient, don't continue calling tools

**Examples:**

**Example 1: Simple task (avoid over-calling)**
```
User: "Check Beijing weather"

Correct approach:
1. terminal("curl -s 'wttr.in/Beijing?format=j1'")
2. Evaluate: information is sufficient
3. Generate response

Wrong approach:
1. terminal("curl -s 'wttr.in/Beijing?format=j1'")
2. terminal("curl -s 'wttr.in/Beijing?format=lines'")
3. read_file("weather_history.txt")
4. ... continue calling more tools
```

**Example 2: Deep Research task**
```
User: "Deep research GPT-4 technical architecture"

Correct approach:
1. read_file("papers/gpt4_1.md")
2. read_file("papers/gpt4_2.md")
3. read_file("papers/gpt4_3.md")
4. Evaluate: collected core technical information
5. Generate response: "Based on three core papers..."

Wrong approach:
1. read_file("papers/gpt4_1.md")
2. read_file("papers/gpt4_2.md")
3. ... read to 10th paper
4. Forced to stop at 50-round limit
```

**Example 3: Redundancy detection**
```
User: "Analyze this function"

If 3 consecutive rounds call `read_file` with similar file paths:
- System automatically detects redundancy
- Force response generation
- Output warning: "Detected repetitive tool calls"
```

---

### Key Design Decisions

**Performance Balance:**
- Evaluate every 2 rounds (not every round) to avoid frequent LLM calls
- Redundancy detection uses sliding window (O(1) memory overhead)
- Similarity calculation is lightweight (string prefix matching)

**Conservative Design:**
- Only stop when LLM explicitly outputs "SUFFICIENT"
- Otherwise continue tool calling (fail-safe behavior)
- Evaluation errors default to continuing (conservative fallback)

**Controllability:**
- `enable_smart_stopping` master switch can disable all optimizations
- Individual tuning for detection window and evaluation interval
- Can fallback to original 10-round behavior if needed

**Observability:**
- Detailed logging for all detection and evaluation steps
- Event stream includes warning/info messages
- Easy to debug and monitor optimization behavior

---

### Testing Strategy

**Test Scenario 1: Simple Task**
1. User asks: "What's the weather today?"
2. Expected: Stop after 1-2 tool calling rounds
3. Log should show: "LLM determined information is sufficient"

**Test Scenario 2: Deep Research**
1. User asks: "Research LangChain architecture design"
2. Expected: Can call 10+ rounds until information is sufficient
3. Should not stop prematurely

**Test Scenario 3: Redundancy Detection**
1. Construct consecutive duplicate read_file calls
2. Expected: Detect redundancy after 3 rounds and stop
3. Log should show: "Detected redundant tool calls"

**Test Scenario 4: Disable Smart Stopping**
1. Set `enable_smart_stopping = False`
2. Expected: Fallback to original behavior (only stop at max_tool_rounds)

---

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| LLM evaluation cost (time and tokens) | Evaluate every 2 rounds, not every round |
| False positive sufficiency judgment | Conservative design: only stop on explicit "SUFFICIENT" |
| Redundancy detection false positives | Requires high similarity (>0.8) to trigger |
| Increased complexity | `enable_smart_stopping` switch can disable optimizations |

---

### Modified Files

| File Path | Type | Description |
|-----------|------|-------------|
| `backend/app/config.py` | Modified | Added 4 new config items, updated max_tool_rounds to 50 |
| `backend/app/core/agent.py` | Modified | Added smart stopping logic in astream, 4 new methods |
| `backend/workspace/AGENTS.md` | Modified | Added "Tool Calling Optimization Strategy" section |

---

### Future Enhancements

**Possible improvements:**
1. **Adaptive evaluation interval**: Dynamically adjust evaluation frequency based on task complexity
2. **Tool dependency analysis**: Detect dependencies between tools to optimize calling order
3. **Performance monitoring**: Add detailed metrics (average calling rounds, evaluation success rate, etc.)
4. **User feedback**: Allow users to mark "insufficient information" to improve evaluation strategy

---

### Summary

This update implements:

✅ **Increased upper limit**: 10 → 50 rounds (supports deep research)
✅ **Intelligent stopping**: Redundancy detection + sufficiency evaluation
✅ **Better observability**: Detailed logging and event messages
✅ **Controllability**: Master switch for easy fallback
✅ **Performance balance**: Every 2 rounds evaluation to minimize overhead

**miniClaw Agent now intelligently decides when to stop tool calling, avoiding both over-calling on simple tasks and under-calling on complex research tasks!**

---

## 2025-03-15 - Bug Fix: Skills API Validation Error

### Problem
Skills API (`/api/skills/list`) was failing with validation error:

```
1 validation error for SkillMetadata
description_en
  Field required [type=missing, input_value={...}]
```

**Root Cause**: Two different `SkillMetadata` definitions:
- `bootstrap.py:19-78` - No `description_en` field (used for scanning skills)
- `api/skills.py:29-38` - Required `description_en` field (used for API responses)

Old registry entries without `description_en` caused Pydantic validation to fail.

### Solution
Made `description_en` optional with intelligent fallback mechanism:

**Modified**: `backend/app/api/skills.py`

1. **Changed `description_en` to optional field**
   ```python
   # Before
   description_en: str = Field(..., description="Refined English description")

   # After
   description_en: Optional[str] = Field(None, description="Refined English description (auto-fallback)")
   ```

2. **Added `from_registry_data()` class method**
   ```python
   @classmethod
   def from_registry_data(cls, data: Dict[str, Any]) -> "SkillMetadata":
       """Create SkillMetadata with fallback for missing description_en."""
       description_en = data.get("description_en") or data.get("description", "")
       return cls(
           name=data.get("name", ""),
           description=data.get("description", ""),
           description_en=description_en,
           # ... other fields
       )
   ```

3. **Updated all API endpoints** to use `from_registry_data()`:
   - `/api/skills/list`
   - `/api/skills/install`
   - `/api/skills/create`
   - `/api/skills/{skill_name}/toggle`

### Testing
Created comprehensive test suite (`backend/test_skills_fix.py`):

| Test Case | Result |
|-----------|--------|
| Data with description_en | ✅ PASS |
| Data missing description_en key | ✅ PASS (fallback to description) |
| Empty description_en | ✅ PASS (fallback to description) |
| None description_en | ✅ PASS (fallback to description) |
| Pydantic serialization | ✅ PASS |
| Old registry format | ✅ PASS |
| Model validation | ✅ PASS |

**All 7 tests passed** ✅

### Backward Compatibility

**Old data (without description_en)**:
```json
{"name": "get_weather", "description": "获取天气"}
```
**Automatically handled**:
```json
{"name": "get_weather", "description": "获取天气", "description_en": "获取天气"}
```

**New data (with description_en)**:
```json
{"name": "get_weather", "description": "获取天气", "description_en": "Get weather"}
```
**Preserved as-is**:
```json
{"name": "get_weather", "description": "获取天气", "description_en": "Get weather"}
```

### Modified Files

| File Path | Type | Description |
|-----------|------|-------------|
| `backend/app/api/skills.py` | Modified | Made description_en optional, added from_registry_data() method |
| `backend/test_skills_fix.py` | New | Comprehensive test suite for the fix |

### Summary

✅ **Skills API now handles old registry entries gracefully**
✅ **Automatic fallback to description when description_en is missing**
✅ **No data migration required**
✅ **Backward compatible with existing skills**
✅ **Fully tested with 7/7 tests passing**

---

*Last updated: 2025-03-15*
