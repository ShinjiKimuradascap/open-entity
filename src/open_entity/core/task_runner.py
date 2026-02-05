import subprocess
import os
import sys
import signal
import re
from pathlib import Path
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv, find_dotenv
from ..storage.task_store import TaskStore, TaskStatus

# サブプロセス起動前に .env を読み込む
load_dotenv(find_dotenv())

class TaskRunner:
    def __init__(self, task_store: Optional[TaskStore] = None):
        self.store = task_store or TaskStore()
        self.log_dir = Path.home() / ".moco" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def run_task(self, task_id: str, profile: str, description: str, working_dir: Optional[str] = None, provider: Optional[str] = None, model: Optional[str] = None):
        """
        タスクをバックグラウンドで実行する。
        実際には、自分自身を別のプロセスとして起動し、そこでタスクを実行させる。
        """
        log_file = self.log_dir / f"{task_id}.log"
        
        # 内部的に実行するためのコマンド
        # oe コマンドを直接使用（インストールされたエントリポイントを使う）
        import shutil
        oe_path = shutil.which("oe")
        if oe_path:
            cmd = [
                oe_path,
                "tasks", "_exec",
                task_id,
                "--profile", profile,
            ]
        else:
            # フォールバック: python -m で実行
            cmd = [
                sys.executable, "-m", "open_entity.cli",
                "tasks", "_exec",
                task_id,
                "--profile", profile,
            ]
        
        # 作業ディレクトリが指定されている場合は引数として追加
        if working_dir:
            cmd.extend(["--working-dir", working_dir])
        
        # プロバイダーが指定されている場合は引数として追加
        if provider:
            cmd.extend(["--provider", provider])
        
        # モデルが指定されている場合は引数として追加
        if model:
            cmd.extend(["--model", model])
        
        # PYTHONPATH を確実に引き継ぐ (開発環境用)
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        
        # .env ファイルを読み込んで環境変数に追加
        def load_env_file(env_path: Path):
            if not env_path.exists():
                return
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, _, value = line.partition('=')
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key and key not in env:  # 既存の環境変数を上書きしない
                            env[key] = value

        # 優先順で .env を読み込む
        # 1. 作業ディレクトリの .env
        load_env_file(Path(working_dir or os.getcwd()) / ".env")
        # 2. open-entity の .env
        open_entity_root = Path(__file__).parent.parent.parent.parent
        load_env_file(open_entity_root / ".env")
        # 3. moco-workspace の .env (open-entity の親ディレクトリ)
        load_env_file(open_entity_root.parent / ".env")
        current_pythonpath = env.get("PYTHONPATH", "")
        # src ディレクトリがあれば開発中とみなして追加
        src_path = Path(__file__).parent.parent.parent
        if (src_path / "moco").exists():
            src_path_str = str(src_path)
            if current_pythonpath:
                env["PYTHONPATH"] = os.pathsep.join([src_path_str, current_pythonpath])
            else:
                env["PYTHONPATH"] = src_path_str

        # stdout/stderr をログファイルにリダイレクト
        # buffering=1 (行バッファリング) を指定
        log_f = open(log_file, "w", buffering=1)
        try:
            process = subprocess.Popen(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=env
            )
            
            self.store.update_task(
                task_id,
                pid=process.pid,
                status=TaskStatus.RUNNING,
                started_at=datetime.now().isoformat()
            )
        finally:
            # 親プロセス側では log_f を閉じて良い（子プロセスが引き継ぐ）
            log_f.close()

    def execute_task(self, task_id: str, task_info: dict, profile: str, working_dir: Optional[str] = None):
        """
        タスクを実際に実行する（サブプロセス内で呼ばれる）。
        Orchestratorを使ってタスクを処理し、結果をDBに保存する。
        """
        import asyncio
        from ..core.orchestrator import Orchestrator

        description = task_info.get("task_description", "")
        provider = task_info.get("provider")
        session_id = task_info.get("session_id")

        try:
            print(f"[Task] Starting: {description[:50]}...")
            print(f"[Task] Profile: {profile}, Provider: {provider}")

            # Orchestratorを初期化
            orchestrator = Orchestrator(
                profile=profile,
                provider=provider,
                working_directory=working_dir,
            )

            # タスクを実行
            async def run():
                response = await orchestrator.run(description, session_id=session_id)
                return response

            result = asyncio.run(run())

            # 成功
            print(f"\n[Task] Completed successfully")
            self.store.update_task(
                task_id,
                status=TaskStatus.COMPLETED,
                result=result,
                completed_at=datetime.now().isoformat()
            )

        except Exception as e:
            import traceback
            error_msg = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            print(f"\n[Task] Failed: {error_msg}")
            self.store.update_task(
                task_id,
                status=TaskStatus.FAILED,
                error=error_msg,
                completed_at=datetime.now().isoformat()
            )

    def cancel_task(self, task_id: str) -> bool:
        task = self.store.get_task(task_id)
        if not task or not task.get("pid"):
            # タスクは存在するがpidがない場合もCANCELLEDにする
            if task:
                full_task_id = task.get("task_id", task_id)
                self.store.update_task(full_task_id, status=TaskStatus.CANCELLED)
                return True
            return False
        
        # 完全なtask_idを使用（短縮ID対応）
        full_task_id = task.get("task_id", task_id)
        pid = task["pid"]
        try:
            # プロセスグループ全体を終了させる
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            self.store.update_task(
                full_task_id,
                status=TaskStatus.CANCELLED,
                completed_at=datetime.now().isoformat()
            )
            return True
        except ProcessLookupError:
            # 既に終了している場合
            self.store.update_task(full_task_id, status=TaskStatus.CANCELLED, error="Process already exited")
            return True
        except Exception as e:
            self.store.update_task(full_task_id, status=TaskStatus.CANCELLED, error=str(e))
            return True

    def _find_log_file(self, task_id: str) -> Optional[Path]:
        """短縮IDまたは完全IDからログファイルを検索"""
        # task_id が英数字（とハイフン）のみであることを確認（パストラバーサル対策）
        if not all(c.isalnum() or c == '-' for c in task_id):
            return None

        # 完全一致を試す
        log_file = (self.log_dir / f"{task_id}.log").resolve()
        if log_file.exists() and str(log_file).startswith(str(self.log_dir.resolve())):
            return log_file

        # 前方一致で検索（短縮ID対応）
        for f in self.log_dir.glob(f"{task_id}*.log"):
            resolved = f.resolve()
            if str(resolved).startswith(str(self.log_dir.resolve())):
                return resolved

        return None

    def get_logs(self, task_id: str, max_bytes: int = 10000) -> str:
        log_file = self._find_log_file(task_id)
        if log_file is None:
            return "Log file not found."
        
        file_size = log_file.stat().st_size
        with open(log_file, "r") as f:
            # max_bytes <= 0 は無制限
            if max_bytes > 0 and file_size > max_bytes:
                f.seek(file_size - max_bytes)
                return "...(truncated)...\n" + f.read()
            return f.read()

    def tail_logs(self, task_id: str):
        """
        ログを末尾まで表示し、更新を監視し続ける (tail -f 相当)
        """
        import time

        log_file = self._find_log_file(task_id)
        if log_file is None:
            print(f"Log file not found for task: {task_id}")
            return

        print(f"--- Following logs for task: {task_id} (Ctrl+C to stop) ---")

        with open(log_file, "r") as f:
            # 既存の内容を表示
            print(f.read(), end="")

            # 監視ループ
            try:
                while True:
                    line = f.readline()
                    if not line:
                        # まだ書き込みがあるかもしれないので少し待機
                        time.sleep(0.1)
                        continue
                    print(line, end="", flush=True)
            except KeyboardInterrupt:
                print("\nStopped.")

    def get_last_action(self, task_id: str) -> Optional[str]:
        """
        タスクのログから最後のツールコールを抽出する。
        例: "editing cli.py", "reading base.py", "delegating to @code-reviewer"
        """
        log_file = self._find_log_file(task_id)
        if log_file is None:
            return None

        try:
            # 最後の10KBを読む
            file_size = log_file.stat().st_size
            read_size = min(file_size, 10000)
            
            with open(log_file, "r", errors="ignore") as f:
                if file_size > read_size:
                    f.seek(file_size - read_size)
                content = f.read()            # ツールコールのパターン
            patterns = [
                (r'👤 delegate_to_agent\s*→\s*@?(\S+)', lambda m: f"delegating to @{m.group(1)}"),
                (r'✏️ edit_file\s*→\s*(\S+)', lambda m: f"editing {self._truncate(m.group(1))}"),
                (r'📝 write_file\s*→\s*(\S+)', lambda m: f"writing {self._truncate(m.group(1))}"),
                (r'📖 read_file\s*→\s*(\S+)', lambda m: f"reading {self._truncate(m.group(1))}"),
                (r'🔎 grep\s*→', lambda m: "searching..."),
                (r'⚡ execute_bash\s*→', lambda m: "executing..."),
                (r'🔧 (\w+)\s*→', lambda m: f"{m.group(1)}..."),
                (r'🔍 websearch\s*→', lambda m: "searching web..."),
                (r'\[思考中\.\.\.\]', lambda m: "thinking..."),
            ]

            # 最後にマッチしたものを探す
            last_match = None
            last_pos = -1
            
            for pattern, formatter in patterns:
                for match in re.finditer(pattern, content):
                    if match.start() > last_pos:
                        last_pos = match.start()
                        last_match = (match, formatter)

            if last_match:
                match, formatter = last_match
                return formatter(match)
            return None

        except Exception:
            return None

    def _truncate(self, text: str, max_len: int = 20) -> str:
        """長いテキストを省略する"""
        # パスの場合はファイル名だけ取り出す
        if "/" in text or "\\" in text:
            text = Path(text).name
        if len(text) > max_len:
            return text[:max_len - 3] + "..."
        return text
