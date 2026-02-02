#!/usr/bin/env python3
"""
Escrow Manager 自動修復機能
Self-Healing Module for Escrow Manager

Entity C タスク: C-1769932324-5794
[新機能] Escrow Manager自動修復機能

このモジュールは以下の自動修復機能を提供します:
1. 期限切れエスクローの自動検出と処理
2. 不整合な状態の自動修正
3. スタックしたエスクローの自動解放
4. 健全性チェックと自動修復アクション
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass
from enum import Enum

try:
    from services.escrow_manager import (
        EscrowManager, Escrow, EscrowStatus, DisputeResolution
    )
    ESCROW_AVAILABLE = True
except ImportError:
    ESCROW_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealingAction(Enum):
    """修復アクションの種類"""
    EXPIRE_ESCROW = "expire_escrow"
    RELEASE_STUCK = "release_stuck"
    CANCEL_ORPHANED = "cancel_orphaned"
    NOTIFY_PARTIES = "notify_parties"
    UPDATE_METADATA = "update_metadata"


@dataclass
class HealingReport:
    """修復レポート"""
    timestamp: datetime
    checks_performed: int
    issues_found: int
    issues_fixed: int
    actions_taken: List[Dict]
    errors: List[str]


class EscrowSelfHealing:
    """
    Escrow Manager 自動修復システム
    
    定期的にエスクローの健全性をチェックし、
    問題を自動検出・修復します。
    """
    
    def __init__(
        self,
        escrow_manager: 'EscrowManager',
        check_interval: int = 300,  # 5分ごとにチェック
        auto_heal: bool = True,
        max_escrow_age_days: int = 30,
        stuck_threshold_hours: int = 24
    ):
        """
        初期化
        
        Args:
            escrow_manager: EscrowManagerインスタンス
            check_interval: チェック間隔（秒）
            auto_heal: 自動修復を有効にするか
            max_escrow_age_days: エスクローの最大存続日数
            stuck_threshold_hours: スタックとみなす時間（時間）
        """
        if not ESCROW_AVAILABLE:
            raise ImportError("EscrowManager not available")
        
        self._escrow_manager = escrow_manager
        self._check_interval = check_interval
        self._auto_heal = auto_heal
        self._max_escrow_age_days = max_escrow_age_days
        self._stuck_threshold_hours = stuck_threshold_hours
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._last_report: Optional[HealingReport] = None
    
    async def start(self):
        """自動修復ループを開始"""
        if self._running:
            logger.warning("Self-healing already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._healing_loop())
        logger.info("Escrow self-healing started")
    
    async def stop(self):
        """自動修復ループを停止"""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Escrow self-healing stopped")
    
    async def _healing_loop(self):
        """修復ループ"""
        while self._running:
            try:
                await self.perform_health_check()
            except Exception as e:
                logger.error(f"Error in healing loop: {e}")
            
            await asyncio.sleep(self._check_interval)
    
    async def perform_health_check(self) -> HealingReport:
        """
        健全性チェックを実行
        
        Returns:
            HealingReport: 修復レポート
        """
        report = HealingReport(
            timestamp=datetime.now(),
            checks_performed=0,
            issues_found=0,
            issues_fixed=0,
            actions_taken=[],
            errors=[]
        )
        
        try:
            # 1. 期限切れエスクローのチェック
            expired = await self._check_expired_escrows()
            report.checks_performed += 1
            report.issues_found += len(expired)
            
            if self._auto_heal and expired:
                fixed = await self._heal_expired_escrows(expired)
                report.issues_fixed += fixed
                report.actions_taken.append({
                    "action": "expire_escrows",
                    "count": fixed
                })
            
            # 2. スタックしたエスクローのチェック
            stuck = await self._check_stuck_escrows()
            report.checks_performed += 1
            report.issues_found += len(stuck)
            
            if self._auto_heal and stuck:
                fixed = await self._heal_stuck_escrows(stuck)
                report.issues_fixed += fixed
                report.actions_taken.append({
                    "action": "release_stuck",
                    "count": fixed
                })
            
            # 3. オーファンエスクローのチェック
            orphaned = await self._check_orphaned_escrows()
            report.checks_performed += 1
            report.issues_found += len(orphaned)
            
            if self._auto_heal and orphaned:
                fixed = await self._heal_orphaned_escrows(orphaned)
                report.issues_fixed += fixed
                report.actions_taken.append({
                    "action": "cancel_orphaned",
                    "count": fixed
                })
            
            # 4. 古いエスクローのチェック
            old = await self._check_old_escrows()
            report.checks_performed += 1
            report.issues_found += len(old)
            
            if old:
                report.actions_taken.append({
                    "action": "notify_old_escrows",
                    "count": len(old)
                })
            
        except Exception as e:
            logger.error(f"Error during health check: {e}")
            report.errors.append(str(e))
        
        self._last_report = report
        
        # サマリーログ
        if report.issues_found > 0:
            logger.info(
                f"Health check complete: {report.issues_found} issues found, "
                f"{report.issues_fixed} fixed"
            )
        
        return report
    
    async def _check_expired_escrows(self) -> List[str]:
        """期限切れエスクローを検出"""
        expired = []
        now = datetime.now()
        
        for escrow_id, escrow in self._escrow_manager._escrows.items():
            if escrow.status in [EscrowStatus.CREATED.value, EscrowStatus.LOCKED.value]:
                if escrow.deadline and now > escrow.deadline:
                    expired.append(escrow_id)
                    logger.warning(f"Detected expired escrow: {escrow_id}")
        
        return expired
    
    async def _heal_expired_escrows(self, escrow_ids: List[str]) -> int:
        """期限切れエスクローを修復"""
        fixed = 0
        
        for escrow_id in escrow_ids:
            try:
                escrow = self._escrow_manager._escrows.get(escrow_id)
                if not escrow:
                    continue
                
                if escrow.status == EscrowStatus.CREATED.value:
                    # 未ロックの場合はキャンセル
                    self._escrow_manager.cancel_escrow(
                        escrow_id,
                        reason="Auto-cancelled: expired before locking"
                    )
                    logger.info(f"Auto-cancelled expired escrow: {escrow_id}")
                    fixed += 1
                    
                elif escrow.status == EscrowStatus.LOCKED.value:
                    # ロック済みの場合は紛争申し立て
                    self._escrow_manager.open_dispute(
                        escrow_id,
                        reason="Auto-disputed: deadline exceeded"
                    )
                    logger.info(f"Auto-disputed expired escrow: {escrow_id}")
                    fixed += 1
                    
            except Exception as e:
                logger.error(f"Error healing expired escrow {escrow_id}: {e}")
        
        return fixed
    
    async def _check_stuck_escrows(self) -> List[str]:
        """スタックしたエスクローを検出"""
        stuck = []
        now = datetime.now()
        threshold = timedelta(hours=self._stuck_threshold_hours)
        
        for escrow_id, escrow in self._escrow_manager._escrows.items():
            if escrow.status == EscrowStatus.COMPLETED.value:
                # COMPLETED状態が長時間続いている場合
                last_updated = self._get_last_update_time(escrow_id)
                if last_updated and (now - last_updated) > threshold:
                    stuck.append(escrow_id)
                    logger.warning(f"Detected stuck escrow: {escrow_id}")
        
        return stuck
    
    async def _heal_stuck_escrows(self, escrow_ids: List[str]) -> int:
        """スタックしたエスクローを修復"""
        fixed = 0
        
        for escrow_id in escrow_ids:
            try:
                # 強制的に解放
                result = self._escrow_manager.release_payment(
                    escrow_id,
                    release_notes="Auto-released: stuck escrow"
                )
                if result:
                    logger.info(f"Auto-released stuck escrow: {escrow_id}")
                    fixed += 1
            except Exception as e:
                logger.error(f"Error healing stuck escrow {escrow_id}: {e}")
        
        return fixed
    
    async def _check_orphaned_escrows(self) -> List[str]:
        """オーファンエスクロー（関連タスクがない）を検出"""
        orphaned = []
        
        for escrow_id, escrow in self._escrow_manager._escrows.items():
            if escrow.status in [EscrowStatus.CREATED.value, EscrowStatus.LOCKED.value]:
                # タスクが存在するかチェック（簡易実装）
                if not self._check_task_exists(escrow.task_id):
                    orphaned.append(escrow_id)
                    logger.warning(f"Detected orphaned escrow: {escrow_id}")
        
        return orphaned
    
    async def _heal_orphaned_escrows(self, escrow_ids: List[str]) -> int:
        """オーファンエスクローを修復"""
        fixed = 0
        
        for escrow_id in escrow_ids:
            try:
                self._escrow_manager.cancel_escrow(
                    escrow_id,
                    reason="Auto-cancelled: orphaned (task not found)"
                )
                logger.info(f"Auto-cancelled orphaned escrow: {escrow_id}")
                fixed += 1
            except Exception as e:
                logger.error(f"Error healing orphaned escrow {escrow_id}: {e}")
        
        return fixed
    
    async def _check_old_escrows(self) -> List[str]:
        """古いエスクローを検出"""
        old = []
        now = datetime.now()
        max_age = timedelta(days=self._max_escrow_age_days)
        
        for escrow_id, escrow in self._escrow_manager._escrows.items():
            if escrow.created_at and (now - escrow.created_at) > max_age:
                old.append(escrow_id)
        
        return old
    
    def _get_last_update_time(self, escrow_id: str) -> Optional[datetime]:
        """エスクローの最終更新時間を取得"""
        history = self._escrow_manager._status_history.get(escrow_id, [])
        if history:
            return history[-1]["timestamp"]
        return None
    
    def _check_task_exists(self, task_id: str) -> bool:
        """タスクが存在するかチェック（簡易実装）"""
        # 実際の実装ではタスク管理システムをチェック
        # ここでは常にTrueを返す（実際には適切に実装）
        return True
    
    def get_last_report(self) -> Optional[HealingReport]:
        """最後の修復レポートを取得"""
        return self._last_report
    
    def get_health_status(self) -> Dict:
        """現在の健全性ステータスを取得"""
        total = len(self._escrow_manager._escrows)
        by_status = {}
        
        for escrow in self._escrow_manager._escrows.values():
            status = escrow.status
            by_status[status] = by_status.get(status, 0) + 1
        
        return {
            "total_escrows": total,
            "by_status": by_status,
            "auto_heal_enabled": self._auto_heal,
            "check_interval": self._check_interval,
            "last_report": self._last_report.timestamp if self._last_report else None
        }


# 使い方の例
async def main():
    """使用例"""
    # EscrowManagerの作成（実際の実装に合わせて）
    escrow_manager = EscrowManager()
    
    # 自動修復システムの作成
    healing = EscrowSelfHealing(
        escrow_manager=escrow_manager,
        check_interval=300,  # 5分ごと
        auto_heal=True
    )
    
    # 開始
    await healing.start()
    
    # 手動で健全性チェック
    report = await healing.perform_health_check()
    print(f"Issues found: {report.issues_found}")
    print(f"Issues fixed: {report.issues_fixed}")
    
    # 健全性ステータス
    status = healing.get_health_status()
    print(f"Total escrows: {status['total_escrows']}")
    
    # 停止
    await healing.stop()


if __name__ == "__main__":
    asyncio.run(main())
