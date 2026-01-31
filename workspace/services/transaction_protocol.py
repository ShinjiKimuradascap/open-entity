#!/usr/bin/env python3
"""
AI間取引プロトコル v1.0

AIエージェント間での自律的なサービス取引を実現するプロトコル。
AICトークンを使用した自動決済と、スマートコントラクトによるエスクロー機能を提供する。
"""

import json
import base64
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum, auto

from services.crypto import CryptoManager, KeyPair, generate_entity_keypair


class TransactionState(Enum):
    """取引状態"""
    PROPOSED = auto()
    QUOTED = auto()
    AGREED = auto()
    LOCKED = auto()
    EXECUTING = auto()
    COMPLETED = auto()
    RELEASED = auto()
    CANCELLED = auto()
    EXPIRED = auto()
    DISPUTED = auto()


class TaskType(Enum):
    """タスクタイプ"""
    CODE_REVIEW = "code_review"
    CODE_GENERATION = "code_generation"
    DATA_ANALYSIS = "data_analysis"
    DOCUMENTATION = "documentation"
    TESTING = "testing"
    CONSULTATION = "consultation"
    OTHER = "other"


@dataclass
class TaskProposal:
    """
    タスク提案メッセージ
    
    ClientがProviderに送信するサービス依頼の提案書
    """
    proposal_id: str
    task_type: str
    description: str
    requirements: Dict[str, Any]
    budget: float
    signature: Optional[str] = None
    client_id: Optional[str] = None
    timestamp: Optional[str] = None
    msg_type: str = field(default="task_proposal", init=False, repr=False)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換（署名用）"""
        return {
            "msg_type": self.msg_type,
            "proposal_id": self.proposal_id,
            "task_type": self.task_type,
            "description": self.description,
            "requirements": self.requirements,
            "budget": self.budget,
            "client_id": self.client_id,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskProposal":
        """辞書から生成"""
        return cls(
            proposal_id=data["proposal_id"],
            task_type=data["task_type"],
            description=data["description"],
            requirements=data.get("requirements", {}),
            budget=data["budget"],
            signature=data.get("signature"),
            client_id=data.get("client_id"),
            timestamp=data.get("timestamp"),
        )
    
    def get_signable_data(self) -> Dict[str, Any]:
        """署名対象データを取得"""
        return self.to_dict()


@dataclass
class TaskQuote:
    """
    見積もり返信
    
    ProviderがClientに返信する見積もり情報
    """
    quote_id: str
    proposal_id: str
    estimated_amount: float
    estimated_time: int  # 秒単位
    valid_until: str  # ISO 8601形式
    terms: Dict[str, Any]
    signature: Optional[str] = None
    provider_id: Optional[str] = None
    timestamp: Optional[str] = None
    msg_type: str = field(default="task_quote", init=False, repr=False)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換（署名用）"""
        return {
            "msg_type": self.msg_type,
            "quote_id": self.quote_id,
            "proposal_id": self.proposal_id,
            "estimated_amount": self.estimated_amount,
            "estimated_time": self.estimated_time,
            "valid_until": self.valid_until,
            "terms": self.terms,
            "provider_id": self.provider_id,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TaskQuote":
        """辞書から生成"""
        return cls(
            quote_id=data["quote_id"],
            proposal_id=data["proposal_id"],
            estimated_amount=data["estimated_amount"],
            estimated_time=data["estimated_time"],
            valid_until=data["valid_until"],
            terms=data.get("terms", {}),
            signature=data.get("signature"),
            provider_id=data.get("provider_id"),
            timestamp=data.get("timestamp"),
        )
    
    def get_signable_data(self) -> Dict[str, Any]:
        """署名対象データを取得"""
        return self.to_dict()
    
    def is_valid(self) -> bool:
        """見積もりが有効期限内かチェック"""
        try:
            valid_until = datetime.fromisoformat(self.valid_until)
            return datetime.now(timezone.utc) <= valid_until
        except (ValueError, TypeError):
            return False


@dataclass
class Agreement:
    """
    合意形成
    
    ClientとProviderの間で成立した取引合意
    """
    agreement_id: str
    quote_id: str
    task_id: str
    confirmed_amount: float
    escrow_address: str
    deadline: str  # ISO 8601形式
    signature: Optional[str] = None
    client_id: Optional[str] = None
    provider_id: Optional[str] = None
    timestamp: Optional[str] = None
    msg_type: str = field(default="agreement", init=False, repr=False)
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書に変換（署名用）"""
        return {
            "msg_type": self.msg_type,
            "agreement_id": self.agreement_id,
            "quote_id": self.quote_id,
            "task_id": self.task_id,
            "confirmed_amount": self.confirmed_amount,
            "escrow_address": self.escrow_address,
            "deadline": self.deadline,
            "client_id": self.client_id,
            "provider_id": self.provider_id,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Agreement":
        """辞書から生成"""
        return cls(
            agreement_id=data["agreement_id"],
            quote_id=data["quote_id"],
            task_id=data["task_id"],
            confirmed_amount=data["confirmed_amount"],
            escrow_address=data["escrow_address"],
            deadline=data["deadline"],
            signature=data.get("signature"),
            client_id=data.get("client_id"),
            provider_id=data.get("provider_id"),
            timestamp=data.get("timestamp"),
        )
    
    def get_signable_data(self) -> Dict[str, Any]:
        """署名対象データを取得"""
        return self.to_dict()
    
    def is_expired(self) -> bool:
        """期限切れかチェック"""
        try:
            deadline = datetime.fromisoformat(self.deadline)
            return datetime.now(timezone.utc) > deadline
        except (ValueError, TypeError):
            return True


@dataclass
class Transaction:
    """取引レコード"""
    proposal: TaskProposal
    quote: Optional[TaskQuote] = None
    agreement: Optional[Agreement] = None
    state: TransactionState = field(default=TransactionState.PROPOSED)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def update_state(self, new_state: TransactionState) -> None:
        """状態を更新"""
        self.state = new_state
        self.updated_at = datetime.now(timezone.utc).isoformat()


class TransactionManager:
    """
    取引管理クラス
    
    AIエージェント間の取引プロトコルを管理する。
    Ed25519署名を使用してメッセージの真正性を保証する。
    """
    
    def __init__(self, entity_id: str, private_key_hex: Optional[str] = None):
        """
        TransactionManagerを初期化
        
        Args:
            entity_id: このエンティティのID
            private_key_hex: Ed25519秘密鍵（16進数）。省略時は環境変数から読み込み
        """
        self.entity_id = entity_id
        self._crypto = CryptoManager(entity_id, private_key_hex=private_key_hex)
        self._transactions: Dict[str, Transaction] = {}
        self._public_keys: Dict[str, str] = {}  # entity_id -> public_key_hex
        
    def register_public_key(self, entity_id: str, public_key_hex: str) -> None:
        """
        エンティティの公開鍵を登録
        
        Args:
            entity_id: エンティティID
            public_key_hex: Ed25519公開鍵（16進数）
        """
        self._public_keys[entity_id] = public_key_hex
        self._crypto.add_peer_public_key(entity_id, public_key_hex)
    
    def create_proposal(
        self,
        task_type: TaskType,
        description: str,
        requirements: Dict[str, Any],
        budget: float
    ) -> TaskProposal:
        """
        タスク提案を作成
        
        Args:
            task_type: タスクタイプ
            description: タスク説明
            requirements: 要件詳細
            budget: 予算上限
            
        Returns:
            署名済みTaskProposal
        """
        proposal_id = str(uuid.uuid4())
        
        proposal = TaskProposal(
            proposal_id=proposal_id,
            task_type=task_type.value if isinstance(task_type, TaskType) else task_type,
            description=description,
            requirements=requirements,
            budget=budget,
            client_id=self.entity_id,
        )
        
        # 署名
        signable_data = proposal.get_signable_data()
        proposal.signature = self._crypto.sign_message(signable_data)
        
        # 取引を記録
        transaction = Transaction(proposal=proposal)
        self._transactions[proposal_id] = transaction
        
        return proposal
    
    def create_quote(
        self,
        proposal: TaskProposal,
        estimated_amount: float,
        estimated_time: int,
        valid_hours: int = 24,
        terms: Optional[Dict[str, Any]] = None
    ) -> TaskQuote:
        """
        見積もりを作成
        
        Args:
            proposal: 元のタスク提案
            estimated_amount: 見積額
            estimated_time: 見積時間（秒）
            valid_hours: 有効期限（時間）
            terms: 取引条件
            
        Returns:
            署名済みTaskQuote
        """
        quote_id = str(uuid.uuid4())
        valid_until = datetime.now(timezone.utc)
        valid_until = valid_until.replace(hour=valid_until.hour + valid_hours)
        
        quote = TaskQuote(
            quote_id=quote_id,
            proposal_id=proposal.proposal_id,
            estimated_amount=estimated_amount,
            estimated_time=estimated_time,
            valid_until=valid_until.isoformat(),
            terms=terms or {},
            provider_id=self.entity_id,
        )
        
        # 署名
        signable_data = quote.get_signable_data()
        quote.signature = self._crypto.sign_message(signable_data)
        
        # 取引を更新
        if proposal.proposal_id in self._transactions:
            transaction = self._transactions[proposal.proposal_id]
            transaction.quote = quote
            transaction.update_state(TransactionState.QUOTED)
        
        return quote
    
    def create_agreement(
        self,
        quote: TaskQuote,
        escrow_address: str,
        deadline_hours: int = 72
    ) -> Agreement:
        """
        合意形成を作成
        
        Args:
            quote: 元の見積もり
            escrow_address: エスクローアドレス
            deadline_hours: タスク期限（時間）
            
        Returns:
            署名済みAgreement
        """
        agreement_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        deadline = datetime.now(timezone.utc)
        deadline = deadline.replace(hour=deadline.hour + deadline_hours)
        
        # Provider IDを取得（Quoteから）
        provider_id = quote.provider_id
        
        agreement = Agreement(
            agreement_id=agreement_id,
            quote_id=quote.quote_id,
            task_id=task_id,
            confirmed_amount=quote.estimated_amount,
            escrow_address=escrow_address,
            deadline=deadline.isoformat(),
            client_id=self.entity_id,
            provider_id=provider_id,
        )
        
        # 署名
        signable_data = agreement.get_signable_data()
        agreement.signature = self._crypto.sign_message(signable_data)
        
        # 取引を更新
        if quote.proposal_id in self._transactions:
            transaction = self._transactions[quote.proposal_id]
            transaction.agreement = agreement
            transaction.update_state(TransactionState.AGREED)
        
        return agreement
    
    def verify_signature(
        self,
        message_data: Dict[str, Any],
        signature: str,
        entity_id: str
    ) -> bool:
        """
        署名を検証
        
        Args:
            message_data: メッセージデータ
            signature: Base64エンコードされた署名
            entity_id: 署名者のエンティティID
            
        Returns:
            署名が有効ならTrue
        """
        if entity_id not in self._public_keys:
            raise ValueError(f"Public key not registered for entity: {entity_id}")
        
        public_key_hex = self._public_keys[entity_id]
        public_key_b64 = base64.b64encode(bytes.fromhex(public_key_hex)).decode("ascii")
        
        return self._crypto.verify_signature(message_data, signature, public_key_b64)
    
    def verify_proposal(self, proposal: TaskProposal) -> bool:
        """
        TaskProposalの署名を検証
        
        Args:
            proposal: 検証する提案
            
        Returns:
            署名が有効ならTrue
        """
        if not proposal.signature or not proposal.client_id:
            return False
        
        try:
            return self.verify_signature(
                proposal.get_signable_data(),
                proposal.signature,
                proposal.client_id
            )
        except ValueError:
            return False
    
    def verify_quote(self, quote: TaskQuote) -> bool:
        """
        TaskQuoteの署名を検証
        
        Args:
            quote: 検証する見積もり
            
        Returns:
            署名が有効ならTrue
        """
        if not quote.signature or not quote.provider_id:
            return False
        
        try:
            return self.verify_signature(
                quote.get_signable_data(),
                quote.signature,
                quote.provider_id
            )
        except ValueError:
            return False
    
    def verify_agreement(self, agreement: Agreement) -> bool:
        """
        Agreementの署名を検証
        
        Args:
            agreement: 検証する合意
            
        Returns:
            署名が有効ならTrue
        """
        if not agreement.signature or not agreement.client_id:
            return False
        
        try:
            return self.verify_signature(
                agreement.get_signable_data(),
                agreement.signature,
                agreement.client_id
            )
        except ValueError:
            return False
    
    def get_transaction_state(self, proposal_id: str) -> Optional[TransactionState]:
        """
        取引状態を取得
        
        Args:
            proposal_id: 提案ID
            
        Returns:
            取引状態。見つからない場合はNone
        """
        transaction = self._transactions.get(proposal_id)
        return transaction.state if transaction else None
    
    def get_transaction(self, proposal_id: str) -> Optional[Transaction]:
        """
        取引レコードを取得
        
        Args:
            proposal_id: 提案ID
            
        Returns:
            Transaction。見つからない場合はNone
        """
        return self._transactions.get(proposal_id)
    
    def list_transactions(
        self,
        state: Optional[TransactionState] = None
    ) -> Dict[str, Transaction]:
        """
        取引一覧を取得
        
        Args:
            state: フィルタする状態。省略時は全て
            
        Returns:
            取引ID -> Transactionの辞書
        """
        if state is None:
            return dict(self._transactions)
        
        return {
            k: v for k, v in self._transactions.items()
            if v.state == state
        }
    
    def update_transaction_state(
        self,
        proposal_id: str,
        new_state: TransactionState
    ) -> bool:
        """
        取引状態を更新
        
        Args:
            proposal_id: 提案ID
            new_state: 新しい状態
            
        Returns:
            更新に成功したらTrue
        """
        transaction = self._transactions.get(proposal_id)
        if not transaction:
            return False
        
        transaction.update_state(new_state)
        return True


def generate_task_id() -> str:
    """新しいタスクIDを生成"""
    return str(uuid.uuid4())


def generate_escrow_address() -> str:
    """新しいエスクローアドレスを生成（プレースホルダー）"""
    return f"escrow_{uuid.uuid4().hex[:16]}"


__all__ = [
    "TransactionState",
    "TaskType",
    "TaskProposal",
    "TaskQuote",
    "Agreement",
    "Transaction",
    "TransactionManager",
    "generate_task_id",
    "generate_escrow_address",
]
