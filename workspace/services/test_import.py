#!/usr/bin/env python3
"""api_server直接インポートテスト"""

import sys
sys.path.insert(0, '/home/moco/workspace/services')

print("=" * 60)
print("API Server 直接インポートテスト")
print("=" * 60)

errors = []

# 1. 基本モジュールのインポートテスト
print("\n[1/5] 基本モジュールのインポート...")
try:
    from fastapi import FastAPI
    print("  ✅ FastAPI")
except Exception as e:
    print(f"  ❌ FastAPI: {e}")
    errors.append(f"FastAPI: {e}")

try:
    import uvicorn
    print("  ✅ uvicorn")
except Exception as e:
    print(f"  ❌ uvicorn: {e}")
    errors.append(f"uvicorn: {e}")

# 2. ローカルモジュールのインポートテスト
print("\n[2/5] ローカルモジュールのインポート...")

test_modules = [
    'registry',
    'peer_service', 
    'token_system',
    'crypto',
    'auth',
    'moltbook_client',
]

for module in test_modules:
    try:
        __import__(module)
        print(f"  ✅ {module}")
    except Exception as e:
        print(f"  ❌ {module}: {e}")
        errors.append(f"{module}: {e}")

# 3. api_serverのインポートテスト
print("\n[3/5] api_server のインポート...")
try:
    import api_server
    print("  ✅ api_server インポート成功")
    print(f"     アプリ名: {api_server.app.title}")
    print(f"     バージョン: {api_server.app.version}")
except Exception as e:
    print(f"  ❌ api_server: {e}")
    errors.append(f"api_server: {e}")
    import traceback
    traceback.print_exc()

# 4. 主要コンポーネントの確認
print("\n[4/5] 主要コンポーネントの確認...")
try:
    import api_server
    components = [
        ('registry', 'registry'),
        ('replay_protector', 'replay_protector'),
        ('jwt_auth', 'jwt_auth'),
        ('api_key_auth', 'api_key_auth'),
        ('signature_verifier', 'signature_verifier'),
    ]
    for name, attr in components:
        if hasattr(api_server, attr):
            print(f"  ✅ {name}")
        else:
            print(f"  ⚠️  {name} (未初期化)")
except Exception as e:
    print(f"  ❌ エラー: {e}")

# 5. エンドポイント確認
print("\n[5/5] APIエンドポイント確認...")
try:
    import api_server
    routes = [route.path for route in api_server.app.routes]
    key_routes = ['/register', '/heartbeat', '/discover', '/health', '/auth/token', '/message']
    for route in key_routes:
        if route in routes:
            print(f"  ✅ {route}")
        else:
            print(f"  ⚠️  {route} (未定義)")
    print(f"\n  合計 {len(routes)} ルート定義済み")
except Exception as e:
    print(f"  ❌ エラー: {e}")

# 結果サマリー
print("\n" + "=" * 60)
print("テスト結果サマリー")
print("=" * 60)
if errors:
    print(f"❌ {len(errors)} 個のエラーが発生しました:")
    for err in errors:
        print(f"   - {err}")
    sys.exit(1)
else:
    print("✅ すべてのインポートテストに成功しました！")
    sys.exit(0)
