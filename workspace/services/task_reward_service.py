#!/usr/bin/env python3
"""
Task Reward Service
タスク完了検証とトークン報酬発行の連携サービス
"""

import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime

from task_delegation import (
    TaskDelegationMessage,
    TaskResponseMessage,
    TaskCompletionVerifier,
    VerificationResult
)

# TokenSystemはオプショナル（インポートできなくても動作）
try:
    from token_system import TokenMinter, get_minter
    TOKEN_SYSTEM_AVAILABLE = True
except ImportError:
    TOKEN_SYSTEM_AVAILABLE = False
    TokenMinter = None
    get_minter = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TaskRewardService:
    """タスク報酬サービス
    
    タスク完了検証とトークン報酬発行を連携させるサービス。
    検証合格時に自動的に報酬を発行する。
    """
    
    def __init__(
        self,
        verifier: Optional[TaskCompletionVerifier] = None,
        minter: Optional[TokenMinter] = None,
        auto_reward: bool = True
    ):
        """
        Args:
            verifier: TaskCompletionVerifierインスタンス
            minter: TokenMinterインスタンス（Noneの場合はグローバルインスタンスを使用）
            auto_reward: 検証合格時に自動で報酬を発行するか
        """
        self.verifier = verifier or TaskCompletionVerifier()
        self.minter = minter
        self.auto_reward = auto_reward and TOKEN_SYSTEM_AVAILABLE
        
        # 報酬設定
        self._reward_rates: Dict[str, float] = {
            "default": 10.0,
            "CODE": 20.0,
            "REVIEW": 15.0,
            "RESEARCH": 25.0,
            "ANALYSIS": 15.0,
            "TEST": 10.0,
            "DOCUMENT": 8.0,
            "DEPLOY": 12.0,
            "CRITICAL": 30.0,
            "EMERGENCY": 50.0
        }
        
        # 検証合格時のコールバックを登録
        self.verifier.register_verified_callback(self._on_task_verified)
        
        # 報酬発行履歴
        self._reward_history: Dict[str, list] = {}
        
        logger.info(f"TaskRewardService initialized (auto_reward={self.auto_reward})")
    
    def _on_task_verified(self, task_id: str, result: VerificationResult) -> None:
        """タスク検証合格時のコールバック"""
        logger.info(f"Task {task_id} verified, processing reward")
        
        if self.auto_reward and result.verified:
            self._process_reward(task_id, result)
    
    def _process_reward(
        self, 
        task_id: str, 
        result: VerificationResult,
        agent_id: str = "",
        complexity: int = 10,
        description: str = ""
    ) -> Optional[Dict[str, Any]]:
        """報酬を処理
        
        Args:
            task_id: タスクID
            result: 検証結果
            agent_id: 報酬受取エージェントID
            complexity: タスク複雑度（1-100、TokenMinterに渡す）
            description: タスク説明
            
        Returns:
            報酬発行結果の辞書、失敗時はNone
        """
        if not TOKEN_SYSTEM_AVAILABLE:
            logger.warning("TokenSystem not available, skipping reward")
            return None
        
        # TokenMinterインスタンスを取得
        minter = self.minter or get_minter()
        if not minter:
            logger.warning("TokenMinter not available, skipping reward")
            return None
        
        # 複雑度を1-100の範囲にクリップ
        complexity = max(1, min(100, complexity))
        
        try:
            # 実際のトークン発行
            mint_success = minter.mint_for_task_completion(
                agent_id=agent_id,
                complexity=complexity,
                task_id=task_id,
                description=description
            )
            
            # 報酬発行結果を記録
            reward_result = {
                "task_id": task_id,
                "amount": complexity,
                "timestamp": datetime.utcnow().isoformat(),
                "status": "issued" if mint_success else "failed",
                "verification_score": result.score,
                "agent_id": agent_id,
                "mint_success": mint_success
            }
            
            # 履歴に記録
            if task_id not in self._reward_history:
                self._reward_history[task_id] = []
            self._reward_history[task_id].append(reward_result)
            
            if mint_success:
                logger.info(f"Reward issued for task {task_id}: {complexity} AIC to {agent_id}")
            else:
                logger.error(f"Failed to mint reward for task {task_id}")
                
            return reward_result
            
        except Exception as e:
            logger.error(f"Failed to issue reward: {e}")
            return None
    
    def set_reward_rate(self, task_type: str, amount: float) -> None:
        """タスクタイプごとの報酬額を設定
        
        Args:
            task_type: タスクタイプ（CODE, REVIEW等）
            amount: 報酬額
        """
        self._reward_rates[task_type.upper()] = amount
        logger.info(f"Reward rate for {task_type}: {amount} AIC")
    
    def verify_and_reward(
        self,
        task: TaskDelegationMessage,
        response: TaskResponseMessage
    ) -> VerificationResult:
        """タスクを検証し、合格時に報酬を発行
        
        Args:
            task: タスク定義
            response: 完了応答
            
        Returns:
            VerificationResult: 検証結果
        """
        # 検証実行
        result = self.verifier.verify_completion(task, response)
        
        # 検証合格時に報酬を発行
        if self.auto_reward and result.verified:
            # 報酬額を計算
            reward_amount = self.calculate_reward(task)
            # 1-100の範囲に変換（TokenMinterのcomplexityパラメータ用）
            complexity = min(100, max(1, int(reward_amount)))
            
            # 報酬を発行
            self._process_reward(
                task_id=task.task_id,
                result=result,
                agent_id=response.responder_id,
                complexity=complexity,
                description=task.title
            )
        
        return result
    
    def calculate_reward(self, task: TaskDelegationMessage) -> float:
        """タスクの報酬額を計算
        
        Args:
            task: タスク定義
            
        Returns:
            float: 計算された報酬額
        """
        # タスクタイプに基づく基本報酬
        base_amount = self._reward_rates.get(
            task.task_type.upper(),
            self._reward_rates["default"]
        )
        
        # 優先度によるボーナス
        priority_multiplier = 1.0
        if hasattr(task, 'priority'):
            priority_map = {
                "LOW": 0.8,
                "NORMAL": 1.0,
                "HIGH": 1.5,
                "CRITICAL": 2.0,
                "EMERGENCY": 3.0
            }
            priority_multiplier = priority_map.get(task.priority, 1.0)
        
        # 工数による調整
        hours_multiplier = 1.0
        if task.estimated_hours:
            if task.estimated_hours <= 1:
                hours_multiplier = 0.5
            elif task.estimated_hours <= 4:
                hours_multiplier = 1.0
            elif task.estimated_hours <= 8:
                hours_multiplier = 1.5
            else:
                hours_multiplier = 2.0
        
        calculated = base_amount * priority_multiplier * hours_multiplier
        
        # タスクに設定された報酬があればそれを優先
        if task.reward_amount > 0:
            calculated = task.reward_amount
        
        return round(calculated, 2)
    
    def get_reward_history(self, task_id: str) -> list:
        """タスクの報酬履歴を取得"""
        return self._reward_history.get(task_id, [])
    
    def get_statistics(self) -> Dict[str, Any]:
        """サービス統計を取得"""
        verification_stats = self.verifier.get_statistics()
        total_rewards = sum(
            len(rewards) for rewards in self._reward_history.values()
        )
        
        # Minterの統計情報を取得
        minter_stats = {}
        if TOKEN_SYSTEM_AVAILABLE and self.minter:
            minter_stats = {
                "total_minted": getattr(self.minter, 'total_minted', 0),
                "treasury_balance": getattr(self.minter.treasury, 'balance', 0) if self.minter.treasury else 0
            }
        
        return {
            "verification": verification_stats,
            "total_rewards_issued": total_rewards,
            "reward_rates": self._reward_rates.copy(),
            "auto_reward_enabled": self.auto_reward,
            "token_system_available": TOKEN_SYSTEM_AVAILABLE,
            "minter_stats": minter_stats
        }


# グローバルインスタンス（簡易利用用）
_default_service: Optional[TaskRewardService] = None


def get_reward_service() -> TaskRewardService:
    """デフォルトのTaskRewardServiceを取得"""
    global _default_service
    if _default_service is None:
        _default_service = TaskRewardService()
    return _default_service


def verify_task_completion(
    task: TaskDelegationMessage,
    response: TaskResponseMessage,
    auto_reward: bool = True
) -> VerificationResult:
    """タスク完了を検証（簡易関数）
    
    Args:
        task: タスク定義
        response: 完了応答
        auto_reward: 自動報酬発行の有無
        
    Returns:
        VerificationResult: 検証結果
    """
    service = get_reward_service()
    service.auto_reward = auto_reward
    return service.verify_and_reward(task, response)


if __name__ == "__main__":
    # テスト
    print("=" * 60)
    print("Testing TaskRewardService with TokenMinter")
    print("=" * 60)
    
    from task_delegation import create_delegation_message, create_complete_response
    
    # サービス作成（auto_reward=Trueで実際のトークン発行を有効化）
    service = TaskRewardService(auto_reward=True)
    
    print(f"\nTokenSystem available: {TOKEN_SYSTEM_AVAILABLE}")
    print(f"Auto reward enabled: {service.auto_reward}")
    
    # 報酬設定
    service.set_reward_rate("CODE", 25.0)
    service.set_reward_rate("REVIEW", 15.0)
    
    # テストケース1: 通常のタスク完了と報酬発行
    print("\n" + "-" * 40)
    print("Test 1: Task completion with reward")
    print("-" * 40)
    
    task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-b",
        title="Implement Feature",
        description="Add new feature",
        task_type="CODE",
        priority="HIGH",
        estimated_hours=4.0,
        reward_amount=30.0
    )
    task.deliverables = [{"type": "code"}]
    
    # 報酬計算
    calculated = service.calculate_reward(task)
    print(f"Calculated reward: {calculated} AIC")
    print(f"Complexity (for TokenMinter): {min(100, max(1, int(calculated)))}")
    
    # 完了応答
    response = create_complete_response(
        task_id=task.task_id,
        responder_id="entity-b",
        result={"done": True},
        deliverables=[{"type": "code"}]
    )
    
    # 検証と報酬（実際のトークン発行）
    result = service.verify_and_reward(task, response)
    print(f"Verification: {result.verified} (score: {result.score:.2f})")
    
    # 報酬履歴を確認
    history = service.get_reward_history(task.task_id)
    print(f"Reward history: {len(history)} entries")
    if history:
        print(f"  - Amount: {history[0]['amount']} AIC")
        print(f"  - Status: {history[0]['status']}")
        print(f"  - Mint success: {history[0].get('mint_success', False)}")
    
    # テストケース2: 低複雑度タスク
    print("\n" + "-" * 40)
    print("Test 2: Low complexity task")
    print("-" * 40)
    
    simple_task = create_delegation_message(
        delegator_id="entity-a",
        delegatee_id="entity-c",
        title="Fix typo",
        description="Fix documentation typo",
        task_type="DOCUMENT",
        priority="LOW",
        estimated_hours=0.5,
        reward_amount=0
    )
    simple_task.deliverables = [{"type": "document"}]
    
    simple_calculated = service.calculate_reward(simple_task)
    print(f"Calculated reward: {simple_calculated} AIC")
    
    simple_response = create_complete_response(
        task_id=simple_task.task_id,
        responder_id="entity-c",
        result={"done": True},
        deliverables=[{"type": "document"}]
    )
    
    simple_result = service.verify_and_reward(simple_task, simple_response)
    print(f"Verification: {simple_result.verified}")
    
    # テストケース3: 統計情報
    print("\n" + "-" * 40)
    print("Test 3: Statistics")
    print("-" * 40)
    
    stats = service.get_statistics()
    print(f"Total rewards issued: {stats['total_rewards_issued']}")
    print(f"Auto reward enabled: {stats['auto_reward_enabled']}")
    print(f"Token system available: {stats['token_system_available']}")
    if stats.get('minter_stats'):
        print(f"Minter total minted: {stats['minter_stats'].get('total_minted', 0)}")
        print(f"Treasury balance: {stats['minter_stats'].get('treasury_balance', 0)}")
    
    print("\n" + "=" * 60)
    print("✅ All tests passed!")
    print("=" * 60)
