#!/usr/bin/env python3
"""Bootstrap Discovery + DHT統合テスト"""
import sys
import os
import asyncio

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

print('=== Bootstrap Discovery + DHT Integration Test ===')

try:
    # 1. kademlia_dhtからインポート
    from services.kademlia_dht import DHTRegistry, PeerInfo
    print('✅ kademlia_dht インポート成功')
    
    # 2. bootstrap_discoveryからインポート
    from services.bootstrap_discovery import (
        BootstrapDiscoveryManager, 
        BootstrapNodeInfo,
        DiscoveryStats,
        DiscoveryMode
    )
    print('✅ bootstrap_discovery インポート成功')
    
    # 3. DiscoveryManagerのインスタンス化テスト
    print('\n--- DiscoveryManager インスタンス化 ---')
    manager = BootstrapDiscoveryManager(
        entity_id="test-entity",
        entity_name="Test Entity",
        endpoint="http://localhost:8000",
        public_key="test-public-key",
        capabilities=["discovery", "relay"],
        discovery_mode=DiscoveryMode.HTTP_ONLY  # DHTなしでテスト
    )
    print(f'✅ DiscoveryManager作成成功')
    print(f'   entity_id: {manager.entity_id}')
    print(f'   discovery_mode: {manager.discovery_mode}')
    print(f'   KADEMLIA_AVAILABLE: {manager._get_dht_bootstrap_addresses}')
    
    # 4. Statsメソッド確認
    stats = manager.get_stats()
    print(f'\n--- Stats ---')
    print(f'   total_nodes: {stats["total_nodes"]}')
    print(f'   dht_available: {stats["dht_available"]}')
    print(f'   dht_running: {stats["dht_running"]}')
    
    # 5. Bootstrap config読み込み確認
    print(f'\n--- Bootstrap Config ---')
    addrs = manager._get_dht_bootstrap_addresses()
    print(f'   DHT bootstrap addresses: {addrs}')
    
    print('\n✅ 全てのテスト成功')
    
except ImportError as e:
    print(f'❌ インポート失敗: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f'❌ エラー: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

print('\n=== テスト完了 ===')
