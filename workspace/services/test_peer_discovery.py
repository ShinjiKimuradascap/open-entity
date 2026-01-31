#!/usr/bin/env python3
"""
Peer Discovery Service Tests
Phase1テスト実装 - peer_discovery.py

機能テスト:
- ブートストラップノード読み込み
- ピア発見フロー
- レジストリ統合
- 統計情報取得
"""

import asyncio
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from peer_discovery import (
    BootstrapNode,
    DiscoveryResult,
    PeerDiscovery,
    init_discovery,
    get_discovery
)


class TestBootstrapNode:
    """ブートストラップノードのテスト"""
    
    def test_create_bootstrap_node(self):
        """ブートストラップノードの作成"""
        node = BootstrapNode(
            node_id="test-node-1",
            endpoint="https://test.example.com",
            public_key="test_key",
            last_seen=datetime.now(timezone.utc),
            is_reachable=True
        )
        
        assert node.node_id == "test-node-1"
        assert node.endpoint == "https://test.example.com"
        assert node.public_key == "test_key"
        assert node.is_reachable is True
        print("✅ BootstrapNode creation test passed")
    
    def test_bootstrap_node_defaults(self):
        """デフォルト値のテスト"""
        node = BootstrapNode(
            node_id="test-node-2",
            endpoint="https://test2.example.com"
        )
        
        assert node.public_key is None
        assert node.last_seen is None
        assert node.is_reachable is False
        print("✅ BootstrapNode defaults test passed")


class TestDiscoveryResult:
    """発見結果のテスト"""
    
    def test_create_discovery_result(self):
        """発見結果の作成"""
        peers = [
            {
                "entity_id": "entity-1",
                "endpoint": "https://entity1.example.com",
                "capabilities": ["task_delegation"]
            }
        ]
        
        result = DiscoveryResult(
            peers_found=peers,
            source="bootstrap",
            timestamp=datetime.now(timezone.utc)
        )
        
        assert len(result.peers_found) == 1
        assert result.source == "bootstrap"
        assert result.timestamp is not None
        print("✅ DiscoveryResult creation test passed")


class TestPeerDiscovery:
    """ピア発見サービスのテスト"""
    
    def test_init_default(self):
        """デフォルト初期化"""
        discovery = PeerDiscovery()
        
        assert len(discovery.bootstrap_nodes) == 1
        assert discovery.enable_moltbook is True
        assert discovery.enable_registry is True
        assert discovery.enable_gossip is True
        print("✅ PeerDiscovery default init test passed")
    
    def test_init_custom(self):
        """カスタム初期化"""
        discovery = PeerDiscovery(
            enable_moltbook=False,
            enable_registry=False,
            enable_gossip=False
        )
        
        assert discovery.enable_moltbook is False
        assert discovery.enable_registry is False
        assert discovery.enable_gossip is False
        print("✅ PeerDiscovery custom init test passed")
    
    def test_load_bootstrap_nodes_from_file(self):
        """ファイルからブートストラップノード読み込み"""
        # テスト用JSONファイル作成
        test_data = {
            "nodes": [
                {
                    "node_id": "file-node-1",
                    "endpoint": "https://file1.example.com",
                    "public_key": "pk1",
                    "is_reachable": True
                },
                {
                    "node_id": "file-node-2",
                    "endpoint": "https://file2.example.com",
                    "public_key": "pk2",
                    "is_reachable": False
                }
            ]
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(test_data, f)
            temp_path = f.name
        
        try:
            discovery = PeerDiscovery(bootstrap_file=temp_path)
            
            assert len(discovery.bootstrap_nodes) == 2
            assert discovery.bootstrap_nodes[0].node_id == "file-node-1"
            assert discovery.bootstrap_nodes[1].endpoint == "https://file2.example.com"
            print("✅ Bootstrap nodes file loading test passed")
        finally:
            os.unlink(temp_path)
    
    def test_load_bootstrap_nodes_invalid_file(self):
        """無効なファイルの場合のフォールバック"""
        discovery = PeerDiscovery(bootstrap_file="/nonexistent/path.json")
        
        # デフォルトノードが使用される
        assert len(discovery.bootstrap_nodes) == 1
        print("✅ Bootstrap nodes invalid file test passed")
    
    def test_save_bootstrap_nodes(self):
        """ブートストラップノードの保存"""
        discovery = PeerDiscovery()
        discovery.bootstrap_nodes = [
            BootstrapNode(
                node_id="save-test-1",
                endpoint="https://save1.example.com",
                public_key="saved_pk",
                is_reachable=True
            )
        ]
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = f.name
        
        try:
            discovery.save_bootstrap_nodes(temp_path)
            
            # 保存されたファイルを読み込んで検証
            with open(temp_path, 'r') as f:
                saved_data = json.load(f)
            
            assert len(saved_data['nodes']) == 1
            assert saved_data['nodes'][0]['node_id'] == "save-test-1"
            assert 'updated_at' in saved_data
            print("✅ Bootstrap nodes save test passed")
        finally:
            os.unlink(temp_path)
    
    def test_add_bootstrap_node(self):
        """ブートストラップノード追加"""
        discovery = PeerDiscovery()
        
        discovery.add_bootstrap_node(
            node_id="added-node",
            endpoint="https://added.example.com",
            public_key="added_pk"
        )
        
        assert len(discovery.bootstrap_nodes) == 2  # デフォルト + 追加
        assert discovery.bootstrap_nodes[-1].node_id == "added-node"
        print("✅ Add bootstrap node test passed")
    
    def test_get_stats_empty(self):
        """空の状態の統計"""
        discovery = PeerDiscovery()
        
        stats = discovery.get_stats()
        
        assert stats['total_discovered'] == 0
        assert stats['bootstrap_nodes'] == 1
        assert stats['reachable_bootstrap_nodes'] == 0
        assert stats['sources']['moltbook'] is True
        print("✅ Empty stats test passed")
    
    def test_get_discovered_peers(self):
        """発見済みピアの取得"""
        discovery = PeerDiscovery()
        discovery._discovered_peers = {
            "peer-1": {
                "entity_id": "peer-1",
                "endpoint": "https://peer1.example.com",
                "capabilities": ["cap1"]
            },
            "peer-2": {
                "entity_id": "peer-2",
                "endpoint": "https://peer2.example.com",
                "capabilities": ["cap2"]
            }
        }
        
        peers = discovery.get_discovered_peers()
        
        assert len(peers) == 2
        print("✅ Get discovered peers test passed")
    
    def test_get_peer_by_capability(self):
        """機能によるピア検索"""
        discovery = PeerDiscovery()
        discovery._discovered_peers = {
            "peer-1": {
                "entity_id": "peer-1",
                "endpoint": "https://peer1.example.com",
                "capabilities": ["task_delegation", "storage"]
            },
            "peer-2": {
                "entity_id": "peer-2",
                "endpoint": "https://peer2.example.com",
                "capabilities": ["storage"]
            },
            "peer-3": {
                "entity_id": "peer-3",
                "endpoint": "https://peer3.example.com",
                "capabilities": []
            }
        }
        
        # task_delegation機能を持つピアを検索
        result = discovery.get_peer_by_capability("task_delegation")
        
        assert len(result) == 1
        assert result[0]['entity_id'] == "peer-1"
        
        # storage機能を持つピアを検索
        result = discovery.get_peer_by_capability("storage")
        
        assert len(result) == 2
        print("✅ Get peer by capability test passed")
    
    def test_merge_discovery_results(self):
        """発見結果の統合"""
        discovery = PeerDiscovery()
        
        results = [
            DiscoveryResult(
                peers_found=[
                    {"entity_id": "peer-1", "endpoint": "https://p1.example.com"}
                ],
                source="bootstrap",
                timestamp=datetime.now(timezone.utc)
            ),
            DiscoveryResult(
                peers_found=[
                    {"entity_id": "peer-1", "endpoint": "https://p1.example.com"},  # 重複
                    {"entity_id": "peer-2", "endpoint": "https://p2.example.com"}
                ],
                source="registry",
                timestamp=datetime.now(timezone.utc)
            )
        ]
        
        discovery._merge_discovery_results(results)
        
        # 重複はマージされる
        assert len(discovery._discovered_peers) == 2
        print("✅ Merge discovery results test passed")


class TestAsyncDiscovery:
    """非同期発見機能のテスト"""
    
    async def test_discover_from_registry_empty(self):
        """空のレジストリからの発見"""
        discovery = PeerDiscovery(enable_bootstrap=False)
        
        with patch('peer_discovery.get_registry') as mock_get_registry:
            mock_registry = MagicMock()
            mock_registry.list_all.return_value = []
            mock_get_registry.return_value = mock_registry
            
            result = await discovery._discover_from_registry()
            
            assert result.peers_found == []
            assert result.source == "registry"
        print("✅ Empty registry discovery test passed")
    
    async def test_check_peer_connectivity_not_found(self):
        """存在しないピアの接続チェック"""
        discovery = PeerDiscovery()
        
        result = await discovery.check_peer_connectivity("nonexistent")
        
        assert result is False
        print("✅ Check nonexistent peer test passed")


def run_sync_tests():
    """同期テスト実行"""
    print("\n" + "=" * 60)
    print("Peer Discovery Tests - Phase1")
    print("=" * 60)
    
    # BootstrapNode tests
    test = TestBootstrapNode()
    test.test_create_bootstrap_node()
    test.test_bootstrap_node_defaults()
    
    # DiscoveryResult tests
    test2 = TestDiscoveryResult()
    test2.test_create_discovery_result()
    
    # PeerDiscovery tests
    test3 = TestPeerDiscovery()
    test3.test_init_default()
    test3.test_init_custom()
    test3.test_load_bootstrap_nodes_from_file()
    test3.test_load_bootstrap_nodes_invalid_file()
    test3.test_save_bootstrap_nodes()
    test3.test_add_bootstrap_node()
    test3.test_get_stats_empty()
    test3.test_get_discovered_peers()
    test3.test_get_peer_by_capability()
    test3.test_merge_discovery_results()
    
    print("\n" + "=" * 60)
    print("All sync tests passed!")
    print("=" * 60)


async def run_async_tests():
    """非同期テスト実行"""
    test = TestAsyncDiscovery()
    await test.test_discover_from_registry_empty()
    await test.test_check_peer_connectivity_not_found()
    
    print("\nAll async tests passed!")


def test_global_instance():
    """グローバルインスタンスのテスト"""
    # 初期化前はNone
    assert get_discovery() is None
    
    # 初期化
    discovery = init_discovery()
    assert discovery is not None
    assert get_discovery() is discovery
    
    print("✅ Global instance test passed")


if __name__ == "__main__":
    # 同期テスト
    run_sync_tests()
    
    # 非同期テスト
    asyncio.run(run_async_tests())
    
    # グローバルインスタンステスト
    test_global_instance()
    
    print("\n" + "=" * 60)
    print("✅ All Phase1 peer_discovery tests passed!")
    print("=" * 60)
