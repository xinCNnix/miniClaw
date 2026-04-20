#!/usr/bin/env python3
"""
Resolve PDF URL for academic papers.

Given a DOI, arXiv ID, or source URL, resolve a direct PDF download link.

Usage:
    python resolve_pdf.py --arxiv-id "2307.09288"
    python resolve_pdf.py --doi "10.xxxx/..."
    python resolve_pdf.py --source-url "https://openreview.net/..."
"""

import argparse
import io
import json
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")


def resolve_pdf_url(arxiv_id: str = None, doi: str = None, source_url: str = None) -> dict:
    # arXiv ID -> direct PDF
    if arxiv_id:
        return {"pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf", "source": "arxiv"}

    # DOI -> try Semantic Scholar for open access PDF
    if doi:
        try:
            import requests
            url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
            params = {"fields": "openAccessPdf"}
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            data = r.json()
            oa = data.get("openAccessPdf") or {}
            pdf_url = oa.get("url")
            if pdf_url:
                return {"pdf_url": pdf_url, "source": "semanticscholar_doi"}
        except Exception:
            pass
        return {"pdf_url": f"https://doi.org/{doi}", "source": "doi_redirect"}

    # Source URL patterns
    if source_url:
        if "openreview.net" in source_url:
            # Extract paper ID from OpenReview URL
            paper_id = source_url.split("id=")[-1].split("&")[0] if "id=" in source_url else None
            if paper_id:
                return {"pdf_url": f"https://openreview.net/pdf?id={paper_id}", "source": "openreview"}
        if "arxiv.org" in source_url:
            # Extract arXiv ID from URL
            parts = source_url.split("/")
            for part in parts:
                if part.isdigit() and "." in part:
                    return {"pdf_url": f"https://arxiv.org/pdf/{part}.pdf", "source": "arxiv_url"}

    return {"pdf_url": None, "source": None}


def main():
    parser = argparse.ArgumentParser(description="Resolve PDF URL for academic papers")

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--arxiv-id", help="arXiv paper ID (e.g., 2307.09288)")
    group.add_argument("--doi", help="DOI identifier")
    group.add_argument("--source-url", help="Source page URL")

    parser.add_argument("--format", "-f", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()

    result = resolve_pdf_url(
        arxiv_id=args.arxiv_id,
        doi=args.doi,
        source_url=args.source_url,
    )

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if result["pdf_url"]:
            print(f"PDF URL: {result['pdf_url']}")
            print(f"Source: {result['source']}")
        else:
            print("Could not resolve PDF URL.")


if __name__ == "__main__":
    main()
