"""Auto Restart Service API Integration

APIサーバーとの統合エンドポイントを提供します。
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from services.auto_restart_service import AutoRestartService, ServiceState

# APIルーター
router = APIRouter(prefix="/auto-restart", tags=["auto-restart"])

# グローバルサービスインスタンス
_service: Optional[AutoRestartService] = None


class ServiceStatusResponse(BaseModel):
    """サービス状態レスポンス"""
    state: str
    is_running: bool
    is_paused: bool
    stats: Dict[str, Any]
    crash_count: int
    timestamp: str


class TaskCheckResponse(BaseModel):
    """タスク確認レスポンス"""
    status: str
    pending_tasks: int
    completed_tasks: int
    message: str
    timestamp: str


class ReportResponse(BaseModel):
    """進捗報告レスポンス"""
    status: str
    message: str
    report_file: Optional[str]
    timestamp: str


class WakeUpResponse(BaseModel):
    """Wake Up レスポンス"""
    status: str
    message: str
    service_state: str
    timestamp: str


class ControlRequest(BaseModel):
    """制御リクエスト"""
    action: str = Field(..., description="アクション: start, stop, pause, resume")


def get_service() -> Optional[AutoRestartService]:
    """グローバルサービスインスタンスを取得"""
    return _service


def set_service(service: AutoRestartService):
    """グローバルサービスインスタンスを設定"""
    global _service
    _service = service


@router.get("/status", response_model=ServiceStatusResponse)
async def get_status() -> ServiceStatusResponse:
    """サービスの現在の状態を取得"""
    service = get_service()
    
    if not service:
        # サービスが起動していない場合はファイルから取得
        try:
            from services.auto_restart_service import PersistenceManager
            pm = PersistenceManager()
            state = pm.load_state()
            if state:
                return ServiceStatusResponse(
                    state=state.get('state', 'unknown'),
                    is_running=state.get('state') == ServiceState.RUNNING.value,
                    is_paused=state.get('state') == ServiceState.PAUSED.value,
                    stats=state.get('stats', {}),
                    crash_count=state.get('crash_count', 0),
                    timestamp=datetime.now(timezone.utc).isoformat()
                )
        except Exception:
            pass
        
        raise HTTPException(status_code=503, detail="サービスが起動していません")
    
    status = service.get_status()
    return ServiceStatusResponse(
        state=status['state'],
        is_running=status['state'] == ServiceState.RUNNING.value,
        is_paused=status['is_paused'],
        stats=status['stats'],
        crash_count=status['crash_count'],
        timestamp=status['timestamp']
    )


@router.post("/check", response_model=TaskCheckResponse)
async def check_tasks(background_tasks: BackgroundTasks) -> TaskCheckResponse:
    """即座にタスク確認を実行"""
    service = get_service()
    
    if not service:
        raise HTTPException(status_code=503, detail="サービスが起動していません")
    
    # バックグラウンドでタスク確認を実行
    async def do_check():
        await service._check_tasks_immediate()
    
    background_tasks.add_task(do_check)
    
    return TaskCheckResponse(
        status="started",
        pending_tasks=service.stats.tasks_pending,
        completed_tasks=service.stats.tasks_completed,
        message="タスク確認をバックグラウンドで開始しました",
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.post("/report", response_model=ReportResponse)
async def send_report(background_tasks: BackgroundTasks) -> ReportResponse:
    """即座に進捗報告を送信"""
    service = get_service()
    
    if not service:
        raise HTTPException(status_code=503, detail="サービスが起動していません")
    
    # バックグラウンドでレポート送信
    async def do_report():
        await service._send_progress_report()
    
    background_tasks.add_task(do_report)
    
    return ReportResponse(
        status="started",
        message="進捗報告をバックグラウンドで送信しました",
        report_file=None,
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.post("/wake-up", response_model=WakeUpResponse)
async def wake_up(background_tasks: BackgroundTasks) -> WakeUpResponse:
    """ピアからの起動リクエストを処理"""
    service = get_service()
    
    if not service:
        raise HTTPException(status_code=503, detail="サービスが起動していません")
    
    # wake_up ハンドラを呼び出し
    response = service.peer_handler.handle_message('wake_up', {
        'source': 'api',
        'timestamp': datetime.now(timezone.utc).isoformat()
    })
    
    return WakeUpResponse(
        status=response.get('status', 'unknown'),
        message=response.get('message', ''),
        service_state=response.get('service_state', 'unknown'),
        timestamp=datetime.now(timezone.utc).isoformat()
    )


@router.post("/control")
async def control_service(request: ControlRequest):
    """サービスを制御（start, stop, pause, resume）"""
    service = get_service()
    
    if not service:
        raise HTTPException(status_code=503, detail="サービスが起動していません")
    
    action = request.action.lower()
    
    if action == 'start':
        if service.state == ServiceState.RUNNING:
            return {"status": "already_running", "message": "サービスは既に実行中です"}
        # 別スレッドで開始
        import threading
        thread = threading.Thread(target=service.start)
        thread.daemon = True
        thread.start()
        return {"status": "starting", "message": "サービスを開始しています"}
    
    elif action == 'stop':
        service.stop()
        return {"status": "stopping", "message": "サービスを停止しています"}
    
    elif action == 'pause':
        service.pause()
        return {"status": "paused", "message": "サービスを一時停止しました"}
    
    elif action == 'resume':
        service.resume()
        return {"status": "resumed", "message": "サービスを再開しました"}
    
    else:
        raise HTTPException(status_code=400, detail=f"不明なアクション: {action}")


@router.get("/health")
async def health_check():
    """ヘルスチェックエンドポイント"""
    service = get_service()
    
    if not service:
        return {
            "status": "not_initialized",
            "healthy": False,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    is_healthy = service.state in [ServiceState.RUNNING, ServiceState.PAUSED]
    
    return {
        "status": service.state.value,
        "healthy": is_healthy,
        "uptime": service.stats.start_time if service.stats.start_time else None,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# エクスポート
__all__ = [
    'router',
    'get_service',
    'set_service',
    'ServiceStatusResponse',
    'TaskCheckResponse',
    'ReportResponse',
    'WakeUpResponse',
    'ControlRequest'
]
