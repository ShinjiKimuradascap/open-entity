#!/usr/bin/env python3
"""
DHTモジュールのテスト
"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.dht import (
    KademliaDHT, KBucket, NodeInfo, DHTValue,
    generate_node_id, xor_distance, compute_dht_key,
    node_id_to_hex, hex_to_node_id, DHTPeerDiscovery,
    K_BUCKET_SIZE, ALPHA_PARALLELISM, T_EXPIRE, T_REFRESH
)
from datetime import datetime, timezone


async def test_node_id_generation():
    """ノードID生成テスト"""
    print("\n=== Test: Node ID Generation ===")
    
    node_id = generate_node_id()
    assert len(node_id) == 20, "Node ID should be 160 bits (20 bytes)"
    
    hex_str = node_id_to_hex(node_id)
    assert len(hex_str) == 40, "Hex representation should be 40 chars"
    
    recovered = hex_to_node_id(hex_str)
    assert recovered == node_id, "Hex conversion should be reversible"
    
    print(f"✓ Node ID generated: {hex_str[:16]}...")


async def test_xor_distance():
    """XOR距離計算テスト"""
    print("\n=== Test: XOR Distance ===")
    
    a = bytes([0] * 20)
    b = bytes([255] * 20)
    c = bytes([0] * 20)
    
    dist_ab = xor_distance(a, b)
    dist_ac = xor_distance(a, c)
    dist_aa = xor_distance(a, a)
    
    assert dist_aa == 0, "Distance to self should be 0"
    assert dist_ac == 0, "Distance between identical IDs should be 0"
    assert dist_ab > 0, "Distance should be positive"
    
    print(f"✓ XOR distance calculated: {dist_ab}")


async def test_kbucket():
    """KBucketテスト"""
    print("\n=== Test: KBucket ===")
    
    bucket = KBucket(k=3)
    
    # ノード追加
    for i in range(3):
        node = NodeInfo(
            node_id=generate_node_id(),
            address=f"127.0.0.1:800{i}"
        )
        success = await bucket.add(node)
        assert success, f"Should add node {i}"
    
    # バケット満杯時のテスト
    node_extra = NodeInfo(
        node_id=generate_node_id(),
        address="127.0.0.1:8999"
    )
    success = await bucket.add(node_extra)
    # 古いノードがいない場合は追加失敗
    
    nodes = bucket.get_all_nodes()
    assert len(nodes) == 3, "Bucket should have 3 nodes"
    
    print(f"✓ KBucket operations working: {len(nodes)} nodes stored")


async def test_dht_key_computation():
    """DHTキー計算テスト"""
    print("\n=== Test: DHT Key Computation ===")
    
    key1 = compute_dht_key("entity-a")
    key2 = compute_dht_key("entity-a", "chat")
    key3 = compute_dht_key("entity-b")
    
    assert len(key1) == 32, "Key should be 256 bits (32 bytes)"
    assert key1 != key2, "Keys with different capabilities should differ"
    assert key1 != key3, "Keys for different entities should differ"
    
    print(f"✓ DHT keys computed: {key1.hex()[:16]}..., {key2.hex()[:16]}...")


async def test_kademlia_dht():
    """KademliaDHTテスト"""
    print("\n=== Test: KademliaDHT ===")
    
    dht = KademliaDHT(listen_address="127.0.0.1:8000")
    
    # 統計確認
    stats = dht.get_stats()
    assert "node_id" in stats
    assert "total_nodes" in stats
    
    print(f"✓ DHT created: {stats['node_id']}")
    
    # ノード追加
    node_id = generate_node_id()
    node = NodeInfo(
        node_id=node_id,
        address="127.0.0.1:8001"
    )
    await dht.add_node(node)
    
    stats = dht.get_stats()
    assert stats["total_nodes"] == 1, "Should have 1 node"
    
    print(f"✓ Node added: total_nodes={stats['total_nodes']}")
    
    # 最も近いノードを検索
    target = generate_node_id()
    closest = dht.get_closest_nodes(target, count=1)
    assert len(closest) == 1, "Should find closest node"
    
    print(f"✓ Closest nodes found: {len(closest)}")


async def test_dht_storage():
    """DHT値の保存・検索テスト"""
    print("\n=== Test: DHT Storage ===")
    
    dht = KademliaDHT()
    
    # 値を作成
    value = DHTValue(
        entity_id="test-entity",
        addresses=["127.0.0.1:9000"],
        public_key="test-pubkey-12345",
        capabilities=["chat", "code"],
        last_seen=datetime.now(timezone.utc)
    )
    
    # 保存
    key = compute_dht_key("test-entity")
    await dht.store(key, value)
    
    # 検索
    found = await dht.find_value(key)
    assert found is not None, "Should find stored value"
    assert found.entity_id == "test-entity"
    assert found.public_key == "test-pubkey-12345"
    
    print(f"✓ Value stored and retrieved: {found.entity_id}")


async def test_peer_discovery():
    """DHTPeerDiscoveryテスト"""
    print("\n=== Test: DHTPeerDiscovery ===")
    
    dht = KademliaDHT()
    discovery = DHTPeerDiscovery(
        dht=dht,
        entity_id="test-agent",
        public_key="pubkey-test",
        capabilities=["chat", "code"]
    )
    
    discovery.add_address("127.0.0.1:8000")
    discovery.add_address("127.0.0.1:8001")
    
    assert len(discovery.addresses) == 2
    
    print(f"✓ Discovery service created: {discovery.entity_id}")


async def run_all_tests():
    """全テスト実行"""
    print("=" * 50)
    print("DHT Module Test Suite")
    print("=" * 50)
    
    try:
        await test_node_id_generation()
        await test_xor_distance()
        await test_kbucket()
        await test_dht_key_computation()
        await test_kademlia_dht()
        await test_dht_storage()
        await test_peer_discovery()
        
        print("\n" + "=" * 50)
        print("✅ All tests passed!")
        print("=" * 50)
        return True
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        return False
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
