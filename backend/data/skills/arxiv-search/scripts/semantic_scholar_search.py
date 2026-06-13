#!/usr/bin/env python3
"""
Semantic Scholar Paper Search Script

Search academic papers via Semantic Scholar API.
No API key required (1.5s/request). With key: 0.3s/request.

Usage:
    python semantic_scholar_search.py --query "neural networks" --max-results 10
    python semantic_scholar_search.py --id "abc123" --format json
    python semantic_scholar_search.py --author "Geoffrey Hinton" --year-min 2020
"""

import argparse
import io
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 速率限制
_LAST_REQUEST_TIME = 0.0
_RATE_NO_KEY = 1.5
_RATE_WITH_KEY = 0.3
_MAX_RETRIES = 3

# 可选 API key (环境变量 S2_API_KEY)
_API_KEY = os.environ.get("S2_API_KEY", "")


def _get_rate_limit() -> float:
    return _RATE_WITH_KEY if _API_KEY else _RATE_NO_KEY


def _rate_limit():
    """确保请求间隔"""
    global _LAST_REQUEST_TIME
    elapsed = time.monotonic() - _LAST_REQUEST_TIME
    delay = _get_rate_limit()
    if elapsed < delay:
        time.sleep(delay - elapsed + random.uniform(0, 0.1))
    _LAST_REQUEST_TIME = time.monotonic()


def _request(url: str, timeout: int = 15) -> dict | list | None:
    """发送 HTTP GET 并返回 JSON"""
    for attempt in range(_MAX_RETRIES):
        _rate_limit()
        try:
            headers = {"Accept": "application/json"}
            if _API_KEY:
                headers["x-api-key"] = _API_KEY
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                # 速率限制: 指数退避
                wait = min(2 ** (attempt + 1), 60) + random.uniform(0, 2)
                print(f"  [S2] rate limited, retrying in {wait:.1f}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code == 404:
                return None
            print(f"  [S2] HTTP {e.code}: {e.reason}", file=sys.stderr)
            return None
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                wait = min(2 ** (attempt + 1), 30)
                print(f"  [S2] error: {e}, retrying in {wait:.1f}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  [S2] failed after {_MAX_RETRIES} attempts: {e}", file=sys.stderr)
            return None
    return None


def _parse_paper(item: dict) -> dict:
    """解析 Semantic Scholar 论文为统一格式"""
    # 外部 ID
    ext_ids = item.get("externalIds") or {}
    doi = ext_ids.get("DOI", "") or ""
    arxiv_id = ext_ids.get("ArXiv", "") or ""

    # 作者
    raw_authors = item.get("authors") or []
    authors = []
    for a in raw_authors[:20]:
        name = a.get("name", "")
        if name:
            authors.append(name)

    # 发表年份和日期
    year = item.get("year")
    pub_date = item.get("publicationDate") or ""

    # 期刊/会议
    venue = item.get("venue") or ""
    journal = item.get("journal") or {}
    if journal and not venue:
        venue = journal.get("name", "")

    # 引用数
    cited_by = item.get("citationCount", 0) or 0

    # 摘要 (S2 可能不返回 abstract, 取决于 fields 参数)
    abstract = item.get("abstract") or ""

    return {
        "title": item.get("title", "") or "",
        "authors": authors,
        "summary": abstract,
        "published": pub_date,
        "year": year,
        "venue": venue,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "cited_by_count": cited_by,
        "paper_id": item.get("paperId", ""),
        "url": f"https://www.semanticscholar.org/paper/{item.get('paperId', '')}",
    }


def search_semantic_scholar(
    query: Optional[str] = None,
    author: Optional[str] = None,
    paper_id: Optional[str] = None,
    max_results: int = 10,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    fields: str = "paperId,title,authors,year,publicationDate,venue,journal,citationCount,externalIds,abstract",
) -> dict:
    """搜索 Semantic Scholar"""
    if paper_id:
        # 按论文 ID 查找 (S2 支持 ARXIV:xxx, DOI:xxx, CorpusID:xxx 等前缀)
        # 冒号不编码, S2 API 需要
        encoded_id = urllib.parse.quote(paper_id, safe=':')
        url = f"https://api.semanticscholar.org/graph/v1/paper/{encoded_id}?fields={fields}"
        data = _request(url)
        if not data:
            return {"error": f"Paper not found: {paper_id}"}
        return {
            "source": "semantic_scholar",
            "total_results": 1,
            "returned": 1,
            "papers": [_parse_paper(data)],
        }

    if not query and not author:
        return {"error": "Must provide one of: --query, --author, --id"}

    # 构建搜索查询
    search_query = query or ""
    if author:
        if search_query:
            search_query += " "
        search_query += author

    params = {
        "query": search_query,
        "limit": min(max_results, 100),
        "fields": fields,
    }
    if year_min or year_max:
        y_min = year_min or 1900
        y_max = year_max or 2099
        params["year"] = f"{y_min}-{y_max}"

    url = f"https://api.semanticscholar.org/graph/v1/paper/search?{urllib.parse.urlencode(params)}"
    data = _request(url)

    if not data:
        return {"error": "Failed to fetch results from Semantic Scholar"}

    raw_papers = data.get("data") or []
    papers = [_parse_paper(p) for p in raw_papers]
    total = data.get("total") or len(papers)

    return {
        "source": "semantic_scholar",
        "total_results": total,
        "returned": len(papers),
        "papers": papers,
    }


def batch_fetch(
    paper_ids: list[str],
    fields: str = "paperId,title,authors,year,publicationDate,venue,journal,citationCount,externalIds",
) -> dict:
    """批量获取论文信息 (POST /paper/batch)"""
    url = f"https://api.semanticscholar.org/graph/v1/paper/batch?fields={fields}"
    body = json.dumps({"ids": paper_ids}).encode("utf-8")

    for attempt in range(_MAX_RETRIES):
        _rate_limit()
        try:
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if _API_KEY:
                headers["x-api-key"] = _API_KEY
            req = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                results = json.loads(resp.read().decode("utf-8"))
                papers = [_parse_paper(p) for p in results if p]
                return {
                    "source": "semantic_scholar",
                    "total_results": len(papers),
                    "returned": len(papers),
                    "papers": papers,
                }
        except Exception as e:
            if attempt < _MAX_RETRIES - 1:
                time.sleep(min(2 ** (attempt + 1), 30))
                continue
            return {"error": f"Batch fetch failed: {e}"}


def print_results(results: dict, output_format: str = "text"):
    """输出结果"""
    if "error" in results:
        print(f"Error: {results['error']}")
        return

    if output_format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    papers = results.get("papers", [])
    if not papers:
        print("No papers found.")
        return

    total = results.get("total_results", 0)
    print(f"Found {total} papers (showing {len(papers)})")
    print("=" * 80)

    for i, p in enumerate(papers, 1):
        print(f"\n[{i}] {p['title']}")
        author_str = ", ".join(p["authors"][:5])
        print(f"    Authors: {author_str}" +
              (" et al." if len(p["authors"]) > 5 else ""))
        print(f"    Published: {p['published']} | Venue: {p['venue']}")
        print(f"    Cited by: {p['cited_by_count']}")
        if p["doi"]:
            print(f"    DOI: {p['doi']}")
        if p["arxiv_id"]:
            print(f"    arXiv: {p['arxiv_id']}")
        if p["summary"]:
            print(f"    Abstract: {p['summary'][:200]}...")
        print(f"    S2 URL: {p['url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Search academic papers via Semantic Scholar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python semantic_scholar_search.py --query "neural networks" --max-results 10
  python semantic_scholar_search.py --author "Geoffrey Hinton" --year-min 2020
  python semantic_scholar_search.py --id "649def34f8be52c8b66281af98ae884c09aef38b"
  python semantic_scholar_search.py --query "transformer attention" --sort-by cited --format json

Note: Set S2_API_KEY environment variable for faster rate limits (0.3s vs 1.5s).
        """,
    )

    search_group = parser.add_mutually_exclusive_group(required=True)
    search_group.add_argument("--query", "-q", help="Search query")
    search_group.add_argument("--author", "-a", help="Search by author name")
    search_group.add_argument("--id", "-i", help="Semantic Scholar paper ID or DOI:DOI:xxx or ARXIV:xxx")
    search_group.add_argument("--batch", "-b", nargs="+", help="Batch fetch multiple paper IDs")

    parser.add_argument("--max-results", "-m", type=int, default=10, help="Max results (default: 10, max: 100)")
    parser.add_argument("--year-min", type=int, help="Minimum publication year")
    parser.add_argument("--year-max", type=int, help="Maximum publication year")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text", help="Output format")

    # 兼容 LLM 生成的 --max_results / --sort_by / --year_min 等下划线格式
    sys.argv = [a.replace("_", "-", 1) if a.startswith("--") and "_" in a else a for a in sys.argv]
    args = parser.parse_args()

    if args.batch:
        results = batch_fetch(args.batch)
    else:
        results = search_semantic_scholar(
            query=args.query,
            author=args.author,
            paper_id=args.id,
            max_results=args.max_results,
            year_min=args.year_min,
            year_max=args.year_max,
        )
    print_results(results, args.format)


if __name__ == "__main__":
    main()
