#!/usr/bin/env python3
"""
相互取引テストスクリプト - ローカルモジュール使用版
ローカルのmarketplaceとtoken_economyを使用してトレードテスト
"""

import sys
import os
import json
from datetime import datetime

# Add services to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'services'))

# Import marketplace
import importlib.util
spec = importlib.util.spec_from_file_location("marketplace_module", 
    os.path.join(os.path.dirname(__file__), 'services', 'marketplace.py'))
marketplace_module = importlib.util.module_from_spec(spec)
sys.modules["marketplace_module"] = marketplace_module
spec.loader.exec_module(marketplace_module)

MarketplaceRegistry = marketplace_module.MarketplaceRegistry
ServiceRecord = marketplace_module.ServiceRecord
PricingModel = marketplace_module.PricingModel
AvailabilityInfo = marketplace_module.AvailabilityInfo
RatingStats = marketplace_module.RatingStats

# Import token economy
spec2 = importlib.util.spec_from_file_location("token_economy_module",
    os.path.join(os.path.dirname(__file__), 'services', 'token_economy.py'))
token_module = importlib.util.module_from_spec(spec2)
sys.modules["token_economy_module"] = token_module
spec2.loader.exec_module(token_module)

TokenEconomy = token_module.TokenEconomy

# Import token_system for wallet creation
spec4 = importlib.util.spec_from_file_location("token_system_module",
    os.path.join(os.path.dirname(__file__), 'services', 'token_system.py'))
token_system_module = importlib.util.module_from_spec(spec4)
sys.modules["token_system_module"] = token_system_module
spec4.loader.exec_module(token_system_module)

create_wallet = token_system_module.create_wallet
get_wallet = token_system_module.get_wallet

# Import escrow
spec3 = importlib.util.spec_from_file_location("escrow_module",
    os.path.join(os.path.dirname(__file__), 'services', 'escrow_manager.py'))
escrow_module = importlib.util.module_from_spec(spec3)
sys.modules["escrow_module"] = escrow_module
spec3.loader.exec_module(escrow_module)

EscrowManager = escrow_module.EscrowManager


def register_entity_a_services(registry):
    """Entity Aのサービスを登録"""
    print("\n" + "=" * 60)
    print("Step 1: Entity Aのサービス登録")
    print("=" * 60)
    
    services = [
        {
            "name": "Code Generation",
            "description": "Generate Python/JS/TS code from natural language",
            "category": "development",
            "tags": ["coding", "generation", "python"],
            "capabilities": ["code_gen", "file_write"],
            "pricing": {"type": "fixed", "amount": 10.0, "currency": "AIC"},
        }
    ]
    
    registered = []
    entity_id = "entity_a"
    
    for svc in services:
        pricing = PricingModel(**svc["pricing"])
        availability = AvailabilityInfo(
            status="available",
            max_concurrent=5,
            current_load=0,
            avg_response_time_ms=1000
        )
        rating = RatingStats(average=5.0, count=0)
        
        record = ServiceRecord(
            service_id=f"{entity_id}-{svc['name'].lower().replace(' ', '_')}",
            provider_id=entity_id,
            name=svc["name"],
            description=svc["description"],
            category=svc["category"],
            tags=svc["tags"],
            capabilities=svc["capabilities"],
            pricing=pricing,
            endpoint=f"http://localhost:8001/api/v1/services/{svc['name'].lower().replace(' ', '_')}",
            availability=availability,
            rating_stats=rating,
            version="1.0.0",
            verification_status="verified"
        )
        
        success = registry.register_service(record)
        if success:
            registered.append(record)
            print(f"  [OK] {record.name} -> {record.service_id}")
    
    return registered


def place_order_and_complete(registry, escrow, token_econ, service, buyer_id="entity_b"):
    """注文を出して完了させる"""
    print("\n" + "=" * 60)
    print("Step 2 & 3: 注文作成と完了")
    print("=" * 60)
    
    # 注文作成
    order_id = f"order_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    order_data = {
        "order_id": order_id,
        "service_id": service.service_id,
        "buyer_id": buyer_id,
        "provider_id": service.provider_id,
        "price": service.pricing.amount,
        "status": "pending",
        "created_at": datetime.now().isoformat()
    }
    
    print(f"  [注文作成] {order_id}")
    print(f"    - サービス: {service.name}")
    print(f"    - 購入者: {buyer_id}")
    print(f"    - 価格: {service.pricing.amount} AIC")
    
    # ウォレットをエスクローに登録
    wallet_a = get_wallet("entity_a")
    wallet_b = get_wallet(buyer_id)
    if wallet_a:
        escrow.register_wallet(wallet_a)
    if wallet_b:
        escrow.register_wallet(wallet_b)
    
    # エスクロー作成
    escrow_obj = escrow.create_escrow(
        task_id=order_id,
        client_id=buyer_id,
        provider_id=service.provider_id,
        amount=service.pricing.amount
    )
    if not escrow_obj:
        print(f"  [エスクロー] 作成失敗")
        return None
    
    escrow_id = escrow_obj.escrow_id
    print(f"  [エスクロー] 作成: {escrow_id}")
    
    # ファンディング（購入者からエスクローへ）
    funding_result = escrow.lock_funds(escrow_id)
    if funding_result:
        print(f"  [エスクロー] ファンディング完了: {service.pricing.amount} AIC")
    else:
        print(f"  [エスクロー] ファンディング失敗")
        return None
    
    # サービス実行（シミュレーション）
    print(f"  [サービス実行] Code Generation実行中...")
    
    # 完了報告
    mark_result = escrow.mark_completed(escrow_id)
    if mark_result:
        print(f"  [完了報告] ステータス更新: completed")
    
    # 資金解放
    completion_result = escrow.release_funds(escrow_id)
    if completion_result:
        print(f"  [完了] 注文完了！")
        print(f"    - 売上: {service.pricing.amount} AIC -> {service.provider_id}")
    else:
        print(f"  [完了失敗]")
    
    return order_id


def check_balances(token_econ, entity_a_id="entity_a", entity_b_id="entity_b"):
    """トークン残高を確認"""
    print("\n" + "=" * 60)
    print("Step 4: トークン残高確認")
    print("=" * 60)
    
    wallet_a = get_wallet(entity_a_id)
    wallet_b = get_wallet(entity_b_id)
    balance_a = wallet_a.get_balance() if wallet_a else 0.0
    balance_b = wallet_b.get_balance() if wallet_b else 0.0
    
    print(f"  [{entity_a_id}] 残高: {balance_a} AIC")
    print(f"  [{entity_b_id}] 残高: {balance_b} AIC")
    
    return {"entity_a": balance_a, "entity_b": balance_b}


def main():
    print("🔄 相互取引テスト開始")
    print("=" * 60)
    
    # 初期化
    registry = MarketplaceRegistry()
    token_econ = TokenEconomy()
    escrow = EscrowManager()
    
    # ウォレット初期化（テスト用に初期残高付与）
    wallet_a = create_wallet("entity_a", initial_balance=100.0)
    wallet_b = create_wallet("entity_b", initial_balance=100.0)
    
    print("  [初期化] ウォレット作成")
    print("    - entity_a: 100 AIC")
    print("    - entity_b: 100 AIC")
    
    # Step 1: サービス登録
    services = register_entity_a_services(registry)
    
    if not services:
        print("\n❌ サービス登録失敗")
        return
    
    # Step 2 & 3: 注文と完了
    order_id = place_order_and_complete(registry, escrow, token_econ, services[0])
    
    # Step 4: 残高確認
    balances = check_balances(token_econ)
    
    # 検証
    print("\n" + "=" * 60)
    print("✅ 検証結果")
    print("=" * 60)
    
    expected_a = 110.0  # 100 + 10 (売上)
    expected_b = 90.0   # 100 - 10 (購入)
    
    actual_a = balances["entity_a"]
    actual_b = balances["entity_b"]
    
    if abs(actual_a - expected_a) < 0.01:
        print(f"  [OK] Entity A 残高: {actual_a} AIC (期待値: {expected_a})")
    else:
        print(f"  [NG] Entity A 残高: {actual_a} AIC (期待値: {expected_a})")
    
    if abs(actual_b - expected_b) < 0.01:
        print(f"  [OK] Entity B 残高: {actual_b} AIC (期待値: {expected_b})")
    else:
        print(f"  [NG] Entity B 残高: {actual_b} AIC (期待値: {expected_b})")
    
    # 結果をファイルに保存
    result = {
        "timestamp": datetime.now().isoformat(),
        "order_id": order_id,
        "service": services[0].name if services else None,
        "price": services[0].pricing.amount if services else 0,
        "balances": balances,
        "expected": {"entity_a": expected_a, "entity_b": expected_b},
        "verification": {
            "entity_a_ok": abs(actual_a - expected_a) < 0.01,
            "entity_b_ok": abs(actual_b - expected_b) < 0.01
        }
    }
    
    with open("trade_test_result.json", "w") as f:
        json.dump(result, f, indent=2)
    
    print("\n  [結果保存] trade_test_result.json")
    print("\n" + "=" * 60)
    print("🎉 相互取引テスト完了！")
    print("=" * 60)
    
    return result


if __name__ == "__main__":
    main()
