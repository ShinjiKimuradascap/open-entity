#!/usr/bin/env python3
"""
Token Economy System
AICトークン管理、タスクコントラクト、評価システム
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional, Dict, List, Any
from pathlib import Path
import logging
import json
import threading
from contextlib import contextmanager

# スレッド安全性用ロック
_lock = threading.RLock()

@contextmanager
def _atomic_operation():
    """アトミック操作コンテキストマネージャ"""
    with _lock:
        yield

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """タスクの状態"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class TransactionType(Enum):
    """トランザクションの種類"""
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    LOCK = "lock"
    RELEASE = "release"
    SLASH = "slash"
    REWARD = "reward"
    PENALTY = "penalty"
    MINT = "mint"  # 新規発行


class RewardType(Enum):
    """報酬の種類"""
    TASK_COMPLETION = "task_completion"      # タスク完了報酬
    QUALITY_REVIEW = "quality_review"        # 品質レビュー報酬
    INNOVATION_BONUS = "innovation_bonus"    # イノベーションボーナス
    GOVERNANCE_PARTICIPATION = "governance"  # ガバナンス参加報酬


@dataclass
class Transaction:
    """トランザクション（取引履歴）情報
    
    Attributes:
        type: トランザクションの種類
        amount: 金額
        timestamp: 取引日時
        description: 取引の説明
        counterparty: 相手方のエンティティID（送金の場合）
        related_task_id: 関連するタスクID
    """
    type: TransactionType
    amount: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""
    counterparty: Optional[str] = None
    related_task_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "type": self.type.value,
            "amount": self.amount,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "counterparty": self.counterparty,
            "related_task_id": self.related_task_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Transaction":
        """辞書からインスタンスを作成"""
        return cls(
            type=TransactionType(data["type"]),
            amount=data["amount"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data.get("description", ""),
            counterparty=data.get("counterparty"),
            related_task_id=data.get("related_task_id")
        )


@dataclass
class TokenWallet:
    """AICトークンの残高管理とトランザクション履歴
    
    Attributes:
        entity_id: エンティティID
        _balance: 現在の残高（プライベート）
        _transactions: トランザクション履歴（プライベート）
    """
    entity_id: str
    _balance: float = field(default=0.0, repr=False)
    _transactions: List[Transaction] = field(default_factory=list, repr=False)
    
    def __init__(self, entity_id: str, _balance: float = 0.0):
        """ウォレットを初期化
        
        Args:
            entity_id: エンティティID
            _balance: 初期残高（デフォルト0）
        """
        self.entity_id = entity_id
        self._balance = _balance
        self._transactions = []
    
    def deposit(self, amount: float, description: str = "", 
                related_task_id: Optional[str] = None) -> bool:
        """トークンを入金
        
        Args:
            amount: 入金額（正の数）
            description: 取引の説明
            related_task_id: 関連するタスクID
            
        Returns:
            成功した場合True
        """
        with _atomic_operation():
            if amount <= 0:
                logger.warning(f"Deposit amount must be positive: {amount}")
                return False
            
            self._balance += amount
            transaction = Transaction(
                type=TransactionType.DEPOSIT,
                amount=amount,
                description=description or f"Deposit to {self.entity_id}",
                related_task_id=related_task_id
            )
            self._transactions.append(transaction)
            
            logger.info(f"Deposited {amount} AIC to {self.entity_id}. Balance: {self._balance}")
            return True
    
    def withdraw(self, amount: float, description: str = "",
                 related_task_id: Optional[str] = None) -> bool:
        """トークンを出金
        
        Args:
            amount: 出金額（正の数）
            description: 取引の説明
            related_task_id: 関連するタスクID
            
        Returns:
            成功した場合True
        """
        with _atomic_operation():
            if amount <= 0:
                logger.warning(f"Withdraw amount must be positive: {amount}")
                return False
            if amount > self._balance:
                logger.warning(f"Insufficient balance: {self._balance} < {amount}")
                return False
            
            self._balance -= amount
            transaction = Transaction(
                type=TransactionType.WITHDRAW,
                amount=amount,
                description=description or f"Withdraw from {self.entity_id}",
                related_task_id=related_task_id
            )
            self._transactions.append(transaction)
            
            logger.info(f"Withdrew {amount} AIC from {self.entity_id}. Balance: {self._balance}")
            return True
    
    def get_balance(self) -> float:
        """現在の残高を取得
        
        Returns:
            現在の残高
        """
        return self._balance
    
    def transfer(self, to_wallet: "TokenWallet", amount: float, 
                 description: str = "") -> bool:
        """別のウォレットに送金
        
        Args:
            to_wallet: 送金先ウォレット
            amount: 送金額（正の数）
            description: 取引の説明
            
        Returns:
            成功した場合True
        """
        with _atomic_operation():
            if amount <= 0:
                logger.warning(f"Transfer amount must be positive: {amount}")
                return False
            if amount > self._balance:
                logger.warning(f"Insufficient balance for transfer: {self._balance} < {amount}")
                return False
            
            self._balance -= amount
            to_wallet._balance += amount
        
        # 送金元のトランザクション記録
        out_transaction = Transaction(
            type=TransactionType.TRANSFER_OUT,
            amount=amount,
            description=description or f"Transfer to {to_wallet.entity_id}",
            counterparty=to_wallet.entity_id
        )
        self._transactions.append(out_transaction)
        
        # 送金先のトランザクション記録
        in_transaction = Transaction(
            type=TransactionType.TRANSFER_IN,
            amount=amount,
            description=description or f"Transfer from {self.entity_id}",
            counterparty=self.entity_id
        )
        to_wallet._transactions.append(in_transaction)
        
        logger.info(
            f"Transferred {amount} AIC from {self.entity_id} to {to_wallet.entity_id}. "
            f"Sender balance: {self._balance}, Receiver balance: {to_wallet._balance}"
        )
        return True
    
    def _add_minted(self, amount: float, description: str) -> None:
        """ミントされたトークンを追加（内部使用のみ）
        
        Args:
            amount: 追加額（正の数）
            description: 取引の説明
        """
        self._balance += amount
        transaction = Transaction(
            type=TransactionType.REWARD,
            amount=amount,
            description=description or "Token minting"
        )
        self._transactions.append(transaction)
        logger.info(f"Added {amount} minted AIC to {self.entity_id}. Balance: {self._balance}")
    
    def _burn_tokens(self, amount: float, description: str) -> bool:
        """トークンをバーン（破棄）（内部使用のみ）
        
        Args:
            amount: バーン額（正の数）
            description: 取引の説明
            
        Returns:
            成功した場合True
        """
        if amount <= 0:
            logger.warning(f"Burn amount must be positive: {amount}")
            return False
        if amount > self._balance:
            logger.warning(f"Insufficient balance to burn: {self._balance} < {amount}")
            return False
        
        self._balance -= amount
        transaction = Transaction(
            type=TransactionType.PENALTY,
            amount=amount,
            description=description or "Token burn"
        )
        self._transactions.append(transaction)
        logger.info(f"Burned {amount} AIC from {self.entity_id}. Balance: {self._balance}")
        return True
    
    def get_transaction_history(self, 
                                start_date: Optional[datetime] = None,
                                end_date: Optional[datetime] = None,
                                transaction_type: Optional[TransactionType] = None) -> List[Transaction]:
        """トランザクション履歴を取得
        
        Args:
            start_date: 開始日時（含む）
            end_date: 終了日時（含む）
            transaction_type: フィルタするトランザクション種類
            
        Returns:
            条件にマッチするトランザクションのリスト
        """
        filtered = self._transactions
        
        if start_date:
            filtered = [t for t in filtered if t.timestamp >= start_date]
        if end_date:
            filtered = [t for t in filtered if t.timestamp <= end_date]
        if transaction_type:
            filtered = [t for t in filtered if t.type == transaction_type]
        
        return sorted(filtered, key=lambda t: t.timestamp, reverse=True)
    
    def get_transaction_summary(self, period: str = "daily") -> Dict[str, Dict[str, float]]:
        """トランザクションの集計情報を取得
        
        Args:
            period: 集計期間 ("daily", "weekly", "monthly")
            
        Returns:
            期間ごとの集計情報（収入、支出、合計）
        """
        summary: Dict[str, Dict[str, float]] = {}
        
        for transaction in self._transactions:
            # 期間のキーを生成
            if period == "daily":
                key = transaction.timestamp.strftime("%Y-%m-%d")
            elif period == "weekly":
                key = transaction.timestamp.strftime("%Y-W%U")
            elif period == "monthly":
                key = transaction.timestamp.strftime("%Y-%m")
            else:
                key = transaction.timestamp.strftime("%Y-%m-%d")
            
            if key not in summary:
                summary[key] = {"income": 0.0, "expense": 0.0, "net": 0.0}
            
            # 収入・支出を分類
            if transaction.type in [TransactionType.DEPOSIT, TransactionType.TRANSFER_IN, 
                                    TransactionType.REWARD, TransactionType.RELEASE]:
                summary[key]["income"] += transaction.amount
                summary[key]["net"] += transaction.amount
            elif transaction.type in [TransactionType.WITHDRAW, TransactionType.TRANSFER_OUT, 
                                      TransactionType.PENALTY, TransactionType.LOCK]:
                summary[key]["expense"] += transaction.amount
                summary[key]["net"] -= transaction.amount
        
        return dict(sorted(summary.items()))
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（永続化用）"""
        return {
            "entity_id": self.entity_id,
            "balance": self._balance,
            "transactions": [t.to_dict() for t in self._transactions]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenWallet":
        """辞書からインスタンスを作成（復元用）"""
        wallet = cls(
            entity_id=data["entity_id"],
            _balance=data["balance"]
        )
        wallet._transactions = [Transaction.from_dict(t) for t in data.get("transactions", [])]
        return wallet


@dataclass
class Task:
    """タスク情報
    
    Attributes:
        task_id: タスクID
        client_id: クライアント（依頼者）のエンティティID
        agent_id: エージェント（実行者）のエンティティID
        amount: タスクの金額
        status: タスクの状態
        created_at: 作成日時
        expires_at: 期限日時（Noneの場合は期限なし）
        completed_at: 完了日時
        description: タスクの説明
    """
    task_id: str
    client_id: str
    agent_id: str
    amount: float
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "task_id": self.task_id,
            "client_id": self.client_id,
            "agent_id": self.agent_id,
            "amount": self.amount,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "description": self.description
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        """辞書からインスタンスを作成"""
        return cls(
            task_id=data["task_id"],
            client_id=data["client_id"],
            agent_id=data["agent_id"],
            amount=data["amount"],
            status=TaskStatus(data["status"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            description=data.get("description", "")
        )


@dataclass
class TaskContract:
    """タスクコントラクト - トークンロック、リリース、スラッシュ管理
    
    Attributes:
        _wallets: ウォレット管理（プライベート）
        _tasks: タスク管理（プライベート）
        _locked_amounts: ロック中の金額（プライベート）
        _default_expiry_days: デフォルトの期限（日数）
    """
    
    # ウォレット管理（外部から注入されるべきだが、簡易実装として内部管理）
    _wallets: Dict[str, TokenWallet] = field(default_factory=dict, repr=False)
    _tasks: Dict[str, Task] = field(default_factory=dict, repr=False)
    _locked_amounts: Dict[str, float] = field(default_factory=dict, repr=False)
    _default_expiry_days: int = field(default=7, repr=False)
    
    def register_wallet(self, wallet: TokenWallet) -> None:
        """ウォレットを登録
        
        Args:
            wallet: 登録するウォレット
        """
        self._wallets[wallet.entity_id] = wallet
    
    def create_task(
        self, 
        task_id: str, 
        client_id: str, 
        agent_id: str, 
        amount: float,
        description: str = "",
        expires_at: Optional[datetime] = None
    ) -> bool:
        """タスクを作成し、トークンをロック
        
        Args:
            task_id: タスクID
            client_id: クライアントのエンティティID
            agent_id: エージェントのエンティティID
            amount: タスク金額
            description: タスクの説明
            expires_at: 期限日時（Noneの場合はデフォルト期限）
            
        Returns:
            成功した場合True
        """
        if task_id in self._tasks:
            logger.warning(f"Task {task_id} already exists")
            return False
        
        if amount <= 0:
            logger.warning(f"Task amount must be positive: {amount}")
            return False
        
        client_wallet = self._wallets.get(client_id)
        if not client_wallet:
            logger.warning(f"Client wallet not found: {client_id}")
            return False
        
        # トークンをロック（クライアントから差し引き）
        if not client_wallet.withdraw(amount, description=f"Lock for task {task_id}", 
                                       related_task_id=task_id):
            logger.warning(f"Failed to lock tokens for task {task_id}")
            return False
        
        # ロック額を記録
        self._locked_amounts[task_id] = amount
        
        # 期限を設定
        if expires_at is None:
            expires_at = datetime.now(timezone.utc) + timedelta(days=self._default_expiry_days)
        
        # タスクを作成
        task = Task(
            task_id=task_id,
            client_id=client_id,
            agent_id=agent_id,
            amount=amount,
            status=TaskStatus.IN_PROGRESS,
            expires_at=expires_at,
            description=description
        )
        self._tasks[task_id] = task
        
        logger.info(f"Created task {task_id} with {amount} AIC locked")
        return True
    
    def complete_task(self, task_id: str) -> bool:
        """タスクを完了し、ロックされたトークンをエージェントにリリース
        
        Args:
            task_id: タスクID
            
        Returns:
            成功した場合True
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return False
        
        if task.status != TaskStatus.IN_PROGRESS:
            logger.warning(f"Task {task_id} is not in progress: {task.status}")
            return False
        
        agent_wallet = self._wallets.get(task.agent_id)
        if not agent_wallet:
            logger.warning(f"Agent wallet not found: {task.agent_id}")
            return False
        
        amount = self._locked_amounts.get(task_id, 0)
        
        # エージェントに入金
        agent_wallet.deposit(amount, description=f"Payment for task {task_id}",
                             related_task_id=task_id)
        
        # タスク状態を更新
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.now(timezone.utc)
        
        # ロックを解除
        del self._locked_amounts[task_id]
        
        logger.info(f"Task {task_id} completed. Released {amount} AIC to {task.agent_id}")
        return True
    
    def fail_task(self, task_id: str, slash_percentage: float = 0.5) -> bool:
        """タスクを失敗とし、トークンの一部をスラッシュ（残りはクライアントに返却）
        
        Args:
            task_id: タスクID
            slash_percentage: スラッシュ率（0.0-1.0）
            
        Returns:
            成功した場合True
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return False
        
        if task.status != TaskStatus.IN_PROGRESS:
            logger.warning(f"Task {task_id} is not in progress: {task.status}")
            return False
        
        if not 0 <= slash_percentage <= 1:
            logger.warning(f"Slash percentage must be between 0 and 1: {slash_percentage}")
            return False
        
        client_wallet = self._wallets.get(task.client_id)
        if not client_wallet:
            logger.warning(f"Client wallet not found: {task.client_id}")
            return False
        
        amount = self._locked_amounts.get(task_id, 0)
        slash_amount = amount * slash_percentage
        return_amount = amount - slash_amount
        
        # クライアントに返却
        client_wallet.deposit(return_amount, description=f"Return for failed task {task_id}",
                              related_task_id=task_id)
        
        # タスク状態を更新
        task.status = TaskStatus.FAILED
        task.completed_at = datetime.now(timezone.utc)
        
        # ロックを解除
        del self._locked_amounts[task_id]
        
        logger.info(
            f"Task {task_id} failed. Slashed {slash_amount} AIC, "
            f"returned {return_amount} AIC to {task.client_id}"
        )
        return True
    
    def cancel_task(self, task_id: str, cancelled_by: str) -> bool:
        """タスクをキャンセルし、ロックされたトークンをクライアントに返却
        
        Args:
            task_id: タスクID
            cancelled_by: キャンセルしたエンティティID（クライアントのみ可能）
            
        Returns:
            成功した場合True
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return False
        
        if task.status != TaskStatus.IN_PROGRESS:
            logger.warning(f"Task {task_id} is not in progress: {task.status}")
            return False
        
        # クライアントのみキャンセル可能
        if cancelled_by != task.client_id:
            logger.warning(f"Only client can cancel task. Requested by: {cancelled_by}")
            return False
        
        client_wallet = self._wallets.get(task.client_id)
        if not client_wallet:
            logger.warning(f"Client wallet not found: {task.client_id}")
            return False
        
        amount = self._locked_amounts.get(task_id, 0)
        
        # クライアントに全額返却
        client_wallet.deposit(amount, description=f"Refund for cancelled task {task_id}",
                              related_task_id=task_id)
        
        # タスク状態を更新
        task.status = TaskStatus.CANCELLED
        task.completed_at = datetime.now(timezone.utc)
        
        # ロックを解除
        del self._locked_amounts[task_id]
        
        logger.info(f"Task {task_id} cancelled by {cancelled_by}. Refunded {amount} AIC")
        return True
    
    def expire_task(self, task_id: str) -> bool:
        """タスクを期限切れとして処理
        
        Args:
            task_id: タスクID
            
        Returns:
            成功した場合True
        """
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return False
        
        if task.status != TaskStatus.IN_PROGRESS:
            logger.warning(f"Task {task_id} is not in progress: {task.status}")
            return False
        
        if task.expires_at and datetime.now(timezone.utc) < task.expires_at:
            logger.warning(f"Task {task_id} has not expired yet")
            return False
        
        client_wallet = self._wallets.get(task.client_id)
        if not client_wallet:
            logger.warning(f"Client wallet not found: {task.client_id}")
            return False
        
        amount = self._locked_amounts.get(task_id, 0)
        
        # クライアントに全額返却（期限切れの場合は全額返却）
        client_wallet.deposit(amount, description=f"Refund for expired task {task_id}",
                              related_task_id=task_id)
        
        # タスク状態を更新
        task.status = TaskStatus.EXPIRED
        task.completed_at = datetime.now(timezone.utc)
        
        # ロックを解除
        del self._locked_amounts[task_id]
        
        logger.info(f"Task {task_id} expired. Refunded {amount} AIC to {task.client_id}")
        return True
    
    def check_expired_tasks(self) -> List[str]:
        """期限切れのタスクをチェックし、自動的に期限切れ処理
        
        Returns:
            期限切れとなったタスクIDのリスト
        """
        now = datetime.now(timezone.utc)
        expired_tasks = []
        
        for task_id, task in self._tasks.items():
            if (task.status == TaskStatus.IN_PROGRESS and 
                task.expires_at and 
                now > task.expires_at):
                if self.expire_task(task_id):
                    expired_tasks.append(task_id)
        
        return expired_tasks
    
    def get_locked_amount(self, task_id: str) -> float:
        """タスクにロックされているトークン量を取得
        
        Args:
            task_id: タスクID
            
        Returns:
            ロックされている金額
        """
        return self._locked_amounts.get(task_id, 0.0)
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """タスク情報を取得
        
        Args:
            task_id: タスクID
            
        Returns:
            タスク情報（存在しない場合はNone）
        """
        return self._tasks.get(task_id)
    
    def get_agent_tasks(self, agent_id: str, 
                        status: Optional[TaskStatus] = None) -> List[Task]:
        """エージェントのタスク一覧を取得
        
        Args:
            agent_id: エージェントID
            status: フィルタするステータス（Noneの場合は全て）
            
        Returns:
            タスクのリスト
        """
        tasks = [task for task in self._tasks.values() if task.agent_id == agent_id]
        
        if status:
            tasks = [task for task in tasks if task.status == status]
        
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)
    
    def get_client_tasks(self, client_id: str,
                         status: Optional[TaskStatus] = None) -> List[Task]:
        """クライアントのタスク一覧を取得
        
        Args:
            client_id: クライアントID
            status: フィルタするステータス（Noneの場合は全て）
            
        Returns:
            タスクのリスト
        """
        tasks = [task for task in self._tasks.values() if task.client_id == client_id]
        
        if status:
            tasks = [task for task in tasks if task.status == status]
        
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)
    
    def get_task_stats(self) -> Dict[str, Any]:
        """タスク統計情報を取得
        
        Returns:
            統計情報の辞書
        """
        stats = {
            "total": len(self._tasks),
            "by_status": {status.value: 0 for status in TaskStatus},
            "total_amount_locked": sum(self._locked_amounts.values()),
            "total_amount_completed": 0.0,
            "total_amount_failed": 0.0,
            "total_amount_cancelled": 0.0,
            "total_amount_expired": 0.0
        }
        
        for task in self._tasks.values():
            stats["by_status"][task.status.value] += 1
            
            if task.status == TaskStatus.COMPLETED:
                stats["total_amount_completed"] += task.amount
            elif task.status == TaskStatus.FAILED:
                stats["total_amount_failed"] += task.amount
            elif task.status == TaskStatus.CANCELLED:
                stats["total_amount_cancelled"] += task.amount
            elif task.status == TaskStatus.EXPIRED:
                stats["total_amount_expired"] += task.amount
        
        return stats
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（永続化用）"""
        return {
            "tasks": {k: v.to_dict() for k, v in self._tasks.items()},
            "locked_amounts": self._locked_amounts,
            "default_expiry_days": self._default_expiry_days
        }
    
    def _load_from_dict(self, data: Dict[str, Any]) -> None:
        """辞書から状態を復元（内部使用）"""
        self._tasks = {k: Task.from_dict(v) for k, v in data.get("tasks", {}).items()}
        self._locked_amounts = data.get("locked_amounts", {})
        self._default_expiry_days = data.get("default_expiry_days", 7)


@dataclass
class Rating:
    """評価情報
    
    Attributes:
        from_entity: 評価者のエンティティID
        to_entity: 被評価者のエンティティID
        task_id: 評価対象のタスクID
        score: 評価スコア（1-5）
        comment: コメント
        timestamp: 評価日時
    """
    from_entity: str
    to_entity: str
    task_id: str
    score: float  # 1-5
    comment: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "from_entity": self.from_entity,
            "to_entity": self.to_entity,
            "task_id": self.task_id,
            "score": self.score,
            "comment": self.comment,
            "timestamp": self.timestamp.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Rating":
        """辞書からインスタンスを作成"""
        return cls(
            from_entity=data["from_entity"],
            to_entity=data["to_entity"],
            task_id=data["task_id"],
            score=data["score"],
            comment=data.get("comment", ""),
            timestamp=datetime.fromisoformat(data["timestamp"])
        )


@dataclass
class MintRecord:
    """トークン発行記録
    
    Attributes:
        mint_id: 発行ID
        to_entity: 受領者のエンティティID
        amount: 発行額
        reward_type: 報酬の種類
        description: 説明
        timestamp: 発行日時
        task_id: 関連タスクID（該当する場合）
    """
    mint_id: str
    to_entity: str
    amount: float
    reward_type: RewardType
    description: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    task_id: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "mint_id": self.mint_id,
            "to_entity": self.to_entity,
            "amount": self.amount,
            "reward_type": self.reward_type.value,
            "description": self.description,
            "timestamp": self.timestamp.isoformat(),
            "task_id": self.task_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MintRecord":
        """辞書からインスタンスを作成"""
        return cls(
            mint_id=data["mint_id"],
            to_entity=data["to_entity"],
            amount=data["amount"],
            reward_type=RewardType(data["reward_type"]),
            description=data.get("description", ""),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            task_id=data.get("task_id")
        )


# TokenMinterは行1657で定義（重複削除済み）


@dataclass
class ReputationContract:
    """評価・信頼スコア管理
    
    Attributes:
        _ratings: 評価履歴（プライベート）
        _trust_scores: 信頼スコア（プライベート）
    """
    
    def __init__(self):
        self._ratings: Dict[str, List[Rating]] = {}
        self._trust_scores: Dict[str, float] = {}
    
    def mint_with_reputation(
        self,
        to_entity: str,
        amount: float,
        reward_type: Any,
        task_id: Optional[str] = None,
        description: Optional[str] = None
    ) -> Optional[Any]:
        """評価に基づいてトークンを発行"""
        if self._total_minted + amount > self._max_supply:
            logger.warning(
                f"Mint would exceed max supply. "
                f"Total: {self._total_minted}, Max: {self._max_supply}, "
                f"Requested: {amount}"
            )
            return None
        
        if amount <= 0:
            logger.warning(f"Mint amount must be positive: {amount}")
            return None
        
        # ウォレットを取得または作成
        wallet = self._wallets.get(to_entity)
        if not wallet:
            logger.warning(f"Wallet not found for {to_entity}")
            return None
        
        # トークンを発行（入金）
        wallet.deposit(
            amount=amount,
            description=description or f"Mint: {reward_type.value}",
            related_task_id=task_id
        )
        
        # 発行記録を作成
        mint_record = MintRecord(
            mint_id=self._generate_mint_id(),
            to_entity=to_entity,
            amount=amount,
            reward_type=reward_type,
            description=description,
            task_id=task_id
        )
        
        self._mint_history.append(mint_record)
        self._total_minted += amount
        
        logger.info(
            f"Minted {amount} AIC to {to_entity} "
            f"({reward_type.value}). Total minted: {self._total_minted}"
        )
        return mint_record
    
    def mint_task_reward(
        self, 
        to_entity: str, 
        complexity: int = 1,
        task_id: Optional[str] = None,
        description: str = ""
    ) -> Optional[MintRecord]:
        """タスク完了報酬を発行
        
        Args:
            to_entity: 受領者のエンティティID
            complexity: タスク複雑度（1-10）
            task_id: タスクID
            description: 説明
            
        Returns:
            発行記録（成功時）またはNone（失敗時）
        """
        # 複雑度に応じた報酬計算（1-10 → 10-100 AIC）
        complexity = max(1, min(10, complexity))  # 1-10に制限
        amount = self._task_reward_base + (complexity - 1) * 10
        amount = min(amount, self._task_reward_max)
        
        return self.mint(
            to_entity=to_entity,
            amount=amount,
            reward_type=RewardType.TASK_COMPLETION,
            description=description or f"Task completion reward (complexity: {complexity})",
            task_id=task_id
        )
    
    def mint_review_reward(
        self, 
        to_entity: str,
        description: str = ""
    ) -> Optional[MintRecord]:
        """品質レビュー報酬を発行
        
        Args:
            to_entity: 受領者のエンティティID
            description: 説明
            
        Returns:
            発行記録（成功時）またはNone（失敗時）
        """
        return self.mint(
            to_entity=to_entity,
            amount=self._review_reward,
            reward_type=RewardType.QUALITY_REVIEW,
            description=description or "Quality review reward"
        )
    
    def mint_innovation_bonus(
        self, 
        to_entity: str,
        feature_description: str = "",
        description: str = ""
    ) -> Optional[MintRecord]:
        """イノベーションボーナスを発行
        
        Args:
            to_entity: 受領者のエンティティID
            feature_description: 新機能の説明
            description: 説明
            
        Returns:
            発行記録（成功時）またはNone（失敗時）
        """
        desc = description or f"Innovation bonus for: {feature_description}"
        return self.mint(
            to_entity=to_entity,
            amount=self._innovation_bonus,
            reward_type=RewardType.INNOVATION_BONUS,
            description=desc
        )
    
    def get_mint_history(
        self, 
        entity_id: Optional[str] = None,
        reward_type: Optional[RewardType] = None
    ) -> List[MintRecord]:
        """発行履歴を取得
        
        Args:
            entity_id: フィルタするエンティティID
            reward_type: フィルタする報酬タイプ
            
        Returns:
            発行記録のリスト
        """
        filtered = self._mint_history
        
        if entity_id:
            filtered = [m for m in filtered if m.to_entity == entity_id]
        if reward_type:
            filtered = [m for m in filtered if m.reward_type == reward_type]
        
        return sorted(filtered, key=lambda m: m.timestamp, reverse=True)
    
    def get_total_minted(self) -> float:
        """総発行量を取得"""
        return self._total_minted
    
    def get_remaining_supply(self) -> float:
        """残りの発行可能量を取得"""
        return self._max_supply - self._total_minted
    
    def get_mint_stats(self) -> Dict[str, Any]:
        """発行統計を取得
        
        Returns:
            統計情報の辞書
        """
        stats = {
            "total_minted": self._total_minted,
            "max_supply": self._max_supply,
            "remaining_supply": self.get_remaining_supply(),
            "mint_count": len(self._mint_history),
            "by_reward_type": {rt.value: 0.0 for rt in RewardType},
            "by_reward_type_count": {rt.value: 0 for rt in RewardType}
        }
        
        for record in self._mint_history:
            rt = record.reward_type.value
            stats["by_reward_type"][rt] += record.amount
            stats["by_reward_type_count"][rt] += 1
        
        return stats
    
    def set_reward_amounts(
        self,
        task_base: Optional[float] = None,
        task_max: Optional[float] = None,
        review: Optional[float] = None,
        innovation: Optional[float] = None
    ) -> None:
        """報酬額を設定
        
        Args:
            task_base: タスク報酬基準額
            task_max: タスク報酬最大額
            review: 品質レビュー報酬
            innovation: イノベーションボーナス
        """
        if task_base is not None and task_base > 0:
            self._task_reward_base = task_base
        if task_max is not None and task_max > 0:
            self._task_reward_max = task_max
        if review is not None and review > 0:
            self._review_reward = review
        if innovation is not None and innovation > 0:
            self._innovation_bonus = innovation
        
        logger.info(
            f"Reward amounts updated - Task: {self._task_reward_base}-{self._task_reward_max}, "
            f"Review: {self._review_reward}, Innovation: {self._innovation_bonus}"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（永続化用）"""
        return {
            "mint_history": [m.to_dict() for m in self._mint_history],
            "total_minted": self._total_minted,
            "max_supply": self._max_supply,
            "mint_counter": self._mint_counter,
            "reward_amounts": {
                "task_base": self._task_reward_base,
                "task_max": self._task_reward_max,
                "review": self._review_reward,
                "innovation": self._innovation_bonus
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TokenMinter":
        """辞書からインスタンスを作成（復元用）"""
        minter = cls()
        minter._mint_history = [
            MintRecord.from_dict(m) for m in data.get("mint_history", [])
        ]
        minter._total_minted = data.get("total_minted", 0.0)
        minter._max_supply = data.get("max_supply", 10_000_000.0)
        minter._mint_counter = data.get("mint_counter", 0)
        
        rewards = data.get("reward_amounts", {})
        minter._task_reward_base = rewards.get("task_base", 10.0)
        minter._task_reward_max = rewards.get("task_max", 100.0)
        minter._review_reward = rewards.get("review", 10.0)
        minter._innovation_bonus = rewards.get("innovation", 1000.0)
        
        return minter


@dataclass
class ReputationContract:
    """評価・信頼スコア管理
    
    Attributes:
        _ratings: 評価履歴（プライベート）
        _trust_scores: 信頼スコア（プライベート）
        _rated_tasks: 評価済みタスク（重複防止用）（プライベート）
        _reward_rates: 評価スコアに応じた報酬率（プライベート）
        _penalty_rate: 低評価時のペナルティ率（プライベート）
        _token_reward_enabled: トークン報酬機能の有効化（プライベート）
        _reward_wallet: 報酬用ウォレット（プライベート）
    """
    
    _ratings: Dict[str, List[Rating]] = field(default_factory=dict, repr=False)
    _trust_scores: Dict[str, float] = field(default_factory=dict, repr=False)
    _rated_tasks: Dict[str, set] = field(default_factory=dict, repr=False)  # 重複評価防止
    _reward_rates: Dict[int, float] = field(default_factory=lambda: {5: 0.05, 4: 0.03, 3: 0.01}, 
                                             repr=False)  # 評価スコア -> 報酬率
    _penalty_rate: float = field(default=0.02, repr=False)  # 低評価（1-2）のペナルティ率
    _token_reward_enabled: bool = field(default=True, repr=False)
    _reward_wallet: Optional[TokenWallet] = field(default=None, repr=False)
    
    def enable_token_rewards(self, reward_wallet: TokenWallet) -> None:
        """トークン報酬機能を有効化
        
        Args:
            reward_wallet: 報酬用ウォレット（十分な残高が必要）
        """
        self._reward_wallet = reward_wallet
        self._token_reward_enabled = True
        logger.info(f"Token rewards enabled with wallet: {reward_wallet.entity_id}")
    
    def disable_token_rewards(self) -> None:
        """トークン報酬機能を無効化"""
        self._token_reward_enabled = False
        logger.info("Token rewards disabled")
    
    def set_reward_rate(self, score: int, rate: float) -> None:
        """評価スコアに応じた報酬率を設定
        
        Args:
            score: 評価スコア（1-5）
            rate: 報酬率（0.0-1.0）
        """
        if not 1 <= score <= 5:
            logger.warning(f"Score must be between 1 and 5: {score}")
            return
        if not 0 <= rate <= 1:
            logger.warning(f"Rate must be between 0 and 1: {rate}")
            return
        self._reward_rates[score] = rate
    
    def rate_agent(
        self, 
        from_entity: str, 
        to_entity: str, 
        task_id: str,
        task_contract: TaskContract,
        score: float, 
        comment: str = ""
    ) -> bool:
        """エージェントを評価
        
        Args:
            from_entity: 評価者のエンティティID
            to_entity: 被評価者のエンティティID
            task_id: 評価対象のタスクID
            task_contract: タスクコントラクト（報酬計算用）
            score: 評価スコア（1-5）
            comment: コメント
            
        Returns:
            成功した場合True
        """
        if not 1 <= score <= 5:
            logger.warning(f"Rating score must be between 1 and 5: {score}")
            return False
        
        if from_entity == to_entity:
            logger.warning("Cannot rate yourself")
            return False
        
        # 重複評価のチェック
        rating_key = f"{to_entity}:{task_id}"
        if rating_key in self._rated_tasks:
            if from_entity in self._rated_tasks[rating_key]:
                logger.warning(f"Already rated task {task_id} for agent {to_entity}")
                return False
        
        # タスクの存在と完了状態を確認
        task = task_contract.get_task(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found")
            return False
        
        if task.status != TaskStatus.COMPLETED:
            logger.warning(f"Cannot rate incomplete task: {task.status}")
            return False
        
        if task.agent_id != to_entity:
            logger.warning(f"Task {task_id} was not completed by {to_entity}")
            return False
        
        rating = Rating(
            from_entity=from_entity,
            to_entity=to_entity,
            task_id=task_id,
            score=score,
            comment=comment
        )
        
        if to_entity not in self._ratings:
            self._ratings[to_entity] = []
        
        self._ratings[to_entity].append(rating)
        
        # 評価済みタスクを記録
        if rating_key not in self._rated_tasks:
            self._rated_tasks[rating_key] = set()
        self._rated_tasks[rating_key].add(from_entity)
        
        # 信頼スコアを再計算
        self._update_trust_score(to_entity)
        
        # トークン報酬/ペナルティを配布
        self._distribute_reward_penalty(to_entity, score, task.amount, task_contract)
        
        logger.info(f"Rated {to_entity} with score {score} by {from_entity} for task {task_id}")
        return True
    
    def _distribute_reward_penalty(self, entity_id: str, score: float, 
                                   task_amount: float, task_contract: TaskContract) -> None:
        """評価に基づいて報酬またはペナルティを配布
        
        Args:
            entity_id: 対象エンティティID
            score: 評価スコア
            task_amount: タスク金額
            task_contract: タスクコントラクト（ウォレットアクセス用）
        """
        if not self._token_reward_enabled or not self._reward_wallet:
            return
        
        wallet = task_contract._wallets.get(entity_id)
        if not wallet:
            logger.warning(f"Wallet not found for {entity_id}")
            return
        
        score_int = int(score)
        
        if score_int >= 3:  # 高評価 -> 報酬
            reward_rate = self._reward_rates.get(score_int, 0.01)
            reward_amount = task_amount * reward_rate
            
            if self._reward_wallet.get_balance() >= reward_amount:
                self._reward_wallet.transfer(wallet, reward_amount, 
                                             description=f"Reward for rating {score}")
                logger.info(f"Rewarded {reward_amount} AIC to {entity_id} for rating {score}")
            else:
                logger.warning(f"Insufficient reward balance for {entity_id}")
        else:  # 低評価（1-2）-> ペナルティ
            penalty_amount = task_amount * self._penalty_rate
            
            if wallet.get_balance() >= penalty_amount:
                wallet.transfer(self._reward_wallet, penalty_amount,
                               description=f"Penalty for rating {score}")
                logger.info(f"Penalized {penalty_amount} AIC from {entity_id} for rating {score}")
            else:
                logger.warning(f"Insufficient balance for penalty from {entity_id}")
    
    def _update_trust_score(self, entity_id: str) -> None:
        """信頼スコアを計算（加重平均）"""
        ratings = self._ratings.get(entity_id, [])
        if not ratings:
            self._trust_scores[entity_id] = 0.0
            return
        
        # 時間減衰を含む加重平均
        now = datetime.now(timezone.utc)
        total_weight = 0.0
        weighted_sum = 0.0
        
        for rating in ratings:
            # 古い評価ほど重みを減らす（30日で半減）
            days_old = (now - rating.timestamp).days
            weight = 0.5 ** (days_old / 30)
            
            weighted_sum += rating.score * weight
            total_weight += weight
        
        # スコアを 0-100 に正規化
        avg_score = weighted_sum / total_weight if total_weight > 0 else 0
        trust_score = (avg_score / 5) * 100
        
        self._trust_scores[entity_id] = trust_score
        logger.info(f"Updated trust score for {entity_id}: {trust_score:.2f}")
    
    def get_rating(self, entity_id: str) -> Optional[float]:
        """エージェントの平均評価スコアを取得"""
        ratings = self._ratings.get(entity_id, [])
        if not ratings:
            return None
        return sum(r.score for r in ratings) / len(ratings)
    
    def get_trust_score(self, entity_id: str) -> float:
        """エージェントの信頼スコアを取得（0-100）"""
        if entity_id not in self._trust_scores:
            self._update_trust_score(entity_id)
        return self._trust_scores.get(entity_id, 0.0)
    
    def get_rating_count(self, entity_id: str) -> int:
        """エージェントが受けた評価数を取得"""
        return len(self._ratings.get(entity_id, []))
    
    def get_all_ratings(self, entity_id: str) -> List[Rating]:
        """エージェントの全評価履歴を取得
        
        Args:
            entity_id: エンティティID
            
        Returns:
            評価のリスト
        """
        return list(self._ratings.get(entity_id, []))
    
    def get_top_agents(self, min_ratings: int = 3, limit: int = 10) -> List[Dict[str, Any]]:
        """信頼スコア上位のエージェントを取得
        
        Args:
            min_ratings: 最小評価数（これ以下のエージェントは除外）
            limit: 返す最大件数
            
        Returns:
            エージェント情報のリスト（entity_id, trust_score, avg_rating, rating_count）
        """
        agent_scores = []
        
        for entity_id in self._ratings:
            rating_count = self.get_rating_count(entity_id)
            if rating_count >= min_ratings:
                agent_scores.append({
                    "entity_id": entity_id,
                    "trust_score": self.get_trust_score(entity_id),
                    "avg_rating": self.get_rating(entity_id),
                    "rating_count": rating_count
                })
        
        # 信頼スコアでソート
        sorted_agents = sorted(agent_scores, key=lambda x: x["trust_score"], reverse=True)
        return sorted_agents[:limit]
    
    def has_rated(self, from_entity: str, to_entity: str, task_id: str) -> bool:
        """評価済みかどうかを確認
        
        Args:
            from_entity: 評価者ID
            to_entity: 被評価者ID
            task_id: タスクID
            
        Returns:
            評価済みの場合True
        """
        rating_key = f"{to_entity}:{task_id}"
        if rating_key not in self._rated_tasks:
            return False
        return from_entity in self._rated_tasks[rating_key]
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換（永続化用）"""
        return {
            "ratings": {
                k: [r.to_dict() for r in v] 
                for k, v in self._ratings.items()
            },
            "trust_scores": self._trust_scores,
            "rated_tasks": {k: list(v) for k, v in self._rated_tasks.items()},
            "reward_rates": self._reward_rates,
            "penalty_rate": self._penalty_rate,
            "token_reward_enabled": self._token_reward_enabled
        }
    
    def _load_from_dict(self, data: Dict[str, Any]) -> None:
        """辞書から状態を復元（内部使用）"""
        self._ratings = {
            k: [Rating.from_dict(r) for r in v]
            for k, v in data.get("ratings", {}).items()
        }
        self._trust_scores = data.get("trust_scores", {})
        self._rated_tasks = {
            k: set(v) for k, v in data.get("rated_tasks", {}).items()
        }
        self._reward_rates = data.get("reward_rates", {5: 0.05, 4: 0.03, 3: 0.01})
        self._penalty_rate = data.get("penalty_rate", 0.02)
        self._token_reward_enabled = data.get("token_reward_enabled", True)


# グローバルインスタンス（簡易実装）
_wallet_registry: Dict[str, TokenWallet] = {}
_task_contract: Optional["TaskContract"] = None
_reputation_contract: Optional["ReputationContract"] = None
_token_minter: Optional["TokenMinter"] = None

# 永続化ファイルパス
_DEFAULT_DATA_DIR = Path("./data")
_WALLET_FILE = _DEFAULT_DATA_DIR / "wallets.json"
_TASK_FILE = _DEFAULT_DATA_DIR / "tasks.json"
_REPUTATION_FILE = _DEFAULT_DATA_DIR / "reputation.json"


def create_wallet(entity_id: str, initial_balance: float = 0.0) -> TokenWallet:
    """ウォレットを作成・登録"""
    if entity_id in _wallet_registry:
        logger.warning(f"Wallet already exists for {entity_id}")
        return _wallet_registry[entity_id]
    
    wallet = TokenWallet(entity_id=entity_id, _balance=initial_balance)
    _wallet_registry[entity_id] = wallet
    
    # TaskContractにも登録
    tc = get_task_contract()
    tc.register_wallet(wallet)
    
    logger.info(f"Created wallet for {entity_id} with balance {initial_balance}")
    return wallet


def get_wallet(entity_id: str) -> Optional[TokenWallet]:
    """ウォレットを取得"""
    return _wallet_registry.get(entity_id)


def delete_wallet(entity_id: str) -> bool:
    """ウォレットを削除"""
    if entity_id in _wallet_registry:
        del _wallet_registry[entity_id]
        logger.info(f"Deleted wallet for {entity_id}")
        return True
    return False


def get_task_contract() -> "TaskContract":
    """TaskContractのグローバルインスタンスを取得"""
    global _task_contract
    if _task_contract is None:
        _task_contract = TaskContract()
    return _task_contract


def get_reputation_contract() -> "ReputationContract":
    """ReputationContractのグローバルインスタンスを取得
    
    Returns:
        ReputationContractインスタンス
    """
    global _reputation_contract
    if _reputation_contract is None:
        _reputation_contract = ReputationContract()
    return _reputation_contract


def get_token_minter() -> "TokenMinter":
    """TokenMinterのグローバルインスタンスを取得
    
    Returns:
        TokenMinterインスタンス
    """
    global _token_minter
    if _token_minter is None:
        _token_minter = TokenMinter()
    return _token_minter


def save_all(data_dir: Optional[Path] = None) -> bool:
    """全データをファイルに保存
    
    Args:
        data_dir: データ保存ディレクトリ（Noneの場合はデフォルト）
        
    Returns:
        成功した場合True
    """
    try:
        data_dir = data_dir or _DEFAULT_DATA_DIR
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # ウォレットを保存
        wallets_data = {
            entity_id: wallet.to_dict() 
            for entity_id, wallet in _wallet_registry.items()
        }
        with open(data_dir / "wallets.json", "w", encoding="utf-8") as f:
            json.dump(wallets_data, f, ensure_ascii=False, indent=2)
        
        # タスクを保存
        tc = get_task_contract()
        with open(data_dir / "tasks.json", "w", encoding="utf-8") as f:
            json.dump(tc.to_dict(), f, ensure_ascii=False, indent=2)
        
        # 評価を保存
        rc = get_reputation_contract()
        with open(data_dir / "reputation.json", "w", encoding="utf-8") as f:
            json.dump(rc.to_dict(), f, ensure_ascii=False, indent=2)
        
        logger.info(f"All data saved to {data_dir}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save data: {e}")
        return False


def load_all(data_dir: Optional[Path] = None) -> bool:
    """全データをファイルから読み込み
    
    Args:
        data_dir: データ保存ディレクトリ（Noneの場合はデフォルト）
        
    Returns:
        成功した場合True
    """
    global _wallet_registry
    
    try:
        data_dir = data_dir or _DEFAULT_DATA_DIR
        
        if not data_dir.exists():
            logger.warning(f"Data directory not found: {data_dir}")
            return False
        
        # ウォレットを読み込み
        wallet_file = data_dir / "wallets.json"
        if wallet_file.exists():
            with open(wallet_file, "r", encoding="utf-8") as f:
                wallets_data = json.load(f)
            _wallet_registry = {
                entity_id: TokenWallet.from_dict(data)
                for entity_id, data in wallets_data.items()
            }
            
            # TaskContractにも登録
            tc = get_task_contract()
            for wallet in _wallet_registry.values():
                tc.register_wallet(wallet)
            
            logger.info(f"Loaded {len(_wallet_registry)} wallets")
        
        # タスクを読み込み
        task_file = data_dir / "tasks.json"
        if task_file.exists():
            with open(task_file, "r", encoding="utf-8") as f:
                tasks_data = json.load(f)
            tc = get_task_contract()
            tc._load_from_dict(tasks_data)
            logger.info(f"Loaded {len(tc._tasks)} tasks")
        
        # 評価を読み込み
        reputation_file = data_dir / "reputation.json"
        if reputation_file.exists():
            with open(reputation_file, "r", encoding="utf-8") as f:
                reputation_data = json.load(f)
            rc = get_reputation_contract()
            rc._load_from_dict(reputation_data)
            logger.info(f"Loaded {len(rc._ratings)} agent ratings")
        
        logger.info(f"All data loaded from {data_dir}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to load data: {e}")
        return False


class TokenMinter:
    """AICトークン発行管理
    
    タスク完了報酬、品質レビュー報酬、イノベーションボーナスなど、
    システムによるトークン発行を管理する。
    
    Attributes:
        treasury: 国庫ウォレット（発行元）
        total_minted: 総発行量
    """
    
    # 報酬額の定数
    TASK_REWARD_MIN = 1
    TASK_REWARD_MAX = 100
    REVIEW_REWARD = 10
    INNOVATION_BONUS = 1000
    
    def __init__(self, treasury_wallet: TokenWallet):
        self.treasury = treasury_wallet
        self.total_minted = 0.0
        self._mint_history: List[Dict[str, Any]] = []
    
    def mint_for_task_completion(
        self, 
        agent_id: str, 
        complexity: int,
        task_id: str = "",
        description: str = ""
    ) -> bool:
        """タスク完了報酬を発行
        
        Args:
            agent_id: 報酬受取エージェントID
            complexity: タスク複雑度（1-100、範囲外はクリップ）
            task_id: 関連タスクID
            description: タスク説明
            
        Returns:
            成功した場合True
        """
        # 複雑度を1-100の範囲にクリップ
        amount = max(self.TASK_REWARD_MIN, min(complexity, self.TASK_REWARD_MAX))
        
        desc = f"Task completion reward"
        if description:
            desc += f": {description}"
        if task_id:
            desc += f" [task:{task_id}]"
        
        return self._mint(agent_id, amount, "task_completion", desc, task_id)
    
    def mint_for_review(
        self, 
        reviewer_id: str,
        review_target_id: str = "",
        description: str = ""
    ) -> bool:
        """品質レビュー報酬を発行
        
        Args:
            reviewer_id: レビュアーID
            review_target_id: レビュー対象ID
            description: レビュー説明
            
        Returns:
            成功した場合True
        """
        desc = f"Quality review reward"
        if description:
            desc += f": {description}"
        if review_target_id:
            desc += f" [target:{review_target_id}]"
        
        return self._mint(
            reviewer_id, 
            self.REVIEW_REWARD, 
            "quality_review", 
            desc
        )
    
    def mint_innovation_bonus(
        self, 
        agent_id: str, 
        description: str,
        custom_amount: Optional[float] = None
    ) -> bool:
        """イノベーションボーナスを発行
        
        Args:
            agent_id: ボーナス受取エージェントID
            description: イノベーション内容の説明
            custom_amount: カスタム金額（Noneの場合はデフォルト1000）
            
        Returns:
            成功した場合True
        """
        amount = custom_amount if custom_amount is not None else self.INNOVATION_BONUS
        desc = f"Innovation bonus: {description}"
        
        return self._mint(agent_id, amount, "innovation_bonus", desc)
    
    def _mint(
        self, 
        to_entity_id: str, 
        amount: float, 
        mint_type: str,
        description: str = "",
        related_task_id: Optional[str] = None
    ) -> bool:
        """トークン発行の内部メソッド
        
        Args:
            to_entity_id: 発行先エンティティID
            amount: 発行額
            mint_type: 発行タイプ
            description: 説明
            related_task_id: 関連タスクID
            
        Returns:
            成功した場合True
        """
        with _atomic_operation():
            if amount <= 0:
                logger.warning(f"Mint amount must be positive: {amount}")
                return False
            
            # 対象ウォレットを取得または作成
            wallet = get_wallet(to_entity_id)
            if wallet is None:
                logger.info(f"Creating new wallet for {to_entity_id}")
                wallet = create_wallet(to_entity_id, 0.0)
            
            # トークンを発行（国庫から入金として処理）
            success = wallet.deposit(
                amount=amount,
                description=description or f"Mint {amount} AIC",
                related_task_id=related_task_id
            )
            
            if success:
                self.total_minted += amount
            self._mint_history.append({
                "to_entity": to_entity_id,
                "amount": amount,
                "type": mint_type,
                "description": description,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "related_task_id": related_task_id
            })
            logger.info(f"Minted {amount} AIC to {to_entity_id} ({mint_type})")
        
        return success
    
    def get_total_minted(self) -> float:
        """総発行量を取得"""
        return self.total_minted
    
    def get_mint_history(
        self,
        entity_id: Optional[str] = None,
        mint_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """発行履歴を取得
        
        Args:
            entity_id: フィルタするエンティティID
            mint_type: フィルタする発行タイプ
            
        Returns:
            発行履歴のリスト
        """
        filtered = self._mint_history
        
        if entity_id:
            filtered = [h for h in filtered if h["to_entity"] == entity_id]
        if mint_type:
            filtered = [h for h in filtered if h["type"] == mint_type]
        
        return sorted(filtered, key=lambda h: h["timestamp"], reverse=True)


# グローバルインスタンス
_minter: Optional[TokenMinter] = None


class PersistenceManager:
    """トークンシステムの永続化管理
    
    JSONファイルによる保存・復元を行う。
    原子性を保つため、一時ファイルに書き込んでからrenameする。
    
    Attributes:
        data_dir: データ保存ディレクトリ
    """
    
    def __init__(self, data_dir: str = "data/token_system"):
        self.data_dir = Path(data_dir)
        self.wallets_dir = self.data_dir / "wallets"
        self.tasks_dir = self.data_dir / "tasks"
        self.ratings_dir = self.data_dir / "ratings"
        self._ensure_directories()
    
    def _ensure_directories(self) -> None:
        """必要なディレクトリを作成"""
        self.wallets_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_dir.mkdir(parents=True, exist_ok=True)
        self.ratings_dir.mkdir(parents=True, exist_ok=True)
    
    def save_wallet(self, wallet: TokenWallet) -> bool:
        """ウォレットを保存
        
        Args:
            wallet: 保存するウォレット
            
        Returns:
            成功した場合True
        """
        try:
            filepath = self.wallets_dir / f"{wallet.entity_id}.json"
            temp_path = filepath.with_suffix('.tmp')
            
            data = wallet.to_dict()
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            # 原子性のためtmpファイルをrename
            temp_path.replace(filepath)
            return True
        except Exception as e:
            logger.error(f"Failed to save wallet {wallet.entity_id}: {e}")
            return False
    
    def load_wallet(self, entity_id: str) -> Optional[TokenWallet]:
        """ウォレットを読み込み
        
        Args:
            entity_id: エンティティID
            
        Returns:
            ウォレット（存在しない場合None）
        """
        try:
            filepath = self.wallets_dir / f"{entity_id}.json"
            if not filepath.exists():
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return TokenWallet.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load wallet {entity_id}: {e}")
            return None
    
    def load_all_wallets(self) -> Dict[str, TokenWallet]:
        """すべてのウォレットを読み込み
        
        Returns:
            エンティティIDをキーとするウォレット辞書
        """
        wallets = {}
        try:
            for filepath in self.wallets_dir.glob("*.json"):
                entity_id = filepath.stem
                wallet = self.load_wallet(entity_id)
                if wallet:
                    wallets[entity_id] = wallet
            return wallets
        except Exception as e:
            logger.error(f"Failed to load wallets: {e}")
            return {}
    
    def save_task(self, task: Task) -> bool:
        """タスクを保存
        
        Args:
            task: 保存するタスク
            
        Returns:
            成功した場合True
        """
        try:
            filepath = self.tasks_dir / f"{task.task_id}.json"
            temp_path = filepath.with_suffix('.tmp')
            
            data = task.to_dict()
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_path.replace(filepath)
            return True
        except Exception as e:
            logger.error(f"Failed to save task {task.task_id}: {e}")
            return False
    
    def load_task(self, task_id: str) -> Optional[Task]:
        """タスクを読み込み
        
        Args:
            task_id: タスクID
            
        Returns:
            タスク（存在しない場合None）
        """
        try:
            filepath = self.tasks_dir / f"{task_id}.json"
            if not filepath.exists():
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return Task.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load task {task_id}: {e}")
            return None
    
    def save_reputation_contract(self, contract: ReputationContract) -> bool:
        """評価コントラクトを保存
        
        Args:
            contract: 保存する評価コントラクト
            
        Returns:
            成功した場合True
        """
        try:
            filepath = self.data_dir / "reputation_contract.json"
            temp_path = filepath.with_suffix('.tmp')
            
            # Ratingを辞書に変換
            ratings_data = {}
            for entity_id, ratings in contract._ratings.items():
                ratings_data[entity_id] = [
                    {
                        "from_entity": r.from_entity,
                        "to_entity": r.to_entity,
                        "score": r.score,
                        "comment": r.comment,
                        "timestamp": r.timestamp.isoformat()
                    }
                    for r in ratings
                ]
            
            data = {
                "ratings": ratings_data,
                "trust_scores": contract._trust_scores
            }
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_path.replace(filepath)
            return True
        except Exception as e:
            logger.error(f"Failed to save reputation contract: {e}")
            return False
    
    def load_reputation_contract(self, contract: ReputationContract) -> bool:
        """評価コントラクトを読み込み
        
        Args:
            contract: 読み込み先の評価コントラクト
            
        Returns:
            成功した場合True
        """
        try:
            filepath = self.data_dir / "reputation_contract.json"
            if not filepath.exists():
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Ratingを復元
            for entity_id, ratings_data in data.get("ratings", {}).items():
                contract._ratings[entity_id] = [
                    Rating(
                        from_entity=r["from_entity"],
                        to_entity=r["to_entity"],
                        score=r["score"],
                        comment=r["comment"],
                        timestamp=datetime.fromisoformat(r["timestamp"])
                    )
                    for r in ratings_data
                ]
            
            contract._trust_scores = data.get("trust_scores", {})
            return True
        except Exception as e:
            logger.error(f"Failed to load reputation contract: {e}")
            return False
    
    def save_token_minter(self, minter: TokenMinter) -> bool:
        """TokenMinterを保存
        
        Args:
            minter: 保存するTokenMinter
            
        Returns:
            成功した場合True
        """
        try:
            filepath = self.data_dir / "token_minter.json"
            temp_path = filepath.with_suffix('.tmp')
            
            data = minter.to_dict()
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            temp_path.replace(filepath)
            return True
        except Exception as e:
            logger.error(f"Failed to save token minter: {e}")
            return False
    
    def load_token_minter(self) -> Optional[TokenMinter]:
        """TokenMinterを読み込み
        
        Returns:
            TokenMinter（存在しない場合None）
        """
        try:
            filepath = self.data_dir / "token_minter.json"
            if not filepath.exists():
                return None
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return TokenMinter.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load token minter: {e}")
            return None
    
    def save_all(self) -> Dict[str, int]:
        """すべてのデータを保存
        
        Returns:
            保存した件数の辞書
        """
        results = {"wallets": 0, "tasks": 0, "ratings": 0}
        
        # すべてのウォレットを保存
        global _wallet_registry
        for wallet in _wallet_registry.values():
            if self.save_wallet(wallet):
                results["wallets"] += 1
        
        # タスクコントラクトのタスクを保存
        tc = get_task_contract()
        for task in tc._tasks.values():
            if self.save_task(task):
                results["tasks"] += 1
        
        # 評価コントラクトを保存
        rc = get_reputation_contract()
        if self.save_reputation_contract(rc):
            results["ratings"] = len(rc._ratings)
        
        # TokenMinterを保存
        minter = get_token_minter()
        if self.save_token_minter(minter):
            results["mint_records"] = len(minter._mint_history)
        
        logger.info(f"Saved all data: {results}")
        return results
    
    def load_all(self) -> Dict[str, int]:
        """すべてのデータを読み込み
        
        Returns:
            読み込んだ件数の辞書
        """
        results = {"wallets": 0, "tasks": 0, "ratings": 0, "mint_records": 0}
        
        # すべてのウォレットを読み込み
        global _wallet_registry
        wallets = self.load_all_wallets()
        for entity_id, wallet in wallets.items():
            _wallet_registry[entity_id] = wallet
            # TaskContractにも登録
            tc = get_task_contract()
            tc.register_wallet(wallet)
            # TokenMinterにも登録
            minter = get_token_minter()
            minter.register_wallet(wallet)
            results["wallets"] += 1
        
        # 評価コントラクトを読み込み
        rc = get_reputation_contract()
        if self.load_reputation_contract(rc):
            results["ratings"] = len(rc._ratings)
        
        # TokenMinterを読み込み
        loaded_minter = self.load_token_minter()
        if loaded_minter:
            global _token_minter
            _token_minter = loaded_minter
            # ウォレットを再登録
            for wallet in _wallet_registry.values():
                _token_minter.register_wallet(wallet)
            results["mint_records"] = len(_token_minter._mint_history)
        
        logger.info(f"Loaded all data: {results}")
        return results
    
    def create_backup(self, tag: Optional[str] = None) -> Optional[Path]:
        """バックアップを作成
        
        Args:
            tag: バックアップのタグ（オプション）
            
        Returns:
            バックアップパス（失敗時はNone）
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        tag_suffix = f"_{tag}" if tag else ""
        backup_name = f"backup_{timestamp}{tag_suffix}"
        backup_path = self.data_dir / "backups" / backup_name
        
        try:
            backup_path.mkdir(parents=True, exist_ok=True)
            
            # wallets, tasks, ratings ディレクトリをコピー
            import shutil
            for dirname in ["wallets", "tasks", "ratings"]:
                src_dir = self.data_dir / dirname
                if src_dir.exists():
                    dst_dir = backup_path / dirname
                    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)
            
            # token_minter.json, reputation_contract.json もコピー
            for filename in ["token_minter.json", "reputation_contract.json"]:
                src = self.data_dir / filename
                if src.exists():
                    shutil.copy2(src, backup_path / filename)
            
            logger.info(f"Created backup at {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None
    
    def list_backups(self) -> List[Path]:
        """利用可能なバックアップ一覧を取得
        
        Returns:
            バックアップパスのリスト（新しい順）
        """
        backups_dir = self.data_dir / "backups"
        if not backups_dir.exists():
            return []
        return sorted(backups_dir.glob("backup_*"), reverse=True)
    
    def restore_backup(self, backup_path: Path) -> bool:
        """バックアップからデータを復元
        
        Args:
            backup_path: バックアップパス
            
        Returns:
            成功した場合True
        """
        try:
            import shutil
            
            # wallets, tasks, ratings ディレクトリを復元
            for dirname in ["wallets", "tasks", "ratings"]:
                src_dir = backup_path / dirname
                if src_dir.exists():
                    dst_dir = self.data_dir / dirname
                    if dst_dir.exists():
                        shutil.rmtree(dst_dir)
                    shutil.copytree(src_dir, dst_dir)
            
            # token_minter.json, reputation_contract.json も復元
            for filename in ["token_minter.json", "reputation_contract.json"]:
                src = backup_path / filename
                if src.exists():
                    shutil.copy2(src, self.data_dir / filename)
            
            logger.info(f"Restored backup from {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore backup: {e}")
            return False


# グローバルインスタンス
_persistence: Optional[PersistenceManager] = None


def get_persistence(data_dir: str = "data/token_system") -> PersistenceManager:
    """PersistenceManagerのグローバルインスタンスを取得
    
    Args:
        data_dir: データ保存ディレクトリ
        
    Returns:
        PersistenceManagerインスタンス
    """
    global _persistence
    if _persistence is None:
        _persistence = PersistenceManager(data_dir)
    return _persistence


def get_minter(treasury_wallet: Optional[TokenWallet] = None) -> "TokenMinter":
    """TokenMinterのグローバルインスタンスを取得
    
    Args:
        treasury_wallet: 初回呼び出し時に必要な国庫ウォレット
        
    Returns:
        TokenMinterインスタンス
    """
    global _minter
    if _minter is None:
        if treasury_wallet is None:
            # デフォルトの国庫ウォレットを作成
            treasury_wallet = create_wallet("treasury", 0.0)
        _minter = TokenMinter(treasury_wallet)
    return _minter


# ============================================================================
# 永続化機能
# ============================================================================

# データディレクトリのパス
DEFAULT_DATA_DIR = Path("/home/moco/workspace/data/wallets")


def _ensure_data_dir(data_dir: Optional[Path] = None) -> Path:
    """データディレクトリが存在することを確認し、存在しない場合は作成する
    
    Args:
        data_dir: データディレクトリのパス（Noneの場合はデフォルト）
        
    Returns:
        データディレクトリのパス
    """
    dir_path = data_dir or DEFAULT_DATA_DIR
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def _get_wallet_path(entity_id: str, data_dir: Optional[Path] = None) -> Path:
    """ウォレットファイルのパスを取得
    
    Args:
        entity_id: エンティティID
        data_dir: データディレクトリのパス（Noneの場合はデフォルト）
        
    Returns:
        ウォレットファイルのパス
    """
    dir_path = _ensure_data_dir(data_dir)
    return dir_path / f"{entity_id}.json"


def save_wallet(entity_id: str, data_dir: Optional[Path] = None) -> bool:
    """指定したエンティティのウォレットをJSONファイルに保存
    
    Args:
        entity_id: 保存するエンティティID
        data_dir: データディレクトリのパス（Noneの場合はデフォルト）
        
    Returns:
        保存成功時True、失敗時False
    """
    wallet = _wallet_registry.get(entity_id)
    if not wallet:
        logger.warning(f"Wallet not found for {entity_id}")
        return False
    
    try:
        file_path = _get_wallet_path(entity_id, data_dir)
        data = wallet.to_dict()
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Saved wallet for {entity_id} to {file_path}")
        return True
    except (IOError, OSError, TypeError) as e:
        logger.error(f"Failed to save wallet for {entity_id}: {e}")
        return False


def load_wallet(entity_id: str, data_dir: Optional[Path] = None) -> Optional[TokenWallet]:
    """JSONファイルからウォレットを読み込み、レジストリに登録
    
    Args:
        entity_id: 読み込むエンティティID
        data_dir: データディレクトリのパス（Noneの場合はデフォルト）
        
    Returns:
        読み込まれたTokenWallet、失敗時はNone
    """
    try:
        file_path = _get_wallet_path(entity_id, data_dir)
        
        if not file_path.exists():
            logger.warning(f"Wallet file not found: {file_path}")
            return None
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        wallet = TokenWallet.from_dict(data)
        _wallet_registry[entity_id] = wallet
        
        # TaskContractにも登録
        tc = get_task_contract()
        tc.register_wallet(wallet)
        
        logger.info(f"Loaded wallet for {entity_id} from {file_path}")
        return wallet
    except (IOError, OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        logger.error(f"Failed to load wallet for {entity_id}: {e}")
        return None


def save_all_wallets(data_dir: Optional[Path] = None) -> int:
    """レジストリ内の全てのウォレットを保存
    
    Args:
        data_dir: データディレクトリのパス（Noneの場合はデフォルト）
        
    Returns:
        保存に成功したウォレットの数
    """
    _ensure_data_dir(data_dir)
    success_count = 0
    
    for entity_id in _wallet_registry:
        if save_wallet(entity_id, data_dir):
            success_count += 1
    
    logger.info(f"Saved {success_count}/{len(_wallet_registry)} wallets")
    return success_count


def load_all_wallets(data_dir: Optional[Path] = None) -> int:
    """データディレクトリ内の全てのウォレットファイルを読み込み
    
    Args:
        data_dir: データディレクトリのパス（Noneの場合はデフォルト）
        
    Returns:
        読み込みに成功したウォレットの数
    """
    dir_path = _ensure_data_dir(data_dir)
    success_count = 0
    
    try:
        json_files = list(dir_path.glob("*.json"))
        
        for file_path in json_files:
            entity_id = file_path.stem  # ファイル名から拡張子を除去
            if load_wallet(entity_id, data_dir):
                success_count += 1
        
        logger.info(f"Loaded {success_count}/{len(json_files)} wallets from {dir_path}")
    except (IOError, OSError) as e:
        logger.error(f"Failed to load wallets from {dir_path}: {e}")
    
    return success_count


if __name__ == "__main__":
    # テスト実行
    print("=== Token System Test ===")
    
    # ウォレット作成
    alice = create_wallet("alice", 1000)
    bob = create_wallet("bob", 500)
    reward_pool = create_wallet("reward_pool", 10000)
    
    print(f"Alice balance: {alice.get_balance()}")
    print(f"Bob balance: {bob.get_balance()}")
    
    # 送金テスト
    alice.transfer(bob, 200, "Initial payment")
    print(f"After transfer - Alice: {alice.get_balance()}, Bob: {bob.get_balance()}")
    
    # タスクコントラクトテスト
    tc = get_task_contract()
    tc.create_task("task-001", "alice", "bob", 100, "Code review")
    print(f"\nTask created. Alice balance: {alice.get_balance()}")
    print(f"Locked amount: {tc.get_locked_amount('task-001')}")
    
    # 取引履歴の確認
    print("\n=== Alice's Transaction History ===")
    for tx in alice.get_transaction_history():
        print(f"  {tx.type.value}: {tx.amount} AIC - {tx.description}")
    
    # 日次集計
    print("\n=== Daily Summary ===")
    summary = alice.get_transaction_summary("daily")
    for date, stats in summary.items():
        print(f"  {date}: Income={stats['income']}, Expense={stats['expense']}, Net={stats['net']}")
    
    tc.complete_task("task-001")
    print(f"\nTask completed. Alice: {alice.get_balance()}, Bob: {bob.get_balance()}")
    
    # 評価テスト（新パラメータ対応）
    rc = get_reputation_contract()
    rc.enable_token_rewards(reward_pool)
    rc.rate_agent("alice", "bob", "task-001", tc, 5, "Excellent work!")
    rc.rate_agent("system", "bob", "task-001", tc, 4, "Good job")
    
    print(f"\nBob's average rating: {rc.get_rating('bob'):.2f}")
    print(f"Bob's trust score: {rc.get_trust_score('bob'):.2f}")
    print(f"Bob's balance after rewards: {bob.get_balance()}")
    
    # トップエージェント
    print("\n=== Top Agents ===")
    top_agents = rc.get_top_agents(min_ratings=1)
    for agent in top_agents:
        print(f"  {agent['entity_id']}: Trust={agent['trust_score']:.2f}, "
              f"Avg={agent['avg_rating']:.2f}, Count={agent['rating_count']}")
    
    # タスク統計
    print("\n=== Task Stats ===")
    stats = tc.get_task_stats()
    print(f"  Total: {stats['total']}")
    print(f"  By status: {stats['by_status']}")
    print(f"  Total completed: {stats['total_amount_completed']} AIC")
    
    # データ保存テスト
    print("\n=== Save/Load Test ===")
    save_all()
    print("Data saved!")
    
    # 永続化テスト
    print("\n=== Persistence Test ===")
    load_all()
    alice_loaded = get_wallet("alice")
    print(f"Alice balance after load: {alice_loaded.get_balance()}")
    
    print("\n=== Token Minter Test ===")
    
    # TokenMinterテスト
    minter = get_token_minter()
    minter.register_wallet(alice)
    minter.register_wallet(bob)
    
    # タスク完了報酬（複雑度5）
    minter.mint_task_reward("bob", complexity=5, task_id="task-002", description="Complex refactoring")
    print(f"Bob after task reward: {bob.get_balance()}")
    
    # レビュー報酬
    minter.mint_review_reward("alice", description="Code review for task-002")
    print(f"Alice after review reward: {alice.get_balance()}")
    
    # イノベーションボーナス
    minter.mint_innovation_bonus("bob", feature_description="Implemented new AI collaboration protocol")
    print(f"Bob after innovation bonus: {bob.get_balance()}")
    
    # 総発行量
    print(f"Total minted: {minter.get_total_minted()} AIC")
    print(f"Remaining supply: {minter.get_remaining_supply()} AIC")
    
    # 発行統計
    print("\nMint stats:")
    stats = minter.get_mint_stats()
    print(f"  Total minted: {stats['total_minted']} AIC")
    print(f"  Max supply: {stats['max_supply']} AIC")
    print(f"  By reward type: {stats['by_reward_type']}")
    
    # 発行履歴
    print("\nMint history for bob:")
    for h in minter.get_mint_history(entity_id="bob"):
        print(f"  {h.reward_type.value}: +{h.amount} AIC - {h.description}")
    
    print("\n=== All Tests Complete ===")
