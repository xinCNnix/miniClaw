#!/usr/bin/env python3
"""
Download paper PDF from a direct URL.

Downloads PDF and saves to local storage with SHA256-based filename.

Usage:
    python download_pdf.py --pdf-url "https://arxiv.org/pdf/2307.09288.pdf"
    python download_pdf.py --pdf-url "https://arxiv.org/pdf/2307.09288.pdf" --output-dir downloads/papers
"""

import argparse
import hashlib
import io
import json
import os
import sys

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB


# 项目根目录下的 downloads 文件夹
# __file__ = backend/data/skills/conference-paper/scripts/download_pdf.py
DEFAULT_OUTPUT_DIR = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "..", "downloads"
))


def download_pdf(pdf_url: str, output_dir: str = None) -> dict:
    if output_dir is None:
        output_dir = DEFAULT_OUTPUT_DIR
    try:
        import requests
    except ImportError:
        return {"error": "The 'requests' package is required. Install with: pip install requests"}

    os.makedirs(output_dir, exist_ok=True)

    try:
        r = requests.get(pdf_url, timeout=60, stream=True)
        r.raise_for_status()
    except Exception as e:
        return {"error": f"Download failed: {e}"}

    ctype = r.headers.get("Content-Type", "").lower()
    if "pdf" not in ctype and "octet-stream" not in ctype:
        return {"error": f"Not a PDF response (Content-Type: {ctype})"}

    data = r.content
    if len(data) > MAX_PDF_SIZE:
        return {"error": f"PDF too large ({len(data)} bytes, max {MAX_PDF_SIZE} bytes)"}

    h = hashlib.sha256(data).hexdigest()
    path = os.path.join(output_dir, f"{h}.pdf")

    if not os.path.exists(path):
        with open(path, "wb") as f:
            f.write(data)

    return {
        "local_path": os.path.abspath(path),
        "sha256": h,
        "size_bytes": len(data),
    }


def main():
    parser = argparse.ArgumentParser(description="Download paper PDF")

    parser.add_argument("--pdf-url", required=True, help="Direct PDF URL")
    parser.add_argument("--output-dir", "-o", default=None, help="Output directory (default: <project_root>/downloads)")
    parser.add_argument("--format", "-f", choices=["text", "json"], default="text", help="Output format")

    args = parser.parse_args()

    result = download_pdf(pdf_url=args.pdf_url, output_dir=args.output_dir)

    if args.format == "json":
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if "error" in result:
            print(f"Error: {result['error']}")
        else:
            print(f"Downloaded: {result['local_path']}")
            print(f"SHA256: {result['sha256']}")
            print(f"Size: {result['size_bytes']} bytes")


if __name__ == "__main__":
    main()
