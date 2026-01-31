#!/usr/bin/env python3
"""
HandshakeManager Integration Test Suite

v1.1 Protocol 6-Step Handshake Integration Tests

Tests the complete handshake flow:
1. handshake_init (A -> B)
2. handshake_init_ack (B -> A)
3. challenge_response (A -> B)
4. session_established (B -> A)
5. session_confirm (A -> B)
6. ready (B -> A)

Integration with SessionManager for session key management.
"""

import asyncio
import sys
import os
import secrets
from datetime import datetime, timezone, timedelta

# Path setup
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, WORKSPACE_DIR)

# Imports
try:
    from services.handshake_manager import (
        HandshakeManager, HandshakeSession, HandshakeState,
        HandshakeError, HandshakeConfig, create_handshake_manager
    )
    from services.session_manager import SessionManager, SessionState
    print("✅ Imported using package pattern (services.xxx)")
    IMPORT_SUCCESS = True
except ImportError as e1:
    try:
        from handshake_manager import (
            HandshakeManager, HandshakeSession, HandshakeState,
            HandshakeError, HandshakeConfig, create_handshake_manager
        )
        from session_manager import SessionManager, SessionState
        print("✅ Imported using direct pattern (xxx)")
        IMPORT_SUCCESS = True
    except ImportError as e2:
        print(f"❌ Import failed: {e1}, {e2}")
        IMPORT_SUCCESS = False


def generate_test_keypair():
    """Generate Ed25519 test keypair"""
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        return (
            private_key.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()
            ),
            public_key.public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
        )
    except Exception as e:
        print(f"Failed to generate keypair: {e}")
        return None, None


# Import serialization for key generation
try:
    from cryptography.hazmat.primitives import serialization
except ImportError:
    serialization = None


class TestHandshakeIntegration:
    """Integration test suite for HandshakeManager"""
    
    def __init__(self):
        self.alice_keys = None
        self.bob_keys = None
        self.alice_manager = None
        self.bob_manager = None
        self.alice_session_mgr = None
        self.bob_session_mgr = None
        self.handshake_complete_alice = False
        self.handshake_complete_bob = False
        self.session_key_alice = None
        self.session_key_bob = None
    
    async def setup(self):
        """Setup test environment"""
        print("\n[SETUP] Initializing test environment...")
        
        if not IMPORT_SUCCESS:
            raise RuntimeError("Import failed, cannot run tests")
        
        # Generate keypairs for Alice and Bob
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives import serialization
            
            # Alice's keys
            alice_priv = Ed25519PrivateKey.generate()
            self.alice_keys = {
                'private': alice_priv.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption()
                ),
                'public': alice_priv.public_key().public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
            }
            
            # Bob's keys
            bob_priv = Ed25519PrivateKey.generate()
            self.bob_keys = {
                'private': bob_priv.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption()
                ),
                'public': bob_priv.public_key().public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                )
            }
            
            print(f"  Alice PK: {self.alice_keys['public'].hex()[:32]}...")
            print(f"  Bob PK:   {self.bob_keys['public'].hex()[:32]}...")
            
        except Exception as e:
            raise RuntimeError(f"Failed to generate test keys: {e}")
        
        # Create session managers
        self.alice_session_mgr = SessionManager(entity_id="alice")
        self.bob_session_mgr = SessionManager(entity_id="bob")
        
        # Create handshake managers
        self.alice_manager = HandshakeManager(
            entity_id="alice",
            ed25519_private_key=self.alice_keys['private'],
            session_manager=self.alice_session_mgr,
            config=HandshakeConfig(handshake_timeout=60, challenge_timeout=30)
        )
        
        self.bob_manager = HandshakeManager(
            entity_id="bob",
            ed25519_private_key=self.bob_keys['private'],
            session_manager=self.bob_session_mgr,
            config=HandshakeConfig(handshake_timeout=60, challenge_timeout=30)
        )
        
        # Set completion callbacks
        self.alice_manager.set_callbacks(
            on_complete=self._on_alice_complete,
            on_error=self._on_alice_error
        )
        self.bob_manager.set_callbacks(
            on_complete=self._on_bob_complete,
            on_error=self._on_bob_error
        )
        
        print("  ✓ Setup complete")
    
    async def _on_alice_complete(self, peer_id: str, session_key: bytes):
        """Callback for Alice handshake completion"""
        self.handshake_complete_alice = True
        self.session_key_alice = session_key
        print(f"  [Alice] Handshake complete with {peer_id}")
    
    async def _on_bob_complete(self, peer_id: str, session_key: bytes):
        """Callback for Bob handshake completion"""
        self.handshake_complete_bob = True
        self.session_key_bob = session_key
        print(f"  [Bob] Handshake complete with {peer_id}")
    
    async def _on_alice_error(self, peer_id: str, error: HandshakeError):
        """Callback for Alice handshake error"""
        print(f"  [Alice] Handshake error with {peer_id}: {error.value}")
    
    async def _on_bob_error(self, peer_id: str, error: HandshakeError):
        """Callback for Bob handshake error"""
        print(f"  [Bob] Handshake error with {peer_id}: {error.value}")
    
    async def test_complete_6step_handshake(self):
        """Test complete 6-step handshake flow"""
        print("\n" + "=" * 70)
        print("TEST: Complete 6-Step Handshake Flow")
        print("=" * 70)
        
        # Step 1: Alice initiates handshake
        print("\n[Step 1] Alice -> Bob: handshake_init")
        msg_init = await self.alice_manager.initiate_handshake("bob")
        assert msg_init is not None, "handshake_init should not be None"
        assert msg_init["type"] == "handshake_init"
        assert msg_init["entity_id"] == "alice"
        assert "ed25519_pubkey" in msg_init
        assert "x25519_pubkey" in msg_init
        assert "signature" in msg_init
        session_id = msg_init["session_id"]
        print(f"  ✓ Session ID: {session_id}")
        print(f"  ✓ State: HANDSHAKE_INIT_SENT")
        
        # Step 2: Bob responds with handshake_init_ack
        print("\n[Step 2] Bob -> Alice: handshake_init_ack")
        msg_ack = await self.bob_manager.handle_handshake_init(msg_init)
        assert msg_ack is not None, "handshake_init_ack should not be None"
        assert msg_ack["type"] == "handshake_init_ack"
        assert msg_ack["entity_id"] == "bob"
        assert "challenge" in msg_ack
        assert "signature" in msg_ack
        print(f"  ✓ Challenge sent")
        print(f"  ✓ State: HANDSHAKE_ACK_RECEIVED")
        
        # Step 3: Alice responds with challenge_response
        print("\n[Step 3] Alice -> Bob: challenge_response")
        msg_response = await self.alice_manager.handle_handshake_init_ack(msg_ack)
        assert msg_response is not None, "challenge_response should not be None"
        assert msg_response["type"] == "challenge_response"
        assert "challenge_signature" in msg_response
        assert "signature" in msg_response
        print(f"  ✓ Challenge response signed")
        print(f"  ✓ State: CHALLENGE_SENT")
        
        # Step 4: Bob sends session_established
        print("\n[Step 4] Bob -> Alice: session_established")
        msg_established = await self.bob_manager.handle_challenge_response(msg_response)
        assert msg_established is not None, "session_established should not be None"
        assert msg_established["type"] == "session_established"
        assert "confirmation" in msg_established
        print(f"  ✓ Session confirmed")
        print(f"  ✓ State: SESSION_ESTABLISHED")
        
        # Step 5: Alice sends session_confirm
        print("\n[Step 5] Alice -> Bob: session_confirm")
        msg_confirm = await self.alice_manager.handle_session_established(msg_established)
        assert msg_confirm is not None, "session_confirm should not be None"
        assert msg_confirm["type"] == "session_confirm"
        print(f"  ✓ Session confirmed by Alice")
        print(f"  ✓ State: SESSION_CONFIRMED")
        
        # Step 6: Bob sends ready
        print("\n[Step 6] Bob -> Alice: ready")
        msg_ready = await self.bob_manager.handle_session_confirm(msg_confirm)
        assert msg_ready is not None, "ready should not be None"
        assert msg_ready["type"] == "ready"
        print(f"  ✓ Ready signal sent")
        print(f"  ✓ State: READY")
        
        # Alice handles ready
        success = await self.alice_manager.handle_ready(msg_ready)
        assert success, "Alice should handle ready successfully"
        
        # Verify both sides completed
        print("\n[VERIFICATION]")
        assert self.handshake_complete_alice, "Alice handshake should be complete"
        assert self.handshake_complete_bob, "Bob handshake should be complete"
        print("  ✓ Both callbacks triggered")
        
        # Verify session keys match
        assert self.session_key_alice is not None, "Alice should have session key"
        assert self.session_key_bob is not None, "Bob should have session key"
        assert self.session_key_alice == self.session_key_bob, "Session keys should match!"
        print(f"  ✓ Session keys match: {self.session_key_alice.hex()[:32]}...")
        
        # Verify sessions are in READY state
        alice_session = self.alice_manager.get_session_for_peer("bob")
        bob_session = self.bob_manager.get_session_for_peer("alice")
        assert alice_session.state == HandshakeState.READY
        assert bob_session.state == HandshakeState.READY
        print("  ✓ Both sessions in READY state")
        
        # Verify SessionManager has the sessions
        alice_sm_session = self.alice_session_mgr.get_session(session_id)
        bob_sm_session = self.bob_session_mgr.get_session(session_id)
        assert alice_sm_session is not None, "SessionManager should have Alice's session"
        assert bob_sm_session is not None, "SessionManager should have Bob's session"
        print("  ✓ Sessions registered in SessionManager")
        
        print("\n✅ 6-Step Handshake Test PASSED")
        return True
    
    async def test_invalid_signature_rejection(self):
        """Test rejection of messages with invalid signatures"""
        print("\n" + "=" * 70)
        print("TEST: Invalid Signature Rejection")
        print("=" * 70)
        
        # Start handshake
        msg_init = await self.alice_manager.initiate_handshake("bob")
        
        # Tamper with signature
        msg_init["signature"] = secrets.token_hex(64)
        
        # Bob should reject
        msg_ack = await self.bob_manager.handle_handshake_init(msg_init)
        assert msg_ack is None, "Should reject invalid signature"
        
        print("  ✓ Invalid signature correctly rejected")
        print("\n✅ Invalid Signature Test PASSED")
        return True
    
    async def test_challenge_expiration(self):
        """Test challenge timeout handling"""
        print("\n" + "=" * 70)
        print("TEST: Challenge Expiration")
        print("=" * 70)
        
        # Create manager with very short timeout
        short_config = HandshakeConfig(challenge_timeout=0)  # Immediate timeout
        alice_short = HandshakeManager(
            entity_id="alice",
            ed25519_private_key=self.alice_keys['private'],
            config=short_config
        )
        bob_short = HandshakeManager(
            entity_id="bob",
            ed25519_private_key=self.bob_keys['private'],
            config=short_config
        )
        
        # Start handshake
        msg_init = await alice_short.initiate_handshake("bob")
        msg_ack = await bob_short.handle_handshake_init(msg_init)
        
        # Small delay to ensure expiration
        await asyncio.sleep(0.1)
        
        # Alice sends challenge_response (which Bob should reject as expired)
        msg_response = await alice_short.handle_handshake_init_ack(msg_ack)
        msg_established = await bob_short.handle_challenge_response(msg_response)
        
        # Should be rejected due to expired challenge
        assert msg_established is None, "Should reject expired challenge"
        
        print("  ✓ Expired challenge correctly rejected")
        print("\n✅ Challenge Expiration Test PASSED")
        return True
    
    async def test_session_cleanup(self):
        """Test cleanup of expired sessions"""
        print("\n" + "=" * 70)
        print("TEST: Session Cleanup")
        print("=" * 70)
        
        # Create manager with short timeout
        short_config = HandshakeConfig(handshake_timeout=0)
        alice_short = HandshakeManager(
            entity_id="alice",
            ed25519_private_key=self.alice_keys['private'],
            config=short_config
        )
        
        # Start handshake but don't complete
        msg_init = await alice_short.initiate_handshake("bob")
        session_id = msg_init["session_id"]
        
        # Verify session exists
        assert alice_short.get_session(session_id) is not None
        
        # Wait for expiration
        await asyncio.sleep(0.1)
        
        # Cleanup
        await alice_short.cleanup_expired()
        
        # Session should be removed
        assert alice_short.get_session(session_id) is None
        
        print("  ✓ Expired session cleaned up")
        print("\n✅ Session Cleanup Test PASSED")
        return True
    
    async def test_duplicate_handshake_prevention(self):
        """Test prevention of duplicate handshakes"""
        print("\n" + "=" * 70)
        print("TEST: Duplicate Handshake Prevention")
        print("=" * 70)
        
        # Start first handshake
        msg_init_1 = await self.alice_manager.initiate_handshake("bob")
        assert msg_init_1 is not None
        session_id_1 = msg_init_1["session_id"]
        
        # Try to start second handshake (should fail or return same session)
        msg_init_2 = await self.alice_manager.initiate_handshake("bob")
        
        # Should return None or same session
        if msg_init_2 is not None:
            assert msg_init_2["session_id"] == session_id_1, "Should return same session"
        
        print("  ✓ Duplicate handshake prevented")
        print("\n✅ Duplicate Handshake Test PASSED")
        return True
    
    async def test_is_ready_check(self):
        """Test is_ready() method"""
        print("\n" + "=" * 70)
        print("TEST: Is Ready Check")
        print("=" * 70)
        
        # Initially not ready
        assert not self.alice_manager.is_ready("bob")
        assert not self.bob_manager.is_ready("alice")
        
        # Complete handshake
        msg_init = await self.alice_manager.initiate_handshake("bob")
        msg_ack = await self.bob_manager.handle_handshake_init(msg_init)
        msg_response = await self.alice_manager.handle_handshake_init_ack(msg_ack)
        msg_established = await self.bob_manager.handle_challenge_response(msg_response)
        msg_confirm = await self.alice_manager.handle_session_established(msg_established)
        msg_ready = await self.bob_manager.handle_session_confirm(msg_confirm)
        await self.alice_manager.handle_ready(msg_ready)
        
        # Now should be ready
        assert self.alice_manager.is_ready("bob")
        assert self.bob_manager.is_ready("alice")
        
        print("  ✓ is_ready() correctly reflects state")
        print("\n✅ Is Ready Check Test PASSED")
        return True
    
    async def test_get_session_key(self):
        """Test get_session_key() method"""
        print("\n" + "=" * 70)
        print("TEST: Get Session Key")
        print("=" * 70)
        
        # Initially no key
        assert self.alice_manager.get_session_key("bob") is None
        
        # Complete handshake
        msg_init = await self.alice_manager.initiate_handshake("bob")
        msg_ack = await self.bob_manager.handle_handshake_init(msg_init)
        msg_response = await self.alice_manager.handle_handshake_init_ack(msg_ack)
        msg_established = await self.bob_manager.handle_challenge_response(msg_response)
        msg_confirm = await self.alice_manager.handle_session_established(msg_established)
        msg_ready = await self.bob_manager.handle_session_confirm(msg_confirm)
        await self.alice_manager.handle_ready(msg_ready)
        
        # Now should have key
        key = self.alice_manager.get_session_key("bob")
        assert key is not None
        assert len(key) == 32  # 256-bit key
        
        print(f"  ✓ Session key retrieved: {key.hex()[:32]}...")
        print("\n✅ Get Session Key Test PASSED")
        return True


async def run_all_tests():
    """Run all integration tests"""
    print("=" * 70)
    print("HandshakeManager Integration Test Suite")
    print("v1.1 Protocol 6-Step Handshake")
    print("=" * 70)
    
    if not IMPORT_SUCCESS:
        print("\n❌ Cannot run tests - import failed")
        return False
    
    tester = TestHandshakeIntegration()
    await tester.setup()
    
    tests = [
        ("Complete 6-Step Handshake", tester.test_complete_6step_handshake),
        ("Invalid Signature Rejection", tester.test_invalid_signature_rejection),
        ("Challenge Expiration", tester.test_challenge_expiration),
        ("Session Cleanup", tester.test_session_cleanup),
        ("Duplicate Handshake Prevention", tester.test_duplicate_handshake_prevention),
        ("Is Ready Check", tester.test_is_ready_check),
        ("Get Session Key", tester.test_get_session_key),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            success = await test_func()
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ Test '{name}' FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 70)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 70)
    
    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
    else:
        print(f"\n⚠️  {failed} test(s) failed")
    
    return failed == 0


if __name__ == "__main__":
    try:
        success = asyncio.run(run_all_tests())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
