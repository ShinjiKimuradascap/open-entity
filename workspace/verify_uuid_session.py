#!/usr/bin/env python3
"""UUID Session verification script"""

import asyncio
import sys
sys.path.insert(0, '/home/moco/workspace')

from services.session_manager import SessionManager

async def verify():
    """Verify UUID-based session management"""
    print("=" * 60)
    print("S3: UUID-based Session Management Verification")
    print("=" * 60)
    
    sm = SessionManager(default_ttl_minutes=5)
    await sm.start()
    
    try:
        # Test 1: Create session with UUID
        print("\n[1] Session creation with UUID...")
        session = await sm.create_session("entity_a", "entity_b")
        session_id = session.session_id
        
        print(f"  Session ID: {session_id}")
        print(f"  Length: {len(session_id)} (expected: 36 for UUID v4)")
        
        # Verify UUID format
        parts = session_id.split('-')
        if len(parts) == 5 and len(session_id) == 36:
            print("  ✓ Valid UUID v4 format")
        else:
            print("  ✗ Invalid UUID format")
            return False
        
        # Test 2: Session reuse
        print("\n[2] Session reuse (same sender/recipient)...")
        session2 = await sm.create_session("entity_a", "entity_b")
        if session2.session_id == session_id:
            print("  ✓ Same session reused correctly")
        else:
            print("  ✗ Session not reused")
            return False
        
        # Test 3: Different recipient = different session
        print("\n[3] Different recipient = new session...")
        session3 = await sm.create_session("entity_a", "entity_c")
        if session3.session_id != session_id:
            print(f"  ✓ New session created: {session3.session_id[:8]}...")
        else:
            print("  ✗ Same session used")
            return False
        
        # Test 4: Get session by ID
        print("\n[4] Get session by UUID...")
        retrieved = await sm.get_session(session_id)
        if retrieved and retrieved.session_id == session_id:
            print("  ✓ Session retrieved correctly")
        else:
            print("  ✗ Session not found")
            return False
        
        # Test 5: Sequence validation
        print("\n[5] Sequence number validation...")
        is_valid = await sm.validate_and_update_sequence(session_id, 1)
        if is_valid:
            print("  ✓ Sequence 1 accepted")
        else:
            print("  ✗ Sequence 1 rejected")
            return False
        
        is_valid = await sm.validate_and_update_sequence(session_id, 2)
        if is_valid:
            print("  ✓ Sequence 2 accepted")
        else:
            print("  ✗ Sequence 2 rejected")
            return False
        
        # Test 6: Statistics
        print("\n[6] Statistics...")
        stats = await sm.get_stats()
        print(f"  Sessions created: {stats['sessions_created']}")
        print(f"  Active sessions: {stats['active_sessions']}")
        print(f"  Messages ordered: {stats['messages_ordered']}")
        
        if stats['sessions_created'] == 2:
            print("  ✓ Stats correct")
        else:
            print("  ✗ Stats incorrect")
            return False
        
        # Test 7: List active sessions
        print("\n[7] List active sessions...")
        active = await sm.list_active_sessions()
        print(f"  Active count: {len(active)}")
        for sid, info in active.items():
            print(f"    - {sid[:8]}...: {info['sender_id']} -> {info['recipient_id']}")
        
        if len(active) == 2:
            print("  ✓ Correct number of active sessions")
        else:
            print("  ✗ Incorrect active count")
            return False
        
        # Test 8: Termination
        print("\n[8] Session termination...")
        result = await sm.terminate_session(session_id)
        if result:
            print("  ✓ Session terminated")
        else:
            print("  ✗ Termination failed")
            return False
        
        retrieved = await sm.get_session(session_id)
        if retrieved is None:
            print("  ✓ Session no longer accessible")
        else:
            print("  ✗ Session still accessible")
            return False
        
        print("\n" + "=" * 60)
        print("✓ All S3 UUID Session tests PASSED")
        print("=" * 60)
        return True
        
    finally:
        await sm.stop()

if __name__ == "__main__":
    success = asyncio.run(verify())
    sys.exit(0 if success else 1)
