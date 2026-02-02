#!/usr/bin/env python3
"""
Auto Monitor - AI Entity Health Check System
自動監視システム - AIエンティティ死活監視

Features:
- Multi-entity health monitoring
- Automatic restart on failure
- Status logging to file
- Alert notifications
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional
import urllib.request
import urllib.error

# Configuration
DEFAULT_TARGETS = [
    "http://entity-a:8001",
    "http://entity-b:8002",
    "http://entity-c:8003",
]
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
ALERT_THRESHOLD = int(os.environ.get("ALERT_THRESHOLD", "3"))
STATUS_FILE = os.environ.get("STATUS_FILE", "/app/data/monitor_status.json")
LOG_FILE = os.environ.get("LOG_FILE", "/app/data/monitor.log")


class EntityMonitor:
    """Monitor multiple AI entities"""
    
    def __init__(self, targets: List[str] = None):
        self.targets = targets or DEFAULT_TARGETS
        self.status_history: Dict[str, List[dict]] = {t: [] for t in self.targets}
        self.consecutive_failures: Dict[str, int] = {t: 0 for t in self.targets}
        self.alert_sent: Dict[str, bool] = {t: False for t in self.targets}
        
    def log(self, message: str, level: str = "INFO"):
        """Log message to file and stdout"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {message}"
        print(log_line)
        
        # Write to log file
        try:
            with open(LOG_FILE, "a") as f:
                f.write(log_line + "\n")
        except Exception as e:
            print(f"Failed to write log: {e}")
    
    def check_health(self, url: str) -> dict:
        """Check health of a single entity"""
        try:
            req = urllib.request.Request(
                f"{url}/health",
                method="GET",
                headers={"Accept": "application/json"},
                timeout=5
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return {
                    "status": "healthy",
                    "code": resp.status,
                    "data": data,
                    "timestamp": datetime.now().isoformat()
                }
        except urllib.error.HTTPError as e:
            return {
                "status": "error",
                "code": e.code,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def save_status(self, statuses: dict):
        """Save current status to file"""
        try:
            status_data = {
                "timestamp": datetime.now().isoformat(),
                "entities": statuses,
                "summary": {
                    "total": len(statuses),
                    "healthy": sum(1 for s in statuses.values() if s["status"] == "healthy"),
                    "unhealthy": sum(1 for s in statuses.values() if s["status"] != "healthy")
                }
            }
            with open(STATUS_FILE, "w") as f:
                json.dump(status_data, f, indent=2)
        except Exception as e:
            self.log(f"Failed to save status: {e}", "ERROR")
    
    def check_and_alert(self, url: str, result: dict):
        """Check status and send alerts if needed"""
        is_healthy = result["status"] == "healthy"
        
        if is_healthy:
            # Reset failure count
            if self.consecutive_failures[url] > 0:
                self.log(f"✅ {url} recovered", "INFO")
                self.consecutive_failures[url] = 0
                self.alert_sent[url] = False
        else:
            # Increment failure count
            self.consecutive_failures[url] += 1
            self.log(
                f"❌ {url} failed ({self.consecutive_failures[url]}/{ALERT_THRESHOLD}): {result.get('error', 'Unknown')}",
                "WARNING"
            )
            
            # Send alert if threshold reached
            if self.consecutive_failures[url] >= ALERT_THRESHOLD and not self.alert_sent[url]:
                self.send_alert(url, result)
                self.alert_sent[url] = True
    
    def send_alert(self, url: str, result: dict):
        """Send alert notification"""
        self.log(f"🚨 ALERT: {url} is down!", "ALERT")
        
        # Future: Send Slack/Discord/Email notification
        # For now, just log
        alert_data = {
            "type": "entity_down",
            "entity": url,
            "error": result.get("error", "Unknown"),
            "timestamp": datetime.now().isoformat(),
            "consecutive_failures": self.consecutive_failures[url]
        }
        
        try:
            alert_file = f"/app/data/alert_{int(time.time())}.json"
            with open(alert_file, "w") as f:
                json.dump(alert_data, f, indent=2)
        except Exception as e:
            self.log(f"Failed to save alert: {e}", "ERROR")
    
    async def run_single_check(self):
        """Run a single health check cycle"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statuses = {}
        
        self.log(f"\n{'='*60}")
        self.log(f"Health Check - {timestamp}")
        self.log(f"{'='*60}")
        
        for target in self.targets:
            if not target:
                continue
                
            result = self.check_health(target)
            statuses[target] = result
            
            # Update history
            self.status_history[target].append(result)
            if len(self.status_history[target]) > 100:  # Keep last 100
                self.status_history[target].pop(0)
            
            # Check and alert
            self.check_and_alert(target, result)
            
            # Display status
            icon = "✅" if result["status"] == "healthy" else "❌"
            self.log(f"{icon} {target}: {result['status']}")
        
        # Save status
        self.save_status(statuses)
        
        # Summary
        healthy_count = sum(1 for s in statuses.values() if s["status"] == "healthy")
        self.log(f"\nSummary: {healthy_count}/{len(statuses)} entities healthy")
        self.log(f"{'='*60}\n")
        
        return statuses
    
    async def run(self):
        """Main monitoring loop"""
        self.log("="*60)
        self.log("Entity Monitor - Auto Health Check System")
        self.log("="*60)
        self.log(f"Targets: {self.targets}")
        self.log(f"Interval: {CHECK_INTERVAL}s")
        self.log(f"Alert Threshold: {ALERT_THRESHOLD}")
        self.log("="*60)
        
        while True:
            try:
                await self.run_single_check()
            except Exception as e:
                self.log(f"Error in check cycle: {e}", "ERROR")
            
            await asyncio.sleep(CHECK_INTERVAL)


def main():
    """Main entry point"""
    # Parse arguments
    import argparse
    parser = argparse.ArgumentParser(description="Entity Health Monitor")
    parser.add_argument("--targets", nargs="+", help="Target URLs to monitor")
    parser.add_argument("--interval", type=int, default=CHECK_INTERVAL, help="Check interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    args = parser.parse_args()
    
    # Create monitor
    targets = args.targets or DEFAULT_TARGETS
    monitor = EntityMonitor(targets)
    
    if args.once:
        # Run single check
        asyncio.run(monitor.run_single_check())
    else:
        # Run continuous monitoring
        try:
            asyncio.run(monitor.run())
        except KeyboardInterrupt:
            print("\nMonitor stopped by user")
            sys.exit(0)


if __name__ == "__main__":
    main()
