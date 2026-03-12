"""
Backend smoke tests - can run without full server startup
"""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../backend'))

def test_imports():
    """Test that core modules can be imported"""
    try:
        from app.main import app
        print("✓ Can import app.main")
    except Exception as e:
        print(f"✗ Failed to import app.main: {e}")
        return False

    try:
        from app.core.config import settings
        print("✓ Can import app.core.config")
    except Exception as e:
        print(f"✗ Failed to import app.core.config: {e}")
        return False

    return True

def test_config():
    """Test configuration settings"""
    try:
        from app.core.config import settings

        # Check required settings
        assert hasattr(settings, 'APP_NAME'), "Missing APP_NAME setting"
        assert hasattr(settings, 'VERSION'), "Missing VERSION setting"
        print(f"✓ Config loaded: {settings.APP_NAME} v{settings.VERSION}")
        return True
    except Exception as e:
        print(f"✗ Config test failed: {e}")
        return False

def test_fastapi_app():
    """Test FastAPI app structure"""
    try:
        from app.main import app

        # Check it's a FastAPI app
        assert hasattr(app, 'routes'), "App missing routes"
        assert len(app.routes) > 0, "App has no routes"

        # List routes
        print(f"✓ FastAPI app has {len(app.routes)} routes:")
        for route in app.routes[:5]:  # Show first 5
            if hasattr(route, 'path') and hasattr(route, 'methods'):
                print(f"  - {route.methods} {route.path}")
        if len(app.routes) > 5:
            print(f"  ... and {len(app.routes) - 5} more")

        return True
    except Exception as e:
        print(f"✗ FastAPI app test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("=== Backend Smoke Tests ===")
    print()

    results = []

    print("[1/3] Testing imports...")
    results.append(test_imports())
    print()

    print("[2/3] Testing configuration...")
    results.append(test_config())
    print()

    print("[3/3] Testing FastAPI app...")
    results.append(test_fastapi_app())
    print()

    print("=== Results ===")
    passed = sum(results)
    total = len(results)
    print(f"Passed: {passed}/{total}")

    if passed == total:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
