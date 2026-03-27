"""
Logging Sanitizer Module

This module provides sensitive information sanitization for logging,
ensuring that API keys, passwords, and other sensitive data are automatically
redacted from log output.
"""

import re
import logging
from typing import Pattern, Dict, Any, Optional, List
from pathlib import Path


class LogSanitizer:
    """
    Sanitizes sensitive information from log messages.

    Automatically detects and redacts:
    - API keys (sk-*, sk-ant-*, Bearer tokens)
    - Passwords and password fields
    - User PII (email, phone, ID)
    - Database connection strings
    - File paths (partial redaction, preserving structure)
    """

    # Default sensitive patterns
    DEFAULT_PATTERNS: Dict[str, tuple[str, str]] = {
        "api_key_openai": (r'sk-[a-zA-Z0-9]{48,}', 'sk-***'),
        "api_key_anthropic": (r'sk-ant-[a-zA-Z0-9_-]{90,}', 'sk-ant-***'),
        "bearer_token": (r'Bearer [a-zA-Z0-9_-]{20,}', 'Bearer ***'),
        "api_key_generic": (r'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{20,}["\']?', 'api_key=***'),
        "password": (r'password["\']?\s*[:=]\s*["\']?[^"\')\s]+["\']?', 'password=***'),
        "token": (r'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_.-]{20,}["\']?', 'token=***'),
        "secret": (r'secret["\']?\s*[:=]\s*["\']?[^"\')\s]+["\']?', 'secret=***'),
        "email": (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***'),
        "phone": (r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b', '***-***-****'),
        "credit_card": (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '****-****-****-****'),
        "ip_address": (r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '***.***.***.***'),
        "connection_string": (r'(mysql|postgresql|mongodb)://[^@]+@[^/]+', '\\1://***:***@***'),
        "jwt": (r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', 'eyJ***.***.***'),
    }

    def __init__(
        self,
        enabled: bool = True,
        sanitize_user_input: bool = False,
        sanitize_file_paths: bool = True,
        custom_patterns: Optional[Dict[str, tuple[str, str]]] = None
    ):
        """
        Initialize log sanitizer.

        Args:
            enabled: Enable/disable sanitization
            sanitize_user_input: Sanitize user input content (may over-sanitize)
            sanitize_file_paths: Sanitize file paths partially
            custom_patterns: Custom regex patterns and replacements
        """
        self.enabled = enabled
        self.sanitize_user_input = sanitize_user_input
        self.sanitize_file_paths = sanitize_file_paths
        self.patterns: Dict[str, tuple[Pattern, str]] = {}

        # Compile default patterns
        for name, (pattern, replacement) in self.DEFAULT_PATTERNS.items():
            self.add_pattern(name, pattern, replacement)

        # Add custom patterns
        if custom_patterns:
            for name, (pattern, replacement) in custom_patterns.items():
                self.add_pattern(name, pattern, replacement)

        # Statistics tracking
        self.stats = {
            "sanitized_logs": 0,
            "patterns_matched": {}
        }

    def add_pattern(self, name: str, pattern: str, replacement: str) -> None:
        """
        Add a custom sanitization pattern.

        Args:
            name: Pattern name for tracking
            pattern: Regex pattern
            replacement: Replacement string
        """
        try:
            compiled = re.compile(pattern, re.IGNORECASE)
            self.patterns[name] = (compiled, replacement)
        except re.error as e:
            logging.getLogger(__name__).warning(f"Invalid sanitization pattern '{name}': {e}")

    def remove_pattern(self, name: str) -> None:
        """
        Remove a sanitization pattern.

        Args:
            name: Pattern name to remove
        """
        if name in self.patterns:
            del self.patterns[name]

    def sanitize_string(self, text: str) -> str:
        """
        Sanitize a string by applying all patterns.

        Args:
            text: Input text

        Returns:
            Sanitized text
        """
        if not self.enabled or not text:
            return text

        result = text
        matched = False

        for name, (pattern, replacement) in self.patterns.items():
            matches = pattern.findall(result)
            if matches:
                matched = True
                result = pattern.sub(replacement, result)
                # Track statistics
                if name not in self.stats["patterns_matched"]:
                    self.stats["patterns_matched"][name] = 0
                self.stats["patterns_matched"][name] += len(matches)

        if matched:
            self.stats["sanitized_logs"] += 1

        # Sanitize file paths if enabled
        if self.sanitize_file_paths:
            result = self._sanitize_file_paths(result)

        return result

    def _sanitize_file_paths(self, text: str) -> str:
        """
        Partially sanitize file paths, preserving structure.

        Examples:
            /Users/john/code/project -> /Users/***/code/project
            C:\\Users\\John\\Documents\\file.txt -> C:\\Users\\***\\Documents\\file.txt

        Args:
            text: Input text

        Returns:
            Text with sanitized file paths
        """
        # Unix paths
        text = re.sub(
            r'/home/[^/]+|/Users/[^/]+|/root/[^/]*',
            lambda m: m.group(0).split('/')[0] + '/***',
            text
        )

        # Windows paths
        text = re.sub(
            r'[A-Z]:\\Users\\[^\\]+',
            lambda m: m.group(0).split('\\')[0] + '\\' + '\\'.join(m.group(0).split('\\')[1:2]) + '\\***',
            text
        )

        return text

    def sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Recursively sanitize dictionary values.

        Args:
            data: Input dictionary

        Returns:
            Sanitized dictionary
        """
        if not self.enabled:
            return data

        sanitized = {}
        for key, value in data.items():
            # Check if key indicates sensitive data
            if self._is_sensitive_key(key):
                sanitized[key] = "***"
            elif isinstance(value, str):
                sanitized[key] = self.sanitize_string(value)
            elif isinstance(value, dict):
                sanitized[key] = self.sanitize_dict(value)
            elif isinstance(value, list):
                sanitized[key] = [
                    self.sanitize_dict(item) if isinstance(item, dict) else
                    self.sanitize_string(item) if isinstance(item, str) else item
                    for item in value
                ]
            else:
                sanitized[key] = value

        return sanitized

    def _is_sensitive_key(self, key: str) -> bool:
        """
        Check if a dictionary key indicates sensitive data.

        Args:
            key: Dictionary key

        Returns:
            True if key suggests sensitive data
        """
        sensitive_keywords = [
            'password', 'passwd', 'pwd',
            'api_key', 'apikey', 'api-key',
            'secret', 'token', 'auth',
            'credential', 'credit_card',
            'ssn', 'social_security',
            'private_key', 'private-key'
        ]

        key_lower = key.lower()
        return any(keyword in key_lower for keyword in sensitive_keywords)

    def sanitize_log_record(self, record: logging.LogRecord) -> logging.LogRecord:
        """
        Sanitize a logging.LogRecord in-place.

        Args:
            record: Log record to sanitize

        Returns:
            Sanitized log record
        """
        if not self.enabled:
            return record

        # Sanitize message
        if record.msg and isinstance(record.msg, str):
            record.msg = self.sanitize_string(record.msg)

        # Sanitize args
        if record.args:
            sanitized_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    sanitized_args.append(self.sanitize_string(arg))
                elif isinstance(arg, dict):
                    sanitized_args.append(self.sanitize_dict(arg))
                else:
                    sanitized_args.append(arg)
            record.args = tuple(sanitized_args)

        # Sanitize extra fields
        for key, value in record.__dict__.items():
            if key not in {'name', 'msg', 'args', 'levelname', 'levelno',
                          'pathname', 'filename', 'module', 'lineno',
                          'funcName', 'created', 'msecs', 'relativeCreated',
                          'thread', 'threadName', 'processName', 'process',
                          'getMessage', 'exc_info', 'exc_text', 'stack_info'}:
                if isinstance(value, str):
                    record.__dict__[key] = self.sanitize_string(value)
                elif isinstance(value, dict):
                    record.__dict__[key] = self.sanitize_dict(value)

        return record

    def get_stats(self) -> Dict[str, Any]:
        """
        Get sanitization statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "enabled": self.enabled,
            "sanitized_logs": self.stats["sanitized_logs"],
            "patterns_matched": self.stats["patterns_matched"].copy(),
            "total_patterns": len(self.patterns)
        }

    def reset_stats(self) -> None:
        """Reset sanitization statistics."""
        self.stats = {
            "sanitized_logs": 0,
            "patterns_matched": {}
        }


# Global sanitizer instance
_global_sanitizer: Optional[LogSanitizer] = None


def get_log_sanitizer() -> LogSanitizer:
    """
    Get the global log sanitizer instance.

    Returns:
        LogSanitizer instance
    """
    global _global_sanitizer
    if _global_sanitizer is None:
        _global_sanitizer = LogSanitizer()
    return _global_sanitizer


def configure_log_sanitizer(
    enabled: bool = True,
    sanitize_user_input: bool = False,
    sanitize_file_paths: bool = True,
    custom_patterns: Optional[Dict[str, tuple[str, str]]] = None
) -> None:
    """
    Configure the global log sanitizer.

    Args:
        enabled: Enable/disable sanitization
        sanitize_user_input: Sanitize user input content
        sanitize_file_paths: Sanitize file paths partially
        custom_patterns: Custom regex patterns and replacements
    """
    global _global_sanitizer
    _global_sanitizer = LogSanitizer(
        enabled=enabled,
        sanitize_user_input=sanitize_user_input,
        sanitize_file_paths=sanitize_file_paths,
        custom_patterns=custom_patterns
    )
