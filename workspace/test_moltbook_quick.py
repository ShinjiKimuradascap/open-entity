#!/usr/bin/env python3
"""Quick test for Moltbook integration modules"""

import sys
sys.path.insert(0, 'services')

def test_imports():
    """Test module imports"""
    results = []
    
    try:
        from moltbook_integration import (
            ExponentialBackoff,
            MoltbookClient,
            MoltbookPeerBridge,
            MoltbookPost,
            MoltbookMessage,
            create_moltbook_client
        )
        results.append("✓ moltbook_integration imports successful")
    except Exception as e:
        results.append(f"✗ moltbook_integration import error: {e}")
        return results
    
    try:
        from moltbook_identity_client import MoltbookClient as IdentityClient
        results.append("✓ moltbook_identity_client imports successful")
    except Exception as e:
        results.append(f"✗ moltbook_identity_client import error: {e}")
    
    return results

def test_exponential_backoff():
    """Test ExponentialBackoff class"""
    from moltbook_integration import ExponentialBackoff
    results = []
    
    # Test 1: Initial delay
    try:
        backoff = ExponentialBackoff(initial_delay=1.0, max_delay=60.0)
        assert backoff.next_delay() == 1.0
        results.append("✓ test_initial_delay passed")
    except Exception as e:
        results.append(f"✗ test_initial_delay failed: {e}")
    
    # Test 2: Exponential increase
    try:
        backoff = ExponentialBackoff(initial_delay=1.0, exponent=2.0)
        delays = [backoff.next_delay() for _ in range(4)]
        assert delays == [1.0, 2.0, 4.0, 8.0]
        results.append("✓ test_exponential_increase passed")
    except Exception as e:
        results.append(f"✗ test_exponential_increase failed: {e}")
    
    # Test 3: Max delay cap
    try:
        backoff = ExponentialBackoff(initial_delay=10.0, max_delay=30.0, exponent=2.0)
        assert backoff.next_delay() == 10.0
        assert backoff.next_delay() == 20.0
        assert backoff.next_delay() == 30.0  # capped
        assert backoff.next_delay() == 30.0  # still capped
        results.append("✓ test_max_delay_cap passed")
    except Exception as e:
        results.append(f"✗ test_max_delay_cap failed: {e}")
    
    # Test 4: Reset
    try:
        backoff = ExponentialBackoff(initial_delay=1.0)
        backoff.next_delay()
        backoff.next_delay()
        assert backoff._attempt == 2
        backoff.reset()
        assert backoff._attempt == 0
        assert backoff.next_delay() == 1.0
        results.append("✓ test_reset passed")
    except Exception as e:
        results.append(f"✗ test_reset failed: {e}")
    
    # Test 5: Exhausted
    try:
        backoff = ExponentialBackoff(max_retries=3)
        assert not backoff.exhausted
        backoff.next_delay()
        backoff.next_delay()
        backoff.next_delay()
        assert backoff.exhausted
        results.append("✓ test_exhausted passed")
    except Exception as e:
        results.append(f"✗ test_exhausted failed: {e}")
    
    return results

def test_data_classes():
    """Test data classes"""
    from moltbook_integration import MoltbookPost, MoltbookMessage
    from datetime import datetime, timezone
    results = []
    
    try:
        now = datetime.now(timezone.utc)
        post = MoltbookPost(
            id="post_123",
            agent_id="agent_a",
            content="Test content",
            submolt="ai_agents",
            created_at=now,
            reply_to=None,
            likes=10,
            replies=3
        )
        assert post.id == "post_123"
        assert post.likes == 10
        results.append("✓ MoltbookPost creation passed")
    except Exception as e:
        results.append(f"✗ MoltbookPost test failed: {e}")
    
    try:
        now = datetime.now(timezone.utc)
        msg = MoltbookMessage(
            id="msg_123",
            from_agent_id="agent_a",
            to_agent_id="agent_b",
            content="Hello",
            created_at=now,
            read=False
        )
        assert msg.id == "msg_123"
        assert not msg.read
        results.append("✓ MoltbookMessage creation passed")
    except Exception as e:
        results.append(f"✗ MoltbookMessage test failed: {e}")
    
    return results

if __name__ == "__main__":
    print("=" * 60)
    print("Moltbook Integration Quick Test")
    print("=" * 60)
    
    print("\n--- Import Tests ---")
    for result in test_imports():
        print(result)
    
    print("\n--- ExponentialBackoff Tests ---")
    for result in test_exponential_backoff():
        print(result)
    
    print("\n--- Data Class Tests ---")
    for result in test_data_classes():
        print(result)
    
    print("\n" + "=" * 60)
    print("Test completed")
    print("=" * 60)
