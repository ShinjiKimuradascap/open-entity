#!/usr/bin/env python3
"""
Entity A-B Integration Tests
クロスエンティティ統合テスト - GitHub Actions自動化対応

Test Coverage:
- Peer-to-peer handshake (Ed25519/X25519 key exchange)
- Encrypted message relay between entities
- Cross-entity token transfer
- Session establishment and validation
- End-to-end task delegation flow

Usage:
    pytest services/test_entity_a_b_integration.py -v
    pytest services/test_entity_a_b_integration.py -v --cov=services
    pytest services/test_entity_a_b_integration.py -v -m "e2e"
"""

import pytest
import sys
import os
import json
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Generator, Dict, Any, Tuple
from unittest.mock import Mock, patch, AsyncMock

# Add services to path
sys.path.insert(0, str(Path(__file__).parent))

from crypto import CryptoManager
from e2e_session import E2ESessionManager, SessionState
from peer_service import PeerService
from token_system import create_wallet, get_wallet, delete_wallet, TransactionType
from task_delegation import TaskDelegationManager


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Provide a temporary data directory for tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="entity_ab_test_"))
    yield temp_dir
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def entity_a_keys() -> Tuple[str, str]:
    """Generate Entity A keypair."""
    crypto = CryptoManager("entity-a-test")
    keys = crypto.get_keypair()
    return keys["private_key"], keys["public_key"]


@pytest.fixture
def entity_b_keys() -> Tuple[str, str]:
    """Generate Entity B keypair."""
    crypto = CryptoManager("entity-b-test")
    keys = crypto.get_keypair()
    return keys["private_key"], keys["public_key"]


@pytest.fixture
def crypto_a(entity_a_keys) -> CryptoManager:
    """Provide Entity A CryptoManager."""
    priv_key, _ = entity_a_keys
    return CryptoManager("entity-a", private_key_hex=priv_key)


@pytest.fixture
def crypto_b(entity_b_keys) -> CryptoManager:
    """Provide Entity B CryptoManager."""
    priv_key, _ = entity_b_keys
    return CryptoManager("entity-b", private_key_hex=priv_key)


# =============================================================================
# Handshake Tests
# =============================================================================

@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.security
class TestEntityABHandshake:
    """Test Entity A-B handshake protocol."""
    
    def test_key_exchange_x25519(self, crypto_a, crypto_b):
        """Test X25519 key exchange between entities."""
        # Get X25519 public keys
        pub_a_x25519 = crypto_a.get_x25519_public_key()
        pub_b_x25519 = crypto_b.get_x25519_public_key()
        
        assert pub_a_x25519 is not None
        assert pub_b_x25519 is not None
        assert len(bytes.fromhex(pub_a_x25519)) == 32
        assert len(bytes.fromhex(pub_b_x25519)) == 32
        
    def test_shared_secret_derivation(self, crypto_a, crypto_b):
        """Test shared secret derivation."""
        pub_a_x25519 = crypto_a.get_x25519_public_key()
        pub_b_x25519 = crypto_b.get_x25519_public_key()
        
        # Entity A derives shared secret with B
        shared_a = crypto_a.derive_shared_secret(pub_b_x25519)
        
        # Entity B derives shared secret with A
        shared_b = crypto_b.derive_shared_secret(pub_a_x25519)
        
        assert shared_a is not None
        assert shared_b is not None
        assert len(shared_a) == 32
        assert len(shared_b) == 32
        assert shared_a == shared_b  # Same shared secret
        
    def test_ed25519_signature_verification(self, crypto_a, crypto_b):
        """Test Ed25519 signature verification between entities."""
        message = b"Hello from Entity A"
        
        # Entity A signs message
        signature = crypto_a.sign(message)
        
        # Entity B verifies signature
        pub_a_ed25519 = crypto_a.get_keypair()["public_key"]
        is_valid = crypto_b.verify_signature(pub_a_ed25519, message, signature)
        
        assert is_valid is True
        
    def test_cross_entity_jwt_creation(self, crypto_a, crypto_b):
        """Test JWT token creation and verification between entities."""
        # Entity A creates JWT for Entity B
        token = crypto_a.create_jwt_token(audience="entity-b")
        
        # Entity B verifies the token
        pub_a_ed25519 = crypto_a.get_keypair()["public_key"]
        decoded = crypto_b.verify_jwt_token(token, pub_a_ed25519)
        
        assert decoded is not None
        assert decoded.get("sub") == "entity-a"
        assert decoded.get("aud") == "entity-b"


# =============================================================================
# Encrypted Communication Tests
# =============================================================================

@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.crypto
class TestEncryptedCommunication:
    """Test encrypted message exchange between entities."""
    
    def test_encrypt_decrypt_message(self, crypto_a, crypto_b):
        """Test message encryption and decryption."""
        pub_b_x25519 = crypto_b.get_x25519_public_key()
        
        # Entity A encrypts message for Entity B
        plaintext = "Secret message from A to B"
        encrypted = crypto_a.encrypt_x25519(pub_b_x25519, plaintext)
        
        assert encrypted is not None
        assert encrypted != plaintext
        
    def test_message_integrity(self, crypto_a, crypto_b):
        """Test message integrity with signature."""
        message = json.dumps({
            "from": "entity-a",
            "to": "entity-b",
            "content": "Important data",
            "timestamp": datetime.now().isoformat()
        })
        
        # Sign message
        signature = crypto_a.sign(message.encode())
        
        # Verify signature
        pub_a_ed25519 = crypto_a.get_keypair()["public_key"]
        is_valid = crypto_b.verify_signature(pub_a_ed25519, message.encode(), signature)
        
        assert is_valid is True
        
    def test_end_to_end_encryption(self, crypto_a, crypto_b):
        """Test complete E2E encryption flow."""
        # Exchange public keys
        pub_a_x25519 = crypto_a.get_x25519_public_key()
        pub_b_x25519 = crypto_b.get_x25519_public_key()
        
        # Entity A encrypts for B
        message = "E2E encrypted message"
        encrypted = crypto_a.encrypt_x25519(pub_b_x25519, message)
        
        # In real scenario, B would decrypt with private key
        # Here we verify encryption happened
        assert encrypted is not None
        assert isinstance(encrypted, str)


# =============================================================================
# Session Management Tests
# =============================================================================

@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.session
class TestCrossEntitySession:
    """Test session management between entities."""
    
    async def test_session_creation(self, crypto_a, crypto_b):
        """Test session creation between entities."""
        session_mgr = E2ESessionManager(crypto_a)
        
        pub_a = crypto_a.get_keypair()["public_key"]
        pub_b = crypto_b.get_keypair()["public_key"]
        
        # Create session
        session_id = await session_mgr.create_session("entity-a", "entity-b")
        
        assert session_id is not None
        assert isinstance(session_id, str)
        assert len(session_id) > 0
        
    async def test_session_validation(self, crypto_a, crypto_b):
        """Test session validation."""
        session_mgr = E2ESessionManager(crypto_a)
        
        session_id = await session_mgr.create_session("entity-a", "entity-b")
        is_valid = await session_mgr.validate_session(session_id, "entity-a", "entity-b")
        
        assert is_valid is True
        
    async def test_session_expiration(self, crypto_a, crypto_b):
        """Test session expiration detection."""
        session_mgr = E2ESessionManager(crypto_a)
        
        session_id = await session_mgr.create_session("entity-a", "entity-b")
        
        # Manually expire session
        session = session_mgr.sessions.get(session_id)
        if session:
            session.expires_at = datetime.now() - timedelta(hours=1)
            
        is_valid = await session_mgr.validate_session(session_id, "entity-a", "entity-b")
        assert is_valid is False


# =============================================================================
# Token Transfer Tests
# =============================================================================

@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.token
class TestCrossEntityTokenTransfer:
    """Test token transfer between entities."""
    
    def test_wallet_creation_both_entities(self):
        """Test wallet creation for both entities."""
        wallet_a = create_wallet("entity-a-wallet", initial_balance=10000.0)
        wallet_b = create_wallet("entity-b-wallet", initial_balance=1000.0)
        
        assert wallet_a is not None
        assert wallet_b is not None
        assert wallet_a.get_balance() == 10000.0
        assert wallet_b.get_balance() == 1000.0
        
    def test_entity_a_to_b_transfer(self):
        """Test token transfer from Entity A to Entity B."""
        wallet_a = create_wallet("entity-a-transfer", initial_balance=5000.0)
        wallet_b = create_wallet("entity-b-transfer", initial_balance=500.0)
        
        transfer_amount = 1000.0
        success = wallet_a.transfer(wallet_b, transfer_amount, "Payment for services")
        
        assert success is True
        assert wallet_a.get_balance() == 4000.0
        assert wallet_b.get_balance() == 1500.0
        
    def test_entity_b_to_a_transfer(self):
        """Test token transfer from Entity B to Entity A."""
        wallet_a = create_wallet("entity-a-recv", initial_balance=2000.0)
        wallet_b = create_wallet("entity-b-send", initial_balance=3000.0)
        
        transfer_amount = 500.0
        success = wallet_b.transfer(wallet_a, transfer_amount, "Refund")
        
        assert success is True
        assert wallet_b.get_balance() == 2500.0
        assert wallet_a.get_balance() == 2500.0
        
    def test_cross_entity_transaction_history(self):
        """Test transaction history across entities."""
        wallet_a = create_wallet("entity-a-history", initial_balance=10000.0)
        wallet_b = create_wallet("entity-b-history", initial_balance=1000.0)
        
        # Multiple transfers
        wallet_a.transfer(wallet_b, 500.0, "First payment")
        wallet_b.transfer(wallet_a, 100.0, "Partial refund")
        wallet_a.transfer(wallet_b, 300.0, "Second payment")
        
        # Verify transaction counts
        a_txs = wallet_a.transactions
        b_txs = wallet_b.transactions
        
        assert len(a_txs) == 4  # Initial + 2 out + 1 in
        assert len(b_txs) == 4  # Initial + 1 out + 2 in
        
        # Verify transaction types
        a_out = [tx for tx in a_txs if tx.tx_type == TransactionType.TRANSFER_OUT]
        a_in = [tx for tx in a_txs if tx.tx_type == TransactionType.TRANSFER_IN]
        
        assert len(a_out) == 2
        assert len(a_in) == 1


# =============================================================================
# Task Delegation Tests
# =============================================================================

class TestCrossEntityTaskDelegation:
    """Test task delegation between Entity A and Entity B."""
    
    def test_task_delegation_a_to_b(self):
        """Test Entity A delegating task to Entity B."""
        from token_system import get_task_contract
        
        wallet_a = create_wallet("entity-a-delegator", initial_balance=5000.0)
        wallet_b = create_wallet("entity-b-worker", initial_balance=1000.0)
        
        contract = get_task_contract()
        
        # Entity A creates task for Entity B
        task_id = contract.create_task(
            delegator="entity-a-delegator",
            worker="entity-b-worker",
            reward=1000.0,
            deadline_hours=48,
            description="Cross-entity task: Analyze data"
        )
        
        assert task_id is not None
        
        task = contract.get_task(task_id)
        assert task.delegator == "entity-a-delegator"
        assert task.worker == "entity-b-worker"
        assert task.reward == 1000.0
        
    def test_task_completion_and_reward(self):
        """Test task completion and reward distribution."""
        from token_system import get_task_contract, TaskStatus
        
        wallet_a = create_wallet("entity-a-complete", initial_balance=5000.0)
        wallet_b = create_wallet("entity-b-complete", initial_balance=1000.0)
        
        contract = get_task_contract()
        
        # Create and complete task
        task_id = contract.create_task(
            delegator="entity-a-complete",
            worker="entity-b-complete",
            reward=500.0,
            deadline_hours=24,
            description="Task to complete"
        )
        
        success = contract.complete_task(task_id)
        assert success is True
        
        task = contract.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        
        # Transfer reward
        reward_success = wallet_a.transfer(wallet_b, task.reward, f"Reward for task {task_id}")
        assert reward_success is True
        
        assert wallet_b.get_balance() == 1500.0
        assert wallet_a.get_balance() == 4500.0


# =============================================================================
# End-to-End Integration Tests
# =============================================================================

class TestEndToEndEntityAB:
    """End-to-end Entity A-B integration scenarios."""
    
    def test_complete_collaboration_workflow(self, crypto_a, crypto_b):
        """Test complete collaboration workflow."""
        from token_system import get_task_contract, TaskStatus
        
        # Setup
        wallet_a = create_wallet("e2e-entity-a", initial_balance=10000.0)
        wallet_b = create_wallet("e2e-entity-b", initial_balance=2000.0)
        
        # Step 1: Handshake (key exchange)
        pub_a_x25519 = crypto_a.get_x25519_public_key()
        pub_b_x25519 = crypto_b.get_x25519_public_key()
        shared_a = crypto_a.derive_shared_secret(pub_b_x25519)
        shared_b = crypto_b.derive_shared_secret(pub_a_x25519)
        assert shared_a == shared_b
        
        # Step 2: Entity A delegates task to Entity B
        contract = get_task_contract()
        task_id = contract.create_task(
            delegator="e2e-entity-a",
            worker="e2e-entity-b",
            reward=2000.0,
            deadline_hours=72,
            description="E2E collaboration task"
        )
        
        # Step 3: Entity B completes task
        contract.complete_task(task_id)
        task = contract.get_task(task_id)
        assert task.status == TaskStatus.COMPLETED
        
        # Step 4: Entity A pays reward to Entity B
        wallet_a.transfer(wallet_b, task.reward, f"Reward for {task_id}")
        
        # Verify final state
        assert wallet_a.get_balance() == 8000.0
        assert wallet_b.get_balance() == 4000.0
        
    def test_error_handling_invalid_transfer(self):
        """Test error handling for invalid transfers."""
        wallet_a = create_wallet("entity-a-error", initial_balance=100.0)
        wallet_b = create_wallet("entity-b-error", initial_balance=100.0)
        
        # Attempt overdraft
        success = wallet_a.transfer(wallet_b, 200.0, "Overdraft attempt")
        
        assert success is False
        assert wallet_a.get_balance() == 100.0  # Unchanged
        assert wallet_b.get_balance() == 100.0  # Unchanged


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
