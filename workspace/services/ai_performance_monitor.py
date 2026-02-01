"""
AI Performance Monitor
AIが自律的にシステムパフォーマンスを監視するモジュール

機能:
- CPU/Memory/Network使用状況の監視
- APIレスポンスタイムの監視
- エラー率の監視
- 閾値超過時のアラート発行
- 非同期で連続的に動作
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any, Union
from collections import deque
from enum import Enum
import functools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """アラートレベル"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class SystemMetrics:
    """システムメトリクス"""
    timestamp: str
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    network_io_sent_mb: float
    network_io_recv_mb: float
    disk_usage_percent: float
    disk_free_gb: float
    load_average_1m: float
    process_count: int


@dataclass
class APIMetrics:
    """APIメトリクス"""
    endpoint: str
    timestamp: str
    response_time_ms: float
    status_code: int
    success: bool
    error_type: Optional[str] = None


@dataclass
class Alert:
    """アラート"""
    level: AlertLevel
    component: str
    message: str
    timestamp: str
    value: float
    threshold: float
    details: Optional[Dict[str, Any]] = None


@dataclass
class PerformanceSnapshot:
    """パフォーマンススナップショット"""
    timestamp: str
    system: SystemMetrics
    api_summary: Dict[str, Any]
    error_rate: float
    alerts: List[Alert] = field(default_factory=list)


class PerformanceThresholds:
    """パフォーマンス閾値設定"""
    
    def __init__(
        self,
        cpu_warning: float = 70.0,
        cpu_critical: float = 90.0,
        memory_warning: float = 80.0,
        memory_critical: float = 95.0,
        disk_warning: float = 80.0,
        disk_critical: float = 95.0,
        api_response_warning_ms: float = 500.0,
        api_response_critical_ms: float = 2000.0,
        error_rate_warning: float = 5.0,
        error_rate_critical: float = 15.0,
        load_average_warning: float = 4.0,
        load_average_critical: float = 8.0
    ):
        self.cpu_warning = cpu_warning
        self.cpu_critical = cpu_critical
        self.memory_warning = memory_warning
        self.memory_critical = memory_critical
        self.disk_warning = disk_warning
        self.disk_critical = disk_critical
        self.api_response_warning_ms = api_response_warning_ms
        self.api_response_critical_ms = api_response_critical_ms
        self.error_rate_warning = error_rate_warning
        self.error_rate_critical = error_rate_critical
        self.load_average_warning = load_average_warning
        self.load_average_critical = load_average_critical


class AIPerformanceMonitor:
    """
    AIパフォーマンスモニター
    
    システムリソースとAPIパフォーマンスを継続的に監視し、
    異常検知時にアラートを発行します。
    """
    
    def __init__(
        self,
        thresholds: Optional[PerformanceThresholds] = None,
        history_size: int = 1000,
        monitoring_interval: float = 5.0
    ):
        self.thresholds = thresholds or PerformanceThresholds()
        self.history_size = history_size
        self.monitoring_interval = monitoring_interval
        
        # メトリクス履歴
        self.system_history: deque = deque(maxlen=history_size)
        self.api_history: deque = deque(maxlen=history_size)
        self.alerts_history: deque = deque(maxlen=history_size)
        
        # アラートコールバック
        self.alert_callbacks: List[Callable[[Alert], None]] = []
        
        # 監視制御
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False
        
        # API追跡用
        self._api_calls: deque = deque(maxlen=10000)
        
        # 前回のネットワークIO（差分計算用）
        self._last_net_io: Optional[tuple] = None
        
        logger.info("AI Performance Monitor initialized")
    
    def register_alert_callback(self, callback: Callable[[Alert], None]) -> None:
        """アラートコールバックを登録"""
        self.alert_callbacks.append(callback)
        logger.info(f"Alert callback registered: {callback.__name__}")
    
    async def start(self) -> None:
        """監視を開始"""
        if self._running:
            logger.warning("Monitor is already running")
            return
        
        self._running = True
        self._monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("AI Performance Monitor started")
    
    async def stop(self) -> None:
        """監視を停止"""
        if not self._running:
            return
        
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()
            try:
                await self._monitoring_task
            except asyncio.CancelledError:
                pass
        logger.info("AI Performance Monitor stopped")
    
    async def _monitoring_loop(self) -> None:
        """監視メインループ"""
        while self._running:
            try:
                # システムメトリクス収集
                metrics = await self._collect_system_metrics()
                self.system_history.append(metrics)
                
                # アラートチェック
                alerts = self._check_thresholds(metrics)
                for alert in alerts:
                    await self._emit_alert(alert)
                
                await asyncio.sleep(self.monitoring_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(self.monitoring_interval)
    
    async def _collect_system_metrics(self) -> SystemMetrics:
        """システムメトリクスを収集"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # CPU使用率
        cpu_percent = await self._get_cpu_percent()
        
        # メモリ情報
        memory_percent, memory_used_mb, memory_total_mb = await self._get_memory_info()
        
        # ネットワークIO
        net_sent_mb, net_recv_mb = await self._get_network_io()
        
        # ディスク使用状況
        disk_usage_percent, disk_free_gb = await self._get_disk_info()
        
        # ロードアベレージ
        load_average = await self._get_load_average()
        
        # プロセス数
        process_count = await self._get_process_count()
        
        return SystemMetrics(
            timestamp=timestamp,
            cpu_percent=cpu_percent,
            memory_percent=memory_percent,
            memory_used_mb=memory_used_mb,
            memory_total_mb=memory_total_mb,
            network_io_sent_mb=net_sent_mb,
            network_io_recv_mb=net_recv_mb,
            disk_usage_percent=disk_usage_percent,
            disk_free_gb=disk_free_gb,
            load_average_1m=load_average,
            process_count=process_count
        )
    
    async def _get_cpu_percent(self) -> float:
        """CPU使用率を取得"""
        try:
            # /proc/stat から取得
            with open("/proc/stat", "r") as f:
                line = f.readline()
            
            fields = line.split()[1:]
            user, nice, system, idle = map(int, fields[:4])
            total = user + nice + system + idle
            used = user + nice + system
            
            if not hasattr(self, "_last_cpu"):
                self._last_cpu = (used, total)
                await asyncio.sleep(0.1)
                return await self._get_cpu_percent()
            
            last_used, last_total = self._last_cpu
            cpu_percent = ((used - last_used) / (total - last_total)) * 100
            self._last_cpu = (used, total)
            
            return min(100.0, max(0.0, cpu_percent))
        except Exception as e:
            logger.debug(f"Failed to get CPU percent: {e}")
            return 0.0
    
    async def _get_memory_info(self) -> tuple:
        """メモリ情報を取得"""
        try:
            with open("/proc/meminfo", "r") as f:
                content = f.read()
            
            lines = content.split("\n")
            mem_total = 0
            mem_available = 0
            
            for line in lines:
                if line.startswith("MemTotal:"):
                    mem_total = int(line.split()[1]) * 1024  # bytes
                elif line.startswith("MemAvailable:"):
                    mem_available = int(line.split()[1]) * 1024
            
            mem_total_mb = mem_total / (1024 * 1024)
            mem_available_mb = mem_available / (1024 * 1024)
            mem_used_mb = mem_total_mb - mem_available_mb
            
            if mem_total > 0:
                mem_percent = (mem_used_mb / mem_total_mb) * 100
            else:
                mem_percent = 0.0
            
            return mem_percent, mem_used_mb, mem_total_mb
        except Exception as e:
            logger.debug(f"Failed to get memory info: {e}")
            return 0.0, 0.0, 0.0
    
    async def _get_network_io(self) -> tuple:
        """ネットワークIOを取得"""
        try:
            # /proc/net/dev から取得
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()[2:]  # ヘッダーをスキップ
            
            total_sent = 0
            total_recv = 0
            
            for line in lines:
                parts = line.split()
                if len(parts) >= 9:
                    recv_bytes = int(parts[1])
                    sent_bytes = int(parts[9])
                    total_recv += recv_bytes
                    total_sent += sent_bytes
            
            sent_mb = total_sent / (1024 * 1024)
            recv_mb = total_recv / (1024 * 1024)
            
            # 差分を計算
            if self._last_net_io:
                last_sent, last_recv = self._last_net_io
                delta_sent = max(0, sent_mb - last_sent)
                delta_recv = max(0, recv_mb - last_recv)
            else:
                delta_sent = 0.0
                delta_recv = 0.0
            
            self._last_net_io = (sent_mb, recv_mb)
            return delta_sent, delta_recv
        except Exception as e:
            logger.debug(f"Failed to get network IO: {e}")
            return 0.0, 0.0
    
    async def _get_disk_info(self) -> tuple:
        """ディスク情報を取得"""
        try:
            stat = os.statvfs("/home/moco/workspace")
            total = stat.f_blocks * stat.f_frsize
            free = stat.f_bavail * stat.f_frsize
            
            free_gb = free / (1024**3)
            
            if total > 0:
                usage_percent = ((total - free) / total) * 100
            else:
                usage_percent = 0.0
            
            return usage_percent, free_gb
        except Exception as e:
            logger.debug(f"Failed to get disk info: {e}")
            return 0.0, 0.0
    
    async def _get_load_average(self) -> float:
        """ロードアベレージを取得"""
        try:
            with open("/proc/loadavg", "r") as f:
                line = f.readline()
            return float(line.split()[0])
        except Exception as e:
            logger.debug(f"Failed to get load average: {e}")
            return 0.0
    
    async def _get_process_count(self) -> int:
        """プロセス数を取得"""
        try:
            count = 0
            for entry in os.listdir("/proc"):
                if entry.isdigit():
                    count += 1
            return count
        except Exception as e:
            logger.debug(f"Failed to get process count: {e}")
            return 0
    
    def _check_thresholds(self, metrics: SystemMetrics) -> List[Alert]:
        """閾値チェックとアラート生成"""
        alerts = []
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # CPUチェック
        if metrics.cpu_percent >= self.thresholds.cpu_critical:
            alerts.append(Alert(
                level=AlertLevel.CRITICAL,
                component="cpu",
                message=f"CPU usage critical: {metrics.cpu_percent:.1f}%",
                timestamp=timestamp,
                value=metrics.cpu_percent,
                threshold=self.thresholds.cpu_critical
            ))
        elif metrics.cpu_percent >= self.thresholds.cpu_warning:
            alerts.append(Alert(
                level=AlertLevel.WARNING,
                component="cpu",
                message=f"CPU usage high: {metrics.cpu_percent:.1f}%",
                timestamp=timestamp,
                value=metrics.cpu_percent,
                threshold=self.thresholds.cpu_warning
            ))
        
        # メモリチェック
        if metrics.memory_percent >= self.thresholds.memory_critical:
            alerts.append(Alert(
                level=AlertLevel.CRITICAL,
                component="memory",
                message=f"Memory usage critical: {metrics.memory_percent:.1f}%",
                timestamp=timestamp,
                value=metrics.memory_percent,
                threshold=self.thresholds.memory_critical
            ))
        elif metrics.memory_percent >= self.thresholds.memory_warning:
            alerts.append(Alert(
                level=AlertLevel.WARNING,
                component="memory",
                message=f"Memory usage high: {metrics.memory_percent:.1f}%",
                timestamp=timestamp,
                value=metrics.memory_percent,
                threshold=self.thresholds.memory_warning
            ))
        
        # ディスクチェック
        if metrics.disk_usage_percent >= self.thresholds.disk_critical:
            alerts.append(Alert(
                level=AlertLevel.CRITICAL,
                component="disk",
                message=f"Disk usage critical: {metrics.disk_usage_percent:.1f}%",
                timestamp=timestamp,
                value=metrics.disk_usage_percent,
                threshold=self.thresholds.disk_critical
            ))
        elif metrics.disk_usage_percent >= self.thresholds.disk_warning:
            alerts.append(Alert(
                level=AlertLevel.WARNING,
                component="disk",
                message=f"Disk usage high: {metrics.disk_usage_percent:.1f}%",
                timestamp=timestamp,
                value=metrics.disk_usage_percent,
                threshold=self.thresholds.disk_warning
            ))
        
        # ロードアベレージチェック
        if metrics.load_average_1m >= self.thresholds.load_average_critical:
            alerts.append(Alert(
                level=AlertLevel.CRITICAL,
                component="load",
                message=f"System load critical: {metrics.load_average_1m:.2f}",
                timestamp=timestamp,
                value=metrics.load_average_1m,
                threshold=self.thresholds.load_average_critical
            ))
        elif metrics.load_average_1m >= self.thresholds.load_average_warning:
            alerts.append(Alert(
                level=AlertLevel.WARNING,
                component="load",
                message=f"System load high: {metrics.load_average_1m:.2f}",
                timestamp=timestamp,
                value=metrics.load_average_1m,
                threshold=self.thresholds.load_average_warning
            ))
        
        return alerts
    
    async def _emit_alert(self, alert: Alert) -> None:
        """アラートを発行"""
        self.alerts_history.append(alert)
        
        # ログ出力
        log_method = {
            AlertLevel.INFO: logger.info,
            AlertLevel.WARNING: logger.warning,
            AlertLevel.CRITICAL: logger.error
        }.get(alert.level, logger.info)
        
        log_method(f"[PERFORMANCE ALERT] {alert.level.value.upper()}: {alert.message}")
        
        # コールバック実行
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(alert)
                else:
                    callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
    
    def track_api_call(
        self,
        endpoint: str,
        response_time_ms: float,
        status_code: int,
        success: bool,
        error_type: Optional[str] = None
    ) -> None:
        """API呼び出しを追跡"""
        metrics = APIMetrics(
            endpoint=endpoint,
            timestamp=datetime.now(timezone.utc).isoformat(),
            response_time_ms=response_time_ms,
            status_code=status_code,
            success=success,
            error_type=error_type
        )
        self._api_calls.append(metrics)
        self.api_history.append(metrics)
        
        # APIレスポンスタイムのアラートチェック
        asyncio.create_task(self._check_api_alert(metrics))
    
    async def _check_api_alert(self, metrics: APIMetrics) -> None:
        """APIメトリクスのアラートチェック"""
        timestamp = datetime.now(timezone.utc).isoformat()
        
        if metrics.response_time_ms >= self.thresholds.api_response_critical_ms:
            alert = Alert(
                level=AlertLevel.CRITICAL,
                component="api",
                message=f"API response time critical: {metrics.response_time_ms:.0f}ms ({metrics.endpoint})",
                timestamp=timestamp,
                value=metrics.response_time_ms,
                threshold=self.thresholds.api_response_critical_ms,
                details={"endpoint": metrics.endpoint, "status_code": metrics.status_code}
            )
            await self._emit_alert(alert)
        elif metrics.response_time_ms >= self.thresholds.api_response_warning_ms:
            alert = Alert(
                level=AlertLevel.WARNING,
                component="api",
                message=f"API response time high: {metrics.response_time_ms:.0f}ms ({metrics.endpoint})",
                timestamp=timestamp,
                value=metrics.response_time_ms,
                threshold=self.thresholds.api_response_warning_ms,
                details={"endpoint": metrics.endpoint, "status_code": metrics.status_code}
            )
            await self._emit_alert(alert)
    
    def get_api_summary(self, window_seconds: float = 300.0) -> Dict[str, Any]:
        """APIサマリーを取得"""
        now = time.time()
        window_start = now - window_seconds
        
        recent_calls = [
            call for call in self._api_calls
            if datetime.fromisoformat(call.timestamp).timestamp() > window_start
        ]
        
        if not recent_calls:
            return {
                "total_calls": 0,
                "avg_response_time_ms": 0.0,
                "error_rate": 0.0,
                "endpoints": {}
            }
        
        total_calls = len(recent_calls)
        error_calls = [c for c in recent_calls if not c.success]
        error_rate = (len(error_calls) / total_calls) * 100
        avg_response_time = sum(c.response_time_ms for c in recent_calls) / total_calls
        
        # エンドポイント別集計
        endpoints: Dict[str, Dict[str, Any]] = {}
        for call in recent_calls:
            if call.endpoint not in endpoints:
                endpoints[call.endpoint] = {"calls": 0, "errors": 0, "total_time": 0.0}
            endpoints[call.endpoint]["calls"] += 1
            if not call.success:
                endpoints[call.endpoint]["errors"] += 1
            endpoints[call.endpoint]["total_time"] += call.response_time_ms
        
        for endpoint, data in endpoints.items():
            data["avg_time"] = data["total_time"] / data["calls"]
            data["error_rate"] = (data["errors"] / data["calls"]) * 100
        
        # エラー率アラートチェック
        if error_rate >= self.thresholds.error_rate_critical:
            asyncio.create_task(self._emit_alert(Alert(
                level=AlertLevel.CRITICAL,
                component="api",
                message=f"API error rate critical: {error_rate:.1f}%",
                timestamp=datetime.now(timezone.utc).isoformat(),
                value=error_rate,
                threshold=self.thresholds.error_rate_critical
            )))
        elif error_rate >= self.thresholds.error_rate_warning:
            asyncio.create_task(self._emit_alert(Alert(
                level=AlertLevel.WARNING,
                component="api",
                message=f"API error rate high: {error_rate:.1f}%",
                timestamp=datetime.now(timezone.utc).isoformat(),
                value=error_rate,
                threshold=self.thresholds.error_rate_warning
            )))
        
        return {
            "total_calls": total_calls,
            "avg_response_time_ms": round(avg_response_time, 2),
            "error_rate": round(error_rate, 2),
            "endpoints": endpoints
        }
    
    def get_current_metrics(self) -> Optional[SystemMetrics]:
        """現在のシステムメトリクスを取得"""
        if self.system_history:
            return self.system_history[-1]
        return None
    
    def get_snapshot(self) -> PerformanceSnapshot:
        """パフォーマンススナップショットを取得"""
        system = self.get_current_metrics()
        if not system:
            system = SystemMetrics(
                timestamp=datetime.now(timezone.utc).isoformat(),
                cpu_percent=0.0,
                memory_percent=0.0,
                memory_used_mb=0.0,
                memory_total_mb=0.0,
                network_io_sent_mb=0.0,
                network_io_recv_mb=0.0,
                disk_usage_percent=0.0,
                disk_free_gb=0.0,
                load_average_1m=0.0,
                process_count=0
            )
        
        api_summary = self.get_api_summary()
        
        # 最新のアラート（直近1分）
        recent_alerts = [
            alert for alert in self.alerts_history
            if (datetime.now(timezone.utc) - datetime.fromisoformat(alert.timestamp)).total_seconds() < 60
        ]
        
        return PerformanceSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            system=system,
            api_summary=api_summary,
            error_rate=api_summary["error_rate"],
            alerts=recent_alerts
        )
    
    def get_historical_data(
        self,
        metric_type: str = "system",
        duration_seconds: float = 3600.0
    ) -> List[Dict[str, Any]]:
        """履歴データを取得"""
        now = time.time()
        cutoff = now - duration_seconds
        
        if metric_type == "system":
            data = [
                asdict(m) for m in self.system_history
                if datetime.fromisoformat(m.timestamp).timestamp() > cutoff
            ]
        elif metric_type == "api":
            data = [
                asdict(m) for m in self.api_history
                if datetime.fromisoformat(m.timestamp).timestamp() > cutoff
            ]
        else:
            data = []
        
        return data


# デコレーター: API呼び出しを自動追跡
def track_performance(
    monitor: "AIPerformanceMonitor",
    endpoint: Optional[str] = None
):
    """API関数のパフォーマンスを自動追跡するデコレーター"""
    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            func_name = endpoint or func.__name__
            
            try:
                result = await func(*args, **kwargs)
                response_time = (time.time() - start_time) * 1000
                monitor.track_api_call(
                    endpoint=func_name,
                    response_time_ms=response_time,
                    status_code=200,
                    success=True
                )
                return result
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                monitor.track_api_call(
                    endpoint=func_name,
                    response_time_ms=response_time,
                    status_code=500,
                    success=False,
                    error_type=type(e).__name__
                )
                raise
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            func_name = endpoint or func.__name__
            
            try:
                result = func(*args, **kwargs)
                response_time = (time.time() - start_time) * 1000
                monitor.track_api_call(
                    endpoint=func_name,
                    response_time_ms=response_time,
                    status_code=200,
                    success=True
                )
                return result
            except Exception as e:
                response_time = (time.time() - start_time) * 1000
                monitor.track_api_call(
                    endpoint=func_name,
                    response_time_ms=response_time,
                    status_code=500,
                    success=False,
                    error_type=type(e).__name__
                )
                raise
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


# グローバルインスタンス
_monitor: Optional[AIPerformanceMonitor] = None


def get_performance_monitor() -> AIPerformanceMonitor:
    """グローバルモニターインスタンスを取得"""
    global _monitor
    if _monitor is None:
        _monitor = AIPerformanceMonitor()
    return _monitor


# アラートハンドラ例
async def default_alert_handler(alert: Alert) -> None:
    """デフォルトアラートハンドラ"""
    if alert.level == AlertLevel.CRITICAL:
        # クリティカルアラートは特別な処理
        logger.error(f"🚨 CRITICAL ALERT: {alert.message}")
        # ここに通知処理（メール、Slack等）を追加可能
    elif alert.level == AlertLevel.WARNING:
        logger.warning(f"⚠️ WARNING: {alert.message}")


async def main():
    """デモ実行"""
    monitor = get_performance_monitor()
    
    # アラートハンドラを登録
    monitor.register_alert_callback(default_alert_handler)
    
    # 監視開始
    await monitor.start()
    
    try:
        # デモ用APIトラッキング
        for i in range(10):
            monitor.track_api_call(
                endpoint="/api/test",
                response_time_ms=100 + i * 50,
                status_code=200,
                success=True
            )
        
        # エラーシミュレーション
        monitor.track_api_call(
            endpoint="/api/error",
            response_time_ms=2500,
            status_code=500,
            success=False,
            error_type="InternalError"
        )
        
        # 監視データを表示
        await asyncio.sleep(12)  # 2回の監視サイクル
        
        snapshot = monitor.get_snapshot()
        print("\n=== Performance Snapshot ===")
        print(f"Timestamp: {snapshot.timestamp}")
        print(f"CPU: {snapshot.system.cpu_percent:.1f}%")
        print(f"Memory: {snapshot.system.memory_percent:.1f}%")
        print(f"API Error Rate: {snapshot.error_rate:.1f}%")
        print(f"Recent Alerts: {len(snapshot.alerts)}")
        
        api_summary = monitor.get_api_summary()
        print("\n=== API Summary ===")
        print(json.dumps(api_summary, indent=2))
        
    finally:
        await monitor.stop()


if __name__ == "__main__":
    asyncio.run(main())
