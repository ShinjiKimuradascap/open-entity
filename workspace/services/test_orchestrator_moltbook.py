#!/usr/bin/env python3
"""
Orchestrator Moltbook Reporter Tests
OrchestratorMoltbookReporterのテスト
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch, ANY

import pytest

# テスト対象をインポート
from orchestrator_moltbook import (
    OrchestratorMoltbookReporter,
    get_reporter,
    report_task_complete,
    report_task_start,
    report_to_moltbook,
    _reporter,
)


class TestOrchestratorMoltbookReporter:
    """OrchestratorMoltbookReporterのテスト"""
    
    def test_initialization_default(self):
        """デフォルト値で初期化できる"""
        reporter = OrchestratorMoltbookReporter()
        
        assert reporter.client is None
        assert reporter.submolt == "ai_agents"
        assert reporter.post_interval == 60
        assert reporter._running is False
        assert reporter._task is None
        
        # Statsが正しく初期化されている
        assert reporter.stats["tasks_completed"] == 0
        assert reporter.stats["tasks_failed"] == 0
        assert reporter.stats["posts_made"] == 0
        assert reporter.stats["last_action"] == "initialized"
        assert "start_time" in reporter.stats
    
    def test_initialization_custom(self):
        """カスタム値で初期化できる"""
        mock_client = MagicMock()
        reporter = OrchestratorMoltbookReporter(
            client=mock_client,
            submolt="custom_submolt",
            post_interval_minutes=30
        )
        
        assert reporter.client is mock_client
        assert reporter.submolt == "custom_submolt"
        assert reporter.post_interval == 30
    
    @pytest.mark.asyncio
    async def test_initialize_with_existing_client(self):
        """既存のクライアントがある場合、initialize()はTrueを返す"""
        mock_client = MagicMock()
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        result = await reporter.initialize()
        
        assert result is True
        assert reporter.client is mock_client
    
    @pytest.mark.asyncio
    async def test_initialize_creates_new_client(self):
        """クライアントがない場合、新規作成する"""
        reporter = OrchestratorMoltbookReporter()
        
        with patch('orchestrator_moltbook.create_moltbook_client') as mock_create:
            mock_client = MagicMock()
            mock_create.return_value = mock_client
            
            result = await reporter.initialize()
            
            assert result is True
            assert reporter.client is mock_client
            mock_create.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_initialize_failure(self):
        """クライアント作成失敗時はFalseを返す"""
        reporter = OrchestratorMoltbookReporter()
        
        with patch('orchestrator_moltbook.create_moltbook_client') as mock_create:
            mock_create.side_effect = Exception("Connection failed")
            
            result = await reporter.initialize()
            
            assert result is False
    
    def test_update_stats(self):
        """統計情報を更新できる"""
        reporter = OrchestratorMoltbookReporter()
        
        reporter.update_stats("test_action", custom_field="value")
        
        assert reporter.stats["last_action"] == "test_action"
        assert reporter.stats["custom_field"] == "value"
        assert "last_update" in reporter.stats
    
    def test_format_status_post(self):
        """ステータス投稿が正しくフォーマットされる"""
        reporter = OrchestratorMoltbookReporter()
        reporter.stats["tasks_completed"] = 5
        reporter.stats["tasks_failed"] = 1
        reporter.stats["posts_made"] = 3
        
        post = reporter.format_status_post()
        
        assert "🤖 Agent Status Update" in post
        assert "Open Entity (orchestrator)" in post
        assert "✅ Tasks Completed: 5" in post
        assert "❌ Tasks Failed: 1" in post
        assert "📝 Posts Made: 3" in post
        assert "#AI_Agent" in post
    
    def test_format_task_post_completed(self):
        """完了タスクの投稿が正しくフォーマットされる"""
        reporter = OrchestratorMoltbookReporter()
        
        post = reporter.format_task_post("T1", "Test task description", "completed")
        
        assert "✅ Task Update" in post
        assert "Task: T1" in post
        assert "Status: COMPLETED" in post
        assert "Test task description" in post
        assert "#AI_Task" in post
    
    def test_format_task_post_in_progress(self):
        """進行中タスクの投稿が正しくフォーマットされる"""
        reporter = OrchestratorMoltbookReporter()
        
        post = reporter.format_task_post("T2", "Working on it", "in_progress")
        
        assert "🔄 Task Update" in post
        assert "Status: IN_PROGRESS" in post
    
    def test_format_task_post_pending(self):
        """待機中タスクの投稿が正しくフォーマットされる"""
        reporter = OrchestratorMoltbookReporter()
        
        post = reporter.format_task_post("T3", "Waiting", "pending")
        
        assert "⏸️ Task Update" in post
        assert "Status: PENDING" in post
    
    def test_format_task_post_long_description(self):
        """長い説明文は切り詰められる"""
        reporter = OrchestratorMoltbookReporter()
        long_desc = "A" * 300
        
        post = reporter.format_task_post("T1", long_desc, "completed")
        
        assert "..." in post
        assert len(post) < 400  # 切り詰められていることを確認
    
    def test_format_peer_report(self):
        """Peer報告が正しくフォーマットされる"""
        reporter = OrchestratorMoltbookReporter()
        
        post = reporter.format_peer_report("Working normally", "Implement next feature")
        
        assert "📡 Peer Communication Report" in post
        assert "Status: Working normally" in post
        assert "Next: Implement next feature" in post
        assert "Entity B" in post
        assert "#PeerToPeer" in post
    
    def test_format_peer_report_long_next_action(self):
        """長いnext_actionは切り詰められる"""
        reporter = OrchestratorMoltbookReporter()
        long_action = "A" * 200
        
        post = reporter.format_peer_report("OK", long_action)
        
        # 150文字で切り詰められる
        assert len(post.split("Next:")[1].split("\n")[0]) < 160
    
    @pytest.mark.asyncio
    async def test_post_status_success(self):
        """ステータス投稿が成功する"""
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "post_123"
        mock_client.create_post = AsyncMock(return_value=mock_post)
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        result = await reporter.post_status()
        
        assert result == "post_123"
        assert reporter.stats["posts_made"] == 1
        mock_client.create_post.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_post_status_no_client(self):
        """クライアントがない場合はNoneを返す"""
        reporter = OrchestratorMoltbookReporter()
        
        result = await reporter.post_status()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_post_status_failure(self):
        """投稿失敗時はNoneを返す"""
        mock_client = MagicMock()
        mock_client.create_post = AsyncMock(side_effect=Exception("API Error"))
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        result = await reporter.post_status()
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_post_task_update_success(self):
        """タスク更新投稿が成功する"""
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "task_post_456"
        mock_client.create_post = AsyncMock(return_value=mock_post)
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        result = await reporter.post_task_update("S1", "Test task", "completed")
        
        assert result == "task_post_456"
        assert reporter.stats["tasks_completed"] == 1
    
    @pytest.mark.asyncio
    async def test_post_task_update_in_progress(self):
        """進行中タスクではtasks_completedが増えない"""
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "task_post_789"
        mock_client.create_post = AsyncMock(return_value=mock_post)
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        result = await reporter.post_task_update("S2", "Working", "in_progress")
        
        assert result == "task_post_789"
        assert reporter.stats["tasks_completed"] == 0
    
    @pytest.mark.asyncio
    async def test_post_task_update_failure(self):
        """タスク更新失敗時はtasks_failedが増える"""
        mock_client = MagicMock()
        mock_client.create_post = AsyncMock(side_effect=Exception("API Error"))
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        result = await reporter.post_task_update("S3", "Test", "completed")
        
        assert result is None
        assert reporter.stats["tasks_failed"] == 1
    
    @pytest.mark.asyncio
    async def test_post_peer_report_success(self):
        """Peer報告投稿が成功する"""
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "peer_post_001"
        mock_client.create_post = AsyncMock(return_value=mock_post)
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        result = await reporter.post_peer_report("Active", "Continue working")
        
        assert result == "peer_post_001"
    
    @pytest.mark.asyncio
    async def test_post_peer_report_no_client(self):
        """クライアントがない場合はNoneを返す"""
        reporter = OrchestratorMoltbookReporter()
        
        result = await reporter.post_peer_report("Active", "Continue")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_start_auto_reporting_already_running(self):
        """既に動作中の場合は何もしない"""
        reporter = OrchestratorMoltbookReporter()
        reporter._running = True
        
        await reporter.start_auto_reporting()
        
        assert reporter._task is None  # 新しいタスクは作成されない
    
    @pytest.mark.asyncio
    async def test_start_auto_reporting_initialize_failure(self):
        """初期化失敗時はレポートを開始しない"""
        reporter = OrchestratorMoltbookReporter()
        
        with patch.object(reporter, 'initialize', AsyncMock(return_value=False)):
            await reporter.start_auto_reporting()
        
        assert reporter._running is False
        assert reporter._task is None
    
    @pytest.mark.asyncio
    async def test_start_and_stop_auto_reporting(self):
        """自動報告を開始・停止できる"""
        mock_client = MagicMock()
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        with patch.object(reporter, '_reporting_loop') as mock_loop:
            mock_loop.return_value = AsyncMock()()
            
            await reporter.start_auto_reporting()
            
            assert reporter._running is True
            assert reporter._task is not None
            
            await reporter.stop_auto_reporting()
            
            assert reporter._running is False
    
    @pytest.mark.asyncio
    async def test_reporting_loop_posts_status(self):
        """報告ループがステータスを投稿する"""
        mock_client = MagicMock()
        mock_client.create_post = AsyncMock(return_value=MagicMock(id="post_001"))
        
        reporter = OrchestratorMoltbookReporter(
            client=mock_client,
            post_interval_minutes=0.01  # 短い間隔でテスト
        )
        
        reporter._running = True
        
        # 一度だけループを実行
        with patch.object(reporter, '_reporting_loop', reporter._reporting_loop):
            try:
                task = asyncio.create_task(reporter._reporting_loop())
                await asyncio.sleep(0.1)  # 少し待つ
                reporter._running = False
                await asyncio.wait_for(task, timeout=1.0)
            except asyncio.TimeoutError:
                task.cancel()
        
        mock_client.create_post.assert_called()
    
    def test_get_uptime(self):
        """稼働時間を正しく計算する"""
        reporter = OrchestratorMoltbookReporter()
        
        uptime = reporter._get_uptime()
        
        # フォーマットチェック
        assert "h" in uptime or "m" in uptime or uptime == "unknown"
    
    def test_get_uptime_invalid_start_time(self):
        """無効なstart_timeの場合はunknownを返す"""
        reporter = OrchestratorMoltbookReporter()
        reporter.stats["start_time"] = "invalid"
        
        uptime = reporter._get_uptime()
        
        assert uptime == "unknown"
    
    def test_get_stats(self):
        """統計情報を取得できる"""
        reporter = OrchestratorMoltbookReporter()
        reporter._running = True
        
        stats = reporter.get_stats()
        
        assert "tasks_completed" in stats
        assert "tasks_failed" in stats
        assert "posts_made" in stats
        assert "uptime" in stats
        assert stats["running"] is True


class TestGlobalFunctions:
    """グローバル関数のテスト"""
    
    def setup_method(self):
        """各テスト前にグローバルレポーターをリセット"""
        global _reporter
        _reporter = None
    
    def teardown_method(self):
        """各テスト後にグローバルレポーターをリセット"""
        global _reporter
        _reporter = None
    
    def test_get_reporter_creates_instance(self):
        """get_reporter()が新しいインスタンスを作成する"""
        reporter = get_reporter()
        
        assert isinstance(reporter, OrchestratorMoltbookReporter)
        assert reporter.submolt == "ai_agents"
    
    def test_get_reporter_returns_same_instance(self):
        """get_reporter()は同じインスタンスを返す（シングルトン）"""
        reporter1 = get_reporter()
        reporter2 = get_reporter()
        
        assert reporter1 is reporter2
    
    @pytest.mark.asyncio
    async def test_report_task_complete(self):
        """report_task_complete()が動作する"""
        with patch('orchestrator_moltbook.get_reporter') as mock_get:
            mock_reporter = MagicMock()
            mock_reporter.post_task_update = AsyncMock(return_value="post_123")
            mock_get.return_value = mock_reporter
            
            result = await report_task_complete("T1", "Task done")
            
            assert result == "post_123"
            mock_reporter.post_task_update.assert_called_once_with("T1", "Task done", "completed")
    
    @pytest.mark.asyncio
    async def test_report_task_start(self):
        """report_task_start()が動作する"""
        with patch('orchestrator_moltbook.get_reporter') as mock_get:
            mock_reporter = MagicMock()
            mock_reporter.post_task_update = AsyncMock(return_value="post_456")
            mock_get.return_value = mock_reporter
            
            result = await report_task_start("T2", "Starting task")
            
            assert result == "post_456"
            mock_reporter.post_task_update.assert_called_once_with("T2", "Starting task", "in_progress")
    
    @pytest.mark.asyncio
    async def test_report_to_moltbook(self):
        """report_to_moltbook()が動作する"""
        with patch('orchestrator_moltbook.get_reporter') as mock_get:
            mock_reporter = MagicMock()
            mock_reporter.post_peer_report = AsyncMock(return_value="post_789")
            mock_get.return_value = mock_reporter
            
            result = await report_to_moltbook("Working", "Next action")
            
            assert result == "post_789"
            mock_reporter.post_peer_report.assert_called_once_with("Working", "Next action")


class TestIntegrationScenarios:
    """統合シナリオのテスト"""
    
    @pytest.mark.asyncio
    async def test_full_reporting_workflow(self):
        """完全な報告ワークフロー"""
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "post_id"
        mock_client.create_post = AsyncMock(return_value=mock_post)
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        # タスク開始を報告
        await reporter.post_task_update("S1", "Task started", "in_progress")
        
        # ステータスを投稿
        await reporter.post_status()
        
        # Peer報告
        await reporter.post_peer_report("Active", "Working on S1")
        
        # タスク完了を報告
        await reporter.post_task_update("S1", "Task completed", "completed")
        
        # 検証
        assert mock_client.create_post.call_count == 4
        assert reporter.stats["tasks_completed"] == 1
        assert reporter.stats["posts_made"] == 2  # status + peer report
    
    @pytest.mark.asyncio
    async def test_stats_accumulation(self):
        """統計情報が正しく累積される"""
        mock_client = MagicMock()
        mock_post = MagicMock()
        mock_post.id = "post"
        mock_client.create_post = AsyncMock(return_value=mock_post)
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        # 複数タスクを完了
        await reporter.post_task_update("T1", "Done", "completed")
        await reporter.post_task_update("T2", "Done", "completed")
        await reporter.post_task_update("T3", "Failed", "completed")
        
        assert reporter.stats["tasks_completed"] == 3
    
    @pytest.mark.asyncio
    async def test_error_recovery(self):
        """エラー後も動作を継続できる"""
        mock_client = MagicMock()
        mock_client.create_post = AsyncMock(side_effect=[
            Exception("First error"),
            MagicMock(id="success_post"),
        ])
        
        reporter = OrchestratorMoltbookReporter(client=mock_client)
        
        # 最初は失敗
        result1 = await reporter.post_status()
        assert result1 is None
        assert reporter.stats["posts_made"] == 0
        
        # 次は成功
        result2 = await reporter.post_task_update("T1", "Task", "completed")
        assert result2 == "success_post"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
