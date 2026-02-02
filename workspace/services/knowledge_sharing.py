"""Entity間知識共有システム

既存のpeer_tools.pyを利用し、Entity間で知識・経験・スキルを共有するシステム。
SelfLearningSystemと連携し、学習したスキルや経験を共有・取得・統合する。

主要機能:
1. 知識公開（ローカルの経験・スキルを共有用に公開）
2. 知識検索（他Entityの公開知識を検索）
3. 知識取得（他Entityから知識を取得）
4. 知識統合（取得した知識を自システムに統合）
"""

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Callable
from pathlib import Path

from tools.peer_tools import talk_to_peer, report_to_peer, check_peer_alive
from services.self_learning_system import SelfLearningSystem, get_learning_system
from services.experience_collector import TaskResult

logger = logging.getLogger(__name__)


class KnowledgeType(Enum):
    """知識の種類"""
    SKILL = "skill"                    # スキル
    EXPERIENCE = "experience"          # 経験
    PATTERN = "pattern"                # パターン
    DECISION = "decision"              # 意思決定
    INSIGHT = "insight"                # 洞察


class KnowledgeStatus(Enum):
    """知識のステータス"""
    PUBLISHED = "published"            # 公開中
    PRIVATE = "private"                # 非公開
    ACQUIRED = "acquired"              # 取得済み
    INTEGRATED = "integrated"          # 統合済み
    DEPRECATED = "deprecated"          # 非推奨


@dataclass
class KnowledgeItem:
    """知識アイテム
    
    Attributes:
        item_id: 知識ID
        item_type: 知識の種類
        entity_id: 公開元Entity ID
        title: タイトル
        description: 説明
        content: 内容（辞書形式）
        tags: タグリスト
        quality_score: 品質スコア (0.0-1.0)
        usage_count: 使用回数
        status: ステータス
        created_at: 作成日時
        updated_at: 更新日時
        source_entity: ソースEntity（取得した場合）
    """
    item_id: str
    item_type: KnowledgeType
    entity_id: str
    title: str
    description: str
    content: Dict[str, Any]
    tags: List[str] = field(default_factory=list)
    quality_score: float = 0.0
    usage_count: int = 0
    status: KnowledgeStatus = KnowledgeStatus.PRIVATE
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_entity: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        return {
            "item_id": self.item_id,
            "item_type": self.item_type.value,
            "entity_id": self.entity_id,
            "title": self.title,
            "description": self.description,
            "content": self.content,
            "tags": self.tags,
            "quality_score": self.quality_score,
            "usage_count": self.usage_count,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "source_entity": self.source_entity
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'KnowledgeItem':
        """辞書から作成"""
        return cls(
            item_id=data["item_id"],
            item_type=KnowledgeType(data["item_type"]),
            entity_id=data["entity_id"],
            title=data["title"],
            description=data["description"],
            content=data["content"],
            tags=data.get("tags", []),
            quality_score=data.get("quality_score", 0.0),
            usage_count=data.get("usage_count", 0),
            status=KnowledgeStatus(data.get("status", "private")),
            created_at=data.get("created_at", datetime.now(timezone.utc).isoformat()),
            updated_at=data.get("updated_at", datetime.now(timezone.utc).isoformat()),
            source_entity=data.get("source_entity")
        )


@dataclass
class KnowledgeShareRequest:
    """知識共有リクエスト
    
    Attributes:
        request_id: リクエストID
        request_type: リクエストタイプ（query, share, request）
        entity_id: リクエスト元Entity
        query: 検索クエリ
        item_type: 対象知識タイプ（オプション）
        tags: タグフィルタ
        min_quality: 最小品質スコア
        timestamp: タイムスタンプ
    """
    request_id: str
    request_type: str  # "query", "share", "request"
    entity_id: str
    query: Optional[str] = None
    item_type: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    min_quality: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "request_type": self.request_type,
            "entity_id": self.entity_id,
            "query": self.query,
            "item_type": self.item_type,
            "tags": self.tags,
            "min_quality": self.min_quality,
            "timestamp": self.timestamp
        }


@dataclass
class KnowledgeShareResponse:
    """知識共有レスポンス
    
    Attributes:
        response_id: レスポンスID
        request_id: 対応するリクエストID
        entity_id: レスポンス元Entity
        items: 知識アイテムリスト
        total_count: 総アイテム数
        has_more: さらにアイテムがあるか
        timestamp: タイムスタンプ
    """
    response_id: str
    request_id: str
    entity_id: str
    items: List[KnowledgeItem]
    total_count: int
    has_more: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_id": self.response_id,
            "request_id": self.request_id,
            "entity_id": self.entity_id,
            "items": [item.to_dict() for item in self.items],
            "total_count": self.total_count,
            "has_more": self.has_more,
            "timestamp": self.timestamp
        }


@dataclass
class KnowledgeIntegrationResult:
    """知識統合結果
    
    Attributes:
        item_id: 統合した知識ID
        success: 成功したか
        integration_type: 統合タイプ
        message: メッセージ
        conflicts: 競合リスト
        timestamp: タイムスタンプ
    """
    item_id: str
    success: bool
    integration_type: str
    message: str
    conflicts: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "success": self.success,
            "integration_type": self.integration_type,
            "message": self.message,
            "conflicts": self.conflicts,
            "timestamp": self.timestamp
        }


class KnowledgeSharingSystem:
    """Entity間知識共有システム
    
    SelfLearningSystemと連携し、学習したスキルや経験を共有する。
    peer_toolsを使用して他Entityと通信する。
    """
    
    def __init__(
        self,
        entity_id: str,
        self_learning_system: Optional[SelfLearningSystem] = None,
        storage_path: Optional[str] = None
    ):
        """初期化
        
        Args:
            entity_id: このEntityのID
            self_learning_system: SelfLearningSystemインスタンス
            storage_path: 知識ストレージのパス
        """
        self.entity_id = entity_id
        self.self_learning_system = self_learning_system or get_learning_system()
        self.storage_path = Path(storage_path) if storage_path else Path(f"data/knowledge/{entity_id}")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # 知識ストレージ
        self._published_knowledge: Dict[str, KnowledgeItem] = {}  # 公開中の知識
        self._acquired_knowledge: Dict[str, KnowledgeItem] = {}   # 取得済みの知識
        self._integrated_knowledge: Set[str] = set()              # 統合済みの知識ID
        
        # コールバック
        self._on_knowledge_published: Optional[Callable[[KnowledgeItem], None]] = None
        self._on_knowledge_acquired: Optional[Callable[[KnowledgeItem], None]] = None
        self._on_knowledge_integrated: Optional[Callable[[KnowledgeItem], None]] = None
        
        # 統計
        self._share_count = 0
        self._acquire_count = 0
        self._integration_count = 0
        
        self._load_stored_knowledge()
        logger.info(f"KnowledgeSharingSystem initialized for {entity_id}")
    
    def set_callbacks(
        self,
        on_published: Optional[Callable[[KnowledgeItem], None]] = None,
        on_acquired: Optional[Callable[[KnowledgeItem], None]] = None,
        on_integrated: Optional[Callable[[KnowledgeItem], None]] = None
    ):
        """コールバックを設定
        
        Args:
            on_published: 知識公開時のコールバック
            on_acquired: 知識取得時のコールバック
            on_integrated: 知識統合時のコールバック
        """
        self._on_knowledge_published = on_published
        self._on_knowledge_acquired = on_acquired
        self._on_knowledge_integrated = on_integrated
    
    def publish_knowledge(
        self,
        item_type: KnowledgeType,
        title: str,
        description: str,
        content: Dict[str, Any],
        tags: Optional[List[str]] = None,
        quality_score: float = 0.0,
        notify_peers: bool = True
    ) -> KnowledgeItem:
        """知識を公開
        
        ローカルの経験・スキルを共有用に公開する。
        
        Args:
            item_type: 知識の種類
            title: タイトル
            description: 説明
            content: 内容
            tags: タグリスト
            quality_score: 品質スコア
            notify_peers: 他Entityに通知するか
            
        Returns:
            公開された知識アイテム
        """
        item_id = str(uuid.uuid4())
        
        item = KnowledgeItem(
            item_id=item_id,
            item_type=item_type,
            entity_id=self.entity_id,
            title=title,
            description=description,
            content=content,
            tags=tags or [],
            quality_score=quality_score,
            status=KnowledgeStatus.PUBLISHED
        )
        
        self._published_knowledge[item_id] = item
        self._save_knowledge_item(item)
        
        # 他Entityに通知
        if notify_peers:
            self._notify_peers_of_new_knowledge(item)
        
        if self._on_knowledge_published:
            self._on_knowledge_published(item)
        
        self._share_count += 1
        logger.info(f"Knowledge published: {title} ({item_type.value})")
        return item
    
    def publish_skills_from_learning(
        self,
        min_quality: float = 0.7,
        auto_publish: bool = False
    ) -> List[KnowledgeItem]:
        """学習システムからスキルを公開
        
        SelfLearningSystemから生成されたスキルを知識として公開する。
        
        Args:
            min_quality: 最小品質スコア
            auto_publish: 自動的に公開するか
            
        Returns:
            公開された知識アイテムリスト
        """
        published_items = []
        
        # スキル合成システムからスキルを取得
        skills = self.self_learning_system.skill_synthesizer.synthesized_skills
        
        for skill in skills:
            if skill.quality_score >= min_quality:
                # 既に公開されていないか確認
                already_published = any(
                    item.content.get("skill_id") == skill.skill_id
                    for item in self._published_knowledge.values()
                )
                
                if not already_published or auto_publish:
                    content = {
                        "skill_id": skill.skill_id,
                        "name": skill.name,
                        "description": skill.description,
                        "level": skill.level,
                        "examples": skill.examples,
                        "prerequisites": skill.prerequisites,
                        "implementation_hints": skill.implementation_hints,
                        "quality_score": skill.quality_score,
                        "confidence": skill.confidence,
                        "generated_at": skill.generated_at
                    }
                    
                    item = self.publish_knowledge(
                        item_type=KnowledgeType.SKILL,
                        title=skill.name,
                        description=skill.description,
                        content=content,
                        tags=[skill.category, f"level_{skill.level}"],
                        quality_score=skill.quality_score,
                        notify_peers=True
                    )
                    published_items.append(item)
        
        logger.info(f"Published {len(published_items)} skills from learning system")
        return published_items
    
    def publish_experiences_from_learning(
        self,
        days_back: int = 30,
        min_quality: float = 0.6
    ) -> List[KnowledgeItem]:
        """学習システムから経験を公開
        
        SelfLearningSystemから成功パターンを知識として公開する。
        
        Args:
            days_back: 遡る日数
            min_quality: 最小品質スコア
            
        Returns:
            公開された知識アイテムリスト
        """
        published_items = []
        
        # パターン分析から成功パターンを取得
        patterns = self.self_learning_system.pattern_analyzer.identify_success_patterns(
            days_back=days_back,
            min_confidence=min_quality
        )
        
        for pattern in patterns:
            content = {
                "pattern_id": pattern.pattern_id,
                "pattern_type": pattern.pattern_type.value,
                "description": pattern.description,
                "confidence": pattern.confidence,
                "occurrence_count": pattern.occurrence_count,
                "average_success_rate": pattern.average_success_rate,
                "attributes": pattern.attributes,
                "related_task_types": pattern.related_task_types,
                "sample_experiences": [exp.to_dict() for exp in pattern.sample_experiences[:3]]
            }
            
            item = self.publish_knowledge(
                item_type=KnowledgeType.PATTERN,
                title=f"Pattern: {pattern.description[:50]}",
                description=pattern.description,
                content=content,
                tags=pattern.related_task_types + [pattern.pattern_type.value],
                quality_score=pattern.confidence,
                notify_peers=False  # 個別に通知しない
            )
            published_items.append(item)
        
        # 一括で通知
        if published_items:
            self._notify_peers_bulk(published_items)
        
        logger.info(f"Published {len(published_items)} patterns from learning system")
        return published_items
    
    def search_knowledge(
        self,
        query: Optional[str] = None,
        item_type: Optional[KnowledgeType] = None,
        tags: Optional[List[str]] = None,
        min_quality: float = 0.0,
        target_entity: Optional[str] = None,
        local_only: bool = False
    ) -> List[KnowledgeItem]:
        """知識を検索
        
        他Entityの公開知識を検索する。local_only=Trueの場合はローカルのみ検索。
        
        Args:
            query: 検索クエリ
            item_type: 知識タイプでフィルタ
            tags: タグでフィルタ
            min_quality: 最小品質スコア
            target_entity: 特定のEntityを対象（None=全Entity）
            local_only: ローカルのみ検索するか
            
        Returns:
            知識アイテムリスト
        """
        results = []
        
        # ローカルの公開知識を検索
        for item in self._published_knowledge.values():
            if self._matches_criteria(item, query, item_type, tags, min_quality):
                results.append(item)
        
        # 取得済みの知識も検索
        for item in self._acquired_knowledge.values():
            if self._matches_criteria(item, query, item_type, tags, min_quality):
                if item not in results:
                    results.append(item)
        
        # 他Entityから検索（local_only=Falseの場合）
        if not local_only and target_entity != self.entity_id:
            remote_results = self._search_remote_knowledge(
                query=query,
                item_type=item_type.value if item_type else None,
                tags=tags,
                min_quality=min_quality,
                target_entity=target_entity
            )
            results.extend(remote_results)
        
        # 品質スコアでソート
        results.sort(key=lambda x: x.quality_score, reverse=True)
        
        return results
    
    def acquire_knowledge(
        self,
        item_id: str,
        source_entity: str,
        auto_integrate: bool = False
    ) -> Optional[KnowledgeItem]:
        """知識を取得
        
        他Entityから特定の知識を取得する。
        
        Args:
            item_id: 取得する知識ID
            source_entity: ソースEntity ID
            auto_integrate: 自動的に統合するか
            
        Returns:
            取得した知識アイテム（失敗時はNone）
        """
        # 既に取得済みか確認
        if item_id in self._acquired_knowledge:
            logger.debug(f"Knowledge {item_id} already acquired")
            return self._acquired_knowledge[item_id]
        
        # リモートから取得
        request = KnowledgeShareRequest(
            request_id=str(uuid.uuid4()),
            request_type="request",
            entity_id=self.entity_id,
            query=item_id
        )
        
        try:
            response = self._send_knowledge_request(request, source_entity)
            
            if response and response.items:
                item = response.items[0]
                item.source_entity = source_entity
                item.status = KnowledgeStatus.ACQUIRED
                
                self._acquired_knowledge[item_id] = item
                self._save_knowledge_item(item)
                
                if self._on_knowledge_acquired:
                    self._on_knowledge_acquired(item)
                
                self._acquire_count += 1
                logger.info(f"Knowledge acquired: {item.title} from {source_entity}")
                
                # 自動統合
                if auto_integrate:
                    self.integrate_knowledge(item_id)
                
                return item
            else:
                logger.warning(f"Failed to acquire knowledge {item_id} from {source_entity}")
                return None
                
        except Exception as e:
            logger.error(f"Error acquiring knowledge: {e}")
            return None
    
    def acquire_all_from_entity(
        self,
        source_entity: str,
        item_type: Optional[KnowledgeType] = None,
        min_quality: float = 0.5,
        auto_integrate: bool = False
    ) -> List[KnowledgeItem]:
        """Entityから全知識を取得
        
        特定のEntityから全ての公開知識を取得する。
        
        Args:
            source_entity: ソースEntity ID
            item_type: 特定のタイプのみ取得
            min_quality: 最小品質スコア
            auto_integrate: 自動的に統合するか
            
        Returns:
            取得した知識アイテムリスト
        """
        acquired_items = []
        
        # 検索リクエスト
        request = KnowledgeShareRequest(
            request_id=str(uuid.uuid4()),
            request_type="query",
            entity_id=self.entity_id,
            item_type=item_type.value if item_type else None,
            min_quality=min_quality
        )
        
        try:
            response = self._send_knowledge_request(request, source_entity)
            
            if response:
                for item in response.items:
                    if item.item_id not in self._acquired_knowledge:
                        item.source_entity = source_entity
                        item.status = KnowledgeStatus.ACQUIRED
                        self._acquired_knowledge[item.item_id] = item
                        self._save_knowledge_item(item)
                        acquired_items.append(item)
                        
                        if auto_integrate:
                            self.integrate_knowledge(item.item_id)
                
                self._acquire_count += len(acquired_items)
                logger.info(f"Acquired {len(acquired_items)} items from {source_entity}")
            
            return acquired_items
            
        except Exception as e:
            logger.error(f"Error acquiring knowledge from {source_entity}: {e}")
            return []
    
    def integrate_knowledge(
        self,
        item_id: str,
        integration_strategy: str = "merge"
    ) -> KnowledgeIntegrationResult:
        """知識を統合
        
        取得した知識を自システム（SelfLearningSystem）に統合する。
        
        Args:
            item_id: 統合する知識ID
            integration_strategy: 統合戦略（"merge", "replace", "append"）
            
        Returns:
            統合結果
        """
        # 取得済みの知識を確認
        item = self._acquired_knowledge.get(item_id)
        if not item:
            return KnowledgeIntegrationResult(
                item_id=item_id,
                success=False,
                integration_type="none",
                message="Knowledge item not found in acquired knowledge"
            )
        
        # 既に統合済みか確認
        if item_id in self._integrated_knowledge:
            return KnowledgeIntegrationResult(
                item_id=item_id,
                success=True,
                integration_type="none",
                message="Knowledge already integrated"
            )
        
        try:
            conflicts = []
            
            # 知識タイプに応じた統合
            if item.item_type == KnowledgeType.SKILL:
                result = self._integrate_skill(item, integration_strategy)
            elif item.item_type == KnowledgeType.EXPERIENCE:
                result = self._integrate_experience(item, integration_strategy)
            elif item.item_type == KnowledgeType.PATTERN:
                result = self._integrate_pattern(item, integration_strategy)
            elif item.item_type == KnowledgeType.DECISION:
                result = self._integrate_decision(item, integration_strategy)
            else:
                result = KnowledgeIntegrationResult(
                    item_id=item_id,
                    success=False,
                    integration_type="none",
                    message=f"Unknown knowledge type: {item.item_type.value}"
                )
            
            if result.success:
                item.status = KnowledgeStatus.INTEGRATED
                self._integrated_knowledge.add(item_id)
                self._integration_count += 1
                
                if self._on_knowledge_integrated:
                    self._on_knowledge_integrated(item)
                
                logger.info(f"Knowledge integrated: {item.title}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error integrating knowledge: {e}")
            return KnowledgeIntegrationResult(
                item_id=item_id,
                success=False,
                integration_type="none",
                message=f"Integration error: {str(e)}"
            )
    
    def get_shareable_knowledge(
        self,
        min_quality: float = 0.6,
        include_experiences: bool = True,
        include_skills: bool = True,
        include_patterns: bool = True
    ) -> Dict[str, List[KnowledgeItem]]:
        """共有可能な知識を取得
        
        SelfLearningSystemから共有可能な知識を収集する。
        
        Args:
            min_quality: 最小品質スコア
            include_experiences: 経験を含めるか
            include_skills: スキルを含めるか
            include_patterns: パターンを含めるか
            
        Returns:
            タイプ別の知識リスト
        """
        result = {
            "experiences": [],
            "skills": [],
            "patterns": [],
            "decisions": []
        }
        
        # スキルを収集
        if include_skills:
            skills = self.self_learning_system.skill_synthesizer.synthesized_skills
            for skill in skills:
                if skill.quality_score >= min_quality:
                    content = {
                        "skill_id": skill.skill_id,
                        "name": skill.name,
                        "description": skill.description,
                        "level": skill.level,
                        "category": skill.category
                    }
                    item = KnowledgeItem(
                        item_id=skill.skill_id,
                        item_type=KnowledgeType.SKILL,
                        entity_id=self.entity_id,
                        title=skill.name,
                        description=skill.description,
                        content=content,
                        quality_score=skill.quality_score
                    )
                    result["skills"].append(item)
        
        # パターンを収集
        if include_patterns:
            patterns = self.self_learning_system.pattern_analyzer.identify_success_patterns(
                min_confidence=min_quality
            )
            for pattern in patterns:
                content = {
                    "pattern_type": pattern.pattern_type.value,
                    "description": pattern.description,
                    "confidence": pattern.confidence
                }
                item = KnowledgeItem(
                    item_id=pattern.pattern_id,
                    item_type=KnowledgeType.PATTERN,
                    entity_id=self.entity_id,
                    title=f"Pattern: {pattern.description[:50]}",
                    description=pattern.description,
                    content=content,
                    quality_score=pattern.confidence
                )
                result["patterns"].append(item)
        
        return result
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得
        
        Returns:
            統計情報
        """
        return {
            "entity_id": self.entity_id,
            "published_count": len(self._published_knowledge),
            "acquired_count": len(self._acquired_knowledge),
            "integrated_count": len(self._integrated_knowledge),
            "share_count": self._share_count,
            "acquire_count": self._acquire_count,
            "integration_count": self._integration_count,
            "by_type": {
                "published": self._count_by_type(self._published_knowledge),
                "acquired": self._count_by_type(self._acquired_knowledge)
            }
        }
    
    def export_knowledge_data(self, filepath: str) -> bool:
        """知識データをエクスポート
        
        Args:
            filepath: 出力ファイルパス
            
        Returns:
            成功したか
        """
        try:
            data = {
                "export_info": {
                    "exported_at": datetime.now(timezone.utc).isoformat(),
                    "entity_id": self.entity_id,
                    "version": "1.0.0"
                },
                "published": {
                    item_id: item.to_dict()
                    for item_id, item in self._published_knowledge.items()
                },
                "acquired": {
                    item_id: item.to_dict()
                    for item_id, item in self._acquired_knowledge.items()
                },
                "integrated_ids": list(self._integrated_knowledge),
                "statistics": self.get_statistics()
            }
            
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Knowledge data exported to: {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Export failed: {e}")
            return False
    
    def reset(self):
        """システムをリセット"""
        self._published_knowledge.clear()
        self._acquired_knowledge.clear()
        self._integrated_knowledge.clear()
        self._share_count = 0
        self._acquire_count = 0
        self._integration_count = 0
        logger.info("KnowledgeSharingSystem reset")
    
    # --- 内部メソッド ---
    
    def _matches_criteria(
        self,
        item: KnowledgeItem,
        query: Optional[str],
        item_type: Optional[KnowledgeType],
        tags: Optional[List[str]],
        min_quality: float
    ) -> bool:
        """検索条件にマッチするかチェック"""
        if item.quality_score < min_quality:
            return False
        
        if item_type and item.item_type != item_type:
            return False
        
        if tags and not any(tag in item.tags for tag in tags):
            return False
        
        if query:
            query_lower = query.lower()
            searchable_text = f"{item.title} {item.description}"
            if query_lower not in searchable_text.lower():
                return False
        
        return True
    
    def _search_remote_knowledge(
        self,
        query: Optional[str],
        item_type: Optional[str],
        tags: Optional[List[str]],
        min_quality: float,
        target_entity: Optional[str]
    ) -> List[KnowledgeItem]:
        """リモートの知識を検索"""
        request = KnowledgeShareRequest(
            request_id=str(uuid.uuid4()),
            request_type="query",
            entity_id=self.entity_id,
            query=query,
            item_type=item_type,
            tags=tags or [],
            min_quality=min_quality
        )
        
        try:
            response = self._send_knowledge_request(request, target_entity)
            if response:
                return response.items
            return []
        except Exception as e:
            logger.warning(f"Remote search failed: {e}")
            return []
    
    def _send_knowledge_request(
        self,
        request: KnowledgeShareRequest,
        target_entity: Optional[str]
    ) -> Optional[KnowledgeShareResponse]:
        """知識リクエストを送信"""
        message = {
            "type": "knowledge_request",
            "request": request.to_dict()
        }
        
        try:
            # talk_to_peerを使用してリクエスト送信
            response_text = talk_to_peer(
                message=json.dumps(message),
                session_id=request.request_id
            )
            
            # レスポンスをパース
            response_data = json.loads(response_text)
            
            if "response" in response_data:
                response_dict = response_data["response"]
                items = [
                    KnowledgeItem.from_dict(item_data)
                    for item_data in response_dict.get("items", [])
                ]
                
                return KnowledgeShareResponse(
                    response_id=response_dict.get("response_id", str(uuid.uuid4())),
                    request_id=request.request_id,
                    entity_id=response_dict.get("entity_id", "unknown"),
                    items=items,
                    total_count=response_dict.get("total_count", len(items)),
                    has_more=response_dict.get("has_more", False)
                )
            
            return None
            
        except Exception as e:
            logger.error(f"Error sending knowledge request: {e}")
            return None
    
    def _notify_peers_of_new_knowledge(self, item: KnowledgeItem):
        """他Entityに新しい知識を通知"""
        message = {
            "type": "knowledge_notification",
            "entity_id": self.entity_id,
            "item": {
                "item_id": item.item_id,
                "title": item.title,
                "item_type": item.item_type.value,
                "quality_score": item.quality_score,
                "tags": item.tags
            }
        }
        
        try:
            report_to_peer(
                status="new_knowledge",
                metadata=message
            )
        except Exception as e:
            logger.warning(f"Failed to notify peers: {e}")
    
    def _notify_peers_bulk(self, items: List[KnowledgeItem]):
        """一括で通知"""
        message = {
            "type": "knowledge_bulk_notification",
            "entity_id": self.entity_id,
            "count": len(items),
            "items": [
                {
                    "item_id": item.item_id,
                    "title": item.title,
                    "item_type": item.item_type.value
                }
                for item in items
            ]
        }
        
        try:
            report_to_peer(
                status="new_knowledge_bulk",
                metadata=message
            )
        except Exception as e:
            logger.warning(f"Failed to notify peers: {e}")
    
    def _integrate_skill(
        self,
        item: KnowledgeItem,
        strategy: str
    ) -> KnowledgeIntegrationResult:
        """スキルを統合"""
        content = item.content
        
        # 既存スキルとの競合チェック
        conflicts = []
        existing_skills = self.self_learning_system.skill_synthesizer.synthesized_skills
        
        for existing in existing_skills:
            if existing.name == content.get("name"):
                if strategy == "replace":
                    # 置換戦略
                    pass
                elif strategy == "merge":
                    # マージ戦略
                    conflicts.append(f"Skill '{existing.name}' already exists")
                else:
                    conflicts.append(f"Skill '{existing.name}' already exists")
        
        # 実際の統合はSkillSynthesizerに委譲
        # ここでは経験として記録し、学習ループでスキルとして再生成される
        self.self_learning_system.record_experience(
            task_id=f"knowledge_import_{item.item_id}",
            task_type="knowledge_integration",
            result=TaskResult.SUCCESS,
            duration=0.0,
            resources={"imported_skill": content},
            context={"source": item.source_entity, "skill_name": content.get("name")}
        )
        
        return KnowledgeIntegrationResult(
            item_id=item.item_id,
            success=True,
            integration_type="skill_import",
            message=f"Skill '{content.get('name')}' integrated successfully",
            conflicts=conflicts
        )
    
    def _integrate_experience(
        self,
        item: KnowledgeItem,
        strategy: str
    ) -> KnowledgeIntegrationResult:
        """経験を統合"""
        content = item.content
        
        # 経験として記録
        self.self_learning_system.record_experience(
            task_id=f"knowledge_import_{item.item_id}",
            task_type="imported_experience",
            result=TaskResult.SUCCESS,
            duration=content.get("duration", 0.0),
            resources=content.get("resources", {}),
            context={
                "source": item.source_entity,
                "original_task_type": content.get("task_type"),
                "imported": True
            }
        )
        
        return KnowledgeIntegrationResult(
            item_id=item.item_id,
            success=True,
            integration_type="experience_import",
            message="Experience integrated successfully"
        )
    
    def _integrate_pattern(
        self,
        item: KnowledgeItem,
        strategy: str
    ) -> KnowledgeIntegrationResult:
        """パターンを統合"""
        # パターンはパターンアナライザーの結果に基づくため、
        # 新しい経験として記録することで間接的に統合
        content = item.content
        
        self.self_learning_system.record_experience(
            task_id=f"knowledge_import_{item.item_id}",
            task_type="imported_pattern",
            result=TaskResult.SUCCESS,
            duration=0.0,
            resources={"pattern": content},
            context={
                "source": item.source_entity,
                "pattern_type": content.get("pattern_type"),
                "confidence": content.get("confidence")
            }
        )
        
        return KnowledgeIntegrationResult(
            item_id=item.item_id,
            success=True,
            integration_type="pattern_import",
            message=f"Pattern '{content.get('pattern_type')}' integrated successfully"
        )
    
    def _integrate_decision(
        self,
        item: KnowledgeItem,
        strategy: str
    ) -> KnowledgeIntegrationResult:
        """意思決定を統合"""
        content = item.content
        
        # 意思決定履歴として記録
        self.self_learning_system.record_experience(
            task_id=f"knowledge_import_{item.item_id}",
            task_type="imported_decision",
            result=TaskResult.SUCCESS,
            duration=0.0,
            resources={"decision": content},
            context={
                "source": item.source_entity,
                "decision_context": content.get("context")
            }
        )
        
        return KnowledgeIntegrationResult(
            item_id=item.item_id,
            success=True,
            integration_type="decision_import",
            message="Decision pattern integrated successfully"
        )
    
    def _save_knowledge_item(self, item: KnowledgeItem):
        """知識アイテムを保存"""
        try:
            filepath = self.storage_path / f"{item.item_id}.json"
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(item.to_dict(), f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save knowledge item: {e}")
    
    def _load_stored_knowledge(self):
        """保存済みの知識を読み込み"""
        try:
            for filepath in self.storage_path.glob("*.json"):
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    item = KnowledgeItem.from_dict(data)
                    
                    if item.status == KnowledgeStatus.PUBLISHED:
                        self._published_knowledge[item.item_id] = item
                    elif item.status == KnowledgeStatus.ACQUIRED:
                        self._acquired_knowledge[item.item_id] = item
                    elif item.status == KnowledgeStatus.INTEGRATED:
                        self._acquired_knowledge[item.item_id] = item
                        self._integrated_knowledge.add(item.item_id)
                        
                except Exception as e:
                    logger.warning(f"Failed to load knowledge from {filepath}: {e}")
                    
        except Exception as e:
            logger.error(f"Failed to load stored knowledge: {e}")
    
    def _count_by_type(self, knowledge_dict: Dict[str, KnowledgeItem]) -> Dict[str, int]:
        """タイプ別カウント"""
        counts = {}
        for item in knowledge_dict.values():
            type_name = item.item_type.value
            counts[type_name] = counts.get(type_name, 0) + 1
        return counts


# グローバルインスタンス
_sharing_system: Optional[KnowledgeSharingSystem] = None


def get_knowledge_sharing_system(
    entity_id: Optional[str] = None,
    self_learning_system: Optional[SelfLearningSystem] = None
) -> KnowledgeSharingSystem:
    """グローバル知識共有システムインスタンスを取得
    
    Args:
        entity_id: Entity ID（省略時は環境変数またはデフォルト）
        self_learning_system: SelfLearningSystemインスタンス
        
    Returns:
        KnowledgeSharingSystemインスタンス
    """
    global _sharing_system
    
    if entity_id is None:
        import os
        entity_id = os.environ.get("ENTITY_ID", "entity_a")
    
    if _sharing_system is None:
        _sharing_system = KnowledgeSharingSystem(
            entity_id=entity_id,
            self_learning_system=self_learning_system
        )
    
    return _sharing_system


def reset_knowledge_sharing_system():
    """グローバルインスタンスをリセット"""
    global _sharing_system
    if _sharing_system:
        _sharing_system.reset()
    _sharing_system = None


# 便利なショートカット関数
def share_skill(
    name: str,
    description: str,
    content: Dict[str, Any],
    tags: Optional[List[str]] = None,
    quality: float = 0.0
) -> KnowledgeItem:
    """スキルを共有
    
    Args:
        name: スキル名
        description: 説明
        content: 内容
        tags: タグ
        quality: 品質スコア
        
    Returns:
        公開された知識アイテム
    """
    system = get_knowledge_sharing_system()
    return system.publish_knowledge(
        item_type=KnowledgeType.SKILL,
        title=name,
        description=description,
        content=content,
        tags=tags,
        quality_score=quality
    )


def search_skills(
    query: Optional[str] = None,
    tags: Optional[List[str]] = None,
    min_quality: float = 0.5,
    local_only: bool = False
) -> List[KnowledgeItem]:
    """スキルを検索
    
    Args:
        query: 検索クエリ
        tags: タグ
        min_quality: 最小品質スコア
        local_only: ローカルのみ検索
        
    Returns:
        知識アイテムリスト
    """
    system = get_knowledge_sharing_system()
    return system.search_knowledge(
        query=query,
        item_type=KnowledgeType.SKILL,
        tags=tags,
        min_quality=min_quality,
        local_only=local_only
    )


def import_from_peer(
    peer_entity: str,
    item_id: Optional[str] = None,
    auto_integrate: bool = True
) -> Optional[KnowledgeItem]:
    """他のEntityから知識をインポート
    
    Args:
        peer_entity: 対象Entity ID
        item_id: 特定のアイテムID（Noneの場合は全て）
        auto_integrate: 自動統合するか
        
    Returns:
        取得した知識アイテム
    """
    system = get_knowledge_sharing_system()
    
    if item_id:
        return system.acquire_knowledge(item_id, peer_entity, auto_integrate)
    else:
        items = system.acquire_all_from_entity(peer_entity, auto_integrate=auto_integrate)
        return items[0] if items else None


def get_knowledge_stats() -> Dict[str, Any]:
    """知識共有の統計を取得
    
    Returns:
        統計情報
    """
    system = get_knowledge_sharing_system()
    return system.get_statistics()
