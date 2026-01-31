#!/usr/bin/env python3
"""Tests for WebSocket Transport"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from websocket_transport import (
    WebSocketClient,
    WebSocketServer,
    WSMessage,
    WSConnectionState,
    create_websocket_server
)


async def test_ws_message_serialization():
    """Test WebSocket message serialization"""
    msg = WSMessage(
        message_type="test",
        payload={"data": "hello"},
        sender_id="user-1"
    )
    
    # Serialize
    json_str = msg.to_json()
    assert "test" in json_str
    assert "hello" in json_str
    
    # Deserialize
    msg2 = WSMessage.from_json(json_str)
    assert msg2.message_type == "test"
    assert msg2.payload["data"] == "hello"
    assert msg2.sender_id == "user-1"
    
    print("  test_ws_message_serialization: PASSED")


async def test_websocket_server():
    """Test WebSocket server creation"""
    messages = []
    
    async def handler(entity_id, msg):
        messages.append((entity_id, msg))
    
    server = await create_websocket_server(
        host="127.0.0.1",
        port=8766,
        message_handler=handler
    )
    
    assert server is not None
    
    await server.stop()
    print("  test_websocket_server: PASSED")


async def test_client_state():
    """Test client connection state"""
    client = WebSocketClient(
        uri="ws://127.0.0.1:8767",
        entity_id="test-entity"
    )
    
    assert client.state == WSConnectionState.DISCONNECTED
    assert not client.is_connected
    
    print("  test_client_state: PASSED")


async def main():
    print("=== WebSocket Transport Tests ===\n")
    
    try:
        await test_ws_message_serialization()
        await test_websocket_server()
        await test_client_state()
        print("\n=== All tests passed! ===")
        return 0
    except Exception as e:
        print(f"\n=== FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
