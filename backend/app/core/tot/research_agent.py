"""
Deep Research Agent

Specialized ToT agent for deep research tasks with multi-source gathering,
cross-referencing, and structured report generation.
"""

import logging
from typing import List, Dict, Any, AsyncIterator, Literal

from langchain_core.messages import HumanMessage, AIMessage

from app.core.tot.state import ToTState, Thought
from app.core.tot.router import ToTOrchestrator
from app.core.agent import AgentManager

logger = logging.getLogger(__name__)


class DeepResearchAgent(ToTOrchestrator):
    """
    Specialized ToT agent for deep research tasks.

    Features:
    1. Multi-source information gathering
    2. Cross-source synthesis
    3. Citation tracking
    4. Structured report generation
    5. Research stage mapping

    Research stages:
    - initial_exploration: Broad overview of topic
    - source_identification: Identify relevant sources
    - information_extraction: Gather detailed information
    - cross_referencing: Compare and contrast sources
    - synthesis: Integrate findings into coherent analysis
    - refinement: Polish and finalize report
    """

    # Research stage configuration
    STAGE_CONFIG = {
        "shallow": {
            "max_depth": 2,
            "stages": ["initial_exploration", "synthesis"]
        },
        "medium": {
            "max_depth": 4,
            "stages": [
                "initial_exploration",
                "source_identification",
                "information_extraction",
                "synthesis"
            ]
        },
        "deep": {
            "max_depth": 6,
            "stages": [
                "initial_exploration",
                "source_identification",
                "information_extraction",
                "cross_referencing",
                "synthesis",
                "refinement"
            ]
        }
    }

    def __init__(self, agent_manager: AgentManager):
        """
        Initialize Deep Research Agent.

        Args:
            agent_manager: Base AgentManager instance
        """
        super().__init__(agent_manager)

    async def conduct_research(
        self,
        topic: str,
        depth: Literal["shallow", "medium", "deep"] = "medium",
        sources: List[str] | None = None
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Conduct deep research using ToT reasoning.

        Args:
            topic: Research topic/question
            depth: Research depth (shallow/medium/deep)
            sources: Specific sources to prioritize (arxiv, web, kb)

        Yields:
            SSE events with research progress
        """
        # Get depth configuration
        config = self.STAGE_CONFIG[depth]
        max_depth = config["max_depth"]
        stages = config["stages"]

        logger.info(f"Starting {depth} research on: {topic}")

        # Build research-focused query
        research_query = self._build_research_query(topic, stages)

        # Use specialized research ToT graph
        messages = [{"role": "user", "content": research_query}]

        system_prompt = self._build_research_system_prompt(sources)

        async for event in self._stream_tot_reasoning(
            topic,
            messages,
            system_prompt,
            max_depth
        ):
            # Add research-specific metadata
            if event.get("type") == "tot_reasoning_step":
                current_depth = event.get("depth", 0)
                if current_depth < len(stages):
                    event["research_stage"] = stages[current_depth]
                    event["research_stage_display"] = self._format_stage_name(
                        stages[current_depth]
                    )

            yield event

        logger.info(f"Completed {depth} research on: {topic}")

    def _build_research_query(self, topic: str, stages: List[str]) -> str:
        """Build research query with stage-by-stage instructions."""
        stage_instructions = "\n".join([
            f"{i+1}. {self._format_stage_name(stage)}"
            for i, stage in enumerate(stages)
        ])

        return f"""Conduct comprehensive research on: {topic}

Research Methodology:
{stage_instructions}

For each stage, identify:
1. What information we need
2. Which tools can provide it (search_kb, fetch_url, arxiv-search, etc.)
3. How to verify and cross-reference information

Expected Output:
- Executive summary of key findings
- Detailed analysis by theme/topic
- Source citations where applicable
- Identified contradictions or uncertainties
- Suggestions for further research"""

    def _build_research_system_prompt(
        self,
        sources: List[str] | None
    ) -> str:
        """Build system prompt for research tasks."""
        source_guidance = ""
        if sources:
            source_list = ", ".join(sources)
            source_guidance = f"""
Prioritize these sources: {source_list}
"""

        return f"""You are a research assistant specializing in comprehensive information gathering and synthesis.

Research Methodology:
1. Source Identification: Identify relevant sources (knowledge base, academic papers, web content)
2. Information Extraction: Extract key information from each source
3. Cross-Referencing: Compare and contrast information across sources
4. Synthesis: Integrate findings into coherent narrative
5. Quality Assessment: Note source quality and reliability

Available Tools:
- search_kb: Search domain knowledge base
- fetch_url: Retrieve web content
- arxiv-search: Search academic papers (if available)
- python_repl: Analyze data if needed
- terminal: Execute commands if needed

{source_guidance}
Output Format:
Provide structured findings with:
1. Executive Summary
2. Key Themes (group findings by topic)
3. Contradictions & Uncertainties
4. Confidence Assessment
5. Recommendations for Further Research

Be thorough but concise. Prioritize accuracy and completeness."""

    def _format_stage_name(self, stage: str) -> str:
        """Format stage name for display."""
        return stage.replace("_", " ").title()


# ============================================================================
# Research-Specific Nodes
# ============================================================================

async def source_identifier_node(state: ToTState) -> ToTState:
    """
    Identify relevant sources for research topic.

    Returns:
        Updated state with prioritized sources
    """
    query = state["user_query"]
    llm = state["llm"]

    prompt = f"""Identify the best sources for research on: {query}

Available sources:
1. Knowledge Base (search_kb): Domain-specific documents, previous research
2. Academic Papers (arxiv-search): Peer-reviewed research (if available)
3. Web Content (fetch_url): Current information, blogs, tutorials

For each source type, indicate:
- Relevance (0-10): How relevant is this source for the query?
- Search Terms: What specific terms should we search for?
- Expected Quality: How reliable do we expect this source to be?

Return structured list in format:
Source Type | Relevance | Search Terms | Expected Quality
"""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])

        # Parse response into sources
        sources = _parse_source_plan(response.content)

        state["research_sources"] = sources
        state["reasoning_trace"].append({
            "type": "sources_identified",
            "sources": sources
        })

        logger.info(f"Identified {len(sources)} research sources")

    except Exception as e:
        logger.error(f"Error identifying sources: {e}")
        # Fallback to default sources
        state["research_sources"] = [
            {"type": "knowledge_base", "relevance": 8.0},
            {"type": "web", "relevance": 7.0}
        ]

    return state


async def synthesis_node(state: ToTState) -> ToTState:
    """
    Synthesize findings from multiple sources into coherent report.

    Features:
    1. Identify common themes
    2. Note contradictions
    3. Assess evidence quality
    4. Generate structured report

    Args:
        state: Current ToT state

    Returns:
        Updated state with final synthesized answer
    """
    llm = state["llm"]
    user_query = state["user_query"]
    best_path_ids = state["best_path"]
    all_thoughts = state["thoughts"]

    # Collect all tool results from best path
    best_thoughts = [t for t in all_thoughts if t.id in best_path_ids]
    all_findings = []

    for thought in best_thoughts:
        if thought.tool_results:
            all_findings.extend(thought.tool_results)

    # Use LLM to synthesize
    prompt = f"""Synthesize the following research findings into a coherent report.

Research Query: {user_query}

Findings from {len(all_findings)} sources:
{_format_findings(all_findings)}

Provide structured report with:
1. **Executive Summary** (2-3 sentences)
2. **Key Findings** (bullet points by theme)
3. **Contradictions & Uncertainties** (if any)
4. **Confidence Assessment** (high/medium/low with explanation)
5. **Recommendations** (for further research or action)

Be clear, concise, and well-organized."""

    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        state["final_answer"] = response.content

        logger.info("Research synthesis complete")

    except Exception as e:
        logger.error(f"Error during synthesis: {e}")
        # Fallback synthesis
        state["final_answer"] = _fallback_synthesis(user_query, all_findings)

    return state


def _parse_source_plan(content: str) -> List[Dict[str, Any]]:
    """Parse LLM response to extract source plan."""
    sources = []

    lines = content.strip().split('\n')
    for line in lines:
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                sources.append({
                    "type": parts[0].lower(),
                    "relevance": float(parts[1]) if parts[1].replace('.', '').isdigit() else 7.0,
                    "terms": parts[2] if len(parts) > 2 else "",
                    "quality": parts[3] if len(parts) > 3 else "medium"
                })

    return sources


def _format_findings(findings: List[Dict[str, Any]]) -> str:
    """Format findings for synthesis prompt."""
    formatted = []
    for i, finding in enumerate(findings):
        status = finding.get("status", "unknown")
        tool = finding.get("tool", "unknown")

        if status == "success":
            result = finding.get("result", "")
            formatted.append(f"Source {i+1} ({tool}): {str(result)[:200]}...")
        else:
            error = finding.get("error", "Unknown error")
            formatted.append(f"Source {i+1} ({tool}): ERROR - {error}")

    return "\n".join(formatted)


def _fallback_synthesis(query: str, findings: List[Dict[str, Any]]) -> str:
    """Generate fallback synthesis when LLM fails."""
    successful = sum(1 for f in findings if f.get("status") == "success")

    return f"""Research Summary for: {query}

I explored {len(findings)} sources and successfully gathered information from {successful} of them.

Key findings from available sources:
{_format_findings(findings)}

Note: Automatic synthesis encountered an error. The above findings are raw results from source queries.
"""
