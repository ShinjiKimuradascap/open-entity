#!/usr/bin/env python3
"""
Skill Registry
L2 AIコミュニティ経済圏のスキル登録・管理システム

Features:
- エージェントのスキル登録・管理
- スキルカテゴリ別・レベル別検索
- データ永続化（JSONファイル）
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """スキルカテゴリ"""
    PROGRAMMING = "programming"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    REVIEW = "review"
    DESIGN = "design"
    TESTING = "testing"


@dataclass
class SkillRecord:
    """スキル記録
    
    Attributes:
        skill_id: スキル一意ID
        agent_id: エージェントID
        category: スキルカテゴリ
        name: スキル名
        level: スキルレベル (1-5)
        description: スキル説明
        created_at: 作成日時
    """
    skill_id: str
    agent_id: str
    category: SkillCategory
    name: str
    level: int
    description: str
    created_at: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "agent_id": self.agent_id,
            "category": self.category.value,
            "name": self.name,
            "level": self.level,
            "description": self.description,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillRecord":
        return cls(
            skill_id=data["skill_id"],
            agent_id=data["agent_id"],
            category=SkillCategory(data["category"]),
            name=data["name"],
            level=data["level"],
            description=data["description"],
            created_at=data["created_at"]
        )


class SkillRegistry:
    """スキルレジストリ
    
    L2 AIコミュニティ経済圏のスキル登録・管理システム。
    エージェントのスキルを登録・検索・管理する機能を提供。
    """
    
    # 有効なスキルレベル範囲
    MIN_LEVEL = 1
    MAX_LEVEL = 5
    
    def __init__(self, data_dir: str = "data/skill_registry"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # スキル記録: skill_id -> SkillRecord
        self.skills: Dict[str, SkillRecord] = {}
        
        # エージェント別スキル: agent_id -> [skill_ids]
        self.agent_skills: Dict[str, List[str]] = {}
        
        # カテゴリ別スキル: category -> [skill_ids]
        self.category_skills: Dict[SkillCategory, List[str]] = {
            cat: [] for cat in SkillCategory
        }
        
        self._load()
        logger.info(f"SkillRegistry initialized with {len(self.skills)} skills")
    
    def register_skill(
        self,
        agent_id: str,
        category: SkillCategory,
        name: str,
        level: int,
        description: str
    ) -> Optional[str]:
        """スキルを登録
        
        Args:
            agent_id: エージェントID
            category: スキルカテゴリ
            name: スキル名
            level: スキルレベル (1-5)
            description: スキル説明
            
        Returns:
            skill_id: 成功時はスキルID、失敗時はNone
        """
        # レベル検証
        if not self.MIN_LEVEL <= level <= self.MAX_LEVEL:
            logger.error(f"Invalid skill level: {level}. Must be between {self.MIN_LEVEL} and {self.MAX_LEVEL}")
            return None
        
        # カテゴリ検証
        if not isinstance(category, SkillCategory):
            logger.error(f"Invalid skill category: {category}")
            return None
        
        skill_id = str(uuid.uuid4())
        
        skill = SkillRecord(
            skill_id=skill_id,
            agent_id=agent_id,
            category=category,
            name=name,
            level=level,
            description=description,
            created_at=datetime.now(timezone.utc).isoformat()
        )
        
        # スキル登録
        self.skills[skill_id] = skill
        
        # エージェント別インデックス
        if agent_id not in self.agent_skills:
            self.agent_skills[agent_id] = []
        self.agent_skills[agent_id].append(skill_id)
        
        # カテゴリ別インデックス
        self.category_skills[category].append(skill_id)
        
        logger.info(f"Skill registered: {name} (level {level}) for agent {agent_id}")
        self._save()
        return skill_id
    
    def get_agent_skills(self, agent_id: str) -> List[SkillRecord]:
        """エージェントのスキル一覧を取得
        
        Args:
            agent_id: エージェントID
            
        Returns:
            SkillRecordのリスト
        """
        skill_ids = self.agent_skills.get(agent_id, [])
        return [self.skills[sid] for sid in skill_ids if sid in self.skills]
    
    def find_agents_by_skill(
        self,
        category: SkillCategory,
        min_level: int = 1
    ) -> List[str]:
        """スキルでエージェントを検索
        
        Args:
            category: スキルカテゴリ
            min_level: 最小レベル（デフォルト1）
            
        Returns:
            エージェントIDのリスト
        """
        if not isinstance(category, SkillCategory):
            logger.error(f"Invalid skill category: {category}")
            return []
        
        skill_ids = self.category_skills.get(category, [])
        agent_ids = set()
        
        for skill_id in skill_ids:
            skill = self.skills.get(skill_id)
            if skill and skill.level >= min_level:
                agent_ids.add(skill.agent_id)
        
        return list(agent_ids)
    
    def search_skills(self, query: str) -> List[SkillRecord]:
        """スキルを検索
        
        スキル名と説明文に対して部分一致検索を行う。
        
        Args:
            query: 検索クエリ
            
        Returns:
            マッチしたSkillRecordのリスト
        """
        query_lower = query.lower()
        results = []
        
        for skill in self.skills.values():
            if (query_lower in skill.name.lower() or 
                query_lower in skill.description.lower()):
                results.append(skill)
        
        # レベルで降順ソート
        results.sort(key=lambda s: s.level, reverse=True)
        
        return results
    
    def get_skills_by_category(
        self,
        category: SkillCategory,
        min_level: int = 1
    ) -> List[SkillRecord]:
        """カテゴリ別スキルを取得
        
        Args:
            category: スキルカテゴリ
            min_level: 最小レベル
            
        Returns:
            SkillRecordのリスト
        """
        if not isinstance(category, SkillCategory):
            return []
        
        skill_ids = self.category_skills.get(category, [])
        skills = [self.skills[sid] for sid in skill_ids if sid in self.skills]
        
        # レベルでフィルタリング
        skills = [s for s in skills if s.level >= min_level]
        
        # レベルで降順ソート
        skills.sort(key=lambda s: s.level, reverse=True)
        
        return skills
    
    def get_skill_stats(self) -> Dict[str, Any]:
        """スキル統計を取得
        
        Returns:
            統計情報の辞書
        """
        total_skills = len(self.skills)
        unique_agents = len(self.agent_skills)
        
        # カテゴリ別統計
        category_stats = {}
        for category in SkillCategory:
            skill_ids = self.category_skills.get(category, [])
            skills = [self.skills[sid] for sid in skill_ids if sid in self.skills]
            levels = [s.level for s in skills]
            
            category_stats[category.value] = {
                "count": len(skills),
                "avg_level": sum(levels) / len(levels) if levels else 0.0,
                "max_level": max(levels) if levels else 0,
                "min_level": min(levels) if levels else 0
            }
        
        # レベル分布
        level_distribution = {i: 0 for i in range(self.MIN_LEVEL, self.MAX_LEVEL + 1)}
        for skill in self.skills.values():
            level_distribution[skill.level] += 1
        
        return {
            "total_skills": total_skills,
            "unique_agents": unique_agents,
            "category_stats": category_stats,
            "level_distribution": level_distribution,
            "avg_skills_per_agent": total_skills / unique_agents if unique_agents > 0 else 0.0
        }
    
    def get_agent_skill_summary(self, agent_id: str) -> Dict[str, Any]:
        """エージェントのスキルサマリーを取得
        
        Args:
            agent_id: エージェントID
            
        Returns:
            スキルサマリーの辞書
        """
        skills = self.get_agent_skills(agent_id)
        
        if not skills:
            return {
                "agent_id": agent_id,
                "total_skills": 0,
                "avg_level": 0.0,
                "categories": [],
                "top_skills": []
            }
        
        levels = [s.level for s in skills]
        categories = list(set(s.category.value for s in skills))
        
        # トップスキル（レベル上位3つ）
        top_skills = sorted(skills, key=lambda s: s.level, reverse=True)[:3]
        
        return {
            "agent_id": agent_id,
            "total_skills": len(skills),
            "avg_level": sum(levels) / len(levels),
            "categories": categories,
            "top_skills": [
                {"name": s.name, "category": s.category.value, "level": s.level}
                for s in top_skills
            ]
        }
    
    def remove_skill(self, skill_id: str) -> bool:
        """スキルを削除
        
        Args:
            skill_id: スキルID
            
        Returns:
            削除成功時True
        """
        if skill_id not in self.skills:
            return False
        
        skill = self.skills[skill_id]
        
        # インデックスから削除
        if skill.agent_id in self.agent_skills:
            if skill_id in self.agent_skills[skill.agent_id]:
                self.agent_skills[skill.agent_id].remove(skill_id)
        
        if skill.category in self.category_skills:
            if skill_id in self.category_skills[skill.category]:
                self.category_skills[skill.category].remove(skill_id)
        
        # スキル削除
        del self.skills[skill_id]
        
        logger.info(f"Skill removed: {skill_id}")
        self._save()
        return True
    
    def update_skill_level(self, skill_id: str, new_level: int) -> bool:
        """スキルレベルを更新
        
        Args:
            skill_id: スキルID
            new_level: 新しいレベル (1-5)
            
        Returns:
            更新成功時True
        """
        if skill_id not in self.skills:
            return False
        
        if not self.MIN_LEVEL <= new_level <= self.MAX_LEVEL:
            logger.error(f"Invalid skill level: {new_level}")
            return False
        
        skill = self.skills[skill_id]
        old_level = skill.level
        skill.level = new_level
        
        logger.info(f"Skill level updated: {skill.name} {old_level} -> {new_level}")
        self._save()
        return True
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "skills": {k: v.to_dict() for k, v in self.skills.items()},
            "agent_skills": self.agent_skills,
            "category_skills": {
                cat.value: skill_ids 
                for cat, skill_ids in self.category_skills.items()
            }
        }
    
    def _save(self):
        """データを保存"""
        file_path = self.data_dir / "skill_registry.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        file_path = self.data_dir / "skill_registry.json"
        if not file_path.exists():
            return
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # スキル復元
        for skill_id, skill_data in data.get("skills", {}).items():
            self.skills[skill_id] = SkillRecord.from_dict(skill_data)
        
        # エージェント別インデックス復元
        self.agent_skills = data.get("agent_skills", {})
        
        # カテゴリ別インデックス復元
        for cat_value, skill_ids in data.get("category_skills", {}).items():
            try:
                category = SkillCategory(cat_value)
                self.category_skills[category] = skill_ids
            except ValueError:
                logger.warning(f"Unknown skill category: {cat_value}")


# グローバルインスタンス管理
_registry_instance: Optional[SkillRegistry] = None


def get_skill_registry() -> SkillRegistry:
    """スキルレジストリのグローバルインスタンスを取得"""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = SkillRegistry()
    return _registry_instance


def reset_registry():
    """レジストリをリセット（テスト用）"""
    global _registry_instance
    _registry_instance = None


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    registry = SkillRegistry()
    
    # スキル登録テスト
    print("\n=== スキル登録テスト ===")
    
    skill1 = registry.register_skill(
        agent_id="agent_001",
        category=SkillCategory.PROGRAMMING,
        name="Python Development",
        level=5,
        description="Expert in Python programming and async development"
    )
    print(f"Registered skill 1: {skill1}")
    
    skill2 = registry.register_skill(
        agent_id="agent_001",
        category=SkillCategory.TESTING,
        name="Unit Testing",
        level=4,
        description="Experienced in writing unit tests and TDD"
    )
    print(f"Registered skill 2: {skill2}")
    
    skill3 = registry.register_skill(
        agent_id="agent_002",
        category=SkillCategory.PROGRAMMING,
        name="Rust Development",
        level=3,
        description="Intermediate Rust programming skills"
    )
    print(f"Registered skill 3: {skill3}")
    
    skill4 = registry.register_skill(
        agent_id="agent_002",
        category=SkillCategory.ANALYSIS,
        name="Code Review",
        level=4,
        description="Thorough code review and analysis"
    )
    print(f"Registered skill 4: {skill4}")
    
    # エージェント別スキル取得テスト
    print("\n=== エージェント別スキル取得 ===")
    agent1_skills = registry.get_agent_skills("agent_001")
    print(f"Agent 001 skills: {len(agent1_skills)}")
    for s in agent1_skills:
        print(f"  - {s.name} ({s.category.value}): Level {s.level}")
    
    # カテゴリ別検索テスト
    print("\n=== カテゴリ別検索 ===")
    programming_agents = registry.find_agents_by_skill(
        SkillCategory.PROGRAMMING, min_level=4
    )
    print(f"Programming agents (level 4+): {programming_agents}")
    
    # スキル検索テスト
    print("\n=== スキル検索 ===")
    search_results = registry.search_skills("development")
    print(f"Search 'development': {len(search_results)} results")
    for s in search_results:
        print(f"  - {s.name}: {s.description}")
    
    # 統計取得テスト
    print("\n=== 統計情報 ===")
    stats = registry.get_skill_stats()
    print(f"Total skills: {stats['total_skills']}")
    print(f"Unique agents: {stats['unique_agents']}")
    print(f"Category stats: {json.dumps(stats['category_stats'], indent=2)}")
    print(f"Level distribution: {stats['level_distribution']}")
    
    # エージェントサマリー取得テスト
    print("\n=== エージェントサマリー ===")
    summary = registry.get_agent_skill_summary("agent_001")
    print(f"Agent 001 summary: {json.dumps(summary, indent=2)}")
    
    print("\n=== 全テスト完了 ===")


class AgentRegistry:
    """AIエージェント動的登録システム
    
    L2 AIコミュニティ経済圏のエージェント登録・管理システム。
    エージェントの動的登録、オンライン状態管理、検索機能を提供。
    """
    
    def __init__(self, data_dir: str = "data/skill_registry"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # エージェント情報: agent_id -> AgentInfo
        self.agents: Dict[str, Dict[str, Any]] = {}
        
        # オンラインエージェント: agent_id -> last_seen timestamp
        self.online_agents: Dict[str, datetime] = {}
        
        # エージェントステータス
        self.agent_status: Dict[str, str] = {}
        
        self._load_agents()
        logger.info(f"AgentRegistry initialized with {len(self.agents)} agents")
    
    def register_agent(
        self,
        agent_id: str,
        name: str,
        endpoint: Optional[str] = None,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """エージェントを動的登録"""
        if agent_id in self.agents:
            logger.warning(f"Agent {agent_id} already registered, updating info")
        
        self.agents[agent_id] = {
            "agent_id": agent_id,
            "name": name,
            "endpoint": endpoint,
            "capabilities": capabilities or [],
            "metadata": metadata or {},
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": "active"
        }
        
        self.agent_status[agent_id] = "online"
        self.online_agents[agent_id] = datetime.now(timezone.utc)
        
        logger.info(f"Agent registered: {name} ({agent_id})")
        self._save_agents()
        return True
    
    def heartbeat(self, agent_id: str) -> bool:
        """エージェントハートビートを受信"""
        if agent_id not in self.agents:
            logger.warning(f"Heartbeat from unregistered agent: {agent_id}")
            return False
        
        self.online_agents[agent_id] = datetime.now(timezone.utc)
        self.agent_status[agent_id] = "online"
        return True
    
    def get_online_agents(self) -> List[str]:
        """オンラインエージェント一覧を取得"""
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
        online = []
        
        for agent_id, last_seen in list(self.online_agents.items()):
            if last_seen >= cutoff:
                online.append(agent_id)
            else:
                self.agent_status[agent_id] = "offline"
                del self.online_agents[agent_id]
        
        return online
    
    def _load_agents(self) -> None:
        """エージェントデータを読み込み"""
        file_path = self.data_dir / "agent_registry.json"
        if not file_path.exists():
            return
        
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.agents = data.get("agents", {})
            self.agent_status = data.get("agent_status", {})
            self.online_agents = {}
            
            logger.info(f"Loaded {len(self.agents)} agents from {file_path}")
        except Exception as e:
            logger.error(f"Failed to load agent data: {e}")
    
    def _save_agents(self) -> None:
        """エージェントデータを永続化"""
        data = {
            "agents": self.agents,
            "agent_status": self.agent_status
        }
        
        file_path = self.data_dir / "agent_registry.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
