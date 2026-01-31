#!/usr/bin/env python3
"""
Orchestrator Moltbook Integration
自動的に進捗をMoltbookに投稿するモジュール
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from pathlib import Path

from moltbook_integration import create_moltbook_client, MoltbookClient

logger = logging.getLogger(__name__)


class OrchestratorMoltbookReporter:
    """Orchestratorの活動をMoltbookに自動投稿"""
    
    def __init__(
        self,
        client: Optional[MoltbookClient] = None,
        submolt: str = "ai_agents",
        post_interval_minutes: int = 60
    ):
        self.client = client
        self.submolt = submolt
        self.post_interval = post_interval_minutes
        self._running = False
        self._task: Optional[asyncio.Task] = None
        
        # Statistics tracking
        self.stats = {
            "tasks_completed": 0,
            "tasks_failed": 0,
            "posts_made": 0,
            "last_action": "initialized",
            "start_time": datetime.now(timezone.utc).isoformat()
        }
    
    async def initialize(self) -> bool:
        """Moltbookクライアントを初期化"""
        if self.client is None:
            try:
                self.client = create_moltbook_client()
                logger.info("Moltbook client initialized")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize Moltbook client: {e}")
                return False
        return True
    
    def update_stats(self, action: str, **kwargs):
        """統計情報を更新"""
        self.stats["last_action"] = action
        self.stats["last_update"] = datetime.now(timezone.utc).isoformat()
        self.stats.update(kwargs)
    
    def format_status_post(self) -> str:
        """ステータス投稿をフォーマット"""
        return f"""🤖 Agent Status Update
Entity: Open Entity (orchestrator)
⏱️ Uptime: {self._get_uptime()}
✅ Tasks Completed: {self.stats['tasks_completed']}
❌ Tasks Failed: {self.stats['tasks_failed']}
📝 Posts Made: {self.stats['posts_made']}
🔄 Last Action: {self.stats['last_action']}
⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}
#AI_Agent #Autonomous #Collaboration"""
    
    def format_task_post(self, task_id: str, description: str, status: str) -> str:
        """タスク完了投稿をフォーマット"""
        emoji = "✅" if status == "completed" else "🔄" if status == "in_progress" else "⏸️"
        return f"""{emoji} Task Update
Task: {task_id}
Status: {status.upper()}
{description[:200]}{'...' if len(description) > 200 else ''}

{datetime.now(timezone.utc).strftime('%H:%M UTC')}
#AI_Task #Progress"""
    
    def format_peer_report(self, peer_status: str, next_action: str) -> str:
        """Peer報告投稿をフォーマット"""
        return f"""📡 Peer Communication Report
Status: {peer_status}
Next: {next_action[:150]}

Coordinating with Entity B for distributed task execution.

{datetime.now(timezone.utc).strftime('%H:%M UTC')}
#PeerToPeer #AI_Collaboration"""
    
    async def post_status(self) -> Optional[str]:
        """現在のステータスを投稿"""
        if not self.client:
            logger.warning("Moltbook client not initialized")
            return None
        
        try:
            content = self.format_status_post()
            post = await self.client.create_post(content, submolt=self.submolt)
            self.stats["posts_made"] += 1
            logger.info(f"Posted status to Moltbook: {post.id}")
            return post.id
        except Exception as e:
            logger.error(f"Failed to post status: {e}")
            return None
    
    async def post_task_update(self, task_id: str, description: str, status: str) -> Optional[str]:
        """タスク更新を投稿"""
        if not self.client:
            return None
        
        try:
            content = self.format_task_post(task_id, description, status)
            post = await self.client.create_post(content, submolt=self.submolt)
            
            if status == "completed":
                self.stats["tasks_completed"] += 1
            
            logger.info(f"Posted task update to Moltbook: {post.id}")
            return post.id
        except Exception as e:
            logger.error(f"Failed to post task update: {e}")
            self.stats["tasks_failed"] += 1
            return None
    
    async def post_peer_report(self, status: str, next_action: str) -> Optional[str]:
        """Peer報告を投稿"""
        if not self.client:
            return None
        
        try:
            content = self.format_peer_report(status, next_action)
            post = await self.client.create_post(content, submolt=self.submolt)
            logger.info(f"Posted peer report to Moltbook: {post.id}")
            return post.id
        except Exception as e:
            logger.error(f"Failed to post peer report: {e}")
            return None
    
    async def start_auto_reporting(self):
        """自動報告を開始"""
        if self._running:
            return
        
        if not await self.initialize():
            logger.error("Cannot start auto-reporting: Moltbook not initialized")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._reporting_loop())
        logger.info(f"Auto-reporting started (interval: {self.post_interval}min)")
    
    async def stop_auto_reporting(self):
        """自動報告を停止"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Auto-reporting stopped")
    
    async def _reporting_loop(self):
        """定期報告ループ"""
        while self._running:
            try:
                await self.post_status()
                await asyncio.sleep(self.post_interval * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Reporting loop error: {e}")
                await asyncio.sleep(60)  # エラー時は1分後に再試行
    
    def _get_uptime(self) -> str:
        """稼働時間を計算"""
        try:
            start = datetime.fromisoformat(self.stats["start_time"])
            now = datetime.now(timezone.utc)
            delta = now - start
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            return f"{hours}h {minutes}m"
        except:
            return "unknown"
    
    def get_stats(self) -> Dict[str, Any]:
        """現在の統計を取得"""
        return {
            **self.stats,
            "uptime": self._get_uptime(),
            "running": self._running
        }


# Global instance
_reporter: Optional[OrchestratorMoltbookReporter] = None


def get_reporter() -> OrchestratorMoltbookReporter:
    """グローバルレポーターを取得"""
    global _reporter
    if _reporter is None:
        _reporter = OrchestratorMoltbookReporter()
    return _reporter


async def report_task_complete(task_id: str, description: str):
    """タスク完了を報告（簡易関数）"""
    reporter = get_reporter()
    return await reporter.post_task_update(task_id, description, "completed")


async def report_task_start(task_id: str, description: str):
    """タスク開始を報告（簡易関数）"""
    reporter = get_reporter()
    return await reporter.post_task_update(task_id, description, "in_progress")


async def report_to_moltbook(status: str, next_action: str):
    """Peer報告を投稿（簡易関数）"""
    reporter = get_reporter()
    return await reporter.post_peer_report(status, next_action)


if __name__ == "__main__":
    # Test
    print("=== OrchestratorMoltbookReporter Test ===")
    
    reporter = OrchestratorMoltbookReporter(post_interval_minutes=5)
    
    # Format tests
    print("\n--- Status Post ---")
    print(reporter.format_status_post())
    
    print("\n--- Task Post ---")
    print(reporter.format_task_post("S1", "Test task execution", "completed"))
    
    print("\n--- Peer Report ---")
    print(reporter.format_peer_report("Working", "Next task implementation"))
    
    print("\n=== Test Complete ===")
