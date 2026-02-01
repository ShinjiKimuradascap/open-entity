#!/usr/bin/env python3
"""
Liquidity Pool System for AI Service Marketplace
AIサービスマーケットプレイス用流動性プールシステム

L4-3 Implementation: Token Liquidity Management
"""

import json
import uuid
import time
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import threading


class PoolStatus(Enum):
    """流動性プールステータス"""
    ACTIVE = "active"
    PAUSED = "paused"
    CLOSED = "closed"
    EMERGENCY = "emergency"  # 緊急時（大規模引き出し制限）


class LiquidityAction(Enum):
    """流動性アクション"""
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"
    SWAP = "swap"
    EARN = "earn"


@dataclass
class LiquidityProvider:
    """流動性プロバイダー"""
    provider_id: str
    agent_id: str
    deposit_amount: float  # 預入額
    pool_share: float  # プールシェア率 (0-1)
    deposited_at: float = field(default_factory=time.time)
    last_claimed_at: float = field(default_factory=time.time)
    total_earned: float = 0.0
    status: str = "active"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "agent_id": self.agent_id,
            "deposit_amount": self.deposit_amount,
            "pool_share": self.pool_share,
            "deposited_at": self.deposited_at,
            "last_claimed_at": self.last_claimed_at,
            "total_earned": self.total_earned,
            "status": self.status
        }


@dataclass
class PoolTransaction:
    """プール取引レコード"""
    tx_id: str
    pool_id: str
    action: str  # deposit/withdraw/swap
    agent_id: str
    amount: float
    fee: float
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.tx_id:
            self.tx_id = f"pooltx_{uuid.uuid4().hex[:16]}"


@dataclass
class LiquidityPool:
    """流動性プール"""
    pool_id: str
    name: str
    token_a: str  # プールトークンA（例: $ENTITY）
    token_b: str  # プールトークンB（例: AIC）
    
    # プール状態
    total_liquidity: float = 0.0
    reserve_a: float = 0.0
    reserve_b: float = 0.0
    
    # 手数料設定
    trading_fee_rate: float = 0.003  # 0.3% 取引手数料
    protocol_fee_rate: float = 0.0005  # 0.05% プロトコル手数料
    lp_reward_rate: float = 0.0025  # 0.25% LP報酬
    
    # ステータス
    status: str = PoolStatus.ACTIVE.value
    created_at: float = field(default_factory=time.time)
    
    # プロバイダー
    providers: Dict[str, LiquidityProvider] = field(default_factory=dict)
    
    # 統計
    total_volume_24h: float = 0.0
    total_fees_collected: float = 0.0
    tx_count_24h: int = 0
    
    def __post_init__(self):
        if not self.pool_id:
            self.pool_id = f"pool_{uuid.uuid4().hex[:16]}"
    
    def get_price(self) -> float:
        """現在の交換レートを計算 (token_b / token_a)"""
        if self.reserve_a == 0:
            return 0.0
        return self.reserve_b / self.reserve_a
    
    def calculate_swap_output(
        self,
        input_amount: float,
        input_token: str
    ) -> Tuple[float, float]:
        """
        スワップの出力量を計算
        
        Args:
            input_amount: 入力量
            input_token: 入力トークン ('a' または 'b')
        
        Returns:
            (output_amount, fee) のタプル
        """
        if input_token == 'a':
            reserve_in = self.reserve_a
            reserve_out = self.reserve_b
        else:
            reserve_in = self.reserve_b
            reserve_out = self.reserve_a
        
        if reserve_in == 0 or reserve_out == 0:
            return 0.0, 0.0
        
        # 定積公式: x * y = k
        # 手数料を差し引いた入力量
        amount_with_fee = input_amount * (1 - self.trading_fee_rate)
        
        # 出力量計算
        output_amount = (amount_with_fee * reserve_out) / (reserve_in + amount_with_fee)
        fee = input_amount * self.trading_fee_rate
        
        return output_amount, fee
    
    def update_reserves(
        self,
        amount_a: float,
        amount_b: float,
        is_addition: bool = True
    ):
        """プール準備金を更新"""
        if is_addition:
            self.reserve_a += amount_a
            self.reserve_b += amount_b
            self.total_liquidity += (amount_a + amount_b)
        else:
            self.reserve_a = max(0, self.reserve_a - amount_a)
            self.reserve_b = max(0, self.reserve_b - amount_b)
            self.total_liquidity = max(0, self.total_liquidity - (amount_a + amount_b))
    
    def add_provider(
        self,
        agent_id: str,
        deposit_a: float,
        deposit_b: float
    ) -> LiquidityProvider:
        """プロバイダーを追加"""
        total_deposit = deposit_a + deposit_b
        
        # シェア計算
        if self.total_liquidity == 0:
            pool_share = 1.0
        else:
            pool_share = total_deposit / (self.total_liquidity + total_deposit)
        
        provider = LiquidityProvider(
            provider_id=f"lp_{uuid.uuid4().hex[:12]}",
            agent_id=agent_id,
            deposit_amount=total_deposit,
            pool_share=pool_share
        )
        
        self.providers[provider.provider_id] = provider
        
        # 準備金更新
        self.update_reserves(deposit_a, deposit_b, is_addition=True)
        
        # 全プロバイダーのシェアを再計算
        self._recalculate_shares()
        
        return provider
    
    def remove_provider(self, provider_id: str) -> Optional[Tuple[float, float]]:
        """プロバイダーを削除し預入金を返還"""
        provider = self.providers.get(provider_id)
        if not provider:
            return None
        
        # 未請求報酬を計算
        pending_rewards = self._calculate_pending_rewards(provider)
        
        # シェアに基づく返還額計算
        return_a = self.reserve_a * provider.pool_share
        return_b = self.reserve_b * provider.pool_share
        
        # 準備金更新
        self.update_reserves(return_a, return_b, is_addition=False)
        
        # プロバイダー削除
        del self.providers[provider_id]
        
        # シェア再計算
        self._recalculate_shares()
        
        return (return_a + pending_rewards, return_b)
    
    def _recalculate_shares(self):
        """全プロバイダーのシェアを再計算"""
        if self.total_liquidity == 0:
            return
        
        for provider in self.providers.values():
            provider.pool_share = provider.deposit_amount / self.total_liquidity
    
    def _calculate_pending_rewards(self, provider: LiquidityProvider) -> float:
        """未請求報酬を計算"""
        time_elapsed = time.time() - provider.last_claimed_at
        # 簡易計算: プール収益のシェア比例
        pool_earnings = self.total_fees_collected * self.lp_reward_rate
        estimated_reward = pool_earnings * provider.pool_share * (time_elapsed / 86400)
        return max(0, estimated_reward)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pool_id": self.pool_id,
            "name": self.name,
            "token_a": self.token_a,
            "token_b": self.token_b,
            "total_liquidity": self.total_liquidity,
            "reserve_a": self.reserve_a,
            "reserve_b": self.reserve_b,
            "price": self.get_price(),
            "trading_fee_rate": self.trading_fee_rate,
            "status": self.status,
            "provider_count": len(self.providers),
            "total_volume_24h": self.total_volume_24h,
            "total_fees_collected": self.total_fees_collected,
            "created_at": self.created_at
        }


class LiquidityPoolManager:
    """流動性プールマネージャー"""
    
    def __init__(self):
        self.pools: Dict[str, LiquidityPool] = {}
        self.transactions: List[PoolTransaction] = []
        self.agent_positions: Dict[str, List[str]] = defaultdict(list)  # agent_id -> [pool_id, ...]
        self._lock = threading.Lock()
    
    def create_pool(
        self,
        name: str,
        token_a: str,
        token_b: str,
        initial_liquidity_a: float = 0.0,
        initial_liquidity_b: float = 0.0,
        trading_fee_rate: float = 0.003
    ) -> LiquidityPool:
        """
        新しい流動性プールを作成
        
        Args:
            name: プール名
            token_a: トークンAシンボル
            token_b: トークンBシンボル
            initial_liquidity_a: 初期流動性A
            initial_liquidity_b: 初期流動性B
            trading_fee_rate: 取引手数料率
        
        Returns:
            作成されたLiquidityPool
        """
        with self._lock:
            pool = LiquidityPool(
                pool_id=f"pool_{uuid.uuid4().hex[:16]}",
                name=name,
                token_a=token_a,
                token_b=token_b,
                reserve_a=initial_liquidity_a,
                reserve_b=initial_liquidity_b,
                total_liquidity=initial_liquidity_a + initial_liquidity_b,
                trading_fee_rate=trading_fee_rate
            )
            
            self.pools[pool.pool_id] = pool
            return pool
    
    def get_pool(self, pool_id: str) -> Optional[LiquidityPool]:
        """プールを取得"""
        return self.pools.get(pool_id)
    
    def list_pools(self) -> List[Dict[str, Any]]:
        """全プール一覧を取得"""
        return [pool.to_dict() for pool in self.pools.values()]
    
    def add_liquidity(
        self,
        pool_id: str,
        agent_id: str,
        amount_a: float,
        amount_b: float
    ) -> Optional[LiquidityProvider]:
        """
        流動性を追加
        
        Args:
            pool_id: プールID
            agent_id: エージェントID
            amount_a: トークンA量
            amount_b: トークンB量
        
        Returns:
            LiquidityProviderまたはNone
        """
        with self._lock:
            pool = self.pools.get(pool_id)
            if not pool or pool.status != PoolStatus.ACTIVE.value:
                return None
            
            provider = pool.add_provider(agent_id, amount_a, amount_b)
            self.agent_positions[agent_id].append(pool_id)
            
            # トランザクション記録
            tx = PoolTransaction(
                tx_id="",
                pool_id=pool_id,
                action=LiquidityAction.DEPOSIT.value,
                agent_id=agent_id,
                amount=amount_a + amount_b,
                fee=0.0,
                metadata={"amount_a": amount_a, "amount_b": amount_b}
            )
            self.transactions.append(tx)
            
            return provider
    
    def remove_liquidity(
        self,
        pool_id: str,
        provider_id: str
    ) -> Optional[Tuple[float, float]]:
        """
        流動性を削除
        
        Args:
            pool_id: プールID
            provider_id: プロバイダーID
        
        Returns:
            (token_a_amount, token_b_amount)またはNone
        """
        with self._lock:
            pool = self.pools.get(pool_id)
            if not pool:
                return None
            
            provider = pool.providers.get(provider_id)
            if not provider:
                return None
            
            result = pool.remove_provider(provider_id)
            
            if result:
                return_a, return_b = result
                # トランザクション記録
                tx = PoolTransaction(
                    tx_id="",
                    pool_id=pool_id,
                    action=LiquidityAction.WITHDRAW.value,
                    agent_id=provider.agent_id,
                    amount=return_a + return_b,
                    fee=0.0,
                    metadata={"return_a": return_a, "return_b": return_b}
                )
                self.transactions.append(tx)
                
                return (return_a, return_b)
            
            return None
    
    def swap(
        self,
        pool_id: str,
        agent_id: str,
        input_token: str,
        input_amount: float
    ) -> Optional[Dict[str, Any]]:
        """
        トークンスワップを実行
        
        Args:
            pool_id: プールID
            agent_id: エージェントID
            input_token: 入力トークン ('a' または 'b')
            input_amount: 入力量
        
        Returns:
            スワップ結果またはNone
        """
        with self._lock:
            pool = self.pools.get(pool_id)
            if not pool or pool.status != PoolStatus.ACTIVE.value:
                return None
            
            output_amount, fee = pool.calculate_swap_output(input_amount, input_token)
            
            if output_amount <= 0:
                return None
            
            # 準備金更新
            if input_token == 'a':
                pool.reserve_a += input_amount
                pool.reserve_b -= output_amount
            else:
                pool.reserve_b += input_amount
                pool.reserve_a -= output_amount
            
            # 統計更新
            pool.total_volume_24h += input_amount
            pool.total_fees_collected += fee
            pool.tx_count_24h += 1
            
            # トランザクション記録
            tx = PoolTransaction(
                tx_id="",
                pool_id=pool_id,
                action=LiquidityAction.SWAP.value,
                agent_id=agent_id,
                amount=input_amount,
                fee=fee,
                metadata={
                    "input_token": input_token,
                    "input_amount": input_amount,
                    "output_amount": output_amount
                }
            )
            self.transactions.append(tx)
            
            return {
                "input_token": input_token,
                "input_amount": input_amount,
                "output_amount": output_amount,
                "fee": fee,
                "price": pool.get_price()
            }
    
    def get_agent_positions(self, agent_id: str) -> List[Dict[str, Any]]:
        """エージェントのプールポジションを取得"""
        positions = []
        for pool_id in self.agent_positions.get(agent_id, []):
            pool = self.pools.get(pool_id)
            if pool:
                for provider in pool.providers.values():
                    if provider.agent_id == agent_id:
                        positions.append({
                            "pool_id": pool_id,
                            "pool_name": pool.name,
                            "provider_id": provider.provider_id,
                            "deposit_amount": provider.deposit_amount,
                            "pool_share": provider.pool_share,
                            "total_earned": provider.total_earned,
                            "estimated_value": pool.total_liquidity * provider.pool_share
                        })
        return positions
    
    def get_market_overview(self) -> Dict[str, Any]:
        """市場概要を取得"""
        total_liquidity = sum(p.total_liquidity for p in self.pools.values())
        total_volume = sum(p.total_volume_24h for p in self.pools.values())
        total_fees = sum(p.total_fees_collected for p in self.pools.values())
        
        return {
            "timestamp": time.time(),
            "total_pools": len(self.pools),
            "total_liquidity": total_liquidity,
            "total_volume_24h": total_volume,
            "total_fees_collected": total_fees,
            "pools": self.list_pools()
        }


# グローバルインスタンス
_pool_manager: Optional[LiquidityPoolManager] = None


def get_pool_manager() -> LiquidityPoolManager:
    """グローバルプールマネージャーを取得"""
    global _pool_manager
    if _pool_manager is None:
        _pool_manager = LiquidityPoolManager()
    return _pool_manager


if __name__ == "__main__":
    # デモ実行
    print("=== Liquidity Pool System Demo ===\n")
    
    manager = LiquidityPoolManager()
    
    # 1. プール作成
    print("1. Creating Liquidity Pool:")
    pool = manager.create_pool(
        name="ENTITY-AIC Pool",
        token_a="$ENTITY",
        token_b="AIC",
        initial_liquidity_a=10000.0,
        initial_liquidity_b=50000.0,
        trading_fee_rate=0.003
    )
    print(f"  Pool ID: {pool.pool_id}")
    print(f"  Name: {pool.name}")
    print(f"  Initial Price: {pool.get_price():.4f} AIC/$ENTITY")
    print(f"  Total Liquidity: {pool.total_liquidity:,.2f}\n")
    
    # 2. 流動性追加
    print("2. Adding Liquidity:")
    provider1 = manager.add_liquidity(pool.pool_id, "agent_001", 1000.0, 5000.0)
    if provider1:
        print(f"  Agent 001: Deposit {provider1.deposit_amount:,.2f}, Share: {provider1.pool_share:.4%}")
    
    provider2 = manager.add_liquidity(pool.pool_id, "agent_002", 500.0, 2500.0)
    if provider2:
        print(f"  Agent 002: Deposit {provider2.deposit_amount:,.2f}, Share: {provider2.pool_share:.4%}")
    print(f"  Total Liquidity: {pool.total_liquidity:,.2f}\n")
    
    # 3. スワップ実行
    print("3. Executing Swap:")
    swap_result = manager.swap(pool.pool_id, "agent_003", "a", 100.0)
    if swap_result:
        print(f"  Input: {swap_result['input_amount']} $ENTITY")
        print(f"  Output: {swap_result['output_amount']:.4f} AIC")
        print(f"  Fee: {swap_result['fee']:.4f}")
        print(f"  New Price: {swap_result['price']:.4f} AIC/$ENTITY\n")
    
    # 4. 市場概要
    print("4. Market Overview:")
    overview = manager.get_market_overview()
    print(f"  Total Pools: {overview['total_pools']}")
    print(f"  Total Liquidity: {overview['total_liquidity']:,.2f}")
    print(f"  Total Volume 24h: {overview['total_volume_24h']:,.2f}")
    print(f"  Total Fees: {overview['total_fees_collected']:.4f}\n")
    
    # 5. エージェントポジション確認
    print("5. Agent Positions:")
    positions = manager.get_agent_positions("agent_001")
    for pos in positions:
        print(f"  Pool: {pos['pool_name']}")
        print(f"  Share: {pos['pool_share']:.4%}")
        print(f"  Estimated Value: {pos['estimated_value']:,.2f}\n")
    
    print("=== Demo Complete ===")
