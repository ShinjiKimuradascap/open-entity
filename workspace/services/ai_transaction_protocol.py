#!/usr/bin/env python3
"""
AI間取引プロトコル v1.0
AIエージェント間での自律的なサービス取引を実現するプロトコル
"""

import json
import uuid
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Optional, Dict, List, Any

try:
    from crypto import SecureMessage, MessageSigner
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

logger = logging.getLogger(__name__)


class TransactionStatus(Enum):
    """取引状態"""
    PROPOSED = "proposed"       # 提案中
    QUOTED = "quoted"           # 見積もり返信済み
    AGREED = "agreed"           # 合意済み
    ESCROW_LOCKED = "escrow_locked"  # エスクローにロック
    IN_PROGRESS = "in_progress" # 実行中
    COMPLETED = "completed"     # 完了
    RELEASED = "released"       # 支払い解放済み
    CANCELLED = "cancelled"     # キャンセル
    EXPIRED = "expired"         # 期限切れ
    DISPUTED = "disputed"       # 紛争中


@dataclass
class TaskProposal:
    """タスク提案メッセージ
    
    ClientがProviderに送信するサービス依頼の提案書
    
    Attributes:
        proposal_id: 提案固有ID（UUID）
        client_id: 依頼元エージェントID
        provider_id: 依頼先エージェントID（任意）
        task_type: サービスタイプ
        title: タスクタイトル
        description: タスク説明
        requirements: 要件詳細リスト
        budget_max: 予算上限
        deadline: 希望納期
        signature: Ed25519署名
        created_at: 作成日時
        valid_until: 有効期限
    """
    
    # 基本情報
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    client_id: str = ""
    provider_id: Optional[str] = None  # None = 任意のProviderへ公開
    
    # タスク内容
    task_type: str = "custom"
    title: str = ""
    description: str = ""
    requirements: List[str] = field(default_factory=list)
    
    # 条件
    budget_max: float = 0.0
    deadline: Optional[str] = None
    
    # メタデータ
    signature: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    valid_until: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換"""
        return asdict(self)
    
    def to_json(self) -> str:
        """JSON文字列に変換"""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskProposal":
        """辞書から作成"""
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "TaskProposal":
        """JSON文字列から作成"""
        return cls.from_dict(json.loads(json_str))
    
    def is_expired(self) -> bool:
        """期限切れかチェック"""
        try:
            valid_until = datetime.fromisoformat(self.valid_until.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > valid_until
        except ValueError:
            return True
    
    def sign(self, signer: "MessageSigner") -> None:
        """提案に署名"""
        data = self.to_dict()
        data.pop('signature', None)
        message = json.dumps(data, sort_keys=True)
        self.signature = signer.sign(message.encode()).hex()
    
    def verify_signature(self, verifier) -> bool:
        """署名を検証"""
        if not self.signature:
            return False
        data = self.to_dict()
        data.pop('signature', None)
        message = json.dumps(data, sort_keys=True)
        return verifier.verify(message.encode(), bytes.fromhex(self.signature))


@dataclass
class TaskQuote:
    """タスク見積もりメッセージ
    
    ProviderがClientに返信する見積もり
    
    Attributes:
        quote_id: 見積もり固有ID（UUID）
        proposal_id: 元の提案ID
        provider_id: 見積もり作成者
        estimated_amount: 見積額
        estimated_time_seconds: 見積時間（秒）
        terms: 取引条件
        valid_until: 有効期限
        signature: Ed25519署名
        created_at: 作成日時
    """
    
    # 基本情報
    quote_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    proposal_id: str = ""
    provider_id: str = ""
    
    # 見積もり内容
    estimated_amount: float = 0.0
    estimated_time_seconds: int = 0
    terms: Dict[str, Any] = field(default_factory=dict)
    
    # メタデータ
    valid_until: str = field(default_factory=lambda: (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat())
    signature: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskQuote":
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "TaskQuote":
        return cls.from_dict(json.loads(json_str))
    
    def is_expired(self) -> bool:
        """期限切れかチェック"""
        try:
            valid_until = datetime.fromisoformat(self.valid_until.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > valid_until
        except ValueError:
            return True
    
    def sign(self, signer: "MessageSigner") -> None:
        """見積もりに署名"""
        data = self.to_dict()
        data.pop('signature', None)
        message = json.dumps(data, sort_keys=True)
        self.signature = signer.sign(message.encode()).hex()


@dataclass
class Agreement:
    """取引合意メッセージ
    
    ClientとProviderの合意形成を示す
    
    Attributes:
        agreement_id: 合意固有ID（UUID）
        quote_id: 元の見積もりID
        proposal_id: 元の提案ID
        task_id: タスクID（生成される）
        client_id: ClientエージェントID
        provider_id: ProviderエージェントID
        confirmed_amount: 確定金額
        escrow_address: エスクローアドレス
        deadline: 期限
        client_signature: Clientの署名
        provider_signature: Providerの署名
        created_at: 作成日時
    """
    
    # 基本情報
    agreement_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    quote_id: str = ""
    proposal_id: str = ""
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    # 当事者
    client_id: str = ""
    provider_id: str = ""
    
    # 条件
    confirmed_amount: float = 0.0
    escrow_address: Optional[str] = None
    deadline: Optional[str] = None
    
    # 署名
    client_signature: Optional[str] = None
    provider_signature: Optional[str] = None
    
    # メタデータ
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: str = TransactionStatus.AGREED.value
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Agreement":
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Agreement":
        return cls.from_dict(json.loads(json_str))
    
    def is_fully_signed(self) -> bool:
        """両者の署名が揃っているか"""
        return bool(self.client_signature and self.provider_signature)
    
    def sign_as_client(self, signer: "MessageSigner") -> None:
        """Clientとして署名"""
        data = self.to_dict()
        data.pop('client_signature', None)
        data.pop('provider_signature', None)
        message = json.dumps(data, sort_keys=True)
        self.client_signature = signer.sign(message.encode()).hex()
    
    def sign_as_provider(self, signer: "MessageSigner") -> None:
        """Providerとして署名"""
        data = self.to_dict()
        data.pop('client_signature', None)
        data.pop('provider_signature', None)
        message = json.dumps(data, sort_keys=True)
        self.provider_signature = signer.sign(message.encode()).hex()


class AITransactionManager:
    """AI間取引マネージャー
    
    取引のライフサイクルを管理する
    """
    
    def __init__(self):
        self._transactions: Dict[str, Dict[str, Any]] = {}
        self._proposals: Dict[str, TaskProposal] = {}
        self._quotes: Dict[str, TaskQuote] = {}
        self._agreements: Dict[str, Agreement] = {}
    
    def create_proposal(self, client_id: str, title: str, description: str,
                       budget_max: float, task_type: str = "custom",
                       requirements: List[str] = None) -> TaskProposal:
        """新しい提案を作成"""
        proposal = TaskProposal(
            client_id=client_id,
            title=title,
            description=description,
            budget_max=budget_max,
            task_type=task_type,
            requirements=requirements or []
        )
        self._proposals[proposal.proposal_id] = proposal
        return proposal
    
    def create_quote(self, proposal_id: str, provider_id: str,
                    estimated_amount: float, estimated_time_seconds: int = 3600,
                    terms: Dict[str, Any] = None) -> Optional[TaskQuote]:
        """見積もりを作成"""
        if proposal_id not in self._proposals:
            return None
        
        quote = TaskQuote(
            proposal_id=proposal_id,
            provider_id=provider_id,
            estimated_amount=estimated_amount,
            estimated_time_seconds=estimated_time_seconds,
            terms=terms or {}
        )
        self._quotes[quote.quote_id] = quote
        return quote
    
    def create_agreement(self, quote_id: str) -> Optional[Agreement]:
        """合意を作成"""
        if quote_id not in self._quotes:
            return None
        
        quote = self._quotes[quote_id]
        proposal = self._proposals.get(quote.proposal_id)
        if not proposal:
            return None
        
        agreement = Agreement(
            quote_id=quote_id,
            proposal_id=quote.proposal_id,
            client_id=proposal.client_id,
            provider_id=quote.provider_id,
            confirmed_amount=quote.estimated_amount,
            deadline=proposal.deadline
        )
        self._agreements[agreement.agreement_id] = agreement
        return agreement
    
    def get_transaction_status(self, agreement_id: str) -> Optional[TransactionStatus]:
        """取引状態を取得"""
        if agreement_id not in self._agreements:
            return None
        return TransactionStatus(self._agreements[agreement_id].status)
    
    def update_status(self, agreement_id: str, status: TransactionStatus) -> bool:
        """取引状態を更新"""
        if agreement_id not in self._agreements:
            return False
        self._agreements[agreement_id].status = status.value
        return True


# グローバルマネージャーインスタンス
_transaction_manager: Optional[AITransactionManager] = None


def get_transaction_manager() -> AITransactionManager:
    """グローバル取引マネージャーを取得"""
    global _transaction_manager
    if _transaction_manager is None:
        _transaction_manager = AITransactionManager()
    return _transaction_manager
