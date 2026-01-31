#!/usr/bin/env python3
"""
DHT統合テストスクリプト

M1完了: DHTとPeerService統合テスト
- discover_peers_via_dht
- register_to_dht
- get_peer_from_dht
"""

import asyncio
import sys
import os
import time
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, MagicMock

# servicesディレクトリをパスに追加
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE_DIR = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, WORKSPACE_DIR)

# インポート
import_error_details = []
IMPORT_SUCCESS = False

try:
    from services.peer_service import PeerService
    from services.dht_registry import PeerInfo, DHTRegistry
    from services.crypto import generate_entity_keypair
    IMPORT_SUCCESS = True
    print("✅ Imported using package pattern")
except ImportError as e1:
    import_error_details.append(f"Pattern 1 failed: {e1}")
    try:
        from peer_service import PeerService
        from dht_registry import PeerInfo, DHTRegistry
        from crypto import generate_entity_keypair
        IMPORT_SUCCESS = True
        print("✅ Imported using direct pattern")
    except ImportError as e2:
        import_error_details.append(f"Pattern 2 failed: {e2}")

if not IMPORT_SUCCESS:
    print("❌ Import errors:")
    for detail in import_error_details:
        print(f"   - {detail}")
    raise ImportError(f"Failed to import required modules")


class MockDHTRegistry:
    """テスト用のDHTRegistryモック"""
    
    def __init__(self):
        self.peers = {}
        self.registered_self = False
        
    async def discover_peers(self, count: int = 10):
        """ピア発見のモック"""
        return list(self.peers.values())[:count]
    
    async def find_by_capability(self, capability: str):
        """機能でピアを検索するモック"""
        return [
            peer for peer in self.peers.values()
            if capability in peer.capabilities
        ]
    
    async def lookup_peer(self, peer_id: str):
        """ピア検索のモック"""
        return self.peers.get(peer_id)
    
    async def _register_self(self):
        """自身を登録するモック"""
        self.registered_self = True
        return True
    
    def add_mock_peer(self, peer_info: PeerInfo):
        """テスト用ピアを追加"""
        self.peers[peer_info.peer_id] = peer_info


def create_test_peer_info(entity_id: str, entity_name: str, endpoint: str, 
                          capabilities: list = None) -> PeerInfo:
    """テスト用PeerInfoを作成"""
    priv_key, pub_key = generate_entity_keypair()
    peer_id = f"test_peer_{entity_id}_{int(time.time())}"
    
    return PeerInfo(
        peer_id=peer_id,
        entity_id=entity_id,
        entity_name=entity_name,
        endpoint=endpoint,
        public_key=pub_key,
        capabilities=capabilities or ["messaging", "task_delegation"],
        timestamp=datetime.now(timezone.utc).isoformat(),
        signature="test_signature"
    )


async def test_discover_peers_via_dht():
    """discover_peers_via_dhtのテスト"""
    print("\n=== Test: discover_peers_via_dht ===\n")
    
    # テスト用の鍵を生成
    priv_key, pub_key = generate_entity_keypair()
    
    # PeerServiceを作成（DHTなし）
    service = PeerService(
        entity_id="test-entity",
        host="localhost",
        port=8001,
        private_key_hex=priv_key,
        public_key_hex=pub_key,
        enable_dht=False
    )
    
    # テスト1: DHTがない場合は空リストを返す
    print("Test 1: DHT not available")
    result = await service.discover_peers_via_dht(count=10)
    assert result == [], f"Expected empty list, got {result}"
    print("✅ Returns empty list when DHT not available")
    
    # テスト2: DHTありの場合
    print("\nTest 2: With DHT registry")
    mock_dht = MockDHTRegistry()
    
    # モックピアを追加
    peer1 = create_test_peer_info("peer-1", "Peer One", "http://localhost:8002")
    peer2 = create_test_peer_info("peer-2", "Peer Two", "http://localhost:8003", 
                                   capabilities=["messaging", "storage"])
    mock_dht.add_mock_peer(peer1)
    mock_dht.add_mock_peer(peer2)
    
    # DHTレジストリを設定
    service._dht_registry = mock_dht
    service._auto_discover = False  # 自動追加を無効化
    
    result = await service.discover_peers_via_dht(count=10)
    
    assert len(result) == 2, f"Expected 2 peers, got {len(result)}"
    print(f"✅ Discovered {len(result)} peers")
    
    # ピア情報の検証
    entity_ids = [p["entity_id"] for p in result]
    assert "peer-1" in entity_ids, "peer-1 not found"
    assert "peer-2" in entity_ids, "peer-2 not found"
    print("✅ Peer info structure is correct")
    
    # テスト3: 機能フィルタリング
    print("\nTest 3: Capability filtering")
    result = await service.discover_peers_via_dht(capability="storage")
    
    assert len(result) == 1, f"Expected 1 peer with storage capability, got {len(result)}"
    assert result[0]["entity_id"] == "peer-2", "Expected peer-2 with storage capability"
    print("✅ Capability filtering works")
    
    # テスト4: 自身を除外
    print("\nTest 4: Self exclusion")
    self_peer = create_test_peer_info("test-entity", "Test Entity", "http://localhost:8001")
    mock_dht.add_mock_peer(self_peer)
    
    result = await service.discover_peers_via_dht(count=10)
    entity_ids = [p["entity_id"] for p in result]
    
    assert "test-entity" not in entity_ids, "Self should be excluded"
    print("✅ Self is correctly excluded from discovery")
    
    print("\n✅ All discover_peers_via_dht tests passed!")
    return True


async def test_register_to_dht():
    """register_to_dhtのテスト"""
    print("\n=== Test: register_to_dht ===\n")
    
    # テスト用の鍵を生成
    priv_key, pub_key = generate_entity_keypair()
    
    service = PeerService(
        entity_id="test-entity",
        host="localhost",
        port=8001,
        private_key_hex=priv_key,
        public_key_hex=pub_key,
        enable_dht=False
    )
    
    # テスト1: DHTがない場合はFalseを返す
    print("Test 1: DHT not available")
    result = await service.register_to_dht()
    assert result == False, f"Expected False, got {result}"
    print("✅ Returns False when DHT not available")
    
    # テスト2: DHTありの場合
    print("\nTest 2: With DHT registry")
    mock_dht = MockDHTRegistry()
    service._dht_registry = mock_dht
    
    result = await service.register_to_dht()
    assert result == True, f"Expected True, got {result}"
    assert mock_dht.registered_self == True, "Expected _register_self to be called"
    print("✅ Successfully registers to DHT")
    
    print("\n✅ All register_to_dht tests passed!")
    return True


async def test_get_peer_from_dht():
    """get_peer_from_dhtのテスト"""
    print("\n=== Test: get_peer_from_dht ===\n")
    
    # テスト用の鍵を生成
    priv_key, pub_key = generate_entity_keypair()
    
    service = PeerService(
        entity_id="test-entity",
        host="localhost",
        port=8001,
        private_key_hex=priv_key,
        public_key_hex=pub_key,
        enable_dht=False
    )
    
    # テスト1: DHTがない場合はNoneを返す
    print("Test 1: DHT not available")
    result = await service.get_peer_from_dht("some_peer_id")
    assert result is None, f"Expected None, got {result}"
    print("✅ Returns None when DHT not available")
    
    # テスト2: DHTありの場合
    print("\nTest 2: With DHT registry")
    mock_dht = MockDHTRegistry()
    
    # モックピアを追加
    peer1 = create_test_peer_info("peer-1", "Peer One", "http://localhost:8002")
    mock_dht.add_mock_peer(peer1)
    
    service._dht_registry = mock_dht
    
    # 存在するピアを検索
    result = await service.get_peer_from_dht(peer1.peer_id)
    assert result is not None, "Expected peer info, got None"
    assert result["entity_id"] == "peer-1", f"Expected peer-1, got {result['entity_id']}"
    assert result["endpoint"] == "http://localhost:8002", "Endpoint mismatch"
    print("✅ Successfully retrieves existing peer")
    
    # テスト3: 存在しないピアを検索
    print("\nTest 3: Non-existent peer")
    result = await service.get_peer_from_dht("non_existent_id")
    assert result is None, f"Expected None for non-existent peer, got {result}"
    print("✅ Returns None for non-existent peer")
    
    print("\n✅ All get_peer_from_dht tests passed!")
    return True


async def test_auto_discover_with_dht():
    """auto_discover_with_dhtのテスト"""
    print("\n=== Test: auto_discover_with_dht ===\n")
    
    priv_key, pub_key = generate_entity_keypair()
    
    service = PeerService(
        entity_id="test-entity",
        host="localhost",
        port=8001,
        private_key_hex=priv_key,
        public_key_hex=pub_key,
        enable_dht=False
    )
    
    # テスト1: auto_discoverが無効の場合
    print("Test 1: Auto discover disabled")
    service._auto_discover = False
    result = await service.auto_discover_with_dht()
    assert result == 0, f"Expected 0, got {result}"
    print("✅ Returns 0 when auto_discover is disabled")
    
    # テスト2: auto_discoverが有効でDHTあり
    print("\nTest 2: Auto discover with DHT")
    mock_dht = MockDHTRegistry()
    
    peer1 = create_test_peer_info("peer-1", "Peer One", "http://localhost:8002")
    peer2 = create_test_peer_info("peer-2", "Peer Two", "http://localhost:8003")
    mock_dht.add_mock_peer(peer1)
    mock_dht.add_mock_peer(peer2)
    
    service._dht_registry = mock_dht
    service._auto_discover = True
    
    result = await service.auto_discover_with_dht()
    assert result == 2, f"Expected 2 peers added, got {result}"
    assert "peer-1" in service.peers, "peer-1 should be added to peers"
    assert "peer-2" in service.peers, "peer-2 should be added to peers"
    print(f"✅ Added {result} peers automatically")
    
    print("\n✅ All auto_discover_with_dht tests passed!")
    return True


async def run_all_tests():
    """すべてのテストを実行"""
    print("=" * 60)
    print("DHT Integration Tests")
    print("=" * 60)
    
    tests = [
        ("discover_peers_via_dht", test_discover_peers_via_dht),
        ("register_to_dht", test_register_to_dht),
        ("get_peer_from_dht", test_get_peer_from_dht),
        ("auto_discover_with_dht", test_auto_discover_with_dht),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            await test_func()
            passed += 1
        except Exception as e:
            failed += 1
            print(f"\n❌ Test {name} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
