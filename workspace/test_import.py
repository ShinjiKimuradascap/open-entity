#!/usr/bin/env python3
"""api_server直接インポートテスト"""
import sys
import os

# servicesディレクトリをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

print('=== api_server.py インポートテスト ===')

try:
    import api_server
    print('✅ インポート成功')
    print(f'  FastAPI app: {api_server.app}')
    print(f'  Registry: {api_server.registry}')
    print(f'  PeerService初期化: {"OK" if api_server.peer_service else "None"}')
    
    # エンドポイント一覧を確認
    routes = [r.path for r in api_server.app.routes]
    print(f'\n  登録エンドポイント数: {len(routes)}')
    print(f'  エンドポイント: {routes[:5]}...')
    
except ImportError as e:
    print(f'❌ インポート失敗: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    print(f'❌ エラー: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

print('\n=== テスト完了 ===')
