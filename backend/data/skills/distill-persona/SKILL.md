---
name: distill-persona
description: >
  从人物样本中蒸馏可复用的 Agent 技能 profile。当需要：(1) 从一组问答样本提取某人的决策风格和表达习惯，
  (2) 生成可执行的 skill profile (profile.json + skill.md + skill.py)，(3) 自动评判和修复 profile 质量，
  (4) 批量蒸馏多个 persona 为独立 skill 时使用。输入为人物名称 + 样本列表，输出为完整 skill 包。
---

# Distill Persona

## Overview

从一组人物的问答/行为样本中，蒸馏出一个可被 Agent 执行的 skill profile。包含完整的闭环链路：

1. **DistillProfile** — 从样本提取 profile（风格规则、决策启发式、红线、输出模板）
2. **ProfileJudge** — 审计 profile 是否完整、一致、可执行
3. **ImitationTest** — 用 profile 生成测试输出
4. **ImitationJudge** — 判断生成效果是否符合原始样本风格
5. **AutoRepair** — 根据 failure mode 自动修复 profile

最终输出：`profile.json` + `fewshot.json` + `skill.md` + `skill.py` + `judge_report.json`

## Language Style Extraction

pipeline 中包含专门的 **Style Extractor** 步骤，从 10 个维度深度分析语言风格：

| 维度 | 分析内容 |
|------|---------|
| `tone` | 整体语调（直接/委婉、热情/冷淡、讽刺/真诚） |
| `formality` | 正式程度（口语化/中性/正式），俚语/缩写使用 |
| `vocabulary_traits` | 用词偏好、口头禅、专业术语 vs 通俗表达 |
| `sentence_patterns` | 句式模式（长短句、排比、反问、条件句） |
| `rhetorical_devices` | 修辞手法（比喻、夸张、类比、重复、对比） |
| `punctuation_habits` | 标点习惯（省略号、感叹号、破折号使用） |
| `sentence_length` | 句子长度分布（短促/混合/冗长） |
| `opening_patterns` | 开头模式（直答/共情/反问/故事/类比） |
| `closing_patterns` | 收尾模式（总结/号召/开放问题/情绪钩子） |
| `emotional_coloring` | 情感色彩（冷静/激动/紧迫/共情/疏离） |

每个维度都会从样本中提取具体例子，确保风格可复现。结果合并到 `profile.language_style` 中，ImitationJudge 也会评估风格还原度。

## When to Use

## Input Formats

skill 接受三种输入，自动解析为结构化 Q&A 对：

### 1. 直接粘贴对话文本
用户在聊天窗口直接粘贴对话内容。支持格式：
- `Q: ... A: ...` / `问：... 答：...`
- `User: ... Assistant: ...` / `用户：... 助手：...`
- `A: ... B: ...` / `甲：... 乙：...`
- `你：... 我：...`
- 纯段落交替（奇数段=问题，偶数段=回答）
- 无法识别的格式 → 自动用 LLM 智能解析

### 2. 上传文件
用户上传 txt、md、json 文件：
- `.json` — 必须是 `[{input, output}]` 格式
- `.txt` / `.md` — 自动检测对话格式或段落结构

### 3. 结构化 JSON
直接提供 `[{input, output}]` 列表。

## Input Schema

```json
{
  "persona_name": "string",
  "samples": [{"input": "...", "output": "...", "meta": {}}],
  "target_domain": "string (optional)",
  "output_language": "zh",
  "strictness": "high | medium | low",
  "desired_skill_type": "advisor | writer | planner | coder | teacher",
  "judge_test_cases": [{"task": "...", "context": "..."}],
  "judge_pass_threshold": 0.75,
  "max_repair_rounds": 2
}
```

## Workflow

```
samples → DistillProfile → ExtractLanguageStyle → merge into profile
                                                       ↓
                                              ProfileJudge → pass?
                                                                 ↓ no
                                                          AutoRepair → retry
                                                                 ↓ yes
                                                    ImitationTest → ImitationJudge → pass?
                                                                                          ↓ no
                                                                                     AutoRepair → retry
                                                                                          ↓ yes
                                                    ExtractFewshot → GenerateSkillMD + GenerateSkillPY
                                                                                          ↓
                                                    save_to_folder()
```

1. 运行 `scripts/distill_skill.py` 或按步骤调用各方法
2. `distill_profile()` 提取决策 profile 后，`extract_language_style()` 单独做 10 维度语言风格分析
3. 两者合并到 `profile.language_style`，确保风格可复现
4. ProfileJudge 审计完整性，ImitationJudge 同时评估决策逻辑和语言风格还原度
5. 未通过则自动修复（最多 `max_repair_rounds` 轮）
6. 通过后提取 fewshot，生成 skill.md 和 skill.py

## Prompt Templates

详细的 prompt 模板见 `references/prompts.md`，包含：
- `DISTILL_PROFILE_PROMPT` — 蒸馏 profile 的主 prompt
- `PROFILE_JUDGE_PROMPT` — profile 审计 prompt
- `IMITATION_TEST_PROMPT` — 模仿测试 prompt
- `IMITATION_JUDGE_PROMPT` — 模仿评判 prompt
- `PROFILE_REPAIR_PROMPT` — profile 修复 prompt
- `EXTRACT_FEWSHOT_PROMPT` — fewshot 提取 prompt
- `GENERATE_SKILL_MD_PROMPT` — skill.md 生成 prompt
- `GENERATE_SKILL_PY_PROMPT` — skill.py 生成 prompt

## Usage Example

### 方式一：通过 Agent 对话触发（推荐）

用户在聊天窗口直接说：
- "把下面这段对话蒸馏成一个 skill：[粘贴对话]"
- "我上传了一个对话记录文件，帮我蒸馏一下"
- "从这些问答中提取这个人的风格"

Agent 读取上传文件或粘贴文本 → `SampleParser.parse()` → `parse_and_run()` → 输出 skill 包。

### 方式二：Python REPL 中调用（原始文本）

```python
from app.core.container import get_llm
from distill_skill import DistillSkill, MiniClawLLM

llm = MiniClawLLM(get_llm())
distiller = DistillSkill(llm)

raw_text = """
问：我该选什么专业？
答：先看省份分数位次，再看家庭资源...

问：土木还有前途吗？
答：如果你家没资源，你就别碰...
"""

out = distiller.parse_and_run("zhangxuefeng_v1", raw_text=raw_text, target_domain="career advice")
distiller.save_to_folder(out, "generated_skills/zhangxuefeng_v1")
```

### 方式三：Python REPL（上传文件）

```python
out = distiller.parse_and_run("expert_v1", file_path="data/chat_log.txt", target_domain="finance")
distiller.save_to_folder(out, "generated_skills/expert_v1")
```

### 方式四：命令行

```bash
# 从文件蒸馏
python -m distill_skill --samples chat_log.txt --name my_persona --domain "career"

# 从 JSON 蒸馏
python -m distill_skill --samples samples.json --name my_persona --domain "career"
```

## Output Files

| File | Description |
|------|-------------|
| `profile.json` | 蒸馏出的 persona profile（风格规则、决策启发式、红线等） |
| `fewshot.json` | 提取的代表性 few-shot 示例 |
| `skill.md` | 生成的 skill.md 文件 |
| `skill.py` | 生成的 Python skill 运行时 |
| `judge_report.json` | 评判报告（profile_judge + imitation_judge + repair_rounds） |

## Important Notes

- 不要声称"身份复制" — 提取的是决策启发式和结构习惯，不是人格复制
- `judge_pass_threshold` 默认 0.75，可根据场景调整
- 样本数量建议 ≥5 条，越多 profile 越稳定
- `_json_safe()` 方法会尝试从 LLM 输出中提取 JSON，容错性较强
