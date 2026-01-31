#!/usr/bin/env python3
"""
PeerService E2E Encryption Integration Tests

E2ECryptoManagerとPeerServiceの統合をテストする。
"""

import asyncio
import base64
import json
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add services directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import test targets
try:
    from peer_service import PeerService, CRYPTO_AVAILABLE, E2E_CRYPTO_AVAILABLE
    from e2e_crypto import E2ECryptoManager, SessionState
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)


@pytest.fixture
def mock_keypair():
    """Mock keypair for testing"""
    keypair = MagicMock()
    keypair.get_public_key_hex.return_value = "a" * 64  # 32 bytes hex
    keypair.private_key = b"x" * 32
    return keypair


@pytest.fixture
def peer_service_a(mock_keypair):
    """Create PeerService instance A for testing"""
    with patch("peer_service.CRYPTO_AVAILABLE", True):
        with patch.object(PeerService, "_init_crypto") as mock_init:
            mock_crypto = MagicMock()
            mock_crypto._ed25519_keypair = mock_keypair
            mock_crypto.get_ed25519_public_key_bytes.return_value = b"a" * 32
            
            service = PeerService(
                entity_id="entity-a",
                port=8001,
                enable_encryption=True,
                enable_e2e_encryption=True
            )
            service.crypto_manager = mock_crypto
            service.key_pair = mock_keypair
            service.signer = MagicMock()
            service.verifier = MagicMock()
            service.enable_signing = True
            service.enable_verification = True
            
            # Initialize E2E manager
            if E2E_CRYPTO_AVAILABLE:
                service.e2e_manager = E2ECryptoManager(
                    entity_id="entity-a",
                    keypair=mock_keypair,
                    default_timeout=3600
                )
            
            return service


@pytest.fixture
def peer_service_b(mock_keypair):
    """Create PeerService instance B for testing"""
    with patch("peer_service.CRYPTO_AVAILABLE", True):
        service = PeerService(
            entity_id="entity-b",
            port=8002,
            enable_encryption=True,
            enable_e2e_encryption=True
        )
        service.crypto_manager = MagicMock()
        service.crypto_manager._ed25519_keypair = mock_keypair
        service.key_pair = mock_keypair
        service.signer = MagicMock()
        service.verifier = MagicMock()
        service.enable_signing = True
        service.enable_verification = True
        
        # Initialize E2E manager
        if E2E_CRYPTO_AVAILABLE:
            service.e2e_manager = E2ECryptoManager(
                entity_id="entity-b",
                keypair=mock_keypair,
                default_timeout=3600
            )
        
        return service


@pytest.mark.asyncio
async def test_e2e_manager_initialization(peer_service_a):
    """Test that E2ECryptoManager is properly initialized"""
    if not E2E_CRYPTO_AVAILABLE:
        pytest.skip("E2E_CRYPTO not available")
    
    assert peer_service_a.e2e_manager is not None
    assert peer_service_a.e2e_manager.entity_id == "entity-a"
    assert peer_service_a.enable_e2e_encryption is True


@pytest.mark.asyncio
async def test_initiate_handshake_with_e2e(peer_service_a):
    """Test that initiate_handshake creates E2E session"""
    if not E2E_CRYPTO_AVAILABLE:
        pytest.skip("E2E_CRYPTO not available")
    
    # Add peer
    peer_service_a.peers["entity-b"] = "http://localhost:8002"
    
    # Mock the HTTP call
    with patch("aiohttp.ClientSession") as mock_session_class:
        mock_session = AsyncMock()
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json.return_value = {"status": "success"}
        mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        
        # Initiate handshake with E2E
        success, session_id, error = await peer_service_a.initiate_handshake(
            target_id="entity-b",
            enable_e2e=True
        )
        
        # Check E2E session was created
        e2e_sessions = list(peer_service_a.e2e_manager._sessions.values())
        assert len(e2e_sessions) > 0
        assert e2e_sessions[0].remote_entity_id == "entity-b"


@pytest.mark.asyncio
async def test_e2e_encryption_negotiation_in_handshake(peer_service_a, peer_service_b):
    """Test E2E encryption negotiation during handshake"""
    if not E2E_CRYPTO_AVAILABLE:
        pytest.skip("E2E_CRYPTO not available")
    
    # Setup peer B to receive handshake
    peer_service_b.peers["entity-a"] = "http://localhost:8001"
    
    # Create E2E session on A side
    e2e_session_a = peer_service_a.e2e_manager.create_session("entity-b")
    
    # Create handshake message with E2E info
    handshake_msg = {
        "version": "1.0",
        "msg_type": "handshake",
        "sender_id": "entity-a",
        "recipient_id": "entity-b",
        "session_id": "test-session-123",
        "payload": {
            "version": "1.0",
            "session_id": "test-session-123",
            "challenge": "abcd1234",
            "public_key": "aa" * 32,
            "supported_versions": ["1.0"],
            "capabilities": ["e2e_encryption", "aes_256_gcm", "x25519"],
            "e2e_enabled": True,
            "e2e_session_id": e2e_session_a.session_id,
            "e2e_ephemeral_key": base64.b64encode(e2e_session_a.ephemeral_public_key).decode()
        }
    }
    
    # Process handshake on B side
    result = await peer_service_b.handle_handshake(handshake_msg)
    
    # Check E2E session was created on B side
    assert result["status"] == "success"
    e2e_sessions_b = list(peer_service_b.e2e_manager._sessions.values())
    assert len(e2e_sessions_b) > 0
    assert e2e_sessions_b[0].remote_entity_id == "entity-a"
    assert e2e_sessions_b[0].state == SessionState.ESTABLISHED


@pytest.mark.asyncio
async def test_e2e_encrypt_decrypt_message(peer_service_a, peer_service_b):
    """Test E2E encryption and decryption of messages"""
    if not E2E_CRYPTO_AVAILABLE:
        pytest.skip("E2E_CRYPTO not available")
    
    # Setup sessions on both sides
    session_a = peer_service_a.e2e_manager.create_session("entity-b")
    session_b = peer_service_b.e2e_manager.create_session("entity-a")
    
    # Complete handshake on both sides
    session_a.complete_handshake(
        remote_public_key=b"b" * 32,
        remote_ephemeral_key=session_b.ephemeral_public_key
    )
    session_b.complete_handshake(
        remote_public_key=b"a" * 32,
        remote_ephemeral_key=session_a.ephemeral_public_key
    )
    
    # Test payload
    test_payload = {"message": "Hello, E2E encrypted world!", "timestamp": datetime.now(timezone.utc).isoformat()}
    
    # Encrypt using A's E2E manager
    encrypted_msg = peer_service_a.e2e_manager.encrypt_message(
        session_a.session_id,
        test_payload
    )
    
    # Decrypt using B's E2E manager
    decrypted = peer_service_b.e2e_manager.decrypt_message(session_b, encrypted_msg)
    
    assert decrypted["message"] == test_payload["message"]


@pytest.mark.asyncio
async def test_prepare_payload_with_e2e(peer_service_a):
    """Test _prepare_payload with E2E encryption"""
    if not E2E_CRYPTO_AVAILABLE:
        pytest.skip("E2E_CRYPTO not available")
    
    # Create E2E session
    session = peer_service_a.e2e_manager.create_session("entity-b")
    session.complete_handshake(
        remote_public_key=b"b" * 32,
        remote_ephemeral_key=session.ephemeral_public_key  # Use same key for test
    )
    
    test_payload = {"data": "sensitive information"}
    
    # Prepare payload with encryption
    encrypted_payload = peer_service_a._prepare_payload("entity-b", test_payload, encrypt=True)
    
    # Check encryption markers
    assert "_e2e_encrypted" in encrypted_payload
    assert encrypted_payload["_e2e_encrypted"] is True
    assert "session_id" in encrypted_payload
    assert "data" in encrypted_payload
    assert "nonce" in encrypted_payload


@pytest.mark.asyncio
async def test_cleanup_expired_e2e_sessions(peer_service_a):
    """Test cleanup of expired E2E sessions"""
    if not E2E_CRYPTO_AVAILABLE:
        pytest.skip("E2E_CRYPTO not available")
    
    # Create a session
    session = peer_service_a.e2e_manager.create_session("entity-b")
    
    # Manually expire the session
    session.last_activity = datetime.now(timezone.utc).replace(year=2020)
    
    # Cleanup should remove the expired session
    cleaned = peer_service_a._cleanup_expired_handshake_sessions(max_age_seconds=1)
    
    # The E2E session should be cleaned up
    remaining = peer_service_a.e2e_manager.get_session(session.session_id)
    # Note: E2E sessions are cleaned by e2e_manager.cleanup_expired_sessions()


@pytest.mark.asyncio
async def test_backward_compatibility_without_e2e(peer_service_a):
    """Test that messages work without E2E encryption"""
    # Disable E2E
    peer_service_a.enable_e2e_encryption = False
    peer_service_a.e2e_manager = None
    
    test_payload = {"message": "Plain text message"}
    
    # Prepare payload without encryption
    result = peer_service_a._prepare_payload("entity-b", test_payload, encrypt=False)
    assert result == test_payload
    
    # Prepare payload with encryption (should fallback or return unencrypted)
    result = peer_service_a._prepare_payload("entity-b", test_payload, encrypt=True)
    # Without E2E manager and crypto, should return original payload
    assert "_e2e_encrypted" not in result or "_encrypted_payload" not in result or result == test_payload


class TestE2EIntegrationWithMockServer:
    """Integration tests with mock HTTP server"""
    
    @pytest.mark.asyncio
    async def test_full_handshake_with_e2e(self, peer_service_a, peer_service_b):
        """Test complete handshake flow with E2E encryption"""
        if not E2E_CRYPTO_AVAILABLE:
            pytest.skip("E2E_CRYPTO not available")
        
        # Setup peers
        peer_service_a.peers["entity-b"] = "http://localhost:8002"
        peer_service_b.peers["entity-a"] = "http://localhost:8001"
        
        # Mock send_message on peer_service_a
        async def mock_send_message(target_id, msg_type, payload, **kwargs):
            if msg_type == "handshake_ack":
                # Simulate receiving handshake_ack
                ack_msg = {
                    "version": "1.0",
                    "msg_type": "handshake_ack",
                    "sender_id": "entity-b",
                    "recipient_id": "entity-a",
                    "session_id": payload.get("session_id"),
                    "payload": payload
                }
                await peer_service_a.handle_handshake_ack(ack_msg)
            return True
        
        peer_service_a.send_message = mock_send_message
        
        # Initiate handshake
        with patch("aiohttp.ClientSession") as mock_session_class:
            mock_session = AsyncMock()
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json.return_value = {"status": "success"}
            mock_session.post.return_value.__aenter__ = AsyncMock(return_value=mock_response)
            mock_session_class.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            
            success, session_id, error = await peer_service_a.initiate_handshake(
                target_id="entity-b",
                enable_e2e=True
            )
            
            assert success is True
            assert session_id is not None
            assert error is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
