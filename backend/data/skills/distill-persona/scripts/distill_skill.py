"""
Distill Persona Skill — 从人物样本蒸馏可复用的 Agent skill profile

完整闭环: DistillProfile → ProfileJudge → ImitationTest → ImitationJudge → AutoRepair
输出: profile.json + fewshot.json + skill.md + skill.py + judge_report.json
"""

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# -----------------------------
# Data Schemas
# -----------------------------

@dataclass
class Sample:
    input: str
    output: str
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DistillInput:
    persona_name: str
    samples: List[Sample]
    target_domain: Optional[str] = None
    output_language: str = "zh"
    strictness: str = "high"  # low/medium/high
    desired_skill_type: str = "advisor"  # writer/advisor/planner/coder/teacher
    judge_test_cases: Optional[List[Dict[str, str]]] = None
    judge_pass_threshold: float = 0.75
    max_repair_rounds: int = 2


@dataclass
class DistillOutput:
    profile: Dict[str, Any]
    fewshot_examples: List[Dict[str, str]]
    extracted_rules: List[str]
    suggested_skill_md: str
    suggested_skill_py: str
    judge_report: Dict[str, Any]


# -----------------------------
# Prompt Templates
# -----------------------------

DISTILL_PROFILE_PROMPT = """\
You are a distillation engine.
Given many samples of a person's responses, extract a reusable skill profile.

IMPORTANT:
- Do not claim identity replication.
- Extract decision heuristics, structure habits, and evaluation rubric.
- Output must be actionable for an agent.

OUTPUT LANGUAGE: {output_language}
STRICTNESS: {strictness}
DESIRED SKILL TYPE: {desired_skill_type}
TARGET DOMAIN (optional): {target_domain}

SAMPLES:
{samples_json}

Return JSON with fields:
{{
  "persona_name": "{persona_name}",
  "domain": "...",
  "style_rules": ["..."],
  "structure_preferences": ["..."],
  "intake_questions": ["..."],
  "decision_heuristics": ["..."],
  "redlines": ["..."],
  "common_phrases": ["..."],
  "output_templates": {{
      "default": "...",
      "analysis": "...",
      "recommendation": "..."
  }},
  "language_style": {{
      "tone": "...",
      "formality": "casual|neutral|formal",
      "vocabulary_traits": ["..."],
      "sentence_patterns": ["..."],
      "rhetorical_devices": ["..."],
      "punctuation_habits": ["..."],
      "sentence_length": "short|mixed|long",
      "opening_patterns": ["..."],
      "closing_patterns": ["..."],
      "emotional_coloring": "..."
  }},
  "judge_rubric": {{
      "alignment": 0.35,
      "usefulness": 0.35,
      "correctness": 0.2,
      "clarity": 0.1
  }},
  "scoring_rules": [
      {{
        "name": "...",
        "description": "...",
        "weight": 0.0
      }}
  ]
}}
"""

EXTRACT_FEWSHOT_PROMPT = """\
You are selecting representative examples for few-shot prompting.

PERSONA PROFILE:
{profile_json}

SAMPLES:
{samples_json}

Select at most {k} best samples that best represent this person's style and decision logic.
Return JSON list:
[
  {{"input": "...", "output": "..."}},
  ...
]
"""

GENERATE_SKILL_MD_PROMPT = """\
You are generating a skill.md file.

PERSONA PROFILE:
{profile_json}

Write a production-ready skill.md in markdown.
Must include:
- overview
- inputs/outputs schema
- when to use
- refusal rules
- execution protocol
"""

GENERATE_SKILL_PY_PROMPT = """\
You are generating a Python skill runtime.

PERSONA PROFILE:
{profile_json}

Write a minimal but runnable Python module that:
- loads profile.json
- provides run(task, context) method
- has planner -> generator -> judge -> finalizer
- returns structured JSON output

Do NOT include external dependencies beyond stdlib.
"""

PROFILE_JUDGE_PROMPT = """\
You are a strict skill profile auditor.

Your job is to judge whether the profile is:
- internally consistent
- actionable for execution
- faithful to the samples
- complete enough to generate stable outputs

PROFILE:
{profile_json}

SAMPLES:
{samples_json}

Return JSON:
{{
  "pass": true/false,
  "score": 0.0,
  "missing_fields": ["..."],
  "inconsistencies": ["..."],
  "weak_rules": ["..."],
  "repair_suggestions": ["..."],
  "summary": "..."
}}
"""

IMITATION_TEST_PROMPT = """\
You are testing whether an agent can imitate this persona.

PERSONA PROFILE:
{profile_json}

TEST CASES:
{test_cases_json}

For each test case, produce a short answer using the persona style.
Return JSON list:
[
  {{
    "task": "...",
    "generated": "...",
    "key_rules_used": ["..."]
  }}
]
"""

IMITATION_JUDGE_PROMPT = """\
You are a strict evaluator of persona imitation.

You will compare generated answers to the reference style in samples.
Judge if the generated answer matches:
- tone & phrasing
- structure
- decision logic
- language style (vocabulary, sentence patterns, rhetorical devices, emotional coloring)

PROFILE:
{profile_json}

SAMPLES:
{samples_json}

GENERATED OUTPUTS:
{generated_json}

Return JSON:
{{
  "score": 0.0,
  "pass": true/false,
  "failure_modes": ["..."],
  "suggested_profile_fixes": ["..."]
}}
"""

PROFILE_REPAIR_PROMPT = """\
You are a profile repair engine.
Modify the profile to fix the issues while keeping it faithful to samples.

CURRENT PROFILE:
{profile_json}

SAMPLES:
{samples_json}

ISSUES:
{issues_json}

Return a repaired profile JSON (same schema as before).
"""

STYLE_EXTRACTOR_PROMPT = """\
You are a linguistic style analyst. Analyze the language STYLE of the person in these samples.

Do NOT analyze content or decision logic — focus ONLY on HOW they speak/write.

Analyze these dimensions:
1. **Tone**: overall attitude (direct/roundabout, warm/cold, sarcastic/sincere, confident/hesitant)
2. **Formality**: casual/neutral/formal, use of slang, contractions, honorifics
3. **Vocabulary traits**: preferred word categories, recurring expressions, technical jargon vs plain language, filler words
4. **Sentence patterns**: long vs short, simple vs compound, use of lists/bullet points, rhetorical questions, conditional structures, parallel constructions
5. **Rhetorical devices**: metaphors, analogies, exaggeration, understatement, repetition, contrast, enumeration, rhetorical questions
6. **Punctuation habits**: heavy/light punctuation, ellipsis usage, exclamation marks, dashes, parentheses
7. **Sentence length distribution**: predominantly short punchy sentences, medium mixed, or long flowing ones
8. **Opening patterns**: how they typically start a response (direct answer, empathy first, counter-question, story, analogy)
9. **Closing patterns**: how they end (conclusion, call to action, open question, emotional hook)
10. **Emotional coloring**: emotional baseline (calm, enthusiastic, urgent, empathetic, detached)

SAMPLES:
{samples_json}

Return JSON:
{{
  "tone": "one-paragraph description of overall tone",
  "formality": "casual|neutral|formal",
  "vocabulary_traits": ["specific vocabulary habits with examples"],
  "sentence_patterns": ["specific sentence structure patterns with examples"],
  "rhetorical_devices": ["devices used with examples from samples"],
  "punctuation_habits": ["punctuation patterns with examples"],
  "sentence_length": "short|mixed|long",
  "opening_patterns": ["how they start responses, with examples"],
  "closing_patterns": ["how they end responses, with examples"],
  "emotional_coloring": "one-paragraph description of emotional baseline",
  "style_signature": "a 2-3 sentence summary that captures the unique voice"
}}
"""


# -----------------------------
# LLM Interface
# -----------------------------
class LLM:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError


class MiniClawLLM(LLM):
    """Adapter: wraps miniClaw's ChatOpenAI / BaseChatModel into DistillSkill's LLM interface."""

    def __init__(self, chat_model):
        """
        Args:
            chat_model: langchain BaseChatModel instance (from app.core.llm.create_llm or container.get)
        """
        self._model = chat_model

    def complete(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage
        resp = self._model.invoke([HumanMessage(content=prompt)])
        return resp.content if hasattr(resp, "content") else str(resp)


# -----------------------------
# Sample Parser
# -----------------------------

PARSE_SAMPLES_PROMPT = """\
You are parsing raw text into structured Q&A pairs for persona distillation.

The text below may be:
- A chat log (User/Assistant, Q/A, 问/答, A:/B:, 你/我)
- A transcript (speaker turns)
- A markdown document with sections
- Raw paragraphs that alternate between questions and answers
- A mix of formats

Split the text into input/output pairs. Each "input" is what was asked or prompted,
each "output" is the person's response. If the format is ambiguous, treat alternating
paragraphs as input/output.

TEXT:
{text}

Return JSON list (at least 3 pairs if possible):
[
  {{"input": "...", "output": "..."}},
  ...
]
"""

# Regex patterns for common dialogue formats (ordered by specificity)
_DIALOG_PATTERNS = [
    # Q: ... A: ...  or  问：... 答：...
    (r'(?:^|\n)[Qq]\s*[:：]\s*(.+?)(?=\n(?:[Aa]|答)\s*[:：])\n(?:[Aa]|答)\s*[:：]\s*(.+?)(?=\n[Qq]|$)', "qa"),
    # User: ... Assistant: ...  /  用户：... 助手：...
    (r'(?:^|\n)(?:User|用户)\s*[:：]\s*(.+?)(?=\n(?:Assistant|助手)\s*[:：])\n(?:Assistant|助手)\s*[:：]\s*(.+?)(?=\n(?:User|用户)|$)', "user_assistant"),
    # A: ... B: ...  (alternating speakers)
    (r'(?:^|\n)[A甲]\s*[:：]\s*(.+?)(?=\n[B乙]\s*[:：])\n[B乙]\s*[:：]\s*(.+?)(?=\n[A甲]|$)', "ab"),
    # 你：... 我：...  or 我：... 你：...
    (r'(?:^|\n)(?:你|问)\s*[:：]\s*(.+?)(?=\n(?:我|答)\s*[:：])\n(?:我|答)\s*[:：]\s*(.+?)(?=\n(?:你|问)|$)', "ni_wo"),
]


class SampleParser:
    """Parse raw text (pasted dialogue, file content) into structured Sample list.

    Supports:
    - Structured formats: Q:/A:, User:/Assistant:, 你:/我:, A:/B:
    - Markdown with ## headers as topic dividers
    - Raw paragraphs (alternating input/output)
    - LLM-assisted fallback for unstructured text
    """

    def __init__(self, llm: Optional[LLM] = None):
        self.llm = llm

    def parse(self, text: str, persona_name: str = "unknown") -> List[Sample]:
        """Parse raw text into Sample list. Tries regex first, falls back to LLM."""
        text = text.strip()
        if not text:
            return []

        # Try structured formats
        samples = self._parse_structured(text)
        if len(samples) >= 2:
            return samples

        # Try paragraph splitting
        samples = self._parse_paragraphs(text)
        if len(samples) >= 2:
            return samples

        # LLM fallback
        if self.llm:
            return self._parse_with_llm(text)

        return samples

    def parse_file(self, file_path: str, persona_name: str = "unknown") -> List[Sample]:
        """Read a txt/md/json file and parse into Sample list."""
        path = file_path.strip()
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if path.endswith(".json"):
            return self._parse_json(content)

        return self.parse(content, persona_name)

    def _parse_json(self, content: str) -> List[Sample]:
        """Parse pre-structured JSON: [{input, output, ...}]."""
        data = json.loads(content)
        if isinstance(data, list):
            return [
                Sample(input=item["input"], output=item["output"], meta=item.get("meta", {}))
                for item in data if "input" in item and "output" in item
            ]
        return []

    def _parse_structured(self, text: str) -> List[Sample]:
        """Try regex-based parsing for common dialogue formats."""
        for pattern, _fmt in _DIALOG_PATTERNS:
            matches = re.findall(pattern, text, re.DOTALL)
            if len(matches) >= 2:
                return [
                    Sample(input=m[0].strip(), output=m[1].strip())
                    for m in matches
                ]
        return []

    def _parse_paragraphs(self, text: str) -> List[Sample]:
        """Split into paragraphs and pair them as input/output."""
        # Handle markdown headers as dividers
        sections = re.split(r'\n#{1,3}\s+', text)
        if len(sections) >= 3:
            pairs = []
            for i in range(1, len(sections) - 1, 2):
                inp = sections[i].strip()
                out = sections[i + 1].strip() if i + 1 < len(sections) else ""
                if inp and out:
                    pairs.append(Sample(input=inp, output=out))
            return pairs

        # Split by double newlines, pair alternating
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        if len(paragraphs) < 2:
            return []

        pairs = []
        for i in range(0, len(paragraphs) - 1, 2):
            pairs.append(Sample(input=paragraphs[i], output=paragraphs[i + 1]))
        return pairs

    def _parse_with_llm(self, text: str) -> List[Sample]:
        """Use LLM to parse unstructured text into Q&A pairs."""
        # Truncate very long text to avoid token overflow
        truncated = text[:8000] if len(text) > 8000 else text
        prompt = PARSE_SAMPLES_PROMPT.format(text=truncated)
        result = self.llm.complete(prompt)

        # Extract JSON
        start = result.find("[")
        end = result.rfind("]")
        if start != -1 and end != -1:
            try:
                pairs = json.loads(result[start:end+1])
                return [
                    Sample(input=p["input"], output=p["output"])
                    for p in pairs if "input" in p and "output" in p
                ]
            except (json.JSONDecodeError, TypeError):
                pass
        return []


# -----------------------------
# Distill Skill
# -----------------------------

def _ensure_list(val):
    """Ensure a value is a list. Handles LLM returning dict/str instead of list."""
    if isinstance(val, list):
        return val
    if isinstance(val, dict):
        return [f"{k}: {v}" for k, v in val.items()]
    if isinstance(val, str):
        return [val]
    return []


class DistillSkill:
    def __init__(self, llm: LLM):
        self.llm = llm
        self.parser = SampleParser(llm=llm)

    def parse_and_run(self, persona_name: str, raw_text: str = "", file_path: str = "",
                      **kwargs) -> DistillOutput:
        """One-shot: parse raw text or file, then run full distillation pipeline.

        Args:
            persona_name: Name for the distilled persona
            raw_text: Pasted dialogue text (optional)
            file_path: Path to txt/md/json file (optional)
            **kwargs: Additional DistillInput fields (target_domain, strictness, etc.)

        Returns:
            DistillOutput with all generated artifacts
        """
        if file_path:
            samples = self.parser.parse_file(file_path, persona_name)
        elif raw_text:
            samples = self.parser.parse(raw_text, persona_name)
        else:
            raise ValueError("Must provide raw_text or file_path")

        if not samples:
            raise RuntimeError(f"Failed to extract any Q&A pairs from input")

        inp = DistillInput(persona_name=persona_name, samples=samples, **kwargs)
        return self.run(inp)

    def reinforce_skill(self, profile: Dict[str, Any], new_samples: List[Sample],
                        persona_name: str = "", **kwargs) -> DistillOutput:
        """Reinforce an existing profile with new samples. Incremental distillation.

        Takes an existing profile (e.g., from a previous run) and additional samples,
        then re-distills with the combined data for a stronger profile.

        Args:
            profile: Existing profile dict (from profile.json)
            new_samples: Additional samples to reinforce with
            persona_name: Override name (defaults to profile's persona_name)
            **kwargs: Additional DistillInput fields

        Returns:
            New DistillOutput with reinforced profile
        """
        name = persona_name or profile.get("persona_name", "unknown")

        # Merge new language style analysis with existing
        new_style = self.extract_language_style(samples=new_samples)
        existing_style = profile.get("language_style", {})
        if existing_style and new_style:
            # Deep merge: new data supplements existing
            for key in new_style:
                if key not in existing_style or not existing_style[key]:
                    existing_style[key] = new_style[key]
                elif isinstance(existing_style[key], list) and isinstance(new_style[key], list):
                    # Append new items, deduplicate
                    existing_set = set(str(x) for x in existing_style[key])
                    for item in new_style[key]:
                        if str(item) not in existing_set:
                            existing_style[key].append(item)
            profile["language_style"] = existing_style

        # Run full pipeline with new samples, using existing profile as seed
        inp = DistillInput(persona_name=name, samples=new_samples, **kwargs)
        samples_json = self._samples_to_json_budgeted(new_samples)

        # Generate new profile from new samples
        new_profile = self.distill_profile(inp)

        # Save old profile values for post-repair re-merge
        old_field_values = {}
        for field in ["style_rules", "decision_heuristics", "redlines", "common_phrases",
                      "structure_preferences", "intake_questions"]:
            old_field_values[field] = _ensure_list(profile.get(field, []))

        # Keep the richer language_style
        if existing_style:
            new_profile["language_style"] = existing_style

        # Judge + repair loop (same as run())
        judge_report: Dict[str, Any] = {
            "profile_judge": None,
            "imitation_judge": None,
            "repair_rounds": []
        }

        threshold = kwargs.get("judge_pass_threshold", 0.75)
        max_repairs = kwargs.get("max_repair_rounds", 2)
        test_cases = inp.judge_test_cases or self._default_test_cases(new_samples)

        for r in range(max_repairs + 1):
            profile_judge = self.judge_profile(new_profile, samples_json)
            generated = self.imitation_test(new_profile, test_cases)
            imitation_judge = self.imitation_judge(new_profile, samples_json, generated)

            judge_report["profile_judge"] = profile_judge
            judge_report["imitation_judge"] = imitation_judge

            combined_score = min(
                float(profile_judge.get("score", 0.0)),
                float(imitation_judge.get("score", 0.0))
            )

            pass_flag = (
                bool(profile_judge.get("pass", False))
                and bool(imitation_judge.get("pass", False))
                and combined_score >= threshold
            )

            if pass_flag:
                break

            issues = {
                "profile_judge": profile_judge,
                "imitation_judge": imitation_judge,
                "generated_examples": generated,
                "threshold": threshold
            }
            repaired = self.repair_profile(new_profile, samples_json, issues)
            judge_report["repair_rounds"].append({
                "round": r, "combined_score": combined_score, "issues": issues
            })
            new_profile = repaired

        # Re-merge old profile data AFTER repair loop completes
        # repair_profile() may overwrite merged fields with LLM output,
        # so we re-apply the merge to preserve old profile's specific entries.
        for field in ["style_rules", "decision_heuristics", "redlines", "common_phrases",
                      "structure_preferences", "intake_questions"]:
            old_vals = old_field_values[field]
            new_vals = _ensure_list(new_profile.get(field, []))
            merged = list(new_vals)  # Start with repaired/new data
            existing_set = set(str(v) for v in merged)
            for v in old_vals:
                if str(v) not in existing_set:
                    merged.append(v)
                    existing_set.add(str(v))
            new_profile[field] = merged

        # Extract fewshot from combined samples
        fewshot = self.extract_fewshot(new_profile, samples_json, k=8)

        extracted_rules = (
            _ensure_list(new_profile.get("style_rules", []))
            + _ensure_list(new_profile.get("decision_heuristics", []))
            + _ensure_list(new_profile.get("redlines", []))
        )

        skill_md = self.generate_skill_md(new_profile)
        skill_py = self.generate_skill_py(new_profile)

        return DistillOutput(
            profile=new_profile,
            fewshot_examples=fewshot,
            extracted_rules=extracted_rules,
            suggested_skill_md=skill_md,
            suggested_skill_py=skill_py,
            judge_report=judge_report
        )

    def _json_safe(self, text: str) -> Any:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass

        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass

        return {}

    # Maximum chars for samples JSON in a single prompt (conservative for most LLMs)
    MAX_SAMPLES_CHARS = 30000

    def _samples_to_json(self, samples: List[Sample], limit: int = 120) -> str:
        trimmed = samples[:limit]
        data = [{"input": s.input, "output": s.output, "meta": s.meta} for s in trimmed]
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _samples_to_json_budgeted(self, samples: List[Sample], max_chars: int = 0) -> str:
        """Build samples JSON within a character budget. Truncates individual outputs if needed."""
        budget = max_chars or self.MAX_SAMPLES_CHARS
        data = []
        remaining = budget
        for s in samples:
            entry = {"input": s.input, "output": s.output}
            entry_size = len(json.dumps(entry, ensure_ascii=False))
            if entry_size <= remaining:
                data.append(entry)
                remaining -= entry_size
            else:
                # Truncate output to fit
                allowed = max(remaining - 50, 100)
                truncated_output = s.output[:allowed] + "..."
                data.append({"input": s.input, "output": truncated_output})
                break
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _default_test_cases(self, samples: List[Sample], k: int = 6) -> List[Dict[str, str]]:
        return [{"task": s.input, "context": ""} for s in samples[:k]]

    def distill_profile(self, inp: DistillInput) -> Dict[str, Any]:
        samples_json = self._samples_to_json_budgeted(inp.samples)
        p_prompt = DISTILL_PROFILE_PROMPT.format(
            persona_name=inp.persona_name,
            output_language=inp.output_language,
            strictness=inp.strictness,
            desired_skill_type=inp.desired_skill_type,
            target_domain=inp.target_domain or "",
            samples_json=samples_json
        )
        profile_text = self.llm.complete(p_prompt)
        profile = self._json_safe(profile_text)
        if not profile:
            raise RuntimeError("Distill failed: cannot parse profile JSON.")
        return profile

    def extract_language_style(self, samples_json: str = "", samples: List[Sample] = None) -> Dict[str, Any]:
        """Deep linguistic style analysis — focus on HOW they speak, not WHAT they say."""
        if not samples_json and samples:
            samples_json = self._samples_to_json_budgeted(samples)
        prompt = STYLE_EXTRACTOR_PROMPT.format(samples_json=samples_json)
        style_text = self.llm.complete(prompt)
        style = self._json_safe(style_text)
        if not style:
            style = {"style_signature": "style extraction failed"}
        return style

    def judge_profile(self, profile: Dict[str, Any], samples_json: str) -> Dict[str, Any]:
        prompt = PROFILE_JUDGE_PROMPT.format(
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
            samples_json=samples_json
        )
        judge_text = self.llm.complete(prompt)
        judge = self._json_safe(judge_text)
        if not judge:
            judge = {"pass": False, "score": 0.0, "summary": "judge parse failed"}
        return judge

    def imitation_test(self, profile: Dict[str, Any], test_cases: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        prompt = IMITATION_TEST_PROMPT.format(
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
            test_cases_json=json.dumps(test_cases, ensure_ascii=False, indent=2)
        )
        gen_text = self.llm.complete(prompt)
        generated = self._json_safe(gen_text)
        if not isinstance(generated, list):
            generated = []
        return generated

    def imitation_judge(self, profile: Dict[str, Any], samples_json: str, generated: List[Dict[str, Any]]) -> Dict[str, Any]:
        prompt = IMITATION_JUDGE_PROMPT.format(
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
            samples_json=samples_json,
            generated_json=json.dumps(generated, ensure_ascii=False, indent=2)
        )
        judge_text = self.llm.complete(prompt)
        judge = self._json_safe(judge_text)
        if not judge:
            judge = {"pass": False, "score": 0.0, "failure_modes": ["judge parse failed"]}
        return judge

    def repair_profile(self, profile: Dict[str, Any], samples_json: str, issues: Dict[str, Any]) -> Dict[str, Any]:
        prompt = PROFILE_REPAIR_PROMPT.format(
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
            samples_json=samples_json,
            issues_json=json.dumps(issues, ensure_ascii=False, indent=2)
        )
        repaired_text = self.llm.complete(prompt)
        repaired = self._json_safe(repaired_text)
        return repaired if repaired else profile

    def extract_fewshot(self, profile: Dict[str, Any], samples_json: str, k: int = 8) -> List[Dict[str, str]]:
        prompt = EXTRACT_FEWSHOT_PROMPT.format(
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
            samples_json=samples_json,
            k=k
        )
        fewshot_text = self.llm.complete(prompt)
        fewshot = self._json_safe(fewshot_text)
        return fewshot if isinstance(fewshot, list) else []

    def generate_skill_md(self, profile: Dict[str, Any]) -> str:
        """Generate standard SKILL.md from profile data — deterministic, no LLM needed."""
        name = profile.get("persona_name", "unknown")
        domain = profile.get("domain", "")
        style_rules = _ensure_list(profile.get("style_rules", []))
        structure_prefs = _ensure_list(profile.get("structure_preferences", []))
        decision_heuristics = _ensure_list(profile.get("decision_heuristics", []))
        redlines = _ensure_list(profile.get("redlines", []))
        common_phrases = _ensure_list(profile.get("common_phrases", []))
        intake_questions = _ensure_list(profile.get("intake_questions", []))
        scoring_rules = _ensure_list(profile.get("scoring_rules", []))
        language_style = profile.get("language_style", {})
        templates = profile.get("output_templates", {})

        # Build YAML frontmatter
        skill_name = name.replace("_", "-")
        desc_triggers = f"用 {name} 风格撰写内容"
        description = (
            f"{desc_triggers}。当用户要求用「{name}」风格写作、"
            f"生成{domain}类内容、或需要模仿该 persona 的表达方式时触发。"
        )

        # Build style rules section
        rules_md = ""
        for r in style_rules:
            rules_md += f"- {r}\n"

        # Build structure section
        struct_md = ""
        for s in structure_prefs:
            struct_md += f"- {s}\n"

        # Build decision heuristics table
        heuristics_md = ""
        for h in decision_heuristics:
            heuristics_md += f"- {h}\n"

        # Build redlines section
        redlines_md = ""
        for r in redlines:
            redlines_md += f"- {r}\n"

        # Build language style section
        lang_md = ""
        if language_style:
            tone = language_style.get("tone", "")
            formality = language_style.get("formality", "")
            sent_length = language_style.get("sentence_length", "")
            vocab = _ensure_list(language_style.get("vocabulary_traits", []))
            patterns = _ensure_list(language_style.get("sentence_patterns", []))
            devices = _ensure_list(language_style.get("rhetorical_devices", []))
            openings = _ensure_list(language_style.get("opening_patterns", []))
            closings = _ensure_list(language_style.get("closing_patterns", []))
            emotional = language_style.get("emotional_coloring", "")
            signature = language_style.get("style_signature", "")

            if formality:
                lang_md += f"**正式度**: {formality}\n\n"
            if sent_length:
                lang_md += f"**句长**: {sent_length}\n\n"
            if tone:
                lang_md += f"**语调**: {tone}\n\n"
            if vocab:
                lang_md += "**用词特征**:\n"
                for v in vocab:
                    lang_md += f"- {v}\n"
                lang_md += "\n"
            if patterns:
                lang_md += "**句式模式**:\n"
                for p in patterns:
                    lang_md += f"- {p}\n"
                lang_md += "\n"
            if devices:
                lang_md += "**修辞手法**:\n"
                for d in devices:
                    lang_md += f"- {d}\n"
                lang_md += "\n"
            if openings:
                lang_md += "**开头模式**:\n"
                for o in openings:
                    lang_md += f"- {o}\n"
                lang_md += "\n"
            if closings:
                lang_md += "**收尾模式**:\n"
                for c in closings:
                    lang_md += f"- {c}\n"
                lang_md += "\n"
            if emotional:
                lang_md += f"**情感色彩**: {emotional}\n\n"
            if signature:
                lang_md += f"**风格签名**: {signature}\n\n"

        # Build common phrases
        phrases_md = ""
        for p in common_phrases:
            phrases_md += f"- {p}\n"

        # Build intake questions
        intake_md = ""
        for q in intake_questions:
            intake_md += f"- {q}\n"

        # Build templates
        templates_md = ""
        for tname, tmpl in templates.items():
            templates_md += f"### {tname}\n```\n{tmpl}\n```\n\n"

        # Build scoring rubric
        scoring_md = ""
        for sr in scoring_rules:
            if isinstance(sr, dict):
                scoring_md += f"| {sr.get('name', '')} | {sr.get('weight', 0) * 100:.0f}% | {sr.get('description', '')} |\n"
            else:
                scoring_md += f"| {sr} | - | - |\n"

        # Assemble
        content = f"""---
name: {skill_name}
description: >
  {description}
---

# {name}

## Overview

从样本中蒸馏出的 persona skill。领域：{domain}。

## Execution Protocol

### Step 1: 收集信息（Intake）

{intake_md if intake_md else "根据用户输入确定写作任务的具体要求。"}

### Step 2: 结构模板

{struct_md if struct_md else "根据任务类型选择合适的输出结构。"}

{templates_md if templates_md else ""}

### Step 3: 风格规则

{rules_md if rules_md else "保持 persona 的一致风格。"}

### Step 4: 决策启发式

{heuristics_md if heuristics_md else "根据上下文灵活决策。"}

### Step 5: 语言风格

{lang_md if lang_md else "保持 persona 的语言特征。"}

### Step 6: 红线（绝不违反）

{redlines_md if redlines_md else "保持内容的一致性和合理性。"}

## Common Phrases

{phrases_md if phrases_md else ""}

## Quality Scoring

| 维度 | 权重 | 指标 |
|------|------|------|
{scoring_md if scoring_md else "| - | - | - |"}
"""
        return content

    def generate_skill_py(self, profile: Dict[str, Any]) -> str:
        prompt = GENERATE_SKILL_PY_PROMPT.format(
            profile_json=json.dumps(profile, ensure_ascii=False, indent=2)
        )
        return self.llm.complete(prompt).strip()

    def deploy_skill(self, out: DistillOutput, target_skills_dir: str = "data/skills") -> str:
        """Save as standard miniClaw skill with SKILL.md (not skill.md) and deploy.

        Args:
            out: DistillOutput from run()
            target_skills_dir: Path to the skills directory (default: data/skills)

        Returns:
            Path to deployed skill directory
        """
        name = out.profile.get("persona_name", "unknown")
        skill_name = name.replace("_", "-")
        skill_dir = os.path.join(target_skills_dir, skill_name)
        os.makedirs(skill_dir, exist_ok=True)

        # SKILL.md — standard miniClaw format
        skill_md = self.generate_skill_md(out.profile)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(skill_md)

        # Supporting data files
        with open(os.path.join(skill_dir, "profile.json"), "w", encoding="utf-8") as f:
            json.dump(out.profile, f, ensure_ascii=False, indent=2)

        with open(os.path.join(skill_dir, "fewshot.json"), "w", encoding="utf-8") as f:
            json.dump(out.fewshot_examples, f, ensure_ascii=False, indent=2)

        with open(os.path.join(skill_dir, "judge_report.json"), "w", encoding="utf-8") as f:
            json.dump(out.judge_report, f, ensure_ascii=False, indent=2)

        # Optional: skill.py if generated
        if out.suggested_skill_py:
            scripts_dir = os.path.join(skill_dir, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "skill.py"), "w", encoding="utf-8") as f:
                f.write(out.suggested_skill_py)

        return skill_dir

    def run(self, inp: DistillInput, fewshot_k: int = 8) -> DistillOutput:
        samples_json = self._samples_to_json(inp.samples)

        # 1) distill initial profile
        profile = self.distill_profile(inp)

        # 2) deep language style extraction (parallel dimension to profile)
        language_style = self.extract_language_style(samples_json)

        # merge language_style into profile (profile may already have a partial one)
        if "language_style" not in profile or not profile["language_style"]:
            profile["language_style"] = language_style
        else:
            # deep merge: extracted style takes precedence for its dedicated fields
            profile["language_style"].update({k: v for k, v in language_style.items() if v})

        judge_report: Dict[str, Any] = {
            "profile_judge": None,
            "imitation_judge": None,
            "repair_rounds": []
        }

        # 2) judge + repair loop
        test_cases = inp.judge_test_cases or self._default_test_cases(inp.samples)

        for r in range(inp.max_repair_rounds + 1):
            profile_judge = self.judge_profile(profile, samples_json)
            generated = self.imitation_test(profile, test_cases)
            imitation_judge = self.imitation_judge(profile, samples_json, generated)

            judge_report["profile_judge"] = profile_judge
            judge_report["imitation_judge"] = imitation_judge

            combined_score = min(
                float(profile_judge.get("score", 0.0)),
                float(imitation_judge.get("score", 0.0))
            )

            pass_flag = (
                bool(profile_judge.get("pass", False))
                and bool(imitation_judge.get("pass", False))
                and combined_score >= inp.judge_pass_threshold
            )

            if pass_flag:
                break

            issues = {
                "profile_judge": profile_judge,
                "imitation_judge": imitation_judge,
                "generated_examples": generated,
                "threshold": inp.judge_pass_threshold
            }

            repaired = self.repair_profile(profile, samples_json, issues)
            judge_report["repair_rounds"].append({
                "round": r,
                "combined_score": combined_score,
                "issues": issues
            })
            profile = repaired

        # 3) extract fewshot
        fewshot = self.extract_fewshot(profile, samples_json, k=fewshot_k)

        # 4) rules list
        extracted_rules = (
            _ensure_list(profile.get("style_rules", []))
            + _ensure_list(profile.get("decision_heuristics", []))
            + _ensure_list(profile.get("redlines", []))
        )

        # 5) generate final skill artifacts
        skill_md = self.generate_skill_md(profile)
        skill_py = self.generate_skill_py(profile)

        return DistillOutput(
            profile=profile,
            fewshot_examples=fewshot,
            extracted_rules=extracted_rules,
            suggested_skill_md=skill_md,
            suggested_skill_py=skill_py,
            judge_report=judge_report
        )

    def save_to_folder(self, out: DistillOutput, folder: str):
        os.makedirs(folder, exist_ok=True)

        with open(os.path.join(folder, "profile.json"), "w", encoding="utf-8") as f:
            json.dump(out.profile, f, ensure_ascii=False, indent=2)

        with open(os.path.join(folder, "fewshot.json"), "w", encoding="utf-8") as f:
            json.dump(out.fewshot_examples, f, ensure_ascii=False, indent=2)

        # Always write SKILL.md (standard format), not the LLM-generated skill.md
        skill_md = self.generate_skill_md(out.profile)
        with open(os.path.join(folder, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(skill_md)

        if out.suggested_skill_py:
            scripts_dir = os.path.join(folder, "scripts")
            os.makedirs(scripts_dir, exist_ok=True)
            with open(os.path.join(scripts_dir, "skill.py"), "w", encoding="utf-8") as f:
                f.write(out.suggested_skill_py)

        with open(os.path.join(folder, "judge_report.json"), "w", encoding="utf-8") as f:
            json.dump(out.judge_report, f, ensure_ascii=False, indent=2)


# -----------------------------
# CLI Entry Point
# -----------------------------
if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="Distill a persona from samples")
    parser.add_argument("--samples", required=True, help="Path to samples JSON file")
    parser.add_argument("--name", required=True, help="Persona name")
    parser.add_argument("--domain", default=None, help="Target domain")
    parser.add_argument("--language", default="zh", help="Output language")
    parser.add_argument("--strictness", default="high", choices=["low", "medium", "high"])
    parser.add_argument("--skill-type", default="advisor", choices=["writer", "advisor", "planner", "coder", "teacher"])
    parser.add_argument("--threshold", type=float, default=0.75, help="Judge pass threshold")
    parser.add_argument("--max-repairs", type=int, default=2, help="Max repair rounds")
    parser.add_argument("--output", default=None, help="Output folder (default: generated_skills/{name})")
    args = parser.parse_args()

    with open(args.samples, "r", encoding="utf-8") as f:
        raw = f.read()

    # Auto-detect format: JSON or raw text
    parser = SampleParser()
    if args.samples.endswith(".json"):
        samples = parser._parse_json(raw)
    else:
        samples = parser.parse(raw, args.name)

    from langchain_openai import ChatOpenAI
    from app.config import settings

    llm = MiniClawLLM(ChatOpenAI(
        base_url=settings.openai_base_url,
        api_key=settings.openai_api_key,
        model=settings.openai_model,
        temperature=0.1,
    ))

    distiller = DistillSkill(llm)
    out = distiller.run(DistillInput(
        persona_name=args.name,
        samples=samples,
        target_domain=args.domain,
        output_language=args.language,
        strictness=args.strictness,
        desired_skill_type=args.skill_type,
        judge_pass_threshold=args.threshold,
        max_repair_rounds=args.max_repairs,
    ))

    output_folder = args.output or f"generated_skills/{args.name}"
    distiller.save_to_folder(out, output_folder)
    print(f"Skill saved to {output_folder}/")
    print(f"Judge score: {out.judge_report.get('profile_judge', {}).get('score', 'N/A')}")
