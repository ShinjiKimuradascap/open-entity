#!/usr/bin/env python3
"""インポートテスト用スクリプト"""
import sys
import os

# パス設定
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))
sys.path.insert(0, os.path.dirname(__file__))

print("Testing imports...")
print(f"Python path: {sys.path[:3]}")

try:
    from services.crypto import generate_entity_keypair
    print("✅ generate_entity_keypair imported successfully")
except Exception as e:
    print(f"❌ Failed to import generate_entity_keypair: {e}")
    import traceback
    traceback.print_exc()

try:
    from services.crypto import WalletManager
    print("✅ WalletManager imported successfully")
except Exception as e:
    print(f"❌ Failed to import WalletManager: {e}")
    import traceback
    traceback.print_exc()

try:
    from services.crypto import CryptoManager
    print("✅ CryptoManager imported successfully")
except Exception as e:
    print(f"❌ Failed to import CryptoManager: {e}")
    import traceback
    traceback.print_exc()

try:
    from services.crypto import SecureMessage
    print("✅ SecureMessage imported successfully")
except Exception as e:
    print(f"❌ Failed to import SecureMessage: {e}")
    import traceback
    traceback.print_exc()

print("\nAll import tests completed.")
