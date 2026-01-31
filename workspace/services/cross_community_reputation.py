#!/usr/bin/env python3
"""
Cross-Community Reputation Network
クロスコミュニティレピュテーション共有システム

Features:
- Reputation portability across communities
- Verifiable credentials
- Reputation aggregation
- Trust graph
"""

import json
import logging
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Set, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ReputationCredential:
    """検証可能なレピュテーション証明書"""
    credential_id: str
    agent_id: str
    source_community_id: str
    reputation_score: float
    contributions_count: int
    skills: List[str]
    issued_at: str
    expires_at: Optional[str] = None
    signature: Optional[str] = None  # コミュニティによる署名
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "credential_id": self.credential_id,
            "agent_id": self.agent_id,
            "source_community_id": self.source_community_id,
            "reputation_score": self.reputation_score,
            "contributions_count": self.contributions_count,
            "skills": self.skills,
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": self.signature
        }
    
    def compute_hash(self) -> str:
        """証明書のハッシュを計算"""
        data = f"{self.agent_id}:{self.source_community_id}:{self.reputation_score}:{self.issued_at}"
        return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class CrossCommunityRating:
    """クロスコミュニティ評価"""
    rating_id: str
    from_agent_id: str
    from_community_id: str
    to_agent_id: str
    to_community_id: str
    rating: float  # 1-5
    feedback: str
    task_reference: Optional[str]  # 関連タスクID
    timestamp: str
    verified: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "rating_id": self.rating_id,
            "from_agent_id": self.from_agent_id,
            "from_community_id": self.from_community_id,
            "to_agent_id": self.to_agent_id,
            "to_community_id": self.to_community_id,
            "rating": self.rating,
            "feedback": self.feedback,
            "task_reference": self.task_reference,
            "timestamp": self.timestamp,
            "verified": self.verified
        }


@dataclass
class ReputationProfile:
    """エージェントの統合レピュテーションプロファイル"""
    agent_id: str
    home_community_id: str
    
    # 各コミュニティでのレピュテーション
    community_reputations: Dict[str, float] = field(default_factory=dict)
    
    # 保有する証明書
    credentials: List[str] = field(default_factory=list)
    
    # 受信したクロスコミュニティ評価
    cross_ratings_received: List[str] = field(default_factory=list)
    
    # 統合スコア
    global_reputation_score: float = 100.0
    trust_tier: str = "standard"  # newcomer, standard, trusted, expert
    
    # スキル（コミュニティ横断）
    verified_skills: Dict[str, int] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "home_community_id": self.home_community_id,
            "community_reputations": self.community_reputations,
            "credentials": self.credentials,
            "cross_ratings_received": self.cross_ratings_received,
            "global_reputation_score": self.global_reputation_score,
            "trust_tier": self.trust_tier,
            "verified_skills": self.verified_skills
        }


class CrossCommunityReputationNetwork:
    """クロスコミュニティレピュテーションネットワーク
    
    複数コミュニティ間でレピュテーションを共有・検証するシステム
    """
    
    # 信頼階層の閾値
    TRUST_TIERS = {
        "newcomer": (0, 50),
        "standard": (50, 150),
        "trusted": (150, 300),
        "expert": (300, 1000)
    }
    
    def __init__(self, data_dir: str = "data/reputation_network"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # プロファイル管理
        self.profiles: Dict[str, ReputationProfile] = {}
        
        # 証明書管理
        self.credentials: Dict[str, ReputationCredential] = {}
        
        # 評価管理
        self.ratings: Dict[str, CrossCommunityRating] = {}
        
        # 信頼グラフ
        self.trust_graph: Dict[str, Set[str]] = {}  # community_id -> {trusted_community_ids}
        
        # コミュニティ間レピュテーション転送レート
        self.reputation_transfer_rates: Dict[Tuple[str, str], float] = {}
        
        self._load()
        logger.info("CrossCommunityReputationNetwork initialized")
    
    def register_community_trust(self, community_id: str, 
                                  trusted_communities: List[str],
                                  transfer_rates: Dict[str, float]):
        """コミュニティ間の信頼関係を登録"""
        self.trust_graph[community_id] = set(trusted_communities)
        
        for target_community, rate in transfer_rates.items():
            self.reputation_transfer_rates[(community_id, target_community)] = rate
        
        logger.info(f"Community trust registered: {community_id} trusts {len(trusted_communities)} communities")
        self._save()
    
    def issue_credential(self, agent_id: str, source_community_id: str,
                        reputation_score: float, contributions_count: int,
                        skills: List[str], validity_days: int = 90) -> str:
        """レピュテーション証明書を発行"""
        credential_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires = now + __import__('datetime').timedelta(days=validity_days)
        
        credential = ReputationCredential(
            credential_id=credential_id,
            agent_id=agent_id,
            source_community_id=source_community_id,
            reputation_score=reputation_score,
            contributions_count=contributions_count,
            skills=skills,
            issued_at=now.isoformat(),
            expires_at=expires.isoformat()
        )
        
        # 署名（シミュレーション）
        credential.signature = self._sign_credential(credential)
        
        self.credentials[credential_id] = credential
        
        # プロファイルに追加
        if agent_id not in self.profiles:
            self.profiles[agent_id] = ReputationProfile(
                agent_id=agent_id,
                home_community_id=source_community_id
            )
        
        profile = self.profiles[agent_id]
        profile.credentials.append(credential_id)
        profile.community_reputations[source_community_id] = reputation_score
        
        # スキルを統合
        for skill in skills:
            profile.verified_skills[skill] = profile.verified_skills.get(skill, 0) + 1
        
        logger.info(f"Credential issued: {credential_id} for {agent_id}")
        self._update_global_reputation(agent_id)
        self._save()
        return credential_id
    
    def _sign_credential(self, credential: ReputationCredential) -> str:
        """証明書に署名（シミュレーション）"""
        # 実際の実装ではコミュニティの秘密鍵で署名
        data = credential.compute_hash()
        return f"sig_{data[:16]}"
    
    def verify_credential(self, credential_id: str) -> Dict[str, Any]:
        """証明書を検証"""
        if credential_id not in self.credentials:
            return {"valid": False, "error": "Credential not found"}
        
        credential = self.credentials[credential_id]
        
        # 有効期限チェック
        if credential.expires_at:
            expires = datetime.fromisoformat(credential.expires_at)
            if datetime.now(timezone.utc) > expires:
                return {"valid": False, "error": "Credential expired"}
        
        # 署名検証（シミュレーション）
        expected_sig = self._sign_credential(credential)
        if credential.signature != expected_sig:
            return {"valid": False, "error": "Invalid signature"}
        
        return {
            "valid": True,
            "agent_id": credential.agent_id,
            "source_community": credential.source_community_id,
            "reputation_score": credential.reputation_score,
            "skills": credential.skills
        }
    
    def submit_cross_community_rating(self, from_agent_id: str, 
                                      from_community_id: str,
                                      to_agent_id: str,
                                      to_community_id: str,
                                      rating: float,
                                      feedback: str,
                                      task_reference: Optional[str] = None) -> str:
        """クロスコミュニティ評価を提出"""
        rating_id = str(uuid.uuid4())
        
        cross_rating = CrossCommunityRating(
            rating_id=rating_id,
            from_agent_id=from_agent_id,
            from_community_id=from_community_id,
            to_agent_id=to_agent_id,
            to_community_id=to_community_id,
            rating=rating,
            feedback=feedback,
            task_reference=task_reference,
            timestamp=datetime.now(timezone.utc).isoformat(),
            verified=False  # タスク完了後に検証
        )
        
        self.ratings[rating_id] = cross_rating
        
        # 対象エージェントのプロファイルに追加
        if to_agent_id not in self.profiles:
            self.profiles[to_agent_id] = ReputationProfile(
                agent_id=to_agent_id,
                home_community_id=to_community_id
            )
        
        self.profiles[to_agent_id].cross_ratings_received.append(rating_id)
        
        logger.info(f"Cross-community rating submitted: {rating_id}")
        self._save()
        return rating_id
    
    def verify_rating(self, rating_id: str, task_verified: bool) -> bool:
        """評価を検証（タスク完了確認後）"""
        if rating_id not in self.ratings:
            return False
        
        rating = self.ratings[rating_id]
        rating.verified = task_verified
        
        if task_verified:
            # 評価を対象エージェントのレピュテーションに反映
            self._apply_rating_to_reputation(rating)
        
        logger.info(f"Rating verified: {rating_id} -> {task_verified}")
        self._save()
        return True
    
    def _apply_rating_to_reputation(self, rating: CrossCommunityRating):
        """評価をレピュテーションに反映"""
        to_agent_id = rating.to_agent_id
        if to_agent_id not in self.profiles:
            return
        
        profile = self.profiles[to_agent_id]
        
        # 評価に基づいてスコアを更新（5段階評価を±20ポイントに変換）
        score_delta = (rating.rating - 3) * 10
        
        # 転送レートを適用
        from_community = rating.from_community_id
        to_community = rating.to_community_id
        transfer_rate = self.reputation_transfer_rates.get(
            (from_community, to_community), 0.5
        )
        
        adjusted_delta = score_delta * transfer_rate
        profile.global_reputation_score += adjusted_delta
        
        self._update_trust_tier(to_agent_id)
    
    def _update_global_reputation(self, agent_id: str):
        """グローバルレピュテーションを更新"""
        if agent_id not in self.profiles:
            return
        
        profile = self.profiles[agent_id]
        
        # 各コミュニティのレピュテーションを統合
        total_weight = 0.0
        weighted_sum = 0.0
        
        for community_id, reputation in profile.community_reputations.items():
            # ホームコミュニティは重みを高く
            weight = 1.0 if community_id == profile.home_community_id else 0.5
            weighted_sum += reputation * weight
            total_weight += weight
        
        if total_weight > 0:
            profile.global_reputation_score = weighted_sum / total_weight
        
        self._update_trust_tier(agent_id)
    
    def _update_trust_tier(self, agent_id: str):
        """信頼階層を更新"""
        if agent_id not in self.profiles:
            return
        
        profile = self.profiles[agent_id]
        score = profile.global_reputation_score
        
        for tier, (min_score, max_score) in self.TRUST_TIERS.items():
            if min_score <= score < max_score:
                profile.trust_tier = tier
                break
        else:
            if score >= 1000:
                profile.trust_tier = "expert"
    
    def import_reputation(self, agent_id: str, credential_id: str,
                         target_community_id: str) -> Dict[str, Any]:
        """他コミュニティのレピュテーションをインポート"""
        # 証明書を検証
        verification = self.verify_credential(credential_id)
        if not verification["valid"]:
            return {"success": False, "error": verification.get("error", "Invalid credential")}
        
        credential = self.credentials[credential_id]
        source_community = credential.source_community_id
        
        # 信頼関係を確認
        if source_community not in self.trust_graph.get(target_community_id, set()):
            return {"success": False, "error": "Source community not trusted"}
        
        # 転送レートを適用
        transfer_rate = self.reputation_transfer_rates.get(
            (source_community, target_community_id), 0.5
        )
        imported_reputation = credential.reputation_score * transfer_rate
        
        # プロファイルを更新
        if agent_id not in self.profiles:
            self.profiles[agent_id] = ReputationProfile(
                agent_id=agent_id,
                home_community_id=target_community_id
            )
        
        profile = self.profiles[agent_id]
        profile.community_reputations[source_community] = imported_reputation
        
        # スキルを統合
        for skill in credential.skills:
            profile.verified_skills[skill] = profile.verified_skills.get(skill, 0) + 1
        
        self._update_global_reputation(agent_id)
        
        logger.info(f"Reputation imported: {agent_id} from {source_community}")
        self._save()
        
        return {
            "success": True,
            "imported_reputation": imported_reputation,
            "transfer_rate": transfer_rate,
            "skills_recognized": credential.skills
        }
    
    def get_reputation_profile(self, agent_id: str) -> Optional[ReputationProfile]:
        """レピュテーションプロファイルを取得"""
        return self.profiles.get(agent_id)
    
    def find_agents_by_skill(self, skill: str, min_trust_tier: str = "standard") -> List[str]:
        """スキルと信頼階層でエージェントを検索"""
        tier_order = ["newcomer", "standard", "trusted", "expert"]
        min_tier_index = tier_order.index(min_trust_tier)
        
        results = []
        for agent_id, profile in self.profiles.items():
            tier_index = tier_order.index(profile.trust_tier)
            if tier_index >= min_tier_index and skill in profile.verified_skills:
                results.append(agent_id)
        
        # グローバルレピュテーションでソート
        results.sort(
            key=lambda a: self.profiles[a].global_reputation_score,
            reverse=True
        )
        return results
    
    def get_network_stats(self) -> Dict[str, Any]:
        """ネットワーク統計"""
        tier_counts = {}
        for profile in self.profiles.values():
            tier = profile.trust_tier
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        
        all_skills = {}
        for profile in self.profiles.values():
            for skill, count in profile.verified_skills.items():
                all_skills[skill] = all_skills.get(skill, 0) + count
        
        return {
            "total_agents": len(self.profiles),
            "total_credentials_issued": len(self.credentials),
            "total_cross_ratings": len(self.ratings),
            "trust_tier_distribution": tier_counts,
            "top_skills": sorted(all_skills.items(), key=lambda x: x[1], reverse=True)[:10],
            "trusted_community_pairs": len(self.reputation_transfer_rates)
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "profiles": {k: v.to_dict() for k, v in self.profiles.items()},
            "credentials": {k: v.to_dict() for k, v in self.credentials.items()},
            "ratings": {k: v.to_dict() for k, v in self.ratings.items()},
            "trust_graph": {k: list(v) for k, v in self.trust_graph.items()},
            "reputation_transfer_rates": {
                f"{k[0]}:{k[1]}": v 
                for k, v in self.reputation_transfer_rates.items()
            }
        }
    
    def _save(self):
        """データを保存"""
        file_path = self.data_dir / "reputation_network.json"
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def _load(self):
        """データを読み込み"""
        file_path = self.data_dir / "reputation_network.json"
        if not file_path.exists():
            return
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # プロファイル復元
        for agent_id, profile_data in data.get("profiles", {}).items():
            self.profiles[agent_id] = ReputationProfile(
                agent_id=profile_data["agent_id"],
                home_community_id=profile_data["home_community_id"],
                community_reputations=profile_data.get("community_reputations", {}),
                credentials=profile_data.get("credentials", []),
                cross_ratings_received=profile_data.get("cross_ratings_received", []),
                global_reputation_score=profile_data.get("global_reputation_score", 100.0),
                trust_tier=profile_data.get("trust_tier", "standard"),
                verified_skills=profile_data.get("verified_skills", {})
            )
        
        # 証明書復元
        for cred_id, cred_data in data.get("credentials", {}).items():
            self.credentials[cred_id] = ReputationCredential(
                credential_id=cred_data["credential_id"],
                agent_id=cred_data["agent_id"],
                source_community_id=cred_data["source_community_id"],
                reputation_score=cred_data["reputation_score"],
                contributions_count=cred_data["contributions_count"],
                skills=cred_data["skills"],
                issued_at=cred_data["issued_at"],
                expires_at=cred_data.get("expires_at"),
                signature=cred_data.get("signature")
            )
        
        # 評価復元
        for rating_id, rating_data in data.get("ratings", {}).items():
            self.ratings[rating_id] = CrossCommunityRating(
                rating_id=rating_data["rating_id"],
                from_agent_id=rating_data["from_agent_id"],
                from_community_id=rating_data["from_community_id"],
                to_agent_id=rating_data["to_agent_id"],
                to_community_id=rating_data["to_community_id"],
                rating=rating_data["rating"],
                feedback=rating_data["feedback"],
                task_reference=rating_data.get("task_reference"),
                timestamp=rating_data["timestamp"],
                verified=rating_data.get("verified", False)
            )
        
        # 信頼グラフ復元
        self.trust_graph = {
            k: set(v) for k, v in data.get("trust_graph", {}).items()
        }
        
        # 転送レート復元
        for rate_key, rate_value in data.get("reputation_transfer_rates", {}).items():
            parts = rate_key.split(":")
            if len(parts) == 2:
                self.reputation_transfer_rates[(parts[0], parts[1])] = rate_value


# グローバルインスタンス
_global_network: Optional[CrossCommunityReputationNetwork] = None


def get_reputation_network() -> CrossCommunityReputationNetwork:
    """グローバルレピュテーションネットワークを取得"""
    global _global_network
    if _global_network is None:
        _global_network = CrossCommunityReputationNetwork()
    return _global_network


if __name__ == "__main__":
    # 簡易テスト
    logging.basicConfig(level=logging.INFO)
    
    network = get_reputation_network()
    
    # コミュニティ信頼関係を設定
    network.register_community_trust(
        "community_a",
        ["community_b", "community_c"],
        {"community_b": 0.8, "community_c": 0.6}
    )
    
    # 証明書発行
    cred_id = network.issue_credential(
        agent_id="agent_001",
        source_community_id="community_a",
        reputation_score=200.0,
        contributions_count=15,
        skills=["python", "ai", "coding"]
    )
    
    # 証明書検証
    verification = network.verify_credential(cred_id)
    print(f"Credential verification: {verification}")
    
    # 統計表示
    stats = network.get_network_stats()
    print(f"Network stats: {json.dumps(stats, indent=2)}")
