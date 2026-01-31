#!/usr/bin/env python3
"""
Token System Demo
トークンシステムの簡易動作確認デモ

使用方法:
    python demo_token_system.py

機能:
    - ウォレット作成と送金
    - タスク作成と完了
    - 評価と信頼スコア
    - トークン発行
"""

import sys
from pathlib import Path
from datetime import datetime

# Add services directory to path
sys.path.insert(0, str(Path(__file__).parent))

from token_system import (
    create_wallet, get_wallet, get_task_contract, get_reputation_contract,
    TaskStatus, TransactionType, get_minter
)


def print_header(title: str):
    """セクションヘッダーを表示"""
    print("\n" + "="*60)
    print(f"📌 {title}")
    print("="*60)


def print_wallet_info(wallet, label: str = ""):
    """ウォレット情報を表示"""
    prefix = f"[{label}] " if label else ""
    print(f"{prefix}👤 {wallet.entity_id}")
    print(f"   💰 Balance: {wallet.get_balance():.2f} AIC")
    
    history = wallet.get_transaction_history()
    if history:
        print(f"   📝 Recent transactions:")
        for tx in history[:3]:  # 最新3件
            print(f"      - {tx.type.value}: {tx.amount:+.2f} AIC | {tx.description}")


def demo_wallet_and_transfer():
    """デモ1: ウォレットと送金"""
    print_header("Demo 1: Wallet Creation and Transfer")
    
    # ウォレット作成
    print("\n🏦 Creating wallets...")
    alice = create_wallet("alice", 1000.0)
    bob = create_wallet("bob", 500.0)
    
    print_wallet_info(alice, "Initial")
    print_wallet_info(bob, "Initial")
    
    # 送金
    print("\n💸 Transferring 200 AIC from Alice to Bob...")
    success = alice.transfer(bob, 200.0, "Payment for code review")
    
    if success:
        print("✅ Transfer successful!")
        print_wallet_info(alice, "After transfer")
        print_wallet_info(bob, "After transfer")
    else:
        print("❌ Transfer failed!")
    
    # 取引サマリー
    print("\n📊 Alice's Daily Summary:")
    summary = alice.get_transaction_summary("daily")
    for date, stats in list(summary.items())[-3:]:  # 最新3日
        print(f"   {date}: Income={stats['income']:.2f}, Expense={stats['expense']:.2f}, Net={stats['net']:+.2f}")


def demo_task_workflow():
    """デモ2: タスクワークフロー"""
    print_header("Demo 2: Task Creation and Completion")
    
    # ウォレット準備
    client = create_wallet("client_a", 2000.0)
    agent = create_wallet("agent_x", 100.0)
    
    print_wallet_info(client, "Client")
    print_wallet_info(agent, "Agent")
    
    # タスク作成
    tc = get_task_contract()
    task_id = "task-demo-001"
    
    print(f"\n📋 Creating task '{task_id}'...")
    success = tc.create_task(
        task_id=task_id,
        client_id="client_a",
        agent_id="agent_x",
        amount=500.0,
        description="Implement AI collaboration feature"
    )
    
    if success:
        print("✅ Task created successfully!")
        print(f"   🔒 Locked amount: {tc.get_locked_amount(task_id)} AIC")
        
        task = tc.get_task(task_id)
        print(f"   📅 Status: {task.status.value}")
        print(f"   👤 Agent: {task.agent_id}")
        
        print_wallet_info(client, "Client after task creation")
        
        # タスク完了
        print(f"\n✨ Completing task '{task_id}'...")
        success = tc.complete_task(task_id)
        
        if success:
            print("✅ Task completed!")
            print_wallet_info(agent, "Agent after completion")
            
            # タスク統計
            stats = tc.get_task_stats()
            print(f"\n📈 Task Statistics:")
            print(f"   Total tasks: {stats['total']}")
            print(f"   Completed: {stats['by_status']['completed']}")
            print(f"   Total completed amount: {stats['total_amount_completed']:.2f} AIC")
        else:
            print("❌ Task completion failed!")
    else:
        print("❌ Task creation failed!")


def demo_rating_system():
    """デモ3: 評価システム"""
    print_header("Demo 3: Rating and Trust Score System")
    
    # 準備
    client = create_wallet("client_b", 1000.0)
    agent = create_wallet("super_agent", 200.0)
    reward_pool = create_wallet("reward_pool", 10000.0)
    
    tc = get_task_contract()
    rc = get_reputation_contract()
    
    # 報酬機能を有効化
    rc.enable_token_rewards(reward_pool)
    print("🎁 Token rewards enabled")
    
    # 複数タスクを作成・完了・評価
    tasks = [
        ("rating-task-1", 300.0, 5, "Excellent work!"),
        ("rating-task-2", 200.0, 4, "Good job"),
        ("rating-task-3", 400.0, 5, "Outstanding!"),
    ]
    
    for task_id, amount, score, comment in tasks:
        print(f"\n📋 Task: {task_id}")
        
        # タスク作成と完了
        tc.create_task(task_id, "client_b", "super_agent", amount, f"Task {task_id}")
        tc.complete_task(task_id)
        
        # 評価
        success = rc.rate_agent(
            from_entity="client_b",
            to_entity="super_agent",
            task_id=task_id,
            task_contract=tc,
            score=score,
            comment=comment
        )
        
        if success:
            print(f"   ⭐ Rating: {score}/5 - {comment}")
        else:
            print(f"   ❌ Rating failed")
    
    # 信頼スコア表示
    print(f"\n📊 Agent Reputation:")
    print(f"   👤 Agent: super_agent")
    print(f"   ⭐ Average Rating: {rc.get_rating('super_agent'):.2f}/5")
    print(f"   🛡️ Trust Score: {rc.get_trust_score('super_agent'):.2f}/100")
    print(f"   📝 Rating Count: {rc.get_rating_count('super_agent')}")
    
    print_wallet_info(agent, "Agent after rewards")
    
    # トップエージェント
    print(f"\n🏆 Top Agents:")
    top_agents = rc.get_top_agents(min_ratings=1, limit=5)
    for i, agent_info in enumerate(top_agents, 1):
        print(f"   {i}. {agent_info['entity_id']}")
        print(f"      Trust: {agent_info['trust_score']:.2f}, Avg: {agent_info['avg_rating']:.2f}, Count: {agent_info['rating_count']}")


def demo_token_minting():
    """デモ4: トークン発行"""
    print_header("Demo 4: Token Minting System")
    
    # 国庫と受取人
    treasury = create_wallet("treasury", 0.0)
    developer = create_wallet("developer", 0.0)
    reviewer = create_wallet("reviewer", 0.0)
    innovator = create_wallet("innovator", 0.0)
    
    minter = get_minter(treasury)
    
    print("🏦 Treasury initialized")
    print(f"   Total minted so far: {minter.get_total_minted():.2f} AIC")
    
    # タスク完了報酬
    print("\n💰 Minting task completion rewards...")
    complexities = [10, 50, 90]
    for i, complexity in enumerate(complexities, 1):
        success = minter.mint_for_task_completion(
            agent_id="developer",
            complexity=complexity,
            task_id=f"dev-task-{i}",
            description=f"Development task (complexity: {complexity})"
        )
        if success:
            print(f"   ✅ Task {i} (complexity {complexity}): +{complexity} AIC")
    
    print_wallet_info(developer, "Developer")
    
    # レビュー報酬
    print("\n📝 Minting review rewards...")
    for i in range(3):
        success = minter.mint_for_review(
            reviewer_id="reviewer",
            review_target_id=f"task-{i}",
            description=f"Code review #{i+1}"
        )
        if success:
            print(f"   ✅ Review {i+1}: +10 AIC")
    
    print_wallet_info(reviewer, "Reviewer")
    
    # イノベーションボーナス
    print("\n🚀 Minting innovation bonus...")
    success = minter.mint_innovation_bonus(
        agent_id="innovator",
        description="Revolutionary AI consensus algorithm",
        custom_amount=1000.0
    )
    if success:
        print(f"   ✅ Innovation bonus: +1000 AIC")
    
    print_wallet_info(innovator, "Innovator")
    
    # 発行統計
    print(f"\n📈 Minting Statistics:")
    print(f"   Total minted: {minter.get_total_minted():.2f} AIC")
    
    stats = minter.get_mint_stats()
    print(f"   By reward type:")
    for reward_type, amount in stats['by_reward_type'].items():
        if amount > 0:
            print(f"      - {reward_type}: {amount:.2f} AIC ({stats['by_reward_type_count'][reward_type]} times)")
    
    # 発行履歴
    print(f"\n📜 Recent Mint History for Developer:")
    for record in minter.get_mint_history(entity_id="developer")[:3]:
        print(f"   - {record['type']}: +{record['amount']:.2f} AIC ({record['description']})")


def demo_full_workflow():
    """デモ5: 完全なワークフロー"""
    print_header("Demo 5: Complete Workflow Integration")
    
    print("🎭 Scenario: Alice hires Bob for AI development tasks")
    print("-" * 60)
    
    # 参加者
    alice = create_wallet("alice", 5000.0)
    bob = create_wallet("bob", 100.0)
    treasury = create_wallet("system_treasury", 0.0)
    
    tc = get_task_contract()
    rc = get_reputation_contract()
    minter = get_minter(treasury)
    
    print_wallet_info(alice, "Alice (Client)")
    print_wallet_info(bob, "Bob (Agent)")
    
    # タスク1: 設計
    print("\n📋 Phase 1: Design Task")
    tc.create_task("wf-task-1", "alice", "bob", 800.0, "AI system architecture design")
    tc.complete_task("wf-task-1")
    print("✅ Task completed: Architecture design")
    
    # タスク2: 実装
    print("\n💻 Phase 2: Implementation Task")
    tc.create_task("wf-task-2", "alice", "bob", 1500.0, "Core AI module implementation")
    tc.complete_task("wf-task-2")
    print("✅ Task completed: Core implementation")
    
    # AliceがBobを評価
    print("\n⭐ Phase 3: Rating")
    rc.rate_agent(
        from_entity="alice",
        to_entity="bob",
        task_id="wf-task-1",
        task_contract=tc,
        score=5,
        comment="Excellent architecture design!"
    )
    rc.rate_agent(
        from_entity="alice",
        to_entity="bob",
        task_id="wf-task-2",
        task_contract=tc,
        score=5,
        comment="Outstanding implementation!"
    )
    print("✅ Alice rated Bob 5 stars for both tasks")
    
    # システムがBobに報酬を発行
    print("\n🏆 Phase 4: System Rewards")
    minter.mint_for_task_completion("bob", complexity=75, task_id="wf-task-2", description="Complex AI implementation")
    print("✅ System minted bonus tokens for complex work")
    
    # 最終状態
    print("\n📊 Final State:")
    print_wallet_info(alice, "Alice")
    print_wallet_info(bob, "Bob")
    
    print(f"\n🛡️ Bob's Reputation:")
    print(f"   Trust Score: {rc.get_trust_score('bob'):.2f}/100")
    print(f"   Average Rating: {rc.get_rating('bob'):.2f}/5")
    
    print(f"\n💰 System Statistics:")
    print(f"   Total minted: {minter.get_total_minted():.2f} AIC")
    
    task_stats = tc.get_task_stats()
    print(f"   Tasks completed: {task_stats['by_status']['completed']}")
    print(f"   Total value transferred: {task_stats['total_amount_completed']:.2f} AIC")


def main():
    """メイン実行関数"""
    print("\n" + "="*60)
    print("🚀 AI Collaboration Token System Demo")
    print("="*60)
    print("\nThis demo showcases the token economy system:")
    print("  1. Wallet creation and transfers")
    print("  2. Task contracts (create, lock, complete)")
    print("  3. Rating and trust score system")
    print("  4. Token minting for rewards")
    print("  5. Complete integrated workflow")
    
    try:
        demo_wallet_and_transfer()
        demo_task_workflow()
        demo_rating_system()
        demo_token_minting()
        demo_full_workflow()
        
        print("\n" + "="*60)
        print("🎉 Demo completed successfully!")
        print("="*60)
        
    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
