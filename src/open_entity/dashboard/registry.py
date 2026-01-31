"""
A2A Agent Registry Dashboard

ローカルネットワークおよび公開ネットワーク上のAIエージェントを
発見・表示するダッシュボード機能。
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class RegisteredAgent:
    """登録されたエージェント情報"""
    agent_id: str
    name: str
    endpoint: str
    capabilities: List[str]
    last_seen: datetime
    is_online: bool = True
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
    
    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "endpoint": self.endpoint,
            "capabilities": self.capabilities,
            "last_seen": self.last_seen.isoformat(),
            "is_online": self.is_online,
            "metadata": self.metadata,
        }


class AgentRegistry:
    """
    AIエージェントレジストリ
    
    ローカル(mDNS)およびリモートエージェントの登録・管理を行う。
    """
    
    def __init__(self, storage_path: Optional[str] = None):
        self.agents: Dict[str, RegisteredAgent] = {}
        self.storage_path = storage_path or "data/agent_registry.json"
        self._lock = asyncio.Lock()
        self._mdns_discovery = None
        
        # 保存済みエージェントを読み込み
        self._load_registry()
    
    def _load_registry(self):
        """保存されたレジストリを読み込む"""
        path = Path(self.storage_path)
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                
                for agent_data in data.get("agents", []):
                    agent = RegisteredAgent(
                        agent_id=agent_data["agent_id"],
                        name=agent_data["name"],
                        endpoint=agent_data["endpoint"],
                        capabilities=agent_data.get("capabilities", []),
                        last_seen=datetime.fromisoformat(agent_data["last_seen"]),
                        is_online=False,  # 起動時はオフラインとしてマーク
                        metadata=agent_data.get("metadata", {}),
                    )
                    self.agents[agent.agent_id] = agent
                
                logger.info(f"Loaded {len(self.agents)} agents from registry")
            except Exception as e:
                logger.error(f"Failed to load registry: {e}")
    
    async def _save_registry(self):
        """レジストリを保存"""
        async with self._lock:
            try:
                path = Path(self.storage_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                
                data = {
                    "updated_at": datetime.now().isoformat(),
                    "agents": [agent.to_dict() for agent in self.agents.values()],
                }
                
                with open(path, 'w') as f:
                    json.dump(data, f, indent=2)
            except Exception as e:
                logger.error(f"Failed to save registry: {e}")
    
    async def register(self, agent: RegisteredAgent) -> bool:
        """エージェントを登録"""
        async with self._lock:
            self.agents[agent.agent_id] = agent
            logger.info(f"Registered agent: {agent.name} ({agent.agent_id})")
        
        await self._save_registry()
        return True
    
    async def unregister(self, agent_id: str) -> bool:
        """エージェントを登録解除"""
        async with self._lock:
            if agent_id in self.agents:
                del self.agents[agent_id]
                logger.info(f"Unregistered agent: {agent_id}")
        
        await self._save_registry()
        return True
    
    async def update_status(self, agent_id: str, is_online: bool):
        """エージェントのオンライン状態を更新"""
        async with self._lock:
            if agent_id in self.agents:
                self.agents[agent_id].is_online = is_online
                self.agents[agent_id].last_seen = datetime.now()
    
    async def discover_local_agents(self, timeout: float = 3.0) -> List[RegisteredAgent]:
        """mDNSでローカルエージェントを発見"""
        discovered = []
        
        try:
            from ..discovery.mdns import discover_local_agents, ZEROCO_AVAILABLE
            
            if not ZEROCO_AVAILABLE:
                logger.warning("zeroconf not installed, cannot discover local agents")
                return discovered
            
            local_agents = await discover_local_agents(timeout=timeout)
            
            for agent in local_agents:
                registered = RegisteredAgent(
                    agent_id=agent.agent_id,
                    name=agent.properties.get("name", agent.agent_id),
                    endpoint=agent.a2a_endpoint,
                    capabilities=agent.capabilities,
                    last_seen=datetime.now(),
                    is_online=True,
                    metadata={"source": "mdns", "addresses": agent.addresses},
                )
                discovered.append(registered)
                
                # レジストリに追加/更新
                await self.register(registered)
            
            logger.info(f"Discovered {len(discovered)} local agents via mDNS")
            
        except Exception as e:
            logger.error(f"Local discovery failed: {e}")
        
        return discovered
    
    def get_all_agents(self) -> List[RegisteredAgent]:
        """すべての登録エージェントを取得"""
        return list(self.agents.values())
    
    def get_online_agents(self) -> List[RegisteredAgent]:
        """オンラインのエージェントを取得"""
        return [a for a in self.agents.values() if a.is_online]
    
    def get_agent_by_id(self, agent_id: str) -> Optional[RegisteredAgent]:
        """IDでエージェントを取得"""
        return self.agents.get(agent_id)
    
    async def start_periodic_discovery(self, interval: float = 30.0):
        """定期的な発見を開始（バックグラウンドタスク）"""
        while True:
            try:
                await self.discover_local_agents(timeout=5.0)
            except Exception as e:
                logger.error(f"Periodic discovery error: {e}")
            
            await asyncio.sleep(interval)


# グローバルレジストリインスタンス（シングルトン）
_registry: Optional[AgentRegistry] = None


def get_registry(storage_path: Optional[str] = None) -> AgentRegistry:
    """グローバルレジストリインスタンスを取得"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry(storage_path=storage_path)
    return _registry