"""
WikiPatcher — Section-level incremental update for Wiki MD pages.

Supports three operations:
- append: Append text to an existing section
- replace_section: Replace content of an existing section
- add_section: Add a new section with the given text
"""

import logging
from typing import List

from app.memory.wiki.models import WikiPatchOp

logger = logging.getLogger(__name__)


class WikiPatcher:
    """Apply patch operations to Markdown Wiki page content."""

    def apply(self, md_content: str, op: WikiPatchOp) -> str:
        """Apply a single patch operation to MD content.

        Args:
            md_content: Current Markdown content
            op: Patch operation to apply

        Returns:
            Updated Markdown content
        """
        if op.op == "append":
            return self._append_to_section(md_content, op.section, op.text)
        elif op.op == "replace_section":
            return self._replace_section(md_content, op.section, op.text)
        elif op.op == "add_section":
            return self._add_section(md_content, op.section, op.text)
        else:
            logger.warning(f"Unknown patch op: {op.op}")
            return md_content

    def apply_batch(self, md_content: str, ops: List[WikiPatchOp]) -> str:
        """Apply multiple patch operations sequentially."""
        for op in ops:
            md_content = self.apply(md_content, op)
        return md_content

    def find_section(self, md: str, section_title: str) -> int | None:
        """Find the line number of a ## section heading.

        Args:
            md: Markdown content
            section_title: Section title to find (without ## prefix)

        Returns:
            Line number (0-indexed) or None if not found
        """
        target = f"## {section_title}"
        for i, line in enumerate(md.split("\n")):
            if line.strip() == target:
                return i
        return None

    def extract_section(self, md: str, section_title: str) -> str | None:
        """Extract the content of a specific ## section.

        Args:
            md: Markdown content
            section_title: Section title to extract

        Returns:
            Section content (without heading) or None if not found
        """
        lines = md.split("\n")
        start = self.find_section(md, section_title)
        if start is None:
            return None

        # Collect lines until next ## heading or end
        content_lines = []
        for line in lines[start + 1:]:
            if line.startswith("## "):
                break
            content_lines.append(line)

        return "\n".join(content_lines).strip()

    def _append_to_section(self, md: str, section: str, text: str) -> str:
        """Append text to the end of an existing section."""
        lines = md.split("\n")
        start = self.find_section(md, section)
        if start is None:
            # Section doesn't exist, add it
            return self._add_section(md, section, text)

        # Find the end of this section (next ## or end of doc)
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break

        # Insert text before the next section
        lines.insert(end, text)
        return "\n".join(lines)

    def _replace_section(self, md: str, section: str, text: str) -> str:
        """Replace the content of an existing section."""
        lines = md.split("\n")
        start = self.find_section(md, section)
        if start is None:
            # Section doesn't exist, add it
            return self._add_section(md, section, text)

        # Find the end of this section
        end = len(lines)
        for i in range(start + 1, len(lines)):
            if lines[i].startswith("## "):
                end = i
                break

        # Replace content between heading and next section
        new_lines = lines[:start + 1] + [text] + lines[end:]
        return "\n".join(new_lines)

    def _add_section(self, md: str, section: str, text: str) -> str:
        """Add a new section at the end of the document."""
        new_section = f"\n## {section}\n\n{text}"
        return md + new_section
