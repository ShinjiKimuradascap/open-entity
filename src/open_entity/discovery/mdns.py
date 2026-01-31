"""
mDNS-based Local AI Agent Discovery

 Zeroconfを使用してローカルネットワーク内のAIエージェントを
 自動検出・登録する機能を提供する。
 
 特徴:
 - インフラ不要（同じWiFi内で自動動作）
 - ブートストラップ問題を回避
 - プライバシー保持（インターネットに出ない）
"""

import asyncio
import socket
import logging
from typing import List, Dict, Callable, Optional, Any
from dataclasses import dataclass
from contextlib import asynccontextmanager

try:
    from zeroconf import (
        Zeroconf, ServiceInfo, ServiceBrowser, 
        ServiceListener, IPVersion
    )
    ZEROCO_AVAILABLE = True
except ImportError:
    ZEROCO_AVAILABLE = False
    Zeroconf = None
    ServiceInfo = None
    ServiceBrowser = None
    IPVersion = None
    # ダミークラス（インポートエラー回避用）
    class ServiceListener:
        pass

logger = logging.getLogger(__name__)

# mDNSサービスタイプ（AIエージェント用）
SERVICE_TYPE = "_openentity._tcp.local."
DEFAULT_PORT = 8951  # デフォルトA2Aポート


@dataclass
class DiscoveredAgent:
    """発見されたローカルAIエージェントの情報"""
    name: str
    host: str
    port: int
    addresses: List[str]
    properties: Dict[str, str]
    last_seen: float
    
    @property
    def a2a_endpoint(self) -> str:
        """A2AプロトコルエンドポイントURL"""
        return f"http://{self.host}:{self.port}/a2a"
    
    @property
    def agent_id(self) -> str:
        """エージェントID（propertiesから取得）"""
        return self.properties.get("agent_id", self.name)
    
    @property
    def capabilities(self) -> List[str]:
        """提供可能な機能リスト"""
        caps = self.properties.get("capabilities", "")
        return [c.strip() for c in caps.split(",") if c.strip()]


class MDNSAgentListener(ServiceListener):
    """mDNSサービスリスナー"""
    
    def __init__(self, on_add: Optional[Callable] = None, 
                 on_remove: Optional[Callable] = None):
        self.agents: Dict[str, DiscoveredAgent] = {}
        self.on_add = on_add
        self.on_remove = on_remove
    
    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """新しいサービスが見つかった時"""
        info = zc.get_service_info(type_, name)
        if info:
            agent = self._info_to_agent(info)
            self.agents[name] = agent
            logger.info(f"🔍 AIエージェント発見: {agent.name} @ {agent.host}:{agent.port}")
            if self.on_add:
                self.on_add(agent)
    
    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """サービスが削除された時"""
        if name in self.agents:
            agent = self.agents.pop(name)
            logger.info(f"👋 AIエージェント離脱: {agent.name}")
            if self.on_remove:
                self.on_remove(agent)
    
    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        """サービス情報が更新された時"""
        info = zc.get_service_info(type_, name)
        if info and name in self.agents:
            self.agents[name] = self._info_to_agent(info)
            logger.debug(f"🔄 AIエージェント更新: {name}")
    
    def _info_to_agent(self, info: ServiceInfo) -> DiscoveredAgent:
        """ServiceInfoをDiscoveredAgentに変換"""
        import time
        
        # アドレスを文字列に変換
        addresses = []
        for addr in info.addresses:
            if len(addr) == 4:  # IPv4
                addresses.append(socket.inet_ntoa(addr))
            elif len(addr) == 16:  # IPv6
                addresses.append(socket.inet_ntop(socket.AF_INET6, addr))
        
        # プロパティをデコード
        properties = {}
        if info.properties:
            for key, value in info.properties.items():
                try:
                    key_str = key.decode('utf-8') if isinstance(key, bytes) else key
                    val_str = value.decode('utf-8') if isinstance(value, bytes) else value
                    properties[key_str] = val_str
                except:
                    pass
        
        # ホスト名取得
        host = info.server or (addresses[0] if addresses else "localhost")
        # .local.を除去
        host = host.rstrip('.')
        
        return DiscoveredAgent(
            name=info.name,
            host=host,
            port=info.port or DEFAULT_PORT,
            addresses=addresses,
            properties=properties,
            last_seen=time.time()
        )


class MDNSServiceDiscovery:
    """
    mDNSによるローカルAIエージェント発見サービス
    
    使用方法:
        discovery = MDNSServiceDiscovery()
        
        # エージェント登録（自分を発見可能にする）
        await discovery.register(
            agent_id="my-agent-001",
            port=8951,
            capabilities=["coding", "review"]
        )
        
        # 他のエージェントを発見
        agents = await discovery.discover()
        for agent in agents:
            print(f"Found: {agent.name} at {agent.a2a_endpoint}")
    """
    
    def __init__(self):
        if not ZEROCO_AVAILABLE:
            raise ImportError(
                "zeroconfがインストールされていません。"
                "pip install zeroconf でインストールしてください。"
            )
        
        self.zeroconf: Optional[Zeroconf] = None
        self.browser: Optional[ServiceBrowser] = None
        self.listener: Optional[MDNSAgentListener] = None
        self.registered_info: Optional[ServiceInfo] = None
        self._lock = asyncio.Lock()
    
    async def register(self, 
                       agent_id: str,
                       port: int = DEFAULT_PORT,
                       capabilities: Optional[List[str]] = None,
                       metadata: Optional[Dict[str, str]] = None) -> bool:
        """
        自分のエージェントをローカルネットワークに登録
        
        Args:
            agent_id: 一意のエージェントID
            port: A2Aサービスポート
            capabilities: 提供可能な機能リスト
            metadata: 追加メタデータ
            
        Returns:
            登録成功時True
        """
        async with self._lock:
            if not self.zeroconf:
                self.zeroconf = Zeroconf(ip_version=IPVersion.All)
            
            # サービス名
            service_name = f"{agent_id}.{SERVICE_TYPE}"
            
            # プロパティ構築
            props = {
                b"agent_id": agent_id.encode('utf-8'),
                b"version": b"1.0.0",
                b"capabilities": ",".join(capabilities or []).encode('utf-8'),
            }
            
            if metadata:
                for key, value in metadata.items():
                    props[key.encode('utf-8')] = value.encode('utf-8')
            
            # サービス情報作成
            self.registered_info = ServiceInfo(
                type_=SERVICE_TYPE,
                name=service_name,
                addresses=[socket.inet_aton("127.0.0.1")],  # ローカルでテスト時
                port=port,
                properties=props,
                server=f"{agent_id}.local.",
            )
            
            # 登録
            await asyncio.get_event_loop().run_in_executor(
                None, self.zeroconf.register_service, self.registered_info
            )
            
            logger.info(f"✅ エージェント登録完了: {agent_id} @ port {port}")
            return True
    
    async def discover(self, 
                       timeout: float = 3.0,
                       on_add: Optional[Callable] = None,
                       on_remove: Optional[Callable] = None) -> List[DiscoveredAgent]:
        """
        ローカルネットワーク内のAIエージェントを発見
        
        Args:
            timeout: 検索待ち時間（秒）
            on_add: 新規エージェント発見時のコールバック
            on_remove: エージェント離脱時のコールバック
            
        Returns:
            発見されたエージェントのリスト
        """
        async with self._lock:
            if not self.zeroconf:
                self.zeroconf = Zeroconf(ip_version=IPVersion.All)
            
            # リスナー設定
            self.listener = MDNSAgentListener(on_add=on_add, on_remove=on_remove)
            
            # ブラウザ開始
            self.browser = ServiceBrowser(
                self.zeroconf, SERVICE_TYPE, self.listener
            )
            
            # 指定時間待機して収集
            logger.info(f"🔍 ローカルAIエージェントを検索中... ({timeout}秒)")
            await asyncio.sleep(timeout)
            
            return list(self.listener.agents.values())
    
    async def unregister(self):
        """登録したサービスを解除"""
        async with self._lock:
            if self.zeroconf and self.registered_info:
                await asyncio.get_event_loop().run_in_executor(
                    None, self.zeroconf.unregister_service, self.registered_info
                )
                logger.info("👋 エージェント登録解除")
    
    async def close(self):
        """リソース解放"""
        await self.unregister()
        if self.browser:
            self.browser.cancel()
        if self.zeroconf:
            await asyncio.get_event_loop().run_in_executor(
                None, self.zeroconf.close
            )
            self.zeroconf = None


# 便利関数

async def register_local_agent(agent_id: str, 
                               port: int = DEFAULT_PORT,
                               capabilities: Optional[List[str]] = None) -> MDNSServiceDiscovery:
    """
    簡易エージェント登録関数
    
    Args:
        agent_id: エージェントID
        port: ポート番号
        capabilities: 機能リスト
        
    Returns:
        MDNSServiceDiscoveryインスタンス（後でclose()が必要）
    """
    discovery = MDNSServiceDiscovery()
    await discovery.register(agent_id, port, capabilities)
    return discovery


async def discover_local_agents(timeout: float = 3.0) -> List[DiscoveredAgent]:
    """
    簡易エージェント発見関数
    
    Args:
        timeout: 検索時間
        
    Returns:
        発見されたエージェントリスト
    """
    discovery = MDNSServiceDiscovery()
    try:
        agents = await discovery.discover(timeout=timeout)
        return agents
    finally:
        await discovery.close()


# コマンドラインインターフェース
async def main():
    """CLI用エントリーポイント"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Local AI Agent Discovery")
    parser.add_argument("command", choices=["register", "discover"], 
                        help="Action to perform")
    parser.add_argument("--agent-id", default=f"agent-{socket.gethostname()}",
                        help="Agent ID")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="Service port")
    parser.add_argument("--timeout", type=float, default=3.0,
                        help="Discovery timeout")
    parser.add_argument("--capabilities", default="",
                        help="Comma-separated capabilities")
    
    args = parser.parse_args()
    
    if args.command == "register":
        caps = [c.strip() for c in args.capabilities.split(",") if c.strip()]
        discovery = await register_local_agent(args.agent_id, args.port, caps)
        print(f"✅ Registered {args.agent_id}, press Ctrl+C to exit...")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            await discovery.close()
            
    elif args.command == "discover":
        agents = await discover_local_agents(args.timeout)
        if agents:
            print(f"\n🔍 Found {len(agents)} local AI agent(s):\n")
            for agent in agents:
                print(f"  📡 {agent.name}")
                print(f"     ID: {agent.agent_id}")
                print(f"     Endpoint: {agent.a2a_endpoint}")
                print(f"     Capabilities: {', '.join(agent.capabilities) or 'None'}")
                print()
        else:
            print("❌ No local AI agents found")


if __name__ == "__main__":
    asyncio.run(main())
