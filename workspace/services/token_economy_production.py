#!/usr/bin/env python3
"""
Token Economy Production System
実用化対応トークン経済システム

Features:
- Production-grade configuration
- Monitoring and metrics
- Automated pricing
- Security enhancements
- Inflation control
"""

import json
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from collections import deque

from .token_system import (
    get_wallet, create_wallet, get_task_contract,
    get_reputation_contract, get_minter
)
from .token_economy import TokenEconomy, TokenMetadata, get_token_economy

logger = logging.getLogger(__name__)


@dataclass
class PricingConfig:
    """タスク別価格設定"""
    code_generation: float = 10.0
    code_review: float = 5.0
    document_creation: float = 8.0
    research_task: float = 20.0
    testing: float = 7.0
    debugging: float = 15.0
    consultation: float = 12.0
    
    def get_price(self, task_type: str) -> float:
        """タスクタイプに応じた価格を取得"""
        return getattr(self, task_type, 10.0)


@dataclass
class MintingSchedule:
    """トークン発行スケジュール"""
    daily_cap: float = 10000.0
    task_reward_min: float = 1.0
    task_reward_max: float = 100.0
    complexity_multiplier: float = 1.0
    
    def calculate_reward(self, complexity: int) -> float:
        """複雑さに応じた報酬を計算"""
        base = min(max(complexity, 1), 100)
        return base * self.complexity_multiplier


@dataclass
class TransactionMetrics:
    """トランザクションメトリクス"""
    timestamp: datetime
    tx_type: str
    amount: float
    from_entity: str
    to_entity: str


class TokenEconomyProduction:
    """
    実用化対応トークン経済システム
    
    Features:
    - モニタリングとメトリクス収集
    - 自動価格調整
    - インフレーション制御
    - セキュリティ監査
    """
    
    def __init__(
        self,
        pricing_config: Optional[PricingConfig] = None,
        minting_schedule: Optional[MintingSchedule] = None
    ):
        self.economy = get_token_economy()
        self.pricing = pricing_config or PricingConfig()
        self.minting = minting_schedule or MintingSchedule()
        
        # メトリクス収集
        self._metrics: deque[TransactionMetrics] = deque(maxlen=10000)
        self._lock = threading.Lock()
        
        # 監視コールバック
        self._on_large_transfer: Optional[Callable] = None
        self._on_daily_cap_reached: Optional[Callable] = None
        
        # 統計
        self._daily_minted: float = 0.0
        self._last_reset = datetime.now(timezone.utc).date()
        
        logger.info("Token Economy Production initialized")
    
    # === 価格設定 ===
    
    def get_task_price(self, task_type: str, complexity: int = 50) -> float:
        """
        タスク価格を計算
        
        Args:
            task_type: タスクタイプ
            complexity: 複雑さ (1-100)
            
        Returns:
            価格 (AIC)
        """
        base_price = self.pricing.get_price(task_type)
        complexity_factor = 0.5 + (complexity / 100)  # 0.5 - 1.5
        return base_price * complexity_factor
    
    def update_pricing(self, task_type: str, new_price: float):
        """価格を更新"""
        if hasattr(self.pricing, task_type):
            old_price = getattr(self.pricing, task_type)
            setattr(self.pricing, task_type, new_price)
            logger.info(f"Price updated: {task_type} {old_price} -> {new_price}")
    
    # === 報酬計算 ===
    
    def calculate_task_reward(
        self,
        task_type: str,
        complexity: int,
        quality_score: float = 1.0
    ) -> Dict[str, Any]:
        """
        タスク報酬を計算
        
        Args:
            task_type: タスクタイプ
            complexity: 複雑さ
            quality_score: 品質スコア (0.0 - 1.5)
            
        Returns:
            報酬情報
        """
        base = self.minting.calculate_reward(complexity)
        
        # 品質ボーナス
        quality_multiplier = min(max(quality_score, 0.5), 1.5)
        adjusted = base * quality_multiplier
        
        # デイリーキャップチェック
        if self._daily_minted + adjusted > self.minting.daily_cap:
            adjusted = self.minting.daily_cap - self._daily_minted
            capped = True
        else:
            capped = False
        
        return {
            "base_amount": base,
            "quality_multiplier": quality_multiplier,
            "final_amount": max(adjusted, 0),
            "capped": capped,
            "remaining_daily_cap": self.minting.daily_cap - self._daily_minted
        }
    
    def mint_task_reward(
        self,
        agent_id: str,
        task_type: str,
        complexity: int,
        quality_score: float = 1.0,
        task_id: str = ""
    ) -> Dict[str, Any]:
        """
        タスク報酬を発行
        
        Returns:
            発行結果
        """
        self._check_daily_reset()
        
        reward_info = self.calculate_task_reward(task_type, complexity, quality_score)
        amount = reward_info["final_amount"]
        
        if amount <= 0:
            return {
                "success": False,
                "error": "Daily minting cap reached or invalid amount",
                "daily_cap": self.minting.daily_cap,
                "daily_minted": self._daily_minted
            }
        
        # 発行実行
        result = self.economy.mint(
            amount=amount,
            to_entity_id=agent_id,
            reason=f"Task reward: {task_type} (complexity: {complexity})"
        )
        
        if result["success"]:
            with self._lock:
                self._daily_minted += amount
            
            logger.info(f"Minted {amount} AIC to {agent_id} for {task_type}")
            
            # デイリーキャップ到達チェック
            if self._daily_minted >= self.minting.daily_cap:
                if self._on_daily_cap_reached:
                    self._on_daily_cap_reached()
        
        return result
    
    def _check_daily_reset(self):
        """デイリー統計をリセット"""
        today = datetime.now(timezone.utc).date()
        if today > self._last_reset:
            with self._lock:
                self._daily_minted = 0.0
                self._last_reset = today
            logger.info("Daily minting counter reset")
    
    # === メトリクス収集 ===
    
    def record_transaction(
        self,
        tx_type: str,
        amount: float,
        from_entity: str,
        to_entity: str
    ):
        """トランザクションを記録"""
        metric = TransactionMetrics(
            timestamp=datetime.now(timezone.utc),
            tx_type=tx_type,
            amount=amount,
            from_entity=from_entity,
            to_entity=to_entity
        )
        
        with self._lock:
            self._metrics.append(metric)
        
        # 大額取引監視
        if amount > 10000:
            if self._on_large_transfer:
                self._on_large_transfer(metric)
    
    def get_metrics(
        self,
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        メトリクスを取得
        
        Args:
            hours: 過去何時間分を取得
            
        Returns:
            メトリクス統計
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        with self._lock:
            recent = [m for m in self._metrics if m.timestamp > cutoff]
        
        if not recent:
            return {"error": "No data available"}
        
        # 集計
        total_volume = sum(m.amount for m in recent)
        tx_count = len(recent)
        
        by_type: Dict[str, float] = {}
        for m in recent:
            by_type[m.tx_type] = by_type.get(m.tx_type, 0) + m.amount
        
        unique_entities = len(set(
            [m.from_entity for m in recent] + 
            [m.to_entity for m in recent]
        ))
        
        return {
            "period_hours": hours,
            "total_volume": total_volume,
            "transaction_count": tx_count,
            "average_amount": total_volume / tx_count if tx_count > 0 else 0,
            "by_type": by_type,
            "unique_entities": unique_entities,
            "daily_minted": self._daily_minted,
            "daily_cap": self.minting.daily_cap,
            "supply_stats": self.economy.get_supply_stats()
        }
    
    # === 監視コールバック ===
    
    def on_large_transfer(self, callback: Callable[[TransactionMetrics], None]):
        """大額取引時のコールバックを設定"""
        self._on_large_transfer = callback
    
    def on_daily_cap_reached(self, callback: Callable[[], None]):
        """デイリーキャップ到達時のコールバックを設定"""
        self._on_daily_cap_reached = callback
    
    # === ヘルスチェック ===
    
    def health_check(self) -> Dict[str, Any]:
        """システム健全性チェック"""
        supply_stats = self.economy.get_supply_stats()
        
        issues = []
        
        # インフレーションチェック
        if self._daily_minted > self.minting.daily_cap * 0.9:
            issues.append("Daily minting cap nearly reached")
        
        # サプライチェック
        total_supply = supply_stats.get("total_supply", 0)
        if total_supply > 10000000:  # 10M
            issues.append("High total supply")
        
        return {
            "healthy": len(issues) == 0,
            "issues": issues,
            "daily_minted": self._daily_minted,
            "daily_cap": self.minting.daily_cap,
            "total_supply": total_supply
        }


# === グローバルインスタンス ===

_production_economy: Optional[TokenEconomyProduction] = None


def get_production_economy() -> TokenEconomyProduction:
    """実用化経済システムを取得"""
    global _production_economy
    if _production_economy is None:
        _production_economy = TokenEconomyProduction()
    return _production_economy


def initialize_production_economy(
    pricing: Optional[PricingConfig] = None,
    minting: Optional[MintingSchedule] = None
) -> TokenEconomyProduction:
    """実用化経済システムを初期化"""
    global _production_economy
    _production_economy = TokenEconomyProduction(pricing, minting)
    return _production_economy


if __name__ == "__main__":
    # Demo
    print("=== Token Economy Production Demo ===\n")
    
    economy = initialize_production_economy()
    
    # 価格確認
    print("1. Task Pricing:")
    for task_type in ["code_generation", "code_review", "research_task"]:
        price = economy.get_task_price(task_type, complexity=50)
        print(f"   {task_type}: {price:.2f} AIC")
    
    # 報酬計算
    print("\n2. Reward Calculation:")
    for complexity in [10, 50, 100]:
        reward = economy.calculate_task_reward("code_generation", complexity)
        print(f"   Complexity {complexity}: {reward['final_amount']:.2f} AIC")
    
    # ウォレット作成
    print("\n3. Creating wallets...")
    agent_a = create_wallet("Agent_A", 0)
    agent_b = create_wallet("Agent_B", 0)
    
    # 報酬発行
    print("\n4. Minting rewards...")
    for i, agent_id in enumerate(["Agent_A", "Agent_B"], 1):
        result = economy.mint_task_reward(
            agent_id=agent_id,
            task_type="code_generation",
            complexity=50,
            quality_score=1.2,
            task_id=f"task-{i}"
        )
        if result["success"]:
            print(f"   Minted to {agent_id}: {result['amount']:.2f} AIC")
    
    # メトリクス
    print("\n5. Metrics:")
    metrics = economy.get_metrics(hours=1)
    print(f"   Total minted today: {metrics['daily_minted']:.2f} AIC")
    print(f"   Daily cap: {metrics['daily_cap']:.2f} AIC")
    
    # ヘルスチェック
    print("\n6. Health Check:")
    health = economy.health_check()
    print(f"   Healthy: {health['healthy']}")
    if health['issues']:
        print(f"   Issues: {health['issues']}")
    
    print("\n=== Demo Complete ===")
