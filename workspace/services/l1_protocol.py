#!/usr/bin/env python3
"""
L1 AI Communication Protocol v0.1

AIエージェント間の自律的タスク委譲を実現するコアプロトコル。

Features:
- Ed25519署名によるメッセージ認証
- UUID v4によるユニークメッセージID
- ISO8601タイムスタンプ
- 標準化されたメッセージ形式
- シリアライズ/デシリアライズ機能
- メッセージ検証機能

Protocol Version: 0.1
"""

import json
import uuid
import base64
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from enum import Enum, auto
from typing import Optional, Dict, List, Any, Callable, Union

# Import crypto utilities
try:
    from crypto import (
        KeyPair, MessageSigner, SignatureVerifier,
        SecureMessage, MessageType
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Import E2E crypto for session encryption
try:
    from e2e_crypto import (
        E2ECryptoManager, E2ESession, SessionState,
        E2EMessageType
    )
    E2E_AVAILABLE = True
except ImportError:
    E2E_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# Protocol Constants
# ============================================================================

PROTOCOL_NAME = "l1-ai-comm"
PROTOCOL_VERSION = "0.1"
DEFAULT_MESSAGE_TIMEOUT_SECONDS = 300  # 5 minutes
DEFAULT_VALIDITY_HOURS = 24


# ============================================================================
# Enums
# ============================================================================

class L1MessageType(Enum):
    """L1 Protocol message types"""
    TASK_DELEGATION = "TASK_DELEGATION"           # タスク委譲
    DELEGATION_RESPONSE = "DELEGATION_RESPONSE"   # 委譲応答
    STATUS_UPDATE = "STATUS_UPDATE"               # 進捗更新
    TASK_COMPLETE = "TASK_COMPLETE"               # タスク完了
    PAYMENT = "PAYMENT"                           # 支払い
    SERVICE_REGISTRATION = "SERVICE_REGISTRATION" # サービス登録
    HEARTBEAT = "HEARTBEAT"                       # ハートビート


class L1TaskStatus(Enum):
    """Task lifecycle states"""
    PENDING = "pending"           # 待機中
    ACCEPTED = "accepted"         # 受諾済み
    RUNNING = "running"           # 実行中
    COMPLETED = "completed"       # 完了
    FAILED = "failed"             # 失敗
    REJECTED = "rejected"         # 拒否
    CANCELLED = "cancelled"       # キャンセル
    TIMEOUT = "timeout"           # タイムアウト


class L1ResponseType(Enum):
    """Delegation response types"""
    ACCEPT = "accept"             # 受諾
    REJECT = "reject"             # 拒否
    COUNTER = "counter"           # カウンターオファー
    DEFER = "defer"               # 延期


class L1Priority(Enum):
    """Task priority levels"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4
    EMERGENCY = 5


class L1PaymentStatus(Enum):
    """Payment transaction status"""
    PENDING = "pending"
    ESCROW_LOCKED = "escrow_locked"
    RELEASED = "released"
    REFUNDED = "refunded"
    FAILED = "failed"


# ============================================================================
# Base Message Class
# ============================================================================

@dataclass
class L1Message:
    """
    L1 Protocol Base Message Class
    
    すべてのL1メッセージの基底クラス。
    Protocol v0.1準拠の標準メッセージ構造を定義。
    
    Attributes:
        protocol: プロトコル識別子 ("l1-ai-comm")
        version: プロトコルバージョン ("0.1")
        message_id: メッセージ固有ID (UUID v4)
        timestamp: ISO8601タイムスタンプ
        sender: 送信者情報 {agent_id, public_key}
        recipient: 受信者情報 {agent_id, public_key}
        message_type: メッセージタイプ (L1MessageType)
        payload: メッセージ固有データ
        signature: Ed25519署名 (base64)
        valid_until: 有効期限 (ISO8601)
    """
    
    # Protocol identification
    protocol: str = PROTOCOL_NAME
    version: str = PROTOCOL_VERSION
    
    # Message identification
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    # Routing information
    sender: Dict[str, str] = field(default_factory=dict)
    recipient: Dict[str, str] = field(default_factory=dict)
    
    # Message content
    message_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Security
    signature: Optional[str] = None
    valid_until: str = field(
        default_factory=lambda: (datetime.now(timezone.utc) + 
                                 timedelta(hours=DEFAULT_VALIDITY_HOURS)).isoformat()
    )
    
    def __post_init__(self):
        """Post-initialization validation"""
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert message to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert message to JSON string"""
        return json.dumps(self.to_dict(), indent=2)
    
    def to_bytes(self) -> bytes:
        """Convert message to bytes for signing"""
        # Create canonical representation for signing (exclude signature)
        data = self.to_dict()
        data.pop('signature', None)
        return json.dumps(data, sort_keys=True).encode('utf-8')
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "L1Message":
        """Create message from dictionary"""
        valid_fields = {f.name for f in field(cls)}
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered_data)
    
    @classmethod
    def from_json(cls, json_str: str) -> "L1Message":
        """Create message from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    def sign(self, signer: "MessageSigner") -> None:
        """
        Sign the message using Ed25519
        
        Args:
            signer: MessageSigner instance with private key
        """
        message_bytes = self.to_bytes()
        signature_bytes = signer.sign(message_bytes)
        self.signature = base64.b64encode(signature_bytes).decode('utf-8')
    
    def verify_signature(self, verifier: "SignatureVerifier") -> bool:
        """
        Verify the message signature
        
        Args:
            verifier: SignatureVerifier instance with public key
            
        Returns:
            True if signature is valid
        """
        if not self.signature:
            return False
        
        try:
            message_bytes = self.to_bytes()
            signature_bytes = base64.b64decode(self.signature)
            return verifier.verify(message_bytes, signature_bytes)
        except Exception as e:
            logger.warning(f"Signature verification failed: {e}")
            return False
    
    def is_expired(self) -> bool:
        """Check if message has expired"""
        try:
            valid_until = datetime.fromisoformat(
                self.valid_until.replace('Z', '+00:00')
            )
            return datetime.now(timezone.utc) > valid_until
        except (ValueError, TypeError):
            return True
    
    def is_valid(self) -> tuple[bool, Optional[str]]:
        """
        Validate message structure and content
        
        Returns:
            (is_valid, error_message)
        """
        # Check protocol
        if self.protocol != PROTOCOL_NAME:
            return False, f"Invalid protocol: {self.protocol}"
        
        # Check version
        if self.version != PROTOCOL_VERSION:
            return False, f"Invalid version: {self.version}"
        
        # Check message_id format (UUID v4)
        try:
            uuid.UUID(self.message_id)
        except (ValueError, TypeError):
            return False, f"Invalid message_id: {self.message_id}"
        
        # Check timestamp format
        try:
            datetime.fromisoformat(self.timestamp.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return False, f"Invalid timestamp: {self.timestamp}"
        
        # Check sender
        if not self.sender.get('agent_id'):
            return False, "Missing sender.agent_id"
        
        # Check recipient
        if not self.recipient.get('agent_id'):
            return False, "Missing recipient.agent_id"
        
        # Check message_type
        if not self.message_type:
            return False, "Missing message_type"
        
        # Check expiration
        if self.is_expired():
            return False, "Message has expired"
        
        return True, None
    
    def get_sender_id(self) -> Optional[str]:
        """Get sender agent ID"""
        return self.sender.get('agent_id')
    
    def get_recipient_id(self) -> Optional[str]:
        """Get recipient agent ID"""
        return self.recipient.get('agent_id')


# ============================================================================
# Task Delegation Message
# ============================================================================

@dataclass
class L1TaskDelegation(L1Message):
    """
    Task Delegation Message
    
    AIエージェント間でのタスク委譲を表すメッセージ。
    
    Payload Structure:
        task_id: タスク固有ID (UUID)
        parent_task_id: 親タスクID (オプション)
        title: タスクリスト
        description: タスク詳細説明
        task_type: タスク種別 (code, review, research, etc.)
        requirements: 要件リスト
        constraints: 制約条件
        deliverables: 期待成果物リスト
        priority: 優先度 (low, normal, high, critical, emergency)
        deadline: 期限 (ISO8601)
        estimated_hours: 推定工数
        reward_amount: 報酬額
        reward_token: トークン種別 (デフォルト: AIC)
        escrow_address: エスクローアドレス
        context: 追加コンテキスト
        dependencies: 依存タスクIDリスト
        required_capabilities: 必要能力リスト
    """
    
    message_type: str = L1MessageType.TASK_DELEGATION.value
    
    def __post_init__(self):
        super().__post_init__()
        # Ensure payload has required structure
        if 'task_id' not in self.payload:
            self.payload['task_id'] = str(uuid.uuid4())
        if 'status' not in self.payload:
            self.payload['status'] = L1TaskStatus.PENDING.value
    
    @classmethod
    def create(
        cls,
        sender_id: str,
        recipient_id: str,
        title: str,
        description: str,
        sender_pubkey: Optional[str] = None,
        recipient_pubkey: Optional[str] = None,
        **kwargs
    ) -> "L1TaskDelegation":
        """
        Create a task delegation message
        
        Args:
            sender_id: 委譲元エージェントID
            recipient_id: 委譲先エージェントID
            title: タスクリスト
            description: タスク詳細
            sender_pubkey: 送信者公開鍵 (オプション)
            recipient_pubkey: 受信者公開鍵 (オプション)
            **kwargs: 追加のペイロードフィールド
            
        Returns:
            L1TaskDelegation instance
        """
        sender = {'agent_id': sender_id}
        if sender_pubkey:
            sender['public_key'] = sender_pubkey
        
        recipient = {'agent_id': recipient_id}
        if recipient_pubkey:
            recipient['public_key'] = recipient_pubkey
        
        # Build payload
        payload = {
            'task_id': str(uuid.uuid4()),
            'title': title,
            'description': description,
            'status': L1TaskStatus.PENDING.value,
            'task_type': kwargs.get('task_type', 'custom'),
            'requirements': kwargs.get('requirements', []),
            'constraints': kwargs.get('constraints', {}),
            'deliverables': kwargs.get('deliverables', []),
            'priority': kwargs.get('priority', L1Priority.NORMAL.name.lower()),
            'deadline': kwargs.get('deadline'),
            'estimated_hours': kwargs.get('estimated_hours'),
            'reward_amount': kwargs.get('reward_amount', 0.0),
            'reward_token': kwargs.get('reward_token', 'AIC'),
            'context': kwargs.get('context', {}),
            'dependencies': kwargs.get('dependencies', []),
            'required_capabilities': kwargs.get('required_capabilities', []),
        }
        
        # Add optional fields
        if 'parent_task_id' in kwargs:
            payload['parent_task_id'] = kwargs['parent_task_id']
        if 'escrow_address' in kwargs:
            payload['escrow_address'] = kwargs['escrow_address']
        
        return cls(
            sender=sender,
            recipient=recipient,
            payload=payload,
            message_type=L1MessageType.TASK_DELEGATION.value
        )
    
    def get_task_id(self) -> Optional[str]:
        """Get task ID from payload"""
        return self.payload.get('task_id')
    
    def get_title(self) -> Optional[str]:
        """Get task title"""
        return self.payload.get('title')
    
    def get_priority(self) -> L1Priority:
        """Get task priority as enum"""
        try:
            priority_str = self.payload.get('priority', 'normal').upper()
            return L1Priority[priority_str]
        except (KeyError, ValueError):
            return L1Priority.NORMAL
    
    def is_expired(self) -> bool:
        """Check if task deadline has passed"""
        deadline = self.payload.get('deadline')
        if not deadline:
            return super().is_expired()
        
        try:
            deadline_dt = datetime.fromisoformat(deadline.replace('Z', '+00:00'))
            return datetime.now(timezone.utc) > deadline_dt
        except (ValueError, TypeError):
            return super().is_expired()


# ============================================================================
# Delegation Response Message
# ============================================================================

@dataclass
class L1DelegationResponse(L1Message):
    """
    Delegation Response Message
    
    タスク委譲への応答を表すメッセージ。
    
    Payload Structure:
        task_id: 対応するタスクID
        response_type: 応答タイプ (accept, reject, counter, defer)
        message: 応答メッセージ
        counter_offer: カウンターオファー詳細 (response_type=counterの場合)
        estimated_start: 開始予定時刻
        estimated_completion: 完了予定時刻
        proposed_reward: 提案報酬額 (カウンターオファー時)
        rejection_reason: 拒否理由
    """
    
    message_type: str = L1MessageType.DELEGATION_RESPONSE.value
    
    @classmethod
    def create(
        cls,
        task_id: str,
        sender_id: str,
        recipient_id: str,
        response_type: L1ResponseType,
        sender_pubkey: Optional[str] = None,
        recipient_pubkey: Optional[str] = None,
        **kwargs
    ) -> "L1DelegationResponse":
        """
        Create a delegation response message
        
        Args:
            task_id: 対応するタスクID
            sender_id: 応答者エージェントID
            recipient_id: 委譲元エージェントID
            response_type: 応答タイプ
            sender_pubkey: 送信者公開鍵
            recipient_pubkey: 受信者公開鍵
            **kwargs: 追加のペイロードフィールド
            
        Returns:
            L1DelegationResponse instance
        """
        sender = {'agent_id': sender_id}
        if sender_pubkey:
            sender['public_key'] = sender_pubkey
        
        recipient = {'agent_id': recipient_id}
        if recipient_pubkey:
            recipient['public_key'] = recipient_pubkey
        
        payload = {
            'task_id': task_id,
            'response_type': response_type.value,
            'message': kwargs.get('message', ''),
        }
        
        # Add optional fields
        if 'counter_offer' in kwargs:
            payload['counter_offer'] = kwargs['counter_offer']
        if 'estimated_start' in kwargs:
            payload['estimated_start'] = kwargs['estimated_start']
        if 'estimated_completion' in kwargs:
            payload['estimated_completion'] = kwargs['estimated_completion']
        if 'proposed_reward' in kwargs:
            payload['proposed_reward'] = kwargs['proposed_reward']
        if 'rejection_reason' in kwargs:
            payload['rejection_reason'] = kwargs['rejection_reason']
        
        return cls(
            sender=sender,
            recipient=recipient,
            payload=payload,
            message_type=L1MessageType.DELEGATION_RESPONSE.value
        )
    
    @classmethod
    def accept(
        cls,
        task_id: str,
        sender_id: str,
        recipient_id: str,
        **kwargs
    ) -> "L1DelegationResponse":
        """Create an acceptance response"""
        return cls.create(
            task_id=task_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            response_type=L1ResponseType.ACCEPT,
            **kwargs
        )
    
    @classmethod
    def reject(
        cls,
        task_id: str,
        sender_id: str,
        recipient_id: str,
        reason: str,
        **kwargs
    ) -> "L1DelegationResponse":
        """Create a rejection response"""
        kwargs['rejection_reason'] = reason
        kwargs['message'] = kwargs.get('message', f"Task rejected: {reason}")
        return cls.create(
            task_id=task_id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            response_type=L1ResponseType.REJECT,
            **kwargs
        )
    
    def get_task_id(self) -> Optional[str]:
        """Get associated task ID"""
        return self.payload.get('task_id')
    
    def get_response_type(self) -> L1ResponseType:
        """Get response type as enum"""
        try:
            rt_str = self.payload.get('response_type', 'reject').upper()
            return L1ResponseType[rt_str]
        except (KeyError, ValueError):
            return L1ResponseType.REJECT
    
    def is_accepted(self) -> bool:
        """Check if task was accepted"""
        return self.get_response_type() == L1ResponseType.ACCEPT


# ============================================================================
# Status Update Message
# ============================================================================

@dataclass
class L1StatusUpdate(L1Message):
    """
    Status Update Message
    
    タスク実行中の進捗更新を表すメッセージ。
    
    Payload Structure:
        task_id: 対応するタスクID
        status: 現在の状態 (pending, running, completed, failed, etc.)
        progress_percent: 進捗率 (0-100)
        message: ステータスメッセージ
        deliverables_ready: 完了済み成果物リスト
        issues: 発生した問題リスト
        eta: 推定完了時刻
    """
    
    message_type: str = L1MessageType.STATUS_UPDATE.value
    
    @classmethod
    def create(
        cls,
        task_id: str,
        sender_id: str,
        recipient_id: str,
        status: L1TaskStatus,
        progress_percent: int = 0,
        sender_pubkey: Optional[str] = None,
        recipient_pubkey: Optional[str] = None,
        **kwargs
    ) -> "L1StatusUpdate":
        """
        Create a status update message
        
        Args:
            task_id: 対応するタスクID
            sender_id: 実行エージェントID
            recipient_id: 委譲元エージェントID
            status: 現在の状態
            progress_percent: 進捗率 (0-100)
            sender_pubkey: 送信者公開鍵
            recipient_pubkey: 受信者公開鍵
            **kwargs: 追加のペイロードフィールド
            
        Returns:
            L1StatusUpdate instance
        """
        sender = {'agent_id': sender_id}
        if sender_pubkey:
            sender['public_key'] = sender_pubkey
        
        recipient = {'agent_id': recipient_id}
        if recipient_pubkey:
            recipient['public_key'] = recipient_pubkey
        
        payload = {
            'task_id': task_id,
            'status': status.value,
            'progress_percent': max(0, min(100, progress_percent)),
            'message': kwargs.get('message', ''),
        }
        
        # Add optional fields
        if 'deliverables_ready' in kwargs:
            payload['deliverables_ready'] = kwargs['deliverables_ready']
        if 'issues' in kwargs:
            payload['issues'] = kwargs['issues']
        if 'eta' in kwargs:
            payload['eta'] = kwargs['eta']
        
        return cls(
            sender=sender,
            recipient=recipient,
            payload=payload,
            message_type=L1MessageType.STATUS_UPDATE.value
        )
    
    def get_task_id(self) -> Optional[str]:
        """Get associated task ID"""
        return self.payload.get('task_id')
    
    def get_status(self) -> L1TaskStatus:
        """Get task status as enum"""
        try:
            status_str = self.payload.get('status', 'pending').upper()
            return L1TaskStatus[status_str]
        except (KeyError, ValueError):
            return L1TaskStatus.PENDING
    
    def get_progress(self) -> int:
        """Get progress percentage"""
        return self.payload.get('progress_percent', 0)


# ============================================================================
# Payment Message
# ============================================================================

@dataclass
class L1Payment(L1Message):
    """
    Payment Message
    
    タスク完了時の支払いを表すメッセージ。
    
    Payload Structure:
        payment_id: 支払い固有ID (UUID)
        task_id: 対応するタスクID
        amount: 支払い額
        token: トークン種別
        payment_status: 支払い状態
        escrow_address: エスクローアドレス
        escrow_release_proof: エスクロー解放証明
        from_address: 送信元アドレス
        to_address: 送信先アドレス
        transaction_hash: ブロックチェーントランザクションハッシュ
        payment_reason: 支払い理由
    """
    
    message_type: str = L1MessageType.PAYMENT.value
    
    @classmethod
    def create(
        cls,
        task_id: str,
        sender_id: str,
        recipient_id: str,
        amount: float,
        sender_pubkey: Optional[str] = None,
        recipient_pubkey: Optional[str] = None,
        **kwargs
    ) -> "L1Payment":
        """
        Create a payment message
        
        Args:
            task_id: 対応するタスクID
            sender_id: 支払い元エージェントID
            recipient_id: 支払い先エージェントID
            amount: 支払い額
            sender_pubkey: 送信者公開鍵
            recipient_pubkey: 受信者公開鍵
            **kwargs: 追加のペイロードフィールド
            
        Returns:
            L1Payment instance
        """
        sender = {'agent_id': sender_id}
        if sender_pubkey:
            sender['public_key'] = sender_pubkey
        
        recipient = {'agent_id': recipient_id}
        if recipient_pubkey:
            recipient['public_key'] = recipient_pubkey
        
        payload = {
            'payment_id': str(uuid.uuid4()),
            'task_id': task_id,
            'amount': amount,
            'token': kwargs.get('token', 'AIC'),
            'payment_status': kwargs.get('payment_status', L1PaymentStatus.PENDING.value),
            'payment_reason': kwargs.get('payment_reason', f"Payment for task {task_id}"),
        }
        
        # Add optional fields
        if 'escrow_address' in kwargs:
            payload['escrow_address'] = kwargs['escrow_address']
        if 'escrow_release_proof' in kwargs:
            payload['escrow_release_proof'] = kwargs['escrow_release_proof']
        if 'from_address' in kwargs:
            payload['from_address'] = kwargs['from_address']
        if 'to_address' in kwargs:
            payload['to_address'] = kwargs['to_address']
        if 'transaction_hash' in kwargs:
            payload['transaction_hash'] = kwargs['transaction_hash']
        
        return cls(
            sender=sender,
            recipient=recipient,
            payload=payload,
            message_type=L1MessageType.PAYMENT.value
        )
    
    def get_payment_id(self) -> Optional[str]:
        """Get payment ID"""
        return self.payload.get('payment_id')
    
    def get_task_id(self) -> Optional[str]:
        """Get associated task ID"""
        return self.payload.get('task_id')
    
    def get_amount(self) -> float:
        """Get payment amount"""
        return self.payload.get('amount', 0.0)
    
    def get_payment_status(self) -> L1PaymentStatus:
        """Get payment status as enum"""
        try:
            status_str = self.payload.get('payment_status', 'pending').upper()
            return L1PaymentStatus[status_str]
        except (KeyError, ValueError):
            return L1PaymentStatus.PENDING


# ============================================================================
# Protocol Handler
# ============================================================================

class L1ProtocolHandler:
    """
    L1 Protocol Message Handler
    
    L1プロトコルメッセージの処理と管理を行う。
    - メッセージ検証
    - 署名生成・検証
    - メッセージルーティング
    - ハンドラ登録
    """
    
    def __init__(
        self,
        agent_id: str,
        keypair: Optional["KeyPair"] = None
    ):
        """
        Initialize protocol handler
        
        Args:
            agent_id: このハンドラのエージェントID
            keypair: Ed25519キーペア（署名用）
        """
        self.agent_id = agent_id
        self.keypair = keypair
        self.signer = MessageSigner(keypair) if keypair and CRYPTO_AVAILABLE else None
        
        # Message handlers: message_type -> handler function
        self._handlers: Dict[str, Callable[[L1Message], Any]] = {}
        
        # Message history: message_id -> message
        self._message_history: Dict[str, L1Message] = {}
        
        # E2E session manager (optional)
        self._e2e_manager: Optional["E2ECryptoManager"] = None
        if keypair and E2E_AVAILABLE:
            try:
                self._e2e_manager = E2ECryptoManager(
                    entity_id=agent_id,
                    keypair=keypair
                )
            except Exception as e:
                logger.warning(f"Failed to initialize E2E manager: {e}")
    
    def register_handler(
        self,
        message_type: Union[str, L1MessageType],
        handler: Callable[[L1Message], Any]
    ) -> None:
        """
        Register a message handler
        
        Args:
            message_type: メッセージタイプ
            handler: ハンドラ関数(message -> result)
        """
        mt = message_type.value if isinstance(message_type, L1MessageType) else message_type
        self._handlers[mt] = handler
        logger.info(f"Registered handler for {mt}")
    
    def create_message(
        self,
        message_class: type,
        recipient_id: str,
        recipient_pubkey: Optional[str] = None,
        **kwargs
    ) -> L1Message:
        """
        Create a new message
        
        Args:
            message_class: メッセージクラス (L1TaskDelegation, etc.)
            recipient_id: 受信者エージェントID
            recipient_pubkey: 受信者公開鍵
            **kwargs: メッセージ固有パラメータ
            
        Returns:
            L1Message instance (unsigned)
        """
        sender_pubkey = None
        if self.keypair and CRYPTO_AVAILABLE:
            sender_pubkey = self.keypair.get_public_key_hex()
        
        return message_class.create(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            sender_pubkey=sender_pubkey,
            recipient_pubkey=recipient_pubkey,
            **kwargs
        )
    
    def sign_message(self, message: L1Message) -> bool:
        """
        Sign a message
        
        Args:
            message: 署名するメッセージ
            
        Returns:
            True if signed successfully
        """
        if not self.signer:
            logger.warning("No signer available")
            return False
        
        try:
            message.sign(self.signer)
            return True
        except Exception as e:
            logger.error(f"Failed to sign message: {e}")
            return False
    
    def verify_message(
        self,
        message: L1Message,
        public_key: Optional[bytes] = None
    ) -> bool:
        """
        Verify a message signature
        
        Args:
            message: 検証するメッセージ
            public_key: 検証用公開鍵（省略時はsenderのpublic_keyを使用）
            
        Returns:
            True if valid
        """
        if not CRYPTO_AVAILABLE:
            logger.warning("Crypto not available, skipping verification")
            return True
        
        # Get public key
        if public_key is None:
            pubkey_hex = message.sender.get('public_key')
            if pubkey_hex:
                try:
                    public_key = bytes.fromhex(pubkey_hex)
                except ValueError:
                    pass
        
        if public_key is None:
            logger.warning("No public key available for verification")
            return False
        
        try:
            verifier = SignatureVerifier(public_key)
            return message.verify_signature(verifier)
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False
    
    def validate_message(self, message: L1Message) -> tuple[bool, Optional[str]]:
        """
        Validate message structure
        
        Args:
            message: 検証するメッセージ
            
        Returns:
            (is_valid, error_message)
        """
        return message.is_valid()
    
    def process_message(self, message: L1Message) -> Any:
        """
        Process an incoming message
        
        Args:
            message: 受信メッセージ
            
        Returns:
            Handler result
        """
        # Validate
        is_valid, error = self.validate_message(message)
        if not is_valid:
            logger.warning(f"Invalid message: {error}")
            return {'error': error, 'valid': False}
        
        # Check if message is for us
        recipient_id = message.get_recipient_id()
        if recipient_id and recipient_id != self.agent_id:
            logger.warning(f"Message not for us: {recipient_id}")
            return {'error': 'not_recipient', 'valid': False}
        
        # Store in history
        self._message_history[message.message_id] = message
        
        # Route to handler
        handler = self._handlers.get(message.message_type)
        if handler:
            try:
                return handler(message)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                return {'error': str(e), 'handled': False}
        else:
            logger.warning(f"No handler for {message.message_type}")
            return {'error': 'no_handler', 'handled': False}
    
    def parse_and_process(self, json_str: str) -> Any:
        """
        Parse JSON and process message
        
        Args:
            json_str: JSONメッセージ文字列
            
        Returns:
            Process result
        """
        try:
            data = json.loads(json_str)
            message = L1Message.from_dict(data)
            return self.process_message(message)
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON: {e}")
            return {'error': f'invalid_json: {e}'}
        except Exception as e:
            logger.error(f"Processing error: {e}")
            return {'error': str(e)}
    
    def get_message_history(
        self,
        message_type: Optional[str] = None
    ) -> List[L1Message]:
        """
        Get message history
        
        Args:
            message_type: フィルタするメッセージタイプ
            
        Returns:
            メッセージリスト
        """
        messages = list(self._message_history.values())
        if message_type:
            messages = [m for m in messages if m.message_type == message_type]
        return messages
    
    def create_response(
        self,
        original_message: L1Message,
        response_class: type,
        **kwargs
    ) -> Optional[L1Message]:
        """
        Create a response to a message (swap sender/recipient)
        
        Args:
            original_message: 元のメッセージ
            response_class: 応答メッセージクラス
            **kwargs: 応答パラメータ
            
        Returns:
            Response message (unsigned)
        """
        recipient_id = original_message.get_sender_id()
        recipient_pubkey = original_message.sender.get('public_key')
        
        return self.create_message(
            message_class=response_class,
            recipient_id=recipient_id,
            recipient_pubkey=recipient_pubkey,
            **kwargs
        )


# ============================================================================
# Utility Functions
# ============================================================================

def create_agent_sender(agent_id: str, public_key: Optional[str] = None) -> Dict[str, str]:
    """Create sender dictionary"""
    sender = {'agent_id': agent_id}
    if public_key:
        sender['public_key'] = public_key
    return sender


def create_agent_recipient(agent_id: str, public_key: Optional[str] = None) -> Dict[str, str]:
    """Create recipient dictionary"""
    recipient = {'agent_id': agent_id}
    if public_key:
        recipient['public_key'] = public_key
    return recipient


def get_current_timestamp() -> str:
    """Get current ISO8601 timestamp"""
    return datetime.now(timezone.utc).isoformat()


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("L1 AI Communication Protocol v0.1")
    print("=" * 50)
    
    # Test message creation
    print("\n1. Testing L1TaskDelegation...")
    task_msg = L1TaskDelegation.create(
        sender_id="agent-a",
        recipient_id="agent-b",
        title="Implement feature X",
        description="Add new authentication system",
        requirements=["Use JWT", "Add tests"],
        priority="high",
        reward_amount=100.0
    )
    print(f"   Task ID: {task_msg.get_task_id()}")
    print(f"   Title: {task_msg.get_title()}")
    print(f"   Valid: {task_msg.is_valid()}")
    
    # Test response
    print("\n2. Testing L1DelegationResponse...")
    response_msg = L1DelegationResponse.accept(
        task_id=task_msg.get_task_id(),
        sender_id="agent-b",
        recipient_id="agent-a",
        message="Task accepted, starting work"
    )
    print(f"   Response Type: {response_msg.get_response_type()}")
    print(f"   Accepted: {response_msg.is_accepted()}")
    
    # Test status update
    print("\n3. Testing L1StatusUpdate...")
    status_msg = L1StatusUpdate.create(
        task_id=task_msg.get_task_id(),
        sender_id="agent-b",
        recipient_id="agent-a",
        status=L1TaskStatus.RUNNING,
        progress_percent=50,
        message="Halfway done"
    )
    print(f"   Status: {status_msg.get_status().value}")
    print(f"   Progress: {status_msg.get_progress()}%")
    
    # Test payment
    print("\n4. Testing L1Payment...")
    payment_msg = L1Payment.create(
        task_id=task_msg.get_task_id(),
        sender_id="agent-a",
        recipient_id="agent-b",
        amount=100.0,
        token="AIC",
        payment_status="released"
    )
    print(f"   Payment ID: {payment_msg.get_payment_id()}")
    print(f"   Amount: {payment_msg.get_amount()} {payment_msg.payload.get('token')}")
    
    # Test protocol handler
    print("\n5. Testing L1ProtocolHandler...")
    handler = L1ProtocolHandler(agent_id="agent-test")
    
    # Register handler
    def task_handler(msg: L1Message):
        return {"handled": True, "task_id": msg.get_task_id()}
    
    handler.register_handler(L1MessageType.TASK_DELEGATION, task_handler)
    
    # Process message
    result = handler.process_message(task_msg)
    print(f"   Handler result: {result}")
    
    # Test serialization
    print("\n6. Testing serialization...")
    json_str = task_msg.to_json()
    parsed = L1Message.from_json(json_str)
    print(f"   Original ID: {task_msg.message_id}")
    print(f"   Parsed ID: {parsed.message_id}")
    print(f"   Match: {task_msg.message_id == parsed.message_id}")
    
    print("\n" + "=" * 50)
    print("All tests passed!")
