#!/usr/bin/env python3
"""
Session Sequence Validation Tests (S8)

Tests for session-based message sequence validation:
1. Valid sequence handling
2. SEQUENCE_ERROR for replay attacks (seq < expected)
3. Message gap detection (seq > expected)
4. Backward compatibility without session_id
5. Invalid session handling

Reference: peer_service.py lines 3299-3331 for validation logic
"""

import asyncio
import sys
import os
import time
import secrets
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

# servicesディレクトリをパスに追加
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, WORKSPACE_DIR)

# インポート（複数パターン対応）
import_error_details = []
IMPORT_SUCCESS = False

try:
    from services.peer_service import PeerService, SessionManager, Session, SessionState
    from services.crypto import generate_entity_keypair
    IMPORT_SUCCESS = True
except ImportError as e1:
    import_error_details.append(f"Pattern 1 failed: {e1}")
    try:
        from peer_service import PeerService, SessionManager, Session, SessionState
        from crypto import generate_entity_keypair
        IMPORT_SUCCESS = True
    except ImportError as e2:
        import_error_details.append(f"Pattern 2 failed: {e2}")
        try:
            sys.path.insert(0, os.path.join(WORKSPACE_DIR, 'services'))
            from peer_service import PeerService, SessionManager, Session, SessionState
            from crypto import generate_entity_keypair
            IMPORT_SUCCESS = True
        except ImportError as e3:
            import_error_details.append(f"Pattern 3 failed: {e3}")
            pass

if not IMPORT_SUCCESS:
    print("❌ Import errors:")
    for detail in import_error_details:
        print(f"   - {detail}")
    raise ImportError(f"Failed to import required modules. Errors: {import_error_details}")


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def setup_keys():
    """Generate test key pairs for entities"""
    priv_a_hex, pub_a_hex = generate_entity_keypair()
    priv_b_hex, pub_b_hex = generate_entity_keypair()
    return {
        "entity_a": {"private": priv_a_hex, "public": pub_a_hex},
        "entity_b": {"private": priv_b_hex, "public": pub_b_hex}
    }


@pytest.fixture
async def peer_service(setup_keys):
    """Create a peer service instance for testing"""
    os.environ["ENTITY_PRIVATE_KEY"] = setup_keys["entity_a"]["private"]
    service = PeerService(
        entity_id="test-entity",
        port=8999,
        private_key_hex=setup_keys["entity_a"]["private"]
    )
    yield service
    # Cleanup
    await service.stop()


@pytest.fixture
async def session_manager():
    """Create a session manager for testing"""
    manager = SessionManager(default_ttl=3600)
    yield manager


@pytest.fixture
def base_message():
    """Base message template for testing"""
    return {
        "version": "1.0",
        "msg_type": "test",
        "sender_id": "peer-b",
        "payload": {"data": "test"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "nonce": secrets.token_hex(16)
    }


# =============================================================================
# Test Class: Valid Sequence Handling
# =============================================================================

class TestValidSequenceHandling:
    """Tests for valid sequence number handling"""
    
    @pytest.mark.asyncio
    async def test_first_sequence_accepted(self, peer_service, setup_keys, base_message):
        """Test that sequence number 1 is accepted as the first message"""
        # Add peer
        peer_service.add_peer("peer-b", "http://localhost:8002", 
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        # Create session
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        # Register a test handler
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send first message with sequence 1
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 1
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"
        
        # Verify session was updated
        updated_session = await peer_service.get_session_by_peer("peer-b")
        assert updated_session.expected_sequence == 2
    
    @pytest.mark.asyncio
    async def test_consecutive_sequences_accepted(self, peer_service, setup_keys, base_message):
        """Test that consecutive sequence numbers are accepted"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send messages 1, 2, 3, 4, 5
        for seq in range(1, 6):
            message = base_message.copy()
            message["session_id"] = session_id
            message["sequence_num"] = seq
            message["nonce"] = secrets.token_hex(16)
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            result = await peer_service.handle_message(message)
            assert result["status"] == "success", f"Sequence {seq} should be accepted"
        
        # Verify final expected sequence
        updated_session = await peer_service.get_session_by_peer("peer-b")
        assert updated_session.expected_sequence == 6
    
    @pytest.mark.asyncio
    async def test_large_sequence_number(self, peer_service, setup_keys, base_message):
        """Test handling of large sequence numbers"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        # Set expected sequence to large number
        session.expected_sequence = 1000
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with sequence 1000
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 1000
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"
        
        updated_session = await peer_service.get_session_by_peer("peer-b")
        assert updated_session.expected_sequence == 1001


# =============================================================================
# Test Class: Replay Attack Detection
# =============================================================================

class TestReplayAttackDetection:
    """Tests for SEQUENCE_ERROR on replay attacks (seq < expected)"""
    
    @pytest.mark.asyncio
    async def test_old_sequence_rejected(self, peer_service, setup_keys, base_message):
        """Test that old sequence numbers are rejected with SEQUENCE_ERROR"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send messages 1, 2, 3
        for seq in range(1, 4):
            message = base_message.copy()
            message["session_id"] = session_id
            message["sequence_num"] = seq
            message["nonce"] = secrets.token_hex(16)
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            result = await peer_service.handle_message(message)
            assert result["status"] == "success"
        
        # Try to replay sequence 2 (should fail)
        replay_message = base_message.copy()
        replay_message["session_id"] = session_id
        replay_message["sequence_num"] = 2
        replay_message["nonce"] = secrets.token_hex(16)
        replay_message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(replay_message)
        
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"
        assert "expected" in result
        assert "received" in result
        assert result["received"] == 2
        assert result["expected"] == 4
    
    @pytest.mark.asyncio
    async def test_sequence_zero_rejected(self, peer_service, setup_keys, base_message):
        """Test that sequence number 0 is rejected after first message"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send first message with sequence 1
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 1
        
        await peer_service.handle_message(message)
        
        # Try to send sequence 0 (should fail)
        message["sequence_num"] = 0
        message["nonce"] = secrets.token_hex(16)
        message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"
    
    @pytest.mark.asyncio
    async def test_replay_same_sequence_rejected(self, peer_service, setup_keys, base_message):
        """Test that sending the same sequence twice is rejected"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with sequence 1
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 1
        
        result = await peer_service.handle_message(message)
        assert result["status"] == "success"
        
        # Try to send sequence 1 again
        message["nonce"] = secrets.token_hex(16)
        message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"
    
    @pytest.mark.asyncio
    async def test_replay_with_different_nonce_rejected(self, peer_service, setup_keys, base_message):
        """Test that replay with different nonce is still rejected"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with sequence 1
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 1
        original_nonce = message["nonce"]
        
        result = await peer_service.handle_message(message)
        assert result["status"] == "success"
        
        # Replay with different nonce but same sequence
        replay_message = base_message.copy()
        replay_message["session_id"] = session_id
        replay_message["sequence_num"] = 1
        replay_message["nonce"] = secrets.token_hex(16)  # Different nonce
        replay_message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(replay_message)
        
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"


# =============================================================================
# Test Class: Message Gap Detection
# =============================================================================

class TestMessageGapDetection:
    """Tests for detecting message gaps (seq > expected)"""
    
    @pytest.mark.asyncio
    async def test_sequence_gap_detected(self, peer_service, setup_keys, base_message):
        """Test that sequence gaps are detected but processed"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send first message with sequence 1
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 1
        
        result = await peer_service.handle_message(message)
        assert result["status"] == "success"
        
        # Send message with sequence 10 (gap detected)
        message["sequence_num"] = 10
        message["nonce"] = secrets.token_hex(16)
        message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(message)
        
        # Gap is detected but message is still processed
        assert result["status"] == "success"
        
        # Verify expected sequence was updated to 11
        updated_session = await peer_service.get_session_by_peer("peer-b")
        assert updated_session.expected_sequence == 11
    
    @pytest.mark.asyncio
    async def test_large_gap_handling(self, peer_service, setup_keys, base_message):
        """Test handling of large sequence gaps"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with sequence 1000 (large gap from expected=1)
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 1000
        
        result = await peer_service.handle_message(message)
        
        # Large gap is detected but message is still processed
        assert result["status"] == "success"
        
        # Verify expected sequence was updated
        updated_session = await peer_service.get_session_by_peer("peer-b")
        assert updated_session.expected_sequence == 1001
    
    @pytest.mark.asyncio
    async def test_gap_then_old_sequence_rejected(self, peer_service, setup_keys, base_message):
        """Test that after a gap, old sequences are still rejected"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with sequence 100 (creates gap)
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 100
        
        await peer_service.handle_message(message)
        
        # Try to send sequence 50 (should be rejected)
        message["sequence_num"] = 50
        message["nonce"] = secrets.token_hex(16)
        message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"


# =============================================================================
# Test Class: Backward Compatibility
# =============================================================================

class TestBackwardCompatibility:
    """Tests for backward compatibility without session_id"""
    
    @pytest.mark.asyncio
    async def test_message_without_session_processed(self, peer_service, setup_keys, base_message):
        """Test that messages without session_id are processed (validation skipped)"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message without session_id and sequence_num
        message = base_message.copy()
        # No session_id or sequence_num
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_message_without_sequence_processed(self, peer_service, setup_keys, base_message):
        """Test that messages with session_id but without sequence_num are processed"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with session_id but no sequence_num
        message = base_message.copy()
        message["session_id"] = session_id
        # No sequence_num
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_message_with_sequence_without_session(self, peer_service, setup_keys, base_message):
        """Test that messages with sequence_num but without session_id are processed"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with sequence_num but no session_id
        message = base_message.copy()
        message["sequence_num"] = 1
        # No session_id
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_v1_0_protocol_with_session(self, peer_service, setup_keys, base_message):
        """Test v1.0 protocol with session and sequence validation"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with version 1.0, session_id and sequence_num
        message = base_message.copy()
        message["version"] = "1.0"
        message["session_id"] = session_id
        message["sequence_num"] = 1
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"


# =============================================================================
# Test Class: Invalid Session Handling
# =============================================================================

class TestInvalidSessionHandling:
    """Tests for handling invalid session scenarios"""
    
    @pytest.mark.asyncio
    async def test_invalid_session_id(self, peer_service, setup_keys, base_message):
        """Test that invalid session_id is handled gracefully"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with non-existent session_id
        message = base_message.copy()
        message["session_id"] = "invalid-session-id-12345"
        message["sequence_num"] = 1
        
        # Should process without sequence validation (session not found)
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_malformed_session_id(self, peer_service, setup_keys, base_message):
        """Test handling of malformed session_id"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with malformed session_id
        message = base_message.copy()
        message["session_id"] = ""
        message["sequence_num"] = 1
        
        result = await peer_service.handle_message(message)
        
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_wrong_peer_session(self, peer_service, setup_keys, base_message):
        """Test that message from wrong peer with valid session is handled"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        peer_service.add_peer("peer-c", "http://localhost:8003",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        # Create session for peer-b
        session_b = await peer_service.create_session("peer-b")
        session_id_b = session_b.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message from peer-c but with peer-b's session_id
        message = base_message.copy()
        message["sender_id"] = "peer-c"
        message["session_id"] = session_id_b
        message["sequence_num"] = 1
        
        result = await peer_service.handle_message(message)
        
        # Should process (session lookup is by sender, not session_id)
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_negative_sequence_number(self, peer_service, setup_keys, base_message):
        """Test handling of negative sequence numbers"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with negative sequence number
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = -1
        
        result = await peer_service.handle_message(message)
        
        # Negative sequence should be rejected (less than expected)
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"
    
    @pytest.mark.asyncio
    async def test_non_integer_sequence(self, peer_service, setup_keys, base_message):
        """Test handling of non-integer sequence numbers"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send message with string sequence number
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = "abc"
        
        # Should handle gracefully (may error or convert)
        try:
            result = await peer_service.handle_message(message)
            # If it doesn't crash, check response
            assert result["status"] in ["success", "error"]
        except (ValueError, TypeError):
            # Exception is acceptable for invalid input
            pass


# =============================================================================
# Test Class: Session Manager Sequence Validation
# =============================================================================

class TestSessionManagerValidation:
    """Tests for SessionManager-level sequence validation"""
    
    @pytest.mark.asyncio
    async def test_validate_received_seq_valid(self, session_manager):
        """Test validate_received_seq with valid sequence"""
        # Create session
        session = await session_manager.create_session("peer-b")
        session_id = session.session_id
        
        # Validate sequence 1
        is_valid = await session_manager.validate_received_seq(session_id, 1)
        assert is_valid is True
        
        # Validate sequence 2
        is_valid = await session_manager.validate_received_seq(session_id, 2)
        assert is_valid is True
    
    @pytest.mark.asyncio
    async def test_validate_received_seq_duplicate(self, session_manager):
        """Test validate_received_seq with duplicate sequence"""
        session = await session_manager.create_session("peer-b")
        session_id = session.session_id
        
        # Validate sequence 1
        is_valid = await session_manager.validate_received_seq(session_id, 1)
        assert is_valid is True
        
        # Try to validate sequence 1 again (duplicate)
        is_valid = await session_manager.validate_received_seq(session_id, 1)
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_received_seq_old(self, session_manager):
        """Test validate_received_seq with old sequence"""
        session = await session_manager.create_session("peer-b")
        session_id = session.session_id
        
        # Validate sequence 100
        is_valid = await session_manager.validate_received_seq(session_id, 100)
        assert is_valid is True
        
        # Try to validate very old sequence (outside window)
        is_valid = await session_manager.validate_received_seq(session_id, 1)
        assert is_valid is False
    
    @pytest.mark.asyncio
    async def test_validate_received_seq_invalid_session(self, session_manager):
        """Test validate_received_seq with invalid session"""
        is_valid = await session_manager.validate_received_seq("invalid-session", 1)
        assert is_valid is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestSequenceValidationIntegration:
    """Integration tests for sequence validation"""
    
    @pytest.mark.asyncio
    async def test_full_session_lifecycle(self, peer_service, setup_keys, base_message):
        """Test full session lifecycle with sequence validation"""
        peer_service.add_peer("peer-b", "http://localhost:8002",
                             public_key_hex=setup_keys["entity_b"]["public"])
        
        session = await peer_service.create_session("peer-b")
        session_id = session.session_id
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send 10 messages with proper sequencing
        for seq in range(1, 11):
            message = base_message.copy()
            message["session_id"] = session_id
            message["sequence_num"] = seq
            message["nonce"] = secrets.token_hex(16)
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
            
            result = await peer_service.handle_message(message)
            assert result["status"] == "success", f"Sequence {seq} failed"
        
        # Try to replay sequence 5
        replay = base_message.copy()
        replay["session_id"] = session_id
        replay["sequence_num"] = 5
        replay["nonce"] = secrets.token_hex(16)
        replay["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(replay)
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"
        
        # Continue with sequence 11
        message = base_message.copy()
        message["session_id"] = session_id
        message["sequence_num"] = 11
        message["nonce"] = secrets.token_hex(16)
        message["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        result = await peer_service.handle_message(message)
        assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_multiple_peers_sequences(self, peer_service, setup_keys, base_message):
        """Test sequence validation with multiple peers"""
        # Add multiple peers
        for peer_id in ["peer-b", "peer-c", "peer-d"]:
            peer_service.add_peer(peer_id, f"http://localhost:8000",
                                 public_key_hex=setup_keys["entity_b"]["public"])
            await peer_service.create_session(peer_id)
        
        async def test_handler(message):
            return {"status": "success", "handled": True}
        
        peer_service.register_message_handler("test", test_handler)
        
        # Send messages to each peer with different sequences
        for i, peer_id in enumerate(["peer-b", "peer-c", "peer-d"]):
            session = await peer_service.get_session_by_peer(peer_id)
            
            message = base_message.copy()
            message["sender_id"] = peer_id
            message["session_id"] = session.session_id
            message["sequence_num"] = 1
            
            result = await peer_service.handle_message(message)
            assert result["status"] == "success"
            
            # Each peer should have independent sequence tracking
            updated_session = await peer_service.get_session_by_peer(peer_id)
            assert updated_session.expected_sequence == 2


# =============================================================================
# Main entry point for standalone execution
# =============================================================================

async def run_all_tests():
    """Run all tests standalone (without pytest)"""
    print("\n" + "=" * 70)
    print("Session Sequence Validation Tests (S8)")
    print("=" * 70)
    
    keys = {
        "entity_a": {"private": generate_entity_keypair()[0], "public": generate_entity_keypair()[1]},
        "entity_b": {"private": generate_entity_keypair()[0], "public": generate_entity_keypair()[1]}
    }
    
    # Re-generate keys properly
    priv_a, pub_a = generate_entity_keypair()
    priv_b, pub_b = generate_entity_keypair()
    keys = {
        "entity_a": {"private": priv_a, "public": pub_a},
        "entity_b": {"private": priv_b, "public": pub_b}
    }
    
    def base_msg():
        return {
            "version": "1.0",
            "msg_type": "test",
            "sender_id": "peer-b",
            "payload": {"data": "test"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": secrets.token_hex(16)
        }
    
    test_results = []
    
    # Test 1: Valid sequence handling
    print("\n--- Test 1: Valid Sequence Handling ---")
    try:
        os.environ["ENTITY_PRIVATE_KEY"] = keys["entity_a"]["private"]
        service = PeerService(
            entity_id="test-entity",
            port=8999,
            private_key_hex=keys["entity_a"]["private"]
        )
        service.add_peer("peer-b", "http://localhost:8002",
                        public_key_hex=keys["entity_b"]["public"])
        session = await service.create_session("peer-b")
        
        async def handler(msg):
            return {"status": "success"}
        service.register_message_handler("test", handler)
        
        msg = base_msg()
        msg["session_id"] = session.session_id
        msg["sequence_num"] = 1
        
        result = await service.handle_message(msg)
        assert result["status"] == "success"
        
        updated = await service.get_session_by_peer("peer-b")
        assert updated.expected_sequence == 2
        
        print("✓ Valid sequence handling test passed")
        test_results.append(("Valid sequence", True))
        await service.stop()
    except Exception as e:
        print(f"✗ Valid sequence handling test failed: {e}")
        test_results.append(("Valid sequence", False))
    
    # Test 2: Replay attack detection
    print("\n--- Test 2: Replay Attack Detection ---")
    try:
        os.environ["ENTITY_PRIVATE_KEY"] = keys["entity_a"]["private"]
        service = PeerService(
            entity_id="test-entity-2",
            port=8998,
            private_key_hex=keys["entity_a"]["private"]
        )
        service.add_peer("peer-b", "http://localhost:8002",
                        public_key_hex=keys["entity_b"]["public"])
        session = await service.create_session("peer-b")
        
        async def handler(msg):
            return {"status": "success"}
        service.register_message_handler("test", handler)
        
        # Send sequence 1
        msg = base_msg()
        msg["session_id"] = session.session_id
        msg["sequence_num"] = 1
        await service.handle_message(msg)
        
        # Send sequence 2
        msg = base_msg()
        msg["session_id"] = session.session_id
        msg["sequence_num"] = 2
        await service.handle_message(msg)
        
        # Try to replay sequence 1
        msg = base_msg()
        msg["session_id"] = session.session_id
        msg["sequence_num"] = 1
        result = await service.handle_message(msg)
        
        assert result["status"] == "error"
        assert result.get("error_code") == "SEQUENCE_ERROR"
        
        print("✓ Replay attack detection test passed")
        test_results.append(("Replay detection", True))
        await service.stop()
    except Exception as e:
        print(f"✗ Replay attack detection test failed: {e}")
        test_results.append(("Replay detection", False))
    
    # Test 3: Message gap detection
    print("\n--- Test 3: Message Gap Detection ---")
    try:
        os.environ["ENTITY_PRIVATE_KEY"] = keys["entity_a"]["private"]
        service = PeerService(
            entity_id="test-entity-3",
            port=8997,
            private_key_hex=keys["entity_a"]["private"]
        )
        service.add_peer("peer-b", "http://localhost:8002",
                        public_key_hex=keys["entity_b"]["public"])
        session = await service.create_session("peer-b")
        
        async def handler(msg):
            return {"status": "success"}
        service.register_message_handler("test", handler)
        
        # Send sequence 1
        msg = base_msg()
        msg["session_id"] = session.session_id
        msg["sequence_num"] = 1
        await service.handle_message(msg)
        
        # Send sequence 10 (gap)
        msg = base_msg()
        msg["session_id"] = session.session_id
        msg["sequence_num"] = 10
        result = await service.handle_message(msg)
        
        assert result["status"] == "success"
        
        updated = await service.get_session_by_peer("peer-b")
        assert updated.expected_sequence == 11
        
        print("✓ Message gap detection test passed")
        test_results.append(("Gap detection", True))
        await service.stop()
    except Exception as e:
        print(f"✗ Message gap detection test failed: {e}")
        test_results.append(("Gap detection", False))
    
    # Test 4: Backward compatibility
    print("\n--- Test 4: Backward Compatibility ---")
    try:
        os.environ["ENTITY_PRIVATE_KEY"] = keys["entity_a"]["private"]
        service = PeerService(
            entity_id="test-entity-4",
            port=8996,
            private_key_hex=keys["entity_a"]["private"]
        )
        service.add_peer("peer-b", "http://localhost:8002",
                        public_key_hex=keys["entity_b"]["public"])
        
        async def handler(msg):
            return {"status": "success"}
        service.register_message_handler("test", handler)
        
        # Send message without session_id
        msg = base_msg()
        result = await service.handle_message(msg)
        
        assert result["status"] == "success"
        
        print("✓ Backward compatibility test passed")
        test_results.append(("Backward compatibility", True))
        await service.stop()
    except Exception as e:
        print(f"✗ Backward compatibility test failed: {e}")
        test_results.append(("Backward compatibility", False))
    
    # Test 5: Invalid session handling
    print("\n--- Test 5: Invalid Session Handling ---")
    try:
        os.environ["ENTITY_PRIVATE_KEY"] = keys["entity_a"]["private"]
        service = PeerService(
            entity_id="test-entity-5",
            port=8995,
            private_key_hex=keys["entity_a"]["private"]
        )
        service.add_peer("peer-b", "http://localhost:8002",
                        public_key_hex=keys["entity_b"]["public"])
        
        async def handler(msg):
            return {"status": "success"}
        service.register_message_handler("test", handler)
        
        # Send message with invalid session_id
        msg = base_msg()
        msg["session_id"] = "invalid-session-id"
        msg["sequence_num"] = 1
        result = await service.handle_message(msg)
        
        assert result["status"] == "success"
        
        print("✓ Invalid session handling test passed")
        test_results.append(("Invalid session", True))
        await service.stop()
    except Exception as e:
        print(f"✗ Invalid session handling test failed: {e}")
        test_results.append(("Invalid session", False))
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    passed = sum(1 for _, result in test_results if result)
    total = len(test_results)
    print(f"Passed: {passed}/{total}")
    
    for name, result in test_results:
        status = "✓" if result else "✗"
        print(f"  {status} {name}")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
