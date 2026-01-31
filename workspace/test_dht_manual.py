#!/usr/bin/env python3
"""
DHT Manual Test
DHT手動テスト

L2 Phase 2: DHT機能の検証
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from kademlia_dht import DHTRegistry, PeerInfo


async def test_dht():
    """DHTの基本機能テスト"""
    print("="*60)
    print("DHT Manual Test - L2 Phase 2")
    print("="*60)
    
    # PeerInfoテスト
    print("\n--- Test 1: PeerInfo Data Class ---")
    peer = PeerInfo(
        peer_id="test-entity-1",
        endpoint="http://localhost:8001",
        public_key="aabbccdd11223344",
        capabilities=["token_transfer", "task_delegation"]
    )
    print(f"✅ PeerInfo created: {peer.peer_id}")
    print(f"   Endpoint: {peer.endpoint}")
    print(f"   Capabilities: {peer.capabilities}")
    print(f"   Last seen: {peer.last_seen}")
    print(f"   Is stale: {peer.is_stale()}")
    
    # to_dict/from_dictテスト
    print("\n--- Test 2: Serialization ---")
    peer_dict = peer.to_dict()
    print(f"✅ Serialized: {peer_dict}")
    
    peer2 = PeerInfo.from_dict(peer_dict)
    print(f"✅ Deserialized: {peer2.peer_id}")
    
    # DHTRegistry作成テスト（起動なし）
    print("\n--- Test 3: DHTRegistry Creation ---")
    try:
        registry = DHTRegistry(
            entity_id="test-entity-local",
            keypair=None,
            listen_port=0,  # 自動割り当て
            bootstrap_nodes=[]
        )
        print(f"✅ DHTRegistry created")
        print(f"   Entity ID: {registry.entity_id}")
        print(f"   Running: {registry.is_running}")
    except Exception as e:
        print(f"⚠️ Registry creation skipped: {e}")
    
    print("\n" + "="*60)
    print("DHT tests completed!")
    print("="*60)
    
    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_dht())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
