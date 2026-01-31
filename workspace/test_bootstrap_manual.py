#!/usr/bin/env python3
"""
Bootstrap Server Manual Test
ブートストラップサーバー手動テスト

L2 Phase 1: ブートストラップ機能の検証
"""

import asyncio
import aiohttp
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from bootstrap_server import BootstrapServer, PeerStatus


async def test_bootstrap_server():
    """ブートストラップサーバーの基本機能テスト"""
    print("="*60)
    print("Bootstrap Server Manual Test - L2 Phase 1")
    print("="*60)
    
    # サーバー作成
    server = BootstrapServer(
        host="localhost",
        port=19000,
        cleanup_interval=60,
        peer_timeout=300,
    )
    print("\n✅ BootstrapServer created")
    
    # ピア登録テスト
    print("\n--- Test 1: Peer Registration ---")
    result = await server.register_peer(
        entity_id="test-entity-1",
        address="http://localhost:8001",
        public_key="aabbccdd11223344",
        capabilities=["token_transfer", "task_delegation"]
    )
    print(f"Register peer 1: {'✅ OK' if result else '❌ Failed'}")
    
    result = await server.register_peer(
        entity_id="test-entity-2",
        address="http://localhost:8002",
        public_key="eeffgghh55667788",
        capabilities=["governance"]
    )
    print(f"Register peer 2: {'✅ OK' if result else '❌ Failed'}")
    
    # ピアリスト取得テスト
    print("\n--- Test 2: Peer Discovery ---")
    peers = await server.get_peer_list(count=10)
    print(f"Found {len(peers)} peers:")
    for peer in peers:
        print(f"  - {peer.entity_id}: {peer.address}")
        print(f"    Capabilities: {peer.capabilities}")
    
    # 特定ピア検索テスト
    print("\n--- Test 3: Find Specific Peer ---")
    peer = await server.find_peer("test-entity-1")
    if peer:
        print(f"✅ Found: {peer.entity_id} at {peer.address}")
    else:
        print("❌ Peer not found")
    
    # ハートビートテスト
    print("\n--- Test 4: Heartbeat ---")
    result = await server.update_last_seen("test-entity-1")
    print(f"Heartbeat: {'✅ OK' if result else '❌ Failed'}")
    
    # 統計情報
    print("\n--- Test 5: Statistics ---")
    print(f"Total peers: {len(server._peers)}")
    print(f"Stats: {server._stats}")
    
    # クリーンアップテスト
    print("\n--- Test 6: Cleanup ---")
    await server._cleanup_old_peers()
    print("✅ Cleanup completed")
    
    print("\n" + "="*60)
    print("All manual tests completed!")
    print("="*60)
    
    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_bootstrap_server())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
