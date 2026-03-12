"""
Fetch URL Tool - Web Content Retrieval with HTML Cleaning

This tool fetches content from URLs and cleans HTML to reduce token usage.
Features:
- HTML to Markdown/Text conversion
- Timeout control
- Error handling
- Request header customization
"""

import re
from typing import Optional
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import html2text
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field, HttpUrl
from app.config import settings


class FetchURLInput(BaseModel):
    """Input schema for Fetch URL tool."""

    url: str = Field(
        ...,
        description="The URL to fetch content from",
    )

    timeout: int = Field(
        default=10,
        description="Request timeout in seconds",
    )

    output_format: str = Field(
        default="markdown",
        description="Output format: 'markdown' or 'text'",
    )

    user_agent: str = Field(
        default="Mozilla/5.0 (compatible; miniClaw/1.0)",
        description="User-Agent header for requests",
    )


class FetchURLTool(BaseTool):
    """
    Fetch URL tool for retrieving web content.

    This tool fetches URLs and returns cleaned content to reduce
    token usage compared to raw HTML.
    """

    name: str = "fetch_url"
    description: str = """
    Fetch and extract content from a URL.

    Features:
    - Automatic HTML cleaning (Markdown or plain text)
    - JSON API support (returns raw JSON data)
    - Removes scripts, styles, and navigation elements
    - Preserves main content structure
    - Reduces token usage significantly

    Common uses:
    - Get article content from web pages
    - Fetch JSON data from APIs
    - Retrieve documentation
    - Access weather APIs and other data sources

    Examples:
    - fetch_url: https://example.com
    - fetch_url: https://wttr.in/Beijing?format=j1 (JSON weather data)
    - fetch_url: https://api.github.com/repos/owner/repo (GitHub API)

    Note:
    - HTML pages are cleaned and converted to Markdown
    - JSON responses are returned as-is for parsing
    - Use output_format='text' for plain text instead of Markdown
    """
    args_schema: type[FetchURLInput] = FetchURLInput

    def _validate_url(self, url: str) -> None:
        """
        Validate URL format and safety.

        Args:
            url: URL to validate

        Raises:
            ValueError: If URL is invalid or unsafe
        """
        try:
            parsed = urlparse(url)

            # Check scheme
            if parsed.scheme not in ["http", "https"]:
                raise ValueError(
                    f"Unsupported URL scheme: {parsed.scheme}. "
                    "Only http and https are allowed."
                )

            # Check for localhost/private IPs (optional security measure)
            if parsed.hostname in ["localhost", "127.0.0.1", "0.0.0.0"]:
                raise ValueError(
                    "Access to localhost is not allowed for security reasons."
                )

        except Exception as e:
            raise ValueError(f"Invalid URL: {str(e)}")

    def _clean_html(
        self,
        html: str,
        url: str,
        output_format: str = "markdown",
    ) -> str:
        """
        Clean HTML content.

        Args:
            html: Raw HTML content
            url: Original URL (for resolving relative links)
            output_format: 'markdown' or 'text'

        Returns:
            Cleaned content
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for script in soup(["script", "style", "nav", "footer", "header", "aside"]):
            script.decompose()

        # Try to find main content
        main_content = (
            soup.find("main") or
            soup.find("article") or
            soup.find("div", {"class": re.compile(r"content|main|article", re.I)}) or
            soup.body
        )

        if main_content is None:
            return "No content found on page"

        # Convert to requested format
        if output_format == "markdown":
            # Use html2text for Markdown conversion
            h = html2text.HTML2Text()
            h.ignore_links = False
            h.ignore_images = False
            h.ignore_emphasis = False
            h.body_width = 0  # Don't wrap lines
            content = h.handle(str(main_content))
        else:
            # Plain text
            content = main_content.get_text(separator="\n", strip=True)

        # Clean up whitespace
        lines = content.split("\n")
        lines = [line.strip() for line in lines if line.strip()]
        cleaned = "\n".join(lines)

        return cleaned

    def _fetch_content(
        self,
        url: str,
        timeout: int,
        user_agent: str,
    ) -> tuple[str, bool]:
        """
        Fetch content from URL.

        Args:
            url: URL to fetch
            timeout: Request timeout
            user_agent: User-Agent header

        Returns:
            Tuple of (content, success)
        """
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
            )

            response.raise_for_status()

            # Check content type
            content_type = response.headers.get("content-type", "")

            # Support HTML, JSON, and plain text
            if not any(ct in content_type for ct in ["text/html", "application/json", "text/plain", "application/json", "text/json"]):
                return (
                    f"Unsupported content type: {content_type}. "
                    "Supported types: HTML, JSON, plain text.",
                    False
                )

            # For JSON, return the raw text (Agent can parse it)
            # For HTML, return the text (will be cleaned later)
            return response.text, True

        except requests.Timeout:
            return f"Request timed out after {timeout} seconds", False
        except requests.HTTPError as e:
            return f"HTTP error: {e.response.status_code} {e.response.reason}", False
        except requests.RequestException as e:
            return f"Request failed: {str(e)}", False
        except Exception as e:
            return f"Unexpected error: {str(e)}", False

    def _run(
        self,
        url: str,
        timeout: int = 10,
        output_format: str = "markdown",
        user_agent: str = "Mozilla/5.0 (compatible; miniClaw/1.0)",
    ) -> str:
        """
        Fetch and clean URL content.

        Args:
            url: URL to fetch
            timeout: Request timeout
            output_format: Output format ('markdown' or 'text')
            user_agent: User-Agent header

        Returns:
            Cleaned content or error message
        """
        # Validate URL
        self._validate_url(url)

        # Fetch content
        content, success = self._fetch_content(url, timeout, user_agent)

        if not success:
            return content

        # Determine content type
        headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            response = requests.head(url, headers=headers, timeout=timeout, allow_redirects=True)
            content_type = response.headers.get("content-type", "").lower()
        except:
            content_type = ""

        # Handle JSON responses (return raw)
        if "application/json" in content_type or "text/json" in content_type:
            # Return JSON as-is with a header
            return f"# JSON Response from {url}\n\n{content}"

        # Handle HTML responses (clean and convert)
        if "text/html" in content_type:
            try:
                cleaned_content = self._clean_html(content, url, output_format)

                # Add metadata
                result_parts = [
                    f"# Content from {url}",
                    "",
                    cleaned_content,
                ]

                # Truncate if too long (prevent token overflow)
                max_length = 10000  # characters
                final_content = "\n".join(result_parts)
                if len(final_content) > max_length:
                    final_content = (
                        final_content[:max_length] +
                        "\n\n...[content truncated due to length]"
                    )

                return final_content

            except Exception as e:
                return f"Error cleaning HTML: {str(e)}"

        # Handle plain text or other formats
        return f"# Content from {url}\n\n{content}"

    async def _arun(
        self,
        url: str,
        timeout: int = 10,
        output_format: str = "markdown",
        user_agent: str = "Mozilla/5.0 (compatible; miniClaw/1.0)",
    ) -> str:
        """Async version (wraps sync execution)."""
        import aiohttp

        self._validate_url(url)

        headers = {"User-Agent": user_agent}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    response.raise_for_status()
                    html = await response.text()

            # Clean HTML (same logic as sync version)
            cleaned_content = self._clean_html(html, url, output_format)
            return f"# Content from {url}\n\n{cleaned_content}"

        except Exception as e:
            return f"Error: {str(e)}"


# Create a singleton instance
fetch_url_tool = FetchURLTool()
