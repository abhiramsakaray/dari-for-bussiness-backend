"""
Test database-dependent functions in team_auth.py
"""
import sys
sys.path.insert(0, '.')

from datetime import datetime, timedelta
from app.core.team_auth import increment_failed_attempts, reset_failed_attempts

# Mock database session
class MockDB:
    def __init__(self):
        self.committed = False
    
    def commit(self):
        self.committed = True
        print("  → Database commit called")

# Mock team member
class MockTeamMember:
    def __init__(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        self.last_login = None

def test_increment_failed_attempts():
    """Test failed login attempt tracking and lockout"""
    print("Testing increment_failed_attempts()...")
    
    # Test 1: First 4 attempts (no lock)
    member = MockTeamMember()
    db = MockDB()
    
    for i in range(4):
        increment_failed_attempts(member, db)
        print(f"  Attempt {i+1}: failed_attempts={member.failed_login_attempts}, locked_until={member.locked_until}")
    
    assert member.failed_login_attempts == 4
    assert member.locked_until is None
    print("✓ First 4 attempts: No lockout")
    
    # Test 2: 5th attempt (15 min lock)
    member = MockTeamMember()
    db = MockDB()
    member.failed_login_attempts = 4
    
    increment_failed_attempts(member, db)
    assert member.failed_login_attempts == 5
    assert member.locked_until is not None
    lock_duration = (member.locked_until - datetime.utcnow()).total_seconds()
    assert 890 < lock_duration < 910  # ~15 minutes (900 seconds)
    print(f"✓ 5th attempt: Locked for 15 minutes (until {member.locked_until})")
    
    # Test 3: 10th attempt (1 hour lock)
    member = MockTeamMember()
    db = MockDB()
    member.failed_login_attempts = 9
    
    increment_failed_attempts(member, db)
    assert member.failed_login_attempts == 10
    lock_duration = (member.locked_until - datetime.utcnow()).total_seconds()
    assert 3590 < lock_duration < 3610  # ~1 hour (3600 seconds)
    print(f"✓ 10th attempt: Locked for 1 hour (until {member.locked_until})")
    
    # Test 4: 20th attempt (permanent lock)
    member = MockTeamMember()
    db = MockDB()
    member.failed_login_attempts = 19
    
    increment_failed_attempts(member, db)
    assert member.failed_login_attempts == 20
    lock_duration = (member.locked_until - datetime.utcnow()).total_seconds()
    assert lock_duration >= 31535000  # ~365 days (permanent lock)
    print(f"✓ 20th attempt: Permanently locked (until {member.locked_until})")

def test_reset_failed_attempts():
    """Test resetting failed attempts on successful login"""
    print("\nTesting reset_failed_attempts()...")
    
    member = MockTeamMember()
    member.failed_login_attempts = 7
    member.locked_until = datetime.utcnow() + timedelta(minutes=15)
    
    db = MockDB()
    reset_failed_attempts(member, db)
    
    assert member.failed_login_attempts == 0
    assert member.locked_until is None
    assert member.last_login is not None
    assert db.committed == True
    print(f"✓ Failed attempts reset: attempts={member.failed_login_attempts}, locked_until={member.locked_until}")
    print(f"✓ Last login updated: {member.last_login}")

if __name__ == "__main__":
    print("=" * 60)
    print("Team Auth Database Functions Test")
    print("=" * 60)
    
    try:
        test_increment_failed_attempts()
        test_reset_failed_attempts()
        
        print("\n" + "=" * 60)
        print("✅ ALL DATABASE FUNCTION TESTS PASSED!")
        print("=" * 60)
        print("\nLockout policy verified:")
        print("  ✓ 5 failed attempts → 15 minute lock")
        print("  ✓ 10 failed attempts → 1 hour lock")
        print("  ✓ 20 failed attempts → Permanent lock (admin unlock required)")
        print("  ✓ Successful login resets counter and unlocks account")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
