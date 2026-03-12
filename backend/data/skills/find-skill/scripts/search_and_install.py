#!/usr/bin/env python3
"""
Search and Install Skills Script

Automatically search for skills and install the best match.

Usage:
    python search_and_install.py --query "weather"
    python search_and_install.py --query "pdf processing" --auto-install
"""

import argparse
import subprocess
import sys
import json
from pathlib import Path
from typing import Optional, Dict


def call_script(script_name: str, args: list) -> Dict:
    """Call a sibling script and return parsed JSON output."""
    script_dir = Path(__file__).parent
    script_path = script_dir / script_name

    try:
        result = subprocess.run(
            [sys.executable, str(script_path)] + args,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        if result.returncode != 0:
            return {"error": f"Script failed: {result.stderr}"}

        # Try to parse JSON output
        try:
            # Look for JSON in output (in case there's other text)
            output = result.stdout.strip()
            if output.startswith("{"):
                return json.loads(output)
            else:
                # Try to find JSON in the output
                start = output.find("{")
                end = output.rfind("}") + 1
                if start >= 0 and end > start:
                    return json.loads(output[start:end])
                return {"error": "No JSON output found", "raw_output": output}
        except json.JSONDecodeError:
            return {"error": "Invalid JSON output", "raw_output": result.stdout}

    except subprocess.TimeoutExpired:
        return {"error": "Script timed out"}
    except Exception as e:
        return {"error": f"Failed to run script: {str(e)}"}


def search_and_install(
    query: str,
    source: str = "github",
    max_results: int = 5,
    auto_install: bool = False,
    min_stars: int = 0,
    target_dir: str = "./data/skills",
) -> Dict:
    """
    Search for skills and optionally install the best match.

    Args:
        query: Search query
        source: Source to search (github, clawhub)
        max_results: Maximum search results
        auto_install: If True, automatically install the best match
        min_stars: Minimum star count to consider
        target_dir: Target installation directory

    Returns:
        Dictionary with search results and installation status
    """
    # Step 1: Search
    search_args = [
        "--source", source,
        "--query", query,
        "--max-results", str(max_results),
        "--sort", "stars",
        "--format", "json",
    ]

    search_result = call_script("search_skills.py", search_args)

    if "error" in search_result:
        return {
            "error": f"Search failed: {search_result['error']}",
            "query": query,
        }

    results = search_result.get("results", [])

    if not results:
        return {
            "query": query,
            "source": source,
            "total_count": 0,
            "returned": 0,
            "results": [],
            "installed": None,
            "message": "No skills found",
        }

    # Filter by minimum stars
    filtered_results = [
        r for r in results
        if r.get("stars", 0) >= min_stars
    ]

    if not filtered_results:
        return {
            "query": query,
            "source": source,
            "total_count": search_result.get("total_count", 0),
            "returned": len(results),
            "results": results,
            "installed": None,
            "message": f"No skills meet minimum star requirement ({min_stars})",
        }

    # Step 2: Select best match (highest stars)
    best_match = filtered_results[0]

    result = {
        "query": query,
        "source": source,
        "total_count": search_result.get("total_count", 0),
        "returned": len(results),
        "results": results,
        "best_match": best_match,
        "installed": None,
    }

    # Step 3: Install if auto_install is True
    if auto_install:
        print(f"\nInstalling best match: {best_match['full_name']}")

        install_args = [
            "--url", best_match["clone_url"],
            "--target", target_dir,
        ]

        install_result = call_script("install_skill.py", install_args)

        if "error" in install_result:
            result["install_error"] = install_result["error"]
            result["message"] = f"Found skills but installation failed: {install_result['error']}"
        else:
            result["installed"] = {
                "name": install_result.get("name"),
                "path": install_result.get("path"),
            }
            result["message"] = f"Successfully installed skill '{install_result.get('name')}'"

    else:
        result["message"] = f"Found {len(filtered_results)} skills (auto-install disabled)"

    return result


def print_result(result: Dict):
    """Print search and install result."""
    if "error" in result:
        print(f"Error: {result['error']}")
        return

    query = result.get("query", "")
    total = result.get("total_count", 0)
    returned = result.get("returned", 0)
    source = result.get("source", "unknown")

    print(f"\nSearch results for '{query}' from {source}:")
    print(f"Total: {total} repositories (showing {returned})")
    print("=" * 80)

    results = result.get("results", [])
    best_match = result.get("best_match")

    for i, r in enumerate(results, 1):
        is_best = " [BEST MATCH]" if r == best_match else ""
        print(f"\n[{i}] {r['full_name']}{is_best}")
        print(f"    Description: {r.get('description', 'N/A')}")
        print(f"    Stars: {r.get('stars', 0)} | Forks: {r.get('forks', 0)}")
        print(f"    URL: {r['url']}")
        print(f"    Clone: {r['clone_url']}")

    installed = result.get("installed")
    if installed:
        print(f"\n✓ Installed: {installed['name']}")
        print(f"  Location: {installed['path']}")
    elif result.get("install_error"):
        print(f"\n✗ Installation failed: {result['install_error']}")

    print(f"\n{result.get('message', '')}")


def main():
    parser = argparse.ArgumentParser(
        description="Search for skills and optionally install the best match",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Search only (no installation)
  python search_and_install.py --query "weather"

  # Search and auto-install best match
  python search_and_install.py --query "pdf" --auto-install

  # Search with minimum star requirement
  python search_and_install.py --query "agent" --min-stars 10 --auto-install

  # Search clawhub
  python search_and_install.py --source clawhub --query "document" --auto-install
        """,
    )

    parser.add_argument(
        "--query", "-q",
        required=True,
        help="Search query"
    )
    parser.add_argument(
        "--source", "-s",
        choices=["github", "clawhub"],
        default="github",
        help="Source to search (default: github)"
    )
    parser.add_argument(
        "--max-results", "-m",
        type=int,
        default=5,
        help="Maximum search results (default: 5)"
    )
    parser.add_argument(
        "--auto-install",
        action="store_true",
        help="Automatically install the best matching skill"
    )
    parser.add_argument(
        "--min-stars",
        type=int,
        default=0,
        help="Minimum star count (default: 0)"
    )
    parser.add_argument(
        "--target",
        default="./data/skills",
        help="Target installation directory (default: ./data/skills)"
    )
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)"
    )

    args = parser.parse_args()

    # Perform search and install
    result = search_and_install(
        query=args.query,
        source=args.source,
        max_results=args.max_results,
        auto_install=args.auto_install,
        min_stars=args.min_stars,
        target_dir=args.target,
    )

    # Output
    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_result(result)


if __name__ == "__main__":
    main()
