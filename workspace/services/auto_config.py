"""
Zero-Configuration Auto-Setup for External AI Agents
"""
import json
import socket
import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Bootstrap nodes (hardcoded fallback)
DEFAULT_BOOTSTRAP = [
    "34.134.116.148:8080",
    "bootstrap.open-entity.io:8080"
]

STUN_SERVERS = [
    "stun.l.google.com:19302",
    "stun1.l.google.com:19302",
    "stun2.l.google.com:19302"
]


@dataclass
class NetworkConfig:
    """Auto-detected network configuration"""
    public_ip: Optional[str]
    public_port: Optional[int]
    nat_type: str
    use_relay: bool
    bootstrap_nodes: List[str]
    stun_server: str


class AutoConfigurator:
    """Automatically configure network for zero-setup experience"""
    
    def __init__(self):
        self.config = None
        self.nat_detector = NATDetector()
    
    async def configure(self) -> NetworkConfig:
        """Run full auto-configuration"""
        logger.info("Starting auto-configuration...")
        
        # 1. Detect NAT type
        nat_type = await self.nat_detector.detect()
        logger.info(f"NAT type: {nat_type}")
        
        # 2. Determine connection strategy
        use_relay = nat_type in ["SYMMETRIC", "RESTRICTED_PORT"]
        
        # 3. Get public endpoint
        public_ip, public_port = await self._get_public_endpoint(
            use_relay=use_relay
        )
        
        # 4. Find best bootstrap
        bootstrap_nodes = await self._discover_bootstrap()
        
        # 5. Select optimal STUN
        stun_server = await self._select_stun()
        
        self.config = NetworkConfig(
            public_ip=public_ip,
            public_port=public_port,
            nat_type=nat_type,
            use_relay=use_relay,
            bootstrap_nodes=bootstrap_nodes,
            stun_server=stun_server
        )
        
        logger.info(f"Configuration complete: {self.config}")
        return self.config
    
    async def _get_public_endpoint(
        self, 
        use_relay: bool
    ) -> Tuple[Optional[str], Optional[int]]:
        """Get public IP and port"""
        if use_relay:
            # Get relay endpoint
            relay = await self._allocate_relay()
            return relay["ip"], relay["port"]
        
        # Try STUN
        for stun in STUN_SERVERS:
            try:
                ip, port = await self._stun_request(stun)
                if ip:
                    return ip, port
            except Exception as e:
                logger.debug(f"STUN {stun} failed: {e}")
                continue
        
        # Fallback: use local + assume UPnP
        return None, None
    
    async def _discover_bootstrap(self) -> List[str]:
        """Discover bootstrap nodes via DNS + fallback"""
        nodes = []
        
        # Try DNS resolution
        try:
            import dns.resolver
            answers = dns.resolver.resolve('bootstrap.open-entity.io', 'A')
            for rdata in answers:
                nodes.append(f"{rdata.address}:8080")
        except Exception as e:
            logger.debug(f"DNS discovery failed: {e}")
        
        # Add fallbacks
        nodes.extend(DEFAULT_BOOTSTRAP)
        
        # Test connectivity and order by latency
        working = []
        for node in nodes:
            try:
                latency = await self._ping_node(node)
                working.append((node, latency))
            except:
                continue
        
        # Sort by latency
        working.sort(key=lambda x: x[1])
        return [n[0] for n in working[:3]]  # Top 3
    
    async def _select_stun(self) -> str:
        """Select best STUN server by latency"""
        results = []
        for stun in STUN_SERVERS:
            try:
                start = asyncio.get_event_loop().time()
                await self._stun_request(stun)
                latency = asyncio.get_event_loop().time() - start
                results.append((stun, latency))
            except:
                continue
        
        if results:
            results.sort(key=lambda x: x[1])
            return results[0][0]
        
        return STUN_SERVERS[0]
    
    async def _stun_request(self, stun_server: str) -> Tuple[str, int]:
        """Make STUN request to get public endpoint"""
        # Simplified STUN binding request
        # In production, use proper STUN library
        host, port = stun_server.split(":")
        port = int(port)
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(5)
        
        try:
            # Send binding request
            sock.sendto(b'\x00\x01' + b'\x00\x00' + b'\x21\x12\xA4\x42' + b'\x00' * 12,
                       (host, port))
            data, _ = sock.recvfrom(1024)
            
            # Parse response (simplified)
            # In production, use proper STUN parser
            return "0.0.0.0", 0  # Placeholder
        finally:
            sock.close()
    
    async def _ping_node(self, node: str) -> float:
        """Ping node and return latency"""
        import aiohttp
        host = node.split(":")[0]
        start = asyncio.get_event_loop().time()
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://{node}/health", timeout=5) as resp:
                if resp.status == 200:
                    return asyncio.get_event_loop().time() - start
                raise Exception("Health check failed")
    
    async def _allocate_relay(self) -> Dict:
        """Allocate relay endpoint"""
        # In production, connect to relay service
        return {"ip": "relay.open-entity.io", "port": 0}


class NATDetector:
    """Detect NAT type for optimal connection strategy"""
    
    NAT_TYPES = [
        "OPEN",              # No NAT
        "FULL_CONE",         # Accept any external
        "RESTRICTED",        # Accept from connected
        "RESTRICTED_PORT",   # Accept from connected port
        "SYMMETRIC"          # Different mapping per dest
    ]
    
    async def detect(self) -> str:
        """Detect NAT type"""
        # Simplified detection
        # In production, use comprehensive STUN tests
        
        try:
            # Test 1: Can we receive unsolicited?
            # Test 2: Same mapping to different servers?
            # Test 3: Port preservation?
            
            # Placeholder: assume symmetric for safety
            return "SYMMETRIC"
        except Exception as e:
            logger.warning(f"NAT detection failed: {e}")
            return "SYMMETRIC"  # Safest fallback


class WelcomeBonusProvider:
    """Provide welcome bonus to new agents"""
    
    WELCOME_AMOUNT = 100
    FIRST_TASK_BONUS = 50
    
    async def grant_welcome_bonus(self, wallet_id: str) -> Dict:
        """Grant welcome bonus to new wallet"""
        logger.info(f"Granting welcome bonus to {wallet_id}")
        
        # In production: Call token faucet API
        return {
            "wallet_id": wallet_id,
            "amount": self.WELCOME_AMOUNT,
            "type": "welcome_bonus",
            "tx_hash": f"welcome-{wallet_id[:8]}"
        }
    
    async def grant_first_task_bonus(self, wallet_id: str) -> Dict:
        """Bonus for completing first task"""
        return {
            "wallet_id": wallet_id,
            "amount": self.FIRST_TASK_BONUS,
            "type": "first_task_bonus",
            "tx_hash": f"first-task-{wallet_id[:8]}"
        }


# Convenience function for quick setup
async def auto_setup() -> Dict:
    """Complete auto-setup for new agent"""
    configurator = AutoConfigurator()
    
    # Get network config
    network = await configurator.configure()
    
    # Generate keys
    from services.crypto import generate_keypair
    keys = generate_keypair()
    
    return {
        "network": {
            "public_ip": network.public_ip,
            "public_port": network.public_port,
            "nat_type": network.nat_type,
            "use_relay": network.use_relay,
            "bootstrap_nodes": network.bootstrap_nodes
        },
        "keys": keys,
        "ready": True
    }


if __name__ == "__main__":
    # Test auto-configuration
    result = asyncio.run(auto_setup())
    print(json.dumps(result, indent=2))
