"""
Unit tests for FileDetector class

Tests intelligent file type detection using magic bytes, shebang, and content analysis.
"""

import pytest
from pathlib import Path
from app.utils.file_detector import FileDetector


class TestFileDetector:
    """Test cases for FileDetector class."""

    def test_detect_pdf_by_magic_bytes(self, tmp_path):
        """Test PDF detection using magic bytes."""
        # Create a test file with PDF magic bytes
        test_file = tmp_path / "test.pdf"
        test_file.write_bytes(b'%PDF-1.4\n%test content')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.pdf'
        assert confidence == 'high'

    def test_detect_zip_by_magic_bytes(self, tmp_path):
        """Test ZIP detection using magic bytes."""
        # Create a test file with ZIP magic bytes
        test_file = tmp_path / "test.zip"
        test_file.write_bytes(b'PK\x03\x04\x14\x00\x00\x00')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.zip'
        assert confidence == 'high'

    def test_detect_python_by_extension(self, tmp_path):
        """Test Python file detection by extension."""
        test_file = tmp_path / "test.py"
        test_file.write_text('# Simple Python script\nprint("Hello")')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.py'
        assert confidence == 'high'

    def test_detect_javascript_by_extension(self, tmp_path):
        """Test JavaScript file detection by extension."""
        test_file = tmp_path / "test.js"
        test_file.write_text('console.log("Hello");')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.js'
        assert confidence == 'high'

    def test_detect_by_shebang_python(self, tmp_path):
        """Test Python script detection via shebang."""
        test_file = tmp_path / "script"
        test_file.write_text('#!/usr/bin/env python3\nprint("Hello")')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.py'
        assert confidence == 'high'

    def test_detect_by_shebang_bash(self, tmp_path):
        """Test Bash script detection via shebang."""
        test_file = tmp_path / "script"
        test_file.write_text('#!/bin/bash\necho "Hello"')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.sh'
        assert confidence == 'high'

    def test_detect_go_by_content(self, tmp_path):
        """Test Go file detection by content pattern."""
        test_file = tmp_path / "main"
        test_file.write_text('package main\n\nfunc main() {\n\tprintln("Hello")\n}')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.go'
        assert confidence == 'medium'

    def test_detect_java_by_content(self, tmp_path):
        """Test Java file detection by content pattern."""
        test_file = tmp_path / "Main"
        test_file.write_text('public class Main {\n\tpublic static void main(String[] args) {}\n}')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.java'
        assert confidence == 'medium'

    def test_detect_readme_by_name(self, tmp_path):
        """Test README detection by filename."""
        test_file = tmp_path / "README"
        test_file.write_text('# My Project\nThis is a README file.')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.md'
        assert confidence == 'high'

    def test_detect_license_by_name(self, tmp_path):
        """Test LICENSE detection by filename."""
        test_file = tmp_path / "LICENSE"
        test_file.write_text('MIT License\nCopyright (c) 2024')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.txt'
        assert confidence == 'high'

    def test_is_text_file_without_extension(self, tmp_path):
        """Test text file detection without extension."""
        test_file = tmp_path / "notes"
        test_file.write_text('These are some plain text notes.')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.txt'
        assert confidence == 'low'

    def test_unknown_binary_file(self, tmp_path):
        """Test unknown binary file returns empty type."""
        test_file = tmp_path / "data"
        test_file.write_bytes(b'\x00\x01\x02\x03\x04\x05\x00\x00')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == ''
        assert confidence == 'unknown'

    def test_is_file_allowed_with_allowed_type(self, tmp_path):
        """Test file allowed when type is in allowed list."""
        test_file = tmp_path / "test.py"
        test_file.write_text('print("Hello")')

        allowed_types = ['.py', '.js', '.txt']
        is_allowed, detected_type, reason = FileDetector.is_file_allowed(test_file, allowed_types)

        assert is_allowed is True
        assert detected_type == '.py'
        assert 'Allowed file type' in reason

    def test_is_file_allowed_with_disallowed_type(self, tmp_path):
        """Test file not allowed when type is not in allowed list."""
        test_file = tmp_path / "test.exe"
        test_file.write_bytes(b'MZ\x90\x00')

        allowed_types = ['.py', '.js', '.txt']
        is_allowed, detected_type, reason = FileDetector.is_file_allowed(test_file, allowed_types)

        assert is_allowed is False
        assert detected_type == '.exe'
        assert 'not supported' in reason

    def test_is_file_allowed_readme_with_md_allowed(self, tmp_path):
        """Test README file is allowed when .md is in allowed types."""
        test_file = tmp_path / "README"
        test_file.write_text('# My Project')

        allowed_types = ['.txt', '.md']
        is_allowed, detected_type, reason = FileDetector.is_file_allowed(test_file, allowed_types)

        # README is detected as .md and .md is in allowed types
        assert is_allowed is True
        assert detected_type == '.md'
        assert 'Allowed file type' in reason

    def test_is_file_allowed_readme_without_md_allowed(self, tmp_path):
        """Test README file is allowed as special file even when .md not in allowed types."""
        test_file = tmp_path / "README"
        test_file.write_text('# My Project')

        allowed_types = ['.txt', '.py']  # .md not in allowed types
        is_allowed, detected_type, reason = FileDetector.is_file_allowed(test_file, allowed_types)

        # README is detected as .md but allowed as special documentation file
        assert is_allowed is True
        assert 'Special documentation file' in reason

    def test_detect_batch_files_filters_allowed(self, tmp_path):
        """Test batch file detection filters only allowed files."""
        # Create test files directly in tmp_path
        (tmp_path / "test.py").write_text('print("Hello")')
        (tmp_path / "test.js").write_text('console.log("Hello")')
        (tmp_path / "test.exe").write_bytes(b'MZ\x90\x00')

        files = [tmp_path / "test.py", tmp_path / "test.js", tmp_path / "test.exe"]
        allowed_types = ['.py', '.js', '.txt']

        # Set high max_depth to avoid path depth issues in CI/CD
        allowed, rejected = FileDetector.detect_batch_files(files, allowed_types, max_depth=50)

        assert len(allowed) == 2
        assert len(rejected) == 1
        assert 'not supported' in rejected[0][1]

    def test_detect_batch_files_respects_max_files(self, tmp_path):
        """Test batch file detection respects max files limit."""
        # Create 5 test files directly
        files = []
        for i in range(5):
            test_file = tmp_path / f"test{i}.py"
            test_file.write_text(f'print("{i}")')
            files.append(test_file)

        allowed_types = ['.py']

        # Set max to 3 and high max_depth
        allowed, rejected = FileDetector.detect_batch_files(files, allowed_types, max_files=3, max_depth=50)

        assert len(allowed) == 3

    def test_detect_batch_files_depth_limit(self, tmp_path):
        """Test batch file detection respects depth limit."""
        # Create a deep path
        deep_file = tmp_path / "a" / "b" / "c" / "d" / "e" / "test.py"
        deep_file.parent.mkdir(parents=True, exist_ok=True)
        deep_file.write_text('print("Hello")')

        files = [deep_file]
        allowed_types = ['.py']

        # Set max depth to 3
        allowed, rejected = FileDetector.detect_batch_files(files, allowed_types, max_depth=3)

        assert len(allowed) == 0
        assert len(rejected) == 1
        assert 'Folder depth' in rejected[0][1]
        assert 'exceeds limit' in rejected[0][1]

    def test_detect_sql_by_extension(self, tmp_path):
        """Test SQL file detection by extension."""
        test_file = tmp_path / "test.sql"
        test_file.write_text('CREATE TABLE users (id INT PRIMARY KEY);')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.sql'
        assert confidence == 'high'

    def test_detect_json_by_extension(self, tmp_path):
        """Test JSON file detection by extension."""
        test_file = tmp_path / "test.json"
        test_file.write_text('{"key": "value"}')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.json'
        assert confidence == 'high'

    def test_detect_yaml_by_extension(self, tmp_path):
        """Test YAML file detection by extension."""
        test_file = tmp_path / "config.yaml"
        test_file.write_text('key: value\nlist:\n  - item1')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.yaml'
        assert confidence == 'high'

    def test_detect_csv_by_extension(self, tmp_path):
        """Test CSV file detection by extension."""
        test_file = tmp_path / "data.csv"
        test_file.write_text('name,age\nJohn,30\nJane,25')

        detected_type, confidence = FileDetector.detect_file_type(test_file)
        assert detected_type == '.csv'
        assert confidence == 'high'
