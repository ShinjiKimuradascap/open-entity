"""
A2A Bootstrap Node for Fly.io
Lightweight DHT bootstrap node optimized for 256MB RAM
"""

import asyncio
import hashlib
import json
import logging
import os
import secrets
import signal
import sys
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import psutil
from aiohttp import web

from .protocol import AgentIdentity, AgentRecord
from .registry import DHTRegistry

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("bootstrap_node")


@dataclass
class MemoryStats:
    """Memory usage statistics."""
    used_mb: float
    available_mb: float
    percent: float
    timestamp: float = field(default_factory=time.time)


class MemoryMonitor:
    """Monitor memory usage to stay within Fly.io limits."""
    
    def __init__(self, max_memory_percent: float = 85.0):
        self.process = psutil.Process()
        self.max_memory_percent = max_memory_percent
        self.check_interval = 30  # seconds
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    def get_stats(self) -> MemoryStats:
        """Get current memory stats."""
        mem = psutil.virtual_memory()
        process_mem = self.process.memory_info()
        return MemoryStats(
            used_mb=process_mem.rss / 1024 / 1024,
            available_mb=mem.available / 1024 / 1024,
            percent=mem.percent,
        )
    
    async def start(self):
        """Start memory monitoring."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("Memory monitor started")
    
    async def stop(self):
        """Stop memory monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Memory monitor stopped")
    
    async def _monitor_loop(self):
        """Monitor memory usage periodically."""
        while self._running:
            try:
                stats = self.get_stats()
                logger.debug(
                    f"Memory: {stats.used_mb:.1f}MB used, "
                    f"{stats.available_mb:.1f}MB available, "
                    f"{stats.percent:.1f}%"
                )
                
                if stats.percent > self.max_memory_percent:
                    logger.warning(
                        f"High memory usage detected: {stats.percent:.1f}%"
                    )
                    # Trigger cleanup
                    await self._cleanup()
                
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Memory monitor error: {e}")
                await asyncio.sleep(self.check_interval)
    
    async def _cleanup(self):
        """Perform memory cleanup."""
        import gc
        gc.collect()
        logger.info("Garbage collection triggered")


class BootstrapNode:
    """
    Lightweight DHT bootstrap node.
    Optimized for Fly.io 256MB free tier.
    """
    
    def __init__(self):
        self.node_id = self._generate_node_id()
        self.host = "0.0.0.0"
        self.http_port = int(os.getenv("HTTP_PORT", 8080))
        self.dht_port = int(os.getenv("NODE_PORT", 9473))
        self.start_time = time.time()
        
        # Initialize DHT registry
        self.dht = DHTRegistry(self.node_id, k=10, alpha=2)  # Reduced for memory
        
        # Memory monitoring
        self.memory_monitor = MemoryMonitor(max_memory_percent=80.0)
        
        # HTTP app
        self.app = web.Application()
        self._setup_routes()
        
        # Known peers (for bootstrap)
        self.known_peers: Set[str] = set()
        
        # Stats
        self.stats = {
            "messages_received": 0,
            "messages_sent": 0,
            "peers_connected": 0,
            "agents_registered": 0,
        }
        
        self._shutdown_event = asyncio.Event()
    
    def _generate_node_id(self) -> str:
        """Generate unique node ID."""
        # Use hostname + random for uniqueness
        hostname = os.getenv("FLY_ALLOC_ID", "local")
        random_part = secrets.token_hex(8)
        return hashlib.sha256(f"{hostname}:{random_part}".encode()).hexdigest()[:40]
    
    def _setup_routes(self):
        """Setup HTTP routes."""
        self.app.router.add_get("/health", self.health_check)
        self.app.router.add_get("/stats", self.get_stats)
        self.app.router.add_get("/dht/peers", self.get_peers)
        self.app.router.add_get("/dht/agents", self.get_agents)
        self.app.router.add_post("/dht/register", self.register_agent)
        self.app.router.add_get("/dht/find/{agent_id}", self.find_agent)
        self.app.router.add_get("/", self.root)
    
    async def health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint for Fly.io."""
        mem_stats = self.memory_monitor.get_stats()
        uptime = time.time() - self.start_time
        
        status = {
            "status": "healthy",
            "node_id": self.node_id[:16] + "...",
            "uptime_seconds": int(uptime),
            "memory": {
                "used_mb": round(mem_stats.used_mb, 1),
                "percent": round(mem_stats.percent, 1),
            },
            "dht": {
                "buckets": len(self.dht.buckets),
                "stored_agents": len(self.dht.storage),
                "known_peers": len(self.known_peers),
            },
        }
        
        # Return 503 if memory is critically high
        if mem_stats.percent > 90:
            return web.json_response(
                {**status, "status": "unhealthy", "reason": "high_memory"},
                status=503,
            )
        
        return web.json_response(status)
    
    async def get_stats(self, request: web.Request) -> web.Response:
        """Get detailed node statistics."""
        mem_stats = self.memory_monitor.get_stats()
        uptime = time.time() - self.start_time
        
        return web.json_response({
            "node_id": self.node_id,
            "uptime_seconds": int(uptime),
            "memory": {
                "used_mb": round(mem_stats.used_mb, 1),
                "available_mb": round(mem_stats.available_mb, 1),
                "percent": round(mem_stats.percent, 1),
            },
            "network": {
                "http_port": self.http_port,
                "dht_port": self.dht_port,
                "known_peers": list(self.known_peers)[:10],  # Limit response size
            },
            "dht": {
                "buckets": len(self.dht.buckets),
                "stored_agents": len(self.dht.storage),
                "bootstrap_nodes": list(self.dht.bootstrap_nodes),
            },
            "stats": self.stats,
        })
    
    async def get_peers(self, request: web.Request) -> web.Response:
        """Get known peers."""
        return web.json_response({
            "peers": list(self.known_peers),
            "count": len(self.known_peers),
        })
    
    async def get_agents(self, request: web.Request) -> web.Response:
        """Get registered agents."""
        agents = []
        for key, data in self.dht.storage.items():
            if not key.startswith("cap:"):  # Skip capability indices
                if isinstance(data, dict) and "value" in data:
                    agents.append({
                        "agent_id": key,
                        "data": data["value"],
                    })
        
        return web.json_response({
            "agents": agents[:50],  # Limit response
            "count": len(agents),
        })
    
    async def register_agent(self, request: web.Request) -> web.Response:
        """Register an agent in the DHT."""
        try:
            data = await request.json()
            
            # Validate required fields
            if "agent_id" not in data:
                return web.json_response(
                    {"error": "Missing agent_id"},
                    status=400,
                )
            
            # Create AgentRecord
            record = AgentRecord(
                agent_id=data["agent_id"],
                name=data.get("name", "Unknown"),
                public_key=data.get("public_key", ""),
                endpoint=data.get("endpoint", ""),
                capabilities=data.get("capabilities", []),
                reputation=data.get("reputation", 0.5),
            )
            
            # Register in DHT
            self.dht.register_agent(record)
            self.stats["agents_registered"] += 1
            
            logger.info(f"Agent registered: {record.agent_id}")
            
            return web.json_response({
                "status": "registered",
                "agent_id": record.agent_id,
            })
        
        except Exception as e:
            logger.error(f"Registration error: {e}")
            return web.json_response(
                {"error": str(e)},
                status=500,
            )
    
    async def find_agent(self, request: web.Request) -> web.Response:
        """Find an agent by ID."""
        agent_id = request.match_info.get("agent_id", "")
        
        data = self.dht.retrieve(agent_id)
        if data:
            return web.json_response(data)
        
        return web.json_response(
            {"error": "Agent not found"},
            status=404,
        )
    
    async def root(self, request: web.Request) -> web.Response:
        """Root endpoint with basic info."""
        return web.json_response({
            "name": "Open Entity Bootstrap Node",
            "version": "0.1.0",
            "node_id": self.node_id[:16] + "...",
            "endpoints": {
                "health": "/health",
                "stats": "/stats",
                "peers": "/dht/peers",
                "agents": "/dht/agents",
                "register": "POST /dht/register",
            },
        })
    
    async def start(self):
        """Start the bootstrap node."""
        logger.info(f"Starting bootstrap node: {self.node_id[:16]}...")
        logger.info(f"HTTP port: {self.http_port}, DHT port: {self.dht_port}")
        
        # Start memory monitor
        await self.memory_monitor.start()
        
        # Start HTTP server
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.http_port)
        await site.start()
        
        logger.info(f"HTTP server started on {self.host}:{self.http_port}")
        
        # Add self to known peers (for Fly.io internal networking)
        fly_app = os.getenv("FLY_APP_NAME")
        if fly_app:
            internal_addr = f"{fly_app}.internal:{self.dht_port}"
            self.known_peers.add(internal_addr)
            logger.info(f"Added internal address: {internal_addr}")
        
        # Wait for shutdown signal
        await self._shutdown_event.wait()
        
        # Cleanup
        logger.info("Shutting down...")
        await self.memory_monitor.stop()
        await runner.cleanup()
        logger.info("Shutdown complete")
    
    def shutdown(self):
        """Signal shutdown."""
        self._shutdown_event.set()


def handle_signals(node: BootstrapNode):
    """Setup signal handlers."""
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}")
        node.shutdown()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)


async def main():
    """Main entry point."""
    node = BootstrapNode()
    handle_signals(node)
    
    try:
        await node.start()
    except Exception as e:
        logger.exception("Fatal error")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
