#!/usr/bin/env python3
"""
Escrow Manager 単体テスト
AI間取引プロトコルのエスクロー管理クラスのテスト
"""

import unittest
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

# テスト対象モジュール
from services.escrow_manager import (
    EscrowManager,
    Escrow,
    EscrowStatus,
    DisputeResolution,
    VerificationResult,
    create_escrow_manager,
    create_verification_result,
    TOKEN_SYSTEM_AVAILABLE,
)

# TokenWallet のインポート
if TOKEN_SYSTEM_AVAILABLE:
    from services.token_system import TokenWallet


# ロギング設定
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class TestEscrowManager(unittest.TestCase):
    """EscrowManager の単体テスト"""
    
    def setUp(self) -> None:
        """各テスト前のセットアップ"""
        self.manager = create_escrow_manager()
        
        # モックウォレット作成
        if TOKEN_SYSTEM_AVAILABLE:
            self.client_wallet = TokenWallet("client-1", _balance=1000.0)
            self.provider_wallet = TokenWallet("provider-1", _balance=0.0)
            self.manager.register_wallet(self.client_wallet)
            self.manager.register_wallet(self.provider_wallet)
        
        self.task_id = "task-test-001"
        self.client_id = "client-1"
        self.provider_id = "provider-1"
        self.amount = 100.0
    
    def tearDown(self) -> None:
        """各テスト後のクリーンアップ"""
        self.manager = None
        self.client_wallet = None
        self.provider_wallet = None
    
    def test_create_escrow(self) -> None:
        """エスクロー作成のテスト"""
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # 検証
        self.assertIsNotNone(escrow)
        self.assertIsNotNone(escrow.escrow_id)
        self.assertEqual(escrow.task_id, self.task_id)
        self.assertEqual(escrow.client_id, self.client_id)
        self.assertEqual(escrow.provider_id, self.provider_id)
        self.assertEqual(escrow.amount, self.amount)
        self.assertEqual(escrow.status, EscrowStatus.CREATED.value)
        self.assertIsNotNone(escrow.created_at)
        self.assertIsNotNone(escrow.deadline)
        
        # マネージャーから取得できることを確認
        retrieved = self.manager.get_escrow(escrow.escrow_id)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.escrow_id, escrow.escrow_id)
    
    def test_create_escrow_invalid_amount(self) -> None:
        """無効な金額でのエスクロー作成テスト"""
        # 0以下の金額
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=0,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.assertIsNone(escrow)
        
        # 負の金額
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=-100,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.assertIsNone(escrow)
    
    def test_create_escrow_missing_ids(self) -> None:
        """クライアントID/プロバイダID欠落テスト"""
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id="",
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.assertIsNone(escrow)
    
    def test_lock_funds(self) -> None:
        """資金ロックのテスト"""
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.assertIsNotNone(escrow)
        
        # ロック前の残高を記録
        if TOKEN_SYSTEM_AVAILABLE:
            initial_balance = self.client_wallet.get_balance()
        
        # 資金ロック
        success = self.manager.lock_funds(escrow.escrow_id)
        self.assertTrue(success)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.LOCKED.value)
        
        # 残高確認
        if TOKEN_SYSTEM_AVAILABLE:
            self.assertEqual(self.client_wallet.get_balance(), initial_balance - self.amount)
    
    def test_lock_funds_insufficient_balance(self) -> None:
        """残高不足でのロックテスト"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # 残高不足のクライアントを作成
        poor_client = TokenWallet("poor-client", _balance=10.0)
        self.manager.register_wallet(poor_client)
        
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id="poor-client",
            provider_id=self.provider_id,
            amount=100.0,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # ロックは失敗する
        success = self.manager.lock_funds(escrow.escrow_id)
        self.assertFalse(success)
    
    def test_lock_funds_invalid_status(self) -> None:
        """無効な状態でのロックテスト"""
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # ロック
        self.manager.lock_funds(escrow.escrow_id)
        
        # 再度ロック（失敗する）
        success = self.manager.lock_funds(escrow.escrow_id)
        self.assertFalse(success)
    
    def test_release_funds(self) -> None:
        """資金解放のテスト"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # エスクロー作成・ロック・完了
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        self.manager.mark_completed(escrow.escrow_id)
        
        # 解放前の残高を記録
        provider_initial = self.provider_wallet.get_balance()
        
        # 検証結果を作成
        verification = create_verification_result(
            verified=True,
            score=95.0,
            checks={"deliverables": True, "tests": True}
        )
        
        # 資金解放
        success = self.manager.release_funds(escrow.escrow_id, verification)
        self.assertTrue(success)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.RELEASED.value)
        self.assertIsNotNone(escrow.released_at)
        
        # プロバイダに支払われたことを確認
        self.assertEqual(self.provider_wallet.get_balance(), provider_initial + self.amount)
    
    def test_release_funds_verification_failed(self) -> None:
        """検証失敗での解放テスト"""
        # エスクロー作成・ロック・完了
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        self.manager.mark_completed(escrow.escrow_id)
        
        # 検証失敗の結果を作成
        verification = create_verification_result(
            verified=False,
            score=30.0,
            checks={"deliverables": False, "tests": False},
            errors=["Missing deliverables", "Tests failed"]
        )
        
        # 解放は失敗する
        success = self.manager.release_funds(escrow.escrow_id, verification)
        self.assertFalse(success)
    
    def test_cancel_escrow(self) -> None:
        """エスクロー取消のテスト"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # 取消
        success = self.manager.cancel_escrow(escrow.escrow_id, reason="Client request")
        self.assertTrue(success)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.CANCELLED.value)
    
    def test_cancel_escrow_with_refund(self) -> None:
        """ロック済みエスクローの取消・返金テスト"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # エスクロー作成・ロック
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        
        # ロック前の残高
        client_initial = self.client_wallet.get_balance()
        
        # 取消
        success = self.manager.cancel_escrow(escrow.escrow_id, reason="Task cancelled")
        self.assertTrue(success)
        
        # 返金されていることを確認
        self.assertEqual(self.client_wallet.get_balance(), client_initial + self.amount)
    
    def test_cancel_escrow_invalid_status(self) -> None:
        """無効な状態での取消テスト"""
        # エスクロー作成・ロック・完了
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        self.manager.mark_completed(escrow.escrow_id)
        
        # 取消は失敗する
        success = self.manager.cancel_escrow(escrow.escrow_id, reason="Too late")
        self.assertFalse(success)
    
    def test_open_dispute(self) -> None:
        """紛争申し立てのテスト"""
        # エスクロー作成・ロック
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        
        # 紛争申し立て
        success = self.manager.open_dispute(escrow.escrow_id, reason="Quality issue")
        self.assertTrue(success)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.DISPUTED.value)
        self.assertEqual(escrow.dispute_reason, "Quality issue")
        self.assertEqual(escrow.resolution, DisputeResolution.PENDING.value)
    
    def test_open_dispute_invalid_status(self) -> None:
        """無効な状態での紛争申し立てテスト"""
        # エスクロー作成（未ロック）
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # 紛争申し立ては失敗する
        success = self.manager.open_dispute(escrow.escrow_id, reason="Too early")
        self.assertFalse(success)
    
    def test_resolve_dispute_client_wins(self) -> None:
        """紛争解決：クライアント勝訴のテスト"""
        # エスクロー作成・ロック・紛争
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        self.manager.open_dispute(escrow.escrow_id, reason="Quality issue")
        
        # クライアント勝訴
        success = self.manager.resolve_dispute(
            escrow.escrow_id,
            decision=DisputeResolution.CLIENT_WINS,
            resolution_notes="Provider did not meet requirements"
        )
        self.assertTrue(success)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.COMPLETED.value)
        self.assertEqual(escrow.resolution, DisputeResolution.CLIENT_WINS.value)
        self.assertEqual(escrow.resolution_amount, 0.0)  # 全額返金
    
    def test_resolve_dispute_provider_wins(self) -> None:
        """紛争解決：プロバイダ勝訴のテスト"""
        # エスクロー作成・ロック・紛争
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        self.manager.open_dispute(escrow.escrow_id, reason="Quality issue")
        
        # プロバイダ勝訴
        success = self.manager.resolve_dispute(
            escrow.escrow_id,
            decision=DisputeResolution.PROVIDER_WINS,
            resolution_notes="Work completed satisfactorily"
        )
        self.assertTrue(success)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.COMPLETED.value)
        self.assertEqual(escrow.resolution, DisputeResolution.PROVIDER_WINS.value)
        self.assertEqual(escrow.resolution_amount, self.amount)  # 全額支払
    
    def test_resolve_dispute_split(self) -> None:
        """紛争解決：折衷案（分割）のテスト"""
        # エスクロー作成・ロック・紛争
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        self.manager.open_dispute(escrow.escrow_id, reason="Partial completion")
        
        # 折衷案（50%支払）
        split_amount = self.amount * 0.5
        success = self.manager.resolve_dispute(
            escrow.escrow_id,
            decision=DisputeResolution.SPLIT,
            resolution_amount=split_amount,
            resolution_notes="Partial work completed"
        )
        self.assertTrue(success)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.COMPLETED.value)
        self.assertEqual(escrow.resolution, DisputeResolution.SPLIT.value)
        self.assertEqual(escrow.resolution_amount, split_amount)
    
    def test_resolve_dispute_not_in_dispute(self) -> None:
        """紛争状態でないエスクローの解決テスト"""
        # エスクロー作成・ロック（紛争状態でない）
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.manager.lock_funds(escrow.escrow_id)
        
        # 紛争解決は失敗する
        success = self.manager.resolve_dispute(
            escrow.escrow_id,
            decision=DisputeResolution.CLIENT_WINS
        )
        self.assertFalse(success)
    
    def test_expired_escrow(self) -> None:
        """期限切れエスクローのテスト"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # 過去の期限でエスクロー作成
        past_deadline = datetime.now(timezone.utc) - timedelta(hours=1)
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=past_deadline
        )
        self.manager.lock_funds(escrow.escrow_id)
        
        # ロック前の残高
        client_initial = self.client_wallet.get_balance()
        
        # 期限切れチェック
        expired_ids = self.manager.check_expired_escrows()
        self.assertIn(escrow.escrow_id, expired_ids)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.EXPIRED.value)
        
        # 返金されていることを確認
        self.assertEqual(self.client_wallet.get_balance(), client_initial + self.amount)
    
    def test_expired_escrow_not_locked(self) -> None:
        """未ロックの期限切れエスクローテスト"""
        # 過去の期限でエスクロー作成（未ロック）
        past_deadline = datetime.now(timezone.utc) - timedelta(hours=1)
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=past_deadline
        )
        
        # 期限切れチェック
        expired_ids = self.manager.check_expired_escrows()
        self.assertIn(escrow.escrow_id, expired_ids)
        
        # 状態を確認
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.EXPIRED.value)
    
    def test_complete_flow(self) -> None:
        """完結フローテスト：作成→ロック→完了→解放"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # 初期残高を記録
        client_initial = self.client_wallet.get_balance()
        provider_initial = self.provider_wallet.get_balance()
        
        # 1. エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        self.assertIsNotNone(escrow)
        self.assertEqual(escrow.status, EscrowStatus.CREATED.value)
        
        # 2. 資金ロック
        success = self.manager.lock_funds(escrow.escrow_id)
        self.assertTrue(success)
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.LOCKED.value)
        self.assertEqual(self.client_wallet.get_balance(), client_initial - self.amount)
        
        # 3. タスク完了
        success = self.manager.mark_completed(escrow.escrow_id)
        self.assertTrue(success)
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.COMPLETED.value)
        
        # 4. 資金解放
        verification = create_verification_result(
            verified=True,
            score=95.0,
            checks={"deliverables": True, "tests": True, "documentation": True}
        )
        success = self.manager.release_funds(escrow.escrow_id, verification)
        self.assertTrue(success)
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertEqual(escrow.status, EscrowStatus.RELEASED.value)
        self.assertIsNotNone(escrow.released_at)
        self.assertEqual(self.provider_wallet.get_balance(), provider_initial + self.amount)
        
        # 履歴を確認
        history = self.manager.get_status_history(escrow.escrow_id)
        self.assertEqual(len(history), 4)  # CREATED, LOCKED, COMPLETED, RELEASED
        
        logger.info(f"Complete flow test passed: {len(history)} status changes")
    
    def test_token_system_integration(self) -> None:
        """TokenWallet連携のテスト"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # 複数のウォレットを作成
        client2 = TokenWallet("client-2", _balance=500.0)
        provider2 = TokenWallet("provider-2", _balance=0.0)
        self.manager.register_wallet(client2)
        self.manager.register_wallet(provider2)
        
        # 複数のエスクローを作成
        for i in range(3):
            escrow = self.manager.create_escrow(
                task_id=f"task-multi-{i}",
                client_id="client-2",
                provider_id="provider-2",
                amount=100.0,
                deadline=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            self.manager.lock_funds(escrow.escrow_id)
        
        # 残高を確認
        self.assertEqual(client2.get_balance(), 200.0)  # 500 - 300
        self.assertEqual(provider2.get_balance(), 0.0)  # まだ解放されていない
        
        # 全てのエスクローを完了・解放
        for escrow in self.manager.list_active_escrows():
            if escrow.client_id == "client-2":
                self.manager.mark_completed(escrow.escrow_id)
                verification = create_verification_result(verified=True, score=90.0)
                self.manager.release_funds(escrow.escrow_id, verification)
        
        # 支払い後の残高
        self.assertEqual(client2.get_balance(), 200.0)  # 変わらない
        self.assertEqual(provider2.get_balance(), 300.0)  # 300受け取った
    
    def test_statistics(self) -> None:
        """統計情報のテスト"""
        if not TOKEN_SYSTEM_AVAILABLE:
            self.skipTest("TokenSystem not available")
        
        # 初期統計
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_escrows"], 0)
        
        # エスクローを複数作成
        for i in range(5):
            escrow = self.manager.create_escrow(
                task_id=f"task-stat-{i}",
                client_id=self.client_id,
                provider_id=self.provider_id,
                amount=100.0,
                deadline=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            self.manager.lock_funds(escrow.escrow_id)
            
            if i < 2:
                self.manager.mark_completed(escrow.escrow_id)
                verification = create_verification_result(verified=True, score=90.0)
                self.manager.release_funds(escrow.escrow_id, verification)
            elif i == 2:
                self.manager.cancel_escrow(escrow.escrow_id, reason="Test cancel")
            elif i == 3:
                self.manager.open_dispute(escrow.escrow_id, reason="Test dispute")
        
        # 統計を確認
        stats = self.manager.get_statistics()
        self.assertEqual(stats["total_escrows"], 5)
        self.assertEqual(stats["by_status"][EscrowStatus.RELEASED.value], 2)
        self.assertEqual(stats["by_status"][EscrowStatus.CANCELLED.value], 1)
        self.assertEqual(stats["by_status"][EscrowStatus.DISPUTED.value], 1)
        self.assertEqual(stats["by_status"][EscrowStatus.LOCKED.value], 1)
        self.assertEqual(stats["active_escrows"], 3)  # LOCKED + DISPUTED + ?
        self.assertEqual(stats["disputed_escrows"], 1)
        self.assertEqual(stats["total_released_amount"], 200.0)  # 2 * 100
    
    def test_get_escrow_by_task(self) -> None:
        """タスクIDでのエスクロー検索テスト"""
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id="unique-task-id",
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # タスクIDで検索
        found = self.manager.get_escrow_by_task("unique-task-id")
        self.assertIsNotNone(found)
        self.assertEqual(found.escrow_id, escrow.escrow_id)
        
        # 存在しないタスクID
        not_found = self.manager.get_escrow_by_task("non-existent-task")
        self.assertIsNone(not_found)
    
    def test_list_active_escrows(self) -> None:
        """アクティブエスクロー一覧テスト"""
        # 複数のエスクローを作成
        for i in range(3):
            escrow = self.manager.create_escrow(
                task_id=f"task-active-{i}",
                client_id=self.client_id,
                provider_id=self.provider_id,
                amount=100.0,
                deadline=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            if i == 0:
                self.manager.lock_funds(escrow.escrow_id)
            elif i == 1:
                self.manager.lock_funds(escrow.escrow_id)
                self.manager.mark_completed(escrow.escrow_id)
        
        # アクティブ一覧
        active = self.manager.list_active_escrows()
        self.assertEqual(len(active), 3)  # 全てアクティブ
        
        # フィルタリング
        locked = self.manager.list_active_escrows()
        locked_count = len([e for e in locked if e.status == EscrowStatus.LOCKED.value])
        self.assertEqual(locked_count, 1)
    
    def test_status_history(self) -> None:
        """状態変更履歴のテスト"""
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # 履歴を確認
        history = self.manager.get_status_history(escrow.escrow_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["status"], EscrowStatus.CREATED.value)
        
        # 状態変更
        self.manager.lock_funds(escrow.escrow_id)
        self.manager.mark_completed(escrow.escrow_id)
        
        # 履歴を再確認
        history = self.manager.get_status_history(escrow.escrow_id)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[1]["status"], EscrowStatus.LOCKED.value)
        self.assertEqual(history[2]["status"], EscrowStatus.COMPLETED.value)
    
    def test_escrow_dataclass_methods(self) -> None:
        """Escrow dataclass メソッドのテスト"""
        # エスクロー作成
        escrow = self.manager.create_escrow(
            task_id=self.task_id,
            client_id=self.client_id,
            provider_id=self.provider_id,
            amount=self.amount,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # to_dict
        data = escrow.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["task_id"], self.task_id)
        self.assertEqual(data["amount"], self.amount)
        
        # from_dict
        restored = Escrow.from_dict(data)
        self.assertEqual(restored.escrow_id, escrow.escrow_id)
        self.assertEqual(restored.task_id, escrow.task_id)
        
        # can_lock
        self.assertTrue(restored.can_lock())
        self.manager.lock_funds(escrow.escrow_id)
        escrow = self.manager.get_escrow(escrow.escrow_id)
        self.assertFalse(escrow.can_lock())
    
    def test_verification_result(self) -> None:
        """VerificationResult のテスト"""
        # 検証結果作成
        result = create_verification_result(
            verified=True,
            score=85.5,
            checks={"test1": True, "test2": False},
            errors=["Minor issue"]
        )
        
        self.assertIsInstance(result, VerificationResult)
        self.assertTrue(result.verified)
        self.assertEqual(result.score, 85.5)
        self.assertEqual(result.checks, {"test1": True, "test2": False})
        self.assertEqual(result.errors, ["Minor issue"])
        
        # to_dict
        data = result.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["verified"], True)


class TestEscrowEdgeCases(unittest.TestCase):
    """エッジケースのテスト"""
    
    def setUp(self) -> None:
        """セットアップ"""
        self.manager = create_escrow_manager()
        if TOKEN_SYSTEM_AVAILABLE:
            self.client_wallet = TokenWallet("edge-client", _balance=1000.0)
            self.provider_wallet = TokenWallet("edge-provider", _balance=0.0)
            self.manager.register_wallet(self.client_wallet)
            self.manager.register_wallet(self.provider_wallet)
    
    def tearDown(self) -> None:
        """クリーンアップ"""
        self.manager = None
    
    def test_nonexistent_escrow(self) -> None:
        """存在しないエスクローへのアクセステスト"""
        # 存在しないIDで各種操作
        self.assertIsNone(self.manager.get_escrow("non-existent"))
        self.assertFalse(self.manager.lock_funds("non-existent"))
        self.assertFalse(self.manager.release_funds("non-existent"))
        self.assertFalse(self.manager.cancel_escrow("non-existent"))
        self.assertFalse(self.manager.open_dispute("non-existent", "reason"))
        self.assertFalse(self.manager.mark_completed("non-existent"))
    
    def test_wallet_not_registered(self) -> None:
        """未登録ウォレットでのロックテスト"""
        # 未登録クライアントでエスクロー作成
        manager2 = create_escrow_manager()
        escrow = manager2.create_escrow(
            task_id="task-unregistered",
            client_id="unregistered-client",
            provider_id="unregistered-provider",
            amount=100.0,
            deadline=datetime.now(timezone.utc) + timedelta(hours=24)
        )
        
        # ロックは失敗する（ウォレットが見つからない）
        success = manager2.lock_funds(escrow.escrow_id)
        self.assertFalse(success)


if __name__ == "__main__":
    unittest.main(verbosity=2)
