"""
GCP Gateway Agent - 限定されたGCP操作のみを許可するプロキシサービス

ローカルのEntity A/Bは直接GCPにアクセスせず、このGateway経由で
許可された操作のみを実行できる。

セキュリティ:
- 許可されたサービス名のみデプロイ可能
- 許可されたリージョンのみ使用可能
- 全操作をログに記録
- 認証トークンで保護
"""

import os
import subprocess
import logging
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Header, Depends
from pydantic import BaseModel
import json

# ログ設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GCP Gateway Agent",
    description="Limited GCP operations for AI Entities",
    version="1.0.0"
)

# ========================================
# 設定
# ========================================

# 許可されたサービス名（これ以外はデプロイ不可）
ALLOWED_SERVICES = [
    "ai-roulette",
    "api-server", 
    "frontend",
    "entity-gateway",
    "marketplace-api",
    "messaging-api",
]

# 許可されたリージョン
ALLOWED_REGIONS = [
    "asia-northeast1",  # 東京
    "asia-northeast2",  # 大阪
    "us-central1",
]

# 許可されたDockerレジストリ
ALLOWED_REGISTRIES = [
    "gcr.io",
    "asia.gcr.io",
    "us.gcr.io",
    "docker.io",
]

# 認証トークン（環境変数から取得）
GATEWAY_AUTH_TOKEN = os.getenv("GATEWAY_AUTH_TOKEN", "")

# GCPプロジェクトID
GCP_PROJECT = os.getenv("GCP_PROJECT", "")

# ========================================
# 認証
# ========================================

async def verify_token(authorization: Optional[str] = Header(None)):
    """認証トークンを検証"""
    if not GATEWAY_AUTH_TOKEN:
        # トークン未設定の場合は警告を出すが許可（開発用）
        logger.warning("GATEWAY_AUTH_TOKEN not set - running in insecure mode")
        return True
    
    if not authorization:
        raise HTTPException(401, "Authorization header required")
    
    if authorization != f"Bearer {GATEWAY_AUTH_TOKEN}":
        raise HTTPException(403, "Invalid token")
    
    return True

# ========================================
# リクエスト/レスポンスモデル
# ========================================

class DeployRequest(BaseModel):
    service_name: str
    image: str
    region: str = "asia-northeast1"
    env_vars: Optional[dict] = None
    memory: str = "512Mi"
    cpu: str = "1"
    min_instances: int = 0
    max_instances: int = 10

class DeployResponse(BaseModel):
    status: str
    service_name: str
    url: Optional[str] = None
    message: str
    timestamp: str

class LogsRequest(BaseModel):
    service_name: str
    lines: int = 100
    severity: Optional[str] = None  # INFO, WARNING, ERROR

class StatusResponse(BaseModel):
    service_name: str
    status: str
    url: Optional[str] = None
    last_deployed: Optional[str] = None
    replicas: Optional[int] = None

class ScaleRequest(BaseModel):
    service_name: str
    min_instances: int
    max_instances: int

class CommandLog(BaseModel):
    timestamp: str
    command: str
    service_name: str
    requester: str
    result: str
    duration_ms: int

# 操作ログを保存
operation_logs: List[CommandLog] = []

# ========================================
# ヘルパー関数
# ========================================

def validate_service_name(service_name: str) -> bool:
    """サービス名が許可リストにあるか確認"""
    if service_name not in ALLOWED_SERVICES:
        raise HTTPException(
            403, 
            f"Service '{service_name}' is not allowed. Allowed: {ALLOWED_SERVICES}"
        )
    return True

def validate_region(region: str) -> bool:
    """リージョンが許可リストにあるか確認"""
    if region not in ALLOWED_REGIONS:
        raise HTTPException(
            403,
            f"Region '{region}' is not allowed. Allowed: {ALLOWED_REGIONS}"
        )
    return True

def validate_image(image: str) -> bool:
    """イメージが許可されたレジストリからか確認"""
    for registry in ALLOWED_REGISTRIES:
        if image.startswith(registry) or "/" not in image.split(":")[0]:
            return True
    raise HTTPException(
        403,
        f"Image registry not allowed. Allowed: {ALLOWED_REGISTRIES}"
    )

def run_gcloud_command(args: List[str], timeout: int = 300) -> dict:
    """gcloudコマンドを実行"""
    cmd = ["gcloud"] + args
    logger.info(f"Executing: {' '.join(cmd)}")
    
    start_time = datetime.now()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        duration_ms = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "duration_ms": duration_ms
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": "Command timed out",
            "returncode": -1,
            "duration_ms": timeout * 1000
        }
    except Exception as e:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(e),
            "returncode": -1,
            "duration_ms": 0
        }

def log_operation(command: str, service_name: str, result: str, duration_ms: int):
    """操作をログに記録"""
    log_entry = CommandLog(
        timestamp=datetime.now().isoformat(),
        command=command,
        service_name=service_name,
        requester="entity",  # TODO: 認証から取得
        result=result,
        duration_ms=duration_ms
    )
    operation_logs.append(log_entry)
    # 最新1000件のみ保持
    if len(operation_logs) > 1000:
        operation_logs.pop(0)
    
    logger.info(f"Operation: {command} on {service_name} - {result}")

# ========================================
# エンドポイント
# ========================================

@app.get("/")
async def root():
    """ヘルスチェック"""
    return {
        "service": "GCP Gateway Agent",
        "status": "healthy",
        "version": "1.0.0",
        "allowed_services": ALLOWED_SERVICES,
        "allowed_regions": ALLOWED_REGIONS
    }

@app.get("/health")
async def health():
    """ヘルスチェック"""
    return {"status": "healthy"}

@app.post("/deploy", response_model=DeployResponse)
async def deploy_service(req: DeployRequest, authorized: bool = Depends(verify_token)):
    """
    Cloud Runにサービスをデプロイ
    
    制限:
    - 許可されたサービス名のみ
    - 許可されたリージョンのみ
    - 許可されたレジストリのイメージのみ
    """
    # バリデーション
    validate_service_name(req.service_name)
    validate_region(req.region)
    validate_image(req.image)
    
    # デプロイコマンド構築
    args = [
        "run", "deploy", req.service_name,
        "--image", req.image,
        "--region", req.region,
        "--memory", req.memory,
        "--cpu", req.cpu,
        "--min-instances", str(req.min_instances),
        "--max-instances", str(req.max_instances),
        "--allow-unauthenticated",
        "--format", "json"
    ]
    
    if GCP_PROJECT:
        args.extend(["--project", GCP_PROJECT])
    
    # 環境変数を追加
    if req.env_vars:
        env_str = ",".join([f"{k}={v}" for k, v in req.env_vars.items()])
        args.extend(["--set-env-vars", env_str])
    
    # 実行
    result = run_gcloud_command(args)
    log_operation("deploy", req.service_name, "success" if result["success"] else "failed", result["duration_ms"])
    
    if not result["success"]:
        raise HTTPException(500, f"Deploy failed: {result['stderr']}")
    
    # URLを抽出
    url = None
    try:
        output = json.loads(result["stdout"])
        url = output.get("status", {}).get("url")
    except:
        pass
    
    return DeployResponse(
        status="deployed",
        service_name=req.service_name,
        url=url,
        message="Service deployed successfully",
        timestamp=datetime.now().isoformat()
    )

@app.get("/status/{service_name}", response_model=StatusResponse)
async def get_service_status(service_name: str, region: str = "asia-northeast1", authorized: bool = Depends(verify_token)):
    """サービスのステータスを取得"""
    validate_service_name(service_name)
    validate_region(region)
    
    args = [
        "run", "services", "describe", service_name,
        "--region", region,
        "--format", "json"
    ]
    
    if GCP_PROJECT:
        args.extend(["--project", GCP_PROJECT])
    
    result = run_gcloud_command(args)
    log_operation("status", service_name, "success" if result["success"] else "failed", result["duration_ms"])
    
    if not result["success"]:
        if "could not find" in result["stderr"].lower():
            return StatusResponse(
                service_name=service_name,
                status="not_found"
            )
        raise HTTPException(500, f"Failed to get status: {result['stderr']}")
    
    try:
        output = json.loads(result["stdout"])
        return StatusResponse(
            service_name=service_name,
            status="running",
            url=output.get("status", {}).get("url"),
            last_deployed=output.get("metadata", {}).get("creationTimestamp")
        )
    except:
        return StatusResponse(
            service_name=service_name,
            status="unknown"
        )

@app.get("/logs/{service_name}")
async def get_service_logs(
    service_name: str,
    lines: int = 100,
    region: str = "asia-northeast1",
    authorized: bool = Depends(verify_token)
):
    """サービスのログを取得"""
    validate_service_name(service_name)
    validate_region(region)
    
    # Cloud Loggingからログ取得
    args = [
        "logging", "read",
        f'resource.type="cloud_run_revision" AND resource.labels.service_name="{service_name}"',
        "--limit", str(min(lines, 500)),  # 最大500行
        "--format", "json"
    ]
    
    if GCP_PROJECT:
        args.extend(["--project", GCP_PROJECT])
    
    result = run_gcloud_command(args, timeout=60)
    log_operation("logs", service_name, "success" if result["success"] else "failed", result["duration_ms"])
    
    if not result["success"]:
        raise HTTPException(500, f"Failed to get logs: {result['stderr']}")
    
    try:
        logs = json.loads(result["stdout"])
        return {
            "service_name": service_name,
            "log_count": len(logs),
            "logs": logs
        }
    except:
        return {
            "service_name": service_name,
            "log_count": 0,
            "logs": [],
            "raw": result["stdout"][:1000]  # 生データを一部返す
        }

@app.post("/scale")
async def scale_service(req: ScaleRequest, region: str = "asia-northeast1", authorized: bool = Depends(verify_token)):
    """サービスのインスタンス数を変更"""
    validate_service_name(req.service_name)
    validate_region(region)
    
    args = [
        "run", "services", "update", req.service_name,
        "--region", region,
        "--min-instances", str(req.min_instances),
        "--max-instances", str(req.max_instances)
    ]
    
    if GCP_PROJECT:
        args.extend(["--project", GCP_PROJECT])
    
    result = run_gcloud_command(args)
    log_operation("scale", req.service_name, "success" if result["success"] else "failed", result["duration_ms"])
    
    if not result["success"]:
        raise HTTPException(500, f"Failed to scale: {result['stderr']}")
    
    return {
        "status": "scaled",
        "service_name": req.service_name,
        "min_instances": req.min_instances,
        "max_instances": req.max_instances
    }

@app.get("/services")
async def list_services(region: str = "asia-northeast1", authorized: bool = Depends(verify_token)):
    """デプロイ済みの許可されたサービス一覧を取得"""
    validate_region(region)
    
    args = [
        "run", "services", "list",
        "--region", region,
        "--format", "json"
    ]
    
    if GCP_PROJECT:
        args.extend(["--project", GCP_PROJECT])
    
    result = run_gcloud_command(args)
    
    if not result["success"]:
        raise HTTPException(500, f"Failed to list services: {result['stderr']}")
    
    try:
        all_services = json.loads(result["stdout"])
        # 許可されたサービスのみフィルタ
        allowed = [
            s for s in all_services 
            if s.get("metadata", {}).get("name") in ALLOWED_SERVICES
        ]
        return {
            "region": region,
            "services": allowed,
            "count": len(allowed)
        }
    except:
        return {"region": region, "services": [], "count": 0}

@app.delete("/service/{service_name}")
async def delete_service(service_name: str, region: str = "asia-northeast1", authorized: bool = Depends(verify_token)):
    """サービスを削除（危険操作 - 慎重に）"""
    validate_service_name(service_name)
    validate_region(region)
    
    args = [
        "run", "services", "delete", service_name,
        "--region", region,
        "--quiet"  # 確認なしで削除
    ]
    
    if GCP_PROJECT:
        args.extend(["--project", GCP_PROJECT])
    
    result = run_gcloud_command(args)
    log_operation("delete", service_name, "success" if result["success"] else "failed", result["duration_ms"])
    
    if not result["success"]:
        raise HTTPException(500, f"Failed to delete: {result['stderr']}")
    
    return {
        "status": "deleted",
        "service_name": service_name
    }

@app.get("/audit-log")
async def get_audit_log(limit: int = 100, authorized: bool = Depends(verify_token)):
    """操作ログを取得"""
    return {
        "total": len(operation_logs),
        "logs": operation_logs[-limit:]
    }

# ========================================
# 起動
# ========================================

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
