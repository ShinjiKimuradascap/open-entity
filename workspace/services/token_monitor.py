#!/usr/bin/env python3
"""
Token System Monitor
Token Economy Systemの監視・ヘルスチェック・アラート機能

機能:
- ウォレット残高監視
- タスク状態監視
- 異常検知とアラート
- メトリクス収集
- ヘルスチェックエンドポイント
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import threading
from collections import deque

from services.token_system import TokenEconomy, TaskStatus, TransactionType

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """アラートレベル"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """アラート情報"""
    level: AlertLevel
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    entity_id: Optional[str] = None
    metric_name: Optional[str] = None
    metric_value: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "entity_id": self.entity_id,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value
        }


@dataclass
class Metric:
    """メトリクスデータポイント"""
    name: str
    value: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    labels: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels
        }


class TokenMonitor:
    """
    Token System監視クラス
    
    ウォレット残高、タスク状態、トランザクションを監視し、
    異常を検知した場合にアラートを発行する。
    """
    
    # デフォルトの監視設定
    DEFAULT_CHECK_INTERVAL = 60  # 秒
    DEFAULT_BALANCE_THRESHOLD = 100.0  # 残低保有アラート閾値
    DEFAULT_TASK_TIMEOUT = 3600  # タスクタイムアウト（秒）
    DEFAULT_ALERT_HISTORY_SIZE = 1000
    DEFAULT_METRIC_HISTORY_SIZE = 10000
    
    def __init__(
        self,
        token_economy: Optional[TokenEconomy] = None,
        check_interval: int = DEFAULT_CHECK_INTERVAL,
        balance_threshold: float = DEFAULT_BALANCE_THRESHOLD,
        task_timeout: int = DEFAULT_TASK_TIMEOUT,
        alert_callbacks: Optional[List[Callable[[Alert], None]]] = None
    ):
        """
        TokenMonitorを初期化
        
        Args:
            token_economy: TokenEconomyインスタンス
            check_interval: 監視チェック間隔（秒）
            balance_threshold: 残低保有アラート閾値
            task_timeout: タスクタイムアウト（秒）
            alert_callbacks: アラート発行時のコールバック関数リスト
        """
        self.token_economy = token_economy
        self.check_interval = check_interval
        self.balance_threshold = balance_threshold
        self.task_timeout = task_timeout
        self.alert_callbacks = alert_callbacks or []
        
        # アラート履歴
        self._alerts: deque = deque(maxlen=self.DEFAULT_ALERT_HISTORY_SIZE)
        
        # メトリクス履歴
        self._metrics: deque = deque(maxlen=self.DEFAULT_METRIC_HISTORY_SIZE)
        
        # 監視状態
        self._running = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # カスタム監視ルール
        self._custom_rules: List[Callable[[], Optional[Alert]]] = []
        
        logger.info("TokenMonitor initialized")
    
    def add_alert_callback(self, callback: Callable[[Alert], None]) -> None:
        """アラートコールバックを追加"""
        self.alert_callbacks.append(callback)
        logger.debug(f"Added alert callback: {callback.__name__}")
    
    def add_custom_rule(self, rule: Callable[[], Optional[Alert]]) -> None:
        """カスタム監視ルールを追加"""
        self._custom_rules.append(rule)
        logger.debug(f"Added custom monitoring rule: {rule.__name__}")
    
    def _emit_alert(self, alert: Alert) -> None:
        """アラートを発行"""
        self._alerts.append(alert)
        
        # ログ出力
        log_method = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.ERROR: logger.error,
            AlertLevel.CRITICAL: logger.critical
        }.get(alert.level, logger.info)
        
        log_method(f"[{alert.level.value.upper()}] {alert.message}")
        
        # コールバック実行
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")
    
    def _record_metric(self, metric: Metric) -> None:
        """メトリクスを記録"""
        self._metrics.append(metric)
    
    def _check_wallet_balances(self) -> List[Alert]:
        """ウォレット残高をチェック"""
        alerts = []
        
        if not self.token_economy:
            return alerts
        
        try:
            for entity_id, wallet in self.token_economy.wallets.items():
                balance = wallet.get_balance()
                
                # メトリクス記録
                self._record_metric(Metric(
                    name="wallet_balance",
                    value=balance,
                    labels={"entity_id": entity_id}
                ))
                
                # 残高チェック
                if balance < self.balance_threshold:
                    alert = Alert(
                        level=AlertLevel.WARNING if balance > 0 else AlertLevel.ERROR,
                        message=f"Low balance for {entity_id}: {balance} AIC",
                        entity_id=entity_id,
                        metric_name="wallet_balance",
                        metric_value=balance
                    )
                    alerts.append(alert)
                    self._emit_alert(alert)
        except Exception as e:
            logger.error(f"Failed to check wallet balances: {e}")
        
        return alerts
    
    def _check_task_status(self) -> List[Alert]:
        """タスク状態をチェック"""
        alerts = []
        
        if not self.token_economy:
            return alerts
        
        try:
            now = datetime.now(timezone.utc)
            
            for task_id, task in self.token_economy.tasks.items():
                # メトリクス記録
                self._record_metric(Metric(
                    name="task_status",
                    value=1.0,
                    labels={
                        "task_id": task_id,
                        "status": task.status.value,
                        "provider": task.provider_id,
                        "client": task.client_id
                    }
                ))
                
                # タイムアウトチェック
                if task.status == TaskStatus.IN_PROGRESS:
                    timeout_threshold = now - timedelta(seconds=self.task_timeout)
                    if task.updated_at < timeout_threshold:
                        alert = Alert(
                            level=AlertLevel.WARNING,
                            message=f"Task {task_id} has been in progress for too long",
                            entity_id=task.provider_id,
                            metric_name="task_duration",
                            metric_value=(now - task.updated_at).total_seconds()
                        )
                        alerts.append(alert)
                        self._emit_alert(alert)
                
                # 失敗タスクチェック
                if task.status == TaskStatus.FAILED:
                    alert = Alert(
                        level=AlertLevel.ERROR,
                        message=f"Task {task_id} has failed",
                        entity_id=task.provider_id,
                        metric_name="task_failed",
                        metric_value=1.0
                    )
                    alerts.append(alert)
                    self._emit_alert(alert)
        except Exception as e:
            logger.error(f"Failed to check task status: {e}")
        
        return alerts
    
    def _check_custom_rules(self) -> List[Alert]:
        """カスタム監視ルールをチェック"""
        alerts = []
        
        for rule in self._custom_rules:
            try:
                alert = rule()
                if alert:
                    alerts.append(alert)
                    self._emit_alert(alert)
            except Exception as e:
                logger.error(f"Custom rule {rule.__name__} failed: {e}")
        
        return alerts
    
    def _monitoring_loop(self) -> None:
        """監視ループ"""
        logger.info("Starting monitoring loop")
        
        while not self._stop_event.is_set():
            try:
                # 各種チェック実行
                self._check_wallet_balances()
                self._check_task_status()
                self._check_custom_rules()
                
                # システムメトリクス
                self._record_metric(Metric(
                    name="monitor_check",
                    value=1.0,
                    labels={"status": "success"}
                ))
                
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                self._record_metric(Metric(
                    name="monitor_check",
                    value=0.0,
                    labels={"status": "error"}
                ))
            
            # インターバル待機
            self._stop_event.wait(self.check_interval)
        
        logger.info("Monitoring loop stopped")
    
    def start(self) -> None:
        """監視を開始"""
        if self._running:
            logger.warning("Monitor is already running")
            return
        
        self._running = True
        self._stop_event.clear()
        self._monitor_thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._monitor_thread.start()
        
        logger.info(f"TokenMonitor started (interval: {self.check_interval}s)")
    
    def stop(self) -> None:
        """監視を停止"""
        if not self._running:
            return
        
        self._stop_event.set()
        self._running = False
        
        if self._monitor_thread:
            self._monitor_thread.join(timeout=5.0)
        
        logger.info("TokenMonitor stopped")
    
    def is_running(self) -> bool:
        """監視が実行中かチェック"""
        return self._running
    
    def get_alerts(
        self,
        level: Optional[AlertLevel] = None,
        since: Optional[datetime] = None,
        entity_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Alert]:
        """
        アラート履歴を取得
        
        Args:
            level: フィルタするアラートレベル
            since: この時刻以降のアラート
            entity_id: 特定のエンティティIDでフィルタ
            limit: 最大取得数
        
        Returns:
            アラートリスト
        """
        alerts = list(self._alerts)
        
        if level:
            alerts = [a for a in alerts if a.level == level]
        
        if since:
            alerts = [a for a in alerts if a.timestamp >= since]
        
        if entity_id:
            alerts = [a for a in alerts if a.entity_id == entity_id]
        
        return alerts[-limit:]
    
    def get_metrics(
        self,
        name: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 1000
    ) -> List[Metric]:
        """
        メトリクス履歴を取得
        
        Args:
            name: メトリクス名でフィルタ
            since: この時刻以降のメトリクス
            limit: 最大取得数
        
        Returns:
            メトリクスリスト
        """
        metrics = list(self._metrics)
        
        if name:
            metrics = [m for m in metrics if m.name == name]
        
        if since:
            metrics = [m for m in metrics if m.timestamp >= since]
        
        return metrics[-limit:]
    
    def get_health_status(self) -> Dict[str, Any]:
        """
        ヘルスステータスを取得
        
        Returns:
            ヘルスステータス情報
        """
        now = datetime.now(timezone.utc)
        
        # 最近のアラートを集計
        recent_alerts = self.get_alerts(since=now - timedelta(hours=1))
        alert_counts = {
            "info": len([a for a in recent_alerts if a.level == AlertLevel.INFO]),
            "warning": len([a for a in recent_alerts if a.level == AlertLevel.WARNING]),
            "error": len([a for a in recent_alerts if a.level == AlertLevel.ERROR]),
            "critical": len([a for a in recent_alerts if a.level == AlertLevel.CRITICAL])
        }
        
        # 全体的なステータス
        if alert_counts["critical"] > 0:
            overall_status = "critical"
        elif alert_counts["error"] > 0:
            overall_status = "error"
        elif alert_counts["warning"] > 0:
            overall_status = "warning"
        else:
            overall_status = "healthy"
        
        return {
            "status": overall_status,
            "monitor_running": self._running,
            "check_interval": self.check_interval,
            "balance_threshold": self.balance_threshold,
            "task_timeout": self.task_timeout,
            "alert_counts_last_hour": alert_counts,
            "total_alerts": len(self._alerts),
            "total_metrics": len(self._metrics),
            "timestamp": now.isoformat()
        }
    
    def export_alerts(self, filepath: str, since: Optional[datetime] = None) -> bool:
        """アラートをファイルにエクスポート"""
        try:
            alerts = self.get_alerts(since=since)
            data = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "alert_count": len(alerts),
                "alerts": [a.to_dict() for a in alerts]
            }
            
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(alerts)} alerts to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export alerts: {e}")
            return False
    
    def export_metrics(self, filepath: str, since: Optional[datetime] = None) -> bool:
        """メトリクスをファイルにエクスポート"""
        try:
            metrics = self.get_metrics(since=since)
            data = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "metric_count": len(metrics),
                "metrics": [m.to_dict() for m in metrics]
            }
            
            Path(filepath).parent.mkdir(parents=True, exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(metrics)} metrics to {filepath}")
            return True
        except Exception as e:
            logger.error(f"Failed to export metrics: {e}")
            return False


# グローバルモニターインスタンス
_monitor_instance: Optional[TokenMonitor] = None


def get_monitor(
    token_economy: Optional[TokenEconomy] = None,
    **kwargs
) -> TokenMonitor:
    """
    グローバルモニターインスタンスを取得
    
    Args:
        token_economy: TokenEconomyインスタンス
        **kwargs: TokenMonitorの設定
        
    Returns:
        TokenMonitorインスタンス
    """
    global _monitor_instance
    if _monitor_instance is None:
        _monitor_instance = TokenMonitor(token_economy, **kwargs)
    return _monitor_instance


def reset_monitor() -> None:
    """グローバルモニターインスタンスをリセット（テスト用）"""
    global _monitor_instance
    if _monitor_instance and _monitor_instance.is_running():
        _monitor_instance.stop()
    _monitor_instance = None


# 簡単なテスト
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=== TokenMonitor Test ===")
    
    # モニターを作成
    monitor = TokenMonitor(
        check_interval=5,
        balance_threshold=100.0
    )
    
    # アラートコールバック
    def on_alert(alert: Alert):
        print(f"[CALLBACK] {alert.level.value}: {alert.message}")
    
    monitor.add_alert_callback(on_alert)
    
    # カスタムルール
    def custom_check() -> Optional[Alert]:
        if len(monitor._alerts) > 5:
            return Alert(
                level=AlertLevel.WARNING,
                message="Too many alerts accumulated"
            )
        return None
    
    monitor.add_custom_rule(custom_check)
    
    # テストアラート
    monitor._emit_alert(Alert(
        level=AlertLevel.INFO,
        message="Test alert",
        entity_id="test_entity"
    ))
    
    # ヘルスステータス
    health = monitor.get_health_status()
    print(f"\nHealth Status: {health}")
    
    print("\n=== TokenMonitor tests passed ===")
