"""
Trusted LLM provider domains configuration.

This module maintains a whitelist of trusted LLM provider domains to prevent
API keys from being sent to malicious servers.
"""

from typing import Set

# Trusted LLM provider domains
TRUSTED_DOMAINS: Set[str] = {
    # OpenAI
    "api.openai.com",
    "oai-poc.appspot.com",

    # Alibaba Qwen (通义千问)
    "dashscope.aliyuncs.com",
    "api.aliyun.com",

    # DeepSeek
    "api.deepseek.com",

    # Anthropic Claude
    "api.anthropic.com",

    # Google Gemini
    "generativelanguage.googleapis.com",
    "generativelanguage.googleapis.com",

    # Local development
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
}


def is_trusted_domain(domain: str) -> bool:
    """
    Check if a domain is in the trusted list.

    Args:
        domain: Domain to check (e.g., "api.openai.com")

    Returns:
        True if domain is trusted, False otherwise
    """
    # Remove protocol and path if present
    clean_domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    clean_domain = clean_domain.split(":")[0]  # Remove port

    return clean_domain in TRUSTED_DOMAINS


def get_trusted_domains() -> Set[str]:
    """Get the set of trusted domains."""
    return TRUSTED_DOMAINS.copy()
