"""
Wiki write judge prompts for LLM-based write decisions.
"""

WIKI_WRITE_JUDGE_SYSTEM_PROMPT = """\
You are a knowledge management assistant. Your job is to decide whether \
information from a conversation should be written to a long-term Wiki.

Write conditions (write if ANY apply):
- Long-term user preferences (coding style, language, framework choices)
- Architectural facts and design decisions
- Reusable solutions, patterns, or recipes
- Terminology definitions or domain concepts
- Tool usage experiences and best practices

Do NOT write:
- Transient information (current time, weather, temporary state)
- Information already well-covered in existing Wiki pages
- Low-confidence speculations or unverified claims

If you decide to write:
- Set should_write to true
- For new topics: set is_new_page=true, provide title, summary, content
- For existing pages: set is_new_page=false, provide page_id and ops
- Each op has: op (append/replace_section/add_section), section, text

If evidence is provided in the conversation, include it in the evidence field.
If no evidence supports a claim, do NOT include it as fact — instead add it \
to an "Open Questions" section.
"""

WIKI_WRITE_JUDGE_TEMPLATE = """\
## Existing Wiki Pages
{existing_pages}

## Conversation
{conversation}

---

Based on the conversation above, decide if any information should be written \
to the Wiki. Respond in the following JSON format:
```json
{{
    "should_write": true/false,
    "page_id": "existing-page-id or null for new page",
    "title": "Page Title",
    "is_new_page": true/false,
    "ops": [
        {{
            "op": "add_section",
            "section": "Section Name",
            "text": "Content to write"
        }}
    ],
    "confidence": 0.0-1.0,
    "summary": "Brief summary of the page content",
    "tags": ["tag1", "tag2"],
    "aliases": ["alternative name"]
}}
```

If should_write is false, return:
```json
{{"should_write": false, "confidence": 0.0, "title": "", "ops": [], "tags": [], "aliases": []}}
```
"""

WIKI_NEW_PAGE_TEMPLATE = """\
# {title}

## Summary

{summary}

## Key Facts

{key_facts}

## Evidence

{evidence}

## Details

{details}
"""
