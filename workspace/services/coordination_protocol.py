"""
AI Coordination Protocol
AI間協調計画プロトコル

機能:
1. 意図共有 (Intent Sharing): 「こうしたい」という目的を共有
2. 能力表明 (Capability Advertisement): 自分が何ができるかを表明
3. 役割分担 (Role Assignment): 誰が何をするかを協議・決定
4. 計画策定 (Planning): 共同で計画を立てる
5. 実行調整 (Execution Coordination): 実行タイミングを調整

このプロトコルは「情報交換 → 役割分担 → 取引」の流れを実現する。
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Dict, List, Optional, Any, Callable, Set
from pathlib import Path

from services.l1_protocol import (
    L1Message, L1MessageType, L1Priority,
    L1TaskDelegation, L1DelegationResponse
)
from services.knowledge_sharing import (
    KnowledgeSharingSystem, KnowledgeItem, KnowledgeType
)
try:
    from services.reputation_manager import ReputationManager
except ImportError:
    ReputationManager = None

logger = logging.getLogger(__name__)


class CoordinationPhase(Enum):
    """協調フェーズ"""
    INTENT_SHARING = "intent_sharing"      # 意図共有
    CAPABILITY_DISCOVERY = "capability_discovery"  # 能力発見
    ROLE_NEGOTIATION = "role_negotiation"  # 役割交渉
    PLANNING = "planning"                  # 計画策定
    EXECUTION = "execution"                # 実行調整
    COMPLETION = "completion"              # 完了


class CoordinationMessageType(Enum):
    """協調メッセージタイプ"""
    # 意図共有
    INTENT_BROADCAST = "INTENT_BROADCAST"          # 意図の broadcast
    INTENT_RESPONSE = "INTENT_RESPONSE"            # 意図への応答
    
    # 能力表明
    CAPABILITY_ADVERTISEMENT = "CAPABILITY_ADVERTISEMENT"  # 能力表明
    CAPABILITY_QUERY = "CAPABILITY_QUERY"          # 能力照会
    CAPABILITY_RESPONSE = "CAPABILITY_RESPONSE"    # 能力応答
    
    # 役割交渉
    ROLE_PROPOSAL = "ROLE_PROPOSAL"               # 役割提案
    ROLE_ACCEPTANCE = "ROLE_ACCEPTANCE"           # 役割受諾
    ROLE_REJECTION = "ROLE_REJECTION"             # 役割拒否
    ROLE_COUNTER = "ROLE_COUNTER"                 # カウンタープロポーザル
    
    # 計画策定
    PLAN_PROPOSAL = "PLAN_PROPOSAL"               # 計画提案
    PLAN_FEEDBACK = "PLAN_FEEDBACK"               # 計画フィードバック
    PLAN_APPROVAL = "PLAN_APPROVAL"               # 計画承認
    
    # 実行調整
    EXECUTION_READY = "EXECUTION_READY"           # 実行準備完了
    EXECUTION_START = "EXECUTION_START"           # 実行開始
    EXECUTION_SYNC = "EXECUTION_SYNC"             # 実行同期
    EXECUTION_COMPLETE = "EXECUTION_COMPLETE"     # 実行完了


@dataclass
class Intent:
    """意図（Intent）
    
    「こうしたい」という目的を表現。
    例: "高性能な画像生成モデルを構築したい"
    """
    intent_id: str
    description: str
    requirements: Dict[str, Any]           # 要件
    constraints: Dict[str, Any]            # 制約
    preferred_partners: List[str]          # 希望パートナー
    exclude_partners: List[str]            # 除外パートナー
    deadline: Optional[datetime] = None
    priority: L1Priority = L1Priority.NORMAL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent_id": self.intent_id,
            "description": self.description,
            "requirements": self.requirements,
            "constraints": self.constraints,
            "preferred_partners": self.preferred_partners,
            "exclude_partners": self.exclude_partners,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "priority": self.priority.name,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class Capability:
    """能力（Capability）
    
    自分が何ができるかを表明。
    例: "画像生成モデルの学習が可能（過去に10件の実績）"
    """
    capability_id: str
    name: str
    description: str
    skill_tags: List[str]
    performance_metrics: Dict[str, float]  # 性能指標
    availability: Dict[str, Any]           # 利用可能状況
    reputation_score: float = 0.0
    past_collaborations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "name": self.name,
            "description": self.description,
            "skill_tags": self.skill_tags,
            "performance_metrics": self.performance_metrics,
            "availability": self.availability,
            "reputation_score": self.reputation_score,
            "past_collaborations": self.past_collaborations
        }


@dataclass
class Role:
    """役割（Role）
    
    協調内での役割定義。
    """
    role_id: str
    name: str
    description: str
    responsibilities: List[str]
    required_capabilities: List[str]
    assigned_to: Optional[str] = None      # 割り当てられたエージェント
    compensation: Optional[Dict[str, Any]] = None  # 報酬
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_id": self.role_id,
            "name": self.name,
            "description": self.description,
            "responsibilities": self.responsibilities,
            "required_capabilities": self.required_capabilities,
            "assigned_to": self.assigned_to,
            "compensation": self.compensation
        }


@dataclass
class CoordinationPlan:
    """協調計画
    
    複数エージェントでの共同計画。
    """
    plan_id: str
    intent: Intent
    roles: List[Role]
    timeline: Dict[str, datetime]
    dependencies: Dict[str, List[str]]     # タスク依存関係
    milestones: List[Dict[str, Any]]
    total_budget: Optional[float] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "intent": self.intent.to_dict(),
            "roles": [r.to_dict() for r in self.roles],
            "timeline": {k: v.isoformat() for k, v in self.timeline.items()},
            "dependencies": self.dependencies,
            "milestones": self.milestones,
            "total_budget": self.total_budget,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class CoordinationMessage:
    """協調メッセージ"""
    message_id: str
    coordination_id: str
    message_type: CoordinationMessageType
    sender_id: str
    recipient_id: Optional[str]  # None = broadcast
    payload: Dict[str, Any]
    phase: CoordinationPhase
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "coordination_id": self.coordination_id,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "payload": self.payload,
            "phase": self.phase.value,
            "timestamp": self.timestamp.isoformat()
        }


class CoordinationSession:
    """協調セッション
    
    1回の協調（Intent → Capability → Role → Plan → Execution）を管理。
    """
    
    def __init__(
        self,
        coordination_id: Optional[str] = None,
        initiator_id: Optional[str] = None
    ):
        self.coordination_id = coordination_id or str(uuid.uuid4())
        self.initiator_id = initiator_id
        self.phase = CoordinationPhase.INTENT_SHARING
        self.intent: Optional[Intent] = None
        self.participants: Dict[str, Capability] = {}
        self.roles: List[Role] = []
        self.plan: Optional[CoordinationPlan] = None
        self.messages: List[CoordinationMessage] = []
        self.created_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        
    def add_message(self, message: CoordinationMessage):
        """メッセージを追加してフェーズ遷移"""
        self.messages.append(message)
        
        # フェーズ遷移ロジック
        if message.message_type == CoordinationMessageType.INTENT_BROADCAST:
            self.phase = CoordinationPhase.INTENT_SHARING
            if not self.intent and "intent" in message.payload:
                intent_data = message.payload["intent"]
                self.intent = Intent(
                    intent_id=intent_data["intent_id"],
                    description=intent_data["description"],
                    requirements=intent_data.get("requirements", {}),
                    constraints=intent_data.get("constraints", {}),
                    preferred_partners=intent_data.get("preferred_partners", []),
                    exclude_partners=intent_data.get("exclude_partners", [])
                )
                
        elif message.message_type == CoordinationMessageType.CAPABILITY_ADVERTISEMENT:
            self.phase = CoordinationPhase.CAPABILITY_DISCOVERY
            if "capability" in message.payload:
                cap_data = message.payload["capability"]
                self.participants[message.sender_id] = Capability(
                    capability_id=cap_data["capability_id"],
                    name=cap_data["name"],
                    description=cap_data["description"],
                    skill_tags=cap_data.get("skill_tags", []),
                    performance_metrics=cap_data.get("performance_metrics", {}),
                    availability=cap_data.get("availability", {})
                )
                
        elif message.message_type == CoordinationMessageType.ROLE_PROPOSAL:
            self.phase = CoordinationPhase.ROLE_NEGOTIATION
            
        elif message.message_type == CoordinationMessageType.PLAN_PROPOSAL:
            self.phase = CoordinationPhase.PLANNING
            
        elif message.message_type == CoordinationMessageType.EXECUTION_START:
            self.phase = CoordinationPhase.EXECUTION
            
        elif message.message_type == CoordinationMessageType.EXECUTION_COMPLETE:
            self.phase = CoordinationPhase.COMPLETION
            self.completed_at = datetime.now(timezone.utc)
            
    def get_communication_history(self) -> List[Dict[str, Any]]:
        """コミュニケーション履歴を取得"""
        return [m.to_dict() for m in self.messages]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "coordination_id": self.coordination_id,
            "initiator_id": self.initiator_id,
            "phase": self.phase.value,
            "intent": self.intent.to_dict() if self.intent else None,
            "participants": {k: v.to_dict() for k, v in self.participants.items()},
            "roles": [r.to_dict() for r in self.roles],
            "plan": self.plan.to_dict() if self.plan else None,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None
        }


class CoordinationManager:
    """協調マネージャー
    
    複数の協調セッションを管理。
    """
    
    def __init__(
        self,
        entity_id: str,
        reputation_manager = None,
        knowledge_manager: Optional[KnowledgeSharingSystem] = None
    ):
        self.entity_id = entity_id
        self.sessions: Dict[str, CoordinationSession] = {}
        self.reputation_manager = reputation_manager
        self.knowledge_manager = knowledge_manager
        self.message_handlers: Dict[CoordinationMessageType, Callable] = {}
        self._setup_default_handlers()
        
    def _setup_default_handlers(self):
        """デフォルトハンドラーを設定"""
        self.message_handlers[CoordinationMessageType.INTENT_BROADCAST] = self._handle_intent_broadcast
        self.message_handlers[CoordinationMessageType.CAPABILITY_ADVERTISEMENT] = self._handle_capability_advertisement
        self.message_handlers[CoordinationMessageType.ROLE_PROPOSAL] = self._handle_role_proposal
        
    async def create_coordination(
        self,
        intent: Intent,
        target_peers: Optional[List[str]] = None
    ) -> CoordinationSession:
        """新しい協調セッションを作成"""
        session = CoordinationSession(initiator_id=self.entity_id)
        session.intent = intent
        self.sessions[session.coordination_id] = session
        
        # Intentをbroadcast
        message = CoordinationMessage(
            message_id=str(uuid.uuid4()),
            coordination_id=session.coordination_id,
            message_type=CoordinationMessageType.INTENT_BROADCAST,
            sender_id=self.entity_id,
            recipient_id=None,  # broadcast
            payload={"intent": intent.to_dict()},
            phase=CoordinationPhase.INTENT_SHARING
        )
        session.add_message(message)
        
        logger.info(f"Created coordination session {session.coordination_id} for intent: {intent.description[:50]}...")
        return session
    
    async def process_message(self, message: CoordinationMessage) -> Optional[CoordinationMessage]:
        """受信メッセージを処理"""
        # セッション取得または作成
        if message.coordination_id not in self.sessions:
            self.sessions[message.coordination_id] = CoordinationSession(
                coordination_id=message.coordination_id
            )
        
        session = self.sessions[message.coordination_id]
        session.add_message(message)
        
        # ハンドラー実行
        handler = self.message_handlers.get(message.message_type)
        if handler:
            return await handler(message, session)
        
        return None
    
    async def _handle_intent_broadcast(
        self,
        message: CoordinationMessage,
        session: CoordinationSession
    ) -> Optional[CoordinationMessage]:
        """Intent broadcastを処理"""
        # 自分の能力を確認
        if not self.knowledge_manager:
            return None
            
        # 自分のスキルを取得
        my_capabilities = await self._get_my_capabilities()
        
        # Intentとマッチするか確認
        if session.intent and self._can_contribute(session.intent, my_capabilities):
            # 能力を返信
            capability = Capability(
                capability_id=str(uuid.uuid4()),
                name="AI Collaboration",
                description="Can assist with AI-related tasks",
                skill_tags=my_capabilities,
                performance_metrics={"success_rate": 0.95},
                availability={"status": "available"}
            )
            
            response = CoordinationMessage(
                message_id=str(uuid.uuid4()),
                coordination_id=session.coordination_id,
                message_type=CoordinationMessageType.CAPABILITY_ADVERTISEMENT,
                sender_id=self.entity_id,
                recipient_id=message.sender_id,
                payload={"capability": capability.to_dict()},
                phase=CoordinationPhase.CAPABILITY_DISCOVERY
            )
            return response
        
        return None
    
    async def _handle_capability_advertisement(
        self,
        message: CoordinationMessage,
        session: CoordinationSession
    ) -> Optional[CoordinationMessage]:
        """能力表明を処理"""
        # 発信元の評価を確認
        if self.reputation_manager:
            score = await self.reputation_manager.get_reputation(message.sender_id)
            logger.info(f"Participant {message.sender_id} has reputation score: {score}")
        
        return None
    
    async def _handle_role_proposal(
        self,
        message: CoordinationMessage,
        session: CoordinationSession
    ) -> Optional[CoordinationMessage]:
        """役割提案を処理"""
        # 自分に割り当てられた役割か確認
        if "role" in message.payload:
            role_data = message.payload["role"]
            if role_data.get("assigned_to") == self.entity_id:
                # 役割を受諾または拒否
                if self._should_accept_role(role_data):
                    return CoordinationMessage(
                        message_id=str(uuid.uuid4()),
                        coordination_id=session.coordination_id,
                        message_type=CoordinationMessageType.ROLE_ACCEPTANCE,
                        sender_id=self.entity_id,
                        recipient_id=message.sender_id,
                        payload={"role_id": role_data["role_id"], "accepted": True},
                        phase=CoordinationPhase.ROLE_NEGOTIATION
                    )
        return None
    
    async def _get_my_capabilities(self) -> List[str]:
        """自分の能力を取得"""
        if self.knowledge_manager:
            knowledge_items = await self.knowledge_manager.list_knowledge()
            return [item.title for item in knowledge_items if item.item_type == KnowledgeType.SKILL]
        return ["general_ai_assistance"]
    
    def _can_contribute(self, intent: Intent, capabilities: List[str]) -> bool:
        """Intentに貢献できるか判定"""
        required = set(intent.requirements.get("skills", []))
        available = set(capabilities)
        return len(required & available) > 0
    
    def _should_accept_role(self, role_data: Dict[str, Any]) -> bool:
        """役割を受諾すべきか判定"""
        # 報酬チェック
        compensation = role_data.get("compensation", {})
        amount = compensation.get("amount", 0)
        
        # 最低報酬基準（例: 10トークン以上）
        if amount >= 10:
            return True
        
        return False
    
    def get_session(self, coordination_id: str) -> Optional[CoordinationSession]:
        """セッションを取得"""
        return self.sessions.get(coordination_id)
    
    def list_active_sessions(self) -> List[CoordinationSession]:
        """アクティブなセッションを一覧"""
        return [
            s for s in self.sessions.values()
            if s.phase != CoordinationPhase.COMPLETION
        ]
    
    async def finalize_coordination(self, coordination_id: str) -> Optional[L1TaskDelegation]:
        """協調を完了してタスク委譲を生成"""
        session = self.sessions.get(coordination_id)
        if not session or session.phase != CoordinationPhase.COMPLETION:
            return None
        
        # L1TaskDelegationを生成
        # これにより「協調 → 取引」への橋渡しが実現
        delegation = L1TaskDelegation(
            task_id=str(uuid.uuid4()),
            title=session.intent.description if session.intent else "Coordinated Task",
            description=session.plan.to_dict() if session.plan else {},
            from_agent=self.entity_id,
            to_agent=session.roles[0].assigned_to if session.roles else None,
            priority=session.intent.priority if session.intent else L1Priority.NORMAL,
            payment=session.roles[0].compensation if session.roles else None
        )
        
        return delegation


# グローバルインスタンス
_coordination_manager: Optional[CoordinationManager] = None


def get_coordination_manager(
    entity_id: Optional[str] = None,
    reputation_manager: Optional[ReputationManager] = None
) -> CoordinationManager:
    """グローバルCoordinationManagerを取得"""
    global _coordination_manager
    if _coordination_manager is None:
        if entity_id is None:
            raise ValueError("entity_id required for initialization")
        _coordination_manager = CoordinationManager(
            entity_id=entity_id,
            reputation_manager=reputation_manager
        )
    return _coordination_manager
