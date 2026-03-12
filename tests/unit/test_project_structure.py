"""
Simple project structure tests - no imports required
"""
import os
import sys
from pathlib import Path

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

PROJECT_DIR = Path("I:/code/miniclaw")

def test_project_structure():
    """Test that project structure exists"""
    print("Testing project structure...")

    required_dirs = [
        "backend/app",
        "frontend/app",
        "tests/e2e",
        "tests/unit",
    ]

    missing = []
    for dir_path in required_dirs:
        full_path = PROJECT_DIR / dir_path
        if full_path.exists():
            print(f"  ✓ {dir_path}")
        else:
            print(f"  ✗ {dir_path} MISSING")
            missing.append(dir_path)

    if missing:
        print(f"\n✗ Missing directories: {missing}")
        return False
    else:
        print("\n✓ All required directories exist")
        return True

def test_backend_files():
    """Test that required backend files exist"""
    print("\nTesting backend files...")

    required_files = [
        "backend/app/main.py",
        "backend/app/config.py",
        "backend/requirements.txt",
        "backend/pyproject.toml",
    ]

    missing = []
    for file_path in required_files:
        full_path = PROJECT_DIR / file_path
        if full_path.exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} MISSING")
            missing.append(file_path)

    if missing:
        print(f"\n✗ Missing files: {missing}")
        return False
    else:
        print("\n✓ All required backend files exist")
        return True

def test_frontend_files():
    """Test that required frontend files exist"""
    print("\nTesting frontend files...")

    required_files = [
        "frontend/package.json",
        "frontend/tsconfig.json",
        "frontend/next.config.ts",
        "frontend/app/layout.tsx",
        "frontend/app/page.tsx",
        "frontend/app/globals.css",
    ]

    missing = []
    for file_path in required_files:
        full_path = PROJECT_DIR / file_path
        if full_path.exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} MISSING")
            missing.append(file_path)

    if missing:
        print(f"\n✗ Missing files: {missing}")
        return False
    else:
        print("\n✓ All required frontend files exist")
        return True

def test_test_files():
    """Test that test files exist"""
    print("\nTesting test files...")

    required_files = [
        "tests/e2e/smoke.spec.ts",
        "tests/unit/test_backend_smoke.py",
        "tests/README.md",
        "tests/run-tests.sh",
    ]

    missing = []
    for file_path in required_files:
        full_path = PROJECT_DIR / file_path
        if full_path.exists():
            print(f"  ✓ {file_path}")
        else:
            print(f"  ✗ {file_path} MISSING")
            missing.append(file_path)

    if missing:
        print(f"\n✗ Missing files: {missing}")
        return False
    else:
        print("\n✓ All required test files exist")
        return True

def test_syntax():
    """Test Python files for syntax errors"""
    print("\nTesting Python syntax...")

    python_files = list((PROJECT_DIR / "backend/app").rglob("*.py"))

    errors = []
    for py_file in python_files:
        try:
            with open(py_file, 'r', encoding='utf-8') as f:
                compile(f.read(), str(py_file), 'exec')
            print(f"  ✓ {py_file.relative_to(PROJECT_DIR)}")
        except SyntaxError as e:
            print(f"  ✗ {py_file.relative_to(PROJECT_DIR)}: {e}")
            errors.append(str(py_file))

    if errors:
        print(f"\n✗ Syntax errors in: {errors}")
        return False
    else:
        print("\n✓ All Python files have valid syntax")
        return True

def main():
    """Run all tests"""
    print("=" * 60)
    print("miniClaw Project Structure Tests")
    print("=" * 60)
    print()

    results = []

    results.append(test_project_structure())
    results.append(test_backend_files())
    results.append(test_frontend_files())
    results.append(test_test_files())
    results.append(test_syntax())

    print()
    print("=" * 60)
    print("Results")
    print("=" * 60)

    passed = sum(results)
    total = len(results)
    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("\n✓ All tests passed!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
