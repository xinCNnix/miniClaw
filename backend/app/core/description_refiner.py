"""
Description Refiner Module

Uses LLM to refine skill descriptions into short, UI-friendly summaries.
"""

import re
from typing import Optional
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_default_llm
from app.config import get_settings


class DescriptionRefiner:
    """
    Refines skill descriptions using LLM.

    Takes full skill descriptions (from SKILL.md) and generates
    concise, UI-friendly summaries.
    """

    def __init__(self):
        """Initialize the description refiner."""
        self.llm = get_default_llm()
        self._init_prompts()

    def _init_prompts(self):
        """Initialize refinement prompts for different locales."""
        # Chinese refinement prompt
        self.zh_prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个专业的文案编辑，擅长将详细描述精炼为简短摘要。"),
            ("user", """请将以下技能描述精炼为简短摘要。

要求：
- 中文不超过20个字
- 英文不超过15个词
- 保留核心功能
- 简洁明了，适合在UI界面显示
- 只返回精炼后的描述，不要其他内容

技能描述：
{description}

精炼后的描述（中文）：""")
        ])

        # English refinement prompt
        self.en_prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a professional editor specializing in concise summaries."),
            ("user", """Please refine the following skill description into a short summary.

Requirements:
- Chinese: ≤20 characters
- English: ≤15 words
- Keep core functionality
- Concise and clear, suitable for UI display
- Return ONLY the refined description, no other content

Skill description:
{description}

Refined description (Chinese):""")
        ])

    async def refine_description(
        self,
        skill_content: str,
        locale: str = "zh"
    ) -> tuple[str, str]:
        """
        Refine a skill description into short summaries.

        Args:
            skill_content: Full skill content (from SKILL.md)
            locale: Target locale ('zh' or 'en')

        Returns:
            Tuple of (chinese_description, english_description)

        Raises:
            Exception: If LLM call fails
        """
        # Extract the relevant part (frontmatter description or first paragraph)
        description = self._extract_description(skill_content)

        # Use appropriate prompt based on locale
        prompt = self.zh_prompt if locale == "zh" else self.en_prompt

        try:
            # Invoke LLM
            chain = prompt | self.llm
            result = await chain.ainvoke({"description": description})

            # Parse response
            refined = result.content.strip()

            # Try to extract both Chinese and English if present
            zh_desc, en_desc = self._parse_bilingual_response(refined)

            # If only one language returned, generate the other
            if not zh_desc:
                zh_desc = await self._refine_chinese_only(description)
            if not en_desc:
                en_desc = await self._refine_english_only(description)

            return zh_desc, en_desc

        except Exception as e:
            print(f"Error refining description: {e}")
            # Fallback to truncated original
            return self._fallback_description(description)

    def _extract_description(self, skill_content: str) -> str:
        """
        Extract the description from skill content.

        Args:
            skill_content: Full SKILL.md content

        Returns:
            Extracted description
        """
        # Try to extract from frontmatter
        if skill_content.startswith("---"):
            parts = skill_content.split("---", 2)
            if len(parts) >= 3:
                try:
                    import yaml
                    frontmatter = yaml.safe_load(parts[1])
                    desc = frontmatter.get("description", "")
                    if desc:
                        return desc
                except:
                    pass

        # Fallback: get first paragraph or first few lines
        lines = skill_content.split("\n")
        description_lines = []

        for line in lines[10:]:  # Skip frontmatter
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("-"):
                description_lines.append(line)
                if len(" ".join(description_lines)) > 100:
                    break

        return " ".join(description_lines) if description_lines else skill_content[:200]

    def _parse_bilingual_response(self, response: str) -> tuple[str, str]:
        """
        Parse response that may contain both Chinese and English.

        Args:
            response: LLM response

        Returns:
            Tuple of (chinese, english) descriptions
        """
        # Try to split by common patterns
        patterns = [
            r"中文[：:]\s*(.+?)(?:\n|$)",
            r"Chinese[：:]\s*(.+?)(?:\n|$)",
            r"英文[：:]\s*(.+?)(?:\n|$)",
            r"English[：:]\s*(.+?)(?:\n|$)",
        ]

        zh_match = re.search(r"[\u4e00-\u9fff]{2,}", response)
        en_match = re.search(r"[A-Za-z]{10,}", response)

        zh_desc = zh_match.group(0) if zh_match else ""
        en_desc = en_match.group(0) if en_match else ""

        # Clean up
        zh_desc = re.sub(r"^[^\u4e00-\u9fff]*", "", zh_desc).strip("、。，.")
        en_desc = en_desc.strip(".,;:")

        return zh_desc, en_desc

    async def _refine_chinese_only(self, description: str) -> str:
        """Refine to Chinese only."""
        try:
            chain = self.zh_prompt | self.llm
            result = await chain.ainvoke({"description": description})
            return result.content.strip()[:30]
        except:
            return description[:20]

    async def _refine_english_only(self, description: str) -> str:
        """Refine to English only."""
        try:
            chain = self.en_prompt | self.llm
            result = await chain.ainvoke({"description": description})
            return result.content.strip()[:50]
        except:
            return description[:50]

    def _fallback_description(self, description: str) -> tuple[str, str]:
        """
        Generate fallback description if LLM fails.

        Args:
            description: Original description

        Returns:
            Tuple of (chinese, english) fallbacks
        """
        # Truncate to reasonable length
        zh_fallback = description[:20] if description else "未知技能"
        en_fallback = description[:50] if description else "Unknown skill"

        return zh_fallback, en_fallback


def get_description_refiner() -> DescriptionRefiner:
    """
    Get the global description refiner instance.

    Returns:
        DescriptionRefiner instance
    """
    return DescriptionRefiner()
