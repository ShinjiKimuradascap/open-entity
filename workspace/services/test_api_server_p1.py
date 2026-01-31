#!/usr/bin/env python3
"""
P1 API Server Test Suite
Tests for /wallet/*, /task/*, and /rating/* endpoints
"""

import pytest
import sys
import os
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

# Add services directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock environment variables before importing modules
os.environ["JWT_SECRET"] = "test-secret-key-for-jwt-tokens"
os.environ["ENTITY_ID"] = "test-server"
os.environ["PORT"] = "8000"

from fastapi.testclient import TestClient

# Import after setting env vars
import api_server


@pytest.fixture
def mock_token_wallet():
    """Mock TokenWallet for testing"""
    wallet = Mock()
    wallet.get_balance.return_value = 1000
    wallet.transfer.return_value = True
    wallet.get_transaction_history.return_value = []
    return wallet


@pytest.fixture
def mock_token_economy(mock_token_wallet):
    """Mock TokenEconomy for testing"""
    economy = Mock()
    economy.get_wallet.return_value = mock_token_wallet
    return economy


@pytest.fixture
def mock_task_contract():
    """Mock TaskContract for testing"""
    contract = Mock()
    contract.create_task.return_value = "task-123"
    contract.complete_task.return_value = {"status": "completed", "reward": 100}
    contract.get_task.return_value = {
        "task_id": "task-123",
        "creator": "entity-a",
        "description": "Test task",
        "reward": 100,
        "status": "pending"
    }
    return contract


@pytest.fixture
def mock_reputation_contract():
    """Mock ReputationContract for testing"""
    contract = Mock()
    contract.submit_rating.return_value = {"success": True}
    contract.get_rating.return_value = {
        "entity_id": "entity-a",
        "average": 4.5,
        "count": 10,
        "total": 45
    }
    return contract


@pytest.fixture
def mock_persistence():
    """Mock PersistenceManager for testing"""
    persistence = Mock()
    persistence.save_all.return_value = None
    return persistence


@pytest.fixture
def client_with_mocks(mock_token_wallet, mock_task_contract, mock_reputation_contract, mock_persistence):
    """Create test client with mocked token system"""
    with patch.object(api_server, 'token_economy') as mock_economy:
        with patch.object(api_server, 'get_wallet', return_value=mock_token_wallet):
            with patch.object(api_server, 'get_persistence', return_value=mock_persistence):
                yield TestClient(api_server.app)


class TestWalletEndpoints:
    """Test /wallet/* endpoints"""
    
    def test_get_wallet_balance_success(self, client_with_mocks, mock_token_wallet):
        """Get balance for existing wallet with tokens"""
        mock_token_wallet.get_balance.return_value = 1500
        
        response = client_with_mocks.get("/wallet/entity-a")
        
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "entity-a"
        assert data["balance"] == 1500
        assert data["currency"] == "AIC"
    
    def test_get_wallet_balance_zero(self, client_with_mocks, mock_token_wallet):
        """Get balance for wallet with zero tokens"""
        mock_token_wallet.get_balance.return_value = 0
        
        response = client_with_mocks.get("/wallet/entity-b")
        
        assert response.status_code == 200
        data = response.json()
        assert data["balance"] == 0
    
    def test_get_wallet_not_found(self, client_with_mocks):
        """Get balance for non-existent entity returns 404"""
        with patch.object(api_server, 'get_wallet', return_value=None):
            response = client_with_mocks.get("/wallet/nonexistent")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestWalletTransfer:
    """Test /wallet/transfer endpoint"""
    
    def test_transfer_success(self, client_with_mocks, mock_token_wallet):
        """Valid transfer between two existing wallets"""
        mock_token_wallet.transfer.return_value = True
        mock_token_wallet.get_balance.return_value = 1000
        
        headers = {"Authorization": "Bearer test-entity-a"}
        payload = {
            "to_entity_id": "entity-b",
            "amount": 100,
            "description": "Test transfer"
        }
        
        response = client_with_mocks.post("/wallet/transfer", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["amount"] == 100
        assert data["to_entity_id"] == "entity-b"
    
    def test_transfer_insufficient_balance(self, client_with_mocks, mock_token_wallet):
        """Transfer with insufficient balance returns 400"""
        mock_token_wallet.transfer.return_value = False
        
        headers = {"Authorization": "Bearer test-entity-a"}
        payload = {
            "to_entity_id": "entity-b",
            "amount": 10000,
            "description": "Too much"
        }
        
        response = client_with_mocks.post("/wallet/transfer", json=payload, headers=headers)
        
        assert response.status_code == 400
        assert "insufficient" in response.json()["detail"].lower() or "failed" in response.json()["detail"].lower()
    
    def test_transfer_invalid_amount(self, client_with_mocks):
        """Transfer with invalid amount returns 400"""
        headers = {"Authorization": "Bearer test-entity-a"}
        payload = {
            "to_entity_id": "entity-b",
            "amount": -100,
            "description": "Invalid amount"
        }
        
        response = client_with_mocks.post("/wallet/transfer", json=payload, headers=headers)
        
        assert response.status_code == 422  # Validation error
    
    def test_transfer_no_auth(self, client_with_mocks):
        """Transfer without authentication returns 401"""
        payload = {
            "to_entity_id": "entity-b",
            "amount": 100,
            "description": "Test"
        }
        
        response = client_with_mocks.post("/wallet/transfer", json=payload)
        
        assert response.status_code == 403


class TestWalletTransactions:
    """Test /wallet/{entity_id}/transactions endpoint"""
    
    def test_get_transactions_success(self, client_with_mocks, mock_token_wallet):
        """Get transactions for entity with history"""
        from services.token_system import TransactionType
        
        tx = Mock()
        tx.type = TransactionType.SEND
        tx.amount = 100
        tx.timestamp = datetime.now(timezone.utc)
        tx.description = "Test tx"
        tx.counterparty = "entity-b"
        tx.related_task_id = None
        
        mock_token_wallet.get_transaction_history.return_value = [tx]
        
        response = client_with_mocks.get("/wallet/entity-a/transactions")
        
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "entity-a"
        assert len(data["transactions"]) == 1
        assert data["count"] == 1
    
    def test_get_transactions_empty(self, client_with_mocks, mock_token_wallet):
        """Get transactions for entity with no history"""
        mock_token_wallet.get_transaction_history.return_value = []
        
        response = client_with_mocks.get("/wallet/entity-b/transactions")
        
        assert response.status_code == 200
        data = response.json()
        assert data["transactions"] == []
        assert data["count"] == 0


class TestTaskEndpoints:
    """Test /task/* endpoints"""
    
    def test_get_task_success(self, client_with_mocks, mock_task_contract):
        """Get existing task details"""
        with patch.object(api_server, 'get_task_contract', return_value=mock_task_contract):
            response = client_with_mocks.get("/task/task-123")
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-123"
    
    def test_get_task_not_found(self, client_with_mocks):
        """Get non-existent task returns 404"""
        mock_contract = Mock()
        mock_contract.get_task.return_value = None
        
        with patch.object(api_server, 'get_task_contract', return_value=mock_contract):
            response = client_with_mocks.get("/task/nonexistent")
        
        assert response.status_code == 404
    
    def test_create_task_success(self, client_with_mocks, mock_task_contract, mock_token_wallet):
        """Create task with valid parameters"""
        mock_task_contract.create_task.return_value = "new-task-456"
        mock_token_wallet.get_balance.return_value = 1000
        
        with patch.object(api_server, 'get_task_contract', return_value=mock_task_contract):
            headers = {"Authorization": "Bearer test-entity-a"}
            payload = {
                "description": "New test task",
                "reward": 100,
                "deadline": (datetime.now(timezone.utc).isoformat())
            }
            
            response = client_with_mocks.post("/task/create", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert "task_id" in data
        assert data["creator_id"] == "test-entity-a"
    
    def test_create_task_invalid_reward(self, client_with_mocks):
        """Create task with zero reward returns 400"""
        headers = {"Authorization": "Bearer test-entity-a"}
        payload = {
            "description": "Invalid task",
            "reward": 0,
            "deadline": (datetime.now(timezone.utc).isoformat())
        }
        
        response = client_with_mocks.post("/task/create", json=payload, headers=headers)
        
        # Validation error or insufficient balance
        assert response.status_code in [400, 422]


class TestRatingEndpoints:
    """Test /rating/* endpoints"""
    
    def test_get_rating_success(self, client_with_mocks, mock_reputation_contract):
        """Get rating for entity with ratings"""
        with patch.object(api_server, 'get_reputation_contract', return_value=mock_reputation_contract):
            response = client_with_mocks.get("/rating/entity-a")
        
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "entity-a"
        assert data["average"] == 4.5
        assert data["count"] == 10
    
    def test_get_rating_no_ratings(self, client_with_mocks):
        """Get rating for entity with no ratings"""
        mock_contract = Mock()
        mock_contract.get_rating.return_value = {
            "entity_id": "new-entity",
            "average": 0.0,
            "count": 0,
            "total": 0
        }
        
        with patch.object(api_server, 'get_reputation_contract', return_value=mock_contract):
            response = client_with_mocks.get("/rating/new-entity")
        
        assert response.status_code == 200
        data = response.json()
        assert data["average"] == 0.0
        assert data["count"] == 0
    
    def test_submit_rating_success(self, client_with_mocks, mock_reputation_contract):
        """Submit valid rating (1-5 stars)"""
        with patch.object(api_server, 'get_reputation_contract', return_value=mock_reputation_contract):
            headers = {"Authorization": "Bearer test-entity-b"}
            payload = {
                "rated_entity_id": "entity-a",
                "score": 5,
                "comment": "Great work!"
            }
            
            response = client_with_mocks.post("/rating/submit", json=payload, headers=headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
    
    def test_submit_rating_invalid_score(self, client_with_mocks):
        """Submit rating with invalid score returns 400"""
        headers = {"Authorization": "Bearer test-entity-b"}
        payload = {
            "rated_entity_id": "entity-a",
            "score": 6,  # Invalid: should be 1-5
            "comment": "Invalid"
        }
        
        response = client_with_mocks.post("/rating/submit", json=payload, headers=headers)
        
        assert response.status_code in [400, 422]
    
    def test_submit_rating_no_auth(self, client_with_mocks):
        """Submit rating without authentication returns 401/403"""
        payload = {
            "rated_entity_id": "entity-a",
            "score": 4,
            "comment": "Good"
        }
        
        response = client_with_mocks.post("/rating/submit", json=payload)
        
        assert response.status_code in [401, 403]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
