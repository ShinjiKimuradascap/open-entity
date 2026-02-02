"""Auto Restart Service - 自動再起動と定期実行の仕組み

このモジュールは以下の機能を提供します：
1. 5分ごとのタスク確認 (todoread_all)
2. 1時間ごとの進捗報告 (report_to_peer)
3. ピアからの起動対応 (wake_up_peer)
4. クラッシュ時の自動復帰

Usage:
    # サービスの起動
    python services/auto_restart_service.py
    
    # プログラムからの使用
    from services.auto_restart_service import AutoRestartService
    service = AutoRestartService()
    service.start()
"""

import asyncio
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, asdict, field

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/home/moco/workspace/logs/auto_restart.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# 定数
STATE_FILE = Path('/home/moco/workspace/data/auto_restart_state.json')
PID_FILE = Path('/home/moco/workspace/data/auto_restart.pid')
LOG_DIR = Path('/home/moco/workspace/logs')
CHECK_INTERVAL = 300  # 5分 = 300秒
REPORT_INTERVAL = 3600  # 1時間 = 3600秒
RECOVERY_BACKOFF = [5, 10, 30, 60, 300]  # クラッシュ復帰時の待機時間（秒）


class ServiceState(Enum):
    """サービスの状態"""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    RECOVERING = "recovering"


class TaskStatus(Enum):
    """タスクの状態"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """タスク情報"""
    id: str
    content: str
    status: str
    priority: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ServiceStats:
    """サービス統計情報"""
    start_time: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_check_time: Optional[str] = None
    last_report_time: Optional[str] = None
    total_checks: int = 0
    total_reports: int = 0
    tasks_completed: int = 0
    tasks_pending: int = 0
    crash_count: int = 0
    last_crash_time: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PersistenceManager:
    """永続化管理 - クラッシュ復帰のための状態保存"""
    
    def __init__(self, state_file: Path = STATE_FILE):
        self.state_file = state_file
        self._lock = threading.Lock()
        self._ensure_dir()
    
    def _ensure_dir(self):
        """ディレクトリが存在することを確認"""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
    
    def save_state(self, state: Dict[str, Any]) -> bool:
        """状態をファイルに保存"""
        try:
            with self._lock:
                temp_file = self.state_file.with_suffix('.tmp')
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(state, f, ensure_ascii=False, indent=2)
                temp_file.replace(self.state_file)
                logger.debug(f"状態を保存しました: {self.state_file}")
                return True
        except Exception as e:
            logger.error(f"状態保存エラー: {e}")
            return False
    
    def load_state(self) -> Optional[Dict[str, Any]]:
        """ファイルから状態を読み込み"""
        try:
            if not self.state_file.exists():
                return None
            with self._lock:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"状態読み込みエラー: {e}")
            return None
    
    def clear_state(self) -> bool:
        """状態をクリア"""
        try:
            with self._lock:
                if self.state_file.exists():
                    self.state_file.unlink()
                return True
        except Exception as e:
            logger.error(f"状態クリアエラー: {e}")
            return False


class PeerCommunicationHandler:
    """ピア通信ハンドラー - wake_up_peer 対応"""
    
    def __init__(self, service: 'AutoRestartService'):
        self.service = service
        self._handlers: Dict[str, Callable] = {
            'wake_up': self._handle_wake_up,
            'status_check': self._handle_status_check,
            'pause': self._handle_pause,
            'resume': self._handle_resume,
        }
    
    def handle_message(self, msg_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """メッセージを処理"""
        handler = self._handlers.get(msg_type, self._handle_unknown)
        try:
            return handler(payload)
        except Exception as e:
            logger.error(f"メッセージ処理エラー [{msg_type}]: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _handle_wake_up(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """wake_up メッセージ処理"""
        logger.info(f"🌅 wake_up リクエストを受信: {payload}")
        
        # 即座にタスク確認を実行
        asyncio.create_task(self.service._check_tasks_immediate())
        
        return {
            'status': 'success',
            'message': 'タスク確認を開始しました',
            'service_state': self.service.state.value,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _handle_status_check(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """ステータス確認メッセージ処理"""
        return {
            'status': 'success',
            'service_state': self.service.state.value,
            'stats': self.service.stats.to_dict(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
    
    def _handle_pause(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """一時停止リクエスト処理"""
        self.service.pause()
        return {
            'status': 'success',
            'message': 'サービスを一時停止しました',
            'service_state': self.service.state.value
        }
    
    def _handle_resume(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """再開リクエスト処理"""
        self.service.resume()
        return {
            'status': 'success',
            'message': 'サービスを再開しました',
            'service_state': self.service.state.value
        }
    
    def _handle_unknown(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """不明なメッセージ処理"""
        return {
            'status': 'error',
            'message': '不明なメッセージタイプです',
            'available_types': list(self._handlers.keys())
        }


class AutoRestartService:
    """自動再起動サービス
    
    5分ごとのタスク確認と1時間ごとの進捗報告を自動実行します。
    クラッシュ時には自動的に復帰を試みます。
    """
    
    def __init__(
        self,
        check_interval: int = CHECK_INTERVAL,
        report_interval: int = REPORT_INTERVAL,
        enable_recovery: bool = True
    ):
        self.check_interval = check_interval
        self.report_interval = report_interval
        self.enable_recovery = enable_recovery
        
        self.state = ServiceState.STOPPED
        self.stats = ServiceStats()
        self.persistence = PersistenceManager()
        self.peer_handler = PeerCommunicationHandler(self)
        
        self._stop_event = asyncio.Event()
        self._pause_event = asyncio.Event()
        self._tasks: Set[asyncio.Task] = set()
        self._crash_count = 0
        self._last_crash_time: Optional[datetime] = None
        
        # PIDファイル管理
        self._write_pid()
        
        # シグナルハンドラ設定
        self._setup_signal_handlers()
    
    def _write_pid(self):
        """PIDファイルに書き込み"""
        try:
            PID_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except Exception as e:
            logger.warning(f"PIDファイル書き込みエラー: {e}")
    
    def _remove_pid(self):
        """PIDファイルを削除"""
        try:
            if PID_FILE.exists():
                PID_FILE.unlink()
        except Exception as e:
            logger.warning(f"PIDファイル削除エラー: {e}")
    
    def _setup_signal_handlers(self):
        """シグナルハンドラを設定"""
        def handle_signal(signum, frame):
            sig_name = signal.Signals(signum).name
            logger.info(f"シグナル受信: {sig_name}")
            self._schedule_shutdown()
        
        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)
    
    def _schedule_shutdown(self):
        """シャットダウンをスケジュール"""
        logger.info("シャットダウンをスケジュール...")
        self._stop_event.set()
    
    def _save_current_state(self):
        """現在の状態を保存"""
        state = {
            'state': self.state.value,
            'stats': self.stats.to_dict(),
            'crash_count': self._crash_count,
            'last_crash_time': self._last_crash_time.isoformat() if self._last_crash_time else None,
            'saved_at': datetime.now(timezone.utc).isoformat()
        }
        self.persistence.save_state(state)
    
    def _load_previous_state(self) -> Optional[Dict[str, Any]]:
        """前回の状態を読み込み"""
        return self.persistence.load_state()
    
    def start(self):
        """サービスを開始"""
        if self.state == ServiceState.RUNNING:
            logger.warning("サービスは既に実行中です")
            return
        
        self.state = ServiceState.STARTING
        logger.info("🚀 自動再起動サービスを開始します")
        
        # 前回の状態を確認
        previous_state = self._load_previous_state()
        if previous_state:
            logger.info(f"前回の状態を復元: {previous_state.get('state')}")
            if previous_state.get('state') == ServiceState.ERROR.value:
                logger.info("前回はエラー状態で終了しました。復帰を試みます...")
        
        try:
            asyncio.run(self._main_loop())
        except Exception as e:
            logger.error(f"メインループエラー: {e}")
            self._handle_crash(e)
        finally:
            self._cleanup()
    
    async def _main_loop(self):
        """メインイベントループ"""
        self.state = ServiceState.RUNNING
        self._stop_event.clear()
        self._pause_event.clear()
        
        logger.info(f"✅ サービスが実行中です")
        logger.info(f"   - タスク確認間隔: {self.check_interval}秒")
        logger.info(f"   - 進捗報告間隔: {self.report_interval}秒")
        
        # 定期タスクを開始
        check_task = asyncio.create_task(self._check_loop())
        report_task = asyncio.create_task(self._report_loop())
        
        self._tasks.add(check_task)
        self._tasks.add(report_task)
        
        # 停止イベントを待機
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            # タスクをキャンセル
            for task in self._tasks:
                task.cancel()
            
            # タスク完了を待機
            await asyncio.gather(*self._tasks, return_exceptions=True)
    
    async def _check_loop(self):
        """タスク確認ループ - 5分ごと"""
        while not self._stop_event.is_set():
            try:
                # 一時停止中は待機
                if self._pause_event.is_set():
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=1
                    )
                    continue
                
                await self._check_tasks()
                self.stats.total_checks += 1
                self.stats.last_check_time = datetime.now(timezone.utc).isoformat()
                self._save_current_state()
                
            except Exception as e:
                logger.error(f"タスク確認エラー: {e}")
            
            # 次の確認まで待機
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.check_interval
                )
            except asyncio.TimeoutError:
                pass
    
    async def _report_loop(self):
        """進捗報告ループ - 1時間ごと"""
        # 初回は少し待ってから
        await asyncio.sleep(60)
        
        while not self._stop_event.is_set():
            try:
                if self._pause_event.is_set():
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=1
                    )
                    continue
                
                await self._send_progress_report()
                self.stats.total_reports += 1
                self.stats.last_report_time = datetime.now(timezone.utc).isoformat()
                self._save_current_state()
                
            except Exception as e:
                logger.error(f"進捗報告エラー: {e}")
            
            # 次の報告まで待機
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.report_interval
                )
            except asyncio.TimeoutError:
                pass
    
    async def _check_tasks(self):
        """タスクを確認して未完了があれば処理"""
        logger.info("📋 タスク確認を実行します...")
        
        try:
            # todoread_all() の代わりに直接ファイルを確認
            # 実際のシステムでは todoread_all() を呼び出す
            todos = await self._fetch_todos()
            
            pending_tasks = [
                t for t in todos
                if t.get('status') in ['pending', 'in_progress']
            ]
            
            self.stats.tasks_pending = len(pending_tasks)
            
            if pending_tasks:
                logger.info(f"⏳ 未完了タスクが {len(pending_tasks)} 件あります")
                
                # タスクを処理
                for task in pending_tasks[:5]:  # 一度に最大5件
                    await self._process_task(task)
            else:
                logger.info("✅ 未完了タスクはありません")
            
            # 完了タスク数を更新
            completed = len([t for t in todos if t.get('status') == 'completed'])
            self.stats.tasks_completed = completed
            
        except Exception as e:
            logger.error(f"タスク確認中にエラー: {e}")
            raise
    
    async def _check_tasks_immediate(self):
        """即座にタスク確認を実行（wake_upから呼ばれる）"""
        logger.info("🌅 即座タスク確認を実行します")
        await self._check_tasks()
    
    async def _fetch_todos(self) -> List[Dict[str, Any]]:
        """TODOリストを取得"""
        # 実際のシステムでは todoread_all() を呼び出す
        # ここではファイルベースで実装
        todo_files = [
            Path('/home/moco/workspace/data/todos.json'),
            Path('/home/moco/workspace/data/tasks.json'),
        ]
        
        all_todos = []
        for todo_file in todo_files:
            if todo_file.exists():
                try:
                    with open(todo_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            all_todos.extend(data)
                        elif isinstance(data, dict) and 'todos' in data:
                            all_todos.extend(data['todos'])
                except Exception as e:
                    logger.debug(f"TODOファイル読み込みエラー: {e}")
        
        # todoread_all() のような動作を模倣
        return all_todos
    
    async def _process_task(self, task: Dict[str, Any]):
        """個別タスクを処理"""
        task_id = task.get('id', 'unknown')
        content = task.get('content', '')[:50]
        
        logger.info(f"🔄 タスク処理: [{task_id}] {content}...")
        
        # タスクの種類に応じた処理
        try:
            if 'test' in content.lower():
                await self._run_test_task(task)
            elif 'report' in content.lower():
                await self._run_report_task(task)
            else:
                await self._run_generic_task(task)
            
            # タスクを完了としてマーク
            task['status'] = 'completed'
            task['completed_at'] = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"✅ タスク完了: [{task_id}]")
            
        except Exception as e:
            logger.error(f"❌ タスク処理エラー [{task_id}]: {e}")
            task['status'] = 'error'
            task['error'] = str(e)
    
    async def _run_test_task(self, task: Dict[str, Any]):
        """テストタスクを実行"""
        logger.info(f"🧪 テストタスク実行: {task.get('content', '')}")
        # 実際のテスト実行はここに実装
        await asyncio.sleep(0.5)  # シミュレーション
    
    async def _run_report_task(self, task: Dict[str, Any]):
        """レポートタスクを実行"""
        logger.info(f"📊 レポートタスク実行: {task.get('content', '')}")
        await self._send_progress_report()
        await asyncio.sleep(0.5)
    
    async def _run_generic_task(self, task: Dict[str, Any]):
        """汎用タスクを実行"""
        logger.info(f"⚙️ 汎用タスク実行: {task.get('content', '')}")
        await asyncio.sleep(0.5)
    
    async def _send_progress_report(self):
        """進捗報告を送信"""
        logger.info("📤 進捗報告を送信します...")
        
        try:
            # report_to_peer() の代わりに直接実装
            # 実際のシステムでは report_to_peer() を呼び出す
            
            pending = self.stats.tasks_pending
            completed = self.stats.tasks_completed
            
            status_msg = f"タスク状況: 未完了{pending}件 / 完了{completed}件"
            next_action = "継続監視" if pending > 0 else "新規タスク待機"
            
            report = {
                'type': 'progress_report',
                'status': status_msg,
                'next_action': next_action,
                'stats': self.stats.to_dict(),
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
            # レポートをファイルに保存
            report_file = Path('/home/moco/workspace/data/progress_reports')
            report_file.mkdir(parents=True, exist_ok=True)
            
            filename = f"report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            with open(report_file / filename, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            
            logger.info(f"📤 進捗報告送信完了: {status_msg}")
            
        except Exception as e:
            logger.error(f"進捗報告送信エラー: {e}")
            raise
    
    def _handle_crash(self, error: Exception):
        """クラッシュ時の処理"""
        self.state = ServiceState.ERROR
        self._crash_count += 1
        self._last_crash_time = datetime.now(timezone.utc)
        
        self.stats.crash_count = self._crash_count
        self.stats.last_crash_time = self._last_crash_time.isoformat()
        
        logger.error(f"💥 サービスがクラッシュしました (回数: {self._crash_count})")
        logger.error(f"   エラー: {error}")
        logger.error(traceback.format_exc())
        
        self._save_current_state()
        
        if self.enable_recovery and self._crash_count <= len(RECOVERY_BACKOFF):
            wait_time = RECOVERY_BACKOFF[min(self._crash_count - 1, len(RECOVERY_BACKOFF) - 1)]
            logger.info(f"⏳ {wait_time}秒後に復帰を試みます...")
            time.sleep(wait_time)
            
            self.state = ServiceState.RECOVERING
            logger.info("🔄 サービスを再起動します...")
            
            # 再起動
            self.start()
        else:
            logger.error("💀 復帰上限に達しました。手動での対応が必要です。")
    
    def _cleanup(self):
        """クリーンアップ処理"""
        logger.info("🧹 クリーンアップを実行します")
        self.state = ServiceState.STOPPED
        self._save_current_state()
        self._remove_pid()
    
    def stop(self):
        """サービスを停止"""
        logger.info("🛑 サービス停止をリクエスト")
        self._stop_event.set()
    
    def pause(self):
        """サービスを一時停止"""
        logger.info("⏸️ サービスを一時停止します")
        self.state = ServiceState.PAUSED
        self._pause_event.set()
        self._save_current_state()
    
    def resume(self):
        """サービスを再開"""
        logger.info("▶️ サービスを再開します")
        self.state = ServiceState.RUNNING
        self._pause_event.clear()
        self._save_current_state()
    
    def get_status(self) -> Dict[str, Any]:
        """サービス状態を取得"""
        return {
            'state': self.state.value,
            'stats': self.stats.to_dict(),
            'crash_count': self._crash_count,
            'is_paused': self._pause_event.is_set(),
            'is_stopped': self._stop_event.is_set(),
            'timestamp': datetime.now(timezone.utc).isoformat()
        }


def create_systemd_service_file():
    """Systemdサービスファイルを作成"""
    service_content = """[Unit]
Description=AI Collaboration Platform - Auto Restart Service
After=network.target

[Service]
Type=simple
User=moco
WorkingDirectory=/home/moco/workspace
Environment=PYTHONPATH=/home/moco/workspace
Environment=LOG_LEVEL=INFO
ExecStart=/usr/bin/python3 /home/moco/workspace/services/auto_restart_service.py
Restart=always
RestartSec=10
StandardOutput=append:/home/moco/workspace/logs/auto_restart_systemd.log
StandardError=append:/home/moco/workspace/logs/auto_restart_systemd_error.log

[Install]
WantedBy=multi-user.target
"""
    
    service_path = Path('/home/moco/workspace/setup/auto_restart.service')
    service_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(service_path, 'w') as f:
        f.write(service_content)
    
    print(f"Systemdサービスファイルを作成しました: {service_path}")
    print("インストール方法:")
    print(f"  sudo cp {service_path} /etc/systemd/system/")
    print("  sudo systemctl daemon-reload")
    print("  sudo systemctl enable auto_restart")
    print("  sudo systemctl start auto_restart")


def run_daemon():
    """デーモンとして実行"""
    import daemon
    import daemon.pidfile
    
    log_file = open('/home/moco/workspace/logs/auto_restart_daemon.log', 'a+')
    
    context = daemon.DaemonContext(
        working_directory='/home/moco/workspace',
        umask=0o002,
        pidfile=daemon.pidfile.PIDLockFile('/home/moco/workspace/data/auto_restart.pid'),
        stdout=log_file,
        stderr=log_file,
    )
    
    with context:
        service = AutoRestartService()
        service.start()


async def test_service():
    """サービスのテスト"""
    print("🧪 Auto Restart Service テスト")
    print("=" * 50)
    
    # テスト用のサービスを作成（短い間隔で）
    service = AutoRestartService(
        check_interval=10,  # 10秒
        report_interval=30,  # 30秒
        enable_recovery=False
    )
    
    # 状態確認
    print(f"初期状態: {service.get_status()}")
    
    # 5秒だけ実行
    print("\n⏱️ 5秒間サービスを実行します...")
    
    async def run_and_stop():
        await asyncio.sleep(5)
        service.stop()
    
    await asyncio.gather(
        service._main_loop(),
        run_and_stop()
    )
    
    print(f"\n最終状態: {service.get_status()}")
    print("\n✅ テスト完了")


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Auto Restart Service - 自動再起動と定期実行'
    )
    parser.add_argument(
        '--daemon', '-d',
        action='store_true',
        help='デーモンとして実行'
    )
    parser.add_argument(
        '--test', '-t',
        action='store_true',
        help='テストモードで実行'
    )
    parser.add_argument(
        '--systemd',
        action='store_true',
        help='Systemdサービスファイルを作成'
    )
    parser.add_argument(
        '--check-interval',
        type=int,
        default=CHECK_INTERVAL,
        help=f'タスク確認間隔（秒、デフォルト: {CHECK_INTERVAL}）'
    )
    parser.add_argument(
        '--report-interval',
        type=int,
        default=REPORT_INTERVAL,
        help=f'進捗報告間隔（秒、デフォルト: {REPORT_INTERVAL}）'
    )
    parser.add_argument(
        '--no-recovery',
        action='store_true',
        help='クラッシュ復帰を無効化'
    )
    
    args = parser.parse_args()
    
    if args.systemd:
        create_systemd_service_file()
    elif args.test:
        asyncio.run(test_service())
    elif args.daemon:
        run_daemon()
    else:
        # 通常実行
        service = AutoRestartService(
            check_interval=args.check_interval,
            report_interval=args.report_interval,
            enable_recovery=not args.no_recovery
        )
        
        try:
            service.start()
        except KeyboardInterrupt:
            print("\n👋 終了します")
            service.stop()
