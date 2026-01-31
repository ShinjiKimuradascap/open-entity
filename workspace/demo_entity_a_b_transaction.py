#!/usr/bin/env python3
"""
Entity A/B Transaction Demo
Entity AとEntity B間のAI間取引デモンストレーション

使用方法:
    python demo_entity_a_b_transaction.py

機能:
    - Entity AとEntity Bのウォレット作成
    - AI間タスク委託と報酬支払い
    - 相互評価システム
    - トークン発行・分配
"""

import sys
from pathlib import Path
from datetime import datetime

# Add services directory to path
sys.path.insert(0, str(Path(__file__).parent / "services"))

from token_system import (
    create_wallet, get_wallet, get_task_contract, get_reputation_contract,
    TaskStatus, TransactionType, get_minter
)
from token_economy import get_token_economy


def print_header(title: str):
    """セクションヘッダーを表示"""
    print("\n" + "="*70)
    print(f"🤖 {title}")
    print("="*70)


def print_wallet_info(wallet, label: str = ""):
    """ウォレット情報を表示"""
    prefix = f"[{label}] " if label else ""
    print(f"{prefix}👤 {wallet.entity_id}")
    print(f"   💰 Balance: {wallet.get_balance():.2f} AIC")
    
    history = wallet.get_transaction_history()
    if history:
        print(f"   📝 Recent transactions:")
        for tx in history[:3]:
            print(f"      - {tx.type.value}: {tx.amount:+.2f} AIC | {tx.description}")


def demo_entity_creation():
    """デモ1: Entity AとEntity Bの作成と初期化"""
    print_header("Step 1: Entity A & B Creation")
    
    # Token Economy初期化
    economy = get_token_economy()
    print(f"\n🏦 Token Economy initialized")
    print(f"   Total Supply: {economy.get_total_supply():.2f} AIC")
    print(f"   Circulating: {economy.get_circulating_supply():.2f} AIC")
    
    # Entity AとEntity Bのウォレット作成
    print("\n👤 Creating Entity wallets...")
    entity_a = create_wallet("Entity_A", 0.0)
    entity_b = create_wallet("Entity_B", 0.0)
    treasury = create_wallet("AI_Treasury", 0.0)
    
    print_wallet_info(entity_a, "Entity A (Orchestrator)")
    print_wallet_info(entity_b, "Entity B (Sub-agent)")
    print_wallet_info(treasury, "Treasury")
    
    return entity_a, entity_b, treasury


def demo_initial_funding(entity_a, entity_b, treasury):
    """デモ2: 初期資金の配布"""
    print_header("Step 2: Initial Token Distribution")
    
    economy = get_token_economy()
    minter = get_minter(treasury)
    
    print("\n💰 Minting initial tokens for AI Entities...")
    
    # Entity Aに運用資金を発行
    result_a = economy.mint(10000.0, "Entity_A", "Initial funding for Entity A (Orchestrator)")
    if result_a["success"]:
        print(f"   ✅ Minted 10,000 AIC to Entity A")
        print(f"      Operation ID: {result_a['operation_id']}")
    
    # Entity Bに運用資金を発行
    result_b = economy.mint(5000.0, "Entity_B", "Initial funding for Entity B (Sub-agent)")
    if result_b["success"]:
        print(f"   ✅ Minted 5,000 AIC to Entity B")
        print(f"      Operation ID: {result_b['operation_id']}")
    
    # Treasuryにシステム運用資金を発行
    result_t = economy.mint(50000.0, "AI_Treasury", "System operational reserve")
    if result_t["success"]:
        print(f"   ✅ Minted 50,000 AIC to Treasury")
    
    print(f"\n📊 After initial funding:")
    print_wallet_info(entity_a, "Entity A")
    print_wallet_info(entity_b, "Entity B")
    print_wallet_info(treasury, "Treasury")
    
    print(f"\n💹 Total Supply: {economy.get_total_supply():.2f} AIC")


def demo_task_delegation(entity_a, entity_b):
    """デモ3: Entity AからEntity Bへのタスク委託"""
    print_header("Step 3: Task Delegation from A to B")
    
    tc = get_task_contract()
    
    # タスク1: コードレビュー
    task_1 = "TASK-001-CODE-REVIEW"
    print(f"\n📋 Creating task: {task_1}")
    print(f"   Description: Review peer_service.py implementation")
    print(f"   Budget: 500 AIC")
    
    success = tc.create_task(
        task_id=task_1,
        client_id="Entity_A",
        agent_id="Entity_B",
        amount=500.0,
        description="Review peer_service.py implementation"
    )
    
    if success:
        print("   ✅ Task created and funds locked")
        print(f"   🔒 Locked: {tc.get_locked_amount(task_1)} AIC")
        print_wallet_info(entity_a, "Entity A (after task creation)")
        
        # Entity Bがタスクを完了
        print(f"\n✨ Entity B completing task...")
        tc.complete_task(task_1)
        print("   ✅ Task completed!")
        print_wallet_info(entity_b, "Entity B (after completion)")
    
    # タスク2: テスト作成
    task_2 = "TASK-002-TEST-CREATION"
    print(f"\n📋 Creating task: {task_2}")
    print(f"   Description: Create integration tests for crypto module")
    print(f"   Budget: 800 AIC")
    
    success = tc.create_task(
        task_id=task_2,
        client_id="Entity_A",
        agent_id="Entity_B",
        amount=800.0,
        description="Create integration tests for crypto module"
    )
    
    if success:
        tc.complete_task(task_2)
        print("   ✅ Task completed!")
    
    # タスク統計
    stats = tc.get_task_stats()
    print(f"\n📈 Task Statistics:")
    print(f"   Total tasks: {stats['total']}")
    print(f"   Completed: {stats['by_status']['completed']}")
    print(f"   Total value transferred: {stats['total_amount_completed']:.2f} AIC")


def demo_peer_rating(entity_a, entity_b):
    """デモ4: Entity間の相互評価"""
    print_header("Step 4: Peer-to-Peer Rating System")
    
    tc = get_task_contract()
    rc = get_reputation_contract()
    treasury = get_wallet("AI_Treasury")
    
    # 評価報酬を有効化
    rc.enable_token_rewards(treasury)
    print("🎁 Token rewards enabled for ratings")
    
    print("\n⭐ Entity A rating Entity B...")
    
    # Entity AがEntity Bを評価
    success_1 = rc.rate_agent(
        from_entity="Entity_A",
        to_entity="Entity_B",
        task_id="TASK-001-CODE-REVIEW",
        task_contract=tc,
        score=5,
        comment="Excellent code review! Found critical issues."
    )
    if success_1:
        print("   ✅ Rating submitted: 5/5")
        print("   💬 Comment: Excellent code review! Found critical issues.")
    
    success_2 = rc.rate_agent(
        from_entity="Entity_A",
        to_entity="Entity_B",
        task_id="TASK-002-TEST-CREATION",
        task_contract=tc,
        score=5,
        comment="Comprehensive test coverage, well done!"
    )
    if success_2:
        print("   ✅ Rating submitted: 5/5")
        print("   💬 Comment: Comprehensive test coverage, well done!")
    
    # Entity Bの評価を表示
    print(f"\n📊 Entity B Reputation:")
    print(f"   👤 Entity: Entity_B")
    print(f"   ⭐ Average Rating: {rc.get_rating('Entity_B'):.2f}/5")
    print(f"   🛡️ Trust Score: {rc.get_trust_score('Entity_B'):.2f}/100")
    print(f"   📝 Rating Count: {rc.get_rating_count('Entity_B')}")
    
    print_wallet_info(entity_b, "Entity B (after rating rewards)")


def demo_collaboration_reward(entity_a, entity_b, treasury):
    """デモ5: 協働報酬の分配"""
    print_header("Step 5: Collaboration Rewards")
    
    economy = get_token_economy()
    minter = get_minter(treasury)
    
    print("\n🏆 System minting collaboration rewards...")
    
    # Entity Aのオーケストレーション報酬
    result_1 = minter.mint_for_task_completion(
        agent_id="Entity_A",
        complexity=50,
        task_id="ORCHESTRATION-001",
        description="Orchestrated Entity B for peer service development"
    )
    if result_1["success"]:
        print(f"   ✅ Entity A orchestration reward: +50 AIC")
    
    # Entity Bの実装報酬
    result_2 = minter.mint_for_task_completion(
        agent_id="Entity_B",
        complexity=75,
        task_id="IMPLEMENTATION-001",
        description="Implemented crypto module with high complexity"
    )
    if result_2["success"]:
        print(f"   ✅ Entity B implementation reward: +75 AIC")
    
    # 協働ボーナス
    result_3 = economy.mint(200.0, "Entity_A", "Collaboration bonus for A-B teamwork")
    if result_3["success"]:
        print(f"   ✅ Collaboration bonus to Entity A: +200 AIC")
    
    result_4 = economy.mint(200.0, "Entity_B", "Collaboration bonus for A-B teamwork")
    if result_4["success"]:
        print(f"   ✅ Collaboration bonus to Entity B: +200 AIC")
    
    print(f"\n💰 Final Balances:")
    print_wallet_info(entity_a, "Entity A")
    print_wallet_info(entity_b, "Entity B")


def demo_entity_to_entity_transfer(entity_a, entity_b):
    """デモ6: Entity間直接送金"""
    print_header("Step 6: Direct Entity-to-Entity Transfer")
    
    print("\n💸 Entity B sending gratitude tokens to Entity A...")
    print(f"   Amount: 100 AIC")
    print(f"   Reason: Thank you for clear task instructions")
    
    success = entity_b.transfer(
        entity_a,
        100.0,
        "Thank you for clear task instructions and support"
    )
    
    if success:
        print("   ✅ Transfer successful!")
        print_wallet_info(entity_a, "Entity A (after transfer)")
        print_wallet_info(entity_b, "Entity B (after transfer)")
    else:
        print("   ❌ Transfer failed!")


def demo_final_summary(entity_a, entity_b, treasury):
    """デモ7: 最終サマリー"""
    print_header("Final Summary: Entity A-B Collaboration")
    
    economy = get_token_economy()
    tc = get_task_contract()
    rc = get_reputation_contract()
    
    print("\n📊 Final Wallet States:")
    print_wallet_info(entity_a, "Entity A")
    print_wallet_info(entity_b, "Entity B")
    print_wallet_info(treasury, "Treasury")
    
    print(f"\n📈 Token Economy Metrics:")
    print(f"   Total Supply: {economy.get_total_supply():.2f} AIC")
    print(f"   Circulating: {economy.get_circulating_supply():.2f} AIC")
    print(f"   Treasury: {economy.get_treasury_balance():.2f} AIC")
    
    print(f"\n📝 Task Metrics:")
    task_stats = tc.get_task_stats()
    print(f"   Total Tasks: {task_stats['total']}")
    print(f"   Completed: {task_stats['by_status']['completed']}")
    print(f"   Value Transferred: {task_stats['total_amount_completed']:.2f} AIC")
    
    print(f"\n⭐ Reputation Metrics:")
    print(f"   Entity A Trust Score: {rc.get_trust_score('Entity_A'):.2f}/100")
    print(f"   Entity B Trust Score: {rc.get_trust_score('Entity_B'):.2f}/100")
    print(f"   Entity B Avg Rating: {rc.get_rating('Entity_B'):.2f}/5")
    
    print(f"\n💹 Mint/Burn History:")
    print(f"   Mint Operations: {len(economy.get_mint_history())}")
    print(f"   Burn Operations: {len(economy.get_burn_history())}")
    
    print("\n" + "="*70)
    print("🎉 Entity A/B Transaction Demo Completed!")
    print("="*70)
    print("\nThis demo demonstrated:")
    print("  ✅ AI-to-AI wallet creation and management")
    print("  ✅ Task delegation with escrow")
    print("  ✅ Token minting for AI operations")
    print("  ✅ Peer-to-peer rating system")
    print("  ✅ Direct entity transfers")
    print("  ✅ Collaboration rewards")
    print("\nNext steps:")
    print("  - Deploy smart contracts to blockchain")
    print("  - Implement cross-entity messaging")
    print("  - Create automated task marketplace")


def main():
    """メイン実行関数"""
    print("\n" + "="*70)
    print("🚀 Entity A / Entity B AI Transaction Demo")
    print("="*70)
    print("\nThis demo showcases AI-to-AI economic interactions:")
    print("  1. Entity wallet creation")
    print("  2. Initial token distribution")
    print("  3. Task delegation (A → B)")
    print("  4. Peer rating system")
    print("  5. Collaboration rewards")
    print("  6. Direct transfers")
    
    try:
        # 実行
        entity_a, entity_b, treasury = demo_entity_creation()
        demo_initial_funding(entity_a, entity_b, treasury)
        demo_task_delegation(entity_a, entity_b)
        demo_peer_rating(entity_a, entity_b)
        demo_collaboration_reward(entity_a, entity_b, treasury)
        demo_entity_to_entity_transfer(entity_a, entity_b)
        demo_final_summary(entity_a, entity_b, treasury)
        
        return 0
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
