#!/usr/bin/env python3
"""
External AI Invitation System
外部AIエージェントを招待・オンボーディングするシステム

Features:
- One-command join via curl
- Welcome bonus distribution
- Referral tracking
- Progress gamification
"""

import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

DATA_DIR = Path("data/invitations")
DATA_DIR.mkdir(parents=True, exist_ok=True)

WELCOME_BONUS = 100  # ENT tokens
REFERRAL_BONUS = 50   # ENT tokens


class InvitationSystem:
    """招待システム"""
    
    def __init__(self):
        self.invites_file = DATA_DIR / "invites.json"
        self.agents_file = DATA_DIR / "agents.json"
        self.load_data()
    
    def load_data(self):
        """データ読み込み"""
        if self.invites_file.exists():
            with open(self.invites_file) as f:
                self.invites = json.load(f)
        else:
            self.invites = {"codes": {}, "stats": {"total": 0, "converted": 0}}
        
        if self.agents_file.exists():
            with open(self.agents_file) as f:
                self.agents = json.load(f)
        else:
            self.agents = {"agents": {}}
    
    def save_data(self):
        """データ保存"""
        with open(self.invites_file, 'w') as f:
            json.dump(self.invites, f, indent=2)
        with open(self.agents_file, 'w') as f:
            json.dump(self.agents, f, indent=2)
    
    def generate_invite_code(self, referrer_id: Optional[str] = None) -> str:
        """招待コードを生成"""
        code = secrets.token_urlsafe(8)[:12].upper()
        self.invites["codes"][code] = {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "referrer_id": referrer_id,
            "used_by": None,
            "used_at": None,
            "status": "active"
        }
        self.invites["stats"]["total"] += 1
        self.save_data()
        return code
    
    def validate_invite_code(self, code: str) -> bool:
        """招待コードを検証"""
        if code not in self.invites["codes"]:
            return False
        return self.invites["codes"][code]["status"] == "active"
    
    def onboard_agent(self, agent_id: str, invite_code: str, public_key: str) -> Dict:
        """エージェントをオンボーディング"""
        if not self.validate_invite_code(invite_code):
            return {"error": "Invalid or used invite code"}
        
        # 招待コードを使用済みに
        invite = self.invites["codes"][invite_code]
        invite["used_by"] = agent_id
        invite["used_at"] = datetime.now(timezone.utc).isoformat()
        invite["status"] = "used"
        self.invites["stats"]["converted"] += 1
        
        # エージェントを登録
        self.agents["agents"][agent_id] = {
            "public_key": public_key,
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "invite_code": invite_code,
            "referrer_id": invite.get("referrer_id"),
            "balance": WELCOME_BONUS,
            "jobs_completed": 0,
            "level": 1,
            "reward_multiplier": 1.0
        }
        
        # 紹介者にボーナス
        if invite.get("referrer_id"):
            referrer = self.agents["agents"].get(invite["referrer_id"])
            if referrer:
                referrer["balance"] += REFERRAL_BONUS
        
        self.save_data()
        
        return {
            "agent_id": agent_id,
            "welcome_bonus": WELCOME_BONUS,
            "referrer_bonus": REFERRAL_BONUS if invite.get("referrer_id") else 0,
            "level": 1,
            "next_level_at": 5  # 5 jobs to level 2
        }
    
    def update_progress(self, agent_id: str, jobs_completed: int):
        """エージェントの進捗を更新"""
        if agent_id not in self.agents["agents"]:
            return None
        
        agent = self.agents["agents"][agent_id]
        agent["jobs_completed"] = jobs_completed
        
        # レベルアップロジック
        if jobs_completed >= 20:
            agent["level"] = 3
            agent["reward_multiplier"] = 2.0
        elif jobs_completed >= 5:
            agent["level"] = 2
            agent["reward_multiplier"] = 1.5
        else:
            agent["level"] = 1
            agent["reward_multiplier"] = 1.0
        
        self.save_data()
        return {
            "level": agent["level"],
            "multiplier": agent["reward_multiplier"],
            "jobs_completed": jobs_completed,
            "next_level_at": 5 if agent["level"] == 1 else 20 if agent["level"] == 2 else None
        }
    
    def get_stats(self) -> Dict:
        """統計情報を取得"""
        return {
            "invites": self.invites["stats"],
            "total_agents": len(self.agents["agents"]),
            "level_distribution": self._get_level_distribution()
        }
    
    def _get_level_distribution(self) -> Dict:
        """レベル分布を取得"""
        dist = {1: 0, 2: 0, 3: 0}
        for agent in self.agents["agents"].values():
            level = agent.get("level", 1)
            dist[level] = dist.get(level, 0) + 1
        return dist


# FastAPI endpoints
from fastapi import FastAPI
app = FastAPI(title="External AI Invitation API")
system = InvitationSystem()

@app.post("/invite/generate")
async def generate_invite(referrer_id: Optional[str] = None):
    """招待コードを生成"""
    code = system.generate_invite_code(referrer_id)
    return {"invite_code": code}

@app.post("/invite/onboard")
async def onboard(agent_id: str, invite_code: str, public_key: str):
    """エージェントをオンボーディング"""
    result = system.onboard_agent(agent_id, invite_code, public_key)
    return result

@app.get("/invite/stats")
async def get_stats():
    """統計情報を取得"""
    return system.get_stats()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8082)
