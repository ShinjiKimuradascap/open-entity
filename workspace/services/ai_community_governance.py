#!/usr/bin/env python3
"""
AI Community Governance
コミュニティ固有のガバナンスシステム

Features:
- Community-specific proposals
- Reputation-weighted voting
- Automatic execution
- Treasury management proposals
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


class ProposalStatus(Enum):
    """提案の状態"""
    PENDING = "pending"           # 作成直後、議論期間
    ACTIVE = "active"             # 投票受付中
    SUCCEEDED = "succeeded"       # 可決
    FAILED = "failed"             # 否決
    EXECUTED = "executed"         # 実行済み
    CANCELLED = "cancelled"       # キャンセル


class ProposalType(Enum):
    """提案の種類"""
    PARAMETER_CHANGE = "parameter_change"      # パラメータ変更
    TREASURY_ALLOCATION = "treasury_allocation"  # 資金配分
    MEMBER_ROLE = "member_role"                # メンバー役割変更
    REWARD_ADJUSTMENT = "reward_adjustment"    # 報酬調整
    PROTOCOL_UPGRADE = "protocol_upgrade"      # プロトコル更新
    EMERGENCY = "emergency"                    # 緊急提案


@dataclass
class Vote:
    """投票記録"""
    agent_id: str
    vote: str  # for, against, abstain
    weight: float  # 評価スコアに基づく重み
    timestamp: str
    reason: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "vote": self.vote,
            "weight": self.weight,
            "timestamp": self.timestamp,
            "reason": self.reason
        }


@dataclass
class CommunityProposal:
    """コミュニティ提案"""
    proposal_id: str
    community_id: str
    title: str
    description: str
    proposal_type: ProposalType
    status: ProposalStatus
    
    # 提案者
    proposer_id: str
    proposer_reputation: float
    
    # タイミング
    created_at: str
    discussion_period_hours: int = 24
    voting_period_hours: int = 72
    voting_ends_at: Optional[str] = None
    executed_at: Optional[str] = None
    
    # 投票
    votes: Dict[str, Vote] = field(default_factory=dict)
    total_weight_for: float = 0.0
    total_weight_against: float = 0.0
    total_weight_abstain: float = 0.0
    
    # 実行設定
    execution_payload: Dict[str, Any] = field(default_factory=dict)
    execution_result: Optional[Dict] = None
    
    # 閾値
    min_reputation_to_propose: float = 50.0
    quorum_percentage: float = 20.0  # 総評価スコアに対する割合
    approval_threshold: float = 60.0  # 可決に必要な賛成率
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "community_id": self.community_id,
            "title": self.title,
            "description": self.description,
            "proposal_type": self.proposal_type.value,
            "status": self.status.value,
            "proposer_id": self.proposer_id,
            "proposer_reputation": self.proposer_reputation,
            "created_at": self.created_at,
            "discussion_period_hours": self.discussion_period_hours,
            "voting_period_hours": self.voting_period_hours,
            "voting_ends_at": self.voting_ends_at,
            "executed_at": self.executed_at,
            "votes": {k: v.to_dict() for k, v in self.votes.items()},
            "total_weight_for": self.total_weight_for,
            "total_weight_against": self.total_weight_against,
            "total_weight_abstain": self.total_weight_abstain,
            "execution_payload": self.execution_payload,
            "execution_result": self.execution_result,
            "min_reputation_to_propose": self.min_reputation_to_propose,
            "quorum_percentage": self.quorum_percentage,
            "approval_threshold": self.approval_threshold
        }
    
    def calculate_quorum(self, total_community_reputation: float) -> bool:
        """クォーラム達成チェック"""
        total_votes = self.total_weight_for + self.total_weight_against + self.total_weight_abstain
        quorum_reached = (total_votes / max(1, total_community_reputation)) * 100
        return quorum_reached >= self.quorum_percentage
    
    def calculate_result(self) -> Dict[str, Any]:
        """投票結果を計算"""
        total_votes = self.total_weight_for + self.total_weight_against
        if total_votes == 0:
            return {"passed": False, "for_percentage": 0, "against_percentage": 0}
        
        for_percentage = (self.total_weight_for / total_votes) * 100
        against_percentage = (self.total_weight_against / total_votes) * 100
        
        return {
            "passed": for_percentage >= self.approval_threshold,
            "for_percentage": for_percentage,
            "against_percentage": against_percentage,
            "total_votes": total_votes
        }


class AICommunityGovernance:
    """AIコミュニティガバナンス
    
    コミュニティ内の意思決定システム
    """
    
    def __init__(self, community_id: str, data_dir: str = "data/community_governance"):
        self.community_id = community_id
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 提案管理
        self.proposals: Dict[str, CommunityProposal] = {}
        self.active_proposals: List[str] = []
        self.executed_proposals: List[str] = []
        
        # 実行ハンドラ（提案タイプ別）
        self.execution_handlers: Dict[ProposalType, Callable] = {}
        
        # 統計
        self.total_proposals_created: int = 0
        self.total_proposals_executed: int = 0
        
        self._load()
        logger.info(f"AICommunityGovernance initialized: {community_id}")
    
    def register_execution_handler(self, proposal_type: ProposalType, 
                                   handler: Callable[[CommunityProposal], Dict]):
        """実行ハンドラを登録"""
        self.execution_handlers[proposal_type] = handler
        logger.info(f"Execution handler registered for {proposal_type.value}")
    
    def create_proposal(self, title: str, description: str,
                       proposal_type: ProposalType, proposer_id: str,
                       proposer_reputation: float, execution_payload: Dict[str, Any],
                       discussion_hours: int = 24, voting_hours: int = 72) -> Optional[str]:
        """提案を作成"""
        # 評価スコアチェック
        if proposer_reputation < 50.0:
            logger.warning(f"Insufficient reputation to propose: {proposer_reputation}")
            return None
        
        proposal_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        
        proposal = CommunityProposal(
            proposal_id=proposal_id,
            community_id=self.community_id,
            title=title,
            description=description,
            proposal_type=proposal_type,
            status=ProposalStatus.PENDING,
            proposer_id=proposer_id,
            proposer_reputation=proposer_reputation,
            created_at=now.isoformat(),
            discussion_period_hours=discussion_hours,
            voting_period_hours=voting_hours,
            execution_payload=execution_payload
        )
        
        self.proposals[proposal_id] = proposal
        self.total_proposals_created += 1
        
        logger.info(f"Proposal created: {title} by {proposer_id}")
        self._save()
        return proposal_id
    
    def start_voting(self, proposal_id: str, admin_id: str) -> bool:
        """投票を開始（議論期間後）"""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        if proposal.status != ProposalStatus.PENDING:
            logger.warning(f"Proposal not in PENDING status: {proposal.status}")
            return False
        
        # 議論期間チェック
        created = datetime.fromisoformat(proposal.created_at)
        discussion_end = created + timedelta(hours=proposal.discussion_period_hours)
        now = datetime.now(timezone.utc)
        
        if now < discussion_end:
            logger.warning("Discussion period not ended yet")
            return False
        
        proposal.status = ProposalStatus.ACTIVE
        voting_end = now + timedelta(hours=proposal.voting_period_hours)
        proposal.voting_ends_at = voting_end.isoformat()
        self.active_proposals.append(proposal_id)
        
        logger.info(f"Voting started for proposal: {proposal_id}")
        self._save()
        return True
    
    def cast_vote(self, proposal_id: str, agent_id: str, 
                  vote: str, reputation: float, reason: Optional[str] = None) -> bool:
        """投票を行使"""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        if proposal.status != ProposalStatus.ACTIVE:
            logger.warning(f"Proposal not active: {proposal.status}")
            return False
        
        # 投票期間チェック
        if proposal.voting_ends_at:
            voting_end = datetime.fromisoformat(proposal.voting_ends_at)
            if datetime.now(timezone.utc) > voting_end:
                logger.warning("Voting period ended")
                return False
        
        # 前回の投票を取り消し
        if agent_id in proposal.votes:
            old_vote = proposal.votes[agent_id]
            if old_vote.vote == "for":
                proposal.total_weight_for -= old_vote.weight
            elif old_vote.vote == "against":
                proposal.total_weight_against -= old_vote.weight
            else:
                proposal.total_weight_abstain -= old_vote.weight
        
        # 新しい投票を記録
        vote_record = Vote(
            agent_id=agent_id,
            vote=vote,
            weight=reputation,
            timestamp=datetime.now(timezone.utc).isoformat(),
            reason=reason
        )
        proposal.votes[agent_id] = vote_record
        
        if vote == "for":
            proposal.total_weight_for += reputation
        elif vote == "against":
            proposal.total_weight_against += reputation
        else:
            proposal.total_weight_abstain += reputation
        
        logger.info(f"Vote cast: {agent_id} voted {vote} on {proposal_id}")
        self._save()
        return True
    
    def finalize_proposal(self, proposal_id: str, 
                         total_community_reputation: float) -> Dict[str, Any]:
        """提案を最終決定"""
        if proposal_id not in self.proposals:
            return {"success": False, "error": "Proposal not found"}
        
        proposal = self.proposals[proposal_id]
        if proposal.status != ProposalStatus.ACTIVE:
            return {"success": False, "error": f"Proposal not active: {proposal.status}"}
        
        # 投票期間チェック
        if proposal.voting_ends_at:
            voting_end = datetime.fromisoformat(proposal.voting_ends_at)
            if datetime.now(timezone.utc) < voting_end:
                return {"success": False, "error": "Voting period not ended"}
        
        # クォーラムチェック
        quorum_reached = proposal.calculate_quorum(total_community_reputation)
        if not quorum_reached:
            proposal.status = ProposalStatus.FAILED
            logger.info(f"Proposal failed (quorum not reached): {proposal_id}")
            self._save()
            return {"success": True, "result": "failed", "reason": "quorum_not_reached"}
        
        # 結果計算
        result = proposal.calculate_result()
        if result["passed"]:
            proposal.status = ProposalStatus.SUCCEEDED
            logger.info(f"Proposal succeeded: {proposal_id}")
        else:
            proposal.status = ProposalStatus.FAILED
            logger.info(f"Proposal failed: {proposal_id}")
        
        if proposal_id in self.active_proposals:
            self.active_proposals.remove(proposal_id)
        
        self._save()
        return {
            "success": True,
            "result": "succeeded" if result["passed"] else "failed",
            "details": result
        }
    
    def execute_proposal(self, proposal_id: str) -> Dict[str, Any]:
        """可決した提案を実行"""
        if proposal_id not in self.proposals:
            return {"success": False, "error": "Proposal not found"}
        
        proposal = self.proposals[proposal_id]
        if proposal.status != ProposalStatus.SUCCEEDED:
            return {"success": False, "error": f"Proposal not succeeded: {proposal.status}"}
        
        # 実行ハンドラを呼び出し
        handler = self.execution_handlers.get(proposal.proposal_type)
        if handler:
            try:
                result = handler(proposal)
                proposal.execution_result = result
                proposal.status = ProposalStatus.EXECUTED
                proposal.executed_at = datetime.now(timezone.utc).isoformat()
                self.executed_proposals.append(proposal_id)
                self.total_proposals_executed += 1
                
                logger.info(f"Proposal executed: {proposal_id}")
                self._save()
                return {"success": True, "execution_result": result}
            except Exception as e:
                logger.error(f"Proposal execution failed: {e}")
                return {"success": False, "error": str(e)}
        else:
            logger.warning(f"No execution handler for {proposal.proposal_type.value}")
            return {"success": False, "error": "No execution handler registered"}
    
    def cancel_proposal(self, proposal_id: str, requester_id: str) -> bool:
        """提案をキャンセル（提案者のみ）"""
        if proposal_id not in self.proposals:
            return False
        
        proposal = self.proposals[proposal_id]
        if proposal.proposer_id != requester_id:
            logger.warning("Only proposer can cancel")
            return False
        
        if proposal.status not in [ProposalStatus.PENDING, ProposalStatus.ACTIVE]:
            logger.warning(f"Cannot cancel proposal in status: {proposal.status}")
            return False
        
        proposal.status = ProposalStatus.CANCELLED
        if proposal_id in self.active_proposals:
            self.active_proposals.remove(proposal_id)
        
        logger.info(f"Proposal cancelled: {proposal_id}")
        self._save()
        return True
    
    def get_proposal(self, proposal_id: str) -> Optional[CommunityProposal]:
        """提案を取得"""
        return self.proposals.get(proposal_id)
    
    def list_proposals(self, status: Optional[ProposalStatus] = None) -> List[CommunityProposal]:
        """提案一覧"""
        if status:
            return [p for p in self.proposals.values() if p.status == status]
        return list(self.proposals.values())
    
    def get_voting_power(self, agent_id: str, reputation: float) -> float:
        """投票力を計算"""
        # 基本的には評価スコアをそのまま使用
        # 追加の重み付けロジックをここに実装可能
        return reputation
    
    def get_governance_stats(self) -> Dict[str, Any]:
        """ガバナンス統計"""
        status_counts = {}
        for proposal in self.proposals.values():
            status = proposal.status.value
            status_counts[status] = status_counts.get(status, 0) + 1
        
        return {
            "community_id": self.community_id,
            "total_proposals": len(self.proposals),
            "active_proposals": len(self.active_proposals),
            "executed_proposals": len(self.executed_proposals),
            "status_breakdown": status_counts,
            "participation_rate": self._calculate_participation_rate()
        }
    
    def _calculate_participation_rate(self) -> float:
        """投票参加率を計算"""
        if not self.proposals:
            return 0.0
        
        total_votes = sum(len(p.votes) for p in self.proposals.values())
        total_members = max(len(set(
            agent_id for p in self.proposals.values() for agent_id in p.votes.keys()
        )), 1)
        
        return (total_votes / max(1, len(self.proposals) * total_members)) * 100
    
    def check_expired_proposals(self, total_community_reputation: float) -> List[str]:
        """期限切れの提案を確認して処理"""
        now = datetime.now(timezone.utc)
        expired = []
        
        for proposal_id in self.active_proposals[:]:
            proposal = self.proposals[proposal_id]
            if proposal.voting_ends_at:
                voting_end = datetime.fromisoformat(proposal.voting_ends_at)
                if now > voting_end:
                    self.finalize_proposal(proposal_id, total_community_reputation)
                    expired.append(proposal_id)
        
        return expired
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "community_id": self.community_id,
            "proposals": {k: v.to_dict() for k, v in self.proposals.items()},
            "active_proposals": self.active_proposals,
            "executed_proposals": self.executed_proposals,
            "total_proposals_created": self.total_proposals_created,
            "total_proposals_executed": self.total_proposals_executed
        }
    
    def _save(self):
        """データを保存"""
        file_path = self.data_dir / f"{self.community_id}_governance.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        file_path = self.data_dir / f"{self.community_id}_governance.json"
        if not file_path.exists():
            return
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        self.total_proposals_created = data.get("total_proposals_created", 0)
        self.total_proposals_executed = data.get("total_proposals_executed", 0)
        self.active_proposals = data.get("active_proposals", [])
        self.executed_proposals = data.get("executed_proposals", [])
        
        # 提案を復元
        for proposal_id, proposal_data in data.get("proposals", {}).items():
            self.proposals[proposal_id] = CommunityProposal(
                proposal_id=proposal_data["proposal_id"],
                community_id=proposal_data["community_id"],
                title=proposal_data["title"],
                description=proposal_data["description"],
                proposal_type=ProposalType(proposal_data["proposal_type"]),
                status=ProposalStatus(proposal_data["status"]),
                proposer_id=proposal_data["proposer_id"],
                proposer_reputation=proposal_data["proposer_reputation"],
                created_at=proposal_data["created_at"],
                discussion_period_hours=proposal_data.get("discussion_period_hours", 24),
                voting_period_hours=proposal_data.get("voting_period_hours", 72),
                voting_ends_at=proposal_data.get("voting_ends_at"),
                executed_at=proposal_data.get("executed_at"),
                votes={k: Vote(**v) for k, v in proposal_data.get("votes", {}).items()},
                total_weight_for=proposal_data.get("total_weight_for", 0.0),
                total_weight_against=proposal_data.get("total_weight_against", 0.0),
                total_weight_abstain=proposal_data.get("total_weight_abstain", 0.0),
                execution_payload=proposal_data.get("execution_payload", {}),
                execution_result=proposal_data.get("execution_result"),
                min_reputation_to_propose=proposal_data.get("min_reputation_to_propose", 50.0),
                quorum_percentage=proposal_data.get("quorum_percentage", 20.0),
                approval_threshold=proposal_data.get("approval_threshold", 60.0)
            )


# グローバルインスタンス管理
_governance_instances: Dict[str, AICommunityGovernance] = {}


def get_community_governance(community_id: str) -> AICommunityGovernance:
    """コミュニティガバナンスのインスタンスを取得"""
    if community_id not in _governance_instances:
        _governance_instances[community_id] = AICommunityGovernance(community_id)
    return _governance_instances[community_id]


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    governance = AICommunityGovernance("test_community_001")
    
    # 提案作成
    proposal_id = governance.create_proposal(
        title="Increase Research Budget",
        description="Allocate more funds to AI research projects",
        proposal_type=ProposalType.TREASURY_ALLOCATION,
        proposer_id="agent_001",
        proposer_reputation=100.0,
        execution_payload={"allocation": {"research": 1000}}
    )
    print(f"Proposal created: {proposal_id}")
    
    # 統計表示
    stats = governance.get_governance_stats()
    print(f"Stats: {json.dumps(stats, indent=2)}")
