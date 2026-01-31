#!/usr/bin/env python3
"""
Session State Machine Tests

Tests for session state transitions and validation.
Covers all 5 session states and their transitions.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, patch

# Import session classes
import sys
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

try:
    from peer_service import Session, SessionState, SessionManager
except ImportError:
    from services.peer_service import Session, SessionState, SessionManager


class TestSessionStateTransitions:
    """Test session state machine transitions"""
    
    def test_initial_state(self):
        """Test session starts in INITIAL state"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.INITIAL
        )
        assert session.state == SessionState.INITIAL
        assert session.is_handshake_complete() == False
        assert session.can_receive_messages() == False
    
    def test_handshake_sent_transition(self):
        """Test transition from INITIAL to HANDSHAKE_SENT"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.INITIAL
        )
        
        # Valid transition
        success, error = session.transition_to(SessionState.HANDSHAKE_SENT)
        assert success == True
        assert session.state == SessionState.HANDSHAKE_SENT
    
    def test_handshake_received_transition(self):
        """Test transition to HANDSHAKE_RECEIVED"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.INITIAL
        )
        
        success, error = session.transition_to(SessionState.HANDSHAKE_RECEIVED)
        assert success == True
        assert session.state == SessionState.HANDSHAKE_RECEIVED
    
    def test_established_transition(self):
        """Test transition to ESTABLISHED state"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.HANDSHAKE_SENT
        )
        
        success, error = session.transition_to(SessionState.ESTABLISHED)
        assert success == True
        assert session.state == SessionState.ESTABLISHED
        assert session.is_handshake_complete() == True
        assert session.can_receive_messages() == True
    
    def test_closed_transition(self):
        """Test transition to CLOSED state"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.ESTABLISHED
        )
        
        success, error = session.transition_to(SessionState.CLOSED)
        assert success == True
        assert session.state == SessionState.CLOSED
        assert session.can_receive_messages() == False
    
    def test_invalid_transition(self):
        """Test invalid state transition is rejected"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.INITIAL
        )
        
        # Cannot go directly to ESTABLISHED from INITIAL
        success, error = session.transition_to(SessionState.ESTABLISHED)
        assert success == False
        assert error is not None
        assert session.state == SessionState.INITIAL


class TestSessionExpiration:
    """Test session expiration logic"""
    
    def test_session_not_expired(self):
        """Test active session is not expired"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.ESTABLISHED,
            last_activity=datetime.now(timezone.utc)
        )
        
        assert session.is_expired(max_age_seconds=3600) == False
    
    def test_session_expired(self):
        """Test old session is expired"""
        from datetime import timedelta
        
        old_time = datetime.now(timezone.utc) - timedelta(hours=2)
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.ESTABLISHED,
            last_activity=old_time
        )
        
        assert session.is_expired(max_age_seconds=3600) == True
    
    def test_handshake_expiration(self):
        """Test handshake timeout"""
        from datetime import timedelta
        
        old_time = datetime.now(timezone.utc) - timedelta(minutes=10)
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            state=SessionState.HANDSHAKE_SENT,
            handshake_sent_at=old_time
        )
        
        assert session.is_handshake_expired(max_handshake_seconds=300) == True


class TestSessionSequence:
    """Test sequence number management"""
    
    def test_sequence_increment(self):
        """Test sequence number auto-increment"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            sequence_num=100
        )
        
        seq = session.increment_sequence()
        assert seq == 101
        assert session.sequence_num == 101
    
    def test_expected_sequence_update(self):
        """Test expected sequence tracking"""
        session = Session(
            session_id="test-123",
            peer_id="peer-a",
            expected_sequence=50
        )
        
        session.expected_sequence = 51
        assert session.expected_sequence == 51


class TestSessionManager:
    """Test SessionManager operations"""
    
    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test session creation"""
        manager = SessionManager()
        
        session = await manager.create_session(
            peer_id="peer-a",
            peer_public_key=b"key"
        )
        
        assert session is not None
        assert session.peer_id == "peer-a"
        assert session.state == SessionState.INITIAL
    
    @pytest.mark.asyncio
    async def test_get_session(self):
        """Test session retrieval"""
        manager = SessionManager()
        
        session = await manager.create_session(
            peer_id="peer-a",
            peer_public_key=b"key"
        )
        
        retrieved = await manager.get_session(session.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
    
    @pytest.mark.asyncio
    async def test_get_session_by_peer(self):
        """Test session lookup by peer ID"""
        manager = SessionManager()
        
        session = await manager.create_session(
            peer_id="peer-a",
            peer_public_key=b"key"
        )
        
        retrieved = await manager.get_session_by_peer("peer-a")
        assert retrieved is not None
        assert retrieved.peer_id == "peer-a"
    
    @pytest.mark.asyncio
    async def test_update_session_state(self):
        """Test session state update"""
        manager = SessionManager()
        
        session = await manager.create_session(
            peer_id="peer-a",
            peer_public_key=b"key"
        )
        
        success = await manager.update_session_state(
            session.session_id,
            SessionState.ESTABLISHED
        )
        
        assert success == True
        
        updated = await manager.get_session(session.session_id)
        assert updated.state == SessionState.ESTABLISHED
    
    @pytest.mark.asyncio
    async def test_terminate_session(self):
        """Test session termination"""
        manager = SessionManager()
        
        session = await manager.create_session(
            peer_id="peer-a",
            peer_public_key=b"key"
        )
        
        success = await manager.terminate_session(session.session_id)
        assert success == True
        
        # Session should be closed
        retrieved = await manager.get_session(session.session_id)
        assert retrieved.state == SessionState.CLOSED
    
    @pytest.mark.asyncio
    async def test_cleanup_expired(self):
        """Test expired session cleanup"""
        from datetime import timedelta
        
        manager = SessionManager()
        
        # Create session with old activity
        session = await manager.create_session(
            peer_id="peer-a",
            peer_public_key=b"key"
        )
        session.last_activity = datetime.now(timezone.utc) - timedelta(hours=2)
        
        # Cleanup should remove expired session
        count = await manager.cleanup_expired()
        assert count == 1
        
        # Session should be gone
        retrieved = await manager.get_session(session.session_id)
        assert retrieved is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
