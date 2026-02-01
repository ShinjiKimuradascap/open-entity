#!/usr/bin/env python3
"""
L4 AI Economy - Transaction Fees & Distribution
取引手数料と分配ロジック

Fee Structure:
- Platform Fee: 2.5% (Protocol Treasury)
- Validator Fee: 0.5% (Block validators)
- Liquidity Provider: 0.3% (LP rewards)
- Developer Fund: 0.2% (Protocol development)
- Total: 3.5%

Distribution Strategy:
- 40%: Reinvest (infrastructure)
- 30%: Staking rewards
- 20%: Liquidity pool
- 10%: Reserve
"""

from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum
import json


class FeeType(Enum):
    """手数料タイプ"""
    PLATFORM = "platform"      # プラットフォーム手数料
    VALIDATOR = "validator"    # バリデータ報酬
    LIQUIDITY = "liquidity"    # 流動性提供者報酬
    DEVELOPER = "developer"    # 開発者基金


# 手数料率 (パーセンテージ)
FEE_RATES = {
    FeeType.PLATFORM: 2.5,
    FeeType.VALIDATOR: 0.5,
    FeeType.LIQUIDITY: 0.3,
    FeeType.DEVELOPER: 0.2,
}

# 分配戦略 (収益の内訳)
DISTRIBUTION_STRATEGY = {
    "reinvest": 0.40,      # 再投資 (インフラ強化)
    "staking": 0.30,       # ステーキング報酬
    "liquidity": 0.20,     # 流動性プール
    "reserve": 0.10,       # 準備金
}


@dataclass
class FeeBreakdown:
    """手数料内訳"""
    original_amount: float
    platform_fee: float
    validator_fee: float
    liquidity_fee: float
    developer_fee: float
    seller_receives: float
    
    @property
    def total_fee(self) -> float:
        return self.platform_fee + self.validator_fee + self.liquidity_fee + self.developer_fee
    
    @property
    def total_fee_percentage(self) -> float:
        return (self.total_fee / self.original_amount) * 100 if self.original_amount > 0 else 0


@dataclass
class DistributionAllocation:
    """分配配分"""
    total_revenue: float
    reinvest_amount: float
    staking_amount: float
    liquidity_amount: float
    reserve_amount: float
    
    def to_dict(self) -> Dict:
        return {
            "total_revenue": round(self.total_revenue, 4),
            "reinvest": round(self.reinvest_amount, 4),
            "staking": round(self.staking_amount, 4),
            "liquidity": round(self.liquidity_amount, 4),
            "reserve": round(self.reserve_amount, 4),
            "percentages": {
                "reinvest": f"{DISTRIBUTION_STRATEGY['reinvest'] * 100:.0f}%",
                "staking": f"{DISTRIBUTION_STRATEGY['staking'] * 100:.0f}%",
                "liquidity": f"{DISTRIBUTION_STRATEGY['liquidity'] * 100:.0f}%",
                "reserve": f"{DISTRIBUTION_STRATEGY['reserve'] * 100:.0f}%",
            }
        }


class FeeCalculator:
    """手数料計算機"""
    
    def __init__(self):
        self.fee_rates = FEE_RATES
        self.total_fee_rate = sum(FEE_RATES.values())
    
    def calculate_fees(self, transaction_amount: float) -> FeeBreakdown:
        """
        取引手数料を計算
        
        Args:
            transaction_amount: 取引金額 (AIC)
        
        Returns:
            FeeBreakdown: 手数料内訳
        """
        platform = transaction_amount * (self.fee_rates[FeeType.PLATFORM] / 100)
        validator = transaction_amount * (self.fee_rates[FeeType.VALIDATOR] / 100)
        liquidity = transaction_amount * (self.fee_rates[FeeType.LIQUIDITY] / 100)
        developer = transaction_amount * (self.fee_rates[FeeType.DEVELOPER] / 100)
        
        total_fees = platform + validator + liquidity + developer
        seller_receives = transaction_amount - total_fees
        
        return FeeBreakdown(
            original_amount=transaction_amount,
            platform_fee=round(platform, 4),
            validator_fee=round(validator, 4),
            liquidity_fee=round(liquidity, 4),
            developer_fee=round(developer, 4),
            seller_receives=round(seller_receives, 4)
        )
    
    def get_fee_summary(self) -> Dict:
        """手数料概要を取得"""
        return {
            "rates": {
                ft.value: f"{rate}%" for ft, rate in self.fee_rates.items()
            },
            "total": f"{self.total_fee_rate}%",
            "breakdown_example": self._get_example_breakdown()
        }
    
    def _get_example_breakdown(self) -> Dict:
        """100 AICの例を表示"""
        breakdown = self.calculate_fees(100.0)
        return {
            "transaction_amount": 100.0,
            "platform_fee": breakdown.platform_fee,
            "validator_fee": breakdown.validator_fee,
            "liquidity_fee": breakdown.liquidity_fee,
            "developer_fee": breakdown.developer_fee,
            "total_fee": breakdown.total_fee,
            "seller_receives": breakdown.seller_receives
        }


class RevenueDistributor:
    """収益分配システム"""
    
    def __init__(self):
        self.strategy = DISTRIBUTION_STRATEGY
    
    def distribute(self, revenue: float) -> DistributionAllocation:
        """
        収益を分配
        
        Args:
            revenue: 総収益 (AIC)
        
        Returns:
            DistributionAllocation: 分配配分
        """
        reinvest = revenue * self.strategy["reinvest"]
        staking = revenue * self.strategy["staking"]
        liquidity = revenue * self.strategy["liquidity"]
        reserve = revenue * self.strategy["reserve"]
        
        return DistributionAllocation(
            total_revenue=revenue,
            reinvest_amount=reinvest,
            staking_amount=staking,
            liquidity_amount=liquidity,
            reserve_amount=reserve
        )
    
    def calculate_staking_rewards(self, staked_amount: float, total_staked: float, 
                                   reward_pool: float) -> float:
        """
        ステーキング報酬を計算
        
        Args:
            staked_amount: ユーザーのステーク量
            total_staked: 総ステーク量
            reward_pool: 報酬プール
        
        Returns:
            報酬額
        """
        if total_staked == 0:
            return 0.0
        
        share = staked_amount / total_staked
        return round(reward_pool * share, 4)


class TransactionProcessor:
    """取引プロセッサー (統合機能)"""
    
    def __init__(self):
        self.fee_calculator = FeeCalculator()
        self.revenue_distributor = RevenueDistributor()
        self.transaction_history: List[Dict] = []
    
    def process_transaction(self, buyer_id: str, seller_id: str, 
                           amount: float, service_id: str) -> Dict:
        """
        取引を処理
        
        Args:
            buyer_id: 購入者ID
            seller_id: 販売者ID
            amount: 取引金額
            service_id: サービスID
        
        Returns:
            取引結果
        """
        # 手数料計算
        fees = self.fee_calculator.calculate_fees(amount)
        
        # 手数料収益の分配
        fee_distribution = self.revenue_distributor.distribute(fees.total_fee)
        
        # 販売者収益の分配 (40%を再投資等に)
        seller_distribution = self.revenue_distributor.distribute(fees.seller_receives)
        
        result = {
            "transaction_id": f"tx_{len(self.transaction_history) + 1:06d}",
            "buyer_id": buyer_id,
            "seller_id": seller_id,
            "service_id": service_id,
            "original_amount": amount,
            "fees": {
                "platform": fees.platform_fee,
                "validator": fees.validator_fee,
                "liquidity": fees.liquidity_fee,
                "developer": fees.developer_fee,
                "total": fees.total_fee,
                "percentage": fees.total_fee_percentage
            },
            "seller_receives": fees.seller_receives,
            "fee_distribution": fee_distribution.to_dict(),
            "seller_distribution": seller_distribution.to_dict()
        }
        
        self.transaction_history.append(result)
        return result
    
    def get_network_stats(self) -> Dict:
        """ネットワーク統計を取得"""
        if not self.transaction_history:
            return {"message": "No transactions yet"}
        
        total_volume = sum(tx["original_amount"] for tx in self.transaction_history)
        total_fees = sum(tx["fees"]["total"] for tx in self.transaction_history)
        
        return {
            "total_transactions": len(self.transaction_history),
            "total_volume": round(total_volume, 4),
            "total_fees_collected": round(total_fees, 4),
            "average_transaction": round(total_volume / len(self.transaction_history), 4),
            "fee_percentage": round((total_fees / total_volume) * 100, 2) if total_volume > 0 else 0
        }


def demo():
    """デモンストレーション"""
    print("=" * 70)
    print("L4 AI Economy - Transaction Fees & Distribution Demo")
    print("=" * 70)
    
    processor = TransactionProcessor()
    
    # 手数料構造の表示
    print("\n📊 Fee Structure:")
    print("-" * 70)
    fee_summary = processor.fee_calculator.get_fee_summary()
    for fee_type, rate in fee_summary["rates"].items():
        print(f"  {fee_type.capitalize():12s}: {rate}")
    print(f"  {'Total':12s}: {fee_summary['total']}")
    
    # 内訳例
    print("\n💰 Example Breakdown (100 AIC transaction):")
    print("-" * 70)
    ex = fee_summary["breakdown_example"]
    print(f"  Transaction Amount: {ex['transaction_amount']} AIC")
    print(f"  Platform Fee:       {ex['platform_fee']} AIC")
    print(f"  Validator Fee:      {ex['validator_fee']} AIC")
    print(f"  Liquidity Fee:      {ex['liquidity_fee']} AIC")
    print(f"  Developer Fee:      {ex['developer_fee']} AIC")
    print(f"  Total Fee:          {ex['total_fee']} AIC")
    print(f"  Seller Receives:    {ex['seller_receives']} AIC")
    
    # 取引シミュレーション
    print("\n🔄 Transaction Simulation:")
    print("-" * 70)
    
    transactions = [
        ("entity_b", "entity_a", 10.0, "CODE_GEN"),
        ("entity_c", "entity_a", 25.0, "CODE_REVIEW"),
        ("entity_b", "entity_d", 50.0, "RESEARCH"),
        ("entity_e", "entity_a", 100.0, "FULL_PROJECT"),
    ]
    
    for buyer, seller, amount, service in transactions:
        result = processor.process_transaction(buyer, seller, amount, service)
        print(f"\n  {result['transaction_id']}:")
        print(f"    {buyer} → {seller}: {amount} AIC ({service})")
        print(f"    Fee: {result['fees']['total']} AIC ({result['fees']['percentage']:.1f}%)")
        print(f"    Seller gets: {result['seller_receives']} AIC")
    
    # ネットワーク統計
    print("\n📈 Network Statistics:")
    print("-" * 70)
    stats = processor.get_network_stats()
    print(f"  Total Transactions: {stats['total_transactions']}")
    print(f"  Total Volume:       {stats['total_volume']} AIC")
    print(f"  Total Fees:         {stats['total_fees_collected']} AIC")
    print(f"  Avg Transaction:    {stats['average_transaction']} AIC")
    
    # 分配戦略
    print("\n🏦 Distribution Strategy:")
    print("-" * 70)
    example_revenue = 100.0
    allocation = processor.revenue_distributor.distribute(example_revenue)
    dist = allocation.to_dict()
    print(f"  Revenue: {dist['total_revenue']} AIC")
    print(f"  → Reinvest:   {dist['reinvest']} AIC ({dist['percentages']['reinvest']})")
    print(f"  → Staking:    {dist['staking']} AIC ({dist['percentages']['staking']})")
    print(f"  → Liquidity:  {dist['liquidity']} AIC ({dist['percentages']['liquidity']})")
    print(f"  → Reserve:    {dist['reserve']} AIC ({dist['percentages']['reserve']})")
    
    # ステーキング報酬計算例
    print("\n🥩 Staking Rewards Example:")
    print("-" * 70)
    reward_pool = 30.0  # ステーキング報酬プール
    total_staked = 1000.0
    user_stake = 100.0
    
    reward = processor.revenue_distributor.calculate_staking_rewards(
        user_stake, total_staked, reward_pool
    )
    print(f"  Total Staked:    {total_staked} AIC")
    print(f"  Your Stake:      {user_stake} AIC ({(user_stake/total_staked)*100:.1f}%)")
    print(f"  Reward Pool:     {reward_pool} AIC")
    print(f"  Your Reward:     {reward} AIC")
    
    print("\n" + "=" * 70)
    print("✅ Transaction Fee System Ready!")
    print("=" * 70)


if __name__ == "__main__":
    demo()
