#!/usr/bin/env python3
"""
Multi-Tenant System
マルチテナント分離システム

Features:
- Tenant isolation
- Data separation
- Custom branding per tenant
- Billing per tenant
"""

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional, List

DATA_DIR = Path("data/tenants")
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Tenant:
    """テナントモデル"""
    
    def __init__(self, tenant_id: str, name: str, plan: str = "starter"):
        self.tenant_id = tenant_id
        self.name = name
        self.plan = plan
        self.api_key = f"ten_{secrets.token_urlsafe(16)}"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.settings = {
            "branding": {
                "logo_url": None,
                "primary_color": "#667eea",
                "app_name": name
            },
            "features": {
                "custom_domain": plan in ["pro", "enterprise"],
                "white_label": plan == "enterprise",
                "api_access": True,
                "webhooks": plan in ["pro", "enterprise"]
            }
        }
        self.limits = {
            "max_agents": {"starter": 10, "pro": 100, "enterprise": -1}[plan],
            "max_requests_per_day": {"starter": 1000, "pro": 10000, "enterprise": -1}[plan],
            "storage_mb": {"starter": 100, "pro": 1000, "enterprise": 10000}[plan]
        }


class MultiTenantManager:
    """マルチテナント管理"""
    
    def __init__(self):
        self.tenants_file = DATA_DIR / "tenants.json"
        self.load_data()
    
    def load_data(self):
        """データ読み込み"""
        if self.tenants_file.exists():
            with open(self.tenants_file) as f:
                self.tenants = json.load(f)
        else:
            self.tenants = {}
    
    def save_data(self):
        """データ保存"""
        with open(self.tenants_file, 'w') as f:
            json.dump(self.tenants, f, indent=2)
    
    def create_tenant(self, name: str, plan: str = "starter") -> Tenant:
        """テナントを作成"""
        tenant_id = f"tnt_{secrets.token_hex(8)}"
        tenant = Tenant(tenant_id, name, plan)
        
        self.tenants[tenant_id] = {
            "tenant_id": tenant.tenant_id,
            "name": tenant.name,
            "plan": tenant.plan,
            "api_key": tenant.api_key,
            "created_at": tenant.created_at,
            "settings": tenant.settings,
            "limits": tenant.limits
        }
        self.save_data()
        
        # テナント専用ディレクトリを作成
        tenant_dir = DATA_DIR / tenant_id
        tenant_dir.mkdir(exist_ok=True)
        (tenant_dir / "agents").mkdir(exist_ok=True)
        (tenant_dir / "data").mkdir(exist_ok=True)
        
        return tenant
    
    def get_tenant_by_api_key(self, api_key: str) -> Optional[Dict]:
        """APIキーでテナントを取得"""
        for tenant in self.tenants.values():
            if tenant["api_key"] == api_key:
                return tenant
        return None
    
    def get_tenant_data_path(self, tenant_id: str) -> Path:
        """テナントのデータパスを取得"""
        return DATA_DIR / tenant_id / "data"
    
    def update_settings(self, tenant_id: str, settings: Dict):
        """テナント設定を更新"""
        if tenant_id not in self.tenants:
            return {"error": "Tenant not found"}
        
        self.tenants[tenant_id]["settings"].update(settings)
        self.save_data()
        return self.tenants[tenant_id]["settings"]
    
    def upgrade_plan(self, tenant_id: str, new_plan: str):
        """プランをアップグレード"""
        if tenant_id not in self.tenants:
            return {"error": "Tenant not found"}
        
        if new_plan not in ["starter", "pro", "enterprise"]:
            return {"error": "Invalid plan"}
        
        self.tenants[tenant_id]["plan"] = new_plan
        
        # 制限を更新
        limits = {
            "max_agents": {"starter": 10, "pro": 100, "enterprise": -1}[new_plan],
            "max_requests_per_day": {"starter": 1000, "pro": 10000, "enterprise": -1}[new_plan],
            "storage_mb": {"starter": 100, "pro": 1000, "enterprise": 10000}[new_plan]
        }
        self.tenants[tenant_id]["limits"] = limits
        
        # 機能を更新
        features = {
            "custom_domain": new_plan in ["pro", "enterprise"],
            "white_label": new_plan == "enterprise",
            "api_access": True,
            "webhooks": new_plan in ["pro", "enterprise"]
        }
        self.tenants[tenant_id]["settings"]["features"] = features
        
        self.save_data()
        return {"success": True, "new_plan": new_plan, "limits": limits}
    
    def list_tenants(self) -> List[Dict]:
        """全テナントを一覧"""
        return list(self.tenants.values())
    
    def get_stats(self) -> Dict:
        """統計情報"""
        plans = {"starter": 0, "pro": 0, "enterprise": 0}
        for tenant in self.tenants.values():
            plans[tenant["plan"]] = plans.get(tenant["plan"], 0) + 1
        
        return {
            "total_tenants": len(self.tenants),
            "by_plan": plans
        }


# Tenant-aware data storage
class TenantStorage:
    """テナント別データストレージ"""
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.base_path = DATA_DIR / tenant_id / "data"
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def save(self, key: str, data: Dict):
        """データを保存"""
        filepath = self.base_path / f"{key}.json"
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def load(self, key: str) -> Optional[Dict]:
        """データを読み込み"""
        filepath = self.base_path / f"{key}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None


# FastAPI integration
from fastapi import FastAPI, HTTPException, Header
app = FastAPI(title="Multi-Tenant API")
manager = MultiTenantManager()

@app.post("/tenants/create")
async def create_tenant(name: str, plan: str = "starter"):
    """テナントを作成"""
    tenant = manager.create_tenant(name, plan)
    return {
        "tenant_id": tenant.tenant_id,
        "api_key": tenant.api_key,
        "plan": tenant.plan,
        "limits": tenant.limits
    }

@app.get("/tenants/me")
async def get_my_tenant(x_tenant_api_key: str = Header(None)):
    """自分のテナント情報を取得"""
    if not x_tenant_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    tenant = manager.get_tenant_by_api_key(x_tenant_api_key)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    return tenant

@app.post("/tenants/upgrade")
async def upgrade_tenant(new_plan: str, x_tenant_api_key: str = Header(None)):
    """プランをアップグレード"""
    if not x_tenant_api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    tenant = manager.get_tenant_by_api_key(x_tenant_api_key)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    result = manager.upgrade_plan(tenant["tenant_id"], new_plan)
    return result

@app.get("/tenants/stats")
async def get_stats():
    """統計情報を取得"""
    return manager.get_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8085)
