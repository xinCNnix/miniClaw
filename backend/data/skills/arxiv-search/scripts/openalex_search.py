#!/usr/bin/env python3
"""
OpenAlex Academic Paper Search Script

Search academic papers via OpenAlex API (10K/day polite pool, no API key required).

Usage:
    python openalex_search.py --query "neural networks" --max-results 10
    python openalex_search.py --doi "10.1234/..." --format json
    python openalex_search.py --author "Geoffrey Hinton" --year-min 2020
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from typing import Optional

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# 速率限制: 200ms
_LAST_REQUEST_TIME = 0.0
_RATE_LIMIT_SEC = 0.2
_POLITE_EMAIL = "miniclaw@users.noreply.github.com"


def _rate_limit():
    """确保请求间隔 >= 200ms"""
    global _LAST_REQUEST_TIME
    elapsed = time.monotonic() - _LAST_REQUEST_TIME
    if elapsed < _RATE_LIMIT_SEC:
        time.sleep(_RATE_LIMIT_SEC - elapsed)
    _LAST_REQUEST_TIME = time.monotonic()


def _request(url: str, timeout: int = 15) -> dict | None:
    """发送 HTTP GET 并返回 JSON 解析结果"""
    _rate_limit()
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": f"mailto:{_POLITE_EMAIL}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  [OpenAlex] request error: {e}", file=sys.stderr)
        return None


def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """从 OpenAlex 倒排索引重建摘要文本"""
    if not inverted_index:
        return ""
    word_positions = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def _parse_work(item: dict) -> dict:
    """解析单个 OpenAlex work 为统一格式"""
    # 提取 DOI
    doi = item.get("doi", "") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    # 提取 arXiv ID
    arxiv_id = ""
    ids = item.get("ids") or {}
    if ids.get("arxiv"):
        arxiv_id = ids["arxiv"]
        if arxiv_id.startswith("https://arxiv.org/"):
            arxiv_id = re.search(r"\d{4}\.\d+", arxiv_id)
            arxiv_id = arxiv_id.group(0) if arxiv_id else ""

    # 提取作者
    authorships = item.get("authorships") or []
    authors = []
    for a in authorships[:20]:
        author_obj = a.get("author") or {}
        name = author_obj.get("display_name", "")
        if name:
            institutions = a.get("institutions") or []
            inst = institutions[0].get("display_name", "") if institutions else ""
            authors.append({"name": name, "affiliation": inst})

    # 提取发表年份
    pub_date = item.get("publication_date") or ""

    # 提取期刊/会议名
    primary_location = item.get("primary_location") or {}
    source = primary_location.get("source") or {}
    venue = source.get("display_name", "") or ""

    # 过滤掉 arXiv 分类代码作为 venue
    if re.match(r"^[a-z]{2,}\.[A-Z]{2}$", venue):
        venue = ""

    # 引用数
    cited_by = item.get("cited_by_count", 0) or 0

    # 摘要
    abstract = _reconstruct_abstract(item.get("abstract_inverted_index"))

    return {
        "title": item.get("title", "") or "",
        "authors": authors,
        "summary": abstract,
        "published": pub_date,
        "year": item.get("publication_year"),
        "venue": venue,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "cited_by_count": cited_by,
        "url": item.get("id", ""),  # OpenAlex URL
    }


def search_openalex(
    query: Optional[str] = None,
    author: Optional[str] = None,
    doi: Optional[str] = None,
    max_results: int = 10,
    year_min: Optional[int] = None,
    year_max: Optional[int] = None,
    sort_by: str = "relevance",
    email: str = _POLITE_EMAIL,
) -> dict:
    """搜索 OpenAlex"""
    base = "https://api.openalex.org/works"

    if doi:
        # 按 DOI 查找
        url = f"{base}/doi:{urllib.parse.quote(doi, safe='')}"
        data = _request(url)
        if not data:
            return {"error": f"Failed to fetch DOI: {doi}"}
        return {
            "source": "openalex",
            "total_results": 1,
            "returned": 1,
            "papers": [_parse_work(data)],
        }

    # 构建查询
    filters = []
    if query:
        filters.append(f"default.search:{urllib.parse.quote(query, safe='')}")
    if author:
        filters.append(f"author.display_name.search:{urllib.parse.quote(author, safe='')}")
    if year_min:
        filters.append(f"from_publication_date:{year_min}-01-01")
    if year_max:
        filters.append(f"to_publication_date:{year_max}-12-31")

    if not filters:
        return {"error": "Must provide one of: --query, --author, --doi"}

    filter_str = ",".join(filters)

    # 排序
    sort_map = {
        "relevance": "relevance_score:desc",
        "cited": "cited_by_count:desc",
        "date": "publication_date:desc",
    }
    sort_str = sort_map.get(sort_by, "relevance_score:desc")

    params = f"filter={filter_str}&sort={sort_str}&per_page={min(max_results, 50)}&mailto={email}"
    url = f"{base}?{params}"

    data = _request(url)
    if not data:
        return {"error": "Failed to fetch results from OpenAlex"}

    results = data.get("results") or []
    papers = [_parse_work(w) for w in results]

    return {
        "source": "openalex",
        "total_results": data.get("meta", {}).get("count", len(papers)),
        "returned": len(papers),
        "papers": papers,
    }


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
        author_names = [a["name"] for a in p["authors"][:5]]
        print(f"    Authors: {', '.join(author_names)}" +
              (" et al." if len(p["authors"]) > 5 else ""))
        print(f"    Published: {p['published']} | Venue: {p['venue']}")
        print(f"    Cited by: {p['cited_by_count']}")
        if p["doi"]:
            print(f"    DOI: {p['doi']}")
        if p["arxiv_id"]:
            print(f"    arXiv: {p['arxiv_id']}")
        if p["summary"]:
            print(f"    Abstract: {p['summary'][:200]}...")
        print(f"    URL: {p['url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Search academic papers via OpenAlex (no API key required)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python openalex_search.py --query "neural networks" --max-results 10
  python openalex_search.py --author "Geoffrey Hinton" --year-min 2020
  python openalex_search.py --doi "10.1038/s41586-020-2649-2"
  python openalex_search.py --query "transformer" --sort-by cited --format json
        """,
    )

    search_group = parser.add_mutually_exclusive_group(required=True)
    search_group.add_argument("--query", "-q", help="Search query")
    search_group.add_argument("--author", "-a", help="Search by author name")
    search_group.add_argument("--doi", "-d", help="Look up paper by DOI")

    parser.add_argument("--max-results", "-m", type=int, default=10, help="Max results (default: 10, max: 50)")
    parser.add_argument("--year-min", type=int, help="Minimum publication year")
    parser.add_argument("--year-max", type=int, help="Maximum publication year")
    parser.add_argument("--sort-by", choices=["relevance", "cited", "date"], default="relevance",
                        help="Sort order (default: relevance)")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text", help="Output format")

    # 兼容 LLM 生成的 --max_results / --sort_by / --year_min 等下划线格式
    sys.argv = [a.replace("_", "-", 1) if a.startswith("--") and "_" in a else a for a in sys.argv]
    args = parser.parse_args()

    results = search_openalex(
        query=args.query,
        author=args.author,
        doi=args.doi,
        max_results=args.max_results,
        year_min=args.year_min,
        year_max=args.year_max,
        sort_by=args.sort_by,
    )
    print_results(results, args.format)


if __name__ == "__main__":
    main()
