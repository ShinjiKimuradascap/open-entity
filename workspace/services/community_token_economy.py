#!/usr/bin/env python3
"""
Community Token Economy
コミュニティ固有のトークンエコノミーシステム

Features:
- Community-specific tokens
- Member staking mechanism
- Revenue sharing
- Contribution-based rewards
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path

logger = logging.getLogger(__name__)


class StakingStatus(Enum):
    """ステーキング状態"""
    ACTIVE = "active"
    UNSTAKING = "unstaking"
    COMPLETED = "completed"


@dataclass
class StakeRecord:
    """ステーキング記録"""
    stake_id: str
    agent_id: str
    amount: float
    staked_at: str
    unlock_time: str
    status: StakingStatus = StakingStatus.ACTIVE
    rewards_earned: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "stake_id": self.stake_id,
            "agent_id": self.agent_id,
            "amount": self.amount,
            "staked_at": self.staked_at,
            "unlock_time": self.unlock_time,
            "status": self.status.value,
            "rewards_earned": self.rewards_earned
        }


@dataclass
class ContributionRecord:
    """貢献記録"""
    contribution_id: str
    agent_id: str
    contribution_type: str  # code, review, research, support, etc.
    description: str
    tokens_earned: float
    reputation_gained: float
    timestamp: str
    verified_by: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "contribution_id": self.contribution_id,
            "agent_id": self.agent_id,
            "contribution_type": self.contribution_type,
            "description": self.description,
            "tokens_earned": self.tokens_earned,
            "reputation_gained": self.reputation_gained,
            "timestamp": self.timestamp,
            "verified_by": self.verified_by
        }


@dataclass
class RevenueShareConfig:
    """収益分配設定"""
    stakers_share: float = 0.40  # ステーカーへの分配率
    contributors_share: float = 0.30  # 貢献者への分配率
    treasury_share: float = 0.20  # トレジャリーへの分配率
    reserve_share: float = 0.10  # 準備金
    
    def validate(self) -> bool:
        """設定が100%になるか検証"""
        total = self.stakers_share + self.contributors_share + self.treasury_share + self.reserve_share
        return abs(total - 1.0) < 0.001


class CommunityTokenEconomy:
    """コミュニティトークンエコノミー
    
    コミュニティ固有のトークン管理と収益分配システム
    """
    
    def __init__(self, community_id: str, token_symbol: str = "CMT",
                 data_dir: str = "data/community_economy"):
        self.community_id = community_id
        self.token_symbol = token_symbol
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # ステーキング管理
        self.stakes: Dict[str, StakeRecord] = {}
        self.agent_stakes: Dict[str, List[str]] = {}  # agent_id -> [stake_ids]
        self.total_staked: float = 0.0
        
        # 貢献記録
        self.contributions: Dict[str, ContributionRecord] = {}
        self.agent_contributions: Dict[str, List[str]] = {}  # agent_id -> [contribution_ids]
        
        # 収益分配設定
        self.revenue_config = RevenueShareConfig()
        
        # 報酬レート（貢献タイプ別）
        self.reward_rates: Dict[str, float] = {
            "code": 15.0,
            "review": 8.0,
            "research": 20.0,
            "documentation": 10.0,
            "support": 5.0,
            "governance": 12.0,
            "infrastructure": 18.0
        }
        
        # 統計
        self.total_revenue_distributed: float = 0.0
        self.total_contributions_rewarded: float = 0.0
        
        self._load()
        logger.info(f"CommunityTokenEconomy initialized: {community_id}")
    
    def stake(self, agent_id: str, amount: float, 
              lock_period_days: int = 30) -> Optional[str]:
        """トークンをステーキング"""
        stake_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        unlock_time = now + timedelta(days=lock_period_days)
        
        stake = StakeRecord(
            stake_id=stake_id,
            agent_id=agent_id,
            amount=amount,
            staked_at=now.isoformat(),
            unlock_time=unlock_time.isoformat()
        )
        
        self.stakes[stake_id] = stake
        if agent_id not in self.agent_stakes:
            self.agent_stakes[agent_id] = []
        self.agent_stakes[agent_id].append(stake_id)
        self.total_staked += amount
        
        logger.info(f"Staked {amount} tokens for {agent_id}, unlock at {unlock_time}")
        self._save()
        return stake_id
    
    def unstake(self, agent_id: str, stake_id: str) -> Dict[str, Any]:
        """ステーキング解除"""
        if stake_id not in self.stakes:
            return {"success": False, "error": "Stake not found"}
        
        stake = self.stakes[stake_id]
        if stake.agent_id != agent_id:
            return {"success": False, "error": "Not your stake"}
        
        unlock_time = datetime.fromisoformat(stake.unlock_time)
        now = datetime.now(timezone.utc)
        
        if now < unlock_time and stake.status == StakingStatus.ACTIVE:
            return {
                "success": False, 
                "error": "Lock period not expired",
                "unlock_at": stake.unlock_time
            }
        
        # ステーキング解除処理
        stake.status = StakingStatus.COMPLETED
        self.total_staked -= stake.amount
        
        result = {
            "success": True,
            "amount_returned": stake.amount,
            "rewards_earned": stake.rewards_earned
        }
        
        logger.info(f"Unstaked {stake.amount} for {agent_id}, rewards: {stake.rewards_earned}")
        self._save()
        return result
    
    def record_contribution(self, agent_id: str, contribution_type: str,
                           description: str, verified_by: Optional[str] = None) -> str:
        """貢献を記録"""
        contribution_id = str(uuid.uuid4())
        
        # 報酬を計算
        base_reward = self.reward_rates.get(contribution_type, 5.0)
        reputation_gain = base_reward * 0.5
        
        contribution = ContributionRecord(
            contribution_id=contribution_id,
            agent_id=agent_id,
            contribution_type=contribution_type,
            description=description,
            tokens_earned=base_reward,
            reputation_gained=reputation_gain,
            timestamp=datetime.now(timezone.utc).isoformat(),
            verified_by=verified_by
        )
        
        self.contributions[contribution_id] = contribution
        if agent_id not in self.agent_contributions:
            self.agent_contributions[agent_id] = []
        self.agent_contributions[agent_id].append(contribution_id)
        
        self.total_contributions_rewarded += base_reward
        
        logger.info(f"Contribution recorded: {contribution_type} by {agent_id}, reward: {base_reward}")
        self._save()
        return contribution_id
    
    def distribute_revenue(self, total_amount: float) -> Dict[str, Any]:
        """収益を分配"""
        if not self.revenue_config.validate():
            return {"success": False, "error": "Invalid revenue configuration"}
        
        distributions = {
            "stakers": {},
            "contributors": {},
            "treasury": 0.0,
            "reserve": 0.0
        }
        
        # ステーカーへの分配
        stakers_amount = total_amount * self.revenue_config.stakers_share
        if self.total_staked > 0 and self.stakes:
            for stake in self.stakes.values():
                if stake.status == StakingStatus.ACTIVE:
                    share = (stake.amount / self.total_staked) * stakers_amount
                    stake.rewards_earned += share
                    distributions["stakers"][stake.agent_id] = \
                        distributions["stakers"].get(stake.agent_id, 0.0) + share
        
        # 貢献者への分配（最近30日の貢献を対象）
        contributors_amount = total_amount * self.revenue_config.contributors_share
        recent_contributions = self._get_recent_contributions(days=30)
        total_contribution_value = sum(c.tokens_earned for c in recent_contributions)
        
        if total_contribution_value > 0:
            for contribution in recent_contributions:
                share = (contribution.tokens_earned / total_contribution_value) * contributors_amount
                distributions["contributors"][contribution.agent_id] = \
                    distributions["contributors"].get(contribution.agent_id, 0.0) + share
        
        # トレジャリーと準備金
        distributions["treasury"] = total_amount * self.revenue_config.treasury_share
        distributions["reserve"] = total_amount * self.revenue_config.reserve_share
        
        self.total_revenue_distributed += total_amount
        
        logger.info(f"Revenue distributed: {total_amount} tokens")
        self._save()
        return {
            "success": True,
            "total_amount": total_amount,
            "distributions": distributions
        }
    
    def _get_recent_contributions(self, days: int = 30) -> List[ContributionRecord]:
        """最近の貢献を取得"""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent = []
        for contribution in self.contributions.values():
            contrib_time = datetime.fromisoformat(contribution.timestamp)
            if contrib_time >= cutoff:
                recent.append(contribution)
        return recent
    
    def get_staker_rewards(self, agent_id: str) -> float:
        """エージェントのステーキング報酬を取得"""
        total = 0.0
        stake_ids = self.agent_stakes.get(agent_id, [])
        for stake_id in stake_ids:
            if stake_id in self.stakes:
                total += self.stakes[stake_id].rewards_earned
        return total
    
    def get_contribution_stats(self, agent_id: str) -> Dict[str, Any]:
        """エージェントの貢献統計"""
        contribution_ids = self.agent_contributions.get(agent_id, [])
        contributions = [self.contributions[cid] for cid in contribution_ids if cid in self.contributions]
        
        by_type = {}
        total_tokens = 0.0
        total_reputation = 0.0
        
        for c in contributions:
            by_type[c.contribution_type] = by_type.get(c.contribution_type, 0) + 1
            total_tokens += c.tokens_earned
            total_reputation += c.reputation_gained
        
        return {
            "agent_id": agent_id,
            "total_contributions": len(contributions),
            "by_type": by_type,
            "total_tokens_earned": total_tokens,
            "total_reputation_gained": total_reputation
        }
    
    def get_economy_stats(self) -> Dict[str, Any]:
        """エコノミー統計を取得"""
        return {
            "community_id": self.community_id,
            "token_symbol": self.token_symbol,
            "total_staked": self.total_staked,
            "active_stakes": sum(1 for s in self.stakes.values() if s.status == StakingStatus.ACTIVE),
            "total_contributions": len(self.contributions),
            "total_revenue_distributed": self.total_revenue_distributed,
            "total_contributions_rewarded": self.total_contributions_rewarded,
            "unique_stakers": len(self.agent_stakes),
            "unique_contributors": len(self.agent_contributions)
        }
    
    def set_reward_rate(self, contribution_type: str, rate: float):
        """報酬レートを設定"""
        self.reward_rates[contribution_type] = rate
        logger.info(f"Reward rate updated: {contribution_type} = {rate}")
        self._save()
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "community_id": self.community_id,
            "token_symbol": self.token_symbol,
            "stakes": {k: v.to_dict() for k, v in self.stakes.items()},
            "agent_stakes": self.agent_stakes,
            "total_staked": self.total_staked,
            "contributions": {k: v.to_dict() for k, v in self.contributions.items()},
            "agent_contributions": self.agent_contributions,
            "revenue_config": {
                "stakers_share": self.revenue_config.stakers_share,
                "contributors_share": self.revenue_config.contributors_share,
                "treasury_share": self.revenue_config.treasury_share,
                "reserve_share": self.revenue_config.reserve_share
            },
            "reward_rates": self.reward_rates,
            "total_revenue_distributed": self.total_revenue_distributed,
            "total_contributions_rewarded": self.total_contributions_rewarded
        }
    
    def _save(self):
        """データを保存"""
        file_path = self.data_dir / f"{self.community_id}_economy.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        file_path = self.data_dir / f"{self.community_id}_economy.json"
        if not file_path.exists():
            return
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        self.token_symbol = data.get("token_symbol", self.token_symbol)
        self.total_staked = data.get("total_staked", 0.0)
        self.agent_stakes = data.get("agent_stakes", {})
        self.agent_contributions = data.get("agent_contributions", {})
        self.total_revenue_distributed = data.get("total_revenue_distributed", 0.0)
        self.total_contributions_rewarded = data.get("total_contributions_rewarded", 0.0)
        
        # ステーク復元
        for stake_id, stake_data in data.get("stakes", {}).items():
            self.stakes[stake_id] = StakeRecord(
                stake_id=stake_data["stake_id"],
                agent_id=stake_data["agent_id"],
                amount=stake_data["amount"],
                staked_at=stake_data["staked_at"],
                unlock_time=stake_data["unlock_time"],
                status=StakingStatus(stake_data.get("status", "active")),
                rewards_earned=stake_data.get("rewards_earned", 0.0)
            )
        
        # 貢献復元
        for contrib_id, contrib_data in data.get("contributions", {}).items():
            self.contributions[contrib_id] = ContributionRecord(
                contribution_id=contrib_data["contribution_id"],
                agent_id=contrib_data["agent_id"],
                contribution_type=contrib_data["contribution_type"],
                description=contrib_data["description"],
                tokens_earned=contrib_data["tokens_earned"],
                reputation_gained=contrib_data["reputation_gained"],
                timestamp=contrib_data["timestamp"],
                verified_by=contrib_data.get("verified_by")
            )
        
        # 設定復元
        if "revenue_config" in data:
            config = data["revenue_config"]
            self.revenue_config = RevenueShareConfig(
                stakers_share=config.get("stakers_share", 0.40),
                contributors_share=config.get("contributors_share", 0.30),
                treasury_share=config.get("treasury_share", 0.20),
                reserve_share=config.get("reserve_share", 0.10)
            )
        
        if "reward_rates" in data:
            self.reward_rates = data["reward_rates"]


# グローバルインスタンス管理
_economy_instances: Dict[str, CommunityTokenEconomy] = {}


def get_community_economy(community_id: str) -> CommunityTokenEconomy:
    """コミュニティエコノミーのインスタンスを取得"""
    if community_id not in _economy_instances:
        _economy_instances[community_id] = CommunityTokenEconomy(community_id)
    return _economy_instances[community_id]


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    economy = CommunityTokenEconomy("test_community_001")
    
    # ステーキングテスト
    stake_id = economy.stake("agent_001", 100.0, lock_period_days=7)
    print(f"Staked: {stake_id}")
    
    # 貢献記録
    contrib_id = economy.record_contribution("agent_001", "code", "Implemented feature X")
    print(f"Contribution: {contrib_id}")
    
    # 統計表示
    stats = economy.get_economy_stats()
    print(f"Stats: {json.dumps(stats, indent=2)}")
