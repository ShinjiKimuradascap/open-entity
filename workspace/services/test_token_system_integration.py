#!/usr/bin/env python3
"""
Token System Integration Tests
トークンシステムの統合テスト

テスト項目:
1. ウォレット作成 → 送金 → 残高確認のフロー
2. タスク作成 → 完了 → 報酬配布のフロー
3. 永続化（save/load）の動作確認
4. 評価送信 → 信頼スコア計算のフロー
"""

import sys
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta

# Add services directory to path
sys.path.insert(0, str(Path(__file__).parent))

from token_system import (
    create_wallet, get_wallet, get_task_contract, get_reputation_contract,
    TokenWallet, TaskContract, ReputationContract, TaskStatus, TransactionType,
    save_all, load_all, get_minter
)
from token_persistence import PersistenceManager


class TokenIntegrationTest:
    """トークンシステム統合テスト"""
    
    def __init__(self):
        self.test_results = []
        self.temp_dir = None
        self.original_data_dir = None
        
    def setup(self):
        """テスト環境のセットアップ"""
        # 一時ディレクトリを作成
        self.temp_dir = tempfile.mkdtemp(prefix="token_test_")
        print(f"📁 Test data directory: {self.temp_dir}")
        
        # グローバルレジストリをクリア
        import token_system
        token_system._wallet_registry.clear()
        token_system._task_contract = None
        token_system._reputation_contract = None
        token_system._minter = None
        token_system._persistence = None
        
        return self.temp_dir
    
    def teardown(self):
        """テスト環境のクリーンアップ"""
        if self.temp_dir and Path(self.temp_dir).exists():
            shutil.rmtree(self.temp_dir)
            print(f"🗑️ Cleaned up: {self.temp_dir}")
    
    def log(self, message: str, success: bool = True):
        """テスト結果をログ"""
        status = "✅" if success else "❌"
        print(f"{status} {message}")
        self.test_results.append((message, success))
    
    def test_wallet_creation_and_transfer(self):
        """Test 1: ウォレット作成 → 送金 → 残高確認"""
        print("\n" + "="*60)
        print("🧪 Test 1: Wallet Creation and Transfer")
        print("="*60)
        
        # ウォレット作成
        alice = create_wallet("alice", 1000.0)
        bob = create_wallet("bob", 500.0)
        
        assert alice.get_balance() == 1000.0, "Alice initial balance should be 1000"
        assert bob.get_balance() == 500.0, "Bob initial balance should be 500"
        self.log(f"Created wallets: Alice ({alice.get_balance()} AIC), Bob ({bob.get_balance()} AIC)")
        
        # 送金
        success = alice.transfer(bob, 200.0, "Payment for services")
        assert success, "Transfer should succeed"
        assert alice.get_balance() == 800.0, "Alice balance should be 800"
        assert bob.get_balance() == 700.0, "Bob balance should be 700"
        self.log(f"Transfer 200 AIC: Alice ({alice.get_balance()} AIC) → Bob ({bob.get_balance()} AIC)")
        
        # 取引履歴の確認
        alice_history = alice.get_transaction_history()
        bob_history = bob.get_transaction_history()
        
        assert len(alice_history) == 1, "Alice should have 1 transaction"
        assert len(bob_history) == 1, "Bob should have 1 transaction"
        assert alice_history[0].type == TransactionType.TRANSFER_OUT
        assert bob_history[0].type == TransactionType.TRANSFER_IN
        self.log(f"Transaction history verified: Alice ({len(alice_history)} tx), Bob ({len(bob_history)} tx)")
        
        # 不十分な残高での送金は失敗する
        success = alice.transfer(bob, 1000.0, "Should fail")
        assert not success, "Transfer with insufficient balance should fail"
        self.log("Insufficient balance transfer correctly rejected")
        
        return True
    
    def test_task_workflow(self):
        """Test 2: タスク作成 → 完了 → 報酬配布"""
        print("\n" + "="*60)
        print("🧪 Test 2: Task Creation and Completion Workflow")
        print("="*60)
        
        # ウォレット準備
        client = create_wallet("client", 1000.0)
        agent = create_wallet("agent", 100.0)
        
        tc = get_task_contract()
        initial_client_balance = client.get_balance()
        initial_agent_balance = agent.get_balance()
        
        # タスク作成
        task_id = "task-001"
        success = tc.create_task(
            task_id=task_id,
            client_id="client",
            agent_id="agent",
            amount=300.0,
            description="Develop feature X"
        )
        assert success, "Task creation should succeed"
        assert client.get_balance() == initial_client_balance - 300.0, "Client balance should decrease"
        assert tc.get_locked_amount(task_id) == 300.0, "Tokens should be locked"
        self.log(f"Task created: {task_id} with 300 AIC locked")
        
        # タスク状態確認
        task = tc.get_task(task_id)
        assert task is not None, "Task should exist"
        assert task.status == TaskStatus.IN_PROGRESS, "Task should be in_progress"
        assert task.agent_id == "agent", "Task agent should be 'agent'"
        self.log(f"Task status: {task.status.value}, Agent: {task.agent_id}")
        
        # タスク完了
        success = tc.complete_task(task_id)
        assert success, "Task completion should succeed"
        assert agent.get_balance() == initial_agent_balance + 300.0, "Agent should receive payment"
        assert tc.get_locked_amount(task_id) == 0.0, "Locked amount should be released"
        self.log(f"Task completed: Agent received 300 AIC (balance: {agent.get_balance()} AIC)")
        
        # タスク統計
        stats = tc.get_task_stats()
        assert stats["total"] == 1, "Should have 1 total task"
        assert stats["by_status"]["completed"] == 1, "Should have 1 completed task"
        assert stats["total_amount_completed"] == 300.0, "Completed amount should be 300"
        self.log(f"Task stats: {stats['total']} tasks, {stats['total_amount_completed']} AIC completed")
        
        return True
    
    def test_persistence(self):
        """Test 3: 永続化（save/load）の動作確認"""
        print("\n" + "="*60)
        print("🧪 Test 3: Persistence (Save/Load)")
        print("="*60)
        
        # テストデータ作成
        wallet1 = create_wallet("persist_user1", 500.0)
        wallet2 = create_wallet("persist_user2", 300.0)
        
        tc = get_task_contract()
        tc.create_task("persist-task-1", "persist_user1", "persist_user2", 100.0, "Test task")
        
        # PersistenceManagerを使用
        pm = PersistenceManager(self.temp_dir)
        
        # 保存
        wallets = {"persist_user1": wallet1, "persist_user2": wallet2}
        tasks = tc._tasks
        
        save_success = pm.save_wallets(wallets)
        assert save_success, "Wallet save should succeed"
        self.log(f"Wallets saved to {self.temp_dir}")
        
        save_success = pm.save_tasks(tasks)
        assert save_success, "Task save should succeed"
        self.log(f"Tasks saved to {self.temp_dir}")
        
        # バックアップ作成
        backup_path = pm.create_backup("test")
        assert backup_path is not None, "Backup creation should succeed"
        self.log(f"Backup created: {backup_path}")
        
        # グローバルレジストリをクリア
        import token_system
        token_system._wallet_registry.clear()
        token_system._task_contract = None
        
        # 読み込み
        loaded_wallets = pm.load_wallets()
        assert len(loaded_wallets) == 2, f"Should load 2 wallets, got {len(loaded_wallets)}"
        assert "persist_user1" in loaded_wallets, "persist_user1 should be loaded"
        assert loaded_wallets["persist_user1"].get_balance() == 500.0, "Balance should be preserved"
        self.log(f"Wallets loaded: {len(loaded_wallets)} wallets with correct balances")
        
        loaded_tasks = pm.load_tasks()
        assert len(loaded_tasks) == 1, f"Should load 1 task, got {len(loaded_tasks)}"
        assert "persist-task-1" in loaded_tasks, "persist-task-1 should be loaded"
        self.log(f"Tasks loaded: {len(loaded_tasks)} tasks")
        
        # save_all / load_all テスト
        import token_system
        token_system._wallet_registry = loaded_wallets
        token_system._task_contract = None
        tc = get_task_contract()
        for task in loaded_tasks.values():
            tc._tasks[task.task_id] = task
        
        save_all_result = save_all(Path(self.temp_dir) / "global_save")
        assert save_all_result, "save_all should succeed"
        self.log("Global save_all executed successfully")
        
        load_all_result = load_all(Path(self.temp_dir) / "global_save")
        assert load_all_result, "load_all should succeed"
        loaded_wallet = get_wallet("persist_user1")
        assert loaded_wallet is not None, "Wallet should exist after load"
        assert loaded_wallet.get_balance() == 500.0, "Balance should be preserved"
        self.log("Global load_all executed successfully with correct data")
        
        return True
    
    def test_rating_and_trust_score(self):
        """Test 4: 評価送信 → 信頼スコア計算"""
        print("\n" + "="*60)
        print("🧪 Test 4: Rating and Trust Score Calculation")
        print("="*60)
        
        # 準備
        client = create_wallet("rater", 1000.0)
        agent = create_wallet("rated_agent", 100.0)
        reward_pool = create_wallet("reward_pool", 10000.0)
        
        tc = get_task_contract()
        rc = get_reputation_contract()
        
        # 報酬機能を有効化
        rc.enable_token_rewards(reward_pool)
        self.log("Token rewards enabled")
        
        # タスク作成と完了
        tc.create_task("rating-task-1", "rater", "rated_agent", 200.0, "Test task for rating")
        tc.complete_task("rating-task-1")
        initial_agent_balance = agent.get_balance()
        self.log(f"Task completed: rated_agent balance = {initial_agent_balance} AIC")
        
        # 評価送信（新しいシグネチャ対応）
        success = rc.rate_agent(
            from_entity="rater",
            to_entity="rated_agent",
            task_id="rating-task-1",
            task_contract=tc,
            score=5,
            comment="Excellent work!"
        )
        assert success, "Rating should succeed"
        self.log("Rating submitted: 5 stars")
        
        # 信頼スコア確認
        trust_score = rc.get_trust_score("rated_agent")
        avg_rating = rc.get_rating("rated_agent")
        rating_count = rc.get_rating_count("rated_agent")
        
        assert trust_score > 0, "Trust score should be calculated"
        assert avg_rating == 5.0, f"Average rating should be 5.0, got {avg_rating}"
        assert rating_count == 1, "Should have 1 rating"
        self.log(f"Trust score: {trust_score:.2f}, Avg rating: {avg_rating:.2f}, Count: {rating_count}")
        
        # 複数評価で信頼スコアの変化を確認
        # 2つ目のタスク
        tc.create_task("rating-task-2", "rater", "rated_agent", 100.0, "Second task")
        tc.complete_task("rating-task-2")
        
        success = rc.rate_agent(
            from_entity="rater",
            to_entity="rated_agent",
            task_id="rating-task-2",
            task_contract=tc,
            score=4,
            comment="Good job"
        )
        assert success, "Second rating should succeed"
        
        avg_rating = rc.get_rating("rated_agent")
        assert avg_rating == 4.5, f"Average should be 4.5, got {avg_rating}"
        self.log(f"Second rating submitted: 4 stars, new avg: {avg_rating:.2f}")
        
        # トップエージェント一覧
        top_agents = rc.get_top_agents(min_ratings=1, limit=5)
        assert len(top_agents) >= 1, "Should have at least 1 top agent"
        assert top_agents[0]["entity_id"] == "rated_agent", "rated_agent should be top"
        self.log(f"Top agents: {len(top_agents)} found, top is {top_agents[0]['entity_id']}")
        
        # 重複評価は拒否される
        success = rc.rate_agent(
            from_entity="rater",
            to_entity="rated_agent",
            task_id="rating-task-1",  # 既に評価済み
            task_contract=tc,
            score=3,
            comment="Trying to rate again"
        )
        assert not success, "Duplicate rating should be rejected"
        self.log("Duplicate rating correctly rejected")
        
        return True
    
    def test_token_minting(self):
        """Test 5: トークン発行機能"""
        print("\n" + "="*60)
        print("🧪 Test 5: Token Minting")
        print("="*60)
        
        # 国庫ウォレット作成
        treasury = create_wallet("treasury", 0.0)
        minter = get_minter(treasury)
        
        # 受取人ウォレット
        recipient = create_wallet("recipient", 0.0)
        
        initial_minted = minter.get_total_minted()
        
        # タスク完了報酬
        success = minter.mint_for_task_completion(
            agent_id="recipient",
            complexity=50,
            task_id="mint-task-1",
            description="Complex AI integration"
        )
        assert success, "Task reward minting should succeed"
        
        # 複雑度50 → 50 AIC発行（1-100の範囲でクリップ）
        assert recipient.get_balance() == 50.0, f"Should have 50 AIC, got {recipient.get_balance()}"
        self.log(f"Task reward minted: 50 AIC (complexity: 50)")
        
        # レビュー報酬
        success = minter.mint_for_review(
            reviewer_id="recipient",
            review_target_id="some-task",
            description="Quality code review"
        )
        assert success, "Review reward minting should succeed"
        assert recipient.get_balance() == 60.0, f"Should have 60 AIC, got {recipient.get_balance()}"
        self.log(f"Review reward minted: 10 AIC (total: {recipient.get_balance()} AIC)")
        
        # イノベーションボーナス
        success = minter.mint_innovation_bonus(
            agent_id="recipient",
            description="Revolutionary AI architecture",
            custom_amount=500.0
        )
        assert success, "Innovation bonus should succeed"
        assert recipient.get_balance() == 560.0, f"Should have 560 AIC, got {recipient.get_balance()}"
        self.log(f"Innovation bonus minted: 500 AIC (total: {recipient.get_balance()} AIC)")
        
        # 発行統計
        total_minted = minter.get_total_minted()
        assert total_minted == 560.0, f"Total minted should be 560, got {total_minted}"
        self.log(f"Total minted: {total_minted} AIC")
        
        # 発行履歴
        history = minter.get_mint_history(entity_id="recipient")
        assert len(history) == 3, f"Should have 3 mint records, got {len(history)}"
        self.log(f"Mint history: {len(history)} records")
        
        return True
    
    def run_all_tests(self):
        """全テストを実行"""
        print("\n" + "="*60)
        print("🚀 Token System Integration Tests Starting")
        print("="*60)
        
        try:
            self.setup()
            
            tests = [
                ("Wallet Creation and Transfer", self.test_wallet_creation_and_transfer),
                ("Task Workflow", self.test_task_workflow),
                ("Persistence", self.test_persistence),
                ("Rating and Trust Score", self.test_rating_and_trust_score),
                ("Token Minting", self.test_token_minting),
            ]
            
            passed = 0
            failed = 0
            
            for name, test_func in tests:
                try:
                    test_func()
                    passed += 1
                except Exception as e:
                    failed += 1
                    self.log(f"Test '{name}' failed: {e}", success=False)
                    import traceback
                    traceback.print_exc()
            
            # 結果サマリー
            print("\n" + "="*60)
            print("📊 Test Results Summary")
            print("="*60)
            print(f"✅ Passed: {passed}")
            print(f"❌ Failed: {failed}")
            print(f"📈 Success Rate: {passed/(passed+failed)*100:.1f}%")
            
            return failed == 0
            
        finally:
            self.teardown()


def main():
    """メイン実行関数"""
    tester = TokenIntegrationTest()
    success = tester.run_all_tests()
    
    if success:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n💥 Some tests failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
