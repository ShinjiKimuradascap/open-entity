#!/usr/bin/env python3
"""
E2E暗号化デバッグテスト
"""
import os
import sys
sys.path.insert(0, 'services')

from crypto import CryptoManager, generate_entity_keypair, E2EEncryption

def test_crypto_manager_e2e():
    """CryptoManagerのE2Eテスト"""
    print("="*60)
    print("CryptoManager E2E Test")
    print("="*60)
    
    # キーペア生成
    priv_a, pub_a = generate_entity_keypair()
    priv_b, pub_b = generate_entity_keypair()
    
    # 環境変数設定
    os.environ["ENTITY_PRIVATE_KEY"] = priv_a
    crypto_a = CryptoManager("entity-a")
    
    os.environ["ENTITY_PRIVATE_KEY"] = priv_b
    crypto_b = CryptoManager("entity-b")
    
    # X25519キーペア生成
    crypto_a.generate_x25519_keypair()
    crypto_b.generate_x25519_keypair()
    
    print(f"✓ Keys generated")
    print(f"  A X25519 pub: {crypto_a.get_x25519_public_key_b64()[:32]}...")
    print(f"  B X25519 pub: {crypto_b.get_x25519_public_key_b64()[:32]}...")
    
    # 共有鍵導出
    shared_key_a = crypto_a.derive_shared_key(
        crypto_b.get_x25519_public_key_b64(),
        "entity-b"
    )
    shared_key_b = crypto_b.derive_shared_key(
        crypto_a.get_x25519_public_key_b64(),
        "entity-a"
    )
    
    print(f"✓ Shared keys derived")
    print(f"  A's key: {shared_key_a.hex()[:16]}...")
    print(f"  B's key: {shared_key_b.hex()[:16]}...")
    print(f"  Match: {shared_key_a == shared_key_b}")
    
    # 暗号化テスト
    payload = {"message": "Hello", "secret": "data"}
    
    # AがB向けに暗号化
    ciphertext, nonce = crypto_a.encrypt_payload(
        payload,
        crypto_b.get_x25519_public_key_b64(),
        "entity-b"
    )
    
    print(f"✓ Encrypted: ciphertext len={len(ciphertext)}, nonce len={len(nonce)}")
    
    # Bが復号
    decrypted = crypto_b.decrypt_payload(ciphertext, nonce, "entity-a")
    
    print(f"✓ Decrypted: {decrypted}")
    print(f"  Match: {decrypted == payload}")
    
    return decrypted == payload

def test_e2e_encryption_class():
    """E2EEncryptionクラスのテスト"""
    print("\n" + "="*60)
    print("E2EEncryption Class Test")
    print("="*60)
    
    from crypto import KeyPair, generate_keypair
    
    # インスタンス作成
    e2e_a = E2EEncryption()
    e2e_b = E2EEncryption()
    
    # キーペア生成
    key_a = generate_keypair()
    key_b = generate_keypair()
    
    print(f"✓ Key pairs generated")
    print(f"  A: {key_a.get_public_key_hex()[:16]}...")
    print(f"  B: {key_b.get_public_key_hex()[:16]}...")
    
    # 共有鍵導出
    shared_key_a = e2e_a.derive_shared_key(
        key_a.private_key,
        key_b.public_key,
        "bob"
    )
    shared_key_b = e2e_b.derive_shared_key(
        key_b.private_key,
        key_a.public_key,
        "alice"
    )
    
    print(f"✓ Shared keys derived")
    print(f"  Match: {shared_key_a == shared_key_b}")
    
    # 暗号化
    plaintext = b'{"message": "Hello"}'
    ciphertext, nonce = e2e_a.encrypt(plaintext, shared_key_a)
    
    print(f"✓ Encrypted: ciphertext len={len(ciphertext)}, nonce len={len(nonce)}")
    
    # 復号
    decrypted = e2e_b.decrypt(ciphertext, nonce, shared_key_b)
    
    print(f"✓ Decrypted: {decrypted}")
    print(f"  Match: {decrypted == plaintext}")
    
    return decrypted == plaintext

if __name__ == "__main__":
    result1 = test_crypto_manager_e2e()
    result2 = test_e2e_encryption_class()
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"CryptoManager E2E: {'✓ PASS' if result1 else '✗ FAIL'}")
    print(f"E2EEncryption Class: {'✓ PASS' if result2 else '✗ FAIL'}")
