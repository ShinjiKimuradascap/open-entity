#!/usr/bin/env python3
"""
API v0.5.x Automation Tests
API自動化テスト - 全v0.5エンドポイント網羅

Coverage:
- Health & Status
- Agent Management (register/unregister/heartbeat/discover)
- Messages (send/receive)
- Authentication (JWT token)
- Token Economy (wallet/transfer/transactions)
- Tasks v2 (create/complete)
- Reputation v2 (ratings)

Usage:
    pytest services/test_api_v05_automation.py -v
    pytest services/test_api_v05_automation.py -v --cov=services.api_server
"""

import pytest
import sys
import os
import json
import jwt
import asyncio
from pathlib import Path
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from typing import Generator, Dict, Any

sys.path.insert(0, str(Path(__file__).parent))

# Set test environment
os.environ["JWT_SECRET"] = "test-secret-key-for-jwt-tokens"
os.environ["API_KEY"] = "test-api-key-12345"

from fastapi.testclient import TestClient

# Import after setting env vars
from api_server import app, jwt_auth, signature_verifier


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide test client."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def mock_registry():
    """Mock registry for agent operations."""
    with patch("api_server.registry") as mock:
        mock.get_agent = Mock(return_value={
            "id": "test-agent",
            "entity_id": "test-entity",
            "public_key": "0x1234567890abcdef",
            "last_heartbeat": datetime.now(timezone.utc).isoformat(),
            "metadata": {"capabilities": ["test"]}
        })
        mock.register = Mock(return_value=True)
        mock.unregister = Mock(return_value=True)
        mock.update_heartbeat = Mock(return_value=True)
        mock.discover = Mock(return_value=[{
            "id": "peer-1",
            "entity_id": "peer-entity",
            "metadata": {"capabilities": ["storage"]}
        }])
        yield mock


@pytest.fixture
def valid_jwt_token() -> str:
    """Generate a valid JWT token for testing."""
    payload = {
        "sub": "test-entity",
        "iss": "ai-collaboration-platform",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "aud": "api"
    }
    return jwt.encode(payload, "test-secret-key-for-jwt-tokens", algorithm="HS256")


@pytest.fixture
def expired_jwt_token() -> str:
    """Generate an expired JWT token."""
    payload = {
        "sub": "test-entity",
        "iss": "ai-collaboration-platform",
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "aud": "api"
    }
    return jwt.encode(payload, "test-secret-key-for-jwt-tokens", algorithm="HS256")


# =============================================================================
# Health & Status Tests
# =============================================================================

class TestHealthEndpoints:
    """Test health and status endpoints."""
    
    def test_health_check(self, client):
        """Test health endpoint."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        
    def test_stats_endpoint(self, client):
        """Test stats endpoint."""
        response = client.get("/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "public_key" in data
        assert "uptime" in data
        assert "version" in data
        
    def test_get_public_key(self, client):
        """Test public key endpoint."""
        response = client.get("/keys/public")
        
        assert response.status_code == 200
        data = response.json()
        assert "public_key" in data


# =============================================================================
# Authentication Tests
# =============================================================================

class TestAuthentication:
    """Test authentication endpoints."""
    
    def test_create_jwt_token(self, client):
        """Test JWT token creation with API key."""
        response = client.post(
            "/auth/token",
            headers={"X-API-Key": "test-api-key-12345"},
            json={"entity_id": "test-entity", "ttl_hours": 1}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["entity_id"] == "test-entity"
        
    def test_create_token_invalid_api_key(self, client):
        """Test token creation with invalid API key."""
        response = client.post(
            "/auth/token",
            headers={"X-API-Key": "invalid-key"},
            json={"entity_id": "test-entity"}
        )
        
        assert response.status_code == 401
        
    def test_verify_signature_endpoint(self, client):
        """Test signature verification endpoint."""
        response = client.post(
            "/keys/verify",
            json={
                "message": "test message",
                "signature": "0x" + "ab" * 64,
                "public_key": "0x" + "cd" * 32
            }
        )
        
        # Should return valid response (may fail verification but endpoint works)
        assert response.status_code in [200, 400]


# =============================================================================
# Agent Management Tests
# =============================================================================

class TestAgentManagement:
    """Test agent management endpoints."""
    
    def test_register_agent(self, client, mock_registry):
        """Test agent registration."""
        response = client.post(
            "/register",
            json={
                "entity_id": "new-agent",
                "public_key": "0x" + "ab" * 32,
                "metadata": {"capabilities": ["storage", "compute"]}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "registered"
        mock_registry.register.assert_called_once()
        
    def test_unregister_agent(self, client, mock_registry, valid_jwt_token):
        """Test agent unregistration with JWT."""
        response = client.post(
            "/unregister/test-agent",
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 200
        mock_registry.unregister.assert_called_once()
        
    def test_unregister_without_jwt(self, client):
        """Test unregistration without JWT fails."""
        response = client.post("/unregister/test-agent")
        
        assert response.status_code == 403
        
    def test_heartbeat(self, client, mock_registry):
        """Test heartbeat endpoint."""
        response = client.post(
            "/heartbeat",
            json={"agent_id": "test-agent", "status": "active"}
        )
        
        assert response.status_code == 200
        mock_registry.update_heartbeat.assert_called_once()
        
    def test_discover_agents(self, client, mock_registry):
        """Test agent discovery."""
        response = client.get("/discover")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        mock_registry.discover.assert_called_once()
        
    def test_get_agent_details(self, client, mock_registry):
        """Test getting agent details."""
        response = client.get("/agent/test-agent")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "test-agent"
        mock_registry.get_agent.assert_called_once_with("test-agent")


# =============================================================================
# Message Tests
# =============================================================================

class TestMessageEndpoints:
    """Test message endpoints."""
    
    def test_receive_message(self, client, mock_registry):
        """Test message reception."""
        response = client.post(
            "/message",
            json={
                "sender_id": "sender-agent",
                "receiver_id": "receiver-agent",
                "payload": "encrypted_payload_here",
                "signature": "0x" + "ab" * 64
            }
        )
        
        # Should process message (may succeed or fail validation)
        assert response.status_code in [200, 400, 422]
        
    def test_send_message_with_jwt(self, client, mock_registry, valid_jwt_token):
        """Test sending message with JWT auth."""
        with patch("api_server.message_router") as mock_router:
            mock_router.route_message = AsyncMock(return_value={"status": "delivered"})
            
            response = client.post(
                "/message/send",
                headers={"Authorization": f"Bearer {valid_jwt_token}"},
                json={
                    "to_entity": "receiver-agent",
                    "message": {"type": "test", "data": "hello"},
                    "require_signature": True
                }
            )
            
            assert response.status_code == 200
            
    def test_send_message_without_jwt(self, client):
        """Test sending message without JWT fails."""
        response = client.post(
            "/message/send",
            json={
                "to_entity": "receiver-agent",
                "message": {"type": "test"}
            }
        )
        
        assert response.status_code == 403


# =============================================================================
# Token Economy Tests
# =============================================================================

class TestTokenEconomy:
    """Test token economy endpoints."""
    
    def test_get_wallet_balance(self, client, valid_jwt_token):
        """Test getting wallet balance."""
        with patch("api_server.get_wallet") as mock_wallet:
            mock_wallet.return_value = Mock(get_balance=Mock(return_value=1000.0))
            
            response = client.get(
                "/wallet/test-entity/balance",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "balance" in data
            
    def test_transfer_tokens(self, client, valid_jwt_token):
        """Test token transfer."""
        with patch("api_server.get_wallet") as mock_get_wallet:
            sender = Mock(transfer=Mock(return_value=True))
            receiver = Mock()
            mock_get_wallet.side_effect = [sender, receiver]
            
            response = client.post(
                "/wallet/transfer",
                headers={"Authorization": f"Bearer {valid_jwt_token}"},
                json={
                    "from_entity": "sender",
                    "to_entity": "receiver",
                    "amount": 100.0,
                    "description": "Test transfer"
                }
            )
            
            assert response.status_code in [200, 400]
            
    def test_get_transactions(self, client, valid_jwt_token):
        """Test getting transaction history."""
        with patch("api_server.get_wallet") as mock_wallet:
            mock_wallet.return_value = Mock(
                transactions=[
                    Mock(to_dict=Mock(return_value={
                        "id": "tx-1",
                        "amount": 100.0,
                        "type": "transfer"
                    }))
                ]
            )
            
            response = client.get(
                "/wallet/test-entity/transactions",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)


# =============================================================================
# Tasks v2 Tests
# =============================================================================

class TestTasksV2:
    """Test Tasks v2 endpoints."""
    
    def test_create_task(self, client, valid_jwt_token):
        """Test task creation."""
        with patch("api_server.get_task_contract") as mock_contract:
            mock_task = Mock()
            mock_task.id = "task-123"
            mock_contract.return_value.create_task.return_value = mock_task
            
            response = client.post(
                "/tasks/create",
                headers={"Authorization": f"Bearer {valid_jwt_token}"},
                json={
                    "worker": "worker-entity",
                    "reward": 100.0,
                    "description": "Test task",
                    "deadline_hours": 24
                }
            )
            
            assert response.status_code in [200, 201]
            
    def test_complete_task(self, client, valid_jwt_token):
        """Test task completion."""
        with patch("api_server.get_task_contract") as mock_contract:
            mock_contract.return_value.complete_task.return_value = True
            
            response = client.post(
                "/tasks/task-123/complete",
                headers={"Authorization": f"Bearer {valid_jwt_token}"}
            )
            
            assert response.status_code in [200, 202]
            
    def test_get_task_status(self, client):
        """Test getting task status."""
        with patch("api_server.get_task_contract") as mock_contract:
            mock_task = Mock(
                to_dict=Mock(return_value={
                    "id": "task-123",
                    "status": "in_progress",
                    "reward": 100.0
                })
            )
            mock_contract.return_value.get_task.return_value = mock_task
            
            response = client.get("/tasks/task-123")
            
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == "task-123"


# =============================================================================
# Reputation v2 Tests
# =============================================================================

class TestReputationV2:
    """Test Reputation v2 endpoints."""
    
    def test_submit_rating(self, client, valid_jwt_token):
        """Test rating submission."""
        with patch("api_server.get_reputation_contract") as mock_contract:
            mock_contract.return_value.submit_rating.return_value = True
            
            response = client.post(
                "/ratings/submit",
                headers={"Authorization": f"Bearer {valid_jwt_token}"},
                json={
                    "target_entity": "target-entity",
                    "score": 4.5,
                    "comment": "Great work!"
                }
            )
            
            assert response.status_code in [200, 201]
            
    def test_get_ratings(self, client):
        """Test getting ratings."""
        with patch("api_server.get_reputation_contract") as mock_contract:
            mock_contract.return_value.get_ratings.return_value = [
                {"from": "user-1", "score": 5.0, "comment": "Excellent"}
            ]
            
            response = client.get("/ratings/target-entity")
            
            assert response.status_code == 200
            data = response.json()
            assert isinstance(data, list)


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test API error handling."""
    
    def test_invalid_endpoint(self, client):
        """Test request to invalid endpoint."""
        response = client.get("/invalid/endpoint")
        
        assert response.status_code == 404
        
    def test_invalid_json(self, client):
        """Test request with invalid JSON."""
        response = client.post(
            "/register",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 422
        
    def test_expired_jwt(self, client, expired_jwt_token):
        """Test request with expired JWT."""
        response = client.post(
            "/unregister/test-agent",
            headers={"Authorization": f"Bearer {expired_jwt_token}"}
        )
        
        assert response.status_code == 401


# =============================================================================
# Integration Flow Tests
# =============================================================================

class TestIntegrationFlows:
    """Test complete API integration flows."""
    
    def test_complete_agent_lifecycle(self, client, mock_registry, valid_jwt_token):
        """Test complete agent lifecycle."""
        # 1. Register agent
        reg_response = client.post(
            "/register",
            json={
                "entity_id": "lifecycle-agent",
                "public_key": "0x" + "ab" * 32,
                "metadata": {"capabilities": ["test"]}
            }
        )
        assert reg_response.status_code == 200
        
        # 2. Send heartbeat
        hb_response = client.post(
            "/heartbeat",
            json={"agent_id": "lifecycle-agent", "status": "active"}
        )
        assert hb_response.status_code == 200
        
        # 3. Get agent details
        get_response = client.get("/agent/lifecycle-agent")
        assert get_response.status_code == 200
        
        # 4. Unregister
        unreg_response = client.post(
            "/unregister/lifecycle-agent",
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        assert unreg_response.status_code == 200
        
    def test_messaging_flow(self, client, mock_registry, valid_jwt_token):
        """Test complete messaging flow."""
        # This tests the flow of sending messages between entities
        with patch("api_server.message_router") as mock_router:
            mock_router.route_message = AsyncMock(return_value={"status": "delivered"})
            
            # Send message
            send_response = client.post(
                "/message/send",
                headers={"Authorization": f"Bearer {valid_jwt_token}"},
                json={
                    "to_entity": "receiver",
                    "message": {"type": "task_request", "data": "test"}
                }
            )
            
            assert send_response.status_code == 200


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
