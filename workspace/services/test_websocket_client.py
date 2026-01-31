#!/usr/bin/env python3
"""
Tests for WebSocket Client
WebSocketクライアントのテスト
"""

import asyncio
import unittest
from unittest.mock import Mock, patch, AsyncMock
import json
import time

# Import the module under test
try:
    from services.websocket_client import (
        WebSocketPeerClient,
        WebSocketMessage,
        WebSocketClientConfig,
        WebSocketClientState,
        create_websocket_client,
        get_client_registry
    )
    WEBSOCKET_CLIENT_AVAILABLE = True
except ImportError as e:
    WEBSOCKET_CLIENT_AVAILABLE = False
    print(f"WebSocket client import failed: {e}")


class TestWebSocketMessage(unittest.TestCase):
    """Test WebSocketMessage dataclass"""
    
    def test_message_creation(self):
        """Test creating a message"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        msg = WebSocketMessage(
            type="HELLO",
            from_entity="entity_a",
            to_entity="entity_b",
            payload={"test": "data"}
        )
        
        self.assertEqual(msg.type, "HELLO")
        self.assertEqual(msg.from_entity, "entity_a")
        self.assertEqual(msg.to_entity, "entity_b")
        self.assertEqual(msg.payload, {"test": "data"})
        self.assertIsNotNone(msg.message_id)
        self.assertIsNotNone(msg.timestamp)
    
    def test_message_to_dict(self):
        """Test converting message to dict"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        msg = WebSocketMessage(
            type="MESSAGE",
            from_entity="entity_a",
            payload={"key": "value"}
        )
        
        data = msg.to_dict()
        
        self.assertEqual(data["type"], "MESSAGE")
        self.assertEqual(data["from_entity"], "entity_a")
        self.assertEqual(data["payload"], {"key": "value"})
        self.assertIn("message_id", data)
        self.assertIn("timestamp", data)
    
    def test_message_from_dict(self):
        """Test creating message from dict"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        data = {
            "message_id": "test-id",
            "type": "ACK",
            "from_entity": "entity_b",
            "to_entity": "entity_a",
            "timestamp": 1234567890,
            "payload": {"status": "ok"},
            "signature": None
        }
        
        msg = WebSocketMessage.from_dict(data)
        
        self.assertEqual(msg.message_id, "test-id")
        self.assertEqual(msg.type, "ACK")
        self.assertEqual(msg.from_entity, "entity_b")
        self.assertEqual(msg.payload, {"status": "ok"})


class TestWebSocketClientConfig(unittest.TestCase):
    """Test WebSocketClientConfig"""
    
    def test_default_config(self):
        """Test default configuration values"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        config = WebSocketClientConfig(entity_id="test_entity")
        
        self.assertEqual(config.entity_id, "test_entity")
        self.assertEqual(config.reconnect_interval, 5.0)
        self.assertEqual(config.max_reconnect_attempts, 10)
        self.assertEqual(config.heartbeat_interval, 30.0)
        self.assertEqual(config.connection_timeout, 10.0)
        self.assertTrue(config.enable_http_fallback)
        self.assertIsNone(config.http_fallback_url)
    
    def test_custom_config(self):
        """Test custom configuration"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        config = WebSocketClientConfig(
            entity_id="test_entity",
            reconnect_interval=10.0,
            max_reconnect_attempts=5,
            heartbeat_interval=60.0,
            enable_http_fallback=False
        )
        
        self.assertEqual(config.reconnect_interval, 10.0)
        self.assertEqual(config.max_reconnect_attempts, 5)
        self.assertEqual(config.heartbeat_interval, 60.0)
        self.assertFalse(config.enable_http_fallback)


class TestWebSocketPeerClient(unittest.TestCase):
    """Test WebSocketPeerClient"""
    
    def test_client_initialization(self):
        """Test client initialization"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        client = WebSocketPeerClient(entity_id="test_entity")
        
        self.assertEqual(client.entity_id, "test_entity")
        self.assertEqual(client.state, WebSocketClientState.DISCONNECTED)
        self.assertFalse(client.is_connected)
        self.assertIsNone(client.private_key)
    
    def test_client_with_config(self):
        """Test client with custom config"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        config = WebSocketClientConfig(
            entity_id="test_entity",
            heartbeat_interval=45.0
        )
        client = WebSocketPeerClient(
            entity_id="test_entity",
            config=config
        )
        
        self.assertEqual(client.config.heartbeat_interval, 45.0)
    
    def test_callback_registration(self):
        """Test callback registration"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        client = WebSocketPeerClient(entity_id="test_entity")
        
        message_handler = Mock()
        error_handler = Mock()
        connection_handler = Mock()
        
        client.on_message(message_handler)
        client.on_error(error_handler)
        client.on_connection_change(connection_handler)
        
        self.assertEqual(client._message_handler, message_handler)
        self.assertEqual(client._error_handler, error_handler)
        self.assertEqual(client._connection_handler, connection_handler)
    
    def test_get_stats(self):
        """Test getting client statistics"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        client = WebSocketPeerClient(entity_id="test_entity")
        stats = client.get_stats()
        
        self.assertEqual(stats["entity_id"], "test_entity")
        self.assertEqual(stats["state"], "disconnected")
        self.assertEqual(stats["messages_sent"], 0)
        self.assertEqual(stats["messages_received"], 0)
        self.assertEqual(stats["reconnect_attempts"], 0)


class TestClientRegistry(unittest.TestCase):
    """Test WebSocketClientRegistry"""
    
    def test_registry_singleton(self):
        """Test registry singleton pattern"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        registry1 = get_client_registry()
        registry2 = get_client_registry()
        
        self.assertIs(registry1, registry2)
    
    def test_register_unregister_client(self):
        """Test client registration"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        registry = get_client_registry()
        client = WebSocketPeerClient(entity_id="test_entity")
        
        registry.register_client("peer_1", client)
        
        self.assertEqual(registry.get_client("peer_1"), client)
        
        registry.unregister_client("peer_1")
        
        self.assertIsNone(registry.get_client("peer_1"))


class TestFactoryFunctions(unittest.TestCase):
    """Test factory functions"""
    
    def test_create_websocket_client(self):
        """Test client factory"""
        if not WEBSOCKET_CLIENT_AVAILABLE:
            self.skipTest("WebSocket client not available")
        
        client = create_websocket_client(
            entity_id="test_entity",
            heartbeat_interval=45.0,
            enable_http_fallback=False
        )
        
        self.assertEqual(client.entity_id, "test_entity")
        self.assertEqual(client.config.heartbeat_interval, 45.0)
        self.assertFalse(client.config.enable_http_fallback)


class TestIntegration(unittest.TestCase):
    """Integration tests (requires WebSocket server)"""
    
    @unittest.skip("Requires running WebSocket server")
    def test_full_connection_flow(self):
        """Test full connection flow with server"""
        pass
    
    @unittest.skip("Requires running WebSocket server")
    def test_message_send_receive(self):
        """Test sending and receiving messages"""
        pass


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketMessage))
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketClientConfig))
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketPeerClient))
    suite.addTests(loader.loadTestsFromTestCase(TestClientRegistry))
    suite.addTests(loader.loadTestsFromTestCase(TestFactoryFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
