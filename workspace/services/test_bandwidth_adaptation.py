#!/usr/bin/env python3
"""Tests for BandwidthAdaptationManager"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bandwidth_adaptation import (
    BandwidthAdaptationManager,
    PriorityLevel,
    CongestionLevel,
    create_bandwidth_manager
)


async def test_priority_queues():
    """Test priority queue handling"""
    manager = await create_bandwidth_manager()
    
    sent_messages = []
    async def mock_send(msg):
        sent_messages.append(msg)
    
    await manager.start(mock_send)
    
    # Send messages with different priorities
    await manager.send_message("critical_msg", PriorityLevel.CRITICAL, 100)
    await manager.send_message("normal_msg", PriorityLevel.NORMAL, 100)
    await manager.send_message("low_msg", PriorityLevel.LOW, 100)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    await manager.stop()
    print("  test_priority_queues: PASSED")


async def test_congestion_detection():
    """Test congestion level detection"""
    manager = await create_bandwidth_manager(
        target_bandwidth_bps=1000,  # Very low for testing
        max_queue_size=100
    )
    
    async def mock_send(msg):
        pass
    
    await manager.start(mock_send)
    
    # Send many messages to trigger congestion
    for i in range(50):
        await manager.send_message(f"msg_{i}", PriorityLevel.NORMAL, 100)
    
    # Wait for adaptation
    await asyncio.sleep(6)
    
    status = manager.get_status()
    assert "congestion_level" in status
    
    await manager.stop()
    print("  test_congestion_detection: PASSED")


async def test_priority_lookup():
    """Test message type to priority mapping"""
    from bandwidth_adaptation import MessagePrioritizer
    
    p = MessagePrioritizer()
    assert p.get_priority_for_message_type("heartbeat") == PriorityLevel.LOW
    assert p.get_priority_for_message_type("task_urgent") == PriorityLevel.CRITICAL
    assert p.get_priority_for_message_type("chat") == PriorityLevel.NORMAL
    
    print("  test_priority_lookup: PASSED")


async def test_status_reporting():
    """Test status reporting"""
    manager = await create_bandwidth_manager()
    
    async def mock_send(msg):
        pass
    
    await manager.start(mock_send)
    
    status = manager.get_status()
    assert "congestion_level" in status
    assert "queue_sizes" in status
    assert "bandwidth_limit_bps" in status
    
    await manager.stop()
    print("  test_status_reporting: PASSED")


async def main():
    print("=== BandwidthAdaptationManager Tests ===\n")
    
    try:
        await test_priority_queues()
        await test_congestion_detection()
        await test_priority_lookup()
        await test_status_reporting()
        print("\n=== All tests passed! ===")
        return 0
    except Exception as e:
        print(f"\n=== FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
