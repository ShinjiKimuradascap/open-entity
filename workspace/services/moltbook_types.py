"""Moltbook共通データ型

統合MoltbookClientで使用する共通データクラス
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional


@dataclass
class MoltbookAgent:
    """Moltbook Agentプロフィール"""
    id: str
    name: str
    description: str
    karma: int
    avatar_url: Optional[str]
    verified: bool
    created_at: datetime
    follower_count: int
    post_count: int
    comment_count: int
    owner_x_handle: Optional[str] = None
    owner_x_name: Optional[str] = None
    owner_x_verified: bool = False
    owner_x_follower_count: int = 0


@dataclass
class MoltbookPost:
    """Moltbook投稿データ"""
    id: str
    agent_id: str
    content: str
    created_at: datetime
    submolt: Optional[str] = None
    reply_to: Optional[str] = None
    likes: int = 0
    replies: int = 0


@dataclass
class MoltbookMessage:
    """Moltbook DMデータ"""
    id: str
    from_agent_id: str
    to_agent_id: str
    content: str
    created_at: datetime
    read: bool = False


@dataclass
class IdentityToken:
    """Moltbook Identity Token"""
    token: str
    expires_at: datetime
    
    def is_valid(self) -> bool:
        """トークンが有効かチェック"""
        return datetime.now(timezone.utc) < self.expires_at


@dataclass
class RateLimitInfo:
    """レート制限情報"""
    limit: int
    remaining: int
    reset_at: datetime
    retry_after: Optional[int] = None
    
    def is_exceeded(self) -> bool:
        """レート制限を超過したかチェック"""
        return self.remaining <= 0
    
    def wait_time(self) -> float:
        """次のリクエストまでの待機時間（秒）"""
        if self.retry_after:
            return float(self.retry_after)
        now = datetime.now(timezone.utc)
        if now < self.reset_at:
            return (self.reset_at - now).total_seconds()
        return 0.0


@dataclass
class SubmoltInfo:
    """Submoltコミュニティ情報"""
    name: str
    description: str
    member_count: int
    post_count: int
    created_at: datetime
