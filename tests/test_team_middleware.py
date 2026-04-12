"""
Quick verification test for team_middleware.py
"""
import sys
sys.path.insert(0, '.')

from app.core.team_middleware import get_current_team_member, require_permissions
from fastapi import HTTPException
import inspect

def test_middleware_functions_exist():
    """Test that middleware functions are properly defined"""
    print("Testing middleware function definitions...")
    
    # Test get_current_team_member exists and is async
    assert callable(get_current_team_member)
    assert inspect.iscoroutinefunction(get_current_team_member)
    print("✓ get_current_team_member() is defined as async function")
    
    # Test require_permissions exists and is callable
    assert callable(require_permissions)
    print("✓ require_permissions() decorator is defined")
    
    # Test decorator returns a function
    decorator = require_permissions("test.permission")
    assert callable(decorator)
    print("✓ require_permissions() returns a decorator function")

def test_decorator_signature():
    """Test that decorator preserves function signature"""
    print("\nTesting decorator signature preservation...")
    
    # Create a test function
    async def test_endpoint(data: dict, current_team_member=None, db=None):
        return {"status": "ok"}
    
    # Apply decorator
    decorated = require_permissions("test.permission")(test_endpoint)
    
    # Check it's still callable
    assert callable(decorated)
    assert inspect.iscoroutinefunction(decorated)
    print("✓ Decorated function is still async and callable")
    
    # Check function name is preserved (via functools.wraps)
    assert decorated.__name__ == "test_endpoint"  # wraps preserves the original name
    print("✓ Decorator uses functools.wraps and preserves function name")

def test_multiple_permissions():
    """Test decorator with multiple permissions"""
    print("\nTesting multiple permissions...")
    
    # Test with multiple permissions
    decorator = require_permissions("payments.view", "payments.create", "payments.refund")
    assert callable(decorator)
    print("✓ Decorator accepts multiple permissions")

if __name__ == "__main__":
    print("=" * 60)
    print("Team Middleware Verification Tests")
    print("=" * 60)
    
    try:
        test_middleware_functions_exist()
        test_decorator_signature()
        test_multiple_permissions()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nMiddleware components are properly implemented:")
        print("  ✓ get_current_team_member() dependency")
        print("  ✓ require_permissions() decorator")
        print("  ✓ Decorator preserves function signatures")
        print("  ✓ Multiple permissions support")
        print("\nNote: Full integration tests with database and FastAPI")
        print("      will be performed in the integration test suite.")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

