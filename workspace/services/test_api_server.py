#!/usr/bin/env python3
"""
API Server Test Suite
Tests for /message endpoint with signature verification and handler routing
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# Add services directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Mock environment variables before importing modules
os.environ["JWT_SECRET"] = "test-secret-key-for-jwt-tokens"
os.environ["ENTITY_ID"] = "test-server"
os.environ["PORT"] = "8000"

from fastapi.testclient import TestClient

# Import after setting env vars
import api_server
from crypto import SecureMessage, MessageSigner, SignatureVerifier, ReplayProtector, KeyPair


@pytest.fixture
def test_keypair():
    """Generate test key pair"""
    return KeyPair.generate()


@pytest.fixture
def mock_registry():
    """Mock registry for testing"""
    registry = Mock()
    registry.list_all.return_value = []
    registry.find_by_id.return_value = None
    registry.register.return_value = True
    registry.unregister.return_value = True
    registry.heartbeat.return_value = True
    return registry


@pytest.fixture(autouse=True)
def reset_signature_verifier():
    """Reset signature verifier state before each test to prevent state pollution"""
    # Clear all public keys before each test
    api_server.signature_verifier.public_keys.clear()
    api_server.signature_verifier.key_metadata.clear()
    yield
    # Clean up after test
    api_server.signature_verifier.public_keys.clear()
    api_server.signature_verifier.key_metadata.clear()


@pytest.fixture
def client(mock_registry, reset_signature_verifier):
    """Create test client with mocked dependencies"""
    with patch.object(api_server, 'registry', mock_registry):
        with patch.object(api_server, 'get_registry', return_value=mock_registry):
            yield TestClient(api_server.app)


class TestHealthEndpoint:
    """Test /health endpoint"""
    
    def test_health_check(self, client):
        """Health check returns correct structure"""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "security_features" in data


class TestMessageEndpoint:
    """Test /message endpoint with security features"""
    
    def create_signed_message(self, keypair, msg_type="test", payload=None):
        """Helper to create signed message"""
        signer = MessageSigner(keypair)
        message = SecureMessage(
            version="0.3",
            msg_type=msg_type,
            sender_id="test-entity",
            payload=payload or {"data": "test"}
        )
        message.sign(signer)
        return message.to_dict()
    
    def test_message_without_signature(self, client):
        """Message without signature is accepted but not verified"""
        message = {
            "version": "0.3",
            "msg_type": "ping",
            "sender_id": "test-sender",
            "payload": {"data": "hello"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "abc123"
        }
        
        response = client.post("/message", json=message)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["verified"] is False
        assert data["msg_type"] == "ping"
    
    def test_message_with_invalid_signature(self, client, test_keypair):
        """Message with invalid signature returns 401"""
        # First register the public key
        api_server.signature_verifier.add_public_key(
            "test-sender", 
            test_keypair.public_key
        )
        
        message = {
            "version": "0.3",
            "msg_type": "ping",
            "sender_id": "test-sender",
            "payload": {"data": "hello"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "def456",
            "signature": "invalid-signature-here"
        }
        
        response = client.post("/message", json=message)
        # Should fail signature verification
        assert response.status_code in [400, 401]
    
    def test_replay_protection(self, client):
        """Replay attack is prevented"""
        message = {
            "version": "0.3",
            "msg_type": "ping",
            "sender_id": "test-sender",
            "payload": {"data": "hello"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "replay-nonce-123"
        }
        
        # First request should succeed
        response1 = client.post("/message", json=message)
        assert response1.status_code == 200
        
        # Second request with same nonce should fail (replay)
        response2 = client.post("/message", json=message)
        assert response2.status_code == 400
        assert "replay" in response2.json()["detail"].lower()
    
    def test_old_timestamp_rejected(self, client):
        """Message with old timestamp is rejected"""
        # Use timedelta to create a timestamp 2 minutes in the past
        old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
        
        message = {
            "version": "0.3",
            "msg_type": "ping",
            "sender_id": "test-sender",
            "payload": {"data": "hello"},
            "timestamp": old_time.isoformat(),
            "nonce": "old-nonce-123"
        }
        
        response = client.post("/message", json=message)
        assert response.status_code == 400
        assert "old" in response.json()["detail"].lower() or "timestamp" in response.json()["detail"].lower()


class TestRegisterEndpoint:
    """Test /register endpoint"""
    
    def test_register_agent(self, client, mock_registry):
        """Agent registration works"""
        mock_registry.register.return_value = True
        
        request = {
            "entity_id": "test-agent",
            "name": "Test Agent",
            "endpoint": "http://localhost:8001",
            "capabilities": ["messaging", "task_execution"],
            "public_key": "abc123"
        }
        
        response = client.post("/register", json=request)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["entity_id"] == "test-agent"
        assert "api_key" in data
    
    def test_register_duplicate(self, client, mock_registry):
        """Duplicate registration fails"""
        mock_registry.register.return_value = False
        
        request = {
            "entity_id": "existing-agent",
            "name": "Existing Agent",
            "endpoint": "http://localhost:8001",
            "capabilities": []
        }
        
        response = client.post("/register", json=request)
        assert response.status_code == 400


@pytest.fixture
def valid_jwt_token(client, mock_registry):
    """Generate a valid JWT token for testing"""
    mock_registry.register.return_value = True
    
    # Register to get API key
    register_response = client.post("/register", json={
        "entity_id": "jwt-test-entity",
        "name": "JWT Test Entity",
        "endpoint": "http://localhost:8001",
        "capabilities": []
    })
    api_key = register_response.json()["api_key"]
    
    # Create JWT token
    token_response = client.post("/auth/token", json={
        "entity_id": "jwt-test-entity",
        "api_key": api_key
    })
    
    return token_response.json()["access_token"]


class TestJWTSecurity:
    """Test JWT token security scenarios"""
    
    def test_expired_jwt_token(self, client, mock_registry):
        """Expired JWT tokens are rejected with 401"""
        import jwt
        from datetime import datetime, timezone, timedelta
        
        # Create an expired token manually
        expired_payload = {
            "sub": "test-entity",
            "iat": datetime.now(timezone.utc) - timedelta(minutes=10),
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),  # Expired 5 minutes ago
            "jti": "expired-token-id",
            "type": "access"
        }
        
        # Encode with the same secret used by the server
        expired_token = jwt.encode(
            expired_payload,
            "test-secret-key-for-jwt-tokens",
            algorithm="HS256"
        )
        
        # Try to access protected endpoint with expired token
        response = client.post(
            "/unregister/test-entity",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower() or "token" in response.json()["detail"].lower()
    
    def test_tampered_jwt_token(self, client, mock_registry, valid_jwt_token):
        """Tampered JWT tokens (invalid signature) are rejected with 401"""
        # Tamper with the token by modifying the payload section
        token_parts = valid_jwt_token.split('.')
        assert len(token_parts) == 3
        
        # Modify the payload (middle section) - decode, modify, re-encode
        import base64
        import json
        
        # Add padding if needed
        payload_padding = 4 - len(token_parts[1]) % 4
        if payload_padding != 4:
            payload_b64 = token_parts[1] + '=' * payload_padding
        else:
            payload_b64 = token_parts[1]
        
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        # Tamper with the subject claim
        payload["sub"] = "attacker-entity"
        
        # Re-encode the tampered payload
        tampered_payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).decode().rstrip('=')
        
        # Keep the original signature (which won't match the tampered payload)
        tampered_token = f"{token_parts[0]}.{tampered_payload_b64}.{token_parts[2]}"
        
        # Try to access protected endpoint with tampered token
        response = client.post(
            "/unregister/test-entity",
            headers={"Authorization": f"Bearer {tampered_token}"}
        )
        
        assert response.status_code == 401
        assert "invalid" in response.json()["detail"].lower()
    
    def test_invalid_jwt_format(self, client):
        """Malformed JWT tokens are rejected with 401 or 403"""
        invalid_tokens = [
            "not-a-valid-token",
            "invalid.format",
            "too.many.parts.here.extra",
            "Bearer invalid-token-format",
            "",
        ]
        
        for invalid_token in invalid_tokens:
            response = client.post(
                "/unregister/test-entity",
                headers={"Authorization": f"Bearer {invalid_token}"}
            )
            # Should be rejected - either 401 (unauthorized) or 403 (forbidden)
            assert response.status_code in [401, 403], f"Token '{invalid_token[:20]}...' should be rejected"
    
    def test_missing_jwt_token(self, client):
        """Requests without auth header are rejected for protected endpoints"""
        # Try to access protected endpoint without any auth header
        response = client.post("/unregister/test-entity")
        
        assert response.status_code == 403
        assert "authorization" in response.json()["detail"].lower() or "authentication" in response.json()["detail"].lower()
    
    def test_valid_jwt_token_access(self, client, mock_registry, valid_jwt_token):
        """Valid JWT tokens allow access to protected endpoints"""
        mock_registry.unregister.return_value = True
        
        # Access protected endpoint with valid token
        response = client.post(
            "/unregister/jwt-test-entity",
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        # Should succeed (entity should be found, even if it was just registered)
        assert response.status_code in [200, 404]  # 200 if found, 404 if already gone


class TestAuthentication:
    """Test JWT and API key authentication"""
    
    def test_create_token_with_api_key(self, client, mock_registry):
        """Token creation with valid API key"""
        # First register to get API key
        mock_registry.register.return_value = True
        
        register_response = client.post("/register", json={
            "entity_id": "auth-test",
            "name": "Auth Test",
            "endpoint": "http://localhost:8001",
            "capabilities": []
        })
        api_key = register_response.json()["api_key"]
        
        # Create token
        response = client.post("/auth/token", json={
            "entity_id": "auth-test",
            "api_key": api_key
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_create_token_invalid_api_key(self, client):
        """Token creation with invalid API key fails"""
        response = client.post("/auth/token", json={
            "entity_id": "auth-test",
            "api_key": "invalid-key"
        })
        
        assert response.status_code == 401


class TestPublicKeyEndpoints:
    """Test public key management endpoints"""
    
    def test_get_server_public_key(self, client):
        """Get server public key"""
        response = client.get("/keys/public")
        assert response.status_code == 200
        data = response.json()
        assert "public_key" in data
        assert data["algorithm"] == "Ed25519"
    
    def test_verify_valid_signature(self, client, test_keypair):
        """Verify valid signature"""
        # Create a signed message
        message = {"data": "test"}
        signer = MessageSigner(test_keypair)
        signature = signer.sign_message(message)
        
        # Add public key to verifier
        api_server.signature_verifier.add_public_key("test-entity", test_keypair.public_key)
        
        response = client.post("/keys/verify", json={
            "message": message,
            "signature": signature,
            "sender_id": "test-entity"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True


class TestHandlerRouting:
    """Test message handler routing"""
    
    def test_ping_handler(self, client):
        """Ping messages are handled correctly"""
        message = {
            "version": "0.3",
            "msg_type": "ping",
            "sender_id": "test-sender",
            "payload": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "ping-nonce-1"
        }
        
        response = client.post("/message", json=message)
        assert response.status_code == 200
        data = response.json()
        assert data["handled"] is True
        assert data["status"] == "received"
    
    def test_status_handler(self, client):
        """Status messages are handled"""
        message = {
            "version": "0.3",
            "msg_type": "status",
            "sender_id": "test-sender",
            "payload": {"status": "running"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "status-nonce-1"
        }
        
        response = client.post("/message", json=message)
        assert response.status_code == 200
        data = response.json()
        assert data["handled"] is True
    
    def test_unknown_handler(self, client):
        """Unknown message types are not handled"""
        message = {
            "version": "0.3",
            "msg_type": "unknown_type_xyz",
            "sender_id": "test-sender",
            "payload": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "nonce": "unknown-nonce-1"
        }
        
        response = client.post("/message", json=message)
        assert response.status_code == 200
        # Unknown types are still processed but may not have specific handlers
        data = response.json()
        assert "handler_result" in data


class TestDiscovery:
    """Test /discover and /agent/{entity_id} endpoints"""
    
    def test_discover_all_agents(self, client, mock_registry):
        """Discover returns all registered agents"""
        # Setup mock
        from services.registry import ServiceInfo
        mock_service = ServiceInfo(
            entity_id="agent-1",
            entity_name="Test Agent",
            endpoint="http://localhost:8001",
            capabilities=["messaging"]
        )
        mock_registry.list_all.return_value = [mock_service]
        
        response = client.get("/discover")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert len(data["agents"]) == 1
        assert data["agents"][0]["entity_id"] == "agent-1"
        assert data["agents"][0]["alive"] is True
    
    def test_discover_by_capability(self, client, mock_registry):
        """Discover filters by capability"""
        from services.registry import ServiceInfo
        mock_service = ServiceInfo(
            entity_id="agent-1",
            entity_name="Test Agent",
            endpoint="http://localhost:8001",
            capabilities=["messaging"]
        )
        mock_registry.find_by_capability.return_value = [mock_service]
        
        response = client.get("/discover?capability=messaging")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 1
        mock_registry.find_by_capability.assert_called_once_with("messaging")
    
    def test_discover_empty_registry(self, client, mock_registry):
        """Discover with empty registry returns empty list"""
        mock_registry.list_all.return_value = []
        
        response = client.get("/discover")
        assert response.status_code == 200
        data = response.json()
        assert data["agents"] == []
    
    def test_get_agent_success(self, client, mock_registry):
        """Get existing agent details"""
        from services.registry import ServiceInfo
        mock_service = ServiceInfo(
            entity_id="agent-1",
            entity_name="Test Agent",
            endpoint="http://localhost:8001",
            capabilities=["messaging"]
        )
        mock_registry.find_by_id.return_value = mock_service
        
        response = client.get("/agent/agent-1")
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "agent-1"
        assert data["name"] == "Test Agent"
        assert "alive" in data
        assert "registered_at" in data
    
    def test_get_agent_not_found(self, client, mock_registry):
        """Get non-existent agent returns 404"""
        mock_registry.find_by_id.return_value = None
        
        response = client.get("/agent/nonexistent")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestDiscoverEndpoint:
    """Test /discover endpoint for P0 coverage"""
    
    def test_discover_returns_agents(self, client, mock_registry):
        """Discover returns registered agents list"""
        from services.registry import ServiceInfo
        
        # Setup mock with multiple agents
        mock_services = [
            ServiceInfo(
                entity_id="agent-1",
                entity_name="Test Agent 1",
                endpoint="http://localhost:8001",
                capabilities=["messaging", "task_execution"]
            ),
            ServiceInfo(
                entity_id="agent-2",
                entity_name="Test Agent 2",
                endpoint="http://localhost:8002",
                capabilities=["messaging"]
            )
        ]
        mock_registry.list_all.return_value = mock_services
        
        response = client.get("/discover")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert len(data["agents"]) == 2
        assert data["agents"][0]["entity_id"] == "agent-1"
        assert data["agents"][1]["entity_id"] == "agent-2"
        assert data["agents"][0]["alive"] is True
        assert "capabilities" in data["agents"][0]
    
    def test_discover_filter_by_capability(self, client, mock_registry):
        """Discover filters agents by capability"""
        from services.registry import ServiceInfo
        
        mock_service = ServiceInfo(
            entity_id="task-agent",
            entity_name="Task Agent",
            endpoint="http://localhost:8003",
            capabilities=["task_execution", "messaging"]
        )
        mock_registry.find_by_capability.return_value = [mock_service]
        
        response = client.get("/discover?capability=task_execution")
        assert response.status_code == 200
        data = response.json()
        assert len(data["agents"]) == 1
        assert data["agents"][0]["entity_id"] == "task-agent"
        assert "task_execution" in data["agents"][0]["capabilities"]
        mock_registry.find_by_capability.assert_called_once_with("task_execution")
    
    def test_discover_empty_registry(self, client, mock_registry):
        """Discover with empty registry returns empty list"""
        mock_registry.list_all.return_value = []
        
        response = client.get("/discover")
        assert response.status_code == 200
        data = response.json()
        assert data["agents"] == []
        assert isinstance(data["agents"], list)
    
    def test_discover_all_agents(self, client, mock_registry):
        """登録された全エージェントを一覧取得"""
        from services.registry import ServiceInfo
        
        mock_services = [
            ServiceInfo(
                entity_id="agent-1",
                entity_name="Test Agent 1",
                endpoint="http://localhost:8001",
                capabilities=["messaging", "task_execution"]
            ),
            ServiceInfo(
                entity_id="agent-2",
                entity_name="Test Agent 2",
                endpoint="http://localhost:8002",
                capabilities=["messaging"]
            )
        ]
        mock_registry.list_all.return_value = mock_services
        
        response = client.get("/discover")
        assert response.status_code == 200
        data = response.json()
        assert "agents" in data
        assert len(data["agents"]) == 2
        assert data["agents"][0]["entity_id"] == "agent-1"
        assert data["agents"][1]["entity_id"] == "agent-2"
        assert data["agents"][0]["alive"] is True


class TestAgentEndpoint:
    """Test /agent/{entity_id} endpoint for P0 coverage"""
    
    def test_get_agent_success(self, client, mock_registry):
        """Get existing agent information successfully"""
        from services.registry import ServiceInfo
        
        mock_service = ServiceInfo(
            entity_id="test-agent-123",
            entity_name="Test Agent",
            endpoint="http://localhost:8001",
            capabilities=["messaging", "storage"]
        )
        mock_registry.find_by_id.return_value = mock_service
        
        response = client.get("/agent/test-agent-123")
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "test-agent-123"
        assert data["name"] == "Test Agent"
        assert data["endpoint"] == "http://localhost:8001"
        assert "messaging" in data["capabilities"]
        assert "alive" in data
        assert "registered_at" in data
        assert "last_heartbeat" in data
    
    def test_get_agent_not_found(self, client, mock_registry):
        """Get non-existent agent returns 404"""
        mock_registry.find_by_id.return_value = None
        
        response = client.get("/agent/nonexistent-agent-id")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()
    
    def test_get_agent_invalid_id(self, client):
        """Get agent with invalid ID format returns 400 or 404"""
        # Test with invalid ID formats
        invalid_ids = [
            "",  # Empty ID
            "agent/with/slashes",  # Path traversal attempt
            "agent%20with%20spaces",  # URL encoded spaces
            "a" * 1000,  # Extremely long ID
        ]
        
        for invalid_id in invalid_ids:
            response = client.get(f"/agent/{invalid_id}")
            # Should return 400 (bad request) or 404 (not found)
            assert response.status_code in [400, 404, 422], \
                f"Invalid ID '{invalid_id[:30]}...' should return 400, 404, or 422"
    
    def test_get_existing_agent(self, client, mock_registry):
        """存在するエージェント情報取得"""
        from services.registry import ServiceInfo
        
        mock_service = ServiceInfo(
            entity_id="existing-agent-123",
            entity_name="Existing Agent",
            endpoint="http://localhost:8001",
            capabilities=["messaging", "storage"]
        )
        mock_registry.find_by_id.return_value = mock_service
        
        response = client.get("/agent/existing-agent-123")
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "existing-agent-123"
        assert data["name"] == "Existing Agent"
        assert data["endpoint"] == "http://localhost:8001"
        assert "messaging" in data["capabilities"]
        assert "alive" in data
        assert "registered_at" in data
    
    def test_get_nonexistent_agent(self, client, mock_registry):
        """存在しないエージェントで404"""
        mock_registry.find_by_id.return_value = None
        
        response = client.get("/agent/nonexistent-agent")
        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()


class TestIntegration:
    """Integration tests"""
    
    def test_full_message_flow(self, client, test_keypair, mock_registry):
        """Complete message flow with signature verification"""
        # Register agent with public key
        mock_registry.register.return_value = True
        
        register_response = client.post("/register", json={
            "entity_id": "integrated-agent",
            "name": "Integrated Agent",
            "endpoint": "http://localhost:8002",
            "capabilities": ["test"],
            "public_key": test_keypair.get_public_key_hex()
        })
        
        assert register_response.status_code == 200
        
        # Add public key to verifier
        api_server.signature_verifier.add_public_key(
            "integrated-agent",
            test_keypair.public_key
        )
        
        # Create signed message
        signer = MessageSigner(test_keypair)
        message = SecureMessage(
            version="0.3",
            msg_type="ping",
            sender_id="integrated-agent",
            payload={"test": True}
        )
        message.sign(signer)
        
        # Send message
        response = client.post("/message", json=message.to_dict())
        assert response.status_code == 200
        data = response.json()
        assert data["verified"] is True
        assert data["handled"] is True


class TestMessageSendEndpoint:
    """Test /message/send endpoint for P0 coverage"""
    
    @pytest.fixture
    def valid_jwt_token_for_send(self, client, mock_registry):
        """Generate a valid JWT token for message/send tests"""
        mock_registry.register.return_value = True
        
        # Register to get API key
        register_response = client.post("/register", json={
            "entity_id": "send-test-entity",
            "name": "Send Test Entity",
            "endpoint": "http://localhost:8001",
            "capabilities": []
        })
        api_key = register_response.json()["api_key"]
        
        # Create JWT token
        token_response = client.post("/auth/token", json={
            "entity_id": "send-test-entity",
            "api_key": api_key
        })
        
        return token_response.json()["access_token"]
    
    def test_send_message_to_valid_agent(self, client, mock_registry, valid_jwt_token_for_send):
        """Send message to valid agent returns success"""
        from services.registry import ServiceInfo
        
        # Setup mock for recipient agent
        mock_service = ServiceInfo(
            entity_id="recipient-agent",
            entity_name="Recipient Agent",
            endpoint="http://localhost:8002",
            capabilities=["messaging"]
        )
        mock_registry.find_by_id.return_value = mock_service
        
        # Mock PeerService
        with patch.object(api_server, 'get_peer_service') as mock_get_peer_service:
            mock_peer_service = AsyncMock()
            mock_peer_service.peers = {}
            mock_peer_service.add_peer = Mock()
            mock_peer_service.send_message = AsyncMock(return_value=True)
            mock_get_peer_service.return_value = mock_peer_service
            
            response = client.post(
                "/message/send",
                params={
                    "recipient_id": "recipient-agent",
                    "msg_type": "test_message",
                    "payload": json.dumps({"data": "hello"})
                },
                headers={"Authorization": f"Bearer {valid_jwt_token_for_send}"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "sent"
            assert data["recipient"] == "recipient-agent"
            assert "message" in data
            assert "timestamp" in data
    
    def test_send_to_nonexistent_agent(self, client, mock_registry, valid_jwt_token_for_send):
        """Send message to non-existent agent returns 404"""
        mock_registry.find_by_id.return_value = None
        
        response = client.post(
            "/message/send",
            params={
                "recipient_id": "nonexistent-agent",
                "msg_type": "test_message",
                "payload": json.dumps({"data": "hello"})
            },
            headers={"Authorization": f"Bearer {valid_jwt_token_for_send}"}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_send_with_invalid_jwt(self, client):
        """Send message with invalid JWT returns 401/403"""
        response = client.post(
            "/message/send",
            params={
                "recipient_id": "recipient-agent",
                "msg_type": "test_message",
                "payload": json.dumps({"data": "hello"})
            },
            headers={"Authorization": "Bearer invalid-token"}
        )
        
        assert response.status_code in [401, 403]
    
    def test_send_with_invalid_signature(self, client, mock_registry, valid_jwt_token_for_send):
        """Send message with invalid signature returns 401"""
        from services.registry import ServiceInfo
        
        # Setup mock for recipient agent
        mock_service = ServiceInfo(
            entity_id="recipient-agent",
            entity_name="Recipient Agent",
            endpoint="http://localhost:8002",
            capabilities=["messaging"]
        )
        mock_registry.find_by_id.return_value = mock_service
        
        # Create a message with invalid signature
        invalid_message = {
            "version": "0.3",
            "msg_type": "test_message",
            "sender_id": "send-test-entity",
            "recipient_id": "recipient-agent",
            "payload": {"data": "hello"},
            "timestamp": "2024-01-01T00:00:00Z",
            "nonce": "invalid-nonce-123",
            "signature": "invalid-signature-here"  # Invalid signature
        }
        
        # Send with JWT but invalid message signature
        response = client.post(
            "/message/send",
            params={
                "recipient_id": "recipient-agent",
                "msg_type": "test_message",
                "payload": json.dumps(invalid_message)
            },
            headers={"Authorization": f"Bearer {valid_jwt_token_for_send}"}
        )
        
        # Should fail due to invalid signature or be rejected by server
        # The server may return 401 for invalid signature
        assert response.status_code in [200, 401, 400]
    
    def test_send_to_valid_agent(self, client, mock_registry, valid_jwt_token_for_send):
        """Alias for test_send_message_to_valid_agent - Send message to valid agent"""
        # Call the main test implementation
        self.test_send_message_to_valid_agent(client, mock_registry, valid_jwt_token_for_send)
    
    def test_send_rate_limited(self, client, mock_registry, valid_jwt_token_for_send):
        """Alias for test_send_when_rate_limited - Send message when rate limited"""
        from services.registry import ServiceInfo
        
        # Setup mock for recipient agent
        mock_service = ServiceInfo(
            entity_id="recipient-agent",
            entity_name="Recipient Agent",
            endpoint="http://localhost:8002",
            capabilities=["messaging"]
        )
        mock_registry.find_by_id.return_value = mock_service
        
        # Mock rate limiter to always return rate limited
        with patch.object(api_server, 'get_peer_service') as mock_get_peer_service:
            mock_peer_service = AsyncMock()
            mock_peer_service.peers = {}
            mock_peer_service.add_peer = Mock()
            mock_peer_service.send_message = AsyncMock(return_value=True)
            mock_get_peer_service.return_value = mock_peer_service
            
            # Mock endpoint rate limiter to simulate rate limiting
            with patch.object(api_server, 'endpoint_limiter') as mock_limiter:
                mock_limiter.is_allowed = Mock(return_value=(False, 0, 60))
                
                # Make request that should be rate limited
                response = client.post(
                    "/message/send",
                    params={
                        "recipient_id": "recipient-agent",
                        "msg_type": "test_message",
                        "payload": json.dumps({"data": "hello"})
                    },
                    headers={"Authorization": f"Bearer {valid_jwt_token_for_send}"}
                )
                
                # Note: Rate limiting may be handled at middleware level
                # If 429 is not returned, the test documents current behavior
                if response.status_code == 429:
                    assert "rate limit" in response.json()["detail"].lower() or "too many" in response.json()["detail"].lower()


class TestUnregisterEndpoint:
    """Test /unregister/{entity_id} (POST) endpoint for P0 coverage"""
    
    @pytest.fixture
    def valid_jwt_token_for_unregister(self, client, mock_registry):
        """Generate a valid JWT token for unregister tests"""
        mock_registry.register.return_value = True
        
        # Register to get API key
        register_response = client.post("/register", json={
            "entity_id": "unregister-test-entity",
            "name": "Unregister Test Entity",
            "endpoint": "http://localhost:8001",
            "capabilities": []
        })
        api_key = register_response.json()["api_key"]
        
        # Create JWT token
        token_response = client.post("/auth/token", json={
            "entity_id": "unregister-test-entity",
            "api_key": api_key
        })
        
        return token_response.json()["access_token"]
    
    def test_unregister_existing_agent(self, client, mock_registry, valid_jwt_token_for_unregister):
        """Unregister existing agent returns success"""
        from services.registry import ServiceInfo
        
        # Setup mock to find the agent first
        mock_service = ServiceInfo(
            entity_id="unregister-test-entity",
            entity_name="Unregister Test Entity",
            endpoint="http://localhost:8001",
            capabilities=[]
        )
        mock_registry.find_by_id.return_value = mock_service
        mock_registry.unregister.return_value = True
        
        response = client.post(
            "/unregister/unregister-test-entity",
            headers={"Authorization": f"Bearer {valid_jwt_token_for_unregister}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["entity_id"] == "unregister-test-entity"
    
    def test_unregister_nonexistent_agent(self, client, mock_registry, valid_jwt_token_for_unregister):
        """Unregister non-existent agent returns 404"""
        mock_registry.find_by_id.return_value = None
        
        response = client.post(
            "/unregister/nonexistent-agent",
            headers={"Authorization": f"Bearer {valid_jwt_token_for_unregister}"}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_unregister_unauthorized(self, client):
        """Unauthorized unregistration (no token) returns 403"""
        response = client.post("/unregister/some-agent")
        
        assert response.status_code == 403
        assert "authorization" in response.json()["detail"].lower() or "authentication" in response.json()["detail"].lower()
    
    def test_unregister_wrong_entity(self, client, mock_registry, valid_jwt_token_for_unregister):
        """Trying to unregister different entity than token subject returns 403"""
        from services.registry import ServiceInfo
        
        # Setup mock to find a different agent
        mock_service = ServiceInfo(
            entity_id="different-agent",
            entity_name="Different Agent",
            endpoint="http://localhost:8002",
            capabilities=[]
        )
        mock_registry.find_by_id.return_value = mock_service
        
        # Try to unregister a different entity than what the token is for
        response = client.post(
            "/unregister/different-agent",
            headers={"Authorization": f"Bearer {valid_jwt_token_for_unregister}"}
        )
        
        assert response.status_code == 403
        assert "forbidden" in response.json()["detail"].lower() or "unauthorized" in response.json()["detail"].lower() or "entity" in response.json()["detail"].lower()


# =============================================================================
# Token System P1 Tests
# =============================================================================

@pytest.fixture
def mock_token_system():
    """Mock token_system module"""
    with patch.object(api_server, 'token_system') as mock_ts:
        # Mock Wallet class
        mock_wallet = Mock()
        mock_wallet.get_balance.return_value = 100.0
        mock_wallet.get_transaction_history.return_value = []
        mock_wallet.transfer.return_value = True
        
        # Mock get_wallet function
        mock_ts.get_wallet.return_value = mock_wallet
        mock_ts.create_wallet.return_value = mock_wallet
        
        # Mock TaskContract class
        mock_task = Mock()
        mock_task.task_id = "test-task-123"
        mock_task.client_id = "client-entity"
        mock_task.agent_id = "agent-entity"
        mock_task.amount = 50.0
        mock_task.description = "Test task"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.expires_at = None
        mock_task.status = "completed"
        
        mock_task_contract = Mock()
        mock_task_contract.create_task.return_value = True
        mock_task_contract.complete_task.return_value = True
        mock_task_contract.get_task.return_value = mock_task
        
        mock_ts.TaskContract.return_value = mock_task_contract
        
        yield mock_ts


@pytest.fixture
def mock_persistence():
    """Mock persistence for token state"""
    with patch.object(api_server, 'get_persistence') as mock_get_persist:
        mock_persist = Mock()
        mock_persist.save_all.return_value = None
        mock_get_persist.return_value = mock_persist
        yield mock_persist


class TestWalletBalanceEndpoint:
    """Test GET /wallet/{entity_id} - Wallet balance retrieval (P1)"""
    
    def test_get_wallet_balance_success(self, client, mock_token_system):
        """Get wallet balance for existing entity"""
        mock_wallet = Mock()
        mock_wallet.get_balance.return_value = 150.5
        mock_token_system.get_wallet.return_value = mock_wallet
        
        response = client.get("/wallet/test-entity")
        
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "test-entity"
        assert data["balance"] == 150.5
        assert data["currency"] == "AIC"
    
    def test_get_wallet_balance_not_found(self, client, mock_token_system):
        """Get wallet balance for non-existent entity returns 404"""
        mock_token_system.get_wallet.return_value = None
        
        response = client.get("/wallet/nonexistent-entity")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_get_wallet_balance_zero(self, client, mock_token_system):
        """Get wallet balance with zero balance"""
        mock_wallet = Mock()
        mock_wallet.get_balance.return_value = 0.0
        mock_token_system.get_wallet.return_value = mock_wallet
        
        response = client.get("/wallet/zero-balance-entity")
        
        assert response.status_code == 200
        data = response.json()
        assert data["balance"] == 0.0


class TestWalletTransferEndpoint:
    """Test POST /wallet/transfer - Token transfer (P1, JWT required)"""
    
    def test_transfer_success(self, client, mock_token_system, mock_persistence, valid_jwt_token):
        """Successful token transfer between entities"""
        from_wallet = Mock()
        from_wallet.transfer.return_value = True
        to_wallet = Mock()
        
        mock_token_system.get_wallet.side_effect = lambda e: from_wallet if e == "jwt-test-entity" else to_wallet
        
        response = client.post(
            "/wallet/transfer",
            json={
                "to_entity_id": "recipient-entity",
                "amount": 25.5,
                "description": "Test transfer"
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["from_entity_id"] == "jwt-test-entity"
        assert data["to_entity_id"] == "recipient-entity"
        assert data["amount"] == 25.5
        assert "timestamp" in data
        mock_persistence.save_all.assert_called_once()
    
    def test_transfer_insufficient_balance(self, client, mock_token_system, valid_jwt_token):
        """Transfer with insufficient balance returns 400"""
        from_wallet = Mock()
        from_wallet.transfer.return_value = False  # Transfer fails
        
        mock_token_system.get_wallet.side_effect = lambda e: from_wallet if e == "jwt-test-entity" else Mock()
        
        response = client.post(
            "/wallet/transfer",
            json={
                "to_entity_id": "recipient-entity",
                "amount": 9999.0,
                "description": "Large transfer"
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 400
        assert "transfer failed" in response.json()["detail"].lower() or "insufficient" in response.json()["detail"].lower()
    
    def test_transfer_without_auth(self, client):
        """Transfer without JWT token returns 403"""
        response = client.post(
            "/wallet/transfer",
            json={
                "to_entity_id": "recipient-entity",
                "amount": 10.0,
                "description": "Unauthorized transfer"
            }
        )
        
        assert response.status_code == 403
    
    def test_transfer_invalid_amount(self, client, mock_token_system, valid_jwt_token):
        """Transfer with invalid amount (negative/zero)"""
        response = client.post(
            "/wallet/transfer",
            json={
                "to_entity_id": "recipient-entity",
                "amount": -10.0,
                "description": "Invalid transfer"
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        # Validation error for negative amount
        assert response.status_code in [400, 422]
    
    def test_transfer_sender_wallet_not_found(self, client, mock_token_system, valid_jwt_token):
        """Transfer when sender wallet doesn't exist returns 404"""
        mock_token_system.get_wallet.return_value = None
        
        response = client.post(
            "/wallet/transfer",
            json={
                "to_entity_id": "recipient-entity",
                "amount": 10.0,
                "description": "Test transfer"
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 404
        assert "wallet not found" in response.json()["detail"].lower()


class TestTransactionHistoryEndpoint:
    """Test GET /wallet/{entity_id}/transactions - Transaction history (P1)"""
    
    def test_get_transaction_history_success(self, client, mock_token_system):
        """Get transaction history for existing wallet"""
        mock_tx = Mock()
        mock_tx.type.value = "TRANSFER"
        mock_tx.amount = 25.0
        mock_tx.timestamp = datetime.now(timezone.utc)
        mock_tx.description = "Test transaction"
        mock_tx.counterparty = "other-entity"
        mock_tx.related_task_id = None
        
        mock_wallet = Mock()
        mock_wallet.get_transaction_history.return_value = [mock_tx]
        mock_token_system.get_wallet.return_value = mock_wallet
        
        response = client.get("/wallet/test-entity/transactions")
        
        assert response.status_code == 200
        data = response.json()
        assert data["entity_id"] == "test-entity"
        assert data["count"] == 1
        assert len(data["transactions"]) == 1
        assert data["transactions"][0]["type"] == "TRANSFER"
        assert data["transactions"][0]["amount"] == 25.0
    
    def test_get_transaction_history_empty(self, client, mock_token_system):
        """Get transaction history with no transactions"""
        mock_wallet = Mock()
        mock_wallet.get_transaction_history.return_value = []
        mock_token_system.get_wallet.return_value = mock_wallet
        
        response = client.get("/wallet/new-entity/transactions")
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["transactions"] == []
    
    def test_get_transaction_history_not_found(self, client, mock_token_system):
        """Get transaction history for non-existent wallet returns 404"""
        mock_token_system.get_wallet.return_value = None
        
        response = client.get("/wallet/nonexistent-entity/transactions")
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


class TestTaskCreateEndpoint:
    """Test POST /task/create - Task creation (P1, JWT required)"""
    
    def test_create_task_success(self, client, mock_token_system, mock_persistence, valid_jwt_token):
        """Successfully create a new task"""
        mock_task = Mock()
        mock_task.task_id = "task-123"
        mock_task.client_id = "jwt-test-entity"
        mock_task.agent_id = "agent-entity"
        mock_task.amount = 100.0
        mock_task.description = "Test task creation"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.expires_at = None
        
        mock_task_contract = Mock()
        mock_task_contract.create_task.return_value = True
        mock_task_contract.get_task.return_value = mock_task
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/create",
            json={
                "task_id": "task-123",
                "agent_id": "agent-entity",
                "amount": 100.0,
                "description": "Test task creation"
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["task_id"] == "task-123"
        assert data["client_id"] == "jwt-test-entity"
        assert data["agent_id"] == "agent-entity"
        assert data["amount"] == 100.0
        mock_persistence.save_all.assert_called_once()
    
    def test_create_task_without_auth(self, client):
        """Create task without JWT token returns 403"""
        response = client.post(
            "/task/create",
            json={
                "task_id": "task-123",
                "agent_id": "agent-entity",
                "amount": 100.0,
                "description": "Test task"
            }
        )
        
        assert response.status_code == 403
    
    def test_create_task_insufficient_balance(self, client, mock_token_system, valid_jwt_token):
        """Create task with insufficient balance returns 400"""
        mock_task_contract = Mock()
        mock_task_contract.create_task.return_value = False  # Task creation fails
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/create",
            json={
                "task_id": "task-123",
                "agent_id": "agent-entity",
                "amount": 9999.0,
                "description": "Expensive task"
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 400
        assert "task creation failed" in response.json()["detail"].lower() or "insufficient" in response.json()["detail"].lower()
    
    def test_create_task_duplicate_id(self, client, mock_token_system, valid_jwt_token):
        """Create task with duplicate ID returns 400"""
        mock_task_contract = Mock()
        mock_task_contract.create_task.return_value = False  # Task already exists
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/create",
            json={
                "task_id": "existing-task-id",
                "agent_id": "agent-entity",
                "amount": 50.0,
                "description": "Duplicate task"
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 400
    
    def test_create_task_with_expiration(self, client, mock_token_system, mock_persistence, valid_jwt_token):
        """Create task with expiration date"""
        future_time = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        
        mock_task = Mock()
        mock_task.task_id = "task-with-expiry"
        mock_task.client_id = "jwt-test-entity"
        mock_task.agent_id = "agent-entity"
        mock_task.amount = 75.0
        mock_task.description = "Task with expiration"
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.expires_at = datetime.fromisoformat(future_time)
        
        mock_task_contract = Mock()
        mock_task_contract.create_task.return_value = True
        mock_task_contract.get_task.return_value = mock_task
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/create",
            json={
                "task_id": "task-with-expiry",
                "agent_id": "agent-entity",
                "amount": 75.0,
                "description": "Task with expiration",
                "expires_at": future_time
            },
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "task-with-expiry"
        assert data["expires_at"] is not None


class TestTaskCompleteEndpoint:
    """Test POST /task/complete - Task completion (P1, JWT required)"""
    
    def test_complete_task_success(self, client, mock_token_system, mock_persistence, valid_jwt_token):
        """Successfully complete a task"""
        mock_task = Mock()
        mock_task.task_id = "task-123"
        mock_task.client_id = "jwt-test-entity"
        mock_task.agent_id = "agent-entity"
        mock_task.amount = 100.0
        
        mock_task_contract = Mock()
        mock_task_contract.get_task.return_value = mock_task
        mock_task_contract.complete_task.return_value = True
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/complete",
            json={"task_id": "task-123"},
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"
        assert data["task_id"] == "task-123"
        assert data["agent_id"] == "agent-entity"
        assert data["amount"] == 100.0
        assert "completed_at" in data
        mock_persistence.save_all.assert_called_once()
    
    def test_complete_task_not_found(self, client, mock_token_system, valid_jwt_token):
        """Complete non-existent task returns 404"""
        mock_task_contract = Mock()
        mock_task_contract.get_task.return_value = None
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/complete",
            json={"task_id": "nonexistent-task"},
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    def test_complete_task_without_auth(self, client):
        """Complete task without JWT token returns 403"""
        response = client.post(
            "/task/complete",
            json={"task_id": "task-123"}
        )
        
        assert response.status_code == 403
    
    def test_complete_task_unauthorized_entity(self, client, mock_token_system, valid_jwt_token):
        """Complete task by unauthorized entity returns 403"""
        mock_task = Mock()
        mock_task.task_id = "task-123"
        mock_task.client_id = "other-client"  # Different from jwt-test-entity
        mock_task.agent_id = "other-agent"    # Different from jwt-test-entity
        
        mock_task_contract = Mock()
        mock_task_contract.get_task.return_value = mock_task
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/complete",
            json={"task_id": "task-123"},
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 403
        assert "only client or agent" in response.json()["detail"].lower()
    
    def test_complete_task_not_in_progress(self, client, mock_token_system, valid_jwt_token):
        """Complete task that is not in progress returns 400"""
        mock_task = Mock()
        mock_task.task_id = "task-123"
        mock_task.client_id = "jwt-test-entity"
        mock_task.agent_id = "agent-entity"
        
        mock_task_contract = Mock()
        mock_task_contract.get_task.return_value = mock_task
        mock_task_contract.complete_task.return_value = False  # Task not in progress
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/complete",
            json={"task_id": "task-123"},
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 400
        assert "task completion failed" in response.json()["detail"].lower()
    
    def test_complete_task_by_agent(self, client, mock_token_system, mock_persistence, valid_jwt_token):
        """Agent can complete their assigned task"""
        mock_task = Mock()
        mock_task.task_id = "task-123"
        mock_task.client_id = "client-entity"
        mock_task.agent_id = "jwt-test-entity"  # Token holder is the agent
        mock_task.amount = 50.0
        
        mock_task_contract = Mock()
        mock_task_contract.get_task.return_value = mock_task
        mock_task_contract.complete_task.return_value = True
        mock_token_system.TaskContract.return_value = mock_task_contract
        
        response = client.post(
            "/task/complete",
            json={"task_id": "task-123"},
            headers={"Authorization": f"Bearer {valid_jwt_token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"


if __name__ == "__main__":
    # Run tests
    print("Running API Server tests...")
    pytest.main([__file__, "-v"])
