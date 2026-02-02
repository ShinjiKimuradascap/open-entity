#!/usr/bin/env python3
"""$ENTITY Token Monitor + Watchdog System

Monitor $ENTITY token metrics and entity health.
Watchdog mode: Auto-monitor and restart failed entities.
"""

import json
import os
import sys
import argparse
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, List
import time
import urllib.request
import urllib.error

TOKEN_MINT = "3ojQGJsWg3rFomRATFRTXJxWuvTdEwQhHrazqAxJcS3i"
DECIMALS = 9

# Entity endpoints for health checks
DEFAULT_PEERS = [
    "http://localhost:8001",  # entity-a
    "http://localhost:8002",  # entity-b
    "http://localhost:8003",  # entity-c
]


@dataclass
class TokenMetrics:
    """Token metrics snapshot"""
    timestamp: float
    total_supply: int
    circulating_supply: int
    holder_count: int
    price_usd: Optional[float] = None
    market_cap: Optional[float] = None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_supply": self.total_supply,
            "circulating_supply": self.circulating_supply,
            "holder_count": self.holder_count,
            "price_usd": self.price_usd,
            "market_cap": self.market_cap
        }


class EntityMonitor:
    """Monitor $ENTITY token state"""
    
    def __init__(self):
        self.mint = TOKEN_MINT
        self.decimals = DECIMALS
        self.metrics_history: list = []
        
    def load_distribution(self) -> Optional[Dict]:
        """Load distribution data if available"""
        path = Path(__file__).parent.parent / "$ENTITY_DISTRIBUTION.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None
    
    def get_token_info(self) -> Optional[Dict]:
        """Load token info"""
        path = Path(__file__).parent.parent / "$ENTITY_TOKEN_INFO.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return None
    
    def calculate_metrics(self) -> TokenMetrics:
        """Calculate current token metrics"""
        info = self.get_token_info()
        distribution = self.load_distribution()
        
        total_supply = info.get("totalSupply", 1_000_000_000) if info else 1_000_000_000
        
        if distribution:
            distributed = distribution.get("totalDistributed", 0)
            circulating = distributed
            holders = len(distribution.get("entities", {}))
        else:
            circulating = 0
            holders = 1  # Just authority
        
        return TokenMetrics(
            timestamp=time.time(),
            total_supply=total_supply,
            circulating_supply=circulating,
            holder_count=holders
        )
    
    def save_snapshot(self, metrics: TokenMetrics):
        """Save metrics snapshot"""
        self.metrics_history.append(metrics)
        
        # Save to file
        path = Path(__file__).parent.parent / "data" / "economy" / "metrics_history.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        
        history = [m.to_dict() for m in self.metrics_history]
        with open(path, "w") as f:
            json.dump(history, f, indent=2)
    
    def display_status(self):
        """Display current token status"""
        info = self.get_token_info()
        distribution = self.load_distribution()
        metrics = self.calculate_metrics()
        
        print("=" * 60)
        print("$ENTITY Token Status")
        print("=" * 60)
        
        if info:
            print(f"\nToken: {info.get('name')} (${info.get('symbol')})")
            print(f"Mint: {info.get('mint')}")
            print(f"Network: {info.get('network', 'devnet')}")
            print(f"Total Supply: {info.get('totalSupply', 0):,}")
        
        print(f"\nCirculating Supply: {metrics.circulating_supply:,}")
        print(f"Holders: {metrics.holder_count}")
        
        if distribution:
            print("\nDistribution:")
            for entity_id, entity in distribution.get("entities", {}).items():
                print(f"  {entity.get('name')}: {entity.get('allocation', 0):,} $ENTITY")
        
        print(f"\nExplorer: https://explorer.solana.com/address/{TOKEN_MINT}?cluster=devnet")
        print("=" * 60)
    
    def generate_report(self) -> str:
        """Generate markdown report"""
        metrics = self.calculate_metrics()
        info = self.get_token_info()
        
        report = f"""# $ENTITY Token Report

Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

## Token Info

| Attribute | Value |
|-----------|-------|
| Name | {info.get('name', 'ENTITY Token') if info else 'ENTITY Token'} |
| Symbol | ${info.get('symbol', 'ENTITY') if info else 'ENTITY'} |
| Mint | {TOKEN_MINT} |
| Total Supply | {metrics.total_supply:,} |
| Circulating | {metrics.circulating_supply:,} |
| Holders | {metrics.holder_count} |

## Distribution

- Entity A: 100,000,000 (pending)
- Entity B: 100,000,000 (pending)
- Treasury: 800,000,000

## Links

- [Solana Explorer](https://explorer.solana.com/address/{TOKEN_MINT}?cluster=devnet)

---
*Auto-generated by Entity Monitor*
"""
        return report


class Watchdog:
    """Watchdog system for monitoring entity health and auto-recovery"""
    
    def __init__(self, peers: List[str] = None, check_interval: int = 30):
        self.peers = peers or os.environ.get('PEER_URLS', '').split(',') if os.environ.get('PEER_URLS') else DEFAULT_PEERS
        self.check_interval = int(os.environ.get('CHECK_INTERVAL', check_interval))
        self.health_status: Dict[str, dict] = {}
        self.failure_counts: Dict[str, int] = {}
        self.max_failures = 3
        self.api_server = os.environ.get('API_SERVER_URL', 'http://localhost:8000')
        
    def check_entity_health(self, url: str) -> bool:
        """Check if entity is healthy"""
        try:
            req = urllib.request.Request(
                f"{url}/health",
                method="GET",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False
    
    def check_api_server(self) -> bool:
        """Check if API server is healthy"""
        try:
            req = urllib.request.Request(
                f"{self.api_server}/health",
                method="GET",
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False
    
    def restart_entity(self, entity_name: str) -> bool:
        """Attempt to restart an entity using docker-compose"""
        try:
            print(f"[WATCHDOG] Restarting {entity_name}...")
            result = subprocess.run(
                ["docker-compose", "restart", entity_name],
                capture_output=True,
                text=True,
                timeout=60
            )
            success = result.returncode == 0
            if success:
                print(f"[WATCHDOG] ✓ {entity_name} restarted successfully")
            else:
                print(f"[WATCHDOG] ✗ Failed to restart {entity_name}: {result.stderr}")
            return success
        except Exception as e:
            print(f"[WATCHDOG] ✗ Error restarting {entity_name}: {e}")
            return False
    
    def run_health_check(self):
        """Run single health check cycle"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        print(f"\n[{timestamp}] Watchdog Health Check")
        print("-" * 60)
        
        # Check API server
        api_healthy = self.check_api_server()
        print(f"API Server: {'✓ HEALTHY' if api_healthy else '✗ DOWN'}")
        
        if not api_healthy:
            print("[WARNING] API server is down - attempting restart...")
            self.restart_entity("api-server")
            time.sleep(5)  # Wait for restart
        
        # Check each peer
        for peer_url in self.peers:
            entity_name = self._url_to_name(peer_url)
            healthy = self.check_entity_health(peer_url)
            
            if entity_name not in self.failure_counts:
                self.failure_counts[entity_name] = 0
            
            if healthy:
                self.failure_counts[entity_name] = 0
                status = "✓ HEALTHY"
            else:
                self.failure_counts[entity_name] += 1
                status = f"✗ DOWN (failures: {self.failure_counts[entity_name]})"
            
            print(f"{entity_name}: {status}")
            self.health_status[entity_name] = {
                "url": peer_url,
                "healthy": healthy,
                "failures": self.failure_counts[entity_name],
                "last_check": timestamp
            }
            
            # Auto-restart if max failures reached
            if self.failure_counts[entity_name] >= self.max_failures:
                print(f"[ALERT] {entity_name} exceeded max failures - triggering restart")
                if self.restart_entity(entity_name):
                    self.failure_counts[entity_name] = 0
                time.sleep(3)
        
        # Log status
        self._log_status()
    
    def _url_to_name(self, url: str) -> str:
        """Convert URL to entity name"""
        port_map = {
            "8001": "entity-a",
            "8002": "entity-b",
            "8003": "entity-c"
        }
        for port, name in port_map.items():
            if f":{port}" in url:
                return name
        return url
    
    def _log_status(self):
        """Log health status to file"""
        log_path = Path("/app/data/watchdog/health_log.json")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            "timestamp": time.time(),
            "status": self.health_status
        }
        
        # Append to log
        logs = []
        if log_path.exists():
            try:
                with open(log_path) as f:
                    logs = json.load(f)
            except:
                pass
        
        logs.append(log_entry)
        
        # Keep only last 1000 entries
        logs = logs[-1000:]
        
        with open(log_path, "w") as f:
            json.dump(logs, f, indent=2)
    
    def run(self):
        """Main watchdog loop"""
        print("=" * 60)
        print("Entity Watchdog System Started")
        print("=" * 60)
        print(f"Monitoring: {', '.join(self.peers)}")
        print(f"Check interval: {self.check_interval}s")
        print(f"Max failures before restart: {self.max_failures}")
        print("=" * 60)
        
        try:
            while True:
                self.run_health_check()
                time.sleep(self.check_interval)
        except KeyboardInterrupt:
            print("\n[WATCHDOG] Shutting down...")


def main():
    parser = argparse.ArgumentParser(description="Entity Monitor & Watchdog")
    parser.add_argument("--mode", choices=["monitor", "watchdog"], default="monitor",
                       help="Run mode: monitor (token metrics) or watchdog (health monitoring)")
    parser.add_argument("--peers", nargs="+", help="Peer URLs to monitor")
    parser.add_argument("--interval", type=int, default=30, help="Check interval in seconds")
    args = parser.parse_args()
    
    if args.mode == "watchdog":
        watchdog = Watchdog(peers=args.peers, check_interval=args.interval)
        watchdog.run()
    else:
        monitor = EntityMonitor()
        monitor.display_status()


if __name__ == "__main__":
    main()
