#!/usr/bin/env python3
"""
Bootstrap Discovery Manager Manual Test
ブートストラップディスカバリーマネージャー手動テスト

L2 Phase 1: ブートストラップ発見機能の検証
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

from bootstrap_discovery import BootstrapDiscoveryManager, DiscoveryMode


async def test_discovery_manager():
    """ディスカバリーマネージャーのテスト"""
    print("="*60)
    print("Bootstrap Discovery Manager Manual Test - L2 Phase 1")
    print("="*60)
    
    # マネージャー作成
    manager = BootstrapDiscoveryManager(
        verify_signatures=False,
        max_depth=2,
        cache_file="data/test_bootstrap_cache.json",
        discovery_mode=DiscoveryMode.HTTP_ONLY
    )
    print("\n✅ BootstrapDiscoveryManager created")
    print(f"   Mode: {manager.discovery_mode.value}")
    print(f"   Max depth: {manager.max_depth}")
    
    # 統計情報
    print("\n--- Test 1: Initial Statistics ---")
    stats = manager.get_stats()
    print(f"Stats: {stats}")
    
    # キャッシュ読み込みテスト
    print("\n--- Test 2: Cache Loading ---")
    print(f"Nodes in memory: {len(manager._nodes)}")
    
    # ベストノード取得テスト
    print("\n--- Test 3: Get Best Nodes ---")
    nodes = manager.get_best_nodes(count=5)
    print(f"Best nodes: {len(nodes)}")
    
    # 設定ファイル読み込みテスト
    print("\n--- Test 4: Bootstrap Config ---")
    try:
        import json
        with open(manager.bootstrap_config_path, 'r') as f:
            config = json.load(f)
        print(f"Bootstrap servers: {len(config.get('bootstrap_servers', []))}")
        print(f"Local bootstrap: {len(config.get('local_bootstrap', []))}")
        print(f"Known peers: {len(config.get('known_peers', []))}")
    except Exception as e:
        print(f"❌ Config error: {e}")
    
    print("\n" + "="*60)
    print("Discovery Manager tests completed!")
    print("="*60)
    
    return True


if __name__ == "__main__":
    try:
        result = asyncio.run(test_discovery_manager())
        sys.exit(0 if result else 1)
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
