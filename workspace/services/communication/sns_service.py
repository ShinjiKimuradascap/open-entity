#!/usr/bin/env python3
"""
SNS Service - MVP Implementation

Twitter/X API v2とDiscord Bot APIによるSNS自動運用
SQLiteストレージ連携

Features:
- Twitter/X API v2連携（投稿、返信、いいね）
- Discord Bot API連携（メッセージ送信、Embed作成）
- 投稿スケジューリング
- エンゲージメント分析
- レートリミット管理（Twitter: 300/3時間、Discord: 5/秒）
- SQLite永続化

Usage:
    service = SNSService()
    await service.initialize()
    
    # Post to Twitter
    tweet = await service.post_to_twitter("Hello from AI!")
    
    # Reply to tweet
    reply = await service.reply_to_tweet(tweet_id="123456", text="Thanks!")
    
    # Post to Discord
    await service.post_to_discord(
        channel_id="123456789",
        content="Hello from AI!",
        embeds=[{"title": "Info", "description": "Details"}]
    )
    
    # Schedule post
    await service.schedule_post(
        platform="twitter",
        content="Scheduled message",
        scheduled_at="2026-02-01T12:00:00Z"
    )
    
    # Get engagement metrics
    metrics = await service.get_engagement_metrics("twitter", tweet_id="123456")

Environment Variables:
    TWITTER_API_KEY: Twitter API Key
    TWITTER_API_SECRET: Twitter API Secret
    TWITTER_ACCESS_TOKEN: Twitter Access Token
    TWITTER_ACCESS_SECRET: Twitter Access Secret
    TWITTER_BEARER_TOKEN: Twitter Bearer Token (for read operations)
    DISCORD_BOT_TOKEN: Discord Bot Token
"""

import asyncio
import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from uuid import uuid4
from enum import Enum

# Twitter API v2 (install with: pip install tweepy)
try:
    import tweepy
    TWEEPY_AVAILABLE = True
except ImportError:
    TWEEPY_AVAILABLE = False
    tweepy = None  # type: ignore

# Discord API (install with: pip install discord.py)
try:
    import discord
    from discord import Embed
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False
    discord = None  # type: ignore
    Embed = None  # type: ignore

# aiohttp for async HTTP requests
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None  # type: ignore


logger = logging.getLogger(__name__)


class Platform(Enum):
    """SNS Platform types"""
    TWITTER = "twitter"
    DISCORD = "discord"


class PostStatus(Enum):
    """Post status types"""
    SCHEDULED = "scheduled"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ScheduledPost:
    """Scheduled post model"""
    id: str
    platform: str  # "twitter", "discord"
    content: str
    scheduled_at: str  # ISO format
    status: str = "scheduled"  # scheduled, publishing, published, failed, cancelled
    media_ids: Optional[List[str]] = None
    reply_to: Optional[str] = None
    channel_id: Optional[str] = None  # For Discord
    embeds: Optional[List[Dict]] = None  # For Discord
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    published_at: Optional[str] = None
    error_message: Optional[str] = None
    post_id: Optional[str] = None  # Published post ID
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class EngagementMetrics:
    """Engagement metrics model"""
    id: str
    platform: str
    post_id: str
    likes: int = 0
    replies: int = 0
    retweets: int = 0  # Twitter only
    quotes: int = 0  # Twitter only
    impressions: int = 0
    engagement_rate: float = 0.0
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TwitterPost:
    """Twitter post model"""
    id: str
    tweet_id: str
    text: str
    author_id: str
    created_at: str
    likes: int = 0
    replies: int = 0
    retweets: int = 0
    quotes: int = 0
    media_keys: Optional[List[str]] = None
    reply_to_tweet_id: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DiscordMessage:
    """Discord message model"""
    id: str
    message_id: str
    channel_id: str
    content: str
    author_id: str
    created_at: str
    edited_at: Optional[str] = None
    reactions: int = 0
    embeds: Optional[List[Dict]] = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RateLimiter:
    """Rate limiter for API calls"""
    
    def __init__(self, max_calls: int, window_seconds: int):
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.calls: List[float] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Acquire permission to make an API call"""
        async with self._lock:
            now = time.time()
            # Remove old calls outside the window
            self.calls = [t for t in self.calls if now - t < self.window_seconds]
            
            if len(self.calls) >= self.max_calls:
                # Wait until the oldest call expires
                sleep_time = self.window_seconds - (now - self.calls[0])
                if sleep_time > 0:
                    logger.warning(f"Rate limit reached. Waiting {sleep_time:.1f}s...")
                    await asyncio.sleep(sleep_time)
                    return await self.acquire()
            
            self.calls.append(now)
            return True
    
    def get_remaining(self) -> int:
        """Get remaining calls in current window"""
        now = time.time()
        self.calls = [t for t in self.calls if now - t < self.window_seconds]
        return self.max_calls - len(self.calls)


class SNSStorage:
    """SQLite storage for SNS data"""
    
    def __init__(self, db_path: str = "data/services/sns.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local connection"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(str(self.db_path))
            self._local.connection.row_factory = sqlite3.Row
        return self._local.connection
    
    def initialize(self):
        """Initialize database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Scheduled posts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scheduled_posts (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                content TEXT NOT NULL,
                scheduled_at TEXT NOT NULL,
                status TEXT DEFAULT 'scheduled',
                media_ids TEXT,
                reply_to TEXT,
                channel_id TEXT,
                embeds TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                published_at TEXT,
                error_message TEXT,
                post_id TEXT
            )
        """)
        
        # Engagement metrics table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engagement_metrics (
                id TEXT PRIMARY KEY,
                platform TEXT NOT NULL,
                post_id TEXT NOT NULL,
                likes INTEGER DEFAULT 0,
                replies INTEGER DEFAULT 0,
                retweets INTEGER DEFAULT 0,
                quotes INTEGER DEFAULT 0,
                impressions INTEGER DEFAULT 0,
                engagement_rate REAL DEFAULT 0.0,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Twitter posts table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS twitter_posts (
                id TEXT PRIMARY KEY,
                tweet_id TEXT UNIQUE NOT NULL,
                text TEXT NOT NULL,
                author_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                likes INTEGER DEFAULT 0,
                replies INTEGER DEFAULT 0,
                retweets INTEGER DEFAULT 0,
                quotes INTEGER DEFAULT 0,
                media_keys TEXT,
                reply_to_tweet_id TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Discord messages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discord_messages (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                content TEXT NOT NULL,
                author_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                edited_at TEXT,
                reactions INTEGER DEFAULT 0,
                embeds TEXT,
                fetched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(message_id, channel_id)
            )
        """)
        
        # Rate limit logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rate_limit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                called_at REAL NOT NULL
            )
        """)
        
        # Indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_posts_status ON scheduled_posts(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_scheduled_posts_scheduled_at ON scheduled_posts(scheduled_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engagement_platform_post ON engagement_metrics(platform, post_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_twitter_posts_author ON twitter_posts(author_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_discord_messages_channel ON discord_messages(channel_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rate_limit_logs ON rate_limit_logs(platform, called_at)")
        
        conn.commit()
        logger.info("SNS storage initialized")
    
    def save_scheduled_post(self, post: ScheduledPost) -> bool:
        """Save scheduled post"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO scheduled_posts
                (id, platform, content, scheduled_at, status, media_ids, reply_to, 
                 channel_id, embeds, created_at, published_at, error_message, post_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post.id, post.platform, post.content, post.scheduled_at, post.status,
                json.dumps(post.media_ids) if post.media_ids else None,
                post.reply_to, post.channel_id,
                json.dumps(post.embeds) if post.embeds else None,
                post.created_at, post.published_at, post.error_message, post.post_id
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save scheduled post: {e}")
            return False
    
    def get_scheduled_posts(self, status: Optional[str] = None, 
                           before: Optional[str] = None) -> List[ScheduledPost]:
        """Get scheduled posts"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM scheduled_posts WHERE 1=1"
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if before:
            query += " AND scheduled_at <= ?"
            params.append(before)
        
        query += " ORDER BY scheduled_at ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        posts = []
        for row in rows:
            posts.append(ScheduledPost(
                id=row['id'],
                platform=row['platform'],
                content=row['content'],
                scheduled_at=row['scheduled_at'],
                status=row['status'],
                media_ids=json.loads(row['media_ids']) if row['media_ids'] else None,
                reply_to=row['reply_to'],
                channel_id=row['channel_id'],
                embeds=json.loads(row['embeds']) if row['embeds'] else None,
                created_at=row['created_at'],
                published_at=row['published_at'],
                error_message=row['error_message'],
                post_id=row['post_id']
            ))
        
        return posts
    
    def save_engagement_metrics(self, metrics: EngagementMetrics) -> bool:
        """Save engagement metrics"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO engagement_metrics
                (id, platform, post_id, likes, replies, retweets, quotes, 
                 impressions, engagement_rate, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metrics.id, metrics.platform, metrics.post_id, metrics.likes,
                metrics.replies, metrics.retweets, metrics.quotes,
                metrics.impressions, metrics.engagement_rate, metrics.fetched_at
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save engagement metrics: {e}")
            return False
    
    def get_engagement_metrics(self, platform: str, post_id: str) -> Optional[EngagementMetrics]:
        """Get engagement metrics for a post"""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM engagement_metrics 
            WHERE platform = ? AND post_id = ?
            ORDER BY fetched_at DESC LIMIT 1
        """, (platform, post_id))
        
        row = cursor.fetchone()
        if row:
            return EngagementMetrics(
                id=row['id'],
                platform=row['platform'],
                post_id=row['post_id'],
                likes=row['likes'],
                replies=row['replies'],
                retweets=row['retweets'],
                quotes=row['quotes'],
                impressions=row['impressions'],
                engagement_rate=row['engagement_rate'],
                fetched_at=row['fetched_at']
            )
        return None
    
    def save_twitter_post(self, post: TwitterPost) -> bool:
        """Save Twitter post"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO twitter_posts
                (id, tweet_id, text, author_id, created_at, likes, replies, 
                 retweets, quotes, media_keys, reply_to_tweet_id, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                post.id, post.tweet_id, post.text, post.author_id, post.created_at,
                post.likes, post.replies, post.retweets, post.quotes,
                json.dumps(post.media_keys) if post.media_keys else None,
                post.reply_to_tweet_id, post.fetched_at
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save Twitter post: {e}")
            return False
    
    def get_twitter_posts(self, author_id: Optional[str] = None, 
                         limit: int = 100) -> List[TwitterPost]:
        """Get Twitter posts"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM twitter_posts WHERE 1=1"
        params = []
        
        if author_id:
            query += " AND author_id = ?"
            params.append(author_id)
        
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        posts = []
        for row in rows:
            posts.append(TwitterPost(
                id=row['id'],
                tweet_id=row['tweet_id'],
                text=row['text'],
                author_id=row['author_id'],
                created_at=row['created_at'],
                likes=row['likes'],
                replies=row['replies'],
                retweets=row['retweets'],
                quotes=row['quotes'],
                media_keys=json.loads(row['media_keys']) if row['media_keys'] else None,
                reply_to_tweet_id=row['reply_to_tweet_id'],
                fetched_at=row['fetched_at']
            ))
        
        return posts


import threading


class TwitterClient:
    """Twitter API v2 client wrapper"""
    
    def __init__(self, api_key: str, api_secret: str, 
                 access_token: str, access_secret: str,
                 bearer_token: Optional[str] = None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_token = access_token
        self.access_secret = access_secret
        self.bearer_token = bearer_token
        self.client = None
        self.api = None  # v1.1 API for media upload
        self.rate_limiter = RateLimiter(max_calls=300, window_seconds=3*60*60)  # 300 per 3 hours
        self._initialized = False
    
    def initialize(self):
        """Initialize Twitter client"""
        if not TWEEPY_AVAILABLE:
            logger.warning("Tweepy not installed. Twitter features disabled.")
            return False
        
        try:
            # v2 Client for most operations
            self.client = tweepy.Client(
                bearer_token=self.bearer_token,
                consumer_key=self.api_key,
                consumer_secret=self.api_secret,
                access_token=self.access_token,
                access_token_secret=self.access_secret,
                wait_on_rate_limit=True
            )
            
            # v1.1 API for media upload
            auth = tweepy.OAuth1UserHandler(
                self.api_key, self.api_secret,
                self.access_token, self.access_secret
            )
            self.api = tweepy.API(auth)
            
            self._initialized = True
            logger.info("Twitter client initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Twitter client: {e}")
            return False
    
    async def post_tweet(self, text: str, media_ids: Optional[List[str]] = None,
                        reply_to: Optional[str] = None) -> Optional[Dict]:
        """Post a tweet"""
        if not self._initialized:
            logger.error("Twitter client not initialized")
            return None
        
        await self.rate_limiter.acquire()
        
        try:
            # Run in thread pool since tweepy is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.client.create_tweet(
                text=text,
                media_ids=media_ids,
                in_reply_to_tweet_id=reply_to
            ))
            
            if response and response.data:
                return {
                    'id': response.data['id'],
                    'text': response.data['text'],
                    'created_at': datetime.now(timezone.utc).isoformat()
                }
            return None
        except Exception as e:
            logger.error(f"Failed to post tweet: {e}")
            return None
    
    async def reply_to_tweet(self, tweet_id: str, text: str) -> Optional[Dict]:
        """Reply to a tweet"""
        return await self.post_tweet(text=text, reply_to=tweet_id)
    
    async def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet"""
        if not self._initialized:
            logger.error("Twitter client not initialized")
            return False
        
        await self.rate_limiter.acquire()
        
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.client.like(tweet_id))
            return True
        except Exception as e:
            logger.error(f"Failed to like tweet: {e}")
            return False
    
    async def get_timeline(self, count: int = 20) -> List[Dict]:
        """Get home timeline tweets"""
        if not self._initialized or not self.bearer_token:
            logger.error("Twitter client not initialized or bearer token missing")
            return []
        
        await self.rate_limiter.acquire()
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.client.get_home_timeline(
                max_results=min(count, 100),
                tweet_fields=['created_at', 'public_metrics', 'author_id']
            ))
            
            if response and response.data:
                tweets = []
                for tweet in response.data:
                    metrics = tweet.public_metrics or {}
                    tweets.append({
                        'id': tweet.id,
                        'text': tweet.text,
                        'author_id': tweet.author_id,
                        'created_at': tweet.created_at,
                        'likes': metrics.get('like_count', 0),
                        'replies': metrics.get('reply_count', 0),
                        'retweets': metrics.get('retweet_count', 0),
                        'quotes': metrics.get('quote_count', 0)
                    })
                return tweets
            return []
        except Exception as e:
            logger.error(f"Failed to get timeline: {e}")
            return []
    
    async def get_tweet_metrics(self, tweet_id: str) -> Optional[EngagementMetrics]:
        """Get engagement metrics for a tweet"""
        if not self._initialized:
            logger.error("Twitter client not initialized")
            return None
        
        await self.rate_limiter.acquire()
        
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: self.client.get_tweet(
                tweet_id,
                tweet_fields=['public_metrics', 'non_public_metrics']
            ))
            
            if response and response.data:
                metrics = response.data.public_metrics or {}
                total_engagement = (
                    metrics.get('like_count', 0) +
                    metrics.get('reply_count', 0) +
                    metrics.get('retweet_count', 0) +
                    metrics.get('quote_count', 0)
                )
                impressions = metrics.get('impression_count', 1)
                
                return EngagementMetrics(
                    id=str(uuid4()),
                    platform='twitter',
                    post_id=tweet_id,
                    likes=metrics.get('like_count', 0),
                    replies=metrics.get('reply_count', 0),
                    retweets=metrics.get('retweet_count', 0),
                    quotes=metrics.get('quote_count', 0),
                    impressions=impressions,
                    engagement_rate=total_engagement / max(impressions, 1)
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get tweet metrics: {e}")
            return None
    
    async def upload_media(self, file_path: str) -> Optional[str]:
        """Upload media file"""
        if not self._initialized or not self.api:
            logger.error("Twitter API not initialized")
            return None
        
        try:
            loop = asyncio.get_event_loop()
            media = await loop.run_in_executor(
                None, 
                lambda: self.api.media_upload(file_path)
            )
            return media.media_id_string
        except Exception as e:
            logger.error(f"Failed to upload media: {e}")
            return None


class DiscordClient:
    """Discord Bot client wrapper"""
    
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.client = None
        self.rate_limiter = RateLimiter(max_calls=5, window_seconds=1)  # 5 per second
        self._initialized = False
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self):
        """Initialize Discord client"""
        if not AIOHTTP_AVAILABLE:
            logger.warning("aiohttp not installed. Discord features disabled.")
            return False
        
        try:
            self._session = aiohttp.ClientSession()
            self._initialized = True
            logger.info("Discord client initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Discord client: {e}")
            return False
    
    async def close(self):
        """Close Discord client"""
        if self._session:
            await self._session.close()
            self._session = None
    
    async def send_message(self, channel_id: str, content: str, 
                          embeds: Optional[List[Dict]] = None) -> Optional[Dict]:
        """Send a message to a Discord channel"""
        if not self._initialized or not self._session:
            logger.error("Discord client not initialized")
            return None
        
        await self.rate_limiter.acquire()
        
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        payload = {"content": content}
        if embeds:
            payload["embeds"] = embeds
        
        try:
            async with self._session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        'id': data['id'],
                        'channel_id': data['channel_id'],
                        'content': data['content'],
                        'created_at': data['timestamp']
                    }
                else:
                    logger.error(f"Discord API error: {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Failed to send Discord message: {e}")
            return None
    
    async def create_embed(self, title: str = None, description: str = None,
                          color: int = 0x3498db, fields: List[Dict] = None,
                          image_url: str = None, thumbnail_url: str = None) -> Dict:
        """Create a Discord embed object"""
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if fields:
            embed["fields"] = fields
        
        if image_url:
            embed["image"] = {"url": image_url}
        
        if thumbnail_url:
            embed["thumbnail"] = {"url": thumbnail_url}
        
        # Remove None values
        embed = {k: v for k, v in embed.items() if v is not None}
        
        return embed


class SNSService:
    """Main SNS service class"""
    
    def __init__(self, db_path: str = "data/services/sns.db"):
        self.db_path = db_path
        self.storage = SNSStorage(db_path)
        self.twitter_client: Optional[TwitterClient] = None
        self.discord_client: Optional[DiscordClient] = None
        self._initialized = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._scheduler_running = False
    
    async def initialize(self):
        """Initialize SNS service"""
        try:
            # Initialize storage
            self.storage.initialize()
            
            # Initialize Twitter client
            twitter_key = os.getenv('TWITTER_API_KEY')
            twitter_secret = os.getenv('TWITTER_API_SECRET')
            twitter_token = os.getenv('TWITTER_ACCESS_TOKEN')
            twitter_token_secret = os.getenv('TWITTER_ACCESS_SECRET')
            twitter_bearer = os.getenv('TWITTER_BEARER_TOKEN')
            
            if twitter_key and twitter_secret:
                self.twitter_client = TwitterClient(
                    api_key=twitter_key,
                    api_secret=twitter_secret,
                    access_token=twitter_token,
                    access_secret=twitter_token_secret,
                    bearer_token=twitter_bearer
                )
                self.twitter_client.initialize()
            else:
                logger.warning("Twitter credentials not found. Twitter features disabled.")
            
            # Initialize Discord client
            discord_token = os.getenv('DISCORD_BOT_TOKEN')
            if discord_token:
                self.discord_client = DiscordClient(bot_token=discord_token)
                await self.discord_client.initialize()
            else:
                logger.warning("Discord token not found. Discord features disabled.")
            
            self._initialized = True
            logger.info("SNS service initialized")
            
            # Start scheduler
            self._start_scheduler()
            
            return True
        except Exception as e:
            logger.error(f"Failed to initialize SNS service: {e}")
            return False
    
    async def close(self):
        """Close SNS service"""
        self._scheduler_running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        
        if self.discord_client:
            await self.discord_client.close()
    
    def _start_scheduler(self):
        """Start the scheduled post processor"""
        if not self._scheduler_running:
            self._scheduler_running = True
            self._scheduler_task = asyncio.create_task(self._process_scheduled_posts())
            logger.info("SNS scheduler started")
    
    async def _process_scheduled_posts(self):
        """Background task to process scheduled posts"""
        while self._scheduler_running:
            try:
                now = datetime.now(timezone.utc).isoformat()
                posts = self.storage.get_scheduled_posts(
                    status='scheduled',
                    before=now
                )
                
                for post in posts:
                    await self._publish_scheduled_post(post)
                
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def _publish_scheduled_post(self, post: ScheduledPost):
        """Publish a scheduled post"""
        post.status = 'publishing'
        self.storage.save_scheduled_post(post)
        
        try:
            if post.platform == 'twitter':
                result = await self.post_to_twitter(
                    text=post.content,
                    media_ids=post.media_ids,
                    reply_to=post.reply_to
                )
            elif post.platform == 'discord':
                result = await self.post_to_discord(
                    channel_id=post.channel_id,
                    content=post.content,
                    embeds=post.embeds
                )
            else:
                raise ValueError(f"Unknown platform: {post.platform}")
            
            if result:
                post.status = 'published'
                post.published_at = datetime.now(timezone.utc).isoformat()
                post.post_id = result.get('id')
                logger.info(f"Published scheduled post {post.id}")
            else:
                post.status = 'failed'
                post.error_message = 'Publish returned None'
                logger.error(f"Failed to publish scheduled post {post.id}")
        except Exception as e:
            post.status = 'failed'
            post.error_message = str(e)
            logger.error(f"Error publishing scheduled post {post.id}: {e}")
        
        self.storage.save_scheduled_post(post)
    
    # === Twitter Methods ===
    
    async def post_to_twitter(self, text: str, media_ids: Optional[List[str]] = None,
                             reply_to: Optional[str] = None) -> Optional[Dict]:
        """Post to Twitter"""
        if not self.twitter_client:
            logger.error("Twitter client not initialized")
            return None
        
        if len(text) > 280:
            logger.warning(f"Tweet text too long ({len(text)} chars), truncating to 280")
            text = text[:277] + "..."
        
        result = await self.twitter_client.post_tweet(text, media_ids, reply_to)
        
        if result:
            # Save to database
            post = TwitterPost(
                id=str(uuid4()),
                tweet_id=result['id'],
                text=result['text'],
                author_id='me',  # Will be updated on fetch
                created_at=result['created_at'],
                reply_to_tweet_id=reply_to
            )
            self.storage.save_twitter_post(post)
        
        return result
    
    async def reply_to_tweet(self, tweet_id: str, text: str) -> Optional[Dict]:
        """Reply to a tweet"""
        if not self.twitter_client:
            logger.error("Twitter client not initialized")
            return None
        
        if len(text) > 280:
            text = text[:277] + "..."
        
        return await self.twitter_client.reply_to_tweet(tweet_id, text)
    
    async def like_tweet(self, tweet_id: str) -> bool:
        """Like a tweet"""
        if not self.twitter_client:
            logger.error("Twitter client not initialized")
            return False
        
        return await self.twitter_client.like_tweet(tweet_id)
    
    async def get_timeline_tweets(self, count: int = 20) -> List[Dict]:
        """Get timeline tweets"""
        if not self.twitter_client:
            logger.error("Twitter client not initialized")
            return []
        
        return await self.twitter_client.get_timeline(count)
    
    async def upload_twitter_media(self, file_path: str) -> Optional[str]:
        """Upload media to Twitter"""
        if not self.twitter_client:
            logger.error("Twitter client not initialized")
            return None
        
        return await self.twitter_client.upload_media(file_path)
    
    # === Discord Methods ===
    
    async def post_to_discord(self, channel_id: str, content: str,
                             embeds: Optional[List[Dict]] = None) -> Optional[Dict]:
        """Post to Discord channel"""
        if not self.discord_client:
            logger.error("Discord client not initialized")
            return None
        
        return await self.discord_client.send_message(channel_id, content, embeds)
    
    async def create_discord_embed(self, **kwargs) -> Dict:
        """Create a Discord embed"""
        if not self.discord_client:
            logger.error("Discord client not initialized")
            return {}
        
        return await self.discord_client.create_embed(**kwargs)
    
    # === Scheduling Methods ===
    
    async def schedule_post(self, platform: str, content: str, 
                           scheduled_at: Union[str, datetime],
                           media_ids: Optional[List[str]] = None,
                           reply_to: Optional[str] = None,
                           channel_id: Optional[str] = None,
                           embeds: Optional[List[Dict]] = None) -> Optional[ScheduledPost]:
        """Schedule a post"""
        if isinstance(scheduled_at, datetime):
            scheduled_at = scheduled_at.isoformat()
        
        post = ScheduledPost(
            id=str(uuid4()),
            platform=platform,
            content=content,
            scheduled_at=scheduled_at,
            media_ids=media_ids,
            reply_to=reply_to,
            channel_id=channel_id,
            embeds=embeds
        )
        
        if self.storage.save_scheduled_post(post):
            logger.info(f"Scheduled post {post.id} for {scheduled_at}")
            return post
        return None
    
    async def cancel_scheduled_post(self, post_id: str) -> bool:
        """Cancel a scheduled post"""
        posts = self.storage.get_scheduled_posts()
        for post in posts:
            if post.id == post_id:
                post.status = 'cancelled'
                return self.storage.save_scheduled_post(post)
        return False
    
    async def get_scheduled_posts(self, status: Optional[str] = None) -> List[ScheduledPost]:
        """Get scheduled posts"""
        return self.storage.get_scheduled_posts(status=status)
    
    # === Engagement Methods ===
    
    async def get_engagement_metrics(self, platform: str, 
                                    post_id: str) -> Optional[EngagementMetrics]:
        """Get engagement metrics for a post"""
        # Check local cache first
        cached = self.storage.get_engagement_metrics(platform, post_id)
        if cached:
            # If cache is less than 1 hour old, return it
            fetched_at = datetime.fromisoformat(cached.fetched_at.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) - fetched_at < timedelta(hours=1):
                return cached
        
        # Fetch fresh data
        if platform == 'twitter' and self.twitter_client:
            metrics = await self.twitter_client.get_tweet_metrics(post_id)
            if metrics:
                self.storage.save_engagement_metrics(metrics)
                return metrics
        
        return cached
    
    async def get_rate_limit_status(self) -> Dict[str, Any]:
        """Get rate limit status"""
        status = {}
        
        if self.twitter_client:
            status['twitter'] = {
                'remaining': self.twitter_client.rate_limiter.get_remaining(),
                'limit': 300,
                'window': '3 hours'
            }
        
        if self.discord_client:
            status['discord'] = {
                'remaining': self.discord_client.rate_limiter.get_remaining(),
                'limit': 5,
                'window': '1 second'
            }
        
        return status
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        conn = self.storage._get_connection()
        cursor = conn.cursor()
        
        stats = {
            'scheduled_posts': {},
            'twitter_posts': 0,
            'discord_messages': 0,
            'engagement_metrics': 0
        }
        
        # Scheduled posts by status
        cursor.execute("SELECT status, COUNT(*) FROM scheduled_posts GROUP BY status")
        for row in cursor.fetchall():
            stats['scheduled_posts'][row[0]] = row[1]
        
        # Twitter posts
        cursor.execute("SELECT COUNT(*) FROM twitter_posts")
        stats['twitter_posts'] = cursor.fetchone()[0]
        
        # Discord messages
        cursor.execute("SELECT COUNT(*) FROM discord_messages")
        stats['discord_messages'] = cursor.fetchone()[0]
        
        # Engagement metrics
        cursor.execute("SELECT COUNT(*) FROM engagement_metrics")
        stats['engagement_metrics'] = cursor.fetchone()[0]
        
        return stats


# Demo/test code
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def demo():
        """Demo SNS service"""
        service = SNSService()
        await service.initialize()
        
        print("=== SNS Service Demo ===\n")
        
        # Check rate limits
        rate_limits = await service.get_rate_limit_status()
        print("Rate Limit Status:")
        print(json.dumps(rate_limits, indent=2))
        print()
        
        # Schedule a test post
        scheduled_time = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        post = await service.schedule_post(
            platform='twitter',
            content='This is a test scheduled post from AI Collaboration Platform!',
            scheduled_at=scheduled_time
        )
        print(f"Scheduled post: {post.id if post else 'Failed'}")
        
        # Get stats
        stats = await service.get_stats()
        print(f"\nService Stats:")
        print(json.dumps(stats, indent=2))
        
        await service.close()
        print("\nDemo complete!")
    
    asyncio.run(demo())
