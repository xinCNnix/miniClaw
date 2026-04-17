#!/usr/bin/env python3
"""
Conference Paper Search Script

Search and retrieve papers from top AI conferences.
Supports: ICLR, NeurIPS, ICML, IJCAI, CVPR, ICCV, ACL.

Usage:
    python conference_search.py --conference ICLR --year 2024 --keywords "agent" "tool use"
    python conference_search.py --conference NeurIPS --year 2024 --title "attention"
    python conference_search.py --conference ICML --year 2023 --authors "Hinton"
"""

import argparse
import io
import json
import re
import sys
import time
from typing import Dict, List, Optional

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    import requests
except ImportError:
    print("Error: The 'requests' package is required.")
    print("Install it with: pip install requests")
    sys.exit(1)


SUPPORTED_CONFERENCES = {"ICLR", "NeurIPS", "ICML", "IJCAI", "CVPR", "ICCV", "ACL"}

PROVIDER_PRIORITY: Dict[str, List[str]] = {
    "ICLR": ["openreview", "semanticscholar"],
    "NeurIPS": ["semanticscholar"],
    "ICML": ["semanticscholar"],
    "CVPR": ["semanticscholar"],
    "ICCV": ["semanticscholar"],
    "ACL": ["semanticscholar"],
    "IJCAI": ["semanticscholar"],
}

SEMANTIC_SCHOLAR_VENUE_MAP = {
    "NeurIPS": "NeurIPS",
    "ICML": "ICML",
    "IJCAI": "IJCAI",
    "ACL": "ACL",
    "CVPR": "CVPR",
    "ICCV": "ICCV",
    "ICLR": "ICLR",
}


def normalize_title(t: str) -> str:
    t = t.lower().strip()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^a-z0-9 ]", "", t)
    return t


def dedup_papers(papers: List[dict]) -> List[dict]:
    seen = set()
    out = []
    for p in papers:
        key = (normalize_title(p.get("title", "")), p.get("year"))
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def search_openreview(conference: str, year: int, keywords, title, authors, max_results: int) -> List[dict]:
    if conference != "ICLR":
        return []

    # OpenReview v2 API: find the venue invitation first, then search notes
    venue_id = f"ICLR/{year}/Conference"

    # Build search expression
    search_term = title or " ".join(keywords) if keywords else None

    try:
        # Use v2 notes search with invitation-based filtering
        url = "https://api2.openreview.net/notes/search"
        params = {
            "invitation": f"{venue_id}/-/Submission",
            "limit": max_results,
        }
        if search_term:
            params["query"] = search_term

        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 403:
            # Fallback: try the old v1-style endpoint with different params
            url = "https://api2.openreview.net/notes"
            params = {
                "invitation": f"{venue_id}/-/Submission",
                "limit": max_results,
            }
            r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"Warning: OpenReview API error: {e}", file=sys.stderr)
        return []

    notes = data.get("notes", [])
    papers = []
    for note in notes:
        content = note.get("content", {})

        def _extract(field):
            val = content.get(field, {})
            if isinstance(val, dict):
                val = val.get("value", "")
            return val

        title_val = _extract("title")
        abstract_val = _extract("abstract")
        authors_val = _extract("authors")
        venue_val = _extract("venue")

        # Only include accepted papers or all if venue not specified
        # Filter by keywords if provided
        if keywords:
            title_lower = str(title_val).lower()
            abstract_lower = str(abstract_val).lower()
            if not any(kw.lower() in title_lower or kw.lower() in abstract_lower for kw in keywords):
                continue

        # Try to extract arxiv ID from content
        arxiv_id = None
        pdf_val = _extract("pdf")
        if isinstance(pdf_val, str) and "arxiv" in pdf_val.lower():
            parts = pdf_val.split("/")
            for p in parts:
                if "." in p and any(c.isdigit() for c in p):
                    arxiv_id = p.replace(".pdf", "")

        forum_id = note.get("forum", note.get("id", ""))

        papers.append({
            "title": str(title_val),
            "authors": list(authors_val) if isinstance(authors_val, list) else [],
            "conference": conference,
            "year": year,
            "abstract": str(abstract_val) if abstract_val else None,
            "pdf_url": f"https://openreview.net/pdf?id={forum_id}" if forum_id else None,
            "source_url": f"https://openreview.net/forum?id={forum_id}" if forum_id else None,
            "doi": None,
            "arxiv_id": arxiv_id,
        })

    return papers[:max_results]


def _request_with_retry(url: str, params: dict, max_retries: int = 3, timeout: int = 30) -> Optional[dict]:
    for attempt in range(max_retries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 429:
                wait = min(2 ** (attempt + 1), 10)
                print(f"Warning: Rate limited, retrying in {wait}s... (attempt {attempt+1}/{max_retries})", file=sys.stderr)
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** (attempt + 1)
                print(f"Warning: Request failed ({e}), retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"Warning: API error after {max_retries} retries: {e}", file=sys.stderr)
    return None


def search_semanticscholar(conference: str, year: int, keywords, title, authors, max_results: int) -> List[dict]:
    venue = SEMANTIC_SCHOLAR_VENUE_MAP.get(conference, conference)

    query_parts = []
    if title:
        query_parts.append(title)
    elif keywords:
        query_parts.extend(keywords)
    else:
        query_parts.append(f"{conference} {year}")

    query = " ".join(query_parts)
    if authors:
        query += " " + " ".join(authors)

    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": max_results,
        "fields": "title,authors,abstract,year,venue,url,externalIds,openAccessPdf",
        "year": f"{year}-{year}",
    }

    data = _request_with_retry(url, params)
    if data is None:
        return []

    papers = []
    for p in data.get("data", []):
        external = p.get("externalIds") or {}
        oa = p.get("openAccessPdf") or {}
        paper_venue = p.get("venue", "")

        # Filter by venue match if we have the info
        if venue and paper_venue and venue.lower() not in paper_venue.lower():
            continue

        papers.append({
            "title": p.get("title", ""),
            "authors": [a["name"] for a in p.get("authors", []) if "name" in a],
            "conference": conference,
            "year": p.get("year", year),
            "abstract": p.get("abstract"),
            "source_url": p.get("url"),
            "doi": external.get("DOI"),
            "arxiv_id": external.get("ArXiv"),
            "pdf_url": oa.get("url"),
        })

    return papers[:max_results]


PROVIDERS = {
    "openreview": search_openreview,
    "semanticscholar": search_semanticscholar,
}


def search_papers(
    conference: str,
    year: int,
    keywords: Optional[List[str]] = None,
    title: Optional[str] = None,
    authors: Optional[List[str]] = None,
    max_results: int = 10,
) -> dict:
    conference = conference.strip().upper()
    if conference not in SUPPORTED_CONFERENCES:
        return {"error": f"Unsupported conference: {conference}. Supported: {', '.join(sorted(SUPPORTED_CONFERENCES))}"}

    provider_names = PROVIDER_PRIORITY.get(conference, ["semanticscholar"])
    all_papers = []
    used = None

    for provider_name in provider_names:
        provider_fn = PROVIDERS.get(provider_name)
        if not provider_fn:
            continue
        papers = provider_fn(
            conference=conference,
            year=year,
            keywords=keywords,
            title=title,
            authors=authors,
            max_results=max_results,
        )
        if papers:
            used = provider_name
            all_papers.extend(papers)
            break  # Use first provider that returns results

    all_papers = dedup_papers(all_papers)
    all_papers = all_papers[:max_results]

    return {
        "conference": conference,
        "year": year,
        "returned": len(all_papers),
        "provider_used": used or "none",
        "papers": all_papers,
    }


def print_results(results: dict, output_format: str = "text"):
    if "error" in results:
        print(f"Error: {results['error']}")
        return

    if output_format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    papers = results.get("papers", [])
    if not papers:
        print(f"No papers found for {results.get('conference')} {results.get('year')}.")
        return

    print(f"Found {results.get('returned', 0)} papers from {results.get('conference')} {results.get('year')} (via {results.get('provider_used')})")
    print("=" * 80)

    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}] {paper['title']}")
        authors_str = ", ".join(paper["authors"][:5])
        if len(paper["authors"]) > 5:
            authors_str += " et al."
        print(f"    Authors: {authors_str}")
        if paper.get("abstract"):
            print(f"    Abstract: {paper['abstract'][:200]}...")
        if paper.get("arxiv_id"):
            print(f"    arXiv: {paper['arxiv_id']}")
        if paper.get("doi"):
            print(f"    DOI: {paper['doi']}")
        if paper.get("pdf_url"):
            print(f"    PDF: {paper['pdf_url']}")
        if paper.get("source_url"):
            print(f"    Source: {paper['source_url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Search papers from top AI conferences",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--conference", "-c",
        required=True,
        choices=sorted(SUPPORTED_CONFERENCES),
        help="Conference name",
    )
    parser.add_argument(
        "--year", "-y",
        type=int,
        required=True,
        help="Publication year",
    )
    parser.add_argument(
        "--keywords", "-k",
        nargs="+",
        help="Search keywords",
    )
    parser.add_argument(
        "--title", "-t",
        help="Search by paper title",
    )
    parser.add_argument(
        "--authors", "-a",
        nargs="+",
        help="Search by author names",
    )
    parser.add_argument(
        "--max-results", "-m",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    if not any([args.keywords, args.title, args.authors]):
        print("Warning: No search criteria provided (keywords/title/authors). Returning general results.")

    results = search_papers(
        conference=args.conference,
        year=args.year,
        keywords=args.keywords,
        title=args.title,
        authors=args.authors,
        max_results=args.max_results,
    )

    print_results(results, args.format)


if __name__ == "__main__":
    main()
