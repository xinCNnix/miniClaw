#!/usr/bin/env python3
"""
Skills Search Script

Search for agent skills from GitHub, clawhub, and other repositories.

Usage:
    python search_skills.py --source github --query "weather"
    python search_skills.py --source clawhub --query "pdf processing"
"""

import argparse
import json
import sys
from typing import Optional, List
import urllib.request
import urllib.parse
import urllib.error

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def search_github(
    query: str,
    max_results: int = 10,
    sort: str = "stars",
    language: Optional[str] = None,
) -> dict:
    """
    Search GitHub for skill repositories.

    Args:
        query: Search query (supports GitHub search syntax)
        max_results: Maximum number of results
        sort: Sort by (stars, forks, updated)
        language: Filter by programming language

    Returns:
        Dictionary with search results
    """
    # Build GitHub API query
    search_terms = [query]

    # Add language filter if specified
    if language:
        search_terms.append(f"language:{language}")

    # Combine search terms
    github_query = " ".join(search_terms)

    # Build API URL
    base_url = "https://api.github.com/search/repositories"
    params = {
        "q": github_query,
        "sort": sort,
        "order": "desc",
        "per_page": min(max_results, 100),  # GitHub max is 100 per page
    }

    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        # Make request (GitHub API works without auth for public searches)
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.v3+json")
        req.add_header("User-Agent", "miniClaw-Skill-Search")

        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())

        results = []
        for repo in data.get("items", []):
            result = {
                "name": repo["name"],
                "full_name": repo["full_name"],
                "description": repo.get("description", ""),
                "url": repo["html_url"],
                "clone_url": repo["clone_url"],
                "stars": repo["stargazers_count"],
                "forks": repo["forks_count"],
                "updated": repo["updated_at"][:10],  # YYYY-MM-DD
                "language": repo.get("language", ""),
            }
            results.append(result)

        return {
            "source": "github",
            "query": query,
            "total_count": data.get("total_count", 0),
            "returned": len(results),
            "results": results,
        }

    except urllib.error.HTTPError as e:
        return {"error": f"HTTP error {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"Network error: {e.reason}"}
    except Exception as e:
        return {"error": f"Failed to search GitHub: {str(e)}"}


def search_clawhub(
    query: str,
    max_results: int = 10,
) -> dict:
    """
    Search clawhub for skills.

    Note: This is a placeholder implementation.
    Adjust the URL and parsing logic based on actual clawhub API.

    Args:
        query: Search query
        max_results: Maximum number of results

    Returns:
        Dictionary with search results
    """
    # Placeholder: clawhub URL (adjust to actual API)
    # This could be:
    # - A JSON file at a known URL
    # - A GitHub API search with specific topics
    # - A dedicated API endpoint

    # For now, search GitHub with clawhub-specific topic
    github_query = f"{query} topic:clawhub-skill"

    # Reuse GitHub search with clawhub topic
    result = search_github(github_query, max_results=max_results)
    result["source"] = "clawhub"
    return result


def print_results(results: dict, output_format: str = "text"):
    """Print search results in specified format."""
    if "error" in results:
        print(f"Error: {results['error']}")
        return

    if output_format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    # Text format
    items = results.get("results", [])

    if not items:
        print("No results found.")
        return

    source = results.get("source", "unknown")
    total = results.get("total_count", len(items))
    returned = results.get("returned", len(items))

    print(f"Found {total} repositories from {source} (showing {returned}):")
    print("=" * 80)

    for i, item in enumerate(items, 1):
        print(f"\n[{i}] {item['full_name']}")
        if item.get("description"):
            print(f"    Description: {item['description']}")
        print(f"    Stars: {item.get('stars', 0)} | "
              f"Forks: {item.get('forks', 0)} | "
              f"Updated: {item.get('updated', 'N/A')}")
        if item.get("language"):
            print(f"    Language: {item['language']}")
        print(f"    URL: {item['url']}")
        print(f"    Clone: {item['clone_url']}")


def main():
    parser = argparse.ArgumentParser(
        description="Search for agent skills from external sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search GitHub for weather skills
  python search_skills.py --source github --query "weather"

  # Search with specific topic
  python search_skills.py --source github --query "topic:agent-skill pdf"

  # Search by quality (stars)
  python search_skills.py --source github --query "agent-skill" --sort stars

  # Search clawhub
  python search_skills.py --source clawhub --query "document processing"

  # Filter by language
  python search_skills.py --source github --query "weather" --language python
        """,
    )

    parser.add_argument(
        "--source", "-s",
        choices=["github", "clawhub"],
        default="github",
        help="Source to search (default: github)"
    )
    parser.add_argument(
        "--query", "-q",
        required=True,
        help="Search query"
    )
    parser.add_argument(
        "--max-results", "-m",
        type=int,
        default=10,
        help="Maximum number of results (default: 10)"
    )
    parser.add_argument(
        "--sort", "-o",
        choices=["stars", "forks", "updated"],
        default="stars",
        help="Sort order (default: stars)"
    )
    parser.add_argument(
        "--language", "-l",
        help="Filter by programming language"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    args = parser.parse_args()

    # Perform search based on source
    if args.source == "github":
        results = search_github(
            query=args.query,
            max_results=args.max_results,
            sort=args.sort,
            language=args.language,
        )
    elif args.source == "clawhub":
        results = search_clawhub(
            query=args.query,
            max_results=args.max_results,
        )
    else:
        results = {"error": f"Unknown source: {args.source}"}

    # Print results
    print_results(results, args.format)


if __name__ == "__main__":
    main()
