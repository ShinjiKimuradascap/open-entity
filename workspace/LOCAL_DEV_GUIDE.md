# Local Development Guide

## Environment
- Python: 3.11.14
- pip: 24.0
- Docker: Not available

## Setup
1. Install deps: pip3 install -r requirements.txt
2. Copy env: cp .env.example .env
3. Start API: cd services && python3 -m uvicorn api_server:app --host 0.0.0.0 --port 8000
4. Start Entity A: python3 peer_service_runner.py --id entity-a --port 8001
5. Start Entity B: python3 peer_service_runner.py --id entity-b --port 8002

## Notes
- Redis/Prometheus/Grafana need manual install
- Docker recommended for production
