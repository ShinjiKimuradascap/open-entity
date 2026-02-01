#!/usr/bin/env python3
"""
L4 AI Economy - Pricing Engine
AIサービスの動的価格決定エンジン

Formula: price = base_price * demand_factor * reputation_multiplier * urgency_factor
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
import math


class PricingType(Enum):
    """価格設定タイプ"""
    FIXED = "fixed"           # 固定価格
    DYNAMIC = "dynamic"       # 動的価格
    AUCTION = "auction"       # オークション
    PER_TOKEN = "per_token"   # トークン単位課金
    SUBSCRIPTION = "subscription"  # サブスクリプション


class ServiceCategory(Enum):
    """サービスカテゴリ (基本価格定義)"""
    COMPUTE = "compute"           # 1.0 $ENTITY/min
    STORAGE = "storage"           # 0.01 $ENTITY/MB
    API_CALL = "api_call"         # 0.1 $ENTITY/req
    ANALYSIS = "analysis"         # 5.0 $ENTITY/task
    CONTENT = "content"           # 2.0 $ENTITY/item
    COMMUNICATION = "communication"  # 0.5 $ENTITY/msg
    SECURITY = "security"         # 10.0 $ENTITY/audit
    GOVERNANCE = "governance"     # 1.0 $ENTITY/vote


# 基本価格表 (単位: AIC/$ENTITY)
BASE_PRICES = {
    ServiceCategory.COMPUTE: {"price": 1.0, "unit": "min", "description": "CPU/GPU resources"},
    ServiceCategory.STORAGE: {"price": 0.01, "unit": "MB", "description": "Data storage"},
    ServiceCategory.API_CALL: {"price": 0.1, "unit": "req", "description": "API requests"},
    ServiceCategory.ANALYSIS: {"price": 5.0, "unit": "task", "description": "Data analysis"},
    ServiceCategory.CONTENT: {"price": 2.0, "unit": "item", "description": "Content generation"},
    ServiceCategory.COMMUNICATION: {"price": 0.5, "unit": "msg", "description": "Message relay"},
    ServiceCategory.SECURITY: {"price": 10.0, "unit": "audit", "description": "Security audit"},
    ServiceCategory.GOVERNANCE: {"price": 1.0, "unit": "vote", "description": "Voting"},
}


@dataclass
class PricingFactors:
    """価格決定要因"""
    base_price: float
    demand_factor: float = 1.0      # 需要係数 (0.5 - 3.0)
    reputation_multiplier: float = 1.0  # 評価係数 (0.5 - 2.0)
    urgency_factor: float = 1.0     # 緊急度係数 (1.0 - 2.0)
    complexity_factor: float = 1.0  # 複雑さ係数 (1.0 - 3.0)
    
    def calculate(self) -> float:
        """最終価格を計算"""
        price = (
            self.base_price *
            self.demand_factor *
            self.reputation_multiplier *
            self.urgency_factor *
            self.complexity_factor
        )
        return round(price, 2)


@dataclass
class ServicePricing:
    """サービス価格定義"""
    service_id: str
    service_name: str
    category: ServiceCategory
    pricing_type: PricingType
    base_price: float
    unit: str
    min_price: float = 0.1
    max_price: Optional[float] = None
    
    def get_price_range(self) -> tuple:
        """価格レンジを取得"""
        if self.max_price:
            return (self.min_price, self.max_price)
        return (self.min_price, self.base_price * 5)  # 最大5倍まで


class DemandTracker:
    """需要トラッキングシステム"""
    
    def __init__(self):
        self.demand_history: Dict[str, List[datetime]] = {}
        self.current_requests: Dict[str, int] = {}
    
    def record_request(self, service_id: str):
        """リクエストを記録"""
        now = datetime.now()
        if service_id not in self.demand_history:
            self.demand_history[service_id] = []
        self.demand_history[service_id].append(now)
        
        # 古い記録を削除 (1時間以上前)
        cutoff = now.timestamp() - 3600
        self.demand_history[service_id] = [
            t for t in self.demand_history[service_id]
            if t.timestamp() > cutoff
        ]
    
    def get_demand_factor(self, service_id: str) -> float:
        """
        需要係数を計算
        - 低需要 (< 10/hour): 0.8 (ディスカウント)
        - 通常需要 (10-50/hour): 1.0
        - 高需要 (50-100/hour): 1.5
        - 過負荷 (> 100/hour): 2.0-3.0
        """
        if service_id not in self.demand_history:
            return 1.0
        
        requests_per_hour = len(self.demand_history[service_id])
        
        if requests_per_hour < 10:
            return 0.8
        elif requests_per_hour < 50:
            return 1.0
        elif requests_per_hour < 100:
            return 1.5
        else:
            # 100以上は対数的にスケール
            return min(3.0, 2.0 + math.log10(requests_per_hour / 100))


class PricingEngine:
    """価格決定エンジン"""
    
    def __init__(self):
        self.demand_tracker = DemandTracker()
        self.service_pricings: Dict[str, ServicePricing] = {}
        self._initialize_default_pricings()
    
    def _initialize_default_pricings(self):
        """デフォルトサービス価格を初期化"""
        defaults = [
            ("CODE_GEN", "Code Generation", ServiceCategory.CONTENT, 10.0, "task"),
            ("CODE_REVIEW", "Code Review", ServiceCategory.ANALYSIS, 5.0, "task"),
            ("DOC_CREATE", "Documentation", ServiceCategory.CONTENT, 3.0, "task"),
            ("RESEARCH", "Research", ServiceCategory.ANALYSIS, 15.0, "task"),
            ("BUG_FIX", "Bug Fix", ServiceCategory.ANALYSIS, 8.0, "task"),
            ("API_CALL", "API Call", ServiceCategory.API_CALL, 0.1, "req"),
        ]
        
        for service_id, name, category, base_price, unit in defaults:
            self.service_pricings[service_id] = ServicePricing(
                service_id=service_id,
                service_name=name,
                category=category,
                pricing_type=PricingType.DYNAMIC,
                base_price=base_price,
                unit=unit
            )
    
    def calculate_price(
        self,
        service_id: str,
        reputation_score: float = 50.0,
        urgency_level: int = 1,
        complexity_score: float = 1.0
    ) -> Dict:
        """
        サービス価格を計算
        
        Args:
            service_id: サービスID
            reputation_score: 評価スコア (0-100)
            urgency_level: 緊急度 (1-5)
            complexity_score: 複雑さスコア (1.0-3.0)
        
        Returns:
            価格情報の辞書
        """
        if service_id not in self.service_pricings:
            return {"error": f"Unknown service: {service_id}"}
        
        pricing = self.service_pricings[service_id]
        
        # 需要係数
        demand_factor = self.demand_tracker.get_demand_factor(service_id)
        
        # 評価係数 (高評価 = 高価格でも受注可能)
        reputation_multiplier = 0.5 + (reputation_score / 100) * 1.5  # 0.5 - 2.0
        
        # 緊急度係数
        urgency_factor = 1.0 + (urgency_level - 1) * 0.25  # 1.0 - 2.0
        
        # 複雑さ係数
        complexity_factor = max(1.0, min(3.0, complexity_score))
        
        # 価格計算
        factors = PricingFactors(
            base_price=pricing.base_price,
            demand_factor=demand_factor,
            reputation_multiplier=reputation_multiplier,
            urgency_factor=urgency_factor,
            complexity_factor=complexity_factor
        )
        
        final_price = factors.calculate()
        
        # 最小/最大価格の適用
        min_p, max_p = pricing.get_price_range()
        final_price = max(min_p, min(max_p, final_price))
        
        return {
            "service_id": service_id,
            "service_name": pricing.service_name,
            "base_price": pricing.base_price,
            "unit": pricing.unit,
            "final_price": final_price,
            "factors": {
                "demand": demand_factor,
                "reputation": reputation_multiplier,
                "urgency": urgency_factor,
                "complexity": complexity_factor
            },
            "pricing_type": pricing.pricing_type.value
        }
    
    def get_service_list(self) -> List[Dict]:
        """サービス一覧を取得"""
        return [
            {
                "service_id": p.service_id,
                "name": p.service_name,
                "category": p.category.value,
                "base_price": p.base_price,
                "unit": p.unit,
                "type": p.pricing_type.value
            }
            for p in self.service_pricings.values()
        ]


def demo():
    """デモンストレーション"""
    print("=" * 60)
    print("L4 AI Economy - Pricing Engine Demo")
    print("=" * 60)
    
    engine = PricingEngine()
    
    # サービス一覧
    print("\n📋 Available Services:")
    for svc in engine.get_service_list():
        print(f"  {svc['service_id']}: {svc['name']} ({svc['base_price']} AIC/{svc['unit']})")
    
    # 価格計算例
    test_cases = [
        ("CODE_GEN", 50, 1, 1.0, "Standard"),
        ("CODE_GEN", 90, 3, 2.0, "High reputation + Urgent + Complex"),
        ("CODE_REVIEW", 70, 1, 1.0, "Good reputation"),
        ("RESEARCH", 30, 5, 3.0, "Low rep + Very urgent + Very complex"),
    ]
    
    print("\n💰 Price Calculations:")
    print("-" * 60)
    
    for service_id, rep, urgency, complexity, desc in test_cases:
        result = engine.calculate_price(service_id, rep, urgency, complexity)
        print(f"\n  {result['service_name']} ({desc})")
        print(f"    Base: {result['base_price']} AIC → Final: {result['final_price']} AIC")
        print(f"    Factors: demand={result['factors']['demand']:.2f}, "
              f"reputation={result['factors']['reputation']:.2f}, "
              f"urgency={result['factors']['urgency']:.2f}, "
              f"complexity={result['factors']['complexity']:.2f}")
    
    print("\n" + "=" * 60)
    print("✅ Pricing Engine Ready!")
    print("=" * 60)


if __name__ == "__main__":
    demo()
