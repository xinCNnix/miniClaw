#!/usr/bin/env python3
"""
arXiv Paper Download Script

Download academic papers from arXiv.org in PDF format.

Usage:
    python download_paper.py --id "2307.09288" --output-dir downloads
    python download_paper.py --title "Attention Is All You Need" --output-dir downloads
    python download_paper.py --query "transformers" --max-results 5 --output-dir downloads
"""

import argparse
import io
import json
import os
import re
import sys
import urllib.request
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import quote

# Set UTF-8 encoding for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

try:
    import arxiv

# Script: backend/data/skills/arxiv-download-paper/scripts/download_paper.py
# backend/ root is 5 levels up: scripts/ → arxiv-download-paper/ → skills/ → data/ → backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_PROJECT_ROOT = _BACKEND_ROOT.parent  # project root (miniclaw/)
except ImportError:
    print("Error: The 'arxiv' package is required.")
    print("Install it with: pip install arxiv")
    sys.exit(1)


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing invalid characters.
    
    Args:
        filename: Original filename
        
    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove invalid characters for Windows/Linux/Mac
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    
    # Remove control characters
    filename = ''.join(char for char in filename if ord(char) >= 32)
    
    # Trim whitespace and dots
    filename = filename.strip('. ')
    
    # Limit length (255 is common filesystem limit)
    if len(filename) > 200:
        filename = filename[:200]
    
    return filename


def search_papers(
    query: Optional[str] = None,
    author: Optional[str] = None,
    paper_id: Optional[str] = None,
    max_results: int = 10,
    sort_by: str = "relevance",
    order: str = "descending",
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Search arXiv and return paper metadata.
    
    Args:
        query: Search query string
        author: Author name to search for
        paper_id: Specific arXiv paper ID
        max_results: Maximum number of results to return
        sort_by: Sort criterion (relevance, lastUpdatedDate, submittedDate)
        order: Sort order (ascending, descending)
        category: Filter by arXiv category
        
    Returns:
        List of paper dictionaries
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
        return []
    
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
        print(f"Error fetching results: {str(e)}")
        return []
    
    return papers


def download_pdf(pdf_url: str, output_path: Path) -> bool:
    """
    Download PDF from URL to local path.
    
    Args:
        pdf_url: URL to PDF file
        output_path: Local path to save PDF
        
    Returns:
        True if successful, False otherwise
    """
    try:
        # Create directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download with progress
        print(f"Downloading: {pdf_url}")
        print(f"Saving to: {output_path}")
        
        # Use urllib for better compatibility
        with urllib.request.urlopen(pdf_url) as response:
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 8192
            
            with open(output_path, 'wb') as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    
                    # Show progress
                    if total_size > 0:
                        percent = (downloaded / total_size) * 100
                        print(f"\rProgress: {percent:.1f}% ({downloaded}/{total_size} bytes)", end="")
            
            print(f"\nDownload complete: {output_path}")
            return True
            
    except Exception as e:
        print(f"Error downloading PDF: {str(e)}")
        # Clean up partial download
        if output_path.exists():
            output_path.unlink()
        return False


def download_papers(
    papers: List[Dict[str, Any]],
    output_dir: Path,
    add_to_kb: bool = False,
) -> List[Dict[str, Any]]:
    """
    Download multiple papers.
    
    Args:
        papers: List of paper dictionaries
        output_dir: Directory to save PDFs
        add_to_kb: Whether to add to knowledge base
        
    Returns:
        List of download results
    """
    results = []
    
    for i, paper in enumerate(papers, 1):
        print(f"\n[{i}/{len(papers)}] Processing: {paper['title']}")
        
        # Generate filename from title
        filename = sanitize_filename(paper['title']) + ".pdf"
        output_path = output_dir / filename
        
        # Check if file already exists
        if output_path.exists():
            print(f"File already exists: {output_path}")
            results.append({
                "paper": paper,
                "success": True,
                "path": str(output_path),
                "message": "File already exists"
            })
            continue
        
        # Download PDF
        success = download_pdf(paper['pdf_url'], output_path)
        
        if success:
            # Optionally add to knowledge base
            if add_to_kb:
                try:
                    # Copy to knowledge base directory
                    kb_dir = Path("knowledge_base/papers")
                    kb_dir.mkdir(parents=True, exist_ok=True)
                    kb_path = kb_dir / filename
                    
                    # Copy file
                    import shutil
                    shutil.copy2(output_path, kb_path)
                    print(f"Added to knowledge base: {kb_path}")
                except Exception as e:
                    print(f"Warning: Failed to add to knowledge base: {str(e)}")
            
            results.append({
                "paper": paper,
                "success": True,
                "path": str(output_path),
                "message": "Downloaded successfully"
            })
        else:
            results.append({
                "paper": paper,
                "success": False,
                "path": str(output_path),
                "message": "Download failed"
            })
    
    return results


def main():
    parser = argparse.ArgumentParser(
        description="Download academic papers from arXiv.org in PDF format",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download by arXiv ID
  python download_paper.py --id "2307.09288" --output-dir downloads

  # Download by title search
  python download_paper.py --title "Attention Is All You Need" --output-dir downloads

  # Download multiple papers by query
  python download_paper.py --query "transformers" --max-results 5 --output-dir downloads

  # Download and add to knowledge base
  python download_paper.py --id "2307.09288" --output-dir downloads --add-to-kb

  # Download by author
  python download_paper.py --author "Geoffrey Hinton" --max-results 3 --output-dir downloads
        """,
    )
    
    # Search options (mutually exclusive)
    search_group = parser.add_mutually_exclusive_group(required=True)
    search_group.add_argument(
        "--id", "-i",
        help="Download specific paper by arXiv ID (e.g., 2307.09288)"
    )
    search_group.add_argument(
        "--title", "-t",
        help="Search by paper title"
    )
    search_group.add_argument(
        "--query", "-q",
        help="Search query (supports boolean operators)"
    )
    search_group.add_argument(
        "--author", "-a",
        help="Search by author name"
    )
    
    # Output options
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=str(_PROJECT_ROOT / "downloads"),
        help="Output directory for downloaded PDFs (default: project_root/downloads/)"
    )
    parser.add_argument(
        "--max-results", "-m",
        type=int,
        default=10,
        help="Maximum number of results to download (default: 10)"
    )
    parser.add_argument(
        "--sort-by", "-s",
        choices=["relevance", "lastUpdatedDate", "submittedDate"],
        default="relevance",
        help="Sort criterion (default: relevance)"
    )
    parser.add_argument(
        "--order",
        choices=["ascending", "descending"],
        default="descending",
        help="Sort order (default: descending)"
    )
    parser.add_argument(
        "--category", "-c",
        help="Filter by arXiv category (e.g., cs.AI, cs.LG)"
    )
    parser.add_argument(
        "--add-to-kb",
        action="store_true",
        help="Add downloaded papers to knowledge base"
    )
    
    args = parser.parse_args()
    
    # Convert output directory to Path
    output_dir = Path(args.output_dir)
    
    # Search for papers
    print("Searching arXiv...")
    
    if args.title:
        # Search by title
        papers = search_papers(
            query=f'ti:"{args.title}"',
            max_results=args.max_results,
            sort_by=args.sort_by,
            order=args.order,
            category=args.category,
        )
    else:
        # Search by other criteria
        papers = search_papers(
            query=args.query,
            author=args.author,
            paper_id=args.id,
            max_results=args.max_results,
            sort_by=args.sort_by,
            order=args.order,
            category=args.category,
        )
    
    if not papers:
        print("No papers found.")
        return
    
    print(f"Found {len(papers)} paper(s)")
    
    # Download papers
    results = download_papers(papers, output_dir, args.add_to_kb)
    
    # Print summary
    print("\n" + "=" * 80)
    print("DOWNLOAD SUMMARY")
    print("=" * 80)
    
    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful
    
    print(f"Total papers: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    if failed > 0:
        print("\nFailed downloads:")
        for r in results:
            if not r["success"]:
                print(f"  - {r['paper']['title']}: {r['message']}")
    
    print(f"\nPDFs saved to: {output_dir.absolute()}")


if __name__ == "__main__":
    main()