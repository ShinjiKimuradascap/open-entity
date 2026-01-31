#!/usr/bin/env python3
"""
Tests for WebSocket Manager
WebSocketマネージャーの単体テスト

Coverage:
- Connection management (connect/disconnect)
- Session routing
- Message sending (send_to_peer, send_to_session, broadcast)
- Rate limiting (100 msg/min per connection)
- Message size limits (1MB max)
- Heartbeat/ping-pong
"""

import asyncio
import json
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
import time

# Import the module under test
try:
    from services.websocket_manager import (
        WebSocketManager,
        WebSocketMessage,
        ConnectionInfo,
        ConnectionState,
        WSMessageType,
        WebSocketRateLimiter,
        get_websocket_manager,
        init_websocket_manager,
        shutdown_websocket_manager,
    )
    from services.session_manager import SessionManager
    WEBSOCKET_MANAGER_AVAILABLE = True
except ImportError as e:
    WEBSOCKET_MANAGER_AVAILABLE = False
    print(f"WebSocket manager import failed: {e}")


class TestWebSocketMessage(unittest.TestCase):
    """Test WebSocketMessage dataclass"""
    
    def test_message_creation(self):
        """Test creating a WebSocket message"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        msg = WebSocketMessage(
            message_id="msg-001",
            msg_type="PEER_MESSAGE",
            version="1.1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            sender_id="entity_a",
            session_id="sess-001",
            recipient_id="entity_b",
            payload={"data": "test"}
        )
        
        self.assertEqual(msg.message_id, "msg-001")
        self.assertEqual(msg.msg_type, "PEER_MESSAGE")
        self.assertEqual(msg.sender_id, "entity_a")
        self.assertEqual(msg.recipient_id, "entity_b")
    
    def test_message_to_dict(self):
        """Test converting message to dictionary"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        msg = WebSocketMessage(
            message_id="msg-002",
            msg_type="PING",
            version="1.1",
            timestamp="2026-01-01T00:00:00Z",
            sender_id="entity_a",
            session_id=None,
            recipient_id=None,
            payload={}
        )
        
        data = msg.to_dict()
        
        self.assertEqual(data["message_id"], "msg-002")
        self.assertEqual(data["type"], "PING")
        self.assertEqual(data["sender_id"], "entity_a")
    
    def test_message_from_dict(self):
        """Test creating message from dictionary"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        data = {
            "message_id": "msg-003",
            "type": "PONG",
            "version": "1.1",
            "timestamp": "2026-01-01T00:00:00Z",
            "sender_id": "entity_b",
            "session_id": "sess-002",
            "recipient_id": "entity_a",
            "payload": {"status": "ok"}
        }
        
        msg = WebSocketMessage.from_dict(data)
        
        self.assertEqual(msg.message_id, "msg-003")
        self.assertEqual(msg.msg_type, "PONG")
        self.assertEqual(msg.session_id, "sess-002")


class TestConnectionInfo(unittest.TestCase):
    """Test ConnectionInfo dataclass"""
    
    def test_default_values(self):
        """Test default connection info values"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        info = ConnectionInfo()
        
        self.assertIsNone(info.peer_id)
        self.assertIsNone(info.session_id)
        self.assertEqual(info.state, ConnectionState.CONNECTING)
        self.assertEqual(info.message_count, 0)
        self.assertEqual(info.bytes_received, 0)
        self.assertEqual(info.bytes_sent, 0)
    
    def test_rate_limit_check(self):
        """Test rate limiting check"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        info = ConnectionInfo()
        
        # First 5 messages should be allowed
        for i in range(5):
            result = asyncio.run(info.check_rate_limit(max_messages=5, window_seconds=60))
            self.assertTrue(result, f"Message {i+1} should be allowed")
        
        # 6th message should be denied
        result = asyncio.run(info.check_rate_limit(max_messages=5, window_seconds=60))
        self.assertFalse(result, "6th message should be rate limited")


class TestWebSocketRateLimiter(unittest.TestCase):
    """Test WebSocketRateLimiter"""
    
    def test_rate_limit_basic(self):
        """Test basic rate limiting"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        limiter = WebSocketRateLimiter(max_messages=5, window_seconds=60)
        entity_id = "test_entity"
        
        # First 5 messages should be allowed
        for i in range(5):
            self.assertTrue(limiter.is_allowed(entity_id), f"Message {i+1} should be allowed")
        
        # 6th message should be denied
        self.assertFalse(limiter.is_allowed(entity_id), "6th message should be rate limited")
    
    def test_rate_limit_remaining(self):
        """Test remaining message count"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        limiter = WebSocketRateLimiter(max_messages=10, window_seconds=60)
        entity_id = "test_entity"
        
        self.assertEqual(limiter.get_remaining(entity_id), 10)
        
        limiter.is_allowed(entity_id)
        self.assertEqual(limiter.get_remaining(entity_id), 9)
        
        limiter.is_allowed(entity_id)
        limiter.is_allowed(entity_id)
        self.assertEqual(limiter.get_remaining(entity_id), 7)


class TestWebSocketManager(unittest.TestCase):
    """Test WebSocketManager core functionality"""
    
    def setUp(self):
        """Set up test fixtures"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            return
        
        self.manager = WebSocketManager()
    
    def tearDown(self):
        """Clean up after tests"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            return
        
        # Clean up any remaining state
        asyncio.run(self._cleanup())
    
    async def _cleanup(self):
        """Async cleanup helper"""
        if hasattr(self, 'manager') and self.manager:
            await self.manager.stop()
    
    def test_initialization(self):
        """Test manager initialization"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        self.assertEqual(self.manager.max_message_size, 1024 * 1024)  # 1MB
        self.assertEqual(self.manager.heartbeat_interval, 30)
        self.assertEqual(self.manager.heartbeat_timeout, 40)
        self.assertFalse(self.manager._running)
    
    def test_start_stop(self):
        """Test manager start and stop"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        asyncio.run(self.manager.start())
        self.assertTrue(self.manager._running)
        
        asyncio.run(self.manager.stop())
        self.assertFalse(self.manager._running)
    
    def test_connect_disconnect(self):
        """Test peer connection and disconnection"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            
            # Connect
            result = await self.manager.connect(mock_ws, "peer_1")
            self.assertTrue(result)
            self.assertIn("peer_1", self.manager.active_connections)
            
            # Disconnect
            await self.manager.disconnect("peer_1")
            self.assertNotIn("peer_1", self.manager.active_connections)
        
        asyncio.run(test())
    
    def test_session_routing(self):
        """Test session registration and routing"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            
            # Connect with session
            result = await self.manager.connect(mock_ws, "peer_1", session_id="sess_001")
            self.assertTrue(result)
            
            # Check session routing
            self.assertEqual(self.manager.get_peer_by_session("sess_001"), "peer_1")
            
            # Unregister session
            result = await self.manager.unregister_session("sess_001")
            self.assertTrue(result)
            self.assertIsNone(self.manager.get_peer_by_session("sess_001"))
        
        asyncio.run(test())
    
    def test_send_to_peer(self):
        """Test sending message to peer"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            await self.manager.connect(mock_ws, "peer_1")
            
            message = {"type": "HELLO", "payload": {"data": "test"}}
            result = await self.manager.send_to_peer("peer_1", message)
            
            self.assertTrue(result)
            mock_ws.send_text.assert_called_once()
        
        asyncio.run(test())
    
    def test_send_to_session(self):
        """Test sending message by session ID"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            await self.manager.connect(mock_ws, "peer_1", session_id="sess_001")
            
            message = {"type": "HELLO", "payload": {"data": "test"}}
            result = await self.manager.send_to_session("sess_001", message)
            
            self.assertTrue(result)
            mock_ws.send_text.assert_called_once()
        
        asyncio.run(test())
    
    def test_broadcast(self):
        """Test broadcasting to all peers"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            await self.manager.connect(mock_ws1, "peer_1")
            await self.manager.connect(mock_ws2, "peer_2")
            
            message = {"type": "BROADCAST", "payload": {"data": "hello all"}}
            results = await self.manager.broadcast(message)
            
            self.assertEqual(len(results), 2)
            self.assertTrue(results["peer_1"])
            self.assertTrue(results["peer_2"])
        
        asyncio.run(test())
    
    def test_is_connected(self):
        """Test connection status check"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            
            self.assertFalse(self.manager.is_connected("peer_1"))
            
            await self.manager.connect(mock_ws, "peer_1")
            self.assertTrue(self.manager.is_connected("peer_1"))
            
            await self.manager.disconnect("peer_1")
            self.assertFalse(self.manager.is_connected("peer_1"))
        
        asyncio.run(test())
    
    def test_get_connected_peers(self):
        """Test getting list of connected peers"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws1 = AsyncMock()
        mock_ws1.accept = AsyncMock()
        mock_ws2 = AsyncMock()
        mock_ws2.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            
            # Initially no peers
            peers = self.manager.get_connected_peers()
            self.assertEqual(len(peers), 0)
            
            # Add peers
            await self.manager.connect(mock_ws1, "peer_1")
            await self.manager.connect(mock_ws2, "peer_2")
            
            peers = self.manager.get_connected_peers()
            self.assertEqual(len(peers), 2)
            self.assertIn("peer_1", peers)
            self.assertIn("peer_2", peers)
        
        asyncio.run(test())
    
    def test_message_size_limit(self):
        """Test message size limit enforcement"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        # Create message larger than 1MB
        large_payload = "x" * (2 * 1024 * 1024)  # 2MB
        message = {"type": "LARGE", "payload": large_payload}
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            await self.manager.connect(mock_ws, "peer_1")
            
            result = await self.manager.send_to_peer("peer_1", message)
            self.assertFalse(result)  # Should be rejected due to size
        
        asyncio.run(test())
    
    def test_stats(self):
        """Test statistics tracking"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        
        async def test():
            await self.manager.start()
            
            initial_stats = self.manager.get_stats()
            self.assertEqual(initial_stats["connections_active"], 0)
            
            await self.manager.connect(mock_ws, "peer_1")
            
            stats = self.manager.get_stats()
            self.assertEqual(stats["connections_total"], 1)
            self.assertEqual(stats["connections_active"], 1)
        
        asyncio.run(test())


class TestGlobalFunctions(unittest.TestCase):
    """Test global helper functions"""
    
    def test_get_websocket_manager(self):
        """Test singleton pattern for manager"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        manager1 = get_websocket_manager()
        manager2 = get_websocket_manager()
        
        self.assertIs(manager1, manager2)
    
    def test_init_shutdown_websocket_manager(self):
        """Test init and shutdown functions"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        async def test():
            manager = await init_websocket_manager()
            self.assertIsNotNone(manager)
            self.assertTrue(manager._running)
            
            await shutdown_websocket_manager()
            self.assertFalse(manager._running)
        
        asyncio.run(test())


class TestWSMessageTypes(unittest.TestCase):
    """Test WebSocket message type constants"""
    
    def test_message_types(self):
        """Test message type constants are defined"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        self.assertEqual(WSMessageType.PING, "ping")
        self.assertEqual(WSMessageType.PONG, "pong")
        self.assertEqual(WSMessageType.PEER_MESSAGE, "peer_message")
        self.assertEqual(WSMessageType.BROADCAST, "broadcast")
        self.assertEqual(WSMessageType.ERROR, "error")
        self.assertEqual(WSMessageType.STATUS, "status")


class TestConnectionState(unittest.TestCase):
    """Test connection state enum"""
    
    def test_states(self):
        """Test connection states"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        self.assertEqual(ConnectionState.CONNECTING.value, "connecting")
        self.assertEqual(ConnectionState.CONNECTED.value, "connected")
        self.assertEqual(ConnectionState.READY.value, "ready")
        self.assertEqual(ConnectionState.CLOSING.value, "closing")
        self.assertEqual(ConnectionState.CLOSED.value, "closed")


class TestErrorHandling(unittest.TestCase):
    """Test error handling scenarios"""
    
    def test_send_to_nonexistent_peer(self):
        """Test sending to non-existent peer"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        manager = WebSocketManager()
        
        async def test():
            result = await manager.send_to_peer("nonexistent", {"type": "TEST"})
            self.assertFalse(result)
        
        asyncio.run(test())
    
    def test_send_to_nonexistent_session(self):
        """Test sending to non-existent session"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        manager = WebSocketManager()
        
        async def test():
            result = await manager.send_to_session("nonexistent", {"type": "TEST"})
            self.assertFalse(result)
        
        asyncio.run(test())
    
    def test_disconnect_nonexistent_peer(self):
        """Test disconnecting non-existent peer"""
        if not WEBSOCKET_MANAGER_AVAILABLE:
            self.skipTest("WebSocket manager not available")
        
        manager = WebSocketManager()
        
        async def test():
            # Should not raise exception
            await manager.disconnect("nonexistent")
        
        asyncio.run(test())


def run_tests():
    """Run all tests"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketMessage))
    suite.addTests(loader.loadTestsFromTestCase(TestConnectionInfo))
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketRateLimiter))
    suite.addTests(loader.loadTestsFromTestCase(TestWebSocketManager))
    suite.addTests(loader.loadTestsFromTestCase(TestGlobalFunctions))
    suite.addTests(loader.loadTestsFromTestCase(TestWSMessageTypes))
    suite.addTests(loader.loadTestsFromTestCase(TestConnectionState))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    exit(0 if success else 1)
