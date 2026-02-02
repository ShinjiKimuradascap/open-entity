#!/usr/bin/env python3
"""
Matching Engine
L2自動マッチングアルゴリズム

Features:
- 購入者の要件に最適なサービス提供者を自動マッチング
- 複合スコア計算（カテゴリ、価格、評価、納期）
- 代替案検索機能
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

# 既存サービスのインポート
try:
    from services.task_marketplace import (
        TaskMarketplace, ServiceListing, ListingStatus,
        ServiceType, PricingModel
    )
    from services.skill_registry import SkillRegistry, SkillCategory
except ImportError:
    from task_marketplace import (
        TaskMarketplace, ServiceListing, ListingStatus,
        ServiceType, PricingModel
    )
    from skill_registry import SkillRegistry, SkillCategory

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """マッチング結果
    
    Attributes:
        listing_id: 出品ID
        provider_id: 提供者ID
        match_score: マッチングスコア (0-100)
        price: 価格
        rating: 評価スコア
        estimated_delivery: 予想納期（日数）
        match_reasons: マッチ理由リスト
    """
    listing_id: str
    provider_id: str
    match_score: float
    price: float
    rating: float
    estimated_delivery: int
    match_reasons: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "listing_id": self.listing_id,
            "provider_id": self.provider_id,
            "match_score": round(self.match_score, 2),
            "price": self.price,
            "rating": round(self.rating, 2),
            "estimated_delivery": self.estimated_delivery,
            "match_reasons": self.match_reasons
        }


class MatchingEngine:
    """マッチングエンジン
    
    購入者の要件に最適なサービス提供者を自動的にマッチングするエンジン。
    複合スコア計算により多角的な評価を行う。
    
    スコア計算式:
        スコア = (カテゴリ一致率 × 0.4) + (価格適合度 × 0.3) + 
                (評価スコア × 0.2) + (納期適合度 × 0.1)
    """
    
    # スコア計算の重み
    WEIGHT_CATEGORY = 0.4
    WEIGHT_PRICE = 0.3
    WEIGHT_RATING = 0.2
    WEIGHT_DELIVERY = 0.1
    
    def __init__(
        self,
        marketplace: Optional[TaskMarketplace] = None,
        skill_registry: Optional[SkillRegistry] = None,
        reputation_manager: Optional[Any] = None,
        data_dir: str = "data/matching_engine"
    ):
        """初期化
        
        Args:
            marketplace: TaskMarketplaceインスタンス
            skill_registry: SkillRegistryインスタンス
            reputation_manager: ReputationManagerインスタンス（オプショナル）
            data_dir: データ保存ディレクトリ
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 依存サービス
        self.marketplace = marketplace or TaskMarketplace()
        self.skill_registry = skill_registry or SkillRegistry()
        self.reputation_manager = reputation_manager
        
        # マッチング履歴
        self.match_history: List[Dict[str, Any]] = []
        
        logger.info("MatchingEngine initialized")
    
    def match_service(
        self,
        requirements: Dict[str, Any]
    ) -> List[MatchResult]:
        """サービスマッチング
        
        要件に最適なサービス提供者を検索・ランキングする。
        
        Args:
            requirements: 要件辞書
                - category: 必須 - サービスカテゴリ
                - max_price: 任意 - 最大予算
                - min_rating: 任意 - 最低評価スコア（0-5）
                - required_skills: 任意 - 必要スキルリスト
                - deadline_days: 任意 - 希望納期（日数）
                - preferred_providers: 任意 - 優先提供者リスト
        
        Returns:
            List[MatchResult]: マッチング結果リスト（スコア降順）
        """
        category = requirements.get("category")
        if not category:
            raise ValueError("category is required")
        
        # アクティブな出品を取得
        active_listings = self._get_active_listings(category)
        
        if not active_listings:
            logger.info(f"No active listings found for category: {category}")
            return []
        
        # 各出品のマッチングスコアを計算
        results: List[MatchResult] = []
        for listing in active_listings:
            score, reasons = self.calculate_match_score(listing, requirements)
            if score > 0:  # スコアが0より大きいもののみ結果に含める
                result = MatchResult(
                    listing_id=listing.listing_id,
                    provider_id=listing.provider_id,
                    match_score=score * 100,  # パーセンテージ表示
                    price=listing.price,
                    rating=listing.rating,
                    estimated_delivery=self._estimate_delivery(listing, requirements),
                    match_reasons=reasons
                )
                results.append(result)
        
        # スコア降順にソート
        results.sort(key=lambda x: x.match_score, reverse=True)
        
        # 履歴に保存
        self._save_match_history(requirements, results)
        
        logger.info(f"Found {len(results)} matches for category '{category}'")
        return results
    
    def calculate_match_score(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> Tuple[float, List[str]]:
        """マッチングスコア計算
        
        スコア = (カテゴリ一致率 × 0.4) + (価格適合度 × 0.3) + 
                (評価スコア × 0.2) + (納期適合度 × 0.1)
        
        Args:
            listing: サービス出品情報
            requirements: 要件辞書
        
        Returns:
            Tuple[float, List[str]]: (スコア 0-1, マッチ理由リスト)
        """
        reasons: List[str] = []
        
        # 1. カテゴリ一致率 (40%)
        category_score = self._calculate_category_score(listing, requirements)
        if category_score > 0:
            reasons.append(f"Category match: {category_score:.0%}")
        
        # 2. 価格適合度 (30%)
        price_score = self._calculate_price_score(listing, requirements)
        if price_score > 0:
            max_price = requirements.get("max_price")
            if max_price:
                reasons.append(f"Price within budget: ${listing.price}")
            else:
                reasons.append(f"Price: ${listing.price}")
        
        # 3. 評価スコア (20%)
        rating_score = self._calculate_rating_score(listing, requirements)
        if rating_score > 0:
            if listing.rating > 0:
                reasons.append(f"High rating: {listing.rating:.1f}/5.0")
            else:
                reasons.append("New provider")
        
        # 4. 納期適合度 (10%)
        delivery_score = self._calculate_delivery_score(listing, requirements)
        if delivery_score > 0 and requirements.get("deadline_days"):
            reasons.append(f"Can meet deadline ({requirements['deadline_days']} days)")
        
        # 合計スコア計算
        total_score = (
            category_score * self.WEIGHT_CATEGORY +
            price_score * self.WEIGHT_PRICE +
            rating_score * self.WEIGHT_RATING +
            delivery_score * self.WEIGHT_DELIVERY
        )
        
        # スキルマッチングボーナス
        skill_bonus = self._calculate_skill_bonus(listing, requirements)
        if skill_bonus > 0:
            total_score += skill_bonus
            reasons.append("Has required skills")
        
        # 優先提供者ボーナス
        preferred = requirements.get("preferred_providers", [])
        if listing.provider_id in preferred:
            total_score += 0.1  # 10%ボーナス
            reasons.append("Preferred provider")
        
        return min(total_score, 1.0), reasons
    
    def get_top_matches(
        self,
        requirements: Dict[str, Any],
        limit: int = 5
    ) -> List[MatchResult]:
        """トップマッチング結果取得
        
        Args:
            requirements: 要件辞書
            limit: 返す結果の最大数
        
        Returns:
            List[MatchResult]: トップマッチング結果
        """
        all_matches = self.match_service(requirements)
        return all_matches[:limit]
    
    def find_alternatives(
        self,
        listing_id: str,
        limit: int = 3
    ) -> List[MatchResult]:
        """代替案検索
        
        指定された出品と同じカテゴリの代替サービスを検索する。
        
        Args:
            listing_id: 基準となる出品ID
            limit: 返す代替案の最大数
        
        Returns:
            List[MatchResult]: 代替マッチング結果
        """
        # 基準出品を取得
        listing = self.marketplace.listings.get(listing_id)
        if not listing:
            logger.warning(f"Listing {listing_id} not found")
            return []
        
        # 同じカテゴリのサービスを検索
        requirements = {
            "category": listing.category,
            "max_price": listing.price * 1.2,  # 20%高くてもOK
            "min_rating": max(0, listing.rating - 1.0) if listing.rating > 0 else 0
        }
        
        matches = self.match_service(requirements)
        
        # 自身を除外
        alternatives = [m for m in matches if m.listing_id != listing_id]
        
        return alternatives[:limit]
    
    def get_match_history(
        self,
        category: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """マッチング履歴取得
        
        Args:
            category: カテゴリフィルタ
            limit: 最大件数
        
        Returns:
            List[Dict[str, Any]]: マッチング履歴
        """
        history = self.match_history
        
        if category:
            history = [
                h for h in history 
                if h.get("requirements", {}).get("category") == category
            ]
        
        return history[-limit:]
    
    def _get_active_listings(self, category: Optional[str] = None) -> List[ServiceListing]:
        """アクティブな出品を取得
        
        Args:
            category: カテゴリフィルタ
        
        Returns:
            List[ServiceListing]: アクティブな出品リスト
        """
        all_listings = self.marketplace.listings.values()
        active_listings = [
            l for l in all_listings 
            if l.status == ListingStatus.ACTIVE
        ]
        
        if category:
            active_listings = [
                l for l in active_listings 
                if l.category.lower() == category.lower()
            ]
        
        return active_listings
    
    def _calculate_category_score(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> float:
        """カテゴリ一致率計算
        
        Args:
            listing: サービス出品
            requirements: 要件
        
        Returns:
            float: カテゴリスコア (0-1)
        """
        category = requirements.get("category", "").lower()
        
        if not category:
            return 0.5
        
        # 完全一致
        if listing.category.lower() == category:
            return 1.0
        
        # 部分一致
        if category in listing.category.lower() or listing.category.lower() in category:
            return 0.7
        
        # タグ一致
        for tag in listing.tags:
            if category in tag.lower():
                return 0.6
        
        return 0.0
    
    def _calculate_price_score(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> float:
        """価格適合度計算
        
        Args:
            listing: サービス出品
            requirements: 要件
        
        Returns:
            float: 価格スコア (0-1)
        """
        max_price = requirements.get("max_price")
        
        if max_price is None:
            # 予算指定なし - 市場価格との比較
            return self._calculate_market_price_score(listing)
        
        if listing.price > max_price:
            return 0.0
        
        # 予算内であれば、安いほど高スコア
        ratio = listing.price / max_price
        return 1.0 - (ratio * 0.5)  # 0.5-1.0の範囲
    
    def _calculate_market_price_score(self, listing: ServiceListing) -> float:
        """市場価格に対するスコア計算
        
        Args:
            listing: サービス出品
        
        Returns:
            float: 市場価格スコア
        """
        category_listings = [
            l for l in self.marketplace.listings.values()
            if l.category == listing.category and l.status == ListingStatus.ACTIVE
        ]
        
        if not category_listings:
            return 0.7
        
        avg_price = sum(l.price for l in category_listings) / len(category_listings)
        
        if avg_price == 0:
            return 0.7
        
        # 平均価格より安いほど高スコア（ただし極端に安いと疑わしい）
        ratio = listing.price / avg_price
        if ratio <= 0.5:
            return 0.9  # かなり安い
        elif ratio <= 1.0:
            return 0.8 + (1.0 - ratio) * 0.2
        elif ratio <= 1.5:
            return 0.6
        else:
            return 0.4
    
    def _calculate_rating_score(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> float:
        """評価スコア計算
        
        Args:
            listing: サービス出品
            requirements: 要件
        
        Returns:
            float: 評価スコア (0-1)
        """
        min_rating = requirements.get("min_rating", 0)
        
        if listing.rating < min_rating:
            return 0.0
        
        if listing.rating == 0:
            # 評価なし（新規）
            return 0.5
        
        # 5点満点を0-1に正規化
        return listing.rating / 5.0
    
    def _calculate_delivery_score(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> float:
        """納期適合度計算
        
        Args:
            listing: サービス出品
            requirements: 要件
        
        Returns:
            float: 納期スコア (0-1)
        """
        deadline_days = requirements.get("deadline_days")
        
        if deadline_days is None:
            return 0.7  # 納期指定なし
        
        # 納期見積もり
        estimated = self._estimate_delivery(listing, requirements)
        
        if estimated <= deadline_days:
            return 1.0
        elif estimated <= deadline_days * 1.2:
            return 0.7
        elif estimated <= deadline_days * 1.5:
            return 0.4
        else:
            return 0.0
    
    def _calculate_skill_bonus(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> float:
        """スキルマッチングボーナス計算
        
        Args:
            listing: サービス出品
            requirements: 要件
        
        Returns:
            float: スキルボーナス (0-0.1)
        """
        required_skills = requirements.get("required_skills", [])
        
        if not required_skills:
            return 0.0
        
        # 提供者のスキルを取得
        provider_skills = self.skill_registry.get_agent_skills(listing.provider_id)
        
        if not provider_skills:
            return 0.0
        
        # スキル名リスト
        provider_skill_names = {s.name.lower() for s in provider_skills}
        
        # 一致スキル数
        matched = sum(
            1 for skill in required_skills 
            if skill.lower() in provider_skill_names
        )
        
        if matched == 0:
            return 0.0
        
        # 最大10%のボーナス
        ratio = matched / len(required_skills)
        return min(ratio * 0.1, 0.1)
    
    def _estimate_delivery(
        self,
        listing: ServiceListing,
        requirements: Dict[str, Any]
    ) -> int:
        """納期見積もり
        
        Args:
            listing: サービス出品
            requirements: 要件
        
        Returns:
            int: 予想納期（日数）
        """
        # 基本納期
        base_delivery = 7
        
        # サービスタイプによる調整
        service_type_multipliers = {
            "code_service": 1.0,
            "research_service": 1.5,
            "design_service": 1.2,
            "validation_service": 0.8
        }
        
        multiplier = service_type_multipliers.get(
            listing.service_type.value, 1.0
        )
        
        # 実績がある場合は実績を参考に
        if listing.completed_orders > 0:
            # 実績に応じて短縮（最大20%）
            experience_bonus = min(listing.completed_orders * 0.02, 0.2)
            multiplier *= (1.0 - experience_bonus)
        
        return max(1, int(base_delivery * multiplier))
    
    def _save_match_history(
        self,
        requirements: Dict[str, Any],
        results: List[MatchResult]
    ) -> None:
        """マッチング履歴を保存
        
        Args:
            requirements: 要件
            results: マッチング結果
        """
        history_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requirements": requirements,
            "results_count": len(results),
            "top_match": results[0].to_dict() if results else None,
            "all_matches": [r.to_dict() for r in results[:10]]  # 上位10件のみ
        }
        
        self.match_history.append(history_entry)
        
        # 永続化
        history_file = self.data_dir / "match_history.json"
        try:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(self.match_history[-1000:], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save match history: {e}")
    
    def get_matching_stats(self) -> Dict[str, Any]:
        """マッチング統計情報取得
        
        Returns:
            Dict[str, Any]: 統計情報
        """
        if not self.match_history:
            return {
                "total_searches": 0,
                "avg_results_per_search": 0,
                "top_categories": [],
                "avg_top_match_score": 0
            }
        
        total_searches = len(self.match_history)
        
        # 平均結果数
        avg_results = sum(
            h["results_count"] for h in self.match_history
        ) / total_searches
        
        # カテゴリ別検索回数
        category_counts: Dict[str, int] = {}
        for h in self.match_history:
            cat = h.get("requirements", {}).get("category", "unknown")
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        top_categories = sorted(
            category_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]
        
        # 平均トップマッチスコア
        scores = [
            h["top_match"]["match_score"] 
            for h in self.match_history 
            if h.get("top_match")
        ]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        return {
            "total_searches": total_searches,
            "avg_results_per_search": round(avg_results, 2),
            "top_categories": [
                {"category": c, "count": n} for c, n in top_categories
            ],
            "avg_top_match_score": round(avg_score, 2)
        }


# テスト・デモ用関数
def demo_matching_engine():
    """マッチングエンジンのデモ"""
    print("=" * 60)
    print("L2 Matching Engine Demo")
    print("=" * 60)
    
    # マッチングエンジン初期化
    engine = MatchingEngine()
    
    # テストデータ作成
    marketplace = engine.marketplace
    
    # 出品を作成
    print("\n1. Creating test listings...")
    
    listings_data = [
        {
            "provider_id": "agent_a",
            "service_type": ServiceType.CODE_SERVICE,
            "title": "Python Code Review",
            "description": "Professional Python code review and optimization",
            "price": 50.0,
            "pricing_model": PricingModel.FIXED_PRICE,
            "category": "programming"
        },
        {
            "provider_id": "agent_b",
            "service_type": ServiceType.DESIGN_SERVICE,
            "title": "API Design",
            "description": "RESTful API design and documentation",
            "price": 40.0,
            "pricing_model": PricingModel.FIXED_PRICE,
            "category": "design"
        },
        {
            "provider_id": "agent_c",
            "service_type": ServiceType.RESEARCH_SERVICE,
            "title": "Market Research",
            "description": "AI market research and analysis",
            "price": 60.0,
            "pricing_model": PricingModel.FIXED_PRICE,
            "category": "research"
        },
        {
            "provider_id": "agent_d",
            "service_type": ServiceType.CODE_SERVICE,
            "title": "Fast Python Development",
            "description": "Quick Python development services",
            "price": 45.0,
            "pricing_model": PricingModel.FIXED_PRICE,
            "category": "programming"
        }
    ]
    
    created_listings = []
    for data in listings_data:
        listing_id = marketplace.create_listing(**data)
        listing = marketplace.listings[listing_id]
        created_listings.append(listing)
        print(f"  Created: {listing.title} (${listing.price})")
    
    # 評価を設定
    marketplace.update_listing(
        created_listings[0].listing_id,
        rating=4.5,
        completed_orders=10
    )
    marketplace.update_listing(
        created_listings[3].listing_id,
        rating=4.8,
        completed_orders=25
    )
    
    # スキル登録
    print("\n2. Registering skills...")
    skill_registry = engine.skill_registry
    
    skill_registry.register_skill(
        agent_id="agent_a",
        category=SkillCategory.PROGRAMMING,
        name="Python",
        level=5,
        description="Expert Python developer"
    )
    skill_registry.register_skill(
        agent_id="agent_d",
        category=SkillCategory.PROGRAMMING,
        name="Python",
        level=4,
        description="Advanced Python developer"
    )
    
    print("  Skills registered")
    
    # マッチングテスト
    print("\n3. Testing match_service()...")
    
    requirements = {
        "category": "programming",
        "max_price": 50.0,
        "min_rating": 4.0,
        "required_skills": ["Python"],
        "deadline_days": 10
    }
    
    matches = engine.match_service(requirements)
    
    print(f"  Found {len(matches)} matches:")
    for i, match in enumerate(matches[:3], 1):
        print(f"    {i}. {match.provider_id}")
        print(f"       Score: {match.match_score:.1f}%")
        print(f"       Price: ${match.price}")
        print(f"       Rating: {match.rating}")
        print(f"       Reasons: {', '.join(match.match_reasons)}")
    
    # トップマッチテスト
    print("\n4. Testing get_top_matches()...")
    
    top_matches = engine.get_top_matches(requirements, limit=2)
    print(f"  Top {len(top_matches)} matches:")
    for match in top_matches:
        print(f"    - {match.provider_id} (Score: {match.match_score:.1f}%)")
    
    # 代替案検索テスト
    print("\n5. Testing find_alternatives()...")
    
    if matches:
        alternatives = engine.find_alternatives(matches[0].listing_id, limit=2)
        print(f"  Found {len(alternatives)} alternatives")
        for alt in alternatives:
            print(f"    - {alt.provider_id} (${alt.price})")
    
    # 統計情報
    print("\n6. Statistics:")
    stats = engine.get_matching_stats()
    print(f"  Total searches: {stats['total_searches']}")
    print(f"  Avg results per search: {stats['avg_results_per_search']}")
    print(f"  Avg top match score: {stats['avg_top_match_score']}%")
    
    print("\n" + "=" * 60)
    print("Demo completed successfully!")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo_matching_engine()
