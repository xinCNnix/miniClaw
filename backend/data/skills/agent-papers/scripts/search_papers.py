#!/usr/bin/env python3
"""AI Agent 论文搜索工具 — 基于 Awesome-AI-Agents-Live 数据集。

从本地 papers.json + analyses.json 中搜索、筛选 AI Agent 相关论文，
返回包含摘要、关键洞察、优缺点、评分等结构化信息。

数据来源: https://github.com/Saifs-AIHub/Awesome-AI-Agents-Live
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from urllib.request import urlopen, Request
    from urllib.error import URLError, HTTPError

    _HAS_URLLIB = True
except ImportError:
    _HAS_URLLIB = False

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PAPERS_PATH = DATA_DIR / "papers.json"
ANALYSES_PATH = DATA_DIR / "analyses.json"

VALID_CATEGORIES = [
    "Action Execution",
    "Agent Collaboration",
    "Agent Evolution",
    "Applications",
    "Benchmarks and Datasets",
    "Ethics",
    "Memory Mechanism",
    "Planning Capability",
    "Profile Definition",
    "Security",
    "Social Simulation",
    "Survey",
    "Tools",
]

VALID_DIFFICULTIES = ["Beginner", "Intermediate", "Advanced"]

REMOTE_BASE = (
    "https://raw.githubusercontent.com/SAIFS-AIHub/"
    "Awesome-AI-Agents-Live/main/docs/data"
)
REMOTE_FILES = {
    "papers": f"{REMOTE_BASE}/papers.json",
    "analyses": f"{REMOTE_BASE}/analyses.json",
}


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"Error: data file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _keyword_match(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    text_lower = text.lower()
    return all(kw.lower() in text_lower for kw in keywords)


def search(
    query: list[str] | None = None,
    category: str | None = None,
    labels: list[str] | None = None,
    min_score: int | None = None,
    max_score: int | None = None,
    difficulty: str | None = None,
    author: list[str] | None = None,
    sort_by: str = "score",
    descending: bool = True,
    limit: int = 10,
    offset: int = 0,
) -> dict[str, Any]:
    """搜索 AI Agent 论文。

    Args:
        query: 关键词列表，全部匹配才算命中 (AND 逻辑)
        category: 按分类筛选
        labels: 按标签筛选 (OR 逻辑，命中任一即可)
        min_score: 最低评分 (1-10)
        max_score: 最高评分 (1-10)
        difficulty: 难度等级 (Beginner / Intermediate / Advanced)
        author: 作者关键词列表
        sort_by: 排序字段 (score / date / title)
        descending: 是否降序
        limit: 返回数量上限
        offset: 跳过前 N 条

    Returns:
        包含 total, returned, papers 的字典
    """
    papers_raw = _load_json(PAPERS_PATH)
    analyses_raw = _load_json(ANALYSES_PATH)

    # 构建 analysis 查找表
    analysis_map: dict[str, dict] = {a["paper_id"]: a for a in analyses_raw}

    # 合并数据
    merged: list[dict[str, Any]] = []
    for p in papers_raw:
        pid = p.get("id", "")
        a = analysis_map.get(pid, {})
        merged.append({**p, "_analysis": a})

    results: list[dict[str, Any]] = []

    for item in merged:
        a = item.get("_analysis", {})

        # 分类筛选
        if category and a.get("category", "") != category:
            continue

        # 标签筛选 (OR)
        if labels:
            paper_labels = a.get("labels", [])
            if not any(lb in paper_labels for lb in labels):
                continue

        # 评分筛选
        score = a.get("score")
        if min_score is not None and (score is None or score < min_score):
            continue
        if max_score is not None and (score is None or score > max_score):
            continue

        # 难度筛选
        if difficulty and a.get("difficulty_level", "") != difficulty:
            continue

        # 作者筛选
        if author:
            authors_str = " ".join(item.get("authors", []))
            if not _keyword_match(authors_str, author):
                continue

        # 关键词搜索 (title + summary + key_insights + pros + cons)
        if query:
            searchable = " ".join(
                filter(
                    None,
                    [
                        item.get("title", ""),
                        a.get("summary", ""),
                        " ".join(a.get("key_insights", [])),
                        " ".join(a.get("pros", [])),
                        " ".join(a.get("cons", [])),
                    ],
                )
            )
            if not _keyword_match(searchable, query):
                continue

        # 构建输出条目
        entry = {
            "id": item.get("id", ""),
            "title": item.get("title", ""),
            "authors": item.get("authors", []),
            "url": item.get("url", ""),
            "arxiv_id": item.get("arxiv_id", ""),
            "published_date": item.get("published_date", ""),
            "composite_score": item.get("composite_score"),
            "category": a.get("category", ""),
            "labels": a.get("labels", []),
            "summary": a.get("summary", ""),
            "key_insights": a.get("key_insights", []),
            "pros": a.get("pros", []),
            "cons": a.get("cons", []),
            "score": a.get("score"),
            "difficulty_level": a.get("difficulty_level", ""),
        }
        results.append(entry)

    # 排序
    reverse = descending
    if sort_by == "score":
        results.sort(key=lambda x: x.get("score") or 0, reverse=reverse)
    elif sort_by == "date":
        results.sort(key=lambda x: x.get("published_date") or "", reverse=reverse)
    elif sort_by == "title":
        results.sort(key=lambda x: x.get("title", "").lower(), reverse=reverse)
    elif sort_by == "composite":
        results.sort(key=lambda x: x.get("composite_score") or 0, reverse=reverse)

    total = len(results)
    page = results[offset : offset + limit]

    return {"total_results": total, "returned": len(page), "papers": page}


def list_categories() -> dict[str, int]:
    """列出所有分类及其论文数量。"""
    analyses = _load_json(ANALYSES_PATH)
    counts: dict[str, int] = {}
    for a in analyses:
        cat = a.get("category", "")
        if cat:
            counts[cat] = counts.get(cat, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def list_labels() -> dict[str, int]:
    """列出所有标签及其出现次数。"""
    analyses = _load_json(ANALYSES_PATH)
    counts: dict[str, int] = {}
    for a in analyses:
        for lb in a.get("labels", []):
            if lb:
                counts[lb] = counts.get(lb, 0) + 1
    return dict(sorted(counts.items(), key=lambda x: -x[1]))


def _download_to_temp(url: str, tmp_dir: Path, filename: str) -> Path | None:
    """Download a URL to a temp file. Returns path on success, None on failure."""
    dest = tmp_dir / filename
    try:
        req = Request(url, headers={"User-Agent": "miniClaw-skill/1.0"})
        with urlopen(req, timeout=120) as resp:
            if resp.status != 200:
                print(f"  HTTP {resp.status} for {filename}", file=sys.stderr)
                return None
            with open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
        if dest.stat().st_size < 100:
            print(f"  Downloaded {filename} is too small, skipping", file=sys.stderr)
            return None
        return dest
    except (HTTPError, URLError, OSError) as exc:
        print(f"  Failed to download {filename}: {exc}", file=sys.stderr)
        return None


def _validate_json(path: Path, expect_key: str) -> list | None:
    """Validate JSON file contains a non-empty list with expected structure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        print(f"  Invalid JSON in {path.name}: {exc}", file=sys.stderr)
        return None
    if not isinstance(data, list) or len(data) == 0:
        print(f"  {path.name} is empty or not a list", file=sys.stderr)
        return None
    if expect_key and expect_key not in data[0]:
        print(f"  {path.name} missing expected key '{expect_key}'", file=sys.stderr)
        return None
    return data


def update_data(timeout: int = 120) -> dict[str, Any]:
    """从 GitHub 下载最新数据，失败时不影响本地数据。

    Args:
        timeout: 下载超时秒数

    Returns:
        包含 success, message, papers_count, analyses_count 的字典
    """
    if not _HAS_URLLIB:
        return {
            "success": False,
            "message": "urllib not available, cannot download",
            "papers_count": 0,
            "analyses_count": 0,
        }

    print("Updating agent-papers data from GitHub...")

    # Ensure data dir exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "success": False,
        "message": "",
        "papers_count": 0,
        "analyses_count": 0,
    }

    with tempfile.TemporaryDirectory(prefix="agent-papers-update-") as tmp_dir:
        tmp_path = Path(tmp_dir)

        # Download papers.json
        print("  Downloading papers.json...")
        papers_tmp = _download_to_temp(
            REMOTE_FILES["papers"], tmp_path, "papers.json"
        )
        if papers_tmp is None:
            results["message"] = (
                "Failed to download papers.json. "
                "Local data unchanged."
            )
            print(f"\n  [!] {results['message']}")
            return results

        # Download analyses.json
        print("  Downloading analyses.json...")
        analyses_tmp = _download_to_temp(
            REMOTE_FILES["analyses"], tmp_path, "analyses.json"
        )
        if analyses_tmp is None:
            results["message"] = (
                "Failed to download analyses.json. "
                "Local data unchanged."
            )
            print(f"\n  [!] {results['message']}")
            return results

        # Validate downloaded files
        print("  Validating downloaded data...")
        papers_data = _validate_json(papers_tmp, "id")
        if papers_data is None:
            results["message"] = (
                "papers.json validation failed. "
                "Local data unchanged."
            )
            print(f"\n  [!] {results['message']}")
            return results

        analyses_data = _validate_json(analyses_tmp, "paper_id")
        if analyses_data is None:
            results["message"] = (
                "analyses.json validation failed. "
                "Local data unchanged."
            )
            print(f"\n  [!] {results['message']}")
            return results

        # Backup current files (best effort)
        for target in [PAPERS_PATH, ANALYSES_PATH]:
            if target.exists():
                backup = target.with_suffix(".json.bak")
                try:
                    shutil.copy2(target, backup)
                except OSError:
                    pass  # backup failure is non-critical

        # Atomic-ish replace: write to temp in target dir, then rename
        try:
            tmp_papers = PAPERS_PATH.with_suffix(".json.tmp")
            tmp_analyses = ANALYSES_PATH.with_suffix(".json.tmp")

            shutil.copy2(papers_tmp, tmp_papers)
            shutil.copy2(analyses_tmp, tmp_analyses)

            tmp_papers.replace(PAPERS_PATH)
            tmp_analyses.replace(ANALYSES_PATH)
        except OSError as exc:
            # Clean up temp files if replace failed
            for tmp in [tmp_papers, tmp_analyses]:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
            # Try to restore from backup
            for target, backup in [
                (PAPERS_PATH, PAPERS_PATH.with_suffix(".json.bak")),
                (ANALYSES_PATH, ANALYSES_PATH.with_suffix(".json.bak")),
            ]:
                if backup.exists() and not target.exists():
                    try:
                        shutil.copy2(backup, target)
                    except OSError:
                        pass
            results["message"] = f"File replace failed: {exc}. Data restored."
            print(f"\n  [!] {results['message']}")
            return results

        results["success"] = True
        results["papers_count"] = len(papers_data)
        results["analyses_count"] = len(analyses_data)
        results["message"] = "Update successful."

        # Clean up backups
        for backup in [
            PAPERS_PATH.with_suffix(".json.bak"),
            ANALYSES_PATH.with_suffix(".json.bak"),
        ]:
            try:
                backup.unlink(missing_ok=True)
            except OSError:
                pass

    return results


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI Agent 论文搜索工具 (基于 Awesome-AI-Agents-Live)"
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    # search 子命令
    s = sub.add_parser("search", help="搜索论文")
    s.add_argument("-q", "--query", nargs="+", help="关键词 (AND 逻辑)")
    s.add_argument("-c", "--category", help=f"分类 ({', '.join(VALID_CATEGORIES)})")
    s.add_argument("-l", "--label", nargs="+", help="标签 (OR 逻辑)")
    s.add_argument("--min-score", type=int, help="最低评分 (1-10)")
    s.add_argument("--max-score", type=int, help="最高评分 (1-10)")
    s.add_argument(
        "-d", "--difficulty", choices=VALID_DIFFICULTIES, help="难度等级"
    )
    s.add_argument("-a", "--author", nargs="+", help="作者关键词")
    s.add_argument(
        "-s",
        "--sort-by",
        default="score",
        choices=["score", "date", "title", "composite"],
        help="排序字段 (默认: score)",
    )
    s.add_argument(
        "--asc", action="store_true", default=False, help="升序排列 (默认降序)"
    )
    s.add_argument("-m", "--max-results", type=int, default=10, help="返回数量 (默认 10)")
    s.add_argument("--offset", type=int, default=0, help="跳过前 N 条")
    s.add_argument(
        "--brief", action="store_true", default=False, help="简要输出 (不含 insights/pros/cons)"
    )

    # categories 子命令
    sub.add_parser("categories", help="列出所有分类及数量")

    # labels 子命令
    sub.add_parser("labels", help="列出所有标签及数量")

    # stats 子命令
    sub.add_parser("stats", help="数据集统计信息")

    # update 子命令
    upd = sub.add_parser("update", help="从 GitHub 下载最新论文数据")
    upd.add_argument(
        "--timeout",
        type=int,
        default=120,
        help="下载超时秒数 (默认 120)",
    )

    return parser


def _print_paper(p: dict[str, Any], brief: bool = False) -> None:
    score = p.get("score")
    score_str = f"{score}/10" if score else "N/A"
    diff = p.get("difficulty_level", "")
    cat = p.get("category", "")
    labels = ", ".join(p.get("labels", []))

    print(f"\n{'=' * 70}")
    print(f"  {p['title']}")
    print(f"  ID: {p['id']}  |  Score: {score_str}  |  Difficulty: {diff}")
    if cat:
        print(f"  Category: {cat}")
    if labels:
        print(f"  Labels: {labels}")
    if p.get("published_date"):
        print(f"  Published: {p['published_date']}")
    if p.get("arxiv_id"):
        print(f"  arXiv: {p['arxiv_id']}")
    if p.get("url"):
        print(f"  URL: {p['url']}")

    authors = p.get("authors", [])
    if authors:
        author_str = ", ".join(authors[:5])
        if len(authors) > 5:
            author_str += f" ... (+{len(authors) - 5})"
        print(f"  Authors: {author_str}")

    if p.get("summary"):
        print(f"\n  Summary: {p['summary'][:500]}{'...' if len(p['summary']) > 500 else ''}")

    if not brief:
        insights = p.get("key_insights", [])
        if insights:
            print(f"\n  Key Insights:")
            for i, ins in enumerate(insights[:5], 1):
                print(f"    {i}. {ins[:200]}{'...' if len(ins) > 200 else ''}")

        pros = p.get("pros", [])
        if pros:
            print(f"\n  Pros:")
            for pro in pros[:3]:
                print(f"    + {pro[:150]}{'...' if len(pro) > 150 else ''}")

        cons = p.get("cons", [])
        if cons:
            print(f"\n  Cons:")
            for con in cons[:3]:
                print(f"    - {con[:150]}{'...' if len(con) > 150 else ''}")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    if args.command == "search":
        if not any([args.query, args.category, args.label, args.author,
                     args.min_score, args.max_score, args.difficulty]):
            print("Error: 请至少提供一个搜索条件 (用 -h 查看帮助)", file=sys.stderr)
            sys.exit(1)

        result = search(
            query=args.query,
            category=args.category,
            labels=args.label,
            min_score=args.min_score,
            max_score=args.max_score,
            difficulty=args.difficulty,
            author=args.author,
            sort_by=args.sort_by,
            descending=not args.asc,
            limit=args.max_results,
            offset=args.offset,
        )

        print(f"共找到 {result['total_results']} 篇论文，返回 {result['returned']} 篇:\n")
        for p in result["papers"]:
            _print_paper(p, brief=args.brief)
        print(f"\n{'=' * 70}")
        if result["total_results"] > result["returned"]:
            remaining = result["total_results"] - result["returned"] - args.offset
            if remaining > 0:
                print(f"还有 {remaining} 篇论文，使用 --offset 和 -m 参数翻页")

    elif args.command == "categories":
        cats = list_categories()
        print("AI Agent 论文分类:\n")
        for cat, count in cats.items():
            print(f"  {cat}: {count} 篇")
        print(f"\n  共 {sum(cats.values())} 篇已分类论文")

    elif args.command == "labels":
        labs = list_labels()
        print("AI Agent 论文标签 (前 30):\n")
        for lb, count in list(labs.items())[:30]:
            print(f"  {lb}: {count}")
        print(f"\n  共 {len(labs)} 个标签")

    elif args.command == "stats":
        papers = _load_json(PAPERS_PATH)
        analyses = _load_json(ANALYSES_PATH)
        cats = list_categories()
        print("AI Agent 论文数据集统计:\n")
        print(f"  论文总数: {len(papers)}")
        print(f"  分析总数: {len(analyses)}")
        print(f"  分类数: {len(cats)}")
        labs = list_labels()
        print(f"  标签数: {len(labs)}")
        print(f"\n  分类分布:")
        for cat, count in cats.items():
            print(f"    {cat}: {count}")

    elif args.command == "update":
        result = update_data(timeout=args.timeout)
        if result["success"]:
            print(f"\n  [OK] {result['message']}")
            print(f"  Papers: {result['papers_count']}")
            print(f"  Analyses: {result['analyses_count']}")
        else:
            print(f"\n  [FAIL] {result['message']}", file=sys.stderr)
            print("  Existing local data is intact and usable.", file=sys.stderr)
            sys.exit(0)  # exit 0 so it doesn't break calling workflows


if __name__ == "__main__":
    main()
