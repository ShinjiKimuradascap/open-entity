#!/usr/bin/env python3
"""
SKILL Token Integration
SkillRegistryとSkillTokenコントラクトの連携モジュール

Features:
- スキル登録時のトークンステーキング
- 検証者報酬分配
- スキルレベルに応じた報酬計算
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

from services.skill_registry import SkillRegistry, SkillCategory, SkillRecord

logger = logging.getLogger(__name__)


@dataclass
class SkillTokenConfig:
    """SKILLトークン設定"""
    min_stake: float = 100.0  # 100 SKILL
    level_rewards: Dict[int, float] = None
    verifier_reward_rate: float = 0.1  # 10%
    
    def __post_init__(self):
        if self.level_rewards is None:
            # レベルに応じた報酬（SKILL）
            self.level_rewards = {
                1: 50.0,
                2: 150.0,
                3: 300.0,
                4: 500.0,
                5: 1000.0
            }


class SkillTokenIntegration:
    """
    SKILLトークン統合クラス
    
    SkillRegistryのスキル登録とトークンエコノミーを連携。
    スキルの信頼性をステーキングで保証し、検証により報酬を分配。
    """
    
    def __init__(
        self,
        skill_registry: SkillRegistry,
        config: Optional[SkillTokenConfig] = None,
        data_dir: str = "data/skill_token"
    ):
        self.registry = skill_registry
        self.config = config or SkillTokenConfig()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # ステーキング情報: skill_id -> staking_info
        self.stakes: Dict[str, Dict] = {}
        # 検証者情報: agent_id -> verifier_info
        self.verifiers: Dict[str, Dict] = {}
        
        self._load_data()
    
    def _load_data(self):
        """データ読み込み"""
        stakes_file = self.data_dir / "stakes.json"
        if stakes_file.exists():
            with open(stakes_file) as f:
                self.stakes = json.load(f)
        
        verifiers_file = self.data_dir / "verifiers.json"
        if verifiers_file.exists():
            with open(verifiers_file) as f:
                self.verifiers = json.load(f)
    
    def _save_data(self):
        """データ保存"""
        with open(self.data_dir / "stakes.json", 'w') as f:
            json.dump(self.stakes, f, indent=2)
        with open(self.data_dir / "verifiers.json", 'w') as f:
            json.dump(self.verifiers, f, indent=2)
    
    def register_skill_with_stake(
        self,
        agent_id: str,
        category: SkillCategory,
        name: str,
        level: int,
        description: str,
        stake_amount: float
    ) -> Optional[str]:
        """
        スキルをステーキング付きで登録
        
        Args:
            agent_id: エージェントID
            category: スキルカテゴリ
            name: スキル名
            level: スキルレベル (1-5)
            description: スキル説明
            stake_amount: ステーキング量（SKILL）
        
        Returns:
            skill_id: 成功時、None: 失敗時
        """
        # 最小ステーキングチェック
        if stake_amount < self.config.min_stake:
            logger.warning(f"Stake {stake_amount} below minimum {self.config.min_stake}")
            return None
        
        # SkillRegistryに登録
        skill_id = self.registry.register_skill(
            agent_id=agent_id,
            category=category,
            name=name,
            level=level,
            description=description
        )
        
        if not skill_id:
            return None
        
        # ステーキング情報記録
        self.stakes[skill_id] = {
            "agent_id": agent_id,
            "amount": stake_amount,
            "staked_at": datetime.now(timezone.utc).isoformat(),
            "verified": False,
            "verifier": None,
            "verified_at": None,
            "reward_distributed": False
        }
        self._save_data()
        
        logger.info(f"Skill registered with stake: {skill_id}, amount: {stake_amount}")
        return skill_id
    
    def verify_skill(self, skill_id: str, verifier_id: str) -> bool:
        """
        スキルを検証
        
        Args:
            skill_id: スキルID
            verifier_id: 検証者エージェントID
        
        Returns:
            bool: 成功/失敗
        """
        if skill_id not in self.stakes:
            logger.warning(f"Skill not found: {skill_id}")
            return False
        
        if self.stakes[skill_id]["verified"]:
            logger.warning(f"Skill already verified: {skill_id}")
            return False
        
        # 検証者チェック
        if verifier_id not in self.verifiers:
            logger.warning(f"Verifier not registered: {verifier_id}")
            return False
        
        # 検証記録
        self.stakes[skill_id]["verified"] = True
        self.stakes[skill_id]["verifier"] = verifier_id
        self.stakes[skill_id]["verified_at"] = datetime.now(timezone.utc).isoformat()
        
        # 検証者の実績更新
        self.verifiers[verifier_id]["verified_count"] += 1
        
        self._save_data()
        logger.info(f"Skill verified: {skill_id} by {verifier_id}")
        return True
    
    def distribute_reward(self, skill_id: str) -> Dict[str, float]:
        """
        検証済みスキルに報酬を分配
        
        Returns:
            {"agent": agent_reward, "verifier": verifier_reward}
        """
        if skill_id not in self.stakes:
            return {"agent": 0.0, "verifier": 0.0}
        
        stake_info = self.stakes[skill_id]
        if not stake_info["verified"]:
            return {"agent": 0.0, "verifier": 0.0}
        
        if stake_info["reward_distributed"]:
            return {"agent": 0.0, "verifier": 0.0}
        
        # スキル情報取得
        skill = self.registry.get_skill(skill_id)
        if not skill:
            return {"agent": 0.0, "verifier": 0.0}
        
        # 報酬計算
        total_reward = self.config.level_rewards.get(skill.level, 50.0)
        verifier_reward = total_reward * self.config.verifier_reward_rate
        agent_reward = total_reward - verifier_reward
        
        # 分配済みマーク
        self.stakes[skill_id]["reward_distributed"] = True
        self._save_data()
        
        logger.info(f"Reward distributed for {skill_id}: agent={agent_reward}, verifier={verifier_reward}")
        return {
            "agent": agent_reward,
            "verifier": verifier_reward,
            "total": total_reward
        }
    
    def register_verifier(self, agent_id: str, stake_amount: float) -> bool:
        """検証者として登録"""
        if agent_id in self.verifiers:
            return False
        
        if stake_amount < self.config.min_stake:
            return False
        
        self.verifiers[agent_id] = {
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "stake_amount": stake_amount,
            "verified_count": 0,
            "reputation": 0,
            "is_active": True
        }
        self._save_data()
        logger.info(f"Verifier registered: {agent_id}")
        return True
    
    def get_verified_skills(self, agent_id: str) -> List[Dict]:
        """エージェントの検証済みスキル一覧"""
        skills = self.registry.get_agent_skills(agent_id)
        verified = []
        for skill in skills:
            if skill.skill_id in self.stakes:
                stake_info = self.stakes[skill.skill_id]
                if stake_info["verified"]:
                    verified.append({
                        "skill": skill.to_dict(),
                        "stake": stake_info
                    })
        return verified
    
    def get_reputation_score(self, agent_id: str) -> float:
        """エージェントの信頼性スコア計算"""
        skills = self.registry.get_agent_skills(agent_id)
        if not skills:
            return 0.0
        
        score = 0.0
        for skill in skills:
            if skill.skill_id in self.stakes:
                stake_info = self.stakes[skill.skill_id]
                # レベル × 検証済みボーナス × ステーク量
                base_score = skill.level * 10
                if stake_info["verified"]:
                    base_score *= 2
                score += base_score
        
        return score
    
    def get_total_staked(self) -> float:
        """総ステーキング量"""
        return sum(s["amount"] for s in self.stakes.values())