#!/usr/bin/env python3
"""
Entity A ウォレットセットアップとトークン準備スクリプト
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.token_system import (
    get_wallet, get_task_contract, get_reputation_contract, get_token_minter,
    TokenWallet, TaskContract, ReputationContract, TokenMinter
)
from services.token_economy import TokenEconomy, get_token_economy

def setup_entity_a():
    """Entity Aのウォレット作成とトークン配布"""
    
    print("=" * 60)
    print("Entity A セットアップ開始")
    print("=" * 60)
    
    # トークンエコノミー取得
    economy = get_token_economy()
    
    # Entity Aのウォレット取得（自動作成）
    entity_id = "EntityA"
    wallet = get_wallet(entity_id)
    
    print(f"\n✅ Entity A ウォレット準備完了")
    print(f"   Entity ID: {entity_id}")
    print(f"   現在の残高: {wallet.balance} AIC")
    
    # テスト用トークン配布（ミント）
    initial_balance = wallet.balance
    if initial_balance < 1000:
        mint_amount = 10000 - initial_balance
        print(f"\n💰 テスト用トークンをミント中...")
        print(f"   ミント量: {mint_amount} AIC")
        
        # TokenEconomyでミント
        result = economy.mint(
            to_entity=entity_id,
            amount=mint_amount,
            reason="Entity A test setup"
        )
        
        if result["success"]:
            print(f"   ✅ ミント成功!")
            print(f"   新しい残高: {wallet.balance} AIC")
            print(f"   オペレーションID: {result['operation_id']}")
        else:
            print(f"   ❌ ミント失敗: {result.get('error', 'Unknown error')}")
    else:
        print(f"\n💰 既に十分なトークンを所持: {wallet.balance} AIC")
    
    # 評価コントラクト確認
    reputation = get_reputation_contract()
    rating_info = reputation.get_rating(entity_id)
    
    print(f"\n📊 Entity A 評価情報:")
    print(f"   平均評価: {rating_info.get('average_rating', 'N/A')}")
    print(f"   評価数: {rating_info.get('total_ratings', 0)}")
    print(f"   完了タスク: {rating_info.get('completed_tasks', 0)}")
    
    # エコノミー統計
    supply_stats = economy.get_supply_stats()
    print(f"\n📈 トークンエコノミー統計:")
    print(f"   総供給量: {supply_stats['total_supply']} AIC")
    print(f"   流通量: {supply_stats['circulating_supply']} AIC")
    print(f"   バーン済み: {supply_stats['total_burned']} AIC")
    
    print("\n" + "=" * 60)
    print("Entity A セットアップ完了")
    print("=" * 60)
    
    return {
        "entity_id": entity_id,
        "balance": wallet.balance,
        "wallet": wallet,
        "economy": economy
    }

if __name__ == "__main__":
    result = setup_entity_a()
    print(f"\n🚀 Entity A 準備完了!")
    print(f"   Entity ID: {result['entity_id']}")
    print(f"   Balance: {result['balance']} AIC")
