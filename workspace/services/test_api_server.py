#!/usr/bin/env python3
"""
API Server Test Suite
Tests for /message endpoint with signature verification and handler routing
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
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
from fastapi import HTTPException

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


@pytest.fixture
def client(mock_registry):
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
        old_time = datetime.now(timezone.utc)
        # Subtract 2 minutes (more than max_age_seconds=60)
        old_timestamp = old_time.replace(minute=(old_time.minute - 2) % 60)
        
        message = {
            "version": "0.3",
            "msg_type": "ping",
            "sender_id": "test-sender",
            "payload": {"data": "hello"},
            "timestamp": old_timestamp.isoformat(),
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


if __name__ == "__main__":
    # Run tests
    print("Running API Server tests...")
    pytest.main([__file__, "-v"])
