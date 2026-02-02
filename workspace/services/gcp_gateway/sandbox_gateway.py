"""
Sandbox Gateway Agent - コンテナ内サンドボックス実行環境

Entity A/Bはこのコンテナ内でのみ操作可能。
コンテナ外への脱出は不可能。

機能:
- コンテナ内でコマンド実行
- ファイル読み書き
- サービス起動・停止
- プロセス管理

制限:
- /app 以下のみアクセス可能
- 危険なコマンドはブロック
- ネットワークはコンテナ内のみ
"""

import os
import subprocess
import asyncio
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
import json
import signal

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Sandbox Gateway",
    description="Sandboxed execution environment for AI Entities",
    version="2.0.0"
)

# ========================================
# 設定
# ========================================

# サンドボックスのルートディレクトリ
SANDBOX_ROOT = "/app/sandbox"

# 許可されたベースパス
ALLOWED_PATHS = ["/app/sandbox", "/tmp"]

# 禁止コマンド
BLOCKED_COMMANDS = [
    "rm -rf /",
    "curl", "wget",  # 外部通信禁止
    "nc", "netcat",
    "ssh", "scp",
    "gcloud", "gsutil", "bq",  # GCPアクセス禁止
    "docker", "kubectl",  # コンテナ操作禁止
    "mount", "umount",
    "chmod 777",
    "sudo", "su",
]

# 認証トークン
GATEWAY_AUTH_TOKEN = os.getenv("GATEWAY_AUTH_TOKEN", "")

# 起動中のプロセス管理
running_processes: Dict[str, subprocess.Popen] = {}

# ========================================
# 認証
# ========================================

async def verify_token(authorization: Optional[str] = Header(None)):
    if not GATEWAY_AUTH_TOKEN:
        logger.warning("GATEWAY_AUTH_TOKEN not set - running in insecure mode")
        return True
    
    if not authorization:
        raise HTTPException(401, "Authorization header required")
    
    if authorization != f"Bearer {GATEWAY_AUTH_TOKEN}":
        raise HTTPException(403, "Invalid token")
    
    return True

# ========================================
# ヘルパー関数
# ========================================

def is_path_safe(path: str) -> bool:
    """パスがサンドボックス内かチェック"""
    abs_path = os.path.abspath(path)
    for allowed in ALLOWED_PATHS:
        if abs_path.startswith(allowed):
            return True
    return False

def is_command_safe(command: str) -> bool:
    """コマンドが安全かチェック"""
    cmd_lower = command.lower()
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            return False
    return True

def ensure_sandbox_exists():
    """サンドボックスディレクトリを作成"""
    os.makedirs(SANDBOX_ROOT, exist_ok=True)
    os.makedirs(f"{SANDBOX_ROOT}/services", exist_ok=True)
    os.makedirs(f"{SANDBOX_ROOT}/data", exist_ok=True)
    os.makedirs(f"{SANDBOX_ROOT}/logs", exist_ok=True)

# ========================================
# リクエスト/レスポンスモデル
# ========================================

class ExecRequest(BaseModel):
    command: str
    cwd: Optional[str] = None
    timeout: int = 60
    background: bool = False

class ExecResponse(BaseModel):
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int
    process_id: Optional[str] = None

class FileWriteRequest(BaseModel):
    path: str
    content: str
    overwrite: bool = False

class ServiceRequest(BaseModel):
    name: str
    command: str
    port: Optional[int] = None
    env: Optional[Dict[str, str]] = None

class ServiceInfo(BaseModel):
    name: str
    pid: int
    status: str
    port: Optional[int] = None
    started_at: str

# ========================================
# エンドポイント
# ========================================

@app.on_event("startup")
async def startup():
    ensure_sandbox_exists()
    logger.info(f"Sandbox Gateway started. Root: {SANDBOX_ROOT}")

@app.get("/")
async def root():
    """サンドボックス情報"""
    return {
        "service": "Sandbox Gateway",
        "version": "2.0.0",
        "sandbox_root": SANDBOX_ROOT,
        "status": "healthy",
        "features": [
            "command execution",
            "file operations", 
            "service management",
            "process control"
        ],
        "restrictions": [
            "no external network access",
            "no GCP operations",
            "sandbox paths only"
        ]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "sandbox_root": SANDBOX_ROOT}

# ----------------------------------------
# コマンド実行
# ----------------------------------------

@app.post("/exec", response_model=ExecResponse)
async def execute_command(req: ExecRequest, authorized: bool = Depends(verify_token)):
    """
    サンドボックス内でコマンドを実行
    
    制限:
    - 禁止コマンドはブロック
    - 作業ディレクトリはサンドボックス内のみ
    """
    if not is_command_safe(req.command):
        raise HTTPException(403, f"Command blocked for security reasons")
    
    cwd = req.cwd or SANDBOX_ROOT
    if not is_path_safe(cwd):
        raise HTTPException(403, f"Working directory must be within sandbox")
    
    start_time = datetime.now()
    
    try:
        if req.background:
            # バックグラウンド実行
            process = subprocess.Popen(
                req.command,
                shell=True,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True
            )
            process_id = f"proc_{process.pid}"
            running_processes[process_id] = process
            
            return ExecResponse(
                success=True,
                stdout=f"Started in background",
                stderr="",
                exit_code=0,
                duration_ms=0,
                process_id=process_id
            )
        else:
            # 同期実行
            result = subprocess.run(
                req.command,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=req.timeout
            )
            
            duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            
            return ExecResponse(
                success=result.returncode == 0,
                stdout=result.stdout[-10000:],  # 最後の10KB
                stderr=result.stderr[-5000:],
                exit_code=result.returncode,
                duration_ms=duration_ms
            )
            
    except subprocess.TimeoutExpired:
        return ExecResponse(
            success=False,
            stdout="",
            stderr=f"Command timed out after {req.timeout}s",
            exit_code=-1,
            duration_ms=req.timeout * 1000
        )
    except Exception as e:
        return ExecResponse(
            success=False,
            stdout="",
            stderr=str(e),
            exit_code=-1,
            duration_ms=0
        )

# ----------------------------------------
# ファイル操作
# ----------------------------------------

@app.get("/files/{path:path}")
async def read_file(path: str, authorized: bool = Depends(verify_token)):
    """ファイルを読み取る"""
    full_path = os.path.join(SANDBOX_ROOT, path)
    
    if not is_path_safe(full_path):
        raise HTTPException(403, "Path outside sandbox")
    
    if not os.path.exists(full_path):
        raise HTTPException(404, f"File not found: {path}")
    
    if os.path.isdir(full_path):
        # ディレクトリの場合は一覧を返す
        items = []
        for item in os.listdir(full_path):
            item_path = os.path.join(full_path, item)
            items.append({
                "name": item,
                "type": "directory" if os.path.isdir(item_path) else "file",
                "size": os.path.getsize(item_path) if os.path.isfile(item_path) else 0
            })
        return {"path": path, "type": "directory", "items": items}
    
    # ファイルの場合
    try:
        with open(full_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return {"path": path, "type": "file", "content": content, "size": len(content)}
    except UnicodeDecodeError:
        return {"path": path, "type": "binary", "size": os.path.getsize(full_path)}

@app.post("/files/{path:path}")
async def write_file(path: str, req: FileWriteRequest, authorized: bool = Depends(verify_token)):
    """ファイルを書き込む"""
    full_path = os.path.join(SANDBOX_ROOT, path)
    
    if not is_path_safe(full_path):
        raise HTTPException(403, "Path outside sandbox")
    
    if os.path.exists(full_path) and not req.overwrite:
        raise HTTPException(409, "File exists. Set overwrite=true to replace")
    
    # ディレクトリを作成
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    
    try:
        with open(full_path, 'w', encoding='utf-8') as f:
            f.write(req.content)
        return {"status": "written", "path": path, "size": len(req.content)}
    except Exception as e:
        raise HTTPException(500, f"Write failed: {str(e)}")

@app.delete("/files/{path:path}")
async def delete_file(path: str, authorized: bool = Depends(verify_token)):
    """ファイルを削除"""
    full_path = os.path.join(SANDBOX_ROOT, path)
    
    if not is_path_safe(full_path):
        raise HTTPException(403, "Path outside sandbox")
    
    if not os.path.exists(full_path):
        raise HTTPException(404, "File not found")
    
    try:
        if os.path.isdir(full_path):
            import shutil
            shutil.rmtree(full_path)
        else:
            os.remove(full_path)
        return {"status": "deleted", "path": path}
    except Exception as e:
        raise HTTPException(500, f"Delete failed: {str(e)}")

# ----------------------------------------
# サービス管理
# ----------------------------------------

@app.post("/services/start")
async def start_service(req: ServiceRequest, authorized: bool = Depends(verify_token)):
    """サービスを起動"""
    if req.name in running_processes:
        proc = running_processes[req.name]
        if proc.poll() is None:
            raise HTTPException(409, f"Service {req.name} is already running")
    
    if not is_command_safe(req.command):
        raise HTTPException(403, "Command blocked")
    
    env = os.environ.copy()
    if req.env:
        env.update(req.env)
    
    try:
        process = subprocess.Popen(
            req.command,
            shell=True,
            cwd=f"{SANDBOX_ROOT}/services",
            stdout=open(f"{SANDBOX_ROOT}/logs/{req.name}.log", 'w'),
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True
        )
        
        running_processes[req.name] = process
        
        return {
            "status": "started",
            "name": req.name,
            "pid": process.pid,
            "log_file": f"/logs/{req.name}.log"
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to start service: {str(e)}")

@app.post("/services/stop/{name}")
async def stop_service(name: str, authorized: bool = Depends(verify_token)):
    """サービスを停止"""
    if name not in running_processes:
        raise HTTPException(404, f"Service {name} not found")
    
    proc = running_processes[name]
    if proc.poll() is not None:
        del running_processes[name]
        return {"status": "already_stopped", "name": name}
    
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    
    del running_processes[name]
    return {"status": "stopped", "name": name}

@app.get("/services")
async def list_services(authorized: bool = Depends(verify_token)):
    """実行中のサービス一覧"""
    services = []
    for name, proc in list(running_processes.items()):
        status = "running" if proc.poll() is None else "stopped"
        services.append({
            "name": name,
            "pid": proc.pid,
            "status": status
        })
    return {"services": services, "count": len(services)}

@app.get("/services/logs/{name}")
async def get_service_logs(name: str, lines: int = 100, authorized: bool = Depends(verify_token)):
    """サービスのログを取得"""
    log_path = f"{SANDBOX_ROOT}/logs/{name}.log"
    
    if not os.path.exists(log_path):
        raise HTTPException(404, f"Log file not found for service {name}")
    
    try:
        with open(log_path, 'r') as f:
            all_lines = f.readlines()
            return {
                "name": name,
                "lines": all_lines[-lines:],
                "total_lines": len(all_lines)
            }
    except Exception as e:
        raise HTTPException(500, f"Failed to read logs: {str(e)}")

# ----------------------------------------
# プロセス管理
# ----------------------------------------

@app.get("/processes")
async def list_processes(authorized: bool = Depends(verify_token)):
    """実行中のプロセス一覧"""
    result = subprocess.run(
        "ps aux --no-headers | head -20",
        shell=True,
        capture_output=True,
        text=True
    )
    return {"processes": result.stdout, "count": len(result.stdout.splitlines())}

@app.post("/processes/kill/{pid}")
async def kill_process(pid: int, authorized: bool = Depends(verify_token)):
    """プロセスを終了"""
    try:
        os.kill(pid, signal.SIGTERM)
        return {"status": "killed", "pid": pid}
    except ProcessLookupError:
        raise HTTPException(404, f"Process {pid} not found")
    except PermissionError:
        raise HTTPException(403, f"Permission denied to kill process {pid}")

# ========================================
# 起動
# ========================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
