#!/usr/bin/env python3
"""Token System 永続化機能のテストスクリプト"""

import sys
import json
from pathlib import Path

sys.path.insert(0, '/home/moco/workspace/services')
from token_system import (
    create_wallet, save_wallet, load_wallet, save_all_wallets, load_all_wallets,
    get_wallet, _wallet_registry, DEFAULT_DATA_DIR
)

def test_persistence():
    print('=== 永続化機能テスト ===')
    print(f'Data directory: {DEFAULT_DATA_DIR}')
    
    # 1. ウォレット作成
    print('\n1. ウォレットを作成')
    alice = create_wallet('test_alice', 1000)
    bob = create_wallet('test_bob', 500)
    charlie = create_wallet('test_charlie', 200)
    print(f'  test_alice: {alice.get_balance()} AIC')
    print(f'  test_bob: {bob.get_balance()} AIC')
    print(f'  test_charlie: {charlie.get_balance()} AIC')
    
    # 2. 個別保存テスト
    print('\n2. 個別保存テスト')
    result = save_wallet('test_alice')
    print(f'  save_wallet(test_alice): {result}')
    result = save_wallet('test_bob')
    print(f'  save_wallet(test_bob): {result}')
    result = save_wallet('nonexistent')
    print(f'  save_wallet(nonexistent): {result}')
    
    # 3. ファイル確認
    print('\n3. 保存されたファイル')
    json_files = list(DEFAULT_DATA_DIR.glob('test_*.json'))
    for f in sorted(json_files):
        print(f'  {f.name}')
    
    # 4. レジストリクリアして読み込みテスト
    print('\n4. レジストリクリア後の読み込みテスト')
    _wallet_registry.clear()
    print(f'  レジストリクリア後: {len(_wallet_registry)} ウォレット')
    
    loaded = load_wallet('test_alice')
    print(f'  load_wallet(test_alice): {loaded.get_balance() if loaded else None}')
    loaded = load_wallet('test_bob')
    print(f'  load_wallet(test_bob): {loaded.get_balance() if loaded else None}')
    loaded = load_wallet('test_charlie')  # 保存していない
    print(f'  load_wallet(test_charlie): {loaded}')
    
    # 5. save_all_wallets テスト
    print('\n5. save_all_wallets テスト')
    charlie = create_wallet('test_charlie', 300)  # 再作成
    result = save_all_wallets()
    print(f'  save_all_wallets(): {result} wallets saved')
    
    # 6. load_all_wallets テスト
    print('\n6. load_all_wallets テスト')
    _wallet_registry.clear()
    result = load_all_wallets()
    print(f'  load_all_wallets(): {result} wallets loaded')
    for entity_id, wallet in sorted(_wallet_registry.items()):
        if entity_id.startswith('test_'):
            print(f'    {entity_id}: {wallet.get_balance()} AIC')
    
    # 7. JSONファイル内容確認
    print('\n7. JSONファイル内容（test_alice）')
    alice_file = DEFAULT_DATA_DIR / 'test_alice.json'
    if alice_file.exists():
        with open(alice_file) as f:
            data = json.load(f)
            print(f'  entity_id: {data["entity_id"]}')
            print(f'  balance: {data["balance"]}')
            print(f'  transactions: {len(data["transactions"])}件')
    
    print('\n=== テスト完了 ===')
    return True

if __name__ == '__main__':
    test_persistence()
