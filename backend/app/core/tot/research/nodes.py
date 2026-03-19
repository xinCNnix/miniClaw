"""
Research-Specific Nodes

LangGraph nodes for deep research workflow.
"""

import logging
from typing import List, Dict, Any
from langchain_core.messages import HumanMessage

from app.core.tot.state import ToTState, Thought

logger = logging.getLogger(__name__)


async def source_identifier_node(state: ToTState) -> ToTState:
    """
    Identify relevant sources for research topic.

    This node analyzes the research query and identifies which sources
    (knowledge base, web, academic papers) are most relevant.

    Args:
        state: Current ToT state

    Returns:
        Updated state with prioritized research sources
    """
    query = state["user_query"]
    llm = state["llm"]

    logger.info(f"Identifying sources for: {query}")

    prompt = f"""Analyze this research topic and identify the best sources: {query}

Available sources:
1. Knowledge Base (search_kb): Domain-specific documents and previous research
2. Academic Papers (arxiv-search): Peer-reviewed academic research
3. Web Content (fetch_url): Current information, tutorials, blogs

For each source type, provide:
- Relevance (0-10): How relevant for this specific query?
- Priority (high/medium/low): What priority should this source have?
- Search Strategy: What terms/approach should we use?

Format as:
**Source Type**: [type]
**Relevance**: [0-10]
**Priority**: [high/medium/low]
**Search Strategy**: [brief description]
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])

        # Parse response into structured sources
        sources = _parse_source_identification(response.content)

        state["research_sources"] = sources

        # Add to reasoning trace
        state["reasoning_trace"].append({
            "type": "sources_identified",
            "count": len(sources),
            "sources": sources
        })

        logger.info(f"Identified {len(sources)} sources")

    except Exception as e:
        logger.error(f"Error identifying sources: {e}")
        # Fallback to default sources
        state["research_sources"] = [
            {
                "type": "knowledge_base",
                "relevance": 8.0,
                "priority": "high",
                "strategy": "Search for domain-specific information"
            },
            {
                "type": "web",
                "relevance": 7.0,
                "priority": "medium",
                "strategy": "Search for current information and tutorials"
            }
        ]

    return state


async def information_extractor_node(state: ToTState) -> ToTState:
    """
    Extract key information from identified sources.

    This node generates thoughts specifically focused on extracting
    information from the sources identified in the previous step.

    Args:
        state: Current ToT state

    Returns:
        Updated state with information extraction thoughts
    """
    query = state["user_query"]
    llm = state["llm"]
    sources = state.get("research_sources", [])

    logger.info(f"Generating information extraction thoughts for {len(sources)} sources")

    # Prioritize sources
    priority_sources = [
        s for s in sources
        if s.get("priority") == "high"
    ]

    if not priority_sources:
        priority_sources = sources[:3]  # Top 3 sources

    # Generate extraction thoughts for each source
    extraction_thoughts = []

    for source in priority_sources:
        source_type = source.get("type", "unknown")
        strategy = source.get("strategy", "general search")

        thought = Thought(
            id=f"extract_{source_type}_{len(extraction_thoughts)}",
            content=f"Extract information from {source_type}: {strategy}",
            tool_calls=_get_tool_calls_for_source(source_type, query),
            status="pending"
        )

        extraction_thoughts.append(thought)

    state["thoughts"].extend(extraction_thoughts)

    state["reasoning_trace"].append({
        "type": "extraction_thoughts_generated",
        "count": len(extraction_thoughts),
        "sources": [s["type"] for s in priority_sources]
    })

    logger.info(f"Generated {len(extraction_thoughts)} extraction thoughts")

    return state


async def cross_reference_node(state: ToTState) -> ToTState:
    """
    Cross-reference information from multiple sources.

    This node identifies:
    1. Common themes across sources
    2. Contradictions between sources
    3. Gaps in information

    Args:
        state: Current ToT state

    Returns:
        Updated state with cross-reference analysis
    """
    query = state["user_query"]
    llm = state["llm"]

    # Collect findings from executed thoughts
    thoughts_with_results = [
        t for t in state["thoughts"]
        if t.tool_results and len(t.tool_results) > 0
    ]

    if len(thoughts_with_results) < 2:
        logger.info("Not enough sources for cross-referencing")
        return state

    # Summarize findings
    findings_summary = _summarize_findings(thoughts_with_results)

    prompt = f"""Cross-reference these research findings for: {query}

Findings from {len(thoughts_with_results)} sources:
{findings_summary}

Identify:
1. **Common Themes**: What do most sources agree on?
2. **Contradictions**: Where do sources disagree?
3. **Information Gaps**: What important information is missing?
4. **Quality Assessment**: Which sources seem most reliable?

Provide structured analysis."""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])

        # Store cross-reference analysis
        state["reasoning_trace"].append({
            "type": "cross_reference_complete",
            "analysis": response.content,
            "sources_compared": len(thoughts_with_results)
        })

        logger.info("Cross-reference analysis complete")

    except Exception as e:
        logger.error(f"Error during cross-referencing: {e}")

    return state


async def synthesis_node(state: ToTState) -> ToTState:
    """
    Synthesize all research into a structured report.

    This is the final research node that produces the comprehensive answer.

    Args:
        state: Current ToT state

    Returns:
        Updated state with final synthesized research report
    """
    query = state["user_query"]
    llm = state["llm"]
    best_path_ids = state["best_path"]
    all_thoughts = state["thoughts"]

    # Collect all findings from best path
    best_thoughts = [t for t in all_thoughts if t.id in best_path_ids]
    all_findings = []

    for thought in best_thoughts:
        if thought.tool_results:
            all_findings.extend(thought.tool_results)

    # Check for cross-reference analysis
    xref_analysis = None
    for trace in state.get("reasoning_trace", []):
        if trace.get("type") == "cross_reference_complete":
            xref_analysis = trace.get("analysis", "")
            break

    # Build synthesis prompt
    prompt = _build_synthesis_prompt(query, all_findings, xref_analysis)

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        state["final_answer"] = response.content

        logger.info("Research synthesis complete")

    except Exception as e:
        logger.error(f"Error during synthesis: {e}")
        state["final_answer"] = _fallback_synthesis(query, all_findings)

    return state


# ============================================================================
# Helper Functions
# ============================================================================

def _parse_source_identification(content: str) -> List[Dict[str, Any]]:
    """Parse LLM response to extract structured sources."""
    sources = []
    lines = content.strip().split('\n')

    current_source = {}

    for line in lines:
        line = line.strip()

        if line.startswith("**Source Type**:"):
            if current_source:
                sources.append(current_source)
            current_source = {"type": line.split(":", 1)[1].strip().lower()}

        elif line.startswith("**Relevance**:"):
            current_source["relevance"] = float(line.split(":", 1)[1].strip())

        elif line.startswith("**Priority**:"):
            current_source["priority"] = line.split(":", 1)[1].strip().lower()

        elif line.startswith("**Search Strategy**:"):
            current_source["strategy"] = line.split(":", 1)[1].strip()

    # Add last source
    if current_source:
        sources.append(current_source)

    return sources


def _get_tool_calls_for_source(source_type: str, query: str) -> List[Dict[str, Any]]:
    """Get appropriate tool calls for a source type."""
    tool_mapping = {
        "knowledge_base": {"name": "search_kb", "args": {"query": query}},
        "academic": {"name": "arxiv-search", "args": {"query": query}},
        "papers": {"name": "arxiv-search", "args": {"query": query}},
        "web": {"name": "fetch_url", "args": {"url": "https://example.com/search"}}  # Placeholder
    }

    # Find matching tool
    for key, tool_call in tool_mapping.items():
        if key in source_type.lower():
            return [tool_call]

    # Default to knowledge base search
    return [{"name": "search_kb", "args": {"query": query}}]


def _summarize_findings(thoughts: List[Thought]) -> str:
    """Summarize findings from thoughts for cross-referencing."""
    summaries = []

    for i, thought in enumerate(thoughts):
        summary = f"Source {i+1}: {thought.content}\n"

        if thought.tool_results:
            successful_results = [
                r for r in thought.tool_results
                if r.get("status") == "success"
            ]

            if successful_results:
                for result in successful_results[:2]:  # Limit to 2 results per source
                    result_str = str(result.get("result", ""))[:200]
                    summary += f"  Result: {result_str}...\n"

        summaries.append(summary)

    return "\n".join(summaries)


def _build_synthesis_prompt(
    query: str,
    findings: List[Dict[str, Any]],
    xref_analysis: str | None
) -> str:
    """Build synthesis prompt."""
    findings_text = _format_findings_for_synthesis(findings)

    xref_section = ""
    if xref_analysis:
        xref_section = f"""

Cross-Reference Analysis:
{xref_analysis}
"""

    return f"""Synthesize the following research into a comprehensive report.

**Research Query:** {query}

**Findings from {len(findings)} sources:**
{findings_text}
{xref_section}
**Required Report Structure:**

## Executive Summary
Provide a 2-3 sentence overview of the key findings.

## Key Findings
Organize findings by themes or topics. Use bullet points.
- Theme 1: [findings]
- Theme 2: [findings]
etc.

## Contradictions & Uncertainties
Note any contradictions between sources or areas of uncertainty.

## Confidence Assessment
Rate overall confidence (High/Medium/Low) with brief explanation.

## Recommendations
Provide recommendations for:
- Further research
- Practical applications
- Additional sources to consult

Be clear, concise, and well-organized. Use markdown formatting."""


def _format_findings_for_synthesis(findings: List[Dict[str, Any]]) -> str:
    """Format findings for synthesis prompt."""
    formatted = []
    successful = 0

    for i, finding in enumerate(findings):
        status = finding.get("status", "unknown")

        if status == "success":
            successful += 1
            result = finding.get("result", "")
            tool = finding.get("tool", "unknown")

            # Truncate long results
            result_str = str(result)[:300]
            if len(str(result)) > 300:
                result_str += "..."

            formatted.append(f"Source {i+1} ({tool}): {result_str}")

    header = f"Successfully gathered information from {successful} out of {len(findings)} sources.\n\n"

    return header + "\n\n".join(formatted)


def _fallback_synthesis(query: str, findings: List[Dict[str, Any]]) -> str:
    """Generate fallback synthesis when LLM fails."""
    successful = sum(1 for f in findings if f.get("status") == "success")

    return f"""# Research Summary: {query}

## Overview
I explored {len(findings)} sources and successfully gathered information from {successful} of them.

## Key Findings

{_format_findings_for_synthesis(findings)}

## Note
This is an automatically generated summary. For a more comprehensive analysis, please try rephrasing your query or specify particular aspects you'd like me to focus on.
"""
