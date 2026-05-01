"""
Citation Fetch Node

Fetches primary sources identified by the citation chasing planner.
Executes search queries using available tools, filters results for
high-quality domains (arxiv, pdf, github, official docs), and
appends the fetched content to raw_sources for subsequent extraction.

Uses the concurrent tool execution pattern from thought_executor.py
for parallel fetching with error handling.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List

from langchain_core.tools import BaseTool

from app.core.tot.state import ToTState
from app.core.tot.research.evidence_utils import content_hash

logger = logging.getLogger(__name__)

# Domains that indicate high-quality primary sources.
_PRIORITY_DOMAINS = [
    "arxiv.org",
    "github.com",
    "aclanthology.org",
    "openreview.net",
    "papers.nips.cc",
    "proceedings.mlr.press",
    "nature.com",
    "science.org",
    "dl.acm.org",
    "ieeexplore.ieee.org",
]

# Maximum concurrent fetch operations.
_MAX_CONCURRENT_FETCH = 3


async def citation_fetch_node(state: ToTState) -> Dict:
    """Fetch primary sources identified by the citation planner.

    Reads citation targets from state (set by
    citation_chasing_planner_node), executes search queries using
    available tools, filters results for high-quality domains, and
    appends fetched content to raw_sources.

    Individual target failures are handled gracefully: if one target
    fails, others continue. The node increments citation_chase_rounds
    on completion.

    Args:
        state: Current ToT state with citation_targets, tools, and
            citation chase budget information.

    Returns:
        Dict with updated raw_sources and citation_chase_rounds.
    """
    task_mode = state.get("task_mode", "standard")

    if task_mode != "research":
        logger.debug("citation_fetch_node: non-research mode, skipping")
        return {}

    targets: List[Dict] = state.get("citation_targets") or []

    if not targets:
        logger.debug("citation_fetch_node: no citation targets, skipping")
        chase_rounds = int(state.get("citation_chase_rounds", 0)) + 1
        return {
            "citation_chase_rounds": chase_rounds,
            "research_sub_rounds": state.get("research_sub_rounds", 0) + 1,
        }

    tools: List[BaseTool] = state.get("tools") or []
    existing_sources: List[Dict] = state.get("raw_sources") or []

    logger.info(
        f"citation_fetch_node: fetching {len(targets)} citation targets"
    )

    # Build tool map
    tool_map = {tool.name: tool for tool in tools}

    sem = asyncio.Semaphore(_MAX_CONCURRENT_FETCH)
    fetched_sources: List[Dict] = []
    fetch_errors: int = 0

    async def fetch_one(target: Dict) -> List[Dict]:
        """Fetch sources for a single citation target.

        Args:
            target: Citation target dict with "query" and "source_type".

        Returns:
            List of raw source dicts fetched for this target.
        """
        query = target.get("query", "")
        source_type = target.get("source_type", "auto")

        if not query:
            return []

        async with sem:
            return await _execute_search_for_target(
                query=query,
                source_type=source_type,
                tool_map=tool_map,
                target=target,
            )

    start = time.monotonic()

    # Execute all fetches concurrently
    results = await asyncio.gather(
        *[fetch_one(t) for t in targets],
        return_exceptions=True,
    )

    for result in results:
        if isinstance(result, Exception):
            logger.warning(f"citation_fetch_node: fetch task failed: {result}")
            fetch_errors += 1
            continue
        if isinstance(result, list):
            fetched_sources.extend(result)

    elapsed_ms = (time.monotonic() - start) * 1000

    # Combine with existing raw_sources
    combined_sources = existing_sources + fetched_sources

    # Increment citation chase rounds
    chase_rounds = int(state.get("citation_chase_rounds", 0)) + 1
    chase_max = int(state.get("citation_chase_max", 2))

    logger.info(
        f"citation_fetch_node: fetched {len(fetched_sources)} sources "
        f"from {len(targets)} targets in {elapsed_ms:.0f}ms "
        f"({fetch_errors} errors), "
        f"round {chase_rounds}/{chase_max}"
    )

    # Log via ToTExecutionLogger
    _log_citation_fetch(state, len(targets), len(fetched_sources), chase_rounds, chase_max)

    return {
        "raw_sources": combined_sources,
        "citation_chase_rounds": chase_rounds,
        "citation_targets": [],  # Clear targets after fetching
        "research_sub_rounds": state.get("research_sub_rounds", 0) + 1,
    }


# ---------------------------------------------------------------------------
# Search execution
# ---------------------------------------------------------------------------


async def _execute_search_for_target(
    query: str,
    source_type: str,
    tool_map: Dict[str, BaseTool],
    target: Dict,
) -> List[Dict]:
    """Execute search queries for a single citation target.

    Tries available search tools in priority order: arxiv-search,
    then web_search / search, then search_kb. Filters results for
    priority domains when source_type indicates preference for
    academic or official sources.

    Args:
        query: Search query string.
        source_type: Expected source type (arxiv, github, docs, auto).
        tool_map: Mapping of tool names to BaseTool instances.
        target: Original target dict for metadata.

    Returns:
        List of raw source dicts with source_type="citation_chase".
    """
    sources: List[Dict] = []

    # Determine which tools to try based on source_type
    tool_candidates = _get_tool_candidates(source_type, tool_map)

    for tool_name in tool_candidates:
        # arxiv-search 是虚拟工具名，实际使用 terminal 工具执行
        actual_tool_name = "terminal" if tool_name == "arxiv-search" else tool_name
        tool = tool_map.get(actual_tool_name)
        if not tool:
            continue

        try:
            # Build tool arguments based on tool type
            tool_args = _build_tool_args(tool_name, query, source_type)

            result = await tool.ainvoke(tool_args)

            # Parse tool result into source dicts
            parsed = _parse_tool_result(result, query, tool_name)
            sources.extend(parsed)

            if sources:
                # Got results from this tool, stop trying alternatives
                break

        except AttributeError:
            # Tool doesn't support async, try sync
            try:
                tool_args = _build_tool_args(tool_name, query, source_type)
                result = tool.invoke(tool_args)
                parsed = _parse_tool_result(result, query, tool_name)
                sources.extend(parsed)
                if sources:
                    break
            except Exception as exc:
                logger.warning(
                    f"citation_fetch_node: {tool_name} sync failed for "
                    f"'{query[:50]}': {exc}"
                )
        except Exception as exc:
            logger.warning(
                f"citation_fetch_node: {tool_name} failed for "
                f"'{query[:50]}': {exc}"
            )

    # Filter for priority domains if source_type is specific
    if source_type != "auto" and sources:
        filtered = _filter_by_domain(sources, source_type)
        # If filtering removed everything, keep the unfiltered results
        if filtered:
            sources = filtered

    return sources


def _get_tool_candidates(
    source_type: str,
    tool_map: Dict[str, BaseTool],
) -> List[str]:
    """Get ordered list of tool names to try for a given source type.

    Args:
        source_type: Expected source type (arxiv, github, docs, auto).
        tool_map: Available tools.

    Returns:
        Ordered list of tool names to attempt.
    """
    # Define tool priority per source type
    # "arxiv-search" 是虚拟工具名，映射到 terminal 执行脚本
    type_to_tools: Dict[str, List[str]] = {
        "arxiv": ["arxiv-search", "search_kb", "fetch_url"],
        "github": ["fetch_url", "search_kb"],
        "docs": ["fetch_url", "search_kb"],
        "paper": ["arxiv-search", "search_kb", "fetch_url"],
        "benchmark": ["fetch_url", "search_kb"],
        "auto": ["search_kb", "arxiv-search", "fetch_url"],
    }

    candidates = type_to_tools.get(source_type, type_to_tools["auto"])

    # Filter: arxiv-search 需要 terminal 工具可用，其他需要直接在 tool_map 中
    result = []
    for t in candidates:
        if t == "arxiv-search":
            # arxiv-search 通过 terminal 工具执行脚本
            if "terminal" in tool_map:
                result.append(t)
        elif t in tool_map:
            result.append(t)
    return result


def _build_tool_args(tool_name: str, query: str, source_type: str) -> Dict:
    """Build tool invocation arguments for a search tool.

    Args:
        tool_name: Name of the tool to invoke.
        query: Search query string.
        source_type: Expected source type.

    Returns:
        Dict of tool arguments.
    """
    if tool_name == "arxiv-search":
        escaped_query = query.replace('"', '\\"')
        return {
            "command": (
                f'python data/skills/arxiv-search/scripts/arxiv_search.py'
                f' --query "{escaped_query}"'
                f' --max-results 15'
                f' --sort-by submittedDate'
                f' --order descending'
            )
        }
    elif tool_name in ("web_search", "search"):
        return {"query": query}
    elif tool_name == "search_kb":
        return {"query": query}
    else:
        return {"query": query}


def _parse_tool_result(
    result: Any,
    query: str,
    tool_name: str,
) -> List[Dict]:
    """Parse a tool result into a list of raw source dicts.

    Handles various result formats: strings, dicts with content,
    and lists of items.

    Args:
        result: Raw tool execution result.
        query: The original search query.
        tool_name: Name of the tool that produced the result.

    Returns:
        List of raw source dicts with source_type="citation_chase".
    """
    sources: List[Dict] = []

    if isinstance(result, str):
        if result.strip():
            sources.append({
                "source_id": f"cite_{tool_name}_{content_hash(result)[:8]}",
                "source_text": result,
                "source_type": "citation_chase",
                "title": f"Citation chase: {query[:80]}",
                "url": "",
                "query": query,
                "tool": tool_name,
            })

    elif isinstance(result, dict):
        content = result.get("content") or result.get("output") or ""
        if isinstance(content, str) and content.strip():
            sources.append({
                "source_id": f"cite_{tool_name}_{content_hash(content)[:8]}",
                "source_text": content,
                "source_type": "citation_chase",
                "title": result.get("title", f"Citation chase: {query[:80]}"),
                "url": result.get("url", ""),
                "query": query,
                "tool": tool_name,
            })
        elif isinstance(content, list):
            for item in content:
                text = ""
                if isinstance(item, str):
                    text = item
                elif isinstance(item, dict):
                    text = item.get("content") or item.get("text") or str(item)

                if text.strip():
                    sources.append({
                        "source_id": f"cite_{tool_name}_{content_hash(text)[:8]}",
                        "source_text": text,
                        "source_type": "citation_chase",
                        "title": (
                            item.get("title", f"Citation chase: {query[:80]}")
                            if isinstance(item, dict)
                            else f"Citation chase: {query[:80]}"
                        ),
                        "url": (
                            item.get("url", "")
                            if isinstance(item, dict)
                            else ""
                        ),
                        "query": query,
                        "tool": tool_name,
                    })

    elif isinstance(result, list):
        for item in result:
            text = ""
            title = f"Citation chase: {query[:80]}"
            url = ""

            if isinstance(item, str):
                text = item
            elif isinstance(item, dict):
                text = item.get("content") or item.get("text") or str(item)
                title = item.get("title", title)
                url = item.get("url", "")

            if text.strip():
                sources.append({
                    "source_id": f"cite_{tool_name}_{content_hash(text)[:8]}",
                    "source_text": text,
                    "source_type": "citation_chase",
                    "title": title,
                    "url": url,
                    "query": query,
                    "tool": tool_name,
                })

    return sources


def _filter_by_domain(sources: List[Dict], source_type: str) -> List[Dict]:
    """Filter sources by priority domains matching the expected source_type.

    Args:
        sources: List of raw source dicts.
        source_type: Expected source type to filter for.

    Returns:
        Filtered list of sources, or empty list if none match.
    """
    domain_map = {
        "arxiv": ["arxiv.org", "aclanthology.org"],
        "paper": ["arxiv.org", "aclanthology.org", "openreview.net",
                   "papers.nips.cc", "proceedings.mlr.press"],
        "github": ["github.com"],
        "docs": [],  # No specific domain filter for docs
    }

    priority_domains = domain_map.get(source_type, [])
    if not priority_domains:
        return sources

    filtered = []
    for src in sources:
        url = src.get("url", "").lower()
        text = src.get("source_text", "").lower()
        for domain in priority_domains:
            if domain in url or domain in text:
                filtered.append(src)
                break

    return filtered


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_citation_fetch(
    state: ToTState,
    targets_count: int,
    fetched_count: int,
    chase_rounds: int,
    chase_max: int,
) -> None:
    """Log citation fetch results via ToTExecutionLogger if available.

    Args:
        state: Current ToT state.
        targets_count: Number of targets attempted.
        fetched_count: Number of sources actually fetched.
        chase_rounds: Updated chase rounds count.
        chase_max: Maximum chase rounds.
    """
    try:
        tot_logger = state.get("tot_logger")
        if tot_logger is not None:
            tot_logger.log_citation_chasing(
                depth=state.get("current_depth", 0),
                targets_count=targets_count,
                fetched_count=fetched_count,
                budget_remaining=chase_max - chase_rounds,
            )
    except Exception:
        pass  # Logging is non-critical
