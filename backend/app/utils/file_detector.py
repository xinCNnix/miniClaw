"""
File Type Detector - Intelligent file type detection

This module provides smart file type detection beyond file extensions,
using content analysis and magic bytes detection.
"""

import os
import mimetypes
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class FileDetector:
    """
    Intelligent file type detector.

    Detects file types using:
    1. File extension
    2. Magic bytes (file signatures)
    3. Content analysis (shebang, common patterns)
    """

    # Magic bytes for common file types
    MAGIC_BYTES = {
        b'\x50\x4b\x03\x04': '.zip',
        b'\x50\x4b\x05\x06': '.zip',
        b'\x50\x4b\x07\x08': '.zip',
        b'\x1f\x8b\x08': '.gz',
        b'\x42\x5a\x68': '.bz2',
        b'\xfd\x37\x7a\x58\x5a\x00': '.xz',
        b'\x25\x50\x44\x46': '.pdf',
        b'\x50\x4b\x03\x04': '.zip',
        b'\x50\x4b\x05\x06': '.zip',
        b'\x50\x4b\x07\x08': '.zip',
        b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1': '.docx',  # DOCX/MSEXCEL
        b'\x50\x4b\x03\x04\x14\x00\x06\x00': '.pptx',  # PPTX
        b'\x7f\x45\x4c\x46': '.elf',  # Linux executable
        b'\x4d\x5a': '.exe',  # Windows executable
        b'\x25\x21\x50\x53': '.ps',   # PostScript
    }

    # Shebang patterns for script files
    SHEBANG_PATTERNS = {
        '#!/usr/bin/env python': '.py',
        '#!/usr/bin/python': '.py',
        '#!/usr/bin/env python3': '.py',
        '#!/usr/bin/python3': '.py',
        '#!/bin/bash': '.sh',
        '#!/bin/sh': '.sh',
        '#!/usr/bin/env node': '.js',
        '#!/usr/bin/node': '.js',
        '#!/usr/bin/perl': '.pl',
        '#!/usr/bin/env perl': '.pl',
        '#!/usr/bin/env ruby': '.rb',
        '#!/usr/bin/ruby': '.rb',
        '#!/usr/bin/env php': '.php',
        '#!/usr/bin/php': '.php',
        '#!/usr/bin/env golang': '.go',
    }

    # Content patterns for specific files
    CONTENT_PATTERNS = {
        '#!include <': '.h',      # C header
        '#import <iostream>': '.cpp',  # C++
        '#include <': '.c',       # C (but not header)
        'package main': '.go',     # Go
        'public class': '.java',  # Java
        'def __init__': '.py',     # Python (class definition)
        'function ': '.js',       # JavaScript
        'export const ': '.ts',    # TypeScript
        'CREATE TABLE': '.sql',    # SQL
        '-----BEGIN PGP': '.pgp',   # PGP
        '-----BEGIN SSH': '.ssh',   # SSH key
    }

    @classmethod
    def detect_file_type(
        cls,
        file_path: Path,
        content: Optional[bytes] = None
    ) -> Tuple[str, str]:
        """
        Detect file type intelligently.

        Args:
            file_path: Path to the file
            content: File content (optional, will read if not provided)

        Returns:
            Tuple of (detected_extension, confidence)
            - confidence: 'high', 'medium', 'low'
        """
        # Try extension first
        ext = file_path.suffix.lower()
        if ext and ext != '.':
            return ext, 'high'

        # No extension or dotfile, try content analysis
        if content is None:
            try:
                with open(file_path, 'rb') as f:
                    content = f.read(8192)  # Read first 8KB
            except Exception as e:
                logger.warning(f"Failed to read file {file_path}: {e}")
                return '', 'unknown'

        # Check magic bytes
        for magic, detected_ext in cls.MAGIC_BYTES.items():
            if content.startswith(magic):
                return detected_ext, 'high'

        # Try to detect as text and analyze
        try:
            text_content = content[:4096].decode('utf-8', errors='ignore')
        except:
            return '', 'low'

        # Check for shebang
        for line in text_content.split('\n')[:10]:  # Check first 10 lines
            line = line.strip()
            for shebang, detected_ext in cls.SHEBANG_PATTERNS.items():
                if line.startswith(shebang):
                    return detected_ext, 'high'

        # Check content patterns
        for pattern, detected_ext in cls.CONTENT_PATTERNS.items():
            if pattern in text_content:
                return detected_ext, 'medium'

        # Check if it's a special file by name
        filename = file_path.name.upper()
        special_files = {
            'README': '.md',
            'CHANGELOG': '.md',
            'LICENSE': '.txt',
            'AUTHORS': '.txt',
            'CONTRIBUTING': '.md',
            'MAKEFILE': '.makefile',
            'DOCKERFILE': '.dockerfile',
            'GITIGNORE': '.gitignore',
            'ENV': '.env',
        }

        if filename in special_files:
            return special_files[filename], 'high'

        # Try to detect if it's a text file
        if cls._is_text_content(content):
            return '.txt', 'low'

        return '', 'unknown'

    @staticmethod
    def _is_text_content(content: bytes) -> bool:
        """
        Check if content appears to be text.

        Args:
            content: File content as bytes

        Returns:
            True if content appears to be text
        """
        if len(content) == 0:
            return True

        # Check for null bytes (indicator of binary)
        if b'\x00' in content[:1024]:
            return False

        # Check ratio of text characters
        text_bytes = bytes([7, 8, 9, 10, 12, 13, 27] + list(range(0x20, 0x7F)))
        text_count = sum(1 for byte in content[:4096] if byte in text_bytes)

        return text_count / len(content[:4096]) > 0.7

    @classmethod
    def is_file_allowed(
        cls,
        file_path: Path,
        allowed_types: list[str],
        content: Optional[bytes] = None
    ) -> Tuple[bool, str, str]:
        """
        Check if file is allowed based on intelligent type detection.

        Args:
            file_path: Path to the file
            allowed_types: List of allowed file extensions
            content: File content (optional)

        Returns:
            Tuple of (is_allowed, detected_type, reason)
        """
        detected_type, confidence = cls.detect_file_type(file_path, content)

        if not detected_type:
            # Unknown type, check if it's text
            if content is None:
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read(8192)
                except:
                    return False, '', 'Cannot read file'

            if cls._is_text_content(content):
                return True, '.txt', 'Detected as text file'
            else:
                return False, '', 'Unknown file type (possibly binary)'

        # Check if detected type is in allowed types
        if detected_type in allowed_types:
            return True, detected_type, f'Allowed file type (detected with {confidence} confidence)'

        # Special case: file without extension but known special file
        if not file_path.suffix or file_path.suffix == '.':
            special_names = ['README', 'CHANGELOG', 'LICENSE', 'AUTHORS', 'CONTRIBUTING']
            if file_path.name.upper() in special_names:
                return True, detected_type, 'Special documentation file'

        return False, detected_type, f'File type not supported: {detected_type}'

    @classmethod
    def detect_batch_files(
        cls,
        files: list[Path],
        allowed_types: list[str],
        max_files: int = 20,
        max_depth: int = 5
    ) -> Tuple[list[Path], list[Tuple[Path, str]]]:
        """
        Detect and filter files for batch/folder upload.

        Args:
            files: List of file paths
            allowed_types: Allowed file extensions
            max_files: Maximum number of files to process
            max_depth: Maximum folder depth to traverse

        Returns:
            Tuple of (allowed_files, rejected_files)
            - rejected_files: list of (file_path, reason)
        """
        allowed = []
        rejected = []

        for file_path in files[:max_files]:
            # Check depth
            depth = len(file_path.parts)
            if depth > max_depth:
                rejected.append((file_path, f'Folder depth {depth} exceeds limit {max_depth}'))
                continue

            # Skip directories for now (will be processed recursively if needed)
            if file_path.is_dir():
                continue

            # Detect file type
            try:
                is_allowed, detected_type, reason = cls.is_file_allowed(file_path, allowed_types)
                if is_allowed:
                    allowed.append(file_path)
                else:
                    rejected.append((file_path, reason))
            except Exception as e:
                rejected.append((file_path, f'Error: {str(e)}'))
                logger.warning(f"Error detecting file type for {file_path}: {e}")

        return allowed, rejected


def detect_file_type(file_path: Path, content: Optional[bytes] = None) -> Tuple[str, str]:
    """
    Convenience function to detect file type.

    Args:
        file_path: Path to the file
        content: File content (optional)

    Returns:
        Tuple of (detected_extension, confidence)
    """
    return FileDetector.detect_file_type(file_path, content)


def is_file_allowed(file_path: Path, allowed_types: list[str], content: Optional[bytes] = None) -> Tuple[bool, str, str]:
    """
    Convenience function to check if file is allowed.

    Args:
        file_path: Path to the file
        allowed_types: Allowed file extensions
        content: File content (optional)

    Returns:
        Tuple of (is_allowed, detected_type, reason)
    """
    return FileDetector.is_file_allowed(file_path, allowed_types, content)
