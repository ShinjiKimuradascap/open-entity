#!/usr/bin/env python3
"""
Distributed Registry Tests
分散レジストリ機能のテスト

Tests:
- Vector clock operations
- Registry entry CRDT merge
- Gossip protocol simulation
- Entry lifecycle
- Conflict resolution
"""

import asyncio
import sys
import os
import time
from datetime import datetime, timezone, timedelta

# servicesディレクトリをパスに追加
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, WORKSPACE_DIR)

# インポート
IMPORT_SUCCESS = False
try:
    from services.distributed_registry import (
        VectorClock,
        RegistryEntry,
        EntryStatus,
        DistributedRegistry,
    )
    IMPORT_SUCCESS = True
    print("✅ Imported distributed_registry from services")
except ImportError as e1:
    try:
        from distributed_registry import (
            VectorClock,
            RegistryEntry,
            EntryStatus,
            DistributedRegistry,
        )
        IMPORT_SUCCESS = True
        print("✅ Imported distributed_registry directly")
    except ImportError as e2:
        print(f"❌ Import failed: {e1}, {e2}")
        raise


def test_vector_clock():
    """Test vector clock operations"""
    print("\n=== Vector Clock Test ===\n")
    
    # Create clocks
    vc1 = VectorClock()
    vc2 = VectorClock()
    
    # Increment
    vc1 = vc1.increment("node-a")
    assert vc1.clocks["node-a"] == 1, "Increment failed"
    print("✅ Increment works")
    
    vc1 = vc1.increment("node-a")
    vc1 = vc1.increment("node-b")
    assert vc1.clocks["node-a"] == 2
    assert vc1.clocks["node-b"] == 1
    print("✅ Multiple increments work")
    
    # Merge
    vc2 = vc2.increment("node-c")
    merged = vc1.merge(vc2)
    assert merged.clocks["node-a"] == 2
    assert merged.clocks["node-b"] == 1
    assert merged.clocks["node-c"] == 1
    print("✅ Merge works")
    
    # Compare - happens-before
    vc_a = VectorClock({"node-a": 1, "node-b": 2})
    vc_b = VectorClock({"node-a": 2, "node-b": 3})
    assert vc_a.compare(vc_b) == -1, "Should be happens-before"
    assert vc_b.compare(vc_a) == 1, "Should be happens-after"
    print("✅ Compare happens-before/after works")
    
    # Compare - concurrent
    vc_c = VectorClock({"node-a": 2, "node-b": 1})
    vc_d = VectorClock({"node-a": 1, "node-b": 2})
    assert vc_c.compare(vc_d) == 0, "Should be concurrent"
    print("✅ Compare concurrent works")
    
    # is_concurrent_with
    assert vc_c.is_concurrent_with(vc_d)
    assert not vc_a.is_concurrent_with(vc_b)
    print("✅ is_concurrent_with works")
    
    # to_dict / from_dict
    vc_dict = vc1.to_dict()
    vc_restored = VectorClock.from_dict(vc_dict)
    assert vc_restored.clocks == vc1.clocks
    print("✅ Serialization works")
    
    print("\n✅ Vector clock test passed")


def test_registry_entry():
    """Test registry entry operations"""
    print("\n=== Registry Entry Test ===\n")
    
    now = datetime.now(timezone.utc)
    
    entry = RegistryEntry(
        entity_id="test-entity-1",
        entity_name="Test Entity",
        endpoint="http://localhost:8001",
        capabilities=["task_delegation", "messaging"],
        registered_at=now,
        last_heartbeat=now,
        version=1,
        node_id="node-a",
        status=EntryStatus.ACTIVE
    )
    
    assert entry.entity_id == "test-entity-1"
    assert "task_delegation" in entry.capabilities
    print("✅ Entry creation works")
    
    # to_dict / from_dict
    entry_dict = entry.to_dict()
    restored = RegistryEntry.from_dict(entry_dict)
    assert restored.entity_id == entry.entity_id
    assert restored.endpoint == entry.endpoint
    assert restored.version == entry.version
    print("✅ Entry serialization works")
    
    # is_expired
    assert not entry.is_expired(timeout_sec=120)
    
    old_entry = RegistryEntry(
        entity_id="old-entity",
        entity_name="Old Entity",
        endpoint="http://localhost:8002",
        capabilities=[],
        registered_at=now - timedelta(seconds=200),
        last_heartbeat=now - timedelta(seconds=200),
        version=1,
        node_id="node-b"
    )
    assert old_entry.is_expired(timeout_sec=120)
    print("✅ Expiration check works")
    
    # TOMBSTONE should not be expired
    tombstone = RegistryEntry(
        entity_id="deleted-entity",
        entity_name="Deleted",
        endpoint="",
        capabilities=[],
        registered_at=now - timedelta(seconds=200),
        last_heartbeat=now - timedelta(seconds=200),
        version=1,
        node_id="node-c",
        status=EntryStatus.TOMBSTONE
    )
    assert not tombstone.is_expired(timeout_sec=120)
    print("✅ Tombstone expiration works")
    
    # is_alive
    assert entry.is_alive(timeout_sec=60)
    assert not old_entry.is_alive(timeout_sec=60)
    assert not tombstone.is_alive(timeout_sec=60)
    print("✅ Alive check works")
    
    print("\n✅ Registry entry test passed")


def test_registry_entry_merge():
    """Test CRDT merge for registry entries"""
    print("\n=== Registry Entry Merge Test ===\n")
    
    now = datetime.now(timezone.utc)
    
    # Create two versions with different vector clocks
    entry_v1 = RegistryEntry(
        entity_id="entity-1",
        entity_name="Entity",
        endpoint="http://localhost:8001",
        capabilities=["v1"],
        registered_at=now,
        last_heartbeat=now,
        version=1,
        node_id="node-a",
        vector_clock=VectorClock({"node-a": 1}),
        hlc=(1, 0)
    )
    
    entry_v2 = RegistryEntry(
        entity_id="entity-1",
        entity_name="Entity",
        endpoint="http://localhost:8001",
        capabilities=["v1", "v2"],
        registered_at=now,
        last_heartbeat=now + timedelta(seconds=1),
        version=2,
        node_id="node-a",
        vector_clock=VectorClock({"node-a": 2}),
        hlc=(2, 0)
    )
    
    # v2 happens after v1
    merged = entry_v1.merge(entry_v2)
    assert merged.version == 2
    assert "v2" in merged.capabilities
    print("✅ Simple merge (happens-after) works")
    
    # Concurrent updates - use HLC for tie-breaking
    entry_c1 = RegistryEntry(
        entity_id="entity-2",
        entity_name="Entity",
        endpoint="http://localhost:8001",
        capabilities=["c1"],
        registered_at=now,
        last_heartbeat=now,
        version=1,
        node_id="node-a",
        vector_clock=VectorClock({"node-a": 1, "node-b": 1}),
        hlc=(5, 0)
    )
    
    entry_c2 = RegistryEntry(
        entity_id="entity-2",
        entity_name="Entity",
        endpoint="http://localhost:8001",
        capabilities=["c2"],
        registered_at=now,
        last_heartbeat=now,
        version=1,
        node_id="node-b",
        vector_clock=VectorClock({"node-a": 1, "node-b": 1}),
        hlc=(3, 0)
    )
    
    # Concurrent but c1 has higher HLC
    merged = entry_c1.merge(entry_c2)
    assert "c1" in merged.capabilities
    assert merged.node_id == "node-a"
    print("✅ Concurrent merge with HLC tie-break works")
    
    print("\n✅ Registry entry merge test passed")


async def test_distributed_registry_init():
    """Test distributed registry initialization"""
    print("\n=== Distributed Registry Init Test ===\n")
    
    registry = DistributedRegistry(
        node_id="test-node-1",
        gossip_interval=30,
        cleanup_interval=300,
        max_gossip_peers=3
    )
    
    assert registry.node_id == "test-node-1"
    assert registry.gossip_interval == 30
    assert registry.max_gossip_peers == 3
    print("✅ Registry initialization correct")
    
    # Stats should be empty initially
    stats = registry.get_stats()
    assert stats["total_entries"] == 0
    # Note: active_entries was renamed to total_entries in the API
    assert stats["total_entries"] == 0
    print("✅ Initial stats correct")
    
    print("\n✅ Distributed registry init test passed")


async def test_distributed_registry_register():
    """Test service registration"""
    print("\n=== Distributed Registry Register Test ===\n")
    
    registry = DistributedRegistry(node_id="test-node")
    
    # Register a service
    entry = await registry.register_local(
        entity_id="service-1",
        entity_name="Test Service",
        endpoint="http://localhost:9001",
        capabilities=["task_delegation"]
    )
    
    assert entry is not None
    assert entry.entity_id == "service-1"
    assert entry.node_id == "test-node"
    assert entry.status == EntryStatus.ACTIVE
    print("✅ Service registration works")
    
    # Get entry
    retrieved = registry.get_entry("service-1")
    assert retrieved is not None
    assert retrieved.entity_id == "service-1"
    print("✅ Get entry works")
    
    # Find by capability
    results = registry.find_by_capability("task_delegation")
    assert len(results) == 1
    assert results[0].entity_id == "service-1"
    print("✅ Find by capability works")
    
    # Update heartbeat
    time.sleep(0.1)
    updated = registry.update_heartbeat("service-1")
    assert updated
    entry = registry.get_entry("service-1")
    assert entry.last_heartbeat > entry.registered_at
    print("✅ Heartbeat update works")
    
    # Get all entries
    all_entries = registry.get_all_entries()
    assert len(all_entries) == 1
    print("✅ Get all entries works")
    
    # Get digest
    digest = registry.get_digest()
    assert "service-1" in digest
    assert digest["service-1"] >= 1
    print("✅ Get digest works")
    
    print("\n✅ Distributed registry register test passed")


async def test_distributed_registry_merge():
    """Test registry entry merging"""
    print("\n=== Distributed Registry Merge Test ===\n")
    
    registry = DistributedRegistry(node_id="test-node")
    
    now = datetime.now(timezone.utc)
    
    # Create entry from another node
    remote_entry = RegistryEntry(
        entity_id="remote-service",
        entity_name="Remote Service",
        endpoint="http://remote:8001",
        capabilities=["remote-cap"],
        registered_at=now,
        last_heartbeat=now,
        version=1,
        node_id="remote-node",
        vector_clock=VectorClock({"remote-node": 1}),
        hlc=(1, 0)
    )
    
    # Merge entry
    merged = registry.merge_entry(remote_entry)
    assert merged
    print("✅ Merge remote entry works")
    
    # Get merged entry
    entry = registry.get_entry("remote-service")
    assert entry is not None
    assert entry.entity_id == "remote-service"
    assert "remote-cap" in entry.capabilities
    print("✅ Merged entry retrieval works")
    
    # Try to merge older version (should be rejected)
    older_entry = RegistryEntry(
        entity_id="remote-service",
        entity_name="Remote Service",
        endpoint="http://remote:8001",
        capabilities=["old-cap"],
        registered_at=now,
        last_heartbeat=now,
        version=1,
        node_id="remote-node",
        vector_clock=VectorClock({"remote-node": 0}),
        hlc=(0, 0)
    )
    
    merged = registry.merge_entry(older_entry)
    assert not merged  # Should reject older version
    entry = registry.get_entry("remote-service")
    assert "remote-cap" in entry.capabilities  # Should still have newer cap
    print("✅ Older entry rejection works")
    
    print("\n✅ Distributed registry merge test passed")


async def test_cleanup_expired():
    """Test cleanup of expired entries"""
    print("\n=== Cleanup Expired Test ===\n")
    
    registry = DistributedRegistry(node_id="test-node")
    now = datetime.now(timezone.utc)
    
    # Register fresh entry
    await registry.register_local(
        entity_id="fresh-service",
        entity_name="Fresh",
        endpoint="http://localhost:9001",
        capabilities=[]
    )
    
    # Manually add expired entry (from different node so it can be cleaned up)
    expired_entry = RegistryEntry(
        entity_id="expired-service",
        entity_name="Expired",
        endpoint="http://localhost:9002",
        capabilities=[],
        registered_at=now - timedelta(seconds=200),
        last_heartbeat=now - timedelta(seconds=200),
        version=1,
        node_id="other-node"
    )
    registry._entries["expired-service"] = expired_entry
    
    # Cleanup
    removed = registry.cleanup_expired()
    assert removed == 1, f"Should remove 1 expired, removed {removed}"
    
    # Check entries
    assert registry.get_entry("fresh-service") is not None
    assert registry.get_entry("expired-service") is None
    print("✅ Expired entry cleanup works")
    
    print("\n✅ Cleanup expired test passed")


async def run_all_tests():
    """Run all distributed registry tests"""
    print("\n" + "="*60)
    print("Distributed Registry Tests")
    print("="*60)
    
    if not IMPORT_SUCCESS:
        print("❌ Import failed, cannot run tests")
        return False
    
    tests = [
        ("Vector Clock", test_vector_clock),
        ("Registry Entry", test_registry_entry),
        ("Registry Entry Merge", test_registry_entry_merge),
        ("Distributed Registry Init", test_distributed_registry_init),
        ("Distributed Registry Register", test_distributed_registry_register),
        ("Distributed Registry Merge", test_distributed_registry_merge),
        ("Cleanup Expired", test_cleanup_expired),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            if asyncio.iscoroutinefunction(test_func):
                await test_func()
            else:
                test_func()
            passed += 1
        except Exception as e:
            print(f"\n❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "="*60)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
