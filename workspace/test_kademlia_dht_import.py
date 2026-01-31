#!/usr/bin/env python3
"""kademlia_dhtモジュールインポートテスト"""
import sys
import os

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

print('=== kademlia_dht.py インポートテスト ===')

try:
    from services.kademlia_dht import DHTRegistry, PeerInfo, create_dht_registry
    print('✅ インポート成功')
    print(f'  DHTRegistry: {DHTRegistry}')
    print(f'  PeerInfo: {PeerInfo}')
    print(f'  create_dht_registry: {create_dht_registry}')
    
    # PeerInfoのテスト
    peer = PeerInfo(
        peer_id="test-entity",
        endpoint="http://localhost:8000",
        public_key="test-key",
        capabilities=["chat", "code"]
    )
    print(f'\n  PeerInfo作成成功:')
    print(f'    peer_id: {peer.peer_id}')
    print(f'    endpoint: {peer.endpoint}')
    print(f'    to_dict: {peer.to_dict()}')
    
    # DHTRegistryの存在確認
    print(f'\n  DHTRegistryメソッド:')
    print(f'    start: {hasattr(DHTRegistry, "start")}')
    print(f'    stop: {hasattr(DHTRegistry, "stop")}')
    print(f'    register_peer: {hasattr(DHTRegistry, "register_peer")}')
    print(f'    lookup_peer: {hasattr(DHTRegistry, "lookup_peer")}')
    print(f'    discover_random_peers: {hasattr(DHTRegistry, "discover_random_peers")}')
    
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
