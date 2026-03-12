#!/usr/bin/env python3
"""
arXiv Paper Search Script

Search and retrieve academic papers from arXiv.org.

Usage:
    python arxiv_search.py --query "neural networks" --max-results 10
    python arxiv_search.py --author "Geoffrey Hinton"
    python arxiv_search.py --id "2307.09288"
"""

import argparse
import io
import json
import sys
from datetime import datetime
from typing import Optional, List

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    import arxiv
except ImportError:
    print("Error: The 'arxiv' package is required.")
    print("Install it with: pip install arxiv")
    sys.exit(1)


def format_authors(authors: List) -> str:
    """Format author list for display."""
    return ", ".join([author.name for author in authors])


def search_arxiv(
    query: Optional[str] = None,
    author: Optional[str] = None,
    paper_id: Optional[str] = None,
    max_results: int = 10,
    sort_by: str = "relevance",
    order: str = "descending",
    category: Optional[str] = None,
) -> dict:
    """
    Search arXiv and return results.

    Args:
        query: Search query string
        author: Author name to search for
        paper_id: Specific arXiv paper ID
        max_results: Maximum number of results to return
        sort_by: Sort criterion (relevance, lastUpdatedDate, submittedDate)
        order: Sort order (ascending, descending)
        category: Filter by arXiv category

    Returns:
        Dictionary with search results
    """
    # Build search query
    search_query = ""

    if paper_id:
        # Search by ID - use id_query prefix
        search_query = f"id:{paper_id}"
    elif author:
        # Search by author
        search_query = f"au:{author}"
    elif query:
        # Use the query as-is, but add category filter if specified
        if category:
            search_query = f"cat:{category} AND {query}"
        else:
            search_query = query
    else:
        return {"error": "Must provide one of: --query, --author, --id"}

    # Map sort options
    sort_map = {
        "relevance": arxiv.SortCriterion.Relevance,
        "lastUpdatedDate": arxiv.SortCriterion.LastUpdatedDate,
        "submittedDate": arxiv.SortCriterion.SubmittedDate,
    }

    sort_criterion = sort_map.get(sort_by, arxiv.SortCriterion.Relevance)

    # Map order
    order_map = {
        "ascending": arxiv.SortOrder.Ascending,
        "descending": arxiv.SortOrder.Descending,
    }

    sort_order = order_map.get(order, arxiv.SortOrder.Descending)

    # Create search
    search = arxiv.Search(
        query=search_query,
        max_results=max_results,
        sort_by=sort_criterion,
        sort_order=sort_order,
    )

    # Fetch results using the new API
    papers = []
    try:
        client = arxiv.Client()
        for result in client.results(search):
            paper = {
                "title": result.title,
                "authors": [author.name for author in result.authors],
                "summary": result.summary.replace("\n", " ").strip(),
                "published": result.published.strftime("%Y-%m-%d") if result.published else None,
                "updated": result.updated.strftime("%Y-%m-%d") if result.updated else None,
                "categories": result.categories,
                "arxiv_id": result.entry_id.split("/")[-1],
                "pdf_url": result.pdf_url,
                "abs_url": result.entry_id,
            }
            papers.append(paper)
    except Exception as e:
        return {"error": f"Failed to fetch results: {str(e)}"}

    return {
        "query": search_query,
        "total_results": len(papers),  # Note: actual total may be higher
        "returned": len(papers),
        "papers": papers,
    }


def print_results(results: dict, output_format: str = "text"):
    """Print search results in specified format."""
    if "error" in results:
        print(f"Error: {results['error']}")
        return

    if output_format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    # Text format
    papers = results.get("papers", [])

    if not papers:
        print("No papers found.")
        return

    print(f"Found {results.get('returned', 0)} papers")
    print("=" * 80)

    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}] {paper['title']}")
        print(f"    Authors: {', '.join(paper['authors'][:5])}" +
              (f" et al." if len(paper['authors']) > 5 else ""))
        print(f"    Published: {paper['published']} | Updated: {paper['updated']}")
        print(f"    Categories: {', '.join(paper['categories'])}")
        print(f"    arXiv ID: {paper['arxiv_id']}")
        print(f"    Abstract: {paper['summary'][:200]}...")
        print(f"    Links:")
        print(f"        Abstract: {paper['abs_url']}")
        print(f"        PDF: {paper['pdf_url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Search and retrieve academic papers from arXiv.org",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search by query
  python arxiv_search.py --query "neural networks" --max-results 10

  # Search by author
  python arxiv_search.py --author "Geoffrey Hinton" --max-results 20

  # Get paper by ID
  python arxiv_search.py --id "2307.09288"

  # Advanced query with category
  python arxiv_search.py --query "transformers AND attention" --category cs.AI

  # Sort by date
  python arxiv_search.py --query "diffusion models" --sort-by submittedDate --order descending
        """,
    )

    # Search options (mutually exclusive)
    search_group = parser.add_mutually_exclusive_group(required=True)
    search_group.add_argument(
        "--query", "-q",
        help="Search query (supports boolean operators: AND, OR, NOT)"
    )
    search_group.add_argument(
        "--author", "-a",
        help="Search by author name"
    )
    search_group.add_argument(
        "--id", "-i",
        help="Get specific paper by arXiv ID (e.g., 2307.09288 or cs.AI/1234567)"
    )

    # Output options
    parser.add_argument(
        "--max-results", "-m",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)"
    )
    parser.add_argument(
        "--sort-by", "-s",
        choices=["relevance", "lastUpdatedDate", "submittedDate"],
        default="relevance",
        help="Sort criterion (default: relevance)"
    )
    parser.add_argument(
        "--order", "-o",
        choices=["ascending", "descending"],
        default="descending",
        help="Sort order (default: descending)"
    )
    parser.add_argument(
        "--category", "-c",
        help="Filter by arXiv category (e.g., cs.AI, cs.LG, cs.CV)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    args = parser.parse_args()

    # Perform search
    results = search_arxiv(
        query=args.query,
        author=args.author,
        paper_id=args.id,
        max_results=args.max_results,
        sort_by=args.sort_by,
        order=args.order,
        category=args.category,
    )

    # Print results
    print_results(results, args.format)


if __name__ == "__main__":
    main()
