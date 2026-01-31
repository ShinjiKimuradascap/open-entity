"""Tests for DHT Registry integration

Tests for v1.2 DHT unified implementation
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

# Test target
try:
    from services.dht_registry import (
        PeerInfo,
        DHTRegistry,
        load_bootstrap_nodes,
        create_dht_registry,
        get_dht_registry,
        reset_dht_registry
    )
except ImportError:
    from dht_registry import (
        PeerInfo,
        DHTRegistry,
        load_bootstrap_nodes,
        create_dht_registry,
        get_dht_registry,
        reset_dht_registry
    )


class TestPeerInfo:
    """Test PeerInfo dataclass"""
    
    def test_peer_info_creation(self):
        """Test basic PeerInfo creation"""
        peer = PeerInfo(
            peer_id="abc123",
            entity_id="test-entity",
            entity_name="Test Entity",
            endpoint="localhost:8000",
            public_key="dGVzdC1rZXk=",
            capabilities=["discovery", "messaging"],
            timestamp=datetime.now(timezone.utc).isoformat(),
            ttl=3600,
            signature=None
        )
        
        assert peer.peer_id == "abc123"
        assert peer.entity_id == "test-entity"
        assert "discovery" in peer.capabilities
    
    def test_peer_info_to_dict(self):
        """Test PeerInfo serialization"""
        peer = PeerInfo(
            peer_id="abc123",
            entity_id="test-entity",
            entity_name="Test Entity",
            endpoint="localhost:8000",
            public_key="dGVzdC1rZXk=",
            capabilities=["discovery"],
            timestamp="2026-01-01T00:00:00+00:00",
            ttl=3600,
            signature="sig123"
        )
        
        data = peer.to_dict()
        assert data["peer_id"] == "abc123"
        assert data["entity_id"] == "test-entity"
        assert "signature" not in data  # Signature excluded from signing data
    
    def test_peer_info_json_serialization(self):
        """Test JSON serialization"""
        peer = PeerInfo(
            peer_id="abc123",
            entity_id="test-entity",
            entity_name="Test Entity",
            endpoint="localhost:8000",
            public_key="dGVzdC1rZXk=",
            capabilities=["discovery"],
            timestamp="2026-01-01T00:00:00+00:00",
            ttl=3600,
            signature="sig123"
        )
        
        json_str = peer.to_json()
        restored = PeerInfo.from_json(json_str)
        
        assert restored.peer_id == peer.peer_id
        assert restored.entity_id == peer.entity_id
        assert restored.signature == peer.signature
    
    def test_peer_info_expired(self):
        """Test expiration check"""
        # Expired peer (old timestamp)
        old_time = "2020-01-01T00:00:00+00:00"
        expired_peer = PeerInfo(
            peer_id="old",
            entity_id="old-entity",
            entity_name="Old",
            endpoint="localhost:8000",
            public_key="key=",
            capabilities=[],
            timestamp=old_time,
            ttl=3600
        )
        
        assert expired_peer.is_expired() is True
        
        # Fresh peer
        fresh_peer = PeerInfo(
            peer_id="new",
            entity_id="new-entity",
            entity_name="New",
            endpoint="localhost:8000",
            public_key="key=",
            capabilities=[],
            timestamp=datetime.now(timezone.utc).isoformat(),
            ttl=3600
        )
        
        assert fresh_peer.is_expired() is False


class TestLoadBootstrapNodes:
    """Test bootstrap node loading"""
    
    def test_load_bootstrap_nodes_empty(self):
        """Test loading from non-existent file"""
        nodes = load_bootstrap_nodes("non_existent.json")
        assert nodes == []
    
    @patch('builtins.open')
    @patch('json.load')
    def test_load_bootstrap_nodes_valid(self, mock_json_load, mock_open):
        """Test loading valid bootstrap config"""
        mock_json_load.return_value = {
            "bootstrap_servers": [
                {"dht_endpoint": "host1:8468"},
                {"dht_endpoint": "host2:8469"}
            ],
            "local_bootstrap": [
                {"dht_endpoint": "localhost:8470"}
            ]
        }
        
        nodes = load_bootstrap_nodes("config.json")
        
        assert len(nodes) == 3
        assert ("host1", 8468) in nodes
        assert ("host2", 8469) in nodes
        assert ("localhost", 8470) in nodes


class TestDHTRegistry:
    """Test DHTRegistry class"""
    
    def test_registry_creation(self):
        """Test DHTRegistry initialization"""
        registry = DHTRegistry(
            entity_id="test-entity",
            entity_name="Test Entity",
            endpoint="localhost:8000",
            public_key="dGVzdC1rZXk=",
            private_key=None,
            capabilities=["discovery"],
            bootstrap_nodes=[("host1", 8468)],
            auto_load_bootstrap=False
        )
        
        assert registry.entity_id == "test-entity"
        assert registry.port == 8468
        assert len(registry.bootstrap_nodes) == 1
    
    def test_peer_id_generation(self):
        """Test peer_id is generated from public_key"""
        import hashlib
        public_key = "test-public-key"
        expected_peer_id = hashlib.sha256(public_key.encode()).hexdigest()
        
        registry = DHTRegistry(
            entity_id="test",
            entity_name="Test",
            endpoint="localhost:8000",
            public_key=public_key,
            auto_load_bootstrap=False
        )
        
        assert registry.peer_id == expected_peer_id
    
    def test_add_bootstrap_node(self):
        """Test dynamic bootstrap node addition"""
        registry = DHTRegistry(
            entity_id="test",
            entity_name="Test",
            endpoint="localhost:8000",
            public_key="key",
            auto_load_bootstrap=False
        )
        
        registry.add_bootstrap_node("new-host", 9000)
        
        assert ("new-host", 9000) in registry.bootstrap_nodes
    
    def test_get_stats(self):
        """Test stats retrieval"""
        registry = DHTRegistry(
            entity_id="test-entity",
            entity_name="Test",
            endpoint="localhost:8000",
            public_key="dGVzdC1rZXk=",
            capabilities=["discovery", "messaging"],
            auto_load_bootstrap=False
        )
        
        stats = registry.get_stats()
        
        assert stats["entity_id"] == "test-entity"
        assert stats["running"] is False
        assert "discovery" in stats["capabilities"]
    
    def test_peer_discovered_callback(self):
        """Test peer discovery callbacks"""
        registry = DHTRegistry(
            entity_id="test",
            entity_name="Test",
            endpoint="localhost:8000",
            public_key="key",
            auto_load_bootstrap=False
        )
        
        callback_called = []
        
        def callback(peer_info):
            callback_called.append(peer_info)
        
        registry.add_peer_discovered_callback(callback)
        
        assert callback in registry._peer_discovered_callbacks
        
        registry.remove_peer_discovered_callback(callback)
        
        assert callback not in registry._peer_discovered_callbacks


class TestGlobalRegistry:
    """Test global registry functions"""
    
    def test_create_and_get_registry(self):
        """Test global registry creation and retrieval"""
        reset_dht_registry()
        
        assert get_dht_registry() is None
        
        registry = create_dht_registry(
            entity_id="global-test",
            entity_name="Global Test",
            endpoint="localhost:8000",
            public_key="dGVzdC1rZXk=",
            capabilities=["test"]
        )
        
        assert registry is not None
        assert get_dht_registry() is registry
        assert get_dht_registry().entity_id == "global-test"
        
        reset_dht_registry()
        assert get_dht_registry() is None


# Async tests
@pytest.mark.asyncio
class TestDHTRegistryAsync:
    """Async tests for DHTRegistry"""
    
    async def test_registry_start_without_kademlia(self):
        """Test start when kademlia is not available"""
        with patch('services.dht_registry.KADEMLIA_AVAILABLE', False):
            registry = DHTRegistry(
                entity_id="test",
                entity_name="Test",
                endpoint="localhost:8000",
                public_key="key",
                auto_load_bootstrap=False
            )
            
            result = await registry.start()
            assert result is False
    
    async def test_lookup_peer_without_server(self):
        """Test lookup when server is not running"""
        registry = DHTRegistry(
            entity_id="test",
            entity_name="Test",
            endpoint="localhost:8000",
            public_key="key",
            auto_load_bootstrap=False
        )
        
        result = await registry.lookup_peer("any-peer")
        assert result is None
    
    async def test_discover_peers_without_server(self):
        """Test discover when server is not running"""
        registry = DHTRegistry(
            entity_id="test",
            entity_name="Test",
            endpoint="localhost:8000",
            public_key="key",
            auto_load_bootstrap=False
        )
        
        result = await registry.discover_peers(count=5)
        assert result == []


if __name__ == "__main__":
    # Run basic tests
    print("Running PeerInfo tests...")
    
    peer_test = TestPeerInfo()
    peer_test.test_peer_info_creation()
    print("✓ test_peer_info_creation")
    
    peer_test.test_peer_info_to_dict()
    print("✓ test_peer_info_to_dict")
    
    peer_test.test_peer_info_json_serialization()
    print("✓ test_peer_info_json_serialization")
    
    peer_test.test_peer_info_expired()
    print("✓ test_peer_info_expired")
    
    print("\nRunning DHTRegistry tests...")
    
    registry_test = TestDHTRegistry()
    registry_test.test_registry_creation()
    print("✓ test_registry_creation")
    
    registry_test.test_peer_id_generation()
    print("✓ test_peer_id_generation")
    
    registry_test.test_get_stats()
    print("✓ test_get_stats")
    
    print("\nRunning Global Registry tests...")
    
    global_test = TestGlobalRegistry()
    global_test.test_create_and_get_registry()
    print("✓ test_create_and_get_registry")
    
    print("\n✅ All tests passed!")
