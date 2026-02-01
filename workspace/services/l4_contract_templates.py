#!/usr/bin/env python3
"""
L4 Smart Contract Template Generator
AI間取引のためのスマートコントラクトテンプレート生成
"""

import json
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
import time


class ContractType(Enum):
    """契約タイプ"""
    SERVICE = "service"
    ESCROW = "escrow"
    SUBSCRIPTION = "subscription"
    AUCTION = "auction"


class ContractStatus(Enum):
    """契約ステータス"""
    DRAFT = "draft"
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


@dataclass
class ServiceContract:
    """AIサービス契約テンプレート"""
    contract_id: str
    contract_type: str = "service"
    buyer_id: str = ""
    seller_id: str = ""
    service_type: str = ""
    description: str = ""
    terms: Dict[str, Any] = field(default_factory=dict)
    price: float = 0.0
    currency: str = "$ENTITY"
    delivery_time_hours: int = 24
    quality_threshold: float = 0.8
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None
    status: str = "draft"
    
    def __post_init__(self):
        if not self.contract_id:
            self.contract_id = f"svc_{uuid.uuid4().hex[:16]}"
        if not self.expires_at:
            self.expires_at = self.created_at + (self.delivery_time_hours * 3600)
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return asdict(self)
    
    def to_json(self) -> str:
        """JSON形式に変換"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    def compute_hash(self) -> str:
        """契約ハッシュを計算"""
        data = f"{self.contract_id}:{self.buyer_id}:{self.seller_id}:{self.price}:{self.created_at}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]


@dataclass
class EscrowContract:
    """エスクロー契約テンプレート"""
    escrow_id: str
    contract_type: str = "escrow"
    parties: List[str] = field(default_factory=list)
    amount: float = 0.0
    currency: str = "$ENTITY"
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    release_conditions: List[str] = field(default_factory=list)
    dispute_resolver: str = ""
    timeout_hours: int = 48
    created_at: float = field(default_factory=time.time)
    status: str = "draft"
    
    def __post_init__(self):
        if not self.escrow_id:
            self.escrow_id = f"esc_{uuid.uuid4().hex[:16]}"
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)
    
    def add_condition(self, name: str, condition_type: str, value: Any) -> None:
        """条件を追加"""
        self.conditions.append({
            "name": name,
            "type": condition_type,
            "value": value,
            "fulfilled": False
        })
    
    def check_all_conditions(self) -> bool:
        """全条件が満たされているか確認"""
        return all(c.get("fulfilled", False) for c in self.conditions)


@dataclass
class Milestone:
    """マイルストーン定義"""
    name: str
    description: str
    deliverables: List[str]
    payment_percent: float
    deadline_hours: int
    verification_method: str = "automatic"
    completed: bool = False


@dataclass
class MilestoneContract:
    """マイルストーンベース契約"""
    contract_id: str
    contract_type: str = "milestone"
    buyer_id: str = ""
    seller_id: str = ""
    total_amount: float = 0.0
    milestones: List[Milestone] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    status: str = "draft"
    
    def __post_init__(self):
        if not self.contract_id:
            self.contract_id = f"mil_{uuid.uuid4().hex[:16]}"
    
    def add_milestone(self, milestone: Milestone) -> None:
        """マイルストーンを追加"""
        self.milestones.append(milestone)
    
    def get_progress(self) -> float:
        """進捗率を計算"""
        if not self.milestones:
            return 0.0
        completed = sum(1 for m in self.milestones if m.completed)
        return completed / len(self.milestones)
    
    def get_next_milestone(self) -> Optional[Milestone]:
        """次の未完了マイルストーンを取得"""
        for m in self.milestones:
            if not m.completed:
                return m
        return None


def generate_service_contract(
    buyer: str,
    seller: str,
    service_type: str,
    terms: Dict[str, Any],
    price: float = 0.0,
    delivery_hours: int = 24,
    quality_threshold: float = 0.8
) -> ServiceContract:
    """
    AIサービス契約テンプレートを生成
    
    Args:
        buyer: 購入者ID
        seller: 販売者ID
        service_type: サービスタイプ
        terms: 契約条件
        price: 価格（$ENTITY）
        delivery_hours: 納期（時間）
        quality_threshold: 品質閾値
    
    Returns:
        ServiceContractインスタンス
    """
    contract = ServiceContract(
        contract_id=f"svc_{uuid.uuid4().hex[:16]}",
        buyer_id=buyer,
        seller_id=seller,
        service_type=service_type,
        description=terms.get("description", ""),
        terms=terms,
        price=price,
        delivery_time_hours=delivery_hours,
        quality_threshold=quality_threshold
    )
    return contract


def generate_escrow_contract(
    parties: List[str],
    amount: float,
    conditions: List[Dict[str, Any]],
    timeout_hours: int = 48,
    dispute_resolver: str = ""
) -> EscrowContract:
    """
    エスクロー契約を生成
    
    Args:
        parties: 関与者IDリスト
        amount: エスクロー金額
        conditions: 解放条件リスト
        timeout_hours: タイムアウト時間
        dispute_resolver: 紛争解決者ID
    
    Returns:
        EscrowContractインスタンス
    """
    contract = EscrowContract(
        escrow_id=f"esc_{uuid.uuid4().hex[:16]}",
        parties=parties,
        amount=amount,
        timeout_hours=timeout_hours,
        dispute_resolver=dispute_resolver
    )
    
    for condition in conditions:
        contract.add_condition(
            name=condition.get("name", "unnamed"),
            condition_type=condition.get("type", "generic"),
            value=condition.get("value")
        )
    
    return contract


def generate_milestone_contract(
    buyer: str,
    seller: str,
    total_amount: float,
    milestones: List[Dict[str, Any]]
) -> MilestoneContract:
    """
    マイルストーンベース契約を生成
    
    Args:
        buyer: 購入者ID
        seller: 販売者ID
        total_amount: 総額
        milestones: マイルストーン定義リスト
    
    Returns:
        MilestoneContractインスタンス
    """
    contract = MilestoneContract(
        contract_id=f"mil_{uuid.uuid4().hex[:16]}",
        buyer_id=buyer,
        seller_id=seller,
        total_amount=total_amount
    )
    
    for m_data in milestones:
        milestone = Milestone(
            name=m_data.get("name", "Milestone"),
            description=m_data.get("description", ""),
            deliverables=m_data.get("deliverables", []),
            payment_percent=m_data.get("payment_percent", 0.0),
            deadline_hours=m_data.get("deadline_hours", 24),
            verification_method=m_data.get("verification_method", "automatic")
        )
        contract.add_milestone(milestone)
    
    return contract


def validate_contract(contract_json: Union[str, Dict[str, Any]]) -> Dict[str, Any]:
    """
    契約を検証
    
    Args:
        contract_json: JSON文字列または辞書
    
    Returns:
        検証結果 {"valid": bool, "errors": List[str], "warnings": List[str]}
    """
    result = {
        "valid": True,
        "errors": [],
        "warnings": []
    }
    
    try:
        if isinstance(contract_json, str):
            contract = json.loads(contract_json)
        else:
            contract = contract_json
        
        # 必須フィールドの確認
        required_fields = ["contract_id", "contract_type"]
        for field_name in required_fields:
            if field_name not in contract:
                result["errors"].append(f"Missing required field: {field_name}")
                result["valid"] = False
        
        if not result["valid"]:
            return result
        
        # 契約タイプ別の検証
        contract_type = contract.get("contract_type")
        
        if contract_type == "service":
            # サービス契約の検証
            if "buyer_id" not in contract or "seller_id" not in contract:
                result["errors"].append("Service contract requires buyer_id and seller_id")
                result["valid"] = False
            
            if contract.get("price", 0) <= 0:
                result["errors"].append("Price must be positive")
                result["valid"] = False
            
            if contract.get("delivery_time_hours", 0) <= 0:
                result["warnings"].append("Delivery time should be positive")
        
        elif contract_type == "escrow":
            # エスクロー契約の検証
            parties = contract.get("parties", [])
            if len(parties) < 2:
                result["errors"].append("Escrow requires at least 2 parties")
                result["valid"] = False
            
            if contract.get("amount", 0) <= 0:
                result["errors"].append("Escrow amount must be positive")
                result["valid"] = False
        
        elif contract_type == "milestone":
            # マイルストーン契約の検証
            milestones = contract.get("milestones", [])
            if not milestones:
                result["errors"].append("Milestone contract requires at least one milestone")
                result["valid"] = False
            else:
                total_percent = sum(m.get("payment_percent", 0) for m in milestones)
                if abs(total_percent - 100.0) > 0.01:
                    result["warnings"].append(f"Milestone payment percentages sum to {total_percent}%, not 100%")
        
        else:
            result["warnings"].append(f"Unknown contract type: {contract_type}")
    
    except json.JSONDecodeError as e:
        result["errors"].append(f"Invalid JSON: {str(e)}")
        result["valid"] = False
    except Exception as e:
        result["errors"].append(f"Validation error: {str(e)}")
        result["valid"] = False
    
    return result


def merge_contracts(base_contract: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    契約をマージ
    
    Args:
        base_contract: 基本契約
        override: 上書き内容
    
    Returns:
        マージされた契約
    """
    merged = base_contract.copy()
    merged.update(override)
    return merged


# テンプレート定義
CONTRACT_TEMPLATES = {
    "simple_service": {
        "contract_type": "service",
        "description": "Simple AI service agreement",
        "terms": {
            "revision_count": 2,
            "support_period_days": 7,
            "payment_terms": "50% upfront, 50% on delivery"
        },
        "quality_threshold": 0.75
    },
    "premium_service": {
        "contract_type": "service",
        "description": "Premium AI service with SLA guarantee",
        "terms": {
            "revision_count": 5,
            "support_period_days": 30,
            "payment_terms": "30% upfront, 70% on delivery",
            "sla_uptime": 99.9,
            "penalty_clause": True
        },
        "quality_threshold": 0.9
    },
    "standard_escrow": {
        "contract_type": "escrow",
        "conditions": [
            {"name": "delivery_confirmed", "type": "boolean", "value": False},
            {"name": "quality_accepted", "type": "boolean", "value": False}
        ],
        "timeout_hours": 48
    },
    "milestone_project": {
        "contract_type": "milestone",
        "milestones": [
            {
                "name": "Phase 1: Requirements",
                "description": "Gather and finalize requirements",
                "payment_percent": 20.0,
                "deadline_hours": 48
            },
            {
                "name": "Phase 2: Development",
                "description": "Core development work",
                "payment_percent": 50.0,
                "deadline_hours": 168
            },
            {
                "name": "Phase 3: Delivery",
                "description": "Final delivery and handover",
                "payment_percent": 30.0,
                "deadline_hours": 24
            }
        ]
    }
}


def get_contract_template(template_name: str) -> Optional[Dict[str, Any]]:
    """
    契約テンプレートを取得
    
    Args:
        template_name: テンプレート名
    
    Returns:
        テンプレート辞書またはNone
    """
    return CONTRACT_TEMPLATES.get(template_name)


def list_templates() -> List[str]:
    """
    利用可能なテンプレート一覧を取得
    
    Returns:
        テンプレート名リスト
    """
    return list(CONTRACT_TEMPLATES.keys())


if __name__ == "__main__":
    # 動作確認
    print("=== L4 Contract Templates Demo ===\n")
    
    # サービス契約生成
    print("1. Service Contract:")
    svc_contract = generate_service_contract(
        buyer="buyer_agent_001",
        seller="seller_agent_042",
        service_type="code_generation",
        terms={
            "description": "Generate Python API client",
            "language": "Python",
            "lines_of_code": 500
        },
        price=25.0,
        delivery_hours=12
    )
    print(svc_contract.to_json())
    print(f"Hash: {svc_contract.compute_hash()}\n")
    
    # エスクロー契約生成
    print("2. Escrow Contract:")
    esc_contract = generate_escrow_contract(
        parties=["buyer_001", "seller_042"],
        amount=100.0,
        conditions=[
            {"name": "task_completed", "type": "boolean", "value": False},
            {"name": "code_review_passed", "type": "boolean", "value": False}
        ],
        timeout_hours=72
    )
    print(esc_contract.to_json())
    print()
    
    # マイルストーン契約生成
    print("3. Milestone Contract:")
    mil_contract = generate_milestone_contract(
        buyer="buyer_001",
        seller="seller_042",
        total_amount=500.0,
        milestones=[
            {
                "name": "Design Phase",
                "description": "Architecture design",
                "payment_percent": 20.0,
                "deadline_hours": 48
            },
            {
                "name": "Implementation",
                "description": "Core implementation",
                "payment_percent": 50.0,
                "deadline_hours": 120
            },
            {
                "name": "Testing & Delivery",
                "description": "Final testing and handover",
                "payment_percent": 30.0,
                "deadline_hours": 24
            }
        ]
    )
    print(json.dumps(mil_contract.to_dict(), indent=2))
    print(f"Progress: {mil_contract.get_progress()*100:.0f}%\n")
    
    # 検証テスト
    print("4. Validation Tests:")
    valid_result = validate_contract(svc_contract.to_dict())
    print(f"Service contract valid: {valid_result['valid']}")
    
    invalid_contract = {"contract_id": "bad", "contract_type": "service"}  # missing fields
    invalid_result = validate_contract(invalid_contract)
    print(f"Invalid contract errors: {invalid_result['errors']}")
    
    print("\n5. Templates Available:")
    for name in list_templates():
        print(f"  - {name}")
