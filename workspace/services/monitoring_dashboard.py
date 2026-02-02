#!/usr/bin/env python3
"""
Infrastructure Monitoring Dashboard
インフラ監視ダッシュボード

Features:
- Health check aggregation
- Service status monitoring
- Alert system
- Web dashboard
"""

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List
import aiohttp

DATA_DIR = Path("data/monitoring")
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 監視対象サービス
SERVICES = {
    "api_server": {"url": "http://localhost:8080/health", "interval": 30},
    "bootstrap": {"url": "http://localhost:8468/health", "interval": 60},
    "feedback": {"url": "http://localhost:8081/health", "interval": 60},
    "invitation": {"url": "http://localhost:8082/health", "interval": 60}
}


class MonitoringDashboard:
    """監視ダッシュボード"""
    
    def __init__(self):
        self.status_file = DATA_DIR / "status.json"
        self.history_file = DATA_DIR / "history.json"
        self.alerts_file = DATA_DIR / "alerts.json"
        self.load_data()
    
    def load_data(self):
        """データ読み込み"""
        if self.status_file.exists():
            with open(self.status_file) as f:
                self.status = json.load(f)
        else:
            self.status = {name: {"status": "unknown", "last_check": None} 
                          for name in SERVICES}
        
        if self.alerts_file.exists():
            with open(self.alerts_file) as f:
                self.alerts = json.load(f)
        else:
            self.alerts = {"active": [], "resolved": []}
    
    def save_data(self):
        """データ保存"""
        with open(self.status_file, 'w') as f:
            json.dump(self.status, f, indent=2)
        with open(self.alerts_file, 'w') as f:
            json.dump(self.alerts, f, indent=2)
    
    async def check_health(self, name: str, url: str) -> Dict:
        """ヘルスチェック実行"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as resp:
                    healthy = resp.status == 200
                    return {
                        "name": name,
                        "status": "healthy" if healthy else "unhealthy",
                        "status_code": resp.status,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
        except Exception as e:
            return {
                "name": name,
                "status": "down",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def run_checks(self):
        """全サービスのヘルスチェック"""
        tasks = []
        for name, config in SERVICES.items():
            task = self.check_health(name, config["url"])
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, dict) and "name" in result:
                self.status[result["name"]] = result
                
                # アラート生成
                if result["status"] != "healthy":
                    self._create_alert(result["name"], result)
        
        self.save_data()
        return self.status
    
    def _create_alert(self, service: str, details: Dict):
        """アラートを作成"""
        alert = {
            "id": f"alert_{datetime.now(timezone.utc).timestamp()}",
            "service": service,
            "status": details["status"],
            "timestamp": details["timestamp"],
            "details": details.get("error", "Service unhealthy"),
            "acknowledged": False
        }
        self.alerts["active"].append(alert)
    
    def get_dashboard_data(self) -> Dict:
        """ダッシュボードデータを取得"""
        healthy_count = sum(1 for s in self.status.values() if s.get("status") == "healthy")
        total_count = len(self.status)
        
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_services": total_count,
                "healthy": healthy_count,
                "unhealthy": total_count - healthy_count,
                "uptime_percentage": round(healthy_count / total_count * 100, 1) if total_count > 0 else 0
            },
            "services": self.status,
            "active_alerts": len([a for a in self.alerts["active"] if not a["acknowledged"]]),
            "alerts": self.alerts["active"][:10]  # 最新10件
        }
    
    def generate_html(self) -> str:
        """HTMLダッシュボードを生成"""
        data = self.get_dashboard_data()
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Open Entity - Monitoring Dashboard</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }}
        .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; border-radius: 10px; margin-bottom: 20px; }}
        .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .card h3 {{ margin-top: 0; color: #333; }}
        .metric {{ font-size: 2em; font-weight: bold; color: #667eea; }}
        .status-healthy {{ color: #22c55e; }}
        .status-unhealthy {{ color: #ef4444; }}
        .status-down {{ color: #6b7280; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #e5e7eb; }}
        th {{ background: #f9fafb; font-weight: 600; }}
        .alert {{ background: #fef3c7; border-left: 4px solid #f59e0b; padding: 12px; margin-bottom: 10px; border-radius: 4px; }}
        .alert-critical {{ background: #fee2e2; border-left-color: #ef4444; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🚀 Open Entity Monitoring Dashboard</h1>
        <p>Generated: {data['generated_at']}</p>
    </div>
    
    <div class="summary">
        <div class="card">
            <h3>Services</h3>
            <div class="metric">{data['summary']['healthy']}/{data['summary']['total_services']}</div>
            <p>Healthy</p>
        </div>
        <div class="card">
            <h3>Uptime</h3>
            <div class="metric">{data['summary']['uptime_percentage']}%</div>
            <p>Current</p>
        </div>
        <div class="card">
            <h3>Alerts</h3>
            <div class="metric">{data['active_alerts']}</div>
            <p>Active</p>
        </div>
    </div>
    
    <h2>Service Status</h2>
    <table>
        <thead>
            <tr><th>Service</th><th>Status</th><th>Last Check</th></tr>
        </thead>
        <tbody>
"""
        
        for name, status in data['services'].items():
            status_class = f"status-{status.get('status', 'unknown')}"
            html += f"            <tr><td>{name}</td><td class='{status_class}'>{status.get('status', 'unknown')}</td><td>{status.get('timestamp', 'N/A')}</td></tr>\n"
        
        html += """        </tbody>
    </table>
    
    <h2>Active Alerts</h2>
"""
        
        if data['alerts']:
            for alert in data['alerts']:
                alert_class = "alert-critical" if alert['status'] == 'down' else "alert"
                html += f"    <div class='{alert_class}'><strong>{alert['service']}</strong>: {alert['details']} at {alert['timestamp']}</div>\n"
        else:
            html += "    <p>No active alerts 🎉</p>\n"
        
        html += """</body>
</html>"""
        
        return html


# FastAPI app
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
app = FastAPI(title="Monitoring Dashboard API")
dashboard = MonitoringDashboard()

@app.get("/")
async def root():
    """ダッシュボードHTMLを返す"""
    return HTMLResponse(content=dashboard.generate_html())

@app.get("/api/status")
async def get_status():
    """ステータスJSONを返す"""
    await dashboard.run_checks()
    return dashboard.get_dashboard_data()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8083)
