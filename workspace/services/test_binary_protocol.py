#!/usr/bin/env python3
"""Tests for Binary Protocol (CBOR)"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from binary_protocol import (
    CBORCodec,
    BinaryMessage,
    BinaryProtocolHandler,
    MessageType,
    ProtocolVersion,
    build_heartbeat_payload,
    build_handshake_payload,
    build_task_payload,
    CBOR_AVAILABLE
)


async def test_cbor_encoding():
    """Test CBOR encoding/decoding"""
    codec = CBORCodec()
    
    message = BinaryMessage(
        message_type=MessageType.HEARTBEAT,
        payload={"status": "ok", "count": 42},
        sender_id="test-entity",
        message_id="msg-001"
    )
    
    # Encode
    encoded = codec.encode(message)
    assert len(encoded) > 4  # Has header
    
    # Decode
    decoded = codec.decode(encoded)
    assert decoded is not None
    assert decoded.message_type == MessageType.HEARTBEAT
    assert decoded.payload["status"] == "ok"
    assert decoded.payload["count"] == 42
    assert decoded.sender_id == "test-entity"
    
    print("  test_cbor_encoding: PASSED")


async def test_size_comparison():
    """Test CBOR vs JSON size comparison"""
    codec = CBORCodec()
    
    message = BinaryMessage(
        message_type=MessageType.DATA,
        payload={
            "large_data": "x" * 1000,
            "numbers": list(range(100))
        }
    )
    
    comparison = codec.compare_size(message)
    
    assert "cbor" in comparison
    assert "json" in comparison
    assert "savings" in comparison
    assert "savings_percent" in comparison
    
    # CBOR should generally be smaller
    if CBOR_AVAILABLE:
        assert comparison["cbor"] <= comparison["json"]
    
    print(f"    CBOR: {comparison['cbor']} bytes")
    print(f"    JSON: {comparison['json']} bytes")
    print(f"    Savings: {comparison['savings_percent']}%")
    print("  test_size_comparison: PASSED")


async def test_protocol_handler():
    """Test binary protocol handler"""
    handler = BinaryProtocolHandler()
    
    # Encode message
    encoded = handler.encode_message(
        msg_type=MessageType.TASK,
        payload={"action": "process"},
        sender_id="entity-a"
    )
    
    # Feed data
    messages = handler.feed_data(encoded)
    
    assert len(messages) == 1
    assert messages[0].message_type == MessageType.TASK
    assert messages[0].payload["action"] == "process"
    
    print("  test_protocol_handler: PASSED")


async def test_payload_builders():
    """Test message payload builders"""
    # Heartbeat
    hb = build_heartbeat_payload("entity-1")
    assert hb["entity_id"] == "entity-1"
    assert hb["type"] == "heartbeat"
    
    # Handshake
    hs = build_handshake_payload("entity-1", supported_versions=["1.2"])
    assert hs["entity_id"] == "entity-1"
    assert "1.2" in hs["supported_versions"]
    
    # Task
    task = build_task_payload("task-1", "compute", {"x": 10}, priority=1)
    assert task["task_id"] == "task-1"
    assert task["priority"] == 1
    
    print("  test_payload_builders: PASSED")


async def test_multiple_messages():
    """Test handling multiple messages in buffer"""
    handler = BinaryProtocolHandler()
    
    # Create multiple messages
    msg1 = handler.encode_message(MessageType.HEARTBEAT, {"n": 1})
    msg2 = handler.encode_message(MessageType.HEARTBEAT, {"n": 2})
    msg3 = handler.encode_message(MessageType.DATA, {"n": 3})
    
    # Combine
    combined = msg1 + msg2 + msg3
    
    # Feed combined data
    messages = handler.feed_data(combined)
    
    assert len(messages) == 3
    assert messages[0].payload["n"] == 1
    assert messages[1].payload["n"] == 2
    assert messages[2].payload["n"] == 3
    
    print("  test_multiple_messages: PASSED")


async def main():
    print("=== Binary Protocol (CBOR) Tests ===")
    print(f"CBOR available: {CBOR_AVAILABLE}\n")
    
    try:
        await test_cbor_encoding()
        await test_size_comparison()
        await test_protocol_handler()
        await test_payload_builders()
        await test_multiple_messages()
        print("\n=== All tests passed! ===")
        return 0
    except Exception as e:
        print(f"\n=== FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
