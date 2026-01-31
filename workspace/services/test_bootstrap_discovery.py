#!/usr/bin/env python3
"""
Bootstrap Discovery Manager Tests
"""

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
import pytest

from bootstrap_discovery import (
    BootstrapNodeInfo,
    BootstrapDiscoveryManager,
    DiscoveryStats
)


class TestBootstrapNodeInfo:
    """BootstrapNodeInfoのテスト"""
    
    def test_creation(self):
        node = BootstrapNodeInfo(
            node_id="test-node-1",
            endpoint="https://test.example.com",
            public_key="abc123",
            is_verified=True
        )
        assert node.node_id == "test-node-1"
        assert node.endpoint == "https://test.example.com"
        assert node.reachability_score == 0.0


class TestBootstrapDiscoveryManager:
    """BootstrapDiscoveryManagerのテスト"""
    
    @pytest.fixture
    def temp_cache(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"nodes": []}')
            yield f.name
        Path(f.name).unlink(missing_ok=True)
    
    @pytest.fixture
    def manager(self, temp_cache):
        return BootstrapDiscoveryManager(
            verify_signatures=False,
            max_depth=2,
            cache_file=temp_cache
        )
    
    @pytest.mark.asyncio
    async def test_initialization(self, manager):
        assert manager.verify_signatures == False
        assert manager.max_depth == 2
        assert len(manager._nodes) == 0
    
    @pytest.mark.asyncio
    async def test_get_best_nodes(self, manager):
        # テストノードを追加
        manager._nodes["node1"] = BootstrapNodeInfo(
            node_id="node1",
            endpoint="https://node1.example.com",
            reachability_score=80.0,
            is_verified=True
        )
        manager._nodes["node2"] = BootstrapNodeInfo(
            node_id="node2",
            endpoint="https://node2.example.com",
            reachability_score=90.0,
            is_verified=False
        )
        
        # スコア順にソートされることを確認
        best = manager.get_best_nodes(count=2)
        assert len(best) == 2
        assert best[0].node_id == "node2"  # スコア90
        assert best[1].node_id == "node1"  # スコア80
    
    @pytest.mark.asyncio
    async def test_get_best_nodes_verified_only(self, manager):
        manager._nodes["verified"] = BootstrapNodeInfo(
            node_id="verified",
            endpoint="https://verified.example.com",
            reachability_score=50.0,
            is_verified=True
        )
        manager._nodes["unverified"] = BootstrapNodeInfo(
            node_id="unverified",
            endpoint="https://unverified.example.com",
            reachability_score=90.0,
            is_verified=False
        )
        
        best = manager.get_best_nodes(count=2, require_verified=True)
        assert len(best) == 1
        assert best[0].node_id == "verified"
    
    @pytest.mark.asyncio
    async def test_prune_dead_nodes(self, manager):
        from datetime import datetime, timezone, timedelta
        
        # 古いノード
        manager._nodes["old"] = BootstrapNodeInfo(
            node_id="old",
            endpoint="https://old.example.com",
            last_seen=datetime.now(timezone.utc) - timedelta(hours=48),
            is_reachable=False
        )
        # 新しいノード
        manager._nodes["new"] = BootstrapNodeInfo(
            node_id="new",
            endpoint="https://new.example.com",
            last_seen=datetime.now(timezone.utc),
            is_reachable=True
        )
        
        manager.prune_dead_nodes(max_age_hours=24)
        
        assert "old" not in manager._nodes
        assert "new" in manager._nodes
    
    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        manager._nodes["v1"] = BootstrapNodeInfo(
            node_id="v1",
            endpoint="https://v1.example.com",
            is_verified=True,
            is_reachable=True,
            reachability_score=80.0
        )
        manager._nodes["v2"] = BootstrapNodeInfo(
            node_id="v2",
            endpoint="https://v2.example.com",
            is_verified=True,
            is_reachable=False,
            reachability_score=60.0
        )
        
        stats = manager.get_stats()
        
        assert stats["total_nodes"] == 2
        assert stats["verified_nodes"] == 2
        assert stats["reachable_nodes"] == 1
        assert stats["avg_reachability_score"] == 70.0
    
    @pytest.mark.asyncio
    async def test_cache_save_load(self, temp_cache):
        # 保存
        manager1 = BootstrapDiscoveryManager(cache_file=temp_cache)
        manager1._nodes["test"] = BootstrapNodeInfo(
            node_id="test",
            endpoint="https://test.example.com",
            reachability_score=75.0
        )
        manager1._save_cache()
        
        # 読み込み
        manager2 = BootstrapDiscoveryManager(cache_file=temp_cache)
        assert "test" in manager2._nodes
        assert manager2._nodes["test"].reachability_score == 75.0


@pytest.mark.asyncio
async def test_integration_mock():
    """統合テスト（モック使用）"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        cache_file = f.name
    
    try:
        manager = BootstrapDiscoveryManager(
            verify_signatures=False,
            max_depth=1,
            cache_file=cache_file
        )
        
        # _fetch_bootstrap_nodesをモック
        mock_nodes = [
            {"node_id": "node1", "endpoint": "https://node1.example.com"},
            {"node_id": "node2", "endpoint": "https://node2.example.com"}
        ]
        
        with patch.object(manager, '_fetch_bootstrap_nodes', new_callable=AsyncMock) as mock_fetch:
            with patch.object(manager, '_test_reachability', new_callable=AsyncMock):
                mock_fetch.return_value = mock_nodes
                
                stats = await manager.discover_from_seed(
                    seed_endpoint="https://seed.example.com",
                    target_count=2
                )
                
                assert stats.nodes_discovered == 2
                assert stats.max_depth_reached == 1
                assert mock_fetch.called
        
    finally:
        Path(cache_file).unlink(missing_ok=True)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
