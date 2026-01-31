#!/usr/bin/env python3
"""
Ed25519 -> X25519変換機能のテスト
"""
import os
import sys
import base64

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from crypto_utils import CryptoManager


def test_ed25519_to_x25519_private():
    """Ed25519秘密鍵 -> X25519秘密鍵変換テスト"""
    print("=== Test: Ed25519 Private -> X25519 Private ===")
    
    # Ed25519鍵ペアを生成
    ed25519_private = Ed25519PrivateKey.generate()
    ed25519_public = ed25519_private.public_key()
    
    # 秘密鍵バイトを取得
    ed25519_private_bytes = ed25519_private.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # 変換実行
    x25519_private_bytes = CryptoManager.convert_ed25519_private_to_x25519(
        ed25519_private_bytes
    )
    
    # 結果検証
    assert len(x25519_private_bytes) == 32, "X25519 private key must be 32 bytes"
    
    # clamp処理が正しく行われているか確認
    assert x25519_private_bytes[0] & 0x07 == 0, "Lower 3 bits should be cleared"
    assert x25519_private_bytes[31] & 0x80 == 0, "High bit should be cleared"
    assert x25519_private_bytes[31] & 0x40 == 0x40, "Bit 254 should be set"
    
    print(f"  Ed25519 private (hex): {ed25519_private_bytes.hex()[:16]}...")
    print(f"  X25519 private (hex):  {x25519_private_bytes.hex()[:16]}...")
    print(f"  Clamping verified: OK")
    print("  PASSED\n")
    return True


def test_ed25519_to_x25519_public():
    """Ed25519公開鍵 -> X25519公開鍵変換テスト"""
    print("=== Test: Ed25519 Public -> X25519 Public ===")
    
    # Ed25519鍵ペアを生成
    ed25519_private = Ed25519PrivateKey.generate()
    ed25519_public = ed25519_private.public_key()
    
    # 公開鍵バイトを取得
    ed25519_public_bytes = ed25519_public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    # 変換実行
    x25519_public_bytes = CryptoManager.convert_ed25519_public_to_x25519(
        ed25519_public_bytes
    )
    
    # 結果検証
    assert len(x25519_public_bytes) == 32, "X25519 public key must be 32 bytes"
    
    print(f"  Ed25519 public (hex): {ed25519_public_bytes.hex()[:16]}...")
    print(f"  X25519 public (hex):  {x25519_public_bytes.hex()[:16]}...")
    print("  PASSED\n")
    return True


def test_cross_key_exchange():
    """変換後の鍵でX25519鍵交換が正しく機能するかテスト"""
    print("=== Test: Cross-Key Exchange (Ed25519 -> X25519) ===")
    
    # 2つのエンティティのEd25519鍵を生成
    entity_a_ed_priv = Ed25519PrivateKey.generate()
    entity_a_ed_pub = entity_a_ed_priv.public_key()
    
    entity_b_ed_priv = Ed25519PrivateKey.generate()
    entity_b_ed_pub = entity_b_ed_priv.public_key()
    
    # Ed25519鍵をバイト列に
    entity_a_ed_priv_bytes = entity_a_ed_priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    entity_a_ed_pub_bytes = entity_a_ed_pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    entity_b_ed_priv_bytes = entity_b_ed_priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    entity_b_ed_pub_bytes = entity_b_ed_pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )
    
    # X25519に変換
    entity_a_x_priv = CryptoManager.convert_ed25519_private_to_x25519(
        entity_a_ed_priv_bytes
    )
    entity_a_x_pub = CryptoManager.convert_ed25519_public_to_x25519(
        entity_a_ed_pub_bytes
    )
    
    entity_b_x_priv = CryptoManager.convert_ed25519_private_to_x25519(
        entity_b_ed_priv_bytes
    )
    entity_b_x_pub = CryptoManager.convert_ed25519_public_to_x25519(
        entity_b_ed_pub_bytes
    )
    
    # X25519鍵ペアを作成
    entity_a_x_priv_key = X25519PrivateKey.from_private_bytes(entity_a_x_priv)
    entity_a_x_pub_key = X25519PublicKey.from_public_bytes(entity_a_x_pub)
    
    entity_b_x_priv_key = X25519PrivateKey.from_private_bytes(entity_b_x_priv)
    entity_b_x_pub_key = X25519PublicKey.from_public_bytes(entity_b_x_pub)
    
    # 鍵交換
    shared_a = entity_a_x_priv_key.exchange(entity_b_x_pub_key)
    shared_b = entity_b_x_priv_key.exchange(entity_a_x_pub_key)
    
    # 共有鍵が一致することを確認
    assert shared_a == shared_b, "Shared keys must match!"
    assert len(shared_a) == 32, "Shared key must be 32 bytes"
    
    print(f"  Entity A shared key: {shared_a.hex()[:16]}...")
    print(f"  Entity B shared key: {shared_b.hex()[:16]}...")
    print(f"  Keys match: {shared_a == shared_b}")
    print("  PASSED\n")
    return True


def test_error_handling():
    """エラー処理テスト"""
    print("=== Test: Error Handling ===")
    
    # 無効な長さの秘密鍵
    try:
        CryptoManager.convert_ed25519_private_to_x25519(b"invalid")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  Invalid private key length error: {e}")
    
    # 無効な長さの公開鍵
    try:
        CryptoManager.convert_ed25519_public_to_x25519(b"invalid")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  Invalid public key length error: {e}")
    
    print("  PASSED\n")
    return True


def test_import():
    """インポートテスト"""
    print("=== Test: Import ===")
    from crypto_utils import CryptoManager
    print("  Import successful")
    print("  PASSED\n")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Ed25519 -> X25519 Conversion Tests")
    print("=" * 60 + "\n")
    
    # serialization import
    from cryptography.hazmat.primitives import serialization
    
    all_passed = True
    
    try:
        all_passed &= test_import()
        all_passed &= test_ed25519_to_x25519_private()
        all_passed &= test_ed25519_to_x25519_public()
        all_passed &= test_cross_key_exchange()
        all_passed &= test_error_handling()
        
        if all_passed:
            print("=" * 60)
            print("ALL TESTS PASSED!")
            print("=" * 60)
            sys.exit(0)
        else:
            print("=" * 60)
            print("SOME TESTS FAILED!")
            print("=" * 60)
            sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
