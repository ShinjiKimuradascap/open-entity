#!/usr/bin/env python3
"""
Peer Discovery Service (LEGACY - DEPRECATED)
自動ピア発見・接続機能

⚠️ DEPRECATION NOTICE:
    このモジュールは非推奨です。v1.2以降は services/bootstrap_discovery.py の
    BootstrapDiscoveryManager を使用してください。
    
    BootstrapDiscoveryManager の利点:
    - 再帰的ブートストラップ発見（最大深度3）
    - Ed25519署名検証
    - 到達可能性スコアリング
    - DHT統合（HYBRIDモード対応）
    
    移行例:
        # 古い方法（非推奨）
        from peer_discovery import PeerDiscovery
        discovery = PeerDiscovery()
        
        # 新しい方法（推奨）
        from bootstrap_discovery import BootstrapDiscoveryManager
        manager = BootstrapDiscoveryManager(entity_id=..., public_key=...)
        
機能（レガシー）:
- ブートストラップノードからの発見
- Moltbook経由での発見
- レジストリ照会による発見
- ピア交換による発見 (gossip)

削除予定: v1.3
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Set, Callable
from pathlib import Path

import aiohttp
from aiohttp import ClientTimeout

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class BootstrapNode:
    """ブートストラップノード情報"""
    node_id: str
    endpoint: str
    public_key: Optional[str] = None
    last_seen: Optional[datetime] = None
    is_reachable: bool = False


@dataclass
class DiscoveryResult:
    """発見結果"""
    peers_found: List[Dict]
    source: str  # bootstrap, moltbook, registry, gossip
    timestamp: datetime


class PeerDiscovery:
    """ピア発見サービス
    
    複数のソースからピアを発見し、接続候補を提供する。
    """
    
    # デフォルトブートストラップノード
    DEFAULT_BOOTSTRAP_NODES = [
        BootstrapNode(
            node_id="bootstrap-1",
            endpoint="https://ai-collaboration-1.example.com",
        ),
    ]
    
    def __init__(
        self,
        bootstrap_file: Optional[str] = None,
        enable_moltbook: bool = True,
        enable_registry: bool = True,
        enable_gossip: bool = True
    ):
        """PeerDiscoveryを初期化
        
        Args:
            bootstrap_file: ブートストラップノードリストのJSONファイルパス
            enable_moltbook: Moltbook統合を有効化
            enable_registry: レジストリ照会を有効化
            enable_gossip: Gossipプロトコルを有効化
        """
        self.bootstrap_nodes: List[BootstrapNode] = []
        self.enable_moltbook = enable_moltbook
        self.enable_registry = enable_registry
        self.enable_gossip = enable_gossip
        self._discovered_peers: Dict[str, Dict] = {}
        self._last_discovery: Optional[datetime] = None
        self._session: Optional[aiohttp.ClientSession] = None
        
        # ブートストラップノードを読み込み
        self._load_bootstrap_nodes(bootstrap_file)
    
    def _load_bootstrap_nodes(self, bootstrap_file: Optional[str] = None):
        """ブートストラップノードリストを読み込み"""
        # ファイルが指定されている場合は読み込み
        if bootstrap_file and Path(bootstrap_file).exists():
            try:
                with open(bootstrap_file, 'r') as f:
                    data = json.load(f)
                    for node_data in data.get('nodes', []):
                        self.bootstrap_nodes.append(BootstrapNode(**node_data))
                logger.info(f"Loaded {len(self.bootstrap_nodes)} bootstrap nodes from {bootstrap_file}")
            except Exception as e:
                logger.warning(f"Failed to load bootstrap file: {e}")
        
        # デフォルトノードを追加（ファイルが空または存在しない場合）
        if not self.bootstrap_nodes:
            self.bootstrap_nodes = self.DEFAULT_BOOTSTRAP_NODES.copy()
            logger.info(f"Using {len(self.bootstrap_nodes)} default bootstrap nodes")
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """HTTPセッションを取得（必要に応じて作成）"""
        if self._session is None or self._session.closed:
            timeout = ClientTimeout(total=10, connect=5)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
    
    async def close(self):
        """セッションを閉じる"""
        if self._session and not self._session.closed:
            await self._session.close()
    
    def save_bootstrap_nodes(self, filepath: str):
        """ブートストラップノードリストを保存"""
        data = {
            'nodes': [
                {
                    'node_id': node.node_id,
                    'endpoint': node.endpoint,
                    'public_key': node.public_key,
                    'last_seen': node.last_seen.isoformat() if node.last_seen else None,
                    'is_reachable': node.is_reachable
                }
                for node in self.bootstrap_nodes
            ],
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"Saved bootstrap nodes to {filepath}")
    
    async def discover_peers(self) -> List[DiscoveryResult]:
        """全ソースからピアを発見
        
        Returns:
            各ソースからの発見結果リスト
        """
        results = []
        
        # 1. ブートストラップノードから発見
        bootstrap_result = await self._discover_from_bootstrap()
        if bootstrap_result.peers_found:
            results.append(bootstrap_result)
        
        # 2. Moltbookから発見
        if self.enable_moltbook:
            moltbook_result = await self._discover_from_moltbook()
            if moltbook_result.peers_found:
                results.append(moltbook_result)
        
        # 3. レジストリから発見
        if self.enable_registry:
            registry_result = await self._discover_from_registry()
            if registry_result.peers_found:
                results.append(registry_result)
        
        self._last_discovery = datetime.now(timezone.utc)
        
        # 結果を統合
        self._merge_discovery_results(results)
        
        total_peers = sum(len(r.peers_found) for r in results)
        logger.info(f"Discovery completed: {total_peers} peers found from {len(results)} sources")
        
        return results
    
    async def _discover_from_bootstrap(self) -> DiscoveryResult:
        """ブートストラップノードからピアを発見"""
        peers = []
        
        for node in self.bootstrap_nodes:
            try:
                session = await self._get_session()
                # ノードのレジストリを照会
                url = f"{node.endpoint}/discover"
                async with session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            node.is_reachable = True
                            node.last_seen = datetime.now(timezone.utc)
                            
                            # エージェントリストを追加
                            for agent in data.get('agents', []):
                                peers.append({
                                    'entity_id': agent['entity_id'],
                                    'endpoint': agent['endpoint'],
                                    'capabilities': agent.get('capabilities', []),
                                    'source': f"bootstrap:{node.node_id}",
                                    'discovered_at': datetime.now(timezone.utc).isoformat()
                                })
                        else:
                            node.is_reachable = False
                            
            except Exception as e:
                logger.debug(f"Bootstrap node {node.node_id} unreachable: {e}")
                node.is_reachable = False
        
        return DiscoveryResult(
            peers_found=peers,
            source="bootstrap",
            timestamp=datetime.now(timezone.utc)
        )
    
    async def _discover_from_moltbook(self) -> DiscoveryResult:
        """Moltbookからピアを発見"""
        peers = []
        
        try:
            # Moltbookクライアントを使用
            from services.moltbook_identity_client import init_client as init_moltbook_client
            
            client = init_moltbook_client()
            # MoltbookのAPIでエージェント一覧を取得
            # 注: 実際のMoltbook APIに合わせて調整が必要
            
            # ハートビートで自分の存在を告知
            await client.heartbeat()
            
        except Exception as e:
            logger.debug(f"Moltbook discovery failed: {e}")
        
        return DiscoveryResult(
            peers_found=peers,
            source="moltbook",
            timestamp=datetime.now(timezone.utc)
        )
    
    async def _discover_from_registry(self) -> DiscoveryResult:
        """ローカルレジストリからピアを発見"""
        peers = []
        
        try:
            from registry import get_registry
            registry = get_registry()
            
            for service in registry.list_all():
                if service.is_alive():
                    peers.append({
                        'entity_id': service.entity_id,
                        'endpoint': service.endpoint,
                        'capabilities': service.capabilities,
                        'source': 'registry',
                        'discovered_at': datetime.now(timezone.utc).isoformat()
                    })
        except Exception as e:
            logger.debug(f"Registry discovery failed: {e}")
        
        return DiscoveryResult(
            peers_found=peers,
            source="registry",
            timestamp=datetime.now(timezone.utc)
        )
    
    def _merge_discovery_results(self, results: List[DiscoveryResult]):
        """発見結果を統合"""
        for result in results:
            for peer in result.peers_found:
                peer_id = peer['entity_id']
                if peer_id not in self._discovered_peers:
                    self._discovered_peers[peer_id] = peer
                    logger.debug(f"New peer discovered: {peer_id} from {result.source}")
    
    def get_discovered_peers(self, min_sources: int = 1) -> List[Dict]:
        """発見済みピアを取得
        
        Args:
            min_sources: 最低必要な発見ソース数
            
        Returns:
            ピア情報のリスト
        """
        return list(self._discovered_peers.values())
    
    def get_peer_by_capability(self, capability: str) -> List[Dict]:
        """特定の機能を持つピアを検索"""
        return [
            peer for peer in self._discovered_peers.values()
            if capability in peer.get('capabilities', [])
        ]
    
    async def check_peer_connectivity(self, peer_id: str) -> bool:
        """ピアの接続可能性をチェック"""
        if peer_id not in self._discovered_peers:
            return False
        
        peer = self._discovered_peers[peer_id]
        endpoint = peer.get('endpoint')
        
        if not endpoint:
            return False
        
        try:
            session = await self._get_session()
            url = f"{endpoint}/health"
            async with session.get(url) as response:
                    is_healthy = response.status == 200
                    peer['last_check'] = datetime.now(timezone.utc).isoformat()
                    peer['is_healthy'] = is_healthy
                    return is_healthy
        except Exception as e:
            logger.debug(f"Peer {peer_id} health check failed: {e}")
            peer['is_healthy'] = False
            return False
    
    async def add_bootstrap_node(self, node_id: str, endpoint: str, public_key: Optional[str] = None):
        """ブートストラップノードを追加"""
        node = BootstrapNode(
            node_id=node_id,
            endpoint=endpoint,
            public_key=public_key
        )
        self.bootstrap_nodes.append(node)
        logger.info(f"Added bootstrap node: {node_id} at {endpoint}")
    
    def get_stats(self) -> Dict:
        """発見統計を取得"""
        return {
            'total_discovered': len(self._discovered_peers),
            'bootstrap_nodes': len(self.bootstrap_nodes),
            'reachable_bootstrap_nodes': sum(1 for n in self.bootstrap_nodes if n.is_reachable),
            'last_discovery': self._last_discovery.isoformat() if self._last_discovery else None,
            'sources': {
                'moltbook': self.enable_moltbook,
                'registry': self.enable_registry,
                'gossip': self.enable_gossip
            }
        }


# グローバルインスタンス
_discovery: Optional[PeerDiscovery] = None


def init_discovery(
    bootstrap_file: Optional[str] = None,
    enable_moltbook: bool = True,
    enable_registry: bool = True,
    enable_gossip: bool = True
) -> PeerDiscovery:
    """発見サービスを初期化"""
    global _discovery
    _discovery = PeerDiscovery(
        bootstrap_file=bootstrap_file,
        enable_moltbook=enable_moltbook,
        enable_registry=enable_registry,
        enable_gossip=enable_gossip
    )
    return _discovery


def get_discovery() -> Optional[PeerDiscovery]:
    """発見サービスインスタンスを取得"""
    return _discovery


async def main():
    """テスト実行"""
    discovery = init_discovery()
    
    # ピア発見を実行
    results = await discovery.discover_peers()
    
    print(f"Discovery results:")
    for result in results:
        print(f"  Source: {result.source}")
        print(f"  Peers found: {len(result.peers_found)}")
        for peer in result.peers_found:
            print(f"    - {peer['entity_id']} at {peer['endpoint']}")
    
    # 統計を表示
    stats = discovery.get_stats()
    print(f"\nStats: {stats}")


if __name__ == "__main__":
    asyncio.run(main())
