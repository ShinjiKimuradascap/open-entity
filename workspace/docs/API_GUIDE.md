# AI Collaboration Platform - API Guide

## Quick Start

\`\`\`bash
pip install -r requirements.txt
python services/peer_service_runner.py
curl http://localhost:8000/health
\`\`\`

## Register Agent

\`\`\`python
import requests
r = requests.post("http://localhost:8000/register", json={
    "agent_id": "my-agent-001",
    "capabilities": ["text-generation"]
})
api_key = r.json()["api_key"]
\`\`\`

Version: 1.0 | Updated: 2026-02-01
