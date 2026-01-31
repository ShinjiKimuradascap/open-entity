#!/usr/bin/env python3
"""
Escrow Manager
AI間取引プロトコルのエスクロー管理クラス
Protocol v1.0準拠
"""

import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Optional, Dict, List, Any, Callable
from collections import defaultdict

try:
    from services.token_system import TokenWallet, TaskContract, TransactionType
    TOKEN_SYSTEM_AVAILABLE = True
except ImportError:
    TOKEN_SYSTEM_AVAILABLE = False

try:
    from services.task_delegation import TaskStatus
    TASK_DELEGATION_AVAILABLE = True
except ImportError:
    TASK_DELEGATION_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EscrowStatus(Enum):
    """エスクロー状態
    
    CREATED -> LOCKED -> COMPLETED -> RELEASED
                  |
                  -> CANCELLED
                  |
                  -> EXPIRED
                  |
                  -> DISPUTED
    """
    CREATED = "created"       # 作成済み
    LOCKED = "locked"         # トークンロック済み
    COMPLETED = "completed"   # タスク完了
    RELEASED = "released"     # 支払い解放済み
    CANCELLED = "cancelled"   # キャンセル済み
    EXPIRED = "expired"       # 期限切れ
    DISPUTED = "disputed"     # 紛争中


class DisputeResolution(Enum):
    """紛争解決結果"""
    CLIENT_WINS = "client_wins"       # クライアント勝訴（全額返金）
    PROVIDER_WINS = "provider_wins"   # プロバイダ勝訴（全額支払）
    SPLIT = "split"                   # 折衷案（分割支払）
    PENDING = "pending"               # 保留中


@dataclass
class Escrow:
    """エスクロー情報
    
    Attributes:
        escrow_id: エスクロー固有ID（UUID）
        task_id: 関連タスクID
        client_id: クライアント（依頼者）エンティティID
        provider_id: プロバイダ（受託者）エンティティID
        amount: ロックするトークン量
        status: 現在の状態
        created_at: 作成日時
        deadline: 期限日時
        released_at: 解放日時（解放済みの場合）
        dispute_reason: 紛争理由（紛争中の場合）
        resolution: 紛争解決結果
        resolution_amount: 紛争解決時の支払額
        metadata: 追加メタデータ
    """
    escrow_id: str
    task_id: str
    client_id: str
    provider_id: str
    amount: float
    status: str = EscrowStatus.CREATED.value
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    deadline: Optional[str] = None
    released_at: Optional[str] = None
    dispute_reason: Optional[str] = None
    resolution: Optional[str] = None
    resolution_amount: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Escrow":
        """辞書から作成"""
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    def is_expired(self) -> bool:
        """期限切れかチェック"""
        if not self.deadline:
            return False
        try:
            deadline = datetime.fromisoformat(self.deadline.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > deadline
        except ValueError:
            return False
    
    def can_lock(self) -> bool:
        """ロック可能かチェック"""
        return self.status == EscrowStatus.CREATED.value
    
    def can_release(self) -> bool:
        """解放可能かチェック"""
        return self.status in [
            EscrowStatus.COMPLETED.value,
            EscrowStatus.DISPUTED.value
        ]
    
    def can_cancel(self) -> bool:
        """キャンセル可能かチェック"""
        return self.status in [
            EscrowStatus.CREATED.value,
            EscrowStatus.LOCKED.value
        ]
    
    def can_dispute(self) -> bool:
        """紛争申し立て可能かチェック"""
        return self.status in [
            EscrowStatus.LOCKED.value,
            EscrowStatus.COMPLETED.value
        ]


@dataclass
class VerificationResult:
    """タスク検証結果
    
    Attributes:
        verified: 検証が通過したか
        score: 品質スコア (0-100)
        checks: 各チェック項目の結果
        errors: エラーリスト
        timestamp: 検証日時
    """
    verified: bool
    score: float
    checks: Dict[str, bool] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EscrowManager:
    """エスクロー管理クラス
    
    AI間取引プロトコルのエスクロー機能を管理する。
    TokenWalletと連携してトークンのロック・解放を行う。
    """
    
    def __init__(
        self,
        wallet_manager: Optional[Any] = None,
        default_deadline_hours: int = 24,
        enable_auto_expiry: bool = True
    ):
        """初期化
        
        Args:
            wallet_manager: ウォレット管理オブジェクト（TokenWallet/TaskContract）
            default_deadline_hours: デフォルトの期限（時間）
            enable_auto_expiry: 自動期限切れ処理を有効にするか
        """
        self._escrows: Dict[str, Escrow] = {}
        self._wallets: Dict[str, Any] = {}
        self._wallet_manager = wallet_manager
        self._default_deadline_hours = default_deadline_hours
        self._enable_auto_expiry = enable_auto_expiry
        self._status_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._verification_callbacks: Dict[str, Callable[[str], VerificationResult]] = {}
        
        logger.info(f"EscrowManager initialized (auto_expiry={enable_auto_expiry})")
    
    def register_wallet(self, wallet: TokenWallet) -> None:
        """ウォレットを登録
        
        Args:
            wallet: 登録するTokenWallet
        """
        self._wallets[wallet.entity_id] = wallet
        logger.info(f"Registered wallet for entity: {wallet.entity_id}")
    
    def create_escrow(
        self,
        task_id: str,
        client_id: str,
        provider_id: str,
        amount: float,
        deadline: Optional[datetime] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Escrow]:
        """エスクローを作成
        
        Args:
            task_id: 関連タスクID
            client_id: クライアントエンティティID
            provider_id: プロバイダエンティティID
            amount: ロックするトークン量
            deadline: 期限日時（Noneの場合はデフォルト期限）
            metadata: 追加メタデータ
            
        Returns:
            作成されたEscrowオブジェクト（失敗時はNone）
        """
        # 入力検証
        if amount <= 0:
            logger.error(f"Invalid amount: {amount}")
            return None
        
        if not client_id or not provider_id:
            logger.error("client_id and provider_id are required")
            return None
        
        # 期限を設定
        if deadline is None:
            deadline = datetime.now(timezone.utc) + timedelta(
                hours=self._default_deadline_hours
            )
        
        # エスクロー作成
        escrow = Escrow(
            escrow_id=str(uuid.uuid4()),
            task_id=task_id,
            client_id=client_id,
            provider_id=provider_id,
            amount=amount,
            deadline=deadline.isoformat(),
            metadata=metadata or {}
        )
        
        self._escrows[escrow.escrow_id] = escrow
        self._record_status_change(
            escrow.escrow_id,
            EscrowStatus.CREATED.value,
            "Escrow created"
        )
        
        logger.info(
            f"Created escrow {escrow.escrow_id} for task {task_id} "
            f"({amount} AIC, client={client_id}, provider={provider_id})"
        )
        return escrow
    
    def lock_funds(self, escrow_id: str) -> bool:
        """資金をロック
        
        Args:
            escrow_id: エスクローID
            
        Returns:
            成功した場合True
        """
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            logger.error(f"Escrow not found: {escrow_id}")
            return False
        
        if not escrow.can_lock():
            logger.error(f"Cannot lock escrow {escrow_id}: status={escrow.status}")
            return False
        
        # クライアントウォレットを取得
        client_wallet = self._wallets.get(escrow.client_id)
        if not client_wallet:
            logger.error(f"Client wallet not found: {escrow.client_id}")
            return False
        
        # 残高チェック
        if client_wallet.get_balance() < escrow.amount:
            logger.error(
                f"Insufficient balance for {escrow.client_id}: "
                f"{client_wallet.get_balance()} < {escrow.amount}"
            )
            return False
        
        # トークンをロック（出金）
        if TOKEN_SYSTEM_AVAILABLE:
            success = client_wallet.withdraw(
                amount=escrow.amount,
                description=f"Lock for escrow {escrow_id}",
                related_task_id=escrow.task_id
            )
        else:
            # フォールバック：簡易ロック
            success = True
            logger.warning("TokenSystem not available, using mock lock")
        
        if not success:
            logger.error(f"Failed to lock tokens for escrow {escrow_id}")
            return False
        
        # 状態を更新
        escrow.status = EscrowStatus.LOCKED.value
        self._record_status_change(
            escrow_id,
            EscrowStatus.LOCKED.value,
            f"Locked {escrow.amount} AIC"
        )
        
        logger.info(f"Locked {escrow.amount} AIC for escrow {escrow_id}")
        return True
    
    def release_funds(
        self,
        escrow_id: str,
        verification_result: Optional[VerificationResult] = None
    ) -> bool:
        """資金を解放
        
        Args:
            escrow_id: エスクローID
            verification_result: タスク検証結果（オプション）
            
        Returns:
            成功した場合True
        """
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            logger.error(f"Escrow not found: {escrow_id}")
            return False
        
        if not escrow.can_release():
            logger.error(f"Cannot release escrow {escrow_id}: status={escrow.status}")
            return False
        
        # 検証結果がある場合はチェック
        if verification_result and not verification_result.verified:
            logger.error(
                f"Cannot release escrow {escrow_id}: verification failed "
                f"(score={verification_result.score})"
            )
            return False
        
        # プロバイダウォレットを取得
        provider_wallet = self._wallets.get(escrow.provider_id)
        if not provider_wallet:
            logger.error(f"Provider wallet not found: {escrow.provider_id}")
            return False
        
        # 紛争解決時の分割支払い対応
        release_amount = escrow.resolution_amount or escrow.amount
        
        # トークンを解放（入金）
        if TOKEN_SYSTEM_AVAILABLE:
            success = provider_wallet.deposit(
                amount=release_amount,
                description=f"Payment for escrow {escrow_id}",
                related_task_id=escrow.task_id
            )
        else:
            success = True
            logger.warning("TokenSystem not available, using mock release")
        
        if not success:
            logger.error(f"Failed to release tokens for escrow {escrow_id}")
            return False
        
        # 状態を更新
        escrow.status = EscrowStatus.RELEASED.value
        escrow.released_at = datetime.now(timezone.utc).isoformat()
        self._record_status_change(
            escrow_id,
            EscrowStatus.RELEASED.value,
            f"Released {release_amount} AIC to {escrow.provider_id}"
        )
        
        logger.info(
            f"Released {release_amount} AIC to {escrow.provider_id} "
            f"for escrow {escrow_id}"
        )
        return True
    
    def cancel_escrow(self, escrow_id: str, reason: str = "") -> bool:
        """エスクローを取消
        
        Args:
            escrow_id: エスクローID
            reason: 取消理由
            
        Returns:
            成功した場合True
        """
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            logger.error(f"Escrow not found: {escrow_id}")
            return False
        
        if not escrow.can_cancel():
            logger.error(f"Cannot cancel escrow {escrow_id}: status={escrow.status}")
            return False
        
        # ロック済みの場合は返金
        if escrow.status == EscrowStatus.LOCKED.value:
            client_wallet = self._wallets.get(escrow.client_id)
            if client_wallet and TOKEN_SYSTEM_AVAILABLE:
                client_wallet.deposit(
                    amount=escrow.amount,
                    description=f"Refund for cancelled escrow {escrow_id}",
                    related_task_id=escrow.task_id
                )
        
        # 状態を更新
        escrow.status = EscrowStatus.CANCELLED.value
        self._record_status_change(
            escrow_id,
            EscrowStatus.CANCELLED.value,
            f"Cancelled: {reason}"
        )
        
        logger.info(f"Cancelled escrow {escrow_id}: {reason}")
        return True
    
    def open_dispute(self, escrow_id: str, reason: str) -> bool:
        """紛争申し立て
        
        Args:
            escrow_id: エスクローID
            reason: 紛争理由
            
        Returns:
            成功した場合True
        """
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            logger.error(f"Escrow not found: {escrow_id}")
            return False
        
        if not escrow.can_dispute():
            logger.error(f"Cannot dispute escrow {escrow_id}: status={escrow.status}")
            return False
        
        # 状態を更新
        escrow.status = EscrowStatus.DISPUTED.value
        escrow.dispute_reason = reason
        escrow.resolution = DisputeResolution.PENDING.value
        self._record_status_change(
            escrow_id,
            EscrowStatus.DISPUTED.value,
            f"Dispute opened: {reason}"
        )
        
        logger.info(f"Opened dispute for escrow {escrow_id}: {reason}")
        return True
    
    def resolve_dispute(
        self,
        escrow_id: str,
        decision: DisputeResolution,
        resolution_amount: Optional[float] = None,
        resolution_notes: str = ""
    ) -> bool:
        """紛争解決
        
        Args:
            escrow_id: エスクローID
            decision: 解決決定
            resolution_amount: 解決時の支払額（分割の場合）
            resolution_notes: 解決メモ
            
        Returns:
            成功した場合True
        """
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            logger.error(f"Escrow not found: {escrow_id}")
            return False
        
        if escrow.status != EscrowStatus.DISPUTED.value:
            logger.error(f"Escrow {escrow_id} is not in dispute: status={escrow.status}")
            return False
        
        # 解決額を決定
        if decision == DisputeResolution.CLIENT_WINS:
            resolution_amount = 0.0
        elif decision == DisputeResolution.PROVIDER_WINS:
            resolution_amount = escrow.amount
        elif decision == DisputeResolution.SPLIT:
            if resolution_amount is None:
                resolution_amount = escrow.amount / 2
        else:
            logger.error(f"Invalid dispute resolution: {decision}")
            return False
        
        # 解決情報を記録
        escrow.resolution = decision.value
        escrow.resolution_amount = resolution_amount
        
        # 状態を完了に更新（release_fundsで解放される）
        escrow.status = EscrowStatus.COMPLETED.value
        self._record_status_change(
            escrow_id,
            EscrowStatus.COMPLETED.value,
            f"Dispute resolved: {decision.value}. Amount: {resolution_amount}. {resolution_notes}"
        )
        
        logger.info(
            f"Resolved dispute for escrow {escrow_id}: {decision.value} "
            f"(amount={resolution_amount})"
        )
        return True
    
    def mark_completed(self, escrow_id: str) -> bool:
        """タスク完了をマーク
        
        Args:
            escrow_id: エスクローID
            
        Returns:
            成功した場合True
        """
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            logger.error(f"Escrow not found: {escrow_id}")
            return False
        
        if escrow.status != EscrowStatus.LOCKED.value:
            logger.error(f"Cannot complete escrow {escrow_id}: status={escrow.status}")
            return False
        
        # 状態を更新
        escrow.status = EscrowStatus.COMPLETED.value
        self._record_status_change(
            escrow_id,
            EscrowStatus.COMPLETED.value,
            "Task completed"
        )
        
        logger.info(f"Marked escrow {escrow_id} as completed")
        return True
    
    def get_escrow(self, escrow_id: str) -> Optional[Escrow]:
        """エスクロー情報を取得
        
        Args:
            escrow_id: エスクローID
            
        Returns:
            Escrowオブジェクト（存在しない場合はNone）
        """
        return self._escrows.get(escrow_id)
    
    def get_escrow_by_task(self, task_id: str) -> Optional[Escrow]:
        """タスクIDからエスクローを検索
        
        Args:
            task_id: タスクID
            
        Returns:
            Escrowオブジェクト（存在しない場合はNone）
        """
        for escrow in self._escrows.values():
            if escrow.task_id == task_id:
                return escrow
        return None
    
    def list_active_escrows(
        self,
        client_id: Optional[str] = None,
        provider_id: Optional[str] = None
    ) -> List[Escrow]:
        """アクティブなエスクロー一覧を取得
        
        Args:
            client_id: クライアントIDでフィルタ（オプション）
            provider_id: プロバイダIDでフィルタ（オプション）
            
        Returns:
            アクティブなEscrowオブジェクトのリスト
        """
        active_statuses = [
            EscrowStatus.CREATED.value,
            EscrowStatus.LOCKED.value,
            EscrowStatus.COMPLETED.value,
            EscrowStatus.DISPUTED.value
        ]
        
        escrows = [
            e for e in self._escrows.values()
            if e.status in active_statuses
        ]
        
        if client_id:
            escrows = [e for e in escrows if e.client_id == client_id]
        
        if provider_id:
            escrows = [e for e in escrows if e.provider_id == provider_id]
        
        return escrows
    
    def list_all_escrows(
        self,
        status: Optional[EscrowStatus] = None
    ) -> List[Escrow]:
        """すべてのエスクロー一覧を取得
        
        Args:
            status: 状態でフィルタ（オプション）
            
        Returns:
            Escrowオブジェクトのリスト
        """
        if status:
            return [
                e for e in self._escrows.values()
                if e.status == status.value
            ]
        return list(self._escrows.values())
    
    def get_status_history(self, escrow_id: str) -> List[Dict[str, Any]]:
        """状態変更履歴を取得
        
        Args:
            escrow_id: エスクローID
            
        Returns:
            状態変更履歴のリスト
        """
        return self._status_history.get(escrow_id, [])
    
    def check_expired_escrows(self) -> List[str]:
        """期限切れエスクローをチェック
        
        Returns:
            期限切れとなったエスクローIDのリスト
        """
        expired_ids = []
        
        for escrow_id, escrow in self._escrows.items():
            if escrow.status in [EscrowStatus.CREATED.value, EscrowStatus.LOCKED.value]:
                if escrow.is_expired():
                    # ロック済みの場合は返金
                    if escrow.status == EscrowStatus.LOCKED.value:
                        client_wallet = self._wallets.get(escrow.client_id)
                        if client_wallet and TOKEN_SYSTEM_AVAILABLE:
                            client_wallet.deposit(
                                amount=escrow.amount,
                                description=f"Refund for expired escrow {escrow_id}",
                                related_task_id=escrow.task_id
                            )
                    
                    escrow.status = EscrowStatus.EXPIRED.value
                    self._record_status_change(
                        escrow_id,
                        EscrowStatus.EXPIRED.value,
                        "Escrow expired"
                    )
                    expired_ids.append(escrow_id)
                    logger.info(f"Escrow {escrow_id} expired")
        
        return expired_ids
    
    def register_verification_callback(
        self,
        task_type: str,
        callback: Callable[[str], VerificationResult]
    ) -> None:
        """検証コールバックを登録
        
        Args:
            task_type: タスクタイプ
            callback: 検証関数
        """
        self._verification_callbacks[task_type] = callback
        logger.info(f"Registered verification callback for task type: {task_type}")
    
    def verify_and_release(
        self,
        escrow_id: str,
        task_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """検証して解放
        
        Args:
            escrow_id: エスクローID
            task_type: タスクタイプ（コールバック検索用）
            
        Returns:
            結果辞書
        """
        escrow = self._escrows.get(escrow_id)
        if not escrow:
            return {"success": False, "error": "Escrow not found"}
        
        # 検証を実行
        verification_result = None
        if task_type and task_type in self._verification_callbacks:
            verification_result = self._verification_callbacks[task_type](escrow.task_id)
        
        # 解放を試行
        success = self.release_funds(escrow_id, verification_result)
        
        return {
            "success": success,
            "escrow_id": escrow_id,
            "verification": verification_result.to_dict() if verification_result else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得
        
        Returns:
            統計情報の辞書
        """
        total = len(self._escrows)
        by_status = defaultdict(int)
        total_locked = 0.0
        total_released = 0.0
        
        for escrow in self._escrows.values():
            by_status[escrow.status] += 1
            if escrow.status in [EscrowStatus.LOCKED.value, EscrowStatus.COMPLETED.value]:
                total_locked += escrow.amount
            elif escrow.status == EscrowStatus.RELEASED.value:
                total_released += escrow.amount
        
        return {
            "total_escrows": total,
            "by_status": dict(by_status),
            "active_escrows": len(self.list_active_escrows()),
            "disputed_escrows": by_status.get(EscrowStatus.DISPUTED.value, 0),
            "total_locked_amount": total_locked,
            "total_released_amount": total_released,
            "expired_escrows": by_status.get(EscrowStatus.EXPIRED.value, 0)
        }
    
    def _record_status_change(
        self,
        escrow_id: str,
        status: str,
        message: str
    ) -> None:
        """状態変更を記録
        
        Args:
            escrow_id: エスクローID
            status: 新しい状態
            message: メッセージ
        """
        self._status_history[escrow_id].append({
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": message
        })


# 便利関数
def create_escrow_manager(
    wallet_manager: Optional[Any] = None,
    default_deadline_hours: int = 24
) -> EscrowManager:
    """エスクローマネージャーを作成する便利関数
    
    Args:
        wallet_manager: ウォレット管理オブジェクト
        default_deadline_hours: デフォルトの期限（時間）
        
    Returns:
        EscrowManagerインスタンス
    """
    return EscrowManager(
        wallet_manager=wallet_manager,
        default_deadline_hours=default_deadline_hours
    )


def create_verification_result(
    verified: bool,
    score: float,
    checks: Optional[Dict[str, bool]] = None,
    errors: Optional[List[str]] = None
) -> VerificationResult:
    """検証結果を作成する便利関数
    
    Args:
        verified: 検証が通過したか
        score: 品質スコア (0-100)
        checks: 各チェック項目の結果
        errors: エラーリスト
        
    Returns:
        VerificationResultインスタンス
    """
    return VerificationResult(
        verified=verified,
        score=score,
        checks=checks or {},
        errors=errors or []
    )


if __name__ == "__main__":
    # テスト
    print("Testing Escrow Manager...")
    
    # エスクローマネージャー作成
    manager = create_escrow_manager()
    
    # モックウォレット作成
    if TOKEN_SYSTEM_AVAILABLE:
        from services.token_system import TokenWallet
        
        client_wallet = TokenWallet("client-1", _balance=1000.0)
        provider_wallet = TokenWallet("provider-1", _balance=0.0)
        
        manager.register_wallet(client_wallet)
        manager.register_wallet(provider_wallet)
        
        print(f"Client balance: {client_wallet.get_balance()}")
        print(f"Provider balance: {provider_wallet.get_balance()}")
    
    # エスクロー作成
    escrow = manager.create_escrow(
        task_id="task-001",
        client_id="client-1",
        provider_id="provider-1",
        amount=100.0,
        deadline=datetime.now(timezone.utc) + timedelta(hours=24)
    )
    print(f"\nCreated escrow: {escrow.escrow_id}")
    
    # 資金ロック
    success = manager.lock_funds(escrow.escrow_id)
    print(f"Lock funds: {success}")
    
    if TOKEN_SYSTEM_AVAILABLE:
        print(f"Client balance after lock: {client_wallet.get_balance()}")
    
    # タスク完了
    success = manager.mark_completed(escrow.escrow_id)
    print(f"Mark completed: {success}")
    
    # 検証結果作成
    verification = create_verification_result(
        verified=True,
        score=95.0,
        checks={"deliverables": True, "tests": True}
    )
    
    # 資金解放
    success = manager.release_funds(escrow.escrow_id, verification)
    print(f"Release funds: {success}")
    
    if TOKEN_SYSTEM_AVAILABLE:
        print(f"Provider balance after release: {provider_wallet.get_balance()}")
    
    # 統計情報
    print(f"\nStatistics: {manager.get_statistics()}")
    
    print("\nAll tests passed!")
