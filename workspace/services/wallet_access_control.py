#!/usr/bin/env python3
"""
Wallet Access Control
ウォレットへのアクセス制御（RBAC）機能

機能:
- ロールベースアクセス制御（RBAC）
- アクセス監査ログ
- 時間ベースのアクセス制限
- 操作制限（読み取り専用、書き込み権限など）
- MFA（多要素認証）サポート
"""

import json
import logging
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Callable
from functools import wraps

logger = logging.getLogger(__name__)


class AccessLevel(Enum):
    """アクセスレベル"""
    NONE = 0
    READ = 1          # 読み取りのみ
    SIGN = 2          # 署名可能
    ADMIN = 3         # 管理権限（鍵の保存・削除）


class Role(Enum):
    """定義済みロール"""
    VIEWER = "viewer"           # 読み取り専用
    OPERATOR = "operator"       # 操作可能（署名など）
    ADMIN = "admin"             # 管理者
    SERVICE = "service"         # サービスアカウント
    AUDITOR = "auditor"         # 監査役（読み取り＋監査ログ閲覧）


# ロールとアクセスレベルのマッピング
ROLE_PERMISSIONS: Dict[Role, Dict[str, Any]] = {
    Role.VIEWER: {
        "level": AccessLevel.READ,
        "allowed_operations": {"get_balance", "get_key_info", "list_entities"},
        "max_daily_operations": 1000,
    },
    Role.OPERATOR: {
        "level": AccessLevel.SIGN,
        "allowed_operations": {"get_balance", "get_key_info", "list_entities", "sign", "transfer"},
        "max_daily_operations": 10000,
    },
    Role.ADMIN: {
        "level": AccessLevel.ADMIN,
        "allowed_operations": None,  # 全操作可能
        "max_daily_operations": None,  # 無制限
    },
    Role.SERVICE: {
        "level": AccessLevel.SIGN,
        "allowed_operations": {"sign", "get_balance"},
        "max_daily_operations": 100000,
    },
    Role.AUDITOR: {
        "level": AccessLevel.READ,
        "allowed_operations": {"get_balance", "get_key_info", "list_entities", "view_audit_log"},
        "max_daily_operations": 5000,
    },
}


@dataclass
class AccessPolicy:
    """アクセスポリシー"""
    role: Role
    allowed_hours: Optional[tuple] = None  # (開始時刻, 終了時刻) 例: (9, 18)
    allowed_days: Optional[Set[int]] = None  # 0=Monday, 6=Sunday
    ip_whitelist: Optional[Set[str]] = None
    require_mfa: bool = False
    max_session_duration: int = 3600  # 秒
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role.value,
            "allowed_hours": self.allowed_hours,
            "allowed_days": list(self.allowed_days) if self.allowed_days else None,
            "ip_whitelist": list(self.ip_whitelist) if self.ip_whitelist else None,
            "require_mfa": self.require_mfa,
            "max_session_duration": self.max_session_duration
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AccessPolicy":
        return cls(
            role=Role(data["role"]),
            allowed_hours=tuple(data["allowed_hours"]) if data.get("allowed_hours") else None,
            allowed_days=set(data["allowed_days"]) if data.get("allowed_days") else None,
            ip_whitelist=set(data["ip_whitelist"]) if data.get("ip_whitelist") else None,
            require_mfa=data.get("require_mfa", False),
            max_session_duration=data.get("max_session_duration", 3600)
        )


@dataclass
class UserCredential:
    """ユーザークレデンシャル"""
    user_id: str
    password_hash: str
    salt: str
    role: Role
    entity_access: Set[str]  # アクセス可能なエンティティID
    policy: AccessPolicy
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_login: Optional[datetime] = None
    failed_login_attempts: int = 0
    locked_until: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "password_hash": self.password_hash,
            "salt": self.salt,
            "role": self.role.value,
            "entity_access": list(self.entity_access),
            "policy": self.policy.to_dict(),
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
            "failed_login_attempts": self.failed_login_attempts,
            "locked_until": self.locked_until.isoformat() if self.locked_until else None
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserCredential":
        return cls(
            user_id=data["user_id"],
            password_hash=data["password_hash"],
            salt=data["salt"],
            role=Role(data["role"]),
            entity_access=set(data.get("entity_access", [])),
            policy=AccessPolicy.from_dict(data["policy"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_login=datetime.fromisoformat(data["last_login"]) if data.get("last_login") else None,
            failed_login_attempts=data.get("failed_login_attempts", 0),
            locked_until=datetime.fromisoformat(data["locked_until"]) if data.get("locked_until") else None
        )


@dataclass
class AuditLogEntry:
    """監査ログエントリ"""
    timestamp: datetime
    user_id: str
    entity_id: str
    operation: str
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "user_id": self.user_id,
            "entity_id": self.entity_id,
            "operation": self.operation,
            "success": self.success,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent
        }


@dataclass
class Session:
    """ユーザーセッション"""
    session_id: str
    user_id: str
    entity_id: str
    created_at: datetime
    expires_at: datetime
    ip_address: Optional[str] = None
    mfa_verified: bool = False
    
    def is_valid(self) -> bool:
        """セッションが有効かチェック"""
        return datetime.now(timezone.utc) < self.expires_at


class WalletAccessControl:
    """
    ウォレットアクセス制御マネージャー
    
    RBACベースのアクセス制御、監査ログ、セッション管理を提供
    """
    
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_DURATION = timedelta(minutes=30)
    
    def __init__(self, config_dir: Optional[str] = None):
        """
        WalletAccessControlを初期化
        
        Args:
            config_dir: 設定ディレクトリのパス（省略時は ~/.peer_service/access_control/）
        """
        if config_dir is None:
            config_dir = Path.home() / ".peer_service" / "access_control"
        
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        
        self._users: Dict[str, UserCredential] = {}
        self._sessions: Dict[str, Session] = {}
        self._audit_log: List[AuditLogEntry] = []
        self._operation_counters: Dict[str, Dict[str, int]] = {}  # user_id -> {date -> count}
        
        # 設定ファイルのパス
        self._users_file = self.config_dir / "users.json"
        self._audit_file = self.config_dir / "audit.log"
        
        self._load_users()
        self._load_audit_log()
        
        logger.info("WalletAccessControl initialized")
    
    def _hash_password(self, password: str, salt: Optional[str] = None) -> tuple:
        """パスワードをハッシュ化"""
        if salt is None:
            salt = secrets.token_hex(32)
        
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            600000  # イテレーション回数
        ).hex()
        
        return pwd_hash, salt
    
    def _load_users(self) -> None:
        """ユーザー設定を読み込み"""
        if self._users_file.exists():
            try:
                with open(self._users_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self._users = {
                        uid: UserCredential.from_dict(udata)
                        for uid, udata in data.items()
                    }
                logger.info(f"Loaded {len(self._users)} users")
            except Exception as e:
                logger.error(f"Failed to load users: {e}")
    
    def _save_users(self) -> None:
        """ユーザー設定を保存"""
        try:
            data = {
                uid: udata.to_dict()
                for uid, udata in self._users.items()
            }
            with open(self._users_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            self._users_file.chmod(0o600)
        except Exception as e:
            logger.error(f"Failed to save users: {e}")
    
    def _load_audit_log(self) -> None:
        """監査ログを読み込み"""
        if self._audit_file.exists():
            try:
                with open(self._audit_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            entry = AuditLogEntry(**json.loads(line))
                            self._audit_log.append(entry)
                logger.info(f"Loaded {len(self._audit_log)} audit log entries")
            except Exception as e:
                logger.error(f"Failed to load audit log: {e}")
    
    def _append_audit_log(self, entry: AuditLogEntry) -> None:
        """監査ログに追加"""
        self._audit_log.append(entry)
        try:
            with open(self._audit_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')
        except Exception as e:
            logger.error(f"Failed to append audit log: {e}")
    
    def create_user(
        self,
        user_id: str,
        password: str,
        role: Role,
        entity_access: List[str],
        policy: Optional[AccessPolicy] = None
    ) -> bool:
        """
        新規ユーザーを作成
        
        Args:
            user_id: ユーザーID
            password: パスワード
            role: ロール
            entity_access: アクセス可能なエンティティIDリスト
            policy: アクセスポリシー（省略時はロールのデフォルト）
        
        Returns:
            作成成功時はTrue
        """
        if user_id in self._users:
            logger.warning(f"User already exists: {user_id}")
            return False
        
        pwd_hash, salt = self._hash_password(password)
        
        if policy is None:
            policy = AccessPolicy(role=role)
        
        user = UserCredential(
            user_id=user_id,
            password_hash=pwd_hash,
            salt=salt,
            role=role,
            entity_access=set(entity_access),
            policy=policy
        )
        
        self._users[user_id] = user
        self._save_users()
        
        logger.info(f"Created user: {user_id} with role {role.value}")
        return True
    
    def authenticate(
        self,
        user_id: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Optional[str]:
        """
        ユーザー認証
        
        Args:
            user_id: ユーザーID
            password: パスワード
            ip_address: IPアドレス
        
        Returns:
            成功時はセッションID、失敗時はNone
        """
        user = self._users.get(user_id)
        if not user:
            logger.warning(f"Authentication failed: user not found - {user_id}")
            return None
        
        # アカウントロックチェック
        if user.locked_until and datetime.now(timezone.utc) < user.locked_until:
            logger.warning(f"Authentication failed: account locked - {user_id}")
            return None
        
        # パスワード検証
        pwd_hash, _ = self._hash_password(password, user.salt)
        if pwd_hash != user.password_hash:
            user.failed_login_attempts += 1
            
            # ロックアウト判定
            if user.failed_login_attempts >= self.MAX_LOGIN_ATTEMPTS:
                user.locked_until = datetime.now(timezone.utc) + self.LOCKOUT_DURATION
                logger.warning(f"Account locked due to too many failed attempts: {user_id}")
            
            self._save_users()
            
            self._append_audit_log(AuditLogEntry(
                timestamp=datetime.now(timezone.utc),
                user_id=user_id,
                entity_id="",
                operation="authenticate",
                success=False,
                details={"reason": "invalid_password"},
                ip_address=ip_address
            ))
            
            return None
        
        # 認証成功
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login = datetime.now(timezone.utc)
        self._save_users()
        
        # セッション作成
        session_id = secrets.token_urlsafe(32)
        session = Session(
            session_id=session_id,
            user_id=user_id,
            entity_id="",  # エンティティは後で設定
            created_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=user.policy.max_session_duration),
            ip_address=ip_address,
            mfa_verified=not user.policy.require_mfa
        )
        self._sessions[session_id] = session
        
        self._append_audit_log(AuditLogEntry(
            timestamp=datetime.now(timezone.utc),
            user_id=user_id,
            entity_id="",
            operation="authenticate",
            success=True,
            details={"session_id": session_id},
            ip_address=ip_address
        ))
        
        logger.info(f"User authenticated: {user_id}")
        return session_id
    
    def check_access(
        self,
        session_id: str,
        entity_id: str,
        operation: str,
        ip_address: Optional[str] = None
    ) -> tuple[bool, Optional[str]]:
        """
        アクセス権限をチェック
        
        Args:
            session_id: セッションID
            entity_id: エンティティID
            operation: 操作名
            ip_address: IPアドレス
        
        Returns:
            (許可可否, エラーメッセージ)
        """
        session = self._sessions.get(session_id)
        if not session or not session.is_valid():
            return False, "Invalid or expired session"
        
        user = self._users.get(session.user_id)
        if not user:
            return False, "User not found"
        
        # エンティティアクセスチェック
        if entity_id not in user.entity_access:
            self._append_audit_log(AuditLogEntry(
                timestamp=datetime.now(timezone.utc),
                user_id=session.user_id,
                entity_id=entity_id,
                operation=operation,
                success=False,
                details={"reason": "entity_not_allowed"},
                ip_address=ip_address
            ))
            return False, "Access to entity not allowed"
        
        policy = user.policy
        permissions = ROLE_PERMISSIONS[user.role]
        
        # 操作許可チェック
        allowed_ops = permissions["allowed_operations"]
        if allowed_ops is not None and operation not in allowed_ops:
            return False, f"Operation '{operation}' not allowed for role {user.role.value}"
        
        # 時間制限チェック
        now = datetime.now(timezone.utc)
        if policy.allowed_hours:
            hour = now.hour
            if not (policy.allowed_hours[0] <= hour < policy.allowed_hours[1]):
                return False, "Access not allowed at this time"
        
        if policy.allowed_days:
            if now.weekday() not in policy.allowed_days:
                return False, "Access not allowed on this day"
        
        # IP制限チェック
        if policy.ip_whitelist and ip_address:
            if ip_address not in policy.ip_whitelist:
                return False, "Access not allowed from this IP address"
        
        # MFAチェック
        if policy.require_mfa and not session.mfa_verified:
            return False, "MFA verification required"
        
        # 日次操作回数チェック
        today = now.strftime("%Y-%m-%d")
        user_counters = self._operation_counters.setdefault(session.user_id, {})
        daily_count = user_counters.get(today, 0)
        max_ops = permissions["max_daily_operations"]
        
        if max_ops is not None and daily_count >= max_ops:
            return False, "Daily operation limit exceeded"
        
        # カウンタ更新
        user_counters[today] = daily_count + 1
        
        # 成功ログ
        self._append_audit_log(AuditLogEntry(
            timestamp=now,
            user_id=session.user_id,
            entity_id=entity_id,
            operation=operation,
            success=True,
            details={"session_id": session_id},
            ip_address=ip_address
        ))
        
        return True, None
    
    def logout(self, session_id: str) -> bool:
        """ログアウト（セッション無効化）"""
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"Session logged out: {session_id[:16]}...")
            return True
        return False
    
    def get_audit_log(
        self,
        user_id: Optional[str] = None,
        entity_id: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[AuditLogEntry]:
        """監査ログを取得"""
        entries = self._audit_log
        
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        
        if entity_id:
            entries = [e for e in entries if e.entity_id == entity_id]
        
        if since:
            entries = [e for e in entries if e.timestamp >= since]
        
        return entries[-limit:]
    
    def require_access(self, entity_id: str, operation: str):
        """
        アクセス制御デコレータ
        
        Usage:
            @access_control.require_access("entity_id", "operation")
            def sensitive_function(session_id, ...):
                ...
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(session_id: str, *args, **kwargs):
                allowed, error = self.check_access(session_id, entity_id, operation)
                if not allowed:
                    raise PermissionError(error)
                return func(session_id, *args, **kwargs)
            return wrapper
        return decorator


# グローバルインスタンス
_access_control_instance: Optional[WalletAccessControl] = None


def get_access_control(config_dir: Optional[str] = None) -> WalletAccessControl:
    """グローバルアクセス制御インスタンスを取得"""
    global _access_control_instance
    if _access_control_instance is None:
        _access_control_instance = WalletAccessControl(config_dir)
    return _access_control_instance


def reset_access_control() -> None:
    """グローバルインスタンスをリセット（テスト用）"""
    global _access_control_instance
    _access_control_instance = None


# テスト
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    print("=== WalletAccessControl Test ===")
    
    import tempfile
    test_dir = tempfile.mkdtemp()
    
    try:
        ac = WalletAccessControl(test_dir)
        
        # ユーザー作成
        print("\n--- Test 1: Create User ---")
        result = ac.create_user(
            user_id="test_user",
            password="secure_password",
            role=Role.OPERATOR,
            entity_access=["entity_a", "entity_b"]
        )
        print(f"User created: {result}")
        
        # 認証
        print("\n--- Test 2: Authenticate ---")
        session = ac.authenticate("test_user", "secure_password")
        print(f"Authenticated, session: {session is not None}")
        
        # アクセスチェック
        print("\n--- Test 3: Check Access ---")
        allowed, error = ac.check_access(session, "entity_a", "sign")
        print(f"Access allowed: {allowed}, error: {error}")
        
        # 許可されていないエンティティ
        print("\n--- Test 4: Unauthorized Entity ---")
        allowed, error = ac.check_access(session, "entity_c", "sign")
        print(f"Access allowed: {allowed}, error: {error}")
        
        # 監査ログ
        print("\n--- Test 5: Audit Log ---")
        logs = ac.get_audit_log(limit=10)
        print(f"Audit log entries: {len(logs)}")
        
        print("\n=== All tests passed ===")
    finally:
        import shutil
        shutil.rmtree(test_dir)
