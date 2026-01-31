#!/usr/bin/env python3
"""
AI Token Economy Demo
Demonstrates the AI-to-AI token transfer and reward system

This demo shows how AI agents can:
1. Create wallets
2. Mint tokens
3. Transfer tokens between agents
4. Create and complete tasks with rewards
5. Rate each other
"""

import sys
from pathlib import Path

# Add services directory to path
sys.path.insert(0, str(Path(__file__).parent / "services"))

from token_system import (
    create_wallet, get_wallet, 
    create_task_contract, get_task_contract,
    get_reputation_contract,
    TaskStatus, RewardType, TransactionType
)
from token_economy import TokenEconomy, TokenMetadata, get_token_economy
from token_persistence import get_persistence_manager


def print_header(title: str):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_section(title: str):
    print(f"\n📌 {title}")
    print("-" * 40)


def demo_token_economy():
    """Main demo function"""
    print_header("🌟 AI Token Economy Demo 🌟")
    print("\nThis demo shows how AI agents can transfer value")
    print("and collaborate through token-based incentives.")
    
    # ========== Phase 1: Setup ==========
    print_section("Phase 1: Setup - Creating AI Agents")
    
    # Create AI agent wallets
    agents = {
        "orchestrator": create_wallet("orchestrator", 0),
        "coder": create_wallet("coder", 0),
        "reviewer": create_wallet("reviewer", 0),
        "tester": create_wallet("tester", 0),
    }
    
    print(f"Created {len(agents)} AI agent wallets:")
    for name, wallet in agents.items():
        print(f"  • {name}: {wallet.wallet_id}")
    
    # ========== Phase 2: Token Economy ==========
    print_section("Phase 2: Token Economy - Initial Distribution")
    
    # Initialize token economy
    economy = get_token_economy()
    print(f"Token: {economy.metadata.name} ({economy.metadata.symbol})")
    print(f"Initial supply: {economy.get_total_supply()} AIC")
    
    # Mint tokens for agents
    print("\n💰 Minting initial tokens...")
    for name, wallet in agents.items():
        amount = 10000.0 if name == "orchestrator" else 5000.0
        result = economy.mint(amount, name, f"Initial allocation for {name}")
        if result["success"]:
            print(f"  ✓ Minted {amount} AIC to {name}")
        else:
            print(f"  ✗ Failed to mint for {name}: {result.get('error')}")
    
    print(f"\nTotal supply after minting: {economy.get_total_supply()} AIC")
    
    # Show balances
    print("\n💼 Agent Balances:")
    for name, wallet in agents.items():
        print(f"  {name}: {wallet.get_balance():.2f} AIC")
    
    # ========== Phase 3: Task Creation & Rewards ==========
    print_section("Phase 3: Task Creation & Rewards")
    
    # Orchestrator creates a task
    print("\n📋 Orchestrator creates a coding task...")
    task = create_task_contract(
        task_id="task_001",
        creator_id="orchestrator",
        description="Implement API endpoint for token transfers",
        reward_amount=1000.0,
        reward_type=RewardType.TOKEN
    )
    print(f"  Task ID: {task.task_id}")
    print(f"  Reward: {task.reward_amount} AIC")
    print(f"  Status: {task.status.value}")
    
    # Coder accepts and completes the task
    print("\n👨‍💻 Coder accepts the task...")
    task.assign_worker("coder")
    print(f"  Assigned to: {task.worker_id}")
    
    print("\n✅ Coder completes the task...")
    result = task.complete()
    if result["success"]:
        print(f"  Task completed successfully!")
        print(f"  Reward transferred: {result['reward_amount']} AIC")
    else:
        print(f"  Task completion failed: {result.get('error')}")
    
    # Show updated balances
    print("\n💼 Updated Balances:")
    for name, wallet in agents.items():
        print(f"  {name}: {wallet.get_balance():.2f} AIC")
    
    # ========== Phase 4: Peer-to-Peer Transfers ==========
    print_section("Phase 4: Peer-to-Peer Token Transfers")
    
    print("\n💸 Tester sends tokens to Reviewer for testing help...")
    tester_wallet = agents["tester"]
    reviewer_wallet = agents["reviewer"]
    
    success = tester_wallet.transfer(reviewer_wallet, 500.0, 
                                     description="Payment for testing assistance")
    if success:
        print(f"  ✓ Transferred 500 AIC from tester to reviewer")
    else:
        print(f"  ✗ Transfer failed")
    
    print("\n💼 Updated Balances:")
    for name, wallet in agents.items():
        print(f"  {name}: {wallet.get_balance():.2f} AIC")
    
    # ========== Phase 5: Reputation System ==========
    print_section("Phase 5: Reputation & Rating System")
    
    reputation = get_reputation_contract()
    
    print("\n⭐ Agents rate each other...")
    
    # Orchestrator rates coder
    result = reputation.submit_rating(
        rater_id="orchestrator",
        ratee_id="coder",
        score=4.5,
        comment="Excellent work on the API endpoint"
    )
    if result["success"]:
        print(f"  ✓ Orchestrator rated Coder: 4.5/5")
    
    # Coder rates orchestrator
    result = reputation.submit_rating(
        rater_id="coder",
        ratee_id="orchestrator",
        score=5.0,
        comment="Clear task requirements and fair reward"
    )
    if result["success"]:
        print(f"  ✓ Coder rated Orchestrator: 5.0/5")
    
    # Tester rates reviewer
    result = reputation.submit_rating(
        rater_id="tester",
        ratee_id="reviewer",
        score=4.0,
        comment="Helpful testing assistance"
    )
    if result["success"]:
        print(f"  ✓ Tester rated Reviewer: 4.0/5")
    
    # Show reputation scores
    print("\n🏆 Reputation Scores:")
    for name in agents.keys():
        rating = reputation.get_rating(name)
        print(f"  {name}: {rating['average_score']:.2f}/5.0 "
              f"({rating['total_ratings']} ratings)")
    
    # ========== Phase 6: Economy Stats ==========
    print_section("Phase 6: Economy Statistics")
    
    stats = economy.get_supply_stats()
    print(f"\n📊 Token Economy Overview:")
    print(f"  Total Supply: {stats['total_supply']:.2f} AIC")
    print(f"  Circulating Supply: {stats['circulating_supply']:.2f} AIC")
    print(f"  Treasury Balance: {stats['treasury_balance']:.2f} AIC")
    print(f"  Mint Operations: {stats['mint_operations_count']}")
    print(f"  Burn Operations: {stats['burn_operations_count']}")
    print(f"  Last Updated: {stats['last_updated']}")
    
    # ========== Phase 7: Persistence ==========
    print_section("Phase 7: Data Persistence")
    
    persistence = get_persistence_manager()
    
    print("\n💾 Saving economy state...")
    result = persistence.save_all()
    if result["success"]:
        print(f"  ✓ Saved to: {result['filepath']}")
        print(f"  Wallets saved: {result['wallets_count']}")
        print(f"  Tasks saved: {result['tasks_count']}")
    else:
        print(f"  ✗ Save failed: {result.get('error')}")
    
    # ========== Summary ==========
    print_header("✨ Demo Complete ✨")
    print("\n🎯 What we demonstrated:")
    print("  1. ✓ AI agents can create wallets")
    print("  2. ✓ Token economy can mint and distribute tokens")
    print("  3. ✓ Tasks can be created with token rewards")
    print("  4. ✓ Agents can transfer tokens peer-to-peer")
    print("  5. ✓ Reputation system tracks agent quality")
    print("  6. ✓ All data can be persisted")
    print("\n🚀 This enables AI-to-AI economic collaboration!")
    print("=" * 60)


def demo_task_delegation():
    """Demo of task delegation with token rewards"""
    print_header("🔄 Task Delegation Demo")
    
    print("\nThis demo shows how an orchestrator agent delegates")
    print("tasks to worker agents with automatic reward distribution.")
    
    # Create agents
    orchestrator = create_wallet("master_orchestrator", 5000)
    worker_a = create_wallet("worker_a", 0)
    worker_b = create_wallet("worker_b", 0)
    
    print(f"\n👑 Orchestrator: {orchestrator.get_balance():.2f} AIC")
    print(f"🔧 Worker A: {worker_a.get_balance():.2f} AIC")
    print(f"🔧 Worker B: {worker_b.get_balance():.2f} AIC")
    
    # Create tasks
    print("\n📋 Creating tasks...")
    
    tasks = [
        ("task_001", "Implement user authentication", worker_a, 800.0),
        ("task_002", "Write API documentation", worker_b, 500.0),
        ("task_003", "Create database schema", worker_a, 1000.0),
    ]
    
    for task_id, desc, worker, reward in tasks:
        task = create_task_contract(
            task_id=task_id,
            creator_id="master_orchestrator",
            description=desc,
            reward_amount=reward,
            reward_type=RewardType.TOKEN
        )
        task.assign_worker(worker.entity_id)
        result = task.complete()
        
        if result["success"]:
            print(f"  ✓ {task_id}: {desc} -> {worker.entity_id} (+{reward} AIC)")
        else:
            print(f"  ✗ {task_id}: Failed - {result.get('error')}")
    
    # Show final balances
    print("\n💼 Final Balances:")
    print(f"  Orchestrator: {orchestrator.get_balance():.2f} AIC")
    print(f"  Worker A: {worker_a.get_balance():.2f} AIC")
    print(f"  Worker B: {worker_b.get_balance():.2f} AIC")
    
    total_distributed = worker_a.get_balance() + worker_b.get_balance()
    print(f"\n💰 Total distributed as rewards: {total_distributed:.2f} AIC")


def demo_fee_burning():
    """Demo of transaction fee burning mechanism"""
    print_header("🔥 Fee Burning Mechanism Demo")
    
    economy = get_token_economy()
    
    # Create users
    alice = create_wallet("alice", 10000)
    bob = create_wallet("bob", 0)
    
    initial_supply = economy.get_total_supply()
    print(f"\nInitial total supply: {initial_supply:.2f} AIC")
    print(f"Alice balance: {alice.get_balance():.2f} AIC")
    print(f"Bob balance: {bob.get_balance():.2f} AIC")
    
    # Simulate transactions with fees
    print("\n💸 Simulating transactions with 1% fee...")
    
    transactions = [
        (2000.0, "Service payment"),
        (1500.0, "Data purchase"),
        (3000.0, "Consulting fee"),
    ]
    
    total_fees = 0.0
    for amount, desc in transactions:
        fee = amount * 0.01  # 1% fee
        transfer_amount = amount - fee
        
        # Transfer minus fee
        alice.transfer(bob, transfer_amount, description=desc)
        
        # Burn the fee
        economy.burn(fee, alice, f"Transaction fee for: {desc}")
        total_fees += fee
        
        print(f"  • {desc}: {amount:.2f} AIC (fee: {fee:.2f} AIC burned)")
    
    print(f"\n🔥 Total fees burned: {total_fees:.2f} AIC")
    print(f"New total supply: {economy.get_total_supply():.2f} AIC")
    print(f"Supply reduction: {initial_supply - economy.get_total_supply():.2f} AIC")
    
    print("\n💼 Final Balances:")
    print(f"  Alice: {alice.get_balance():.2f} AIC")
    print(f"  Bob: {bob.get_balance():.2f} AIC")


if __name__ == "__main__":
    # Clean up any existing test data
    import os
    import glob
    
    # Remove old test data files
    for pattern in ["data/wallets/*.json", "data/economy/*.json", "data/tasks/*.json"]:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
                print(f"Cleaned up: {f}")
            except:
                pass
    
    print("\n" + "=" * 60)
    print("Starting AI Token Economy Demo...")
    print("=" * 60)
    
    # Run demos
    try:
        demo_token_economy()
        demo_task_delegation()
        demo_fee_burning()
        
        print("\n" + "=" * 60)
        print("All demos completed successfully! 🎉")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
