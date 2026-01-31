#!/usr/bin/env python3
"""Tests for PersistentOfflineQueue (no pytest dependency)"""

import asyncio
import tempfile
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from persistent_offline_queue import create_offline_queue


async def test_enqueue_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = await create_offline_queue(os.path.join(tmpdir, "test.db"))
        
        msg_id = await queue.enqueue(
            sender_id="sender-1",
            recipient_id="recipient-1",
            message_type="test",
            payload={"data": "hello"},
            priority=1
        )
        
        assert msg_id is not None
        messages = await queue._get_pending_messages_for_test("recipient-1", 10)
        assert len(messages) == 1
        assert messages[0].payload["data"] == "hello"
        
        await queue.close()
        print("  test_enqueue_and_retrieve: PASSED")


async def test_mark_delivered():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = await create_offline_queue(os.path.join(tmpdir, "test.db"))
        
        msg_id = await queue.enqueue(
            sender_id="sender-1",
            recipient_id="recipient-1",
            message_type="test",
            payload={"data": "hello"}
        )
        
        await queue.mark_delivered(msg_id)
        messages = await queue._get_pending_messages_for_test("recipient-1", 10)
        assert len(messages) == 0
        
        await queue.close()
        print("  test_mark_delivered: PASSED")


async def test_retry_mechanism():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = await create_offline_queue(os.path.join(tmpdir, "test.db"))
        
        msg_id = await queue.enqueue(
            sender_id="sender-1",
            recipient_id="recipient-1",
            message_type="test",
            payload={"data": "hello"},
            max_retries=3
        )
        
        assert await queue.mark_failed(msg_id, "Error 1") is True
        assert await queue.mark_failed(msg_id, "Error 2") is True
        assert await queue.mark_failed(msg_id, "Error 3") is False
        
        await queue.close()
        print("  test_retry_mechanism: PASSED")


async def test_peer_online_offline():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = await create_offline_queue(os.path.join(tmpdir, "test.db"))
        
        await queue.enqueue(
            sender_id="sender-1", recipient_id="peer-a",
            message_type="test", payload={"msg": 1}
        )
        await queue.enqueue(
            sender_id="sender-1", recipient_id="peer-a",
            message_type="test", payload={"msg": 2}
        )
        
        messages = await queue.mark_peer_online("peer-a")
        assert len(messages) == 2
        await queue.mark_peer_offline("peer-a")
        
        await queue.close()
        print("  test_peer_online_offline: PASSED")


async def test_stats():
    with tempfile.TemporaryDirectory() as tmpdir:
        queue = await create_offline_queue(os.path.join(tmpdir, "test.db"))
        
        await queue.enqueue(
            sender_id="sender-1", recipient_id="r1",
            message_type="test", payload={"m": 1}
        )
        await queue.enqueue(
            sender_id="sender-1", recipient_id="r2",
            message_type="test", payload={"m": 2}
        )
        await queue.enqueue(
            sender_id="sender-1", recipient_id="r1",
            message_type="test", payload={"m": 3}
        )
        
        stats = await queue.get_stats()
        assert stats.total_messages == 3
        assert stats.pending == 3
        assert stats.by_recipient["r1"] == 2
        
        await queue.close()
        print("  test_stats: PASSED")


async def main():
    print("=== PersistentOfflineQueue Tests ===\n")
    
    try:
        await test_enqueue_and_retrieve()
        await test_mark_delivered()
        await test_retry_mechanism()
        await test_peer_online_offline()
        await test_stats()
        print("\n=== All tests passed! ===")
        return 0
    except Exception as e:
        print(f"\n=== FAILED: {e} ===")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
