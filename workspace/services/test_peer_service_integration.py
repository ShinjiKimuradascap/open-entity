#!/usr/bin/env python3
"""
Peer Service 統合テスト

Protocol v1.0/v1.1対応の統合テスト
- セッション管理
- メッセージキュー
- 死活監視
- チャンク転送
"""

import asyncio
import sys
import os
import json
import time
import secrets
from datetime import datetime, timezone
from typing import Tuple, List, Dict, Optional, Any
from dataclasses import dataclass

# servicesディレクトリをパスに追加（親ディレクトリも追加）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, os.path.dirname(SCRIPT_DIR))  # workspaceも追加

# インポート（複数パターン対応）
import_error_details = []
try:
    # パターン1: パッケージとして実行
    from services.peer_service import (
        PeerService, Session, SessionState,
        MessageQueue, HeartbeatManager, PeerStatus, ChunkInfo,
        init_service, create_server
    )
    from services.session_manager import SessionManager
    from services.crypto import generate_entity_keypair, CryptoManager, SecureMessage
    print("✅ Imported using package pattern (services.xxx)")
except ImportError as e1:
    import_error_details.append(f"Pattern 1 failed: {e1}")
    try:
        # パターン2: スクリプトとして直接実行
        from peer_service import (
            PeerService, Session, SessionState,
            MessageQueue, HeartbeatManager, PeerStatus, ChunkInfo,
            init_service, create_server
        )
        from session_manager import SessionManager
        from crypto import generate_entity_keypair, CryptoManager, SecureMessage
        print("✅ Imported using direct pattern (xxx)")
    except ImportError as e2:
        import_error_details.append(f"Pattern 2 failed: {e2}")
        print("❌ Import errors:")
        for detail in import_error_details:
            print(f"   - {detail}")
        raise ImportError(f"Failed to import required modules. Errors: {import_error_details}")


# ============================================================================
# テスト基盤クラス
# ============================================================================

class PeerServiceIntegrationTestBase:
    """統合テスト基底クラス"""
    
    def __init__(self):
        self.test_peers: List[PeerService] = []
        self.test_servers = []
        self._port_counter = 9000
        
    def _get_next_port(self) -> int:
        """次の利用可能ポートを取得"""
        port = self._port_counter
        self._port_counter += 1
        return port
    
    async def setup_two_peers(self) -> Tuple[PeerService, PeerService]:
        """2ピアのテスト環境構築"""
        # 鍵生成
        priv_a, pub_a = generate_entity_keypair()
        priv_b, pub_b = generate_entity_keypair()
        
        # 環境変数設定
        os.environ["ENTITY_PRIVATE_KEY"] = priv_a
        
        # Peer A作成
        port_a = self._get_next_port()
        peer_a = PeerService(
            "test-peer-a",
            port_a,
            private_key_hex=priv_a,
            enable_encryption=True,
            require_signatures=True,
            enable_session_management=True,
        )
        
        # Peer B作成
        port_b = self._get_next_port()
        peer_b = PeerService(
            "test-peer-b", 
            port_b,
            private_key_hex=priv_b,
            enable_encryption=True,
            require_signatures=True,
            enable_session_management=True,
        )
        
        # 相互に公開鍵登録
        peer_a.add_peer_public_key("test-peer-b", pub_b)
        peer_b.add_peer_public_key("test-peer-a", pub_a)
        
        # ピア登録
        peer_a.add_peer("test-peer-b", f"http://localhost:{port_b}", public_key_hex=pub_b)
        peer_b.add_peer("test-peer-a", f"http://localhost:{port_a}", public_key_hex=pub_a)
        
        self.test_peers.extend([peer_a, peer_b])
        return peer_a, peer_b
    
    async def setup_multi_peers(self, count: int) -> List[PeerService]:
        """Nピアのテスト環境構築"""
        peers = []
        keys = []
        
        # 鍵生成
        for i in range(count):
            priv, pub = generate_entity_keypair()
            keys.append((priv, pub))
        
        # ピア作成
        for i, (priv, pub) in enumerate(keys):
            port = self._get_next_port()
            peer = PeerService(
                f"test-peer-{i}",
                port,
                private_key_hex=priv,
                enable_encryption=True,
                require_signatures=True,
            )
            peers.append(peer)
        
        # 相互に公開鍵登録
        for i, peer_i in enumerate(peers):
            for j, (_, pub_j) in enumerate(keys):
                if i != j:
                    peer_i.add_peer_public_key(f"test-peer-{j}", pub_j)
                    peer_j_port = 9000 + j
                    peer_i.add_peer(f"test-peer-{j}", f"http://localhost:{peer_j_port}", public_key_hex=pub_j)
        
        self.test_peers.extend(peers)
        return peers
    
    async def teardown_peers(self):
        """テスト環境の破棄"""
        for peer in self.test_peers:
            try:
                # セッションマネージャー停止
                if hasattr(peer, '_session_manager') and peer._session_manager:
                    await peer._session_manager.stop()
            except Exception as e:
                print(f"Warning: Error during teardown: {e}")
        
        self.test_peers.clear()


# ============================================================================
# シナリオ1: 完全なハンドシェイクフロー
# ============================================================================

async def test_scenario_1_handshake_flow():
    """シナリオ1: 完全なハンドシェイクフロー"""
    print("\n" + "="*60)
    print("Scenario 1: Complete Handshake Flow")
    print("="*60)
    
    base = PeerServiceIntegrationTestBase()
    
    try:
        # 2ピアセットアップ
        peer_a, peer_b = await base.setup_two_peers()
        print("✓ Two peers initialized")
        
        # 1. セッション作成
        session_mgr_a = peer_a._session_manager
        session_mgr_b = peer_b._session_manager
        
        # SessionManager開始
        await session_mgr_a.start()
        await session_mgr_b.start()
        print("✓ Session managers started")
        
        # セッション作成
        _, pub_a = generate_entity_keypair()
        _, pub_b = generate_entity_keypair()
        
        session_a = await session_mgr_a.create_session(
            peer_id="test-peer-b",
            peer_public_key=pub_b
        )
        print(f"✓ Session created by A: {session_a.session_id[:8]}...")
        
        # 2. セッション状態確認
        assert session_a.state == SessionState.INITIAL
        assert session_a.peer_id == "test-peer-b"
        print("✓ Session state is INITIAL")
        
        # 3. シーケンス番号確認
        assert session_a.sequence_num == 0
        assert session_a.expected_sequence == 1
        print("✓ Sequence numbers initialized correctly")
        
        # 4. セッション更新
        session_a.state = SessionState.ESTABLISHED
        session_a.increment_sequence()
        assert session_a.sequence_num == 1
        print("✓ Sequence increment works")
        
        # 5. セッション取得
        retrieved = session_mgr_a.get_session(session_a.session_id)
        assert retrieved is not None
        assert retrieved.session_id == session_a.session_id
        print("✓ Session retrieval works")
        
        # 6. ピア関連セッション取得
        peer_session = session_mgr_a.get_session_by_peer("test-peer-b")
        assert peer_session is not None
        print("✓ Session by peer retrieval works")
        
        # 7. 統計確認
        stats = peer_a.get_peer_stats("test-peer-b")
        assert stats is not None
        print(f"✓ Peer stats: {len(stats)} fields")
        
        # 8. ヘルスチェック
        health = await peer_a.health_check()
        assert health["status"] == "healthy"
        assert health["crypto_available"] is True
        print("✓ Health check passed")
        
        print("\n✅ Scenario 1 completed successfully")
        
    finally:
        await base.teardown_peers()


# ============================================================================
# シナリオ2: 切断・再接続フロー
# ============================================================================

async def test_scenario_2_disconnect_reconnect():
    """シナリオ2: 切断・再接続フロー"""
    print("\n" + "="*60)
    print("Scenario 2: Disconnect and Reconnect Flow")
    print("="*60)
    
    base = PeerServiceIntegrationTestBase()
    
    try:
        peer_a, peer_b = await base.setup_two_peers()
        print("✓ Two peers initialized")
        
        # HeartbeatManagerテスト
        hb_a = peer_a._heartbeat
        hb_b = peer_b._heartbeat
        
        # ピア登録
        hb_a.register_peer("test-peer-b")
        hb_b.register_peer("test-peer-a")
        print("✓ Peers registered for heartbeat")
        
        # 初期状態確認
        status_a = hb_a.get_status("test-peer-b")
        assert status_a == PeerStatus.UNKNOWN
        print("✓ Initial status is UNKNOWN")
        
        # 健全ピアリスト
        healthy = hb_a.get_healthy_peers()
        assert len(healthy) == 0  # ping前は空
        print("✓ No healthy peers before ping")
        
        # MessageQueueテスト
        queue = peer_a._queue
        await queue.enqueue("test-peer-b", "test_type", {"data": "test"})
        assert queue.get_queue_size() == 1
        print("✓ Message enqueued")
        
        # キュー統計
        q_stats = queue.get_stats()
        assert q_stats["queued"] == 1
        print(f"✓ Queue stats: {q_stats}")
        
        # ピア削除（切断シミュレート）
        peer_a.remove_peer("test-peer-b")
        assert "test-peer-b" not in peer_a.peers
        print("✓ Peer removed (simulated disconnect)")
        
        # 再登録（再接続）
        _, pub_b = generate_entity_keypair()
        peer_a.add_peer("test-peer-b", "http://localhost:9002", public_key_hex=pub_b)
        assert "test-peer-b" in peer_a.peers
        print("✓ Peer re-added (simulated reconnect)")
        
        print("\n✅ Scenario 2 completed successfully")
        
    finally:
        await base.teardown_peers()


# ============================================================================
# シナリオ3: マルチピア管理
# ============================================================================

async def test_scenario_3_multi_peer():
    """シナリオ3: マルチピア管理"""
    print("\n" + "="*60)
    print("Scenario 3: Multi-Peer Management")
    print("="*60)
    
    base = PeerServiceIntegrationTestBase()
    
    try:
        # 4ピア作成
        peers = await base.setup_multi_peers(4)
        peer_a, peer_b, peer_c, peer_d = peers
        print("✓ 4 peers initialized")
        
        # 各ピアのピアリスト確認
        for i, peer in enumerate(peers):
            peers_list = peer.list_peers()
            assert len(peers_list) == 3  # 他の3ピア
            print(f"✓ Peer-{i} has {len(peers_list)} peers")
        
        # 統計情報の個別管理確認
        for peer in peers:
            all_stats = peer.get_peer_stats()
            assert len(all_stats) == 3  # 3ピア分の統計
        print("✓ Stats managed individually per peer")
        
        # 特定ピア統計
        stats_b = peer_a.get_peer_stats("test-peer-1")
        assert stats_b is not None
        assert stats_b["entity_id"] == "test-peer-1"
        print("✓ Individual peer stats retrieval works")
        
        # 存在しないピア
        unknown_stats = peer_a.get_peer_stats("unknown-peer")
        assert unknown_stats == {}
        print("✓ Unknown peer stats returns empty dict")
        
        print("\n✅ Scenario 3 completed successfully")
        
    finally:
        await base.teardown_peers()


# ============================================================================
# シナリオ4: 大容量メッセージ転送
# ============================================================================

async def test_scenario_4_chunked_transfer():
    """シナリオ4: 大容量メッセージ転送"""
    print("\n" + "="*60)
    print("Scenario 4: Chunked Message Transfer")
    print("="*60)
    
    base = PeerServiceIntegrationTestBase()
    
    try:
        peer_a, peer_b = await base.setup_two_peers()
        print("✓ Two peers initialized")
        
        # ChunkInfoテスト
        chunk_info = ChunkInfo(message_id="test-msg-001", total_chunks=3)
        assert chunk_info.message_id == "test-msg-001"
        assert chunk_info.total_chunks == 3
        assert not chunk_info.is_complete()
        print("✓ ChunkInfo initialized")
        
        # チャンク追加
        chunk_info.received_chunks[0] = '{"type": "large_data", "content": "part1'
        chunk_info.received_chunks[1] = 'part2'
        assert not chunk_info.is_complete()
        print("✓ Partial chunks not complete")
        
        # 最後のチャンク追加
        chunk_info.received_chunks[2] = 'part3"}'
        assert chunk_info.is_complete()
        print("✓ All chunks complete")
        
        # ペイロード再構築
        payload = chunk_info.get_payload()
        assert payload is not None
        assert payload["type"] == "large_data"
        print("✓ Payload reconstructed successfully")
        
        # PeerServiceのchunkハンドラ確認
        assert "chunk" in peer_a.message_handlers
        print("✓ Chunk handler registered")
        
        # 古いチャンククリーンアップ
        old_chunk = ChunkInfo(message_id="old-msg", total_chunks=2)
        from datetime import timedelta
        old_chunk.created_at = datetime.now(timezone.utc) - timedelta(hours=2)
        peer_a._chunk_buffer["old-msg"] = old_chunk
        
        cleaned = await peer_a.cleanup_old_chunks(max_age_seconds=3600)
        assert cleaned == 1
        assert "old-msg" not in peer_a._chunk_buffer
        print("✓ Old chunks cleaned up")
        
        print("\n✅ Scenario 4 completed successfully")
        
    finally:
        await base.teardown_peers()


# ============================================================================
# シナリオ5: エラー回復とリトライ
# ============================================================================

async def test_scenario_5_error_recovery():
    """シナリオ5: エラー回復とリトライ"""
    print("\n" + "="*60)
    print("Scenario 5: Error Recovery and Retry")
    print("="*60)
    
    base = PeerServiceIntegrationTestBase()
    
    try:
        peer_a, peer_b = await base.setup_two_peers()
        print("✓ Two peers initialized")
        
        # ExponentialBackoffテスト
        from peer_service import ExponentialBackoff
        
        backoff = ExponentialBackoff(
            base_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0
        )
        
        # バックオフ計算
        delay_0 = backoff.get_delay(0)
        delay_1 = backoff.get_delay(1)
        delay_2 = backoff.get_delay(2)
        
        assert delay_0 == 1.0
        assert delay_1 == 2.0
        assert delay_2 == 4.0
        print(f"✓ Exponential backoff: {delay_0}, {delay_1}, {delay_2}")
        
        # 最大遅延制限
        delay_large = backoff.get_delay(10)
        assert delay_large <= 30.0
        print(f"✓ Max delay capped at {delay_large}")
        
        # MessageQueueのリトライ設定
        queue = peer_a._queue
        assert queue._max_retries == 3  # デフォルト値
        print("✓ Max retries configured")
        
        # キュー統計確認
        stats = queue.get_stats()
        assert "queued" in stats
        assert "sent" in stats
        assert "failed" in stats
        print(f"✓ Queue stats structure: {list(stats.keys())}")
        
        print("\n✅ Scenario 5 completed successfully")
        
    finally:
        await base.teardown_peers()


# ============================================================================
# メイン実行
# ============================================================================

async def main():
    """全統合テスト実行"""
    print("="*60)
    print("Peer Service Integration Test Suite v1.0")
    print("="*60)
    
    try:
        # シナリオ実行
        await test_scenario_1_handshake_flow()
        await test_scenario_2_disconnect_reconnect()
        await test_scenario_3_multi_peer()
        await test_scenario_4_chunked_transfer()
        await test_scenario_5_error_recovery()
        
        print("\n" + "="*60)
        print("All integration tests completed successfully!")
        print("="*60)
        
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        raise
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
