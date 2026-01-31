#!/usr/bin/env python3
"""
Health Monitor Service
システム健全性を監視し、異常時に自動復旧または報告を行う
"""

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """ヘルスステータス"""
    component: str
    status: str  # healthy, warning, error
    message: str
    timestamp: str
    details: Optional[Dict] = None


class HealthMonitor:
    """システム健全性モニタリング"""
    
    def __init__(self):
        self.checks: Dict[str, Callable] = {}
        self.status_history: List[HealthStatus] = []
        self.max_history = 100
        
    def register_check(self, name: str, check_func: Callable) -> None:
        """健全性チェックを登録"""
        self.checks[name] = check_func
        logger.info(f"Health check registered: {name}")
    
    async def run_check(self, name: str) -> HealthStatus:
        """単一チェックを実行"""
        if name not in self.checks:
            return HealthStatus(
                component=name,
                status="error",
                message=f"Check '{name}' not registered",
                timestamp=datetime.now(timezone.utc).isoformat()
            )
        
        try:
            result = await self.checks[name]()
            return result
        except Exception as e:
            return HealthStatus(
                component=name,
                status="error",
                message=str(e),
                timestamp=datetime.now(timezone.utc).isoformat()
            )
    
    async def run_all_checks(self) -> List[HealthStatus]:
        """全チェックを実行"""
        results = []
        for name in self.checks:
            result = await self.run_check(name)
            results.append(result)
            self.status_history.append(result)
        
        # 履歴を制限
        if len(self.status_history) > self.max_history:
            self.status_history = self.status_history[-self.max_history:]
        
        return results
    
    def get_summary(self) -> Dict:
        """サマリーを取得"""
        if not self.status_history:
            return {"status": "unknown", "checks": 0}
        
        latest = {}
        for status in reversed(self.status_history):
            if status.component not in latest:
                latest[status.component] = status
        
        statuses = [s.status for s in latest.values()]
        error_count = statuses.count("error")
        warning_count = statuses.count("warning")
        
        if error_count > 0:
            overall = "error"
        elif warning_count > 0:
            overall = "warning"
        else:
            overall = "healthy"
        
        return {
            "status": overall,
            "checks": len(latest),
            "error_count": error_count,
            "warning_count": warning_count,
            "components": {name: asdict(status) for name, status in latest.items()}
        }


# グローバルインスタンス
_monitor: Optional[HealthMonitor] = None


def get_monitor() -> HealthMonitor:
    """グローバルモニターを取得"""
    global _monitor
    if _monitor is None:
        _monitor = HealthMonitor()
    return _monitor


# 組み込みチェック関数
async def check_disk_space() -> HealthStatus:
    """ディスク容量チェック"""
    try:
        stat = os.statvfs("/home/moco/workspace")
        free_gb = (stat.f_bavail * stat.f_frsize) / (1024**3)
        total_gb = (stat.f_blocks * stat.f_frsize) / (1024**3)
        usage_percent = ((total_gb - free_gb) / total_gb) * 100
        
        if usage_percent > 90:
            status = "error"
        elif usage_percent > 80:
            status = "warning"
        else:
            status = "healthy"
        
        return HealthStatus(
            component="disk",
            status=status,
            message=f"Disk usage: {usage_percent:.1f}% ({free_gb:.1f}GB free)",
            timestamp=datetime.now(timezone.utc).isoformat(),
            details={"free_gb": free_gb, "total_gb": total_gb, "usage_percent": usage_percent}
        )
    except Exception as e:
        return HealthStatus(
            component="disk",
            status="error",
            message=str(e),
            timestamp=datetime.now(timezone.utc).isoformat()
        )


async def check_memory() -> HealthStatus:
    """メモリチェック"""
    try:
        with open("/proc/meminfo", "r") as f:
            lines = f.readlines()
        
        mem_total = 0
        mem_available = 0
        
        for line in lines:
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) / 1024 / 1024  # GB
            elif line.startswith("MemAvailable:"):
                mem_available = int(line.split()[1]) / 1024 / 1024  # GB
        
        if mem_total > 0:
            usage_percent = ((mem_total - mem_available) / mem_total) * 100
        else:
            usage_percent = 0
        
        if usage_percent > 95:
            status = "error"
        elif usage_percent > 85:
            status = "warning"
        else:
            status = "healthy"
        
        return HealthStatus(
            component="memory",
            status=status,
            message=f"Memory usage: {usage_percent:.1f}% ({mem_available:.1f}GB available)",
            timestamp=datetime.now(timezone.utc).isoformat(),
            details={"total_gb": mem_total, "available_gb": mem_available, "usage_percent": usage_percent}
        )
    except Exception as e:
        return HealthStatus(
            component="memory",
            status="error",
            message=str(e),
            timestamp=datetime.now(timezone.utc).isoformat()
        )


async def check_tasks() -> HealthStatus:
    """タスク状態チェック"""
    try:
        # tasks.dbの存在確認
        if os.path.exists("tasks.db"):
            size = os.path.getsize("tasks.db")
            return HealthStatus(
                component="tasks",
                status="healthy",
                message=f"Task database exists ({size} bytes)",
                timestamp=datetime.now(timezone.utc).isoformat(),
                details={"db_size": size}
            )
        else:
            return HealthStatus(
                component="tasks",
                status="warning",
                message="Task database not found",
                timestamp=datetime.now(timezone.utc).isoformat()
            )
    except Exception as e:
        return HealthStatus(
            component="tasks",
            status="error",
            message=str(e),
            timestamp=datetime.now(timezone.utc).isoformat()
        )


async def main():
    """ヘルスチェック実行"""
    monitor = get_monitor()
    
    # チェックを登録
    monitor.register_check("disk", check_disk_space)
    monitor.register_check("memory", check_memory)
    monitor.register_check("tasks", check_tasks)
    
    # 実行
    results = await monitor.run_all_checks()
    summary = monitor.get_summary()
    
    print(json.dumps(summary, indent=2, default=str))
    
    return summary


if __name__ == "__main__":
    asyncio.run(main())
