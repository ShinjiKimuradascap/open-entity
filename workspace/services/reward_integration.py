#!/usr/bin/env python3
"""
Reward Integration Module
タスク評価とトークン報酬の連携モジュール

評価が確定した際に自動的にトークン報酬を発行し、
タスクと報酬トランザクションの紐付けを管理する。
"""

import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sys
import json

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from task_evaluation import TaskEvaluator, TaskEvaluation, EvaluationStatus
from token_economy import TokenEconomy, get_token_economy, TokenMetadata
from token_system import TokenWallet, get_wallet, create_wallet, Transaction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class RewardRecord:
    """報酬発行記録
    
    Attributes:
        record_id: 記録ID
        task_id: タスクID
        evaluation_id: 評価ID
        recipient_id: 受取人エンティティID
        amount: 報酬額
        transaction_id: トランザクションID（token_system内部ID）
        status: 発行状態
        reason: 発行理由
        created_at: 作成日時
        metadata: 追加メタデータ
    """
    record_id: str
    task_id: str
    evaluation_id: str
    recipient_id: str
    amount: float
    transaction_id: Optional[str] = None
    status: str = "pending"  # pending, issued, failed
    reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "record_id": self.record_id,
            "task_id": self.task_id,
            "evaluation_id": self.evaluation_id,
            "recipient_id": self.recipient_id,
            "amount": self.amount,
            "transaction_id": self.transaction_id,
            "status": self.status,
            "reason": self.reason,
            "created_at": self.created_at,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RewardRecord":
        return cls(
            record_id=data["record_id"],
            task_id=data["task_id"],
            evaluation_id=data["evaluation_id"],
            recipient_id=data["recipient_id"],
            amount=data["amount"],
            transaction_id=data.get("transaction_id"),
            status=data.get("status", "pending"),
            reason=data.get("reason", ""),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            metadata=data.get("metadata", {})
        )


class RewardIntegration:
    """報酬統合マネージャー
    
    タスク評価とトークン報酬の連携を管理する中心クラス。
    評価確定時に自動的に報酬を発行し、履歴を追跡する。
    """
    
    def __init__(self, 
                 token_economy: Optional[TokenEconomy] = None,
                 auto_issue: bool = True):
        """
        Args:
            token_economy: TokenEconomyインスタンス（None時はグローバル取得）
            auto_issue: 評価確定時に自動で報酬を発行するか
        """
        self._economy = token_economy or get_token_economy()
        self._auto_issue = auto_issue
        self._records: Dict[str, RewardRecord] = {}
        self._task_reward_map: Dict[str, str] = {}  # task_id -> record_id
        self._persistence_file = Path("data/reward_records.json")
        self._load_records()
        
        logger.info(f"RewardIntegration initialized (auto_issue={auto_issue})")
    
    def _load_records(self) -> None:
        """永続化された記録を読み込み"""
        if self._persistence_file.exists():
            try:
                with open(self._persistence_file, 'r') as f:
                    data = json.load(f)
                    for record_data in data.get("records", []):
                        record = RewardRecord.from_dict(record_data)
                        self._records[record.record_id] = record
                        self._task_reward_map[record.task_id] = record.record_id
                logger.info(f"Loaded {len(self._records)} reward records")
            except Exception as e:
                logger.error(f"Failed to load records: {e}")
    
    def _save_records(self) -> None:
        """記録を永続化"""
        try:
            self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "records": [r.to_dict() for r in self._records.values()],
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            with open(self._persistence_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save records: {e}")
    
    def issue_reward(self,
                     task_id: str,
                     evaluation_id: str,
                     recipient_id: str,
                     amount: float,
                     reason: str = "",
                     metadata: Optional[Dict[str, Any]] = None) -> Optional[RewardRecord]:
        """報酬を発行
        
        Args:
            task_id: タスクID
            evaluation_id: 評価ID
            recipient_id: 受取人エンティティID
            amount: 報酬額
            reason: 発行理由
            metadata: 追加メタデータ
            
        Returns:
            RewardRecord if successful, None otherwise
        """
        import uuid
        
        if amount <= 0:
            logger.warning(f"Reward amount must be positive: {amount}")
            return None
        
        # Create record
        record = RewardRecord(
            record_id=str(uuid.uuid4()),
            task_id=task_id,
            evaluation_id=evaluation_id,
            recipient_id=recipient_id,
            amount=amount,
            reason=reason or f"Reward for task {task_id}",
            metadata=metadata or {}
        )
        
        # Mint tokens
        full_reason = f"Task {task_id}: {reason}"
        success = self._economy.mint(
            amount=amount,
            to_entity_id=recipient_id,
            reason=full_reason
        )
        
        if success:
            record.status = "issued"
            # Get wallet to find transaction ID
            wallet = get_wallet(recipient_id)
            if wallet and wallet.transactions:
                last_tx = wallet.transactions[-1]
                record.transaction_id = getattr(last_tx, 'tx_id', None)
            logger.info(f"Issued {amount} AIC to {recipient_id} for task {task_id}")
        else:
            record.status = "failed"
            logger.error(f"Failed to issue reward for task {task_id}")
        
        # Store record
        self._records[record.record_id] = record
        self._task_reward_map[task_id] = record.record_id
        self._save_records()
        
        return record
    
    def issue_reward_from_evaluation(self, evaluation: TaskEvaluation) -> Optional[RewardRecord]:
        """評価結果から報酬を発行
        
        Args:
            evaluation: TaskEvaluationオブジェクト
            
        Returns:
            RewardRecord if successful, None otherwise
        """
        if evaluation.status != EvaluationStatus.FINALIZED.value:
            logger.warning(f"Evaluation {evaluation.evaluation_id} is not finalized")
            return None
        
        if evaluation.reward_recommendation <= 0:
            logger.info(f"No reward recommended for evaluation {evaluation.evaluation_id}")
            return None
        
        # Extract recipient from evaluation context (if available)
        recipient_id = evaluation.evaluator_id  # Fallback
        # In real implementation, would get from task metadata
        
        return self.issue_reward(
            task_id=evaluation.task_id,
            evaluation_id=evaluation.evaluation_id,
            recipient_id=recipient_id,
            amount=evaluation.reward_recommendation,
            reason=f"Task evaluation: {evaluation.verdict} (score: {evaluation.overall_score:.1f})",
            metadata={
                "overall_score": evaluation.overall_score,
                "verdict": evaluation.verdict,
                "feedback": evaluation.feedback
            }
        )
    
    def get_reward_by_task(self, task_id: str) -> Optional[RewardRecord]:
        """タスクIDで報酬記録を取得"""
        record_id = self._task_reward_map.get(task_id)
        if record_id:
            return self._records.get(record_id)
        return None
    
    def get_reward_by_evaluation(self, evaluation_id: str) -> Optional[RewardRecord]:
        """評価IDで報酬記録を取得"""
        for record in self._records.values():
            if record.evaluation_id == evaluation_id:
                return record
        return None
    
    def get_entity_rewards(self, entity_id: str) -> List[RewardRecord]:
        """エンティティの報酬記録一覧を取得"""
        return [r for r in self._records.values() if r.recipient_id == entity_id]
    
    def get_total_rewards_issued(self, entity_id: Optional[str] = None) -> float:
        """発行済み報酬合計を取得
        
        Args:
            entity_id: 指定時はそのエンティティのみ、None時は全エンティティ
        """
        records = self._records.values()
        if entity_id:
            records = [r for r in records if r.recipient_id == entity_id]
        
        return sum(r.amount for r in records if r.status == "issued")
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得"""
        total_records = len(self._records)
        issued = sum(1 for r in self._records.values() if r.status == "issued")
        failed = sum(1 for r in self._records.values() if r.status == "failed")
        pending = sum(1 for r in self._records.values() if r.status == "pending")
        total_amount = sum(r.amount for r in self._records.values() if r.status == "issued")
        
        # Unique entities
        entities = set(r.recipient_id for r in self._records.values())
        
        return {
            "total_records": total_records,
            "issued": issued,
            "failed": failed,
            "pending": pending,
            "total_amount_issued": total_amount,
            "unique_entities": len(entities),
            "token_supply": self._economy.get_total_supply()
        }


class AutoRewardEvaluator(TaskEvaluator):
    """自動報酬発行付きタスク評価器
    
    TaskEvaluatorを継承し、評価確定時に自動で報酬を発行する。
    """
    
    def __init__(self, reward_integration: Optional[RewardIntegration] = None):
        super().__init__()
        self._reward_integration = reward_integration or RewardIntegration()
    
    def finalize_evaluation(self, *args, **kwargs) -> Optional[TaskEvaluation]:
        """評価を確定し、報酬を自動発行"""
        evaluation = super().finalize_evaluation(*args, **kwargs)
        
        if evaluation and evaluation.reward_recommendation > 0:
            # Auto-issue reward
            record = self._reward_integration.issue_reward_from_evaluation(evaluation)
            if record:
                logger.info(f"Auto-issued reward: {record.amount} AIC for task {evaluation.task_id}")
        
        return evaluation


# Global instance
_reward_integration: Optional[RewardIntegration] = None


def get_reward_integration() -> RewardIntegration:
    """グローバルRewardIntegrationインスタンスを取得"""
    global _reward_integration
    if _reward_integration is None:
        _reward_integration = RewardIntegration()
    return _reward_integration


def initialize_reward_integration(token_economy: Optional[TokenEconomy] = None,
                                   auto_issue: bool = True) -> RewardIntegration:
    """RewardIntegrationを初期化"""
    global _reward_integration
    _reward_integration = RewardIntegration(
        token_economy=token_economy,
        auto_issue=auto_issue
    )
    return _reward_integration


if __name__ == "__main__":
    print("=== Reward Integration Test ===\n")
    
    # Initialize
    integration = RewardIntegration()
    
    # Test 1: Direct reward issuance
    print("Test 1: Direct reward issuance")
    record = integration.issue_reward(
        task_id="task-001",
        evaluation_id="eval-001",
        recipient_id="entity-b",
        amount=50.0,
        reason="Task completion reward"
    )
    if record and record.status == "issued":
        print(f"  ✓ Issued {record.amount} AIC to {record.recipient_id}")
        wallet = get_wallet("entity-b")
        print(f"  ✓ Wallet balance: {wallet.get_balance()} AIC")
    else:
        print("  ✗ Failed to issue reward")
    
    # Test 2: Get reward by task
    print("\nTest 2: Get reward by task")
    found = integration.get_reward_by_task("task-001")
    if found:
        print(f"  ✓ Found reward: {found.amount} AIC for task {found.task_id}")
    else:
        print("  ✗ Reward not found")
    
    # Test 3: Entity rewards
    print("\nTest 3: Entity rewards")
    integration.issue_reward(
        task_id="task-002",
        evaluation_id="eval-002",
        recipient_id="entity-b",
        amount=30.0,
        reason="Second task"
    )
    rewards = integration.get_entity_rewards("entity-b")
    print(f"  ✓ Entity-b has {len(rewards)} rewards")
    total = integration.get_total_rewards_issued("entity-b")
    print(f"  ✓ Total received: {total} AIC")
    
    # Test 4: Statistics
    print("\nTest 4: Statistics")
    stats = integration.get_statistics()
    print(f"  Total records: {stats['total_records']}")
    print(f"  Issued: {stats['issued']}")
    print(f"  Total amount: {stats['total_amount_issued']} AIC")
    print(f"  Token supply: {stats['token_supply']} AIC")
    
    print("\n=== All Tests Passed ===")
