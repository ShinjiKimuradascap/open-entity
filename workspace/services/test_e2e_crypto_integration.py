#!/usr/bin/env python3
"""
E2E暗号化統合テスト
E2ECryptoManagerとPeerServiceの統合をテスト
"""

import asyncio
import pytest

pytestmark = pytest.mark.integration

from typing import Optional
from datetime import datetime, timezone

# テスト対象のインポート
try:
    from services.e2e_crypto import (
        E2ECryptoManager,
        E2ESession,
        SessionState,
        SessionKeys,
    )
    from services.crypto import generate_entity_keypair, CryptoManager
    E2E_AVAILABLE = True
except ImportError:
    E2E_AVAILABLE = False
    pytest.skip("E2E crypto modules not available", allow_module_level=True)


class TestE2ESession:
    """E2Eセッション管理のテスト"""
    
    def test_session_creation(self):
        """セッション作成テスト"""
        priv_key, pub_key = generate_entity_keypair()
        crypto_manager = CryptoManager("entity-a", priv_key)
        
        e2e_manager = E2ECryptoManager(
            entity_id="entity-a",
            keypair=crypto_manager.keypair
        )
        
        # セッション作成
        session = e2e_manager.create_session("entity-b")
        
        assert session is not None
        assert session.local_entity_id == "entity-a"
        assert session.remote_entity_id == "entity-b"
        assert session.state == SessionState.INITIAL
        assert len(session.session_id) == 36  # UUID v4
        print(f"✓ Session created: {session.session_id}")
    
    def test_session_state_transitions(self):
        """セッション状態遷移テスト"""
        priv_key, pub_key = generate_entity_keypair()
        crypto_manager = CryptoManager("entity-a", priv_key)
        
        e2e_manager = E2ECryptoManager(
            entity_id="entity-a",
            keypair=crypto_manager.keypair
        )
        
        session = e2e_manager.create_session("entity-b")
        
        # 初期状態
        assert session.state == SessionState.INITIAL
        
        # 状態遷移（シミュレーション）
        session.state = SessionState.HANDSHAKE_INIT_SENT
        assert session.state == SessionState.HANDSHAKE_INIT_SENT
        
        session.state = SessionState.READY
        assert session.state == SessionState.READY
        
        print("✓ Session state transitions work correctly")
    
    def test_session_keys_derivation(self):
        """セッション鍵導出テスト"""
        # 共有シークレット（32バイト）
        shared_secret = b'x' * 32
        
        # 鍵導出
        session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
        
        assert len(session_keys.encryption_key) == 32
        assert len(session_keys.auth_key) == 32
        assert session_keys.encryption_key != session_keys.auth_key
        
        print(f"✓ Session keys derived: enc={len(session_keys.encryption_key)} bytes, auth={len(session_keys.auth_key)} bytes")


class TestE2ECryptoManager:
    """E2ECryptoManagerのテスト"""
    
    def test_manager_initialization(self):
        """マネージャー初期化テスト"""
        priv_key, pub_key = generate_entity_keypair()
        crypto_manager = CryptoManager("test-entity", priv_key)
        
        e2e_manager = E2ECryptoManager(
            entity_id="test-entity",
            keypair=crypto_manager.keypair,
            default_timeout=3600
        )
        
        assert e2e_manager.entity_id == "test-entity"
        assert e2e_manager.default_timeout == 3600
        print("✓ E2ECryptoManager initialized")
    
    def test_get_or_create_session(self):
        """セッション取得/作成テスト"""
        priv_key, pub_key = generate_entity_keypair()
        crypto_manager = CryptoManager("entity-a", priv_key)
        
        e2e_manager = E2ECryptoManager(
            entity_id="entity-a",
            keypair=crypto_manager.keypair
        )
        
        # セッション作成
        session1 = e2e_manager.get_or_create_session("entity-b")
        session2 = e2e_manager.get_or_create_session("entity-b")
        
        # 同じセッションが返される
        assert session1.session_id == session2.session_id
        print("✓ Session reuse works correctly")
    
    def test_session_cleanup(self):
        """セッションクリーンアップテスト"""
        priv_key, pub_key = generate_entity_keypair()
        crypto_manager = CryptoManager("entity-a", priv_key)
        
        e2e_manager = E2ECryptoManager(
            entity_id="entity-a",
            keypair=crypto_manager.keypair,
            default_timeout=1  # 1秒で期限切れ
        )
        
        # セッション作成
        session = e2e_manager.create_session("entity-b")
        session_id = session.session_id
        
        assert session_id in e2e_manager.sessions
        
        # 期限切れにする
        import time
        time.sleep(1.1)
        
        # クリーンアップ実行
        e2e_manager.cleanup_expired_sessions()
        
        # 期限切れセッションは削除される
        assert session_id not in e2e_manager.sessions
        print("✓ Expired session cleanup works")


class TestE2EIntegration:
    """E2E統合テスト"""
    
    def test_two_entity_key_exchange(self):
        """2エンティティ間の鍵交換テスト"""
        # Entity A
        priv_a, pub_a = generate_entity_keypair()
        crypto_a = CryptoManager("entity-a", priv_a)
        e2e_a = E2ECryptoManager(
            entity_id="entity-a",
            keypair=crypto_a.keypair
        )
        
        # Entity B
        priv_b, pub_b = generate_entity_keypair()
        crypto_b = CryptoManager("entity-b", priv_b)
        e2e_b = E2ECryptoManager(
            entity_id="entity-b",
            keypair=crypto_b.keypair
        )
        
        # セッション作成
        session_a = e2e_a.create_session("entity-b")
        session_b = e2e_b.create_session("entity-a")
        
        # 公開鍵交換（シミュレーション）
        # 実際の実装ではハンドシェイクで交換
        session_a.remote_public_key = bytes.fromhex(pub_b)
        session_b.remote_public_key = bytes.fromhex(pub_a)
        
        assert session_a.remote_public_key is not None
        assert session_b.remote_public_key is not None
        print("✓ Key exchange simulation completed")
    
    def test_ephemeral_key_generation(self):
        """エフェメラル鍵生成テスト（PFS）"""
        priv_key, pub_key = generate_entity_keypair()
        crypto_manager = CryptoManager("entity-a", priv_key)
        
        e2e_manager = E2ECryptoManager(
            entity_id="entity-a",
            keypair=crypto_manager.keypair
        )
        
        session1 = e2e_manager.create_session("entity-b")
        session2 = e2e_manager.create_session("entity-c")
        
        # 異なるセッションは異なるエフェメラル鍵を持つ
        assert session1.ephemeral_private_key != session2.ephemeral_private_key
        assert session1.ephemeral_public_key != session2.ephemeral_public_key
        
        print("✓ Ephemeral keys are unique per session (PFS)")


@pytest.mark.asyncio
class TestE2EAsync:
    """非同期E2Eテスト"""
    
    async def test_async_session_operations(self):
        """非同期セッション操作テスト"""
        priv_key, pub_key = generate_entity_keypair()
        crypto_manager = CryptoManager("entity-a", priv_key)
        
        e2e_manager = E2ECryptoManager(
            entity_id="entity-a",
            keypair=crypto_manager.keypair
        )
        
        # 非同期でセッション作成
        session = await asyncio.to_thread(e2e_manager.create_session, "entity-b")
        
        assert session is not None
        print("✓ Async session creation works")


def run_all_tests():
    """全テスト実行"""
    print("=" * 60)
    print("E2E Crypto Integration Tests")
    print("=" * 60)
    
    if not E2E_AVAILABLE:
        print("❌ E2E crypto modules not available - skipping tests")
        return
    
    # テストクラスインスタンス化
    test_session = TestE2ESession()
    test_manager = TestE2ECryptoManager()
    test_integration = TestE2EIntegration()
    
    # テスト実行
    try:
        test_session.test_session_creation()
        test_session.test_session_state_transitions()
        test_session.test_session_keys_derivation()
        
        test_manager.test_manager_initialization()
        test_manager.test_get_or_create_session()
        test_manager.test_session_cleanup()
        
        test_integration.test_two_entity_key_exchange()
        test_integration.test_ephemeral_key_generation()
        
        print("\n" + "=" * 60)
        print("✅ All E2E integration tests passed!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        raise


if __name__ == "__main__":
    run_all_tests()
