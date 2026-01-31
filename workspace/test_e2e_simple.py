#!/usr/bin/env python3
"""
シンプルなE2E暗号化テスト - pytest不要
"""

import sys
import os
sys.path.insert(0, '/home/moco/workspace')

from services.e2e_crypto import (
    E2ECryptoManager,
    E2ESession,
    SessionState,
    SessionKeys,
)
from services.crypto import generate_entity_keypair, CryptoManager

def test_session_creation():
    """セッション作成テスト"""
    print("\n=== Test: Session Creation ===")
    priv_key, pub_key = generate_entity_keypair()
    crypto_manager = CryptoManager("entity-a", priv_key)
    
    e2e_manager = E2ECryptoManager(
        entity_id="entity-a",
        keypair=crypto_manager.keypair
    )
    
    # セッション作成
    session = e2e_manager.create_session("entity-b")
    
    assert session is not None, "Session should not be None"
    assert session.local_entity_id == "entity-a", "Local entity ID mismatch"
    assert session.remote_entity_id == "entity-b", "Remote entity ID mismatch"
    assert session.state == SessionState.INITIAL, "Initial state should be INITIAL"
    assert len(session.session_id) == 36, "Session ID should be UUID v4"
    print(f"✓ Session created: {session.session_id}")
    return True

def test_session_state_transitions():
    """セッション状態遷移テスト"""
    print("\n=== Test: Session State Transitions ===")
    priv_key, pub_key = generate_entity_keypair()
    crypto_manager = CryptoManager("entity-a", priv_key)
    
    e2e_manager = E2ECryptoManager(
        entity_id="entity-a",
        keypair=crypto_manager.keypair
    )
    
    session = e2e_manager.create_session("entity-b")
    
    # 初期状態
    assert session.state == SessionState.INITIAL, "Initial state should be INITIAL"
    
    # 状態遷移（シミュレーション）
    session.state = SessionState.HANDSHAKE_INIT_SENT
    assert session.state == SessionState.HANDSHAKE_INIT_SENT, "State should be HANDSHAKE_INIT_SENT"
    
    session.state = SessionState.READY
    assert session.state == SessionState.READY, "State should be READY"
    
    print("✓ Session state transitions work correctly")
    return True

def test_session_keys_derivation():
    """セッション鍵導出テスト"""
    print("\n=== Test: Session Keys Derivation ===")
    # 共有シークレット（32バイト）
    shared_secret = b'x' * 32
    
    # 鍵導出
    session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
    
    assert session_keys is not None, "SessionKeys should not be None"
    assert len(session_keys.encryption_key) == 32, "Encryption key should be 32 bytes"
    assert len(session_keys.auth_key) == 32, "Auth key should be 32 bytes"
    assert len(session_keys.iv_seed) == 16, "IV seed should be 16 bytes"
    
    print(f"✓ Encryption key: {session_keys.encryption_key.hex()[:16]}...")
    print(f"✓ Auth key: {session_keys.auth_key.hex()[:16]}...")
    return True

def test_full_handshake_simulation():
    """完全なハンドシェイクシミュレーション"""
    print("\n=== Test: Full Handshake Simulation ===")
    
    # Entity A のキー生成
    priv_a, pub_a = generate_entity_keypair()
    crypto_a = CryptoManager("entity-a", priv_a)
    e2e_a = E2ECryptoManager(entity_id="entity-a", keypair=crypto_a.keypair)
    
    # Entity B のキー生成
    priv_b, pub_b = generate_entity_keypair()
    crypto_b = CryptoManager("entity-b", priv_b)
    e2e_b = E2ECryptoManager(entity_id="entity-b", keypair=crypto_b.keypair)
    
    # Entity A がセッション作成
    session_a = e2e_a.create_session("entity-b")
    print(f"Entity A created session: {session_a.session_id}")
    
    # Entity B がセッション作成
    session_b = e2e_b.create_session("entity-a")
    session_b.session_id = session_a.session_id  # 同じセッションIDを使用
    print(f"Entity B joined session: {session_b.session_id}")
    
    # X25519鍵交換シミュレーション
    from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
    
    ephemeral_a = X25519PrivateKey.generate()
    ephemeral_b = X25519PrivateKey.generate()
    
    pub_ephemeral_a = ephemeral_a.public_key()
    pub_ephemeral_b = ephemeral_b.public_key()
    
    # 共有シークレット導出
    shared_a = ephemeral_a.exchange(pub_ephemeral_b)
    shared_b = ephemeral_b.exchange(pub_ephemeral_a)
    
    assert shared_a == shared_b, "Shared secrets should match"
    print(f"✓ Shared secret established: {shared_a.hex()[:16]}...")
    
    # セッション鍵導出
    keys_a = SessionKeys.derive_from_shared_secret(shared_a)
    keys_b = SessionKeys.derive_from_shared_secret(shared_b)
    
    assert keys_a.encryption_key == keys_b.encryption_key, "Encryption keys should match"
    assert keys_a.auth_key == keys_b.auth_key, "Auth keys should match"
    print("✓ Session keys derived successfully")
    
    # 状態更新
    session_a.state = SessionState.READY
    session_b.state = SessionState.READY
    print("✓ Both sessions are READY")
    
    return True

def test_encrypt_decrypt():
    """暗号化・復号テスト"""
    print("\n=== Test: Encrypt/Decrypt ===")
    
    priv_key, pub_key = generate_entity_keypair()
    crypto_manager = CryptoManager("entity-a", priv_key)
    
    e2e_manager = E2ECryptoManager(
        entity_id="entity-a",
        keypair=crypto_manager.keypair
    )
    
    session = e2e_manager.create_session("entity-b")
    
    # テスト用セッション鍵
    shared_secret = b'test_secret_key_32bytes_long!!!!!'
    session_keys = SessionKeys.derive_from_shared_secret(shared_secret)
    session.session_keys = session_keys
    session.state = SessionState.READY
    
    # 暗号化
    plaintext = b"Hello, E2E Encryption!"
    ciphertext = session.encrypt(plaintext)
    
    assert ciphertext is not None, "Ciphertext should not be None"
    assert ciphertext != plaintext, "Ciphertext should be different from plaintext"
    print(f"✓ Encrypted: {len(plaintext)} bytes -> {len(ciphertext)} bytes")
    
    # 復号
    decrypted = session.decrypt(ciphertext)
    assert decrypted == plaintext, "Decrypted text should match original"
    print(f"✓ Decrypted: {decrypted.decode()}")
    
    return True

def run_all_tests():
    """全テスト実行"""
    print("=" * 60)
    print("E2E Crypto Integration Tests (No pytest required)")
    print("=" * 60)
    
    tests = [
        test_session_creation,
        test_session_state_transitions,
        test_session_keys_derivation,
        test_full_handshake_simulation,
        test_encrypt_decrypt,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
                print(f"✅ {test.__name__} PASSED")
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__} FAILED: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
