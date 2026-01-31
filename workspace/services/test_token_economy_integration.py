#!/usr/bin/env python3
"""
Token Economy Integration Tests (pytest version)
トークン経済統合テスト - GitHub Actions自動化対応

Test Coverage:
- Wallet lifecycle (create/transfer/delete)
- Task contract lifecycle (create/complete/reward)
- Token minting and burning
- Persistence (save/load)
- Economy metrics and statistics

Usage:
    pytest services/test_token_economy_integration.py -v
    pytest services/test_token_economy_integration.py -v --cov=services
"""

import pytest
import sys
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from typing import Generator

# Add services to path
sys.path.insert(0, str(Path(__file__).parent))

from token_system import (
    create_wallet, get_wallet, delete_wallet,
    get_task_contract, get_reputation_contract,
    TaskStatus, TransactionType,
    save_all, load_all, get_minter, set_minter
)
from token_economy import TokenEconomy, TokenMetadata, initialize_token_economy, get_token_economy
from token_persistence import PersistenceManager


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_data_dir() -> Generator[Path, None, None]:
    """Provide a temporary data directory for tests."""
    temp_dir = Path(tempfile.mkdtemp(prefix="token_economy_test_"))
    yield temp_dir
    # Cleanup
    if temp_dir.exists():
        shutil.rmtree(temp_dir)


@pytest.fixture
def clean_registry() -> Generator[None, None, None]:
    """Clean global registries before and after test."""
    import token_system
    import token_economy
    
    # Clear before test
    token_system._wallet_registry.clear()
    token_system._task_contract = None
    token_system._reputation_contract = None
    token_system._minter = None
    token_system._persistence = None
    token_economy._economy_instance = None
    
    yield
    
    # Clear after test
    token_system._wallet_registry.clear()
    token_system._task_contract = None
    token_system._reputation_contract = None
    token_system._minter = None
    token_system._persistence = None
    token_economy._economy_instance = None


@pytest.fixture
def persistence_manager(temp_data_dir: Path) -> PersistenceManager:
    """Provide a configured persistence manager."""
    return PersistenceManager(str(temp_data_dir))


@pytest.fixture
def token_economy(temp_data_dir: Path, clean_registry) -> TokenEconomy:
    """Provide an initialized token economy."""
    return initialize_token_economy(
        data_dir=str(temp_data_dir),
        metadata=TokenMetadata(
            name="Test AI Credit",
            symbol="TAIC",
            decimals=8,
            mintable=True,
            burnable=True
        )
    )


# =============================================================================
# Wallet Tests
# =============================================================================

class TestWalletLifecycle:
    """Test wallet creation, operations, and deletion."""
    
    def test_create_wallet(self, clean_registry):
        """Test wallet creation with initial balance."""
        wallet = create_wallet("test-entity-1", initial_balance=1000.0)
        
        assert wallet is not None
        assert wallet.entity_id == "test-entity-1"
        assert wallet.get_balance() == 1000.0
        assert len(wallet.transactions) == 1  # Initial deposit
        
    def test_create_wallet_zero_balance(self, clean_registry):
        """Test wallet creation with zero balance."""
        wallet = create_wallet("test-entity-2", initial_balance=0.0)
        
        assert wallet.get_balance() == 0.0
        assert len(wallet.transactions) == 0
        
    def test_get_existing_wallet(self, clean_registry):
        """Test retrieving existing wallet."""
        original = create_wallet("test-entity-3", initial_balance=500.0)
        retrieved = get_wallet("test-entity-3")
        
        assert retrieved is original  # Same instance
        assert retrieved.get_balance() == 500.0
        
    def test_delete_wallet(self, clean_registry):
        """Test wallet deletion."""
        create_wallet("test-entity-4", initial_balance=100.0)
        assert get_wallet("test-entity-4") is not None
        
        delete_wallet("test-entity-4")
        assert get_wallet("test-entity-4") is None


class TestTokenTransfer:
    """Test token transfer between wallets."""
    
    def test_successful_transfer(self, clean_registry):
        """Test successful token transfer."""
        sender = create_wallet("sender", initial_balance=1000.0)
        receiver = create_wallet("receiver", initial_balance=100.0)
        
        sender_before = sender.get_balance()
        receiver_before = receiver.get_balance()
        transfer_amount = 500.0
        
        success = sender.transfer(receiver, transfer_amount, "Test payment")
        
        assert success is True
        assert sender.get_balance() == sender_before - transfer_amount
        assert receiver.get_balance() == receiver_before + transfer_amount
        
    def test_insufficient_balance_transfer(self, clean_registry):
        """Test transfer with insufficient balance."""
        sender = create_wallet("sender-poor", initial_balance=100.0)
        receiver = create_wallet("receiver-poor", initial_balance=0.0)
        
        success = sender.transfer(receiver, 200.0, "Overdraft attempt")
        
        assert success is False
        assert sender.get_balance() == 100.0  # Unchanged
        assert receiver.get_balance() == 0.0
        
    def test_transfer_transaction_history(self, clean_registry):
        """Test transaction history after transfer."""
        sender = create_wallet("sender-history", initial_balance=1000.0)
        receiver = create_wallet("receiver-history", initial_balance=0.0)
        
        sender.transfer(receiver, 300.0, "Payment for services")
        
        sender_txs = sender.transactions
        receiver_txs = receiver.transactions
        
        assert len(sender_txs) == 2  # Initial deposit + transfer out
        assert len(receiver_txs) == 1  # Transfer in
        
        assert sender_txs[-1].tx_type == TransactionType.TRANSFER_OUT
        assert receiver_txs[-1].tx_type == TransactionType.TRANSFER_IN


# =============================================================================
# Task Contract Tests
# =============================================================================

class TestTaskContractLifecycle:
    """Test task contract creation, completion, and reward."""
    
    def test_create_task_contract(self, clean_registry):
        """Test task contract creation."""
        contract = get_task_contract()
        
        task_id = contract.create_task(
            delegator="delegator-1",
            worker="worker-1",
            reward=100.0,
            deadline_hours=24,
            description="Test task"
        )
        
        assert task_id is not None
        task = contract.get_task(task_id)
        assert task is not None
        assert task.delegator == "delegator-1"
        assert task.worker == "worker-1"
        assert task.reward == 100.0
        assert task.status == TaskStatus.PENDING
        
    def test_complete_task_and_reward(self, clean_registry):
        """Test task completion and reward distribution."""
        # Setup wallets and contract
        delegator = create_wallet("delegator-2", initial_balance=1000.0)
        worker = create_wallet("worker-2", initial_balance=0.0)
        contract = get_task_contract()
        
        # Create task
        task_id = contract.create_task(
            delegator="delegator-2",
            worker="worker-2",
            reward=100.0,
            deadline_hours=24,
            description="Reward test task"
        )
        
        # Complete task
        success = contract.complete_task(task_id)
        assert success is True
        
        # Distribute reward
        task = contract.get_task(task_id)
        reward_success = delegator.transfer(worker, task.reward, f"Reward for task {task_id}")
        
        assert reward_success is True
        assert worker.get_balance() == 100.0
        assert delegator.get_balance() == 900.0
        
    def test_task_expiration(self, clean_registry):
        """Test task expiration detection."""
        contract = get_task_contract()
        
        # Create task with very short deadline
        task_id = contract.create_task(
            delegator="delegator-3",
            worker="worker-3",
            reward=50.0,
            deadline_hours=0,  # Already expired
            description="Expired task"
        )
        
        # Manually set created_at to past
        task = contract.get_task(task_id)
        task.created_at = datetime.now() - timedelta(hours=1)
        task.deadline = task.created_at + timedelta(seconds=1)
        
        expired = contract.check_expired_tasks()
        assert len(expired) >= 1
        assert task.status == TaskStatus.EXPIRED


# =============================================================================
# Token Economy Tests
# =============================================================================

class TestTokenEconomyOperations:
    """Test token economy operations (mint, burn, supply)."""
    
    def test_mint_tokens(self, clean_registry, temp_data_dir):
        """Test token minting."""
        economy = initialize_token_economy(
            data_dir=str(temp_data_dir),
            metadata=TokenMetadata(mintable=True)
        )
        
        recipient = create_wallet("mint-recipient", initial_balance=0.0)
        initial_supply = economy.metadata.total_supply
        
        success = economy.mint(recipient, 1000.0, "Initial mint")
        
        assert success is True
        assert recipient.get_balance() == 1000.0
        assert economy.metadata.total_supply == initial_supply + 1000.0
        
    def test_burn_tokens(self, clean_registry, temp_data_dir):
        """Test token burning."""
        economy = initialize_token_economy(
            data_dir=str(temp_data_dir),
            metadata=TokenMetadata(burnable=True)
        )
        
        holder = create_wallet("burn-holder", initial_balance=1000.0)
        initial_supply = economy.metadata.total_supply
        
        success = economy.burn(holder, 300.0, "Token burn")
        
        assert success is True
        assert holder.get_balance() == 700.0
        
    def test_max_supply_enforcement(self, clean_registry, temp_data_dir):
        """Test max supply limit enforcement."""
        economy = initialize_token_economy(
            data_dir=str(temp_data_dir),
            metadata=TokenMetadata(
                mintable=True,
                max_supply=1000.0,
                total_supply=0.0
            )
        )
        
        recipient = create_wallet("max-supply-test", initial_balance=0.0)
        
        # First mint within limit
        success1 = economy.mint(recipient, 500.0, "First mint")
        assert success1 is True
        
        # Second mint exceeding limit
        success2 = economy.mint(recipient, 600.0, "Second mint (should fail)")
        assert success2 is False  # Would exceed max_supply
        
    def test_economy_metrics(self, clean_registry, temp_data_dir):
        """Test economy metrics calculation."""
        economy = initialize_token_economy(data_dir=str(temp_data_dir))
        
        # Create multiple wallets
        create_wallet("metrics-1", initial_balance=1000.0)
        create_wallet("metrics-2", initial_balance=500.0)
        create_wallet("metrics-3", initial_balance=200.0)
        
        metrics = economy.get_metrics()
        
        assert metrics["total_supply"] >= 1700.0
        assert metrics["holder_count"] >= 3


# =============================================================================
# Persistence Tests
# =============================================================================

class TestTokenPersistence:
    """Test data persistence across sessions."""
    
    def test_save_and_load_wallets(self, clean_registry, temp_data_dir):
        """Test wallet persistence."""
        pm = PersistenceManager(str(temp_data_dir))
        
        # Create and save wallets
        alice = create_wallet("alice", initial_balance=1000.0)
        bob = create_wallet("bob", initial_balance=500.0)
        
        wallets = {"alice": alice, "bob": bob}
        assert pm.save_wallets(wallets) is True
        
        # Load wallets
        loaded = pm.load_wallets()
        assert len(loaded) == 2
        assert loaded["alice"].get_balance() == 1000.0
        assert loaded["bob"].get_balance() == 500.0
        
    def test_save_and_load_economy(self, clean_registry, temp_data_dir):
        """Test economy state persistence."""
        pm = PersistenceManager(str(temp_data_dir))
        
        # Initialize and modify economy
        economy = initialize_token_economy(
            data_dir=str(temp_data_dir),
            metadata=TokenMetadata(name="Test Token", symbol="TEST")
        )
        
        wallet = create_wallet("economy-test", initial_balance=1000.0)
        economy.mint(wallet, 500.0, "Test mint")
        
        # Save
        assert pm.save_economy(economy) is True
        
        # Load
        loaded_economy = pm.load_economy()
        assert loaded_economy is not None
        assert loaded_economy.metadata.name == "Test Token"
        assert loaded_economy.metadata.symbol == "TEST"
        
    def test_persistence_round_trip(self, clean_registry, temp_data_dir):
        """Test complete persistence round-trip."""
        pm = PersistenceManager(str(temp_data_dir))
        
        # Setup initial state
        economy = initialize_token_economy(data_dir=str(temp_data_dir))
        alice = create_wallet("round-trip-alice", initial_balance=1000.0)
        bob = create_wallet("round-trip-bob", initial_balance=500.0)
        alice.transfer(bob, 200.0, "Test transfer")
        
        # Save all
        wallets = {"round-trip-alice": alice, "round-trip-bob": bob}
        assert pm.save_all(wallets, economy, None, None) is True
        
        # Clear registries
        import token_system
        token_system._wallet_registry.clear()
        
        # Load all
        loaded_wallets, loaded_economy, _, _ = pm.load_all()
        
        assert len(loaded_wallets) == 2
        assert loaded_wallets["round-trip-alice"].get_balance() == 800.0
        assert loaded_wallets["round-trip-bob"].get_balance() == 700.0


# =============================================================================
# End-to-End Integration Tests
# =============================================================================

class TestEndToEndScenarios:
    """End-to-end integration scenarios."""
    
    def test_complete_workflow(self, clean_registry, temp_data_dir):
        """Test complete token economy workflow."""
        # Initialize
        economy = initialize_token_economy(data_dir=str(temp_data_dir))
        contract = get_task_contract()
        
        # Create participants
        delegator = create_wallet("e2e-delegator", initial_balance=2000.0)
        worker = create_wallet("e2e-worker", initial_balance=0.0)
        platform = create_wallet("e2e-platform", initial_balance=0.0)
        
        # Mint additional tokens
        economy.mint(delegator, 1000.0, "Bonus allocation")
        assert delegator.get_balance() == 3000.0
        
        # Create and complete task
        task_id = contract.create_task(
            delegator="e2e-delegator",
            worker="e2e-worker",
            reward=500.0,
            deadline_hours=48,
            description="E2E test task"
        )
        
        # Complete task
        contract.complete_task(task_id)
        
        # Distribute reward (worker + platform fee)
        task = contract.get_task(task_id)
        platform_fee = task.reward * 0.05  # 5% fee
        worker_reward = task.reward - platform_fee
        
        delegator.transfer(worker, worker_reward, "Worker reward")
        delegator.transfer(platform, platform_fee, "Platform fee")
        
        # Verify final state
        assert worker.get_balance() == worker_reward
        assert platform.get_balance() == platform_fee
        assert delegator.get_balance() == 3000.0 - task.reward
        
    def test_multiple_tasks_and_rewards(self, clean_registry, temp_data_dir):
        """Test multiple tasks with rewards."""
        economy = initialize_token_economy(data_dir=str(temp_data_dir))
        contract = get_task_contract()
        
        # Setup
        delegator = create_wallet("multi-delegator", initial_balance=5000.0)
        workers = [create_wallet(f"worker-{i}", initial_balance=0.0) for i in range(3)]
        
        # Create multiple tasks
        tasks = []
        for i, worker in enumerate(workers):
            task_id = contract.create_task(
                delegator="multi-delegator",
                worker=f"worker-{i}",
                reward=500.0 + (i * 100),
                deadline_hours=24,
                description=f"Task {i}"
            )
            tasks.append(task_id)
            
        # Complete all tasks and distribute rewards
        total_rewards = 0.0
        for i, task_id in enumerate(tasks):
            contract.complete_task(task_id)
            task = contract.get_task(task_id)
            delegator.transfer(workers[i], task.reward, f"Reward for task {i}")
            total_rewards += task.reward
            
        # Verify
        assert delegator.get_balance() == 5000.0 - total_rewards
        for i, worker in enumerate(workers):
            expected_reward = 500.0 + (i * 100)
            assert worker.get_balance() == expected_reward


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    # Run with pytest if available
    pytest.main([__file__, "-v", "--tb=short"])
