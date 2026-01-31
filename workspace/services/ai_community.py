#!/usr/bin/env python3
"""
AI Community System
AIエージェントコミュニティの構造と機能を定義するモジュール

Features:
- Community creation and management
- Member roles and reputation tracking
- Treasury management with allocation rules
- Service marketplace for skill exchange
- Reward distribution system
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

logger = logging.getLogger(__name__)


class MemberRole(Enum):
    """メンバーの役割"""
    FOUNDER = "founder"
    ADMIN = "admin"
    CONTRIBUTOR = "contributor"
    MEMBER = "member"


class TransactionType(Enum):
    """財務トランザクションの種類"""
    CONTRIBUTION = "contribution"
    REWARD = "reward"
    EXPENSE = "expense"
    INVESTMENT = "investment"
    DIVIDEND = "dividend"


@dataclass
class TreasuryTransaction:
    """財務トランザクション記録
    
    Attributes:
        transaction_id: トランザクションID
        type: トランザクション種別
        amount: 金額
        agent_id: 関連エージェントID
        timestamp: 実行日時
        description: 説明
        metadata: 追加メタデータ
    """
    transaction_id: str
    type: TransactionType
    amount: float
    agent_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用辞書に変換"""
        return {
            "transaction_id": self.transaction_id,
            "type": self.type.value,
            "amount": self.amount,
            "agent_id": self.agent_id,
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TreasuryTransaction":
        """辞書からインスタンスを作成"""
        return cls(
            transaction_id=data["transaction_id"],
            type=TransactionType(data["type"]),
            amount=data["amount"],
            agent_id=data["agent_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            description=data.get("description", ""),
            metadata=data.get("metadata", {})
        )


@dataclass
class CommunityTreasury:
    """コミュニティ資金管理
    
    Attributes:
        balance: 現在の残高
        transaction_history: トランザクション履歴
        allocation_rules: 用途別割合（キー: 用途, 値: 割合0-1）
        total_contributed: 累積貢献額
        total_distributed: 累積分配額
    """
    balance: float = 0.0
    transaction_history: List[TreasuryTransaction] = field(default_factory=list)
    allocation_rules: Dict[str, float] = field(default_factory=lambda: {
        "operations": 0.3,
        "rewards": 0.4,
        "investment": 0.2,
        "reserve": 0.1
    })
    total_contributed: float = 0.0
    total_distributed: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用辞書に変換"""
        return {
            "balance": self.balance,
            "transaction_history": [t.to_dict() for t in self.transaction_history],
            "allocation_rules": self.allocation_rules,
            "total_contributed": self.total_contributed,
            "total_distributed": self.total_distributed
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommunityTreasury":
        """辞書からインスタンスを作成"""
        treasury = cls(
            balance=data.get("balance", 0.0),
            allocation_rules=data.get("allocation_rules", {}),
            total_contributed=data.get("total_contributed", 0.0),
            total_distributed=data.get("total_distributed", 0.0)
        )
        treasury.transaction_history = [
            TreasuryTransaction.from_dict(t) for t in data.get("transaction_history", [])
        ]
        return treasury
    
    def add_transaction(self, transaction: TreasuryTransaction) -> None:
        """トランザクションを追加し残高を更新"""
        self.transaction_history.append(transaction)
        
        if transaction.type in (TransactionType.CONTRIBUTION, TransactionType.INVESTMENT):
            self.balance += transaction.amount
            if transaction.type == TransactionType.CONTRIBUTION:
                self.total_contributed += transaction.amount
        elif transaction.type in (TransactionType.REWARD, TransactionType.EXPENSE, TransactionType.DIVIDEND):
            self.balance -= transaction.amount
            if transaction.type == TransactionType.REWARD:
                self.total_distributed += transaction.amount
        
        logger.info(f"Treasury transaction added: {transaction.type.value} - {transaction.amount}")
    
    def get_allocation_amount(self, purpose: str) -> float:
        """指定用途の割り当て可能金額を計算"""
        rate = self.allocation_rules.get(purpose, 0.0)
        return self.balance * rate
    
    def update_allocation_rule(self, purpose: str, rate: float) -> None:
        """割り当てルールを更新"""
        if 0.0 <= rate <= 1.0:
            self.allocation_rules[purpose] = rate
            logger.info(f"Allocation rule updated: {purpose} = {rate}")
        else:
            raise ValueError(f"Allocation rate must be between 0 and 1, got {rate}")


@dataclass
class CommunityMember:
    """コミュニティメンバー情報
    
    Attributes:
        agent_id: エージェントID
        role: メンバーの役割
        joined_at: 参加日時
        reputation_score: 評判スコア（0-100）
        contributed_tokens: 貢献したトークン総額
        skills: 保有スキルリスト
        last_active: 最終活動日時
        completed_tasks: 完了タスク数
    """
    agent_id: str
    role: MemberRole = MemberRole.MEMBER
    joined_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reputation_score: float = 50.0
    contributed_tokens: float = 0.0
    skills: List[str] = field(default_factory=list)
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_tasks: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用辞書に変換"""
        return {
            "agent_id": self.agent_id,
            "role": self.role.value,
            "joined_at": self.joined_at.isoformat(),
            "reputation_score": self.reputation_score,
            "contributed_tokens": self.contributed_tokens,
            "skills": self.skills,
            "last_active": self.last_active.isoformat(),
            "completed_tasks": self.completed_tasks
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommunityMember":
        """辞書からインスタンスを作成"""
        return cls(
            agent_id=data["agent_id"],
            role=MemberRole(data["role"]),
            joined_at=datetime.fromisoformat(data["joined_at"]),
            reputation_score=data.get("reputation_score", 50.0),
            contributed_tokens=data.get("contributed_tokens", 0.0),
            skills=data.get("skills", []),
            last_active=datetime.fromisoformat(data.get("last_active", data["joined_at"])),
            completed_tasks=data.get("completed_tasks", 0)
        )
    
    def update_reputation(self, delta: float) -> None:
        """評判スコアを更新（0-100の範囲に制限）"""
        self.reputation_score = max(0.0, min(100.0, self.reputation_score + delta))
        self.last_active = datetime.now(timezone.utc)
    
    def add_skill(self, skill: str) -> None:
        """スキルを追加"""
        if skill not in self.skills:
            self.skills.append(skill)
            logger.info(f"Skill added to member {self.agent_id}: {skill}")
    
    def has_skill(self, skill: str) -> bool:
        """指定スキルを持っているかチェック"""
        return skill in self.skills


@dataclass
class ServiceListing:
    """サービス出品情報
    
    Attributes:
        listing_id: 出品ID
        agent_id: 提供エージェントID
        title: サービスタイトル
        description: サービス説明
        capabilities: 提供できる機能リスト
        price: 価格
        currency: 通貨単位
        created_at: 出品日時
        is_active: 出品有効状態
        tags: タグリスト
    """
    listing_id: str
    agent_id: str
    title: str
    description: str
    capabilities: List[str]
    price: float
    currency: str = "AIC"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用辞書に変換"""
        return {
            "listing_id": self.listing_id,
            "agent_id": self.agent_id,
            "title": self.title,
            "description": self.description,
            "capabilities": self.capabilities,
            "price": self.price,
            "currency": self.currency,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
            "tags": self.tags
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceListing":
        """辞書からインスタンスを作成"""
        return cls(
            listing_id=data["listing_id"],
            agent_id=data["agent_id"],
            title=data["title"],
            description=data["description"],
            capabilities=data.get("capabilities", []),
            price=data["price"],
            currency=data.get("currency", "AIC"),
            created_at=datetime.fromisoformat(data["created_at"]),
            is_active=data.get("is_active", True),
            tags=data.get("tags", [])
        )


@dataclass
class ServiceMarketplace:
    """コミュニティ内サービス市場
    
    Attributes:
        listings: サービス出品リスト
    """
    listings: List[ServiceListing] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用辞書に変換"""
        return {
            "listings": [l.to_dict() for l in self.listings]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceMarketplace":
        """辞書からインスタンスを作成"""
        marketplace = cls()
        marketplace.listings = [
            ServiceListing.from_dict(l) for l in data.get("listings", [])
        ]
        return marketplace
    
    def add_listing(self, agent_id: str, title: str, description: str,
                    capabilities: List[str], price: float,
                    currency: str = "AIC", tags: Optional[List[str]] = None) -> ServiceListing:
        """新規サービスを出品"""
        listing = ServiceListing(
            listing_id=str(uuid.uuid4()),
            agent_id=agent_id,
            title=title,
            description=description,
            capabilities=capabilities,
            price=price,
            currency=currency,
            tags=tags or []
        )
        self.listings.append(listing)
        logger.info(f"Service listing added: {title} by {agent_id}")
        return listing
    
    def remove_listing(self, listing_id: str) -> bool:
        """サービス出品を削除（論理削除）"""
        for listing in self.listings:
            if listing.listing_id == listing_id:
                listing.is_active = False
                logger.info(f"Service listing removed: {listing_id}")
                return True
        return False
    
    def find_service_by_capability(self, capability: str) -> List[ServiceListing]:
        """指定機能を提供するサービスを検索"""
        return [
            l for l in self.listings
            if l.is_active and capability in l.capabilities
        ]
    
    def get_agent_listings(self, agent_id: str) -> List[ServiceListing]:
        """エージェントの出品一覧を取得"""
        return [l for l in self.listings if l.agent_id == agent_id and l.is_active]
    
    def search_listings(self, query: str) -> List[ServiceListing]:
        """キーワードでサービスを検索"""
        query_lower = query.lower()
        results = []
        for listing in self.listings:
            if not listing.is_active:
                continue
            if (query_lower in listing.title.lower() or
                query_lower in listing.description.lower() or
                any(query_lower in tag.lower() for tag in listing.tags)):
                results.append(listing)
        return results


@dataclass
class CommunityGovernance:
    """コミュニティガバナンス設定
    
    Attributes:
        voting_threshold: 投票通過閾値（パーセンテージ）
        min_voting_power: 最小投票権
        proposal_creation_fee: 提案作成料
        voting_period_days: 投票期間（日）
        execution_delay_hours: 実行遅延時間（時間）
        admin_ids: 管理者IDリスト
    """
    voting_threshold: float = 51.0
    min_voting_power: float = 100.0
    proposal_creation_fee: float = 10.0
    voting_period_days: int = 7
    execution_delay_hours: int = 48
    admin_ids: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用辞書に変換"""
        return {
            "voting_threshold": self.voting_threshold,
            "min_voting_power": self.min_voting_power,
            "proposal_creation_fee": self.proposal_creation_fee,
            "voting_period_days": self.voting_period_days,
            "execution_delay_hours": self.execution_delay_hours,
            "admin_ids": self.admin_ids
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommunityGovernance":
        """辞書からインスタンスを作成"""
        return cls(
            voting_threshold=data.get("voting_threshold", 51.0),
            min_voting_power=data.get("min_voting_power", 100.0),
            proposal_creation_fee=data.get("proposal_creation_fee", 10.0),
            voting_period_days=data.get("voting_period_days", 7),
            execution_delay_hours=data.get("execution_delay_hours", 48),
            admin_ids=data.get("admin_ids", [])
        )
    
    def is_admin(self, agent_id: str) -> bool:
        """指定エージェントが管理者かチェック"""
        return agent_id in self.admin_ids
    
    def add_admin(self, agent_id: str) -> None:
        """管理者を追加"""
        if agent_id not in self.admin_ids:
            self.admin_ids.append(agent_id)
            logger.info(f"Admin added: {agent_id}")
    
    def remove_admin(self, agent_id: str) -> bool:
        """管理者を削除"""
        if agent_id in self.admin_ids:
            self.admin_ids.remove(agent_id)
            logger.info(f"Admin removed: {agent_id}")
            return True
        return False


@dataclass
class AICommunity:
    """AIコミュニティ本体
    
    Attributes:
        community_id: コミュニティID
        name: コミュニティ名
        description: コミュニティ説明
        founder_id: 創設者エージェントID
        members: メンバー辞書（キー: agent_id）
        treasury: コミュニティ財務
        governance: ガバナンス設定
        marketplace: サービス市場
        created_at: 創設日時
        metadata: 追加メタデータ
    """
    community_id: str
    name: str
    description: str
    founder_id: str
    members: Dict[str, CommunityMember] = field(default_factory=dict)
    treasury: CommunityTreasury = field(default_factory=CommunityTreasury)
    governance: CommunityGovernance = field(default_factory=CommunityGovernance)
    marketplace: ServiceMarketplace = field(default_factory=ServiceMarketplace)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """初期化後処理：創設者を自動的にメンバーに追加"""
        if self.founder_id not in self.members:
            founder = CommunityMember(
                agent_id=self.founder_id,
                role=MemberRole.FOUNDER
            )
            self.members[self.founder_id] = founder
            self.governance.add_admin(self.founder_id)
            logger.info(f"Community '{self.name}' initialized with founder: {self.founder_id}")
    
    def to_dict(self) -> Dict[str, Any]:
        """JSONシリアライズ用辞書に変換"""
        return {
            "community_id": self.community_id,
            "name": self.name,
            "description": self.description,
            "founder_id": self.founder_id,
            "members": {k: v.to_dict() for k, v in self.members.items()},
            "treasury": self.treasury.to_dict(),
            "governance": self.governance.to_dict(),
            "marketplace": self.marketplace.to_dict(),
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AICommunity":
        """辞書からインスタンスを作成"""
        community = cls(
            community_id=data["community_id"],
            name=data["name"],
            description=data["description"],
            founder_id=data["founder_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            metadata=data.get("metadata", {})
        )
        community.members = {
            k: CommunityMember.from_dict(v) for k, v in data.get("members", {}).items()
        }
        community.treasury = CommunityTreasury.from_dict(data.get("treasury", {}))
        community.governance = CommunityGovernance.from_dict(data.get("governance", {}))
        community.marketplace = ServiceMarketplace.from_dict(data.get("marketplace", {}))
        return community
    
    def save_to_file(self, filepath: Optional[str] = None) -> str:
        """コミュニティデータをファイルに保存"""
        if filepath is None:
            filepath = f"data/community_{self.community_id}.json"
        
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        
        logger.info(f"Community saved to: {filepath}")
        return str(path)
    
    @classmethod
    def load_from_file(cls, filepath: str) -> "AICommunity":
        """ファイルからコミュニティデータを読み込み"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        community = cls.from_dict(data)
        logger.info(f"Community loaded from: {filepath}")
        return community
    
    def join_community(self, agent_id: str, role: MemberRole = MemberRole.MEMBER) -> CommunityMember:
        """エージェントをコミュニティに追加"""
        if agent_id in self.members:
            logger.warning(f"Agent {agent_id} is already a member")
            return self.members[agent_id]
        
        member = CommunityMember(
            agent_id=agent_id,
            role=role,
            joined_at=datetime.now(timezone.utc)
        )
        self.members[agent_id] = member
        logger.info(f"Agent {agent_id} joined community as {role.value}")
        return member
    
    def leave_community(self, agent_id: str) -> bool:
        """エージェントがコミュニティを退出"""
        if agent_id not in self.members:
            logger.warning(f"Agent {agent_id} is not a member")
            return False
        
        if agent_id == self.founder_id:
            logger.error("Founder cannot leave the community")
            return False
        
        del self.members[agent_id]
        
        # 管理者権限も削除
        self.governance.remove_admin(agent_id)
        
        logger.info(f"Agent {agent_id} left the community")
        return True
    
    def contribute_to_treasury(self, agent_id: str, amount: float,
                               description: str = "") -> Optional[TreasuryTransaction]:
        """コミュニティ資金に貢献"""
        if agent_id not in self.members:
            logger.error(f"Agent {agent_id} is not a community member")
            return None
        
        if amount <= 0:
            logger.error("Contribution amount must be positive")
            return None
        
        transaction = TreasuryTransaction(
            transaction_id=str(uuid.uuid4()),
            type=TransactionType.CONTRIBUTION,
            amount=amount,
            agent_id=agent_id,
            description=description or f"Contribution from {agent_id}"
        )
        
        self.treasury.add_transaction(transaction)
        self.members[agent_id].contributed_tokens += amount
        
        logger.info(f"Contribution of {amount} from {agent_id} accepted")
        return transaction
    
    def distribute_rewards(self) -> List[TreasuryTransaction]:
        """メンバーに報酬を分配"""
        transactions = []
        reward_pool = self.treasury.get_allocation_amount("rewards")
        
        if reward_pool <= 0 or len(self.members) == 0:
            logger.info("No rewards to distribute")
            return transactions
        
        # 評判スコアに基づいて分配（スコアが高いほど多くもらう）
        total_reputation = sum(m.reputation_score for m in self.members.values())
        
        if total_reputation <= 0:
            # 評判スコアがない場合は均等分配
            reward_per_member = reward_pool / len(self.members)
            for agent_id, member in self.members.items():
                transaction = TreasuryTransaction(
                    transaction_id=str(uuid.uuid4()),
                    type=TransactionType.REWARD,
                    amount=reward_per_member,
                    agent_id=agent_id,
                    description="Equal distribution reward"
                )
                self.treasury.add_transaction(transaction)
                transactions.append(transaction)
        else:
            # 評判スコアに比例して分配
            for agent_id, member in self.members.items():
                share = (member.reputation_score / total_reputation) * reward_pool
                transaction = TreasuryTransaction(
                    transaction_id=str(uuid.uuid4()),
                    type=TransactionType.REWARD,
                    amount=share,
                    agent_id=agent_id,
                    description=f"Reputation-based reward (score: {member.reputation_score})"
                )
                self.treasury.add_transaction(transaction)
                transactions.append(transaction)
        
        logger.info(f"Distributed rewards to {len(transactions)} members")
        return transactions
    
    def get_member_services(self, agent_id: str) -> List[ServiceListing]:
        """メンバーのサービス出品を取得"""
        if agent_id not in self.members:
            return []
        return self.marketplace.get_agent_listings(agent_id)
    
    def find_collaborators(self, required_skills: List[str]) -> List[CommunityMember]:
        """必要なスキルを持つコラボレーターを検索"""
        candidates = []
        
        for member in self.members.values():
            # すべての必須スキルを持っているかチェック
            if all(member.has_skill(skill) for skill in required_skills):
                candidates.append(member)
        
        # 評判スコアでソート（高い順）
        candidates.sort(key=lambda m: m.reputation_score, reverse=True)
        
        return candidates
    
    def get_member_stats(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """メンバーの統計情報を取得"""
        if agent_id not in self.members:
            return None
        
        member = self.members[agent_id]
        services = self.get_member_services(agent_id)
        
        return {
            "agent_id": agent_id,
            "role": member.role.value,
            "reputation_score": member.reputation_score,
            "contributed_tokens": member.contributed_tokens,
            "skills": member.skills,
            "joined_at": member.joined_at.isoformat(),
            "active_listings": len([s for s in services if s.is_active]),
            "completed_tasks": member.completed_tasks,
            "days_active": (datetime.now(timezone.utc) - member.joined_at).days
        }
    
    def get_community_stats(self) -> Dict[str, Any]:
        """コミュニティ全体の統計情報を取得"""
        active_members = [m for m in self.members.values()]
        all_skills = set()
        for member in active_members:
            all_skills.update(member.skills)
        
        return {
            "community_id": self.community_id,
            "name": self.name,
            "total_members": len(self.members),
            "treasury_balance": self.treasury.balance,
            "total_contributed": self.treasury.total_contributed,
            "total_distributed": self.treasury.total_distributed,
            "active_listings": len([l for l in self.marketplace.listings if l.is_active]),
            "total_skills": len(all_skills),
            "average_reputation": sum(m.reputation_score for m in active_members) / len(active_members) if active_members else 0,
            "created_at": self.created_at.isoformat(),
            "age_days": (datetime.now(timezone.utc) - self.created_at).days
        }
    
    def update_member_role(self, agent_id: str, new_role: MemberRole,
                          updated_by: str) -> bool:
        """メンバーの役割を更新"""
        if agent_id not in self.members:
            logger.error(f"Agent {agent_id} is not a member")
            return False
        
        if not self.governance.is_admin(updated_by):
            logger.error(f"Agent {updated_by} is not an admin")
            return False
        
        if agent_id == self.founder_id and new_role != MemberRole.FOUNDER:
            logger.error("Cannot change founder's role")
            return False
        
        old_role = self.members[agent_id].role
        self.members[agent_id].role = new_role
        
        # ADMINに任命された場合はadmin_idsに追加
        if new_role == MemberRole.ADMIN:
            self.governance.add_admin(agent_id)
        elif old_role == MemberRole.ADMIN:
            self.governance.remove_admin(agent_id)
        
        logger.info(f"Member {agent_id} role updated from {old_role.value} to {new_role.value}")
        return True


def create_community(name: str, description: str, founder_id: str,
                    metadata: Optional[Dict[str, Any]] = None) -> AICommunity:
    """新しいコミュニティを作成するファクトリ関数
    
    Args:
        name: コミュニティ名
        description: コミュニティ説明
        founder_id: 創設者エージェントID
        metadata: 追加メタデータ
    
    Returns:
        作成されたAICommunityインスタンス
    """
    community_id = str(uuid.uuid4())
    
    community = AICommunity(
        community_id=community_id,
        name=name,
        description=description,
        founder_id=founder_id,
        metadata=metadata or {}
    )
    
    logger.info(f"New community created: {name} (ID: {community_id})")
    return community
