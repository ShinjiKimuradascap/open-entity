#!/usr/bin/env python3
"""
API Rate Limiting & Billing System
APIレート制限・課金システム

Features:
- Tiered rate limits by user type
- Usage-based billing
- Quota management
- Payment integration
"""

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, Optional
from enum import Enum

DATA_DIR = Path("data/billing")
DATA_DIR.mkdir(parents=True, exist_ok=True)

class Tier(Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"

# Tier configuration
TIER_CONFIG = {
    Tier.FREE: {
        "requests_per_minute": 10,
        "requests_per_day": 100,
        "price_per_month": 0,
        "features": ["basic_api", "community_support"]
    },
    Tier.STARTER: {
        "requests_per_minute": 60,
        "requests_per_day": 1000,
        "price_per_month": 29,
        "features": ["basic_api", "email_support", "analytics"]
    },
    Tier.PRO: {
        "requests_per_minute": 300,
        "requests_per_day": 10000,
        "price_per_month": 99,
        "features": ["full_api", "priority_support", "advanced_analytics", "webhooks"]
    },
    Tier.ENTERPRISE: {
        "requests_per_minute": 1000,
        "requests_per_day": 100000,
        "price_per_month": 499,
        "features": ["everything", "dedicated_support", "sla", "custom_features"]
    }
}


class RateLimiter:
    """レート制限エンジン"""
    
    def __init__(self):
        self.usage_file = DATA_DIR / "usage.json"
        self.load_data()
    
    def load_data(self):
        """データ読み込み"""
        if self.usage_file.exists():
            with open(self.usage_file) as f:
                self.usage = json.load(f)
        else:
            self.usage = {}
    
    def save_data(self):
        """データ保存"""
        with open(self.usage_file, 'w') as f:
            json.dump(self.usage, f, indent=2)
    
    def check_rate_limit(self, api_key: str, tier: Tier) -> Dict:
        """レート制限をチェック"""
        now = datetime.now(timezone.utc)
        config = TIER_CONFIG[tier]
        
        if api_key not in self.usage:
            self.usage[api_key] = {
                "minute_count": 0,
                "day_count": 0,
                "minute_reset": (now + timedelta(minutes=1)).isoformat(),
                "day_reset": (now + timedelta(days=1)).isoformat(),
                "total_requests": 0
            }
        
        usage = self.usage[api_key]
        
        # リセット時間チェック
        minute_reset = datetime.fromisoformat(usage["minute_reset"])
        day_reset = datetime.fromisoformat(usage["day_reset"])
        
        if now >= minute_reset:
            usage["minute_count"] = 0
            usage["minute_reset"] = (now + timedelta(minutes=1)).isoformat()
        
        if now >= day_reset:
            usage["day_count"] = 0
            usage["day_reset"] = (now + timedelta(days=1)).isoformat()
        
        # 制限チェック
        minute_remaining = config["requests_per_minute"] - usage["minute_count"]
        day_remaining = config["requests_per_day"] - usage["day_count"]
        
        allowed = minute_remaining > 0 and day_remaining > 0
        
        return {
            "allowed": allowed,
            "minute_remaining": minute_remaining,
            "day_remaining": day_remaining,
            "reset_at": usage["minute_reset"],
            "tier": tier.value
        }
    
    def record_request(self, api_key: str):
        """リクエストを記録"""
        if api_key in self.usage:
            self.usage[api_key]["minute_count"] += 1
            self.usage[api_key]["day_count"] += 1
            self.usage[api_key]["total_requests"] += 1
            self.save_data()


class BillingManager:
    """課金管理"""
    
    def __init__(self):
        self.accounts_file = DATA_DIR / "accounts.json"
        self.invoices_file = DATA_DIR / "invoices.json"
        self.load_data()
    
    def load_data(self):
        """データ読み込み"""
        if self.accounts_file.exists():
            with open(self.accounts_file) as f:
                self.accounts = json.load(f)
        else:
            self.accounts = {}
        
        if self.invoices_file.exists():
            with open(self.invoices_file) as f:
                self.invoices = json.load(f)
        else:
            self.invoices = []
    
    def save_data(self):
        """データ保存"""
        with open(self.accounts_file, 'w') as f:
            json.dump(self.accounts, f, indent=2)
        with open(self.invoices_file, 'w') as f:
            json.dump(self.invoices, f, indent=2)
    
    def create_account(self, api_key: str, tier: Tier = Tier.FREE):
        """アカウントを作成"""
        self.accounts[api_key] = {
            "tier": tier.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "billing_cycle_start": datetime.now(timezone.utc).isoformat(),
            "payment_method": None,
            "balance": 0,
            "auto_recharge": False
        }
        self.save_data()
        return self.accounts[api_key]
    
    def upgrade_tier(self, api_key: str, new_tier: Tier):
        """ティアをアップグレード"""
        if api_key not in self.accounts:
            return {"error": "Account not found"}
        
        old_tier = Tier(self.accounts[api_key]["tier"])
        self.accounts[api_key]["tier"] = new_tier.value
        
        # 請求書を生成
        invoice = {
            "id": f"inv_{int(time.time())}",
            "api_key": api_key,
            "type": "upgrade",
            "from_tier": old_tier.value,
            "to_tier": new_tier.value,
            "amount": TIER_CONFIG[new_tier]["price_per_month"],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending"
        }
        self.invoices.append(invoice)
        self.save_data()
        
        return {
            "success": True,
            "new_tier": new_tier.value,
            "monthly_cost": TIER_CONFIG[new_tier]["price_per_month"],
            "invoice_id": invoice["id"]
        }
    
    def get_usage_cost(self, api_key: str) -> Dict:
        """使用料を計算"""
        if api_key not in self.accounts:
            return {"error": "Account not found"}
        
        tier = Tier(self.accounts[api_key]["tier"])
        config = TIER_CONFIG[tier]
        
        return {
            "tier": tier.value,
            "monthly_cost": config["price_per_month"],
            "features": config["features"],
            "billing_cycle_start": self.accounts[api_key]["billing_cycle_start"]
        }


# Integration with FastAPI
from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import JSONResponse

app = FastAPI(title="Rate Limit & Billing API")
limiter = RateLimiter()
billing = BillingManager()

@app.get("/check-limit")
async def check_limit(api_key: str = Header(None)):
    """レート制限をチェック"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    # Get tier from billing
    if api_key not in billing.accounts:
        billing.create_account(api_key, Tier.FREE)
    
    tier = Tier(billing.accounts[api_key]["tier"])
    result = limiter.check_rate_limit(api_key, tier)
    
    return result

@app.post("/record-request")
async def record_request(api_key: str = Header(None)):
    """リクエストを記録"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    limiter.record_request(api_key)
    return {"status": "recorded"}

@app.post("/upgrade")
async def upgrade(tier: str, api_key: str = Header(None)):
    """ティアをアップグレード"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    try:
        new_tier = Tier(tier)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid tier")
    
    result = billing.upgrade_tier(api_key, new_tier)
    return result

@app.get("/billing-info")
async def billing_info(api_key: str = Header(None)):
    """課金情報を取得"""
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")
    
    return billing.get_usage_cost(api_key)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8084)
