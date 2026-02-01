# Deployment Guide

AI Collaboration Platform - Deployment Guide for Render.com, Railway, and Fly.io

## Table of Contents

1. Platform Comparison
2. Prerequisites
3. GitHub Secrets Setup
4. Platform-Specific Deployment
5. Health Check Endpoints
6. Troubleshooting

---

## Platform Comparison

| Feature | Render.com | Railway | Fly.io |
|---------|------------|---------|--------|
| Free Tier | Yes | Yes | Yes |
| Custom Domains | Yes | Yes | Yes |
| Auto-deploy from Git | Yes | Yes | Yes |
| WebSocket Support | Yes | Yes | Yes |
| Persistent Storage | Yes | Yes | Yes |
| Multi-region | No | No | Yes |
| Build Time (Free) | Unlimited | 500 hours/mo | Shared |
| Sleep on Inactivity | Yes (15 min) | No | Configurable |
| Best For | Simple APIs | Full-stack apps | Global scale |

### Recommendation Matrix

| Use Case | Platform | Reason |
|----------|----------|--------|
| Quick prototype | Render.com | Simplest setup |
| Production API | Railway | No sleep |
| Global distribution | Fly.io | Edge deployment |
| WebSocket apps | Fly.io | Best WS support |

---

## Prerequisites

### Required Accounts

1. GitHub - Source repository
2. Platform Account - Render/Railway/Fly.io

### Environment Variables

Create .env locally (never commit to Git):

    API_HOST=0.0.0.0
    API_PORT=8000
    DATA_DIR=/tmp/data
    JWT_SECRET_KEY=your-key-min-32-chars
    API_SECRET_KEY=your-api-key
    MOLTBOOK_API_KEY=your-moltbook-key
    BOOTSTRAP_HOST=0.0.0.0
    BOOTSTRAP_PORT=8468

---

## GitHub Secrets Setup

Configure in GitHub: Settings - Secrets - Actions

### Render.com Secrets

- RENDER_API_KEY: Render API key
- RENDER_SERVICE_ID: Service ID
- RENDER_SERVICE_NAME: Service name
- RENDER_BOOTSTRAP_SERVICE_ID: Bootstrap service ID

### Railway Secrets

- RAILWAY_TOKEN: API token
- RAILWAY_PROJECT_ID: Project ID

### Fly.io Secrets

- FLY_API_TOKEN: API token
- FLY_APP_NAME: App name

### Application Secrets (All Platforms)

- JWT_SECRET_KEY: Required - JWT signing key
- API_SECRET_KEY: Required - API auth key
- MOLTBOOK_API_KEY: Optional - Moltbook service

---

## Platform Deployment

### 1. Render.com

Configuration: render.yaml

Services:
- open-entity-api (Port 8000, Health: /health)
- open-entity-bootstrap (Port 8468, Health: /health)

Deploy: Push to main triggers auto-deploy

Manual:
1. Connect GitHub repo on Render Dashboard
2. Select Blueprint option
3. Render reads render.yaml

Environment Variables:
- PYTHON_VERSION=3.11.0
- API_HOST=0.0.0.0
- API_PORT=8000
- DATA_DIR=/tmp/data
- JWT_SECRET_KEY
- API_SECRET_KEY

Custom Domain:
1. Dashboard - Settings - Custom Domain
2. Add domain, SSL auto-provisioned

### 2. Railway

Configuration: railway.json

Deploy:
    railway login
    railway link
    railway up
    railway logs
    railway status

Environment Variables:
    railway variables set JWT_SECRET_KEY=your-key
    railway variables set API_SECRET_KEY=your-key

Database: railway add --database postgres

### 3. Fly.io

Configuration: fly.toml

Region: nrt (Tokyo), Options: iad/lhr/sin

Deploy:
    flyctl launch --name open-entity-api
    flyctl deploy
    flyctl logs
    flyctl status

Environment Variables:
    flyctl secrets set JWT_SECRET_KEY=your-key
    flyctl secrets set API_SECRET_KEY=your-key

Scaling:
    flyctl scale count 2
    flyctl scale vm shared-cpu-2x --memory 1024

Custom Domain:
    flyctl certs create api.yourdomain.com

---

## Health Check Endpoints

### API Server (services/api_server.py)

GET /health

Response:
    {
      "status": "healthy",
      "version": "0.4.0",
      "registered_agents": 5,
      "timestamp": "2026-02-01T10:00:00Z",
      "security_features": {
        "ed25519_signatures": true,
        "jwt_authentication": true,
        "replay_protection": true
      }
    }

Curl Test:
    curl https://your-service.onrender.com/health
    curl https://your-service.up.railway.app/health
    curl https://your-service.fly.dev/health

### Bootstrap Server (services/bootstrap_server.py)

GET /health

Response:
    {
      "status": "healthy",
      "peers": 12,
      "timestamp": "2026-02-01T10:00:00Z"
    }

### Platform Health Check Configs

| Platform | Timeout | Interval | Path |
|----------|---------|----------|------|
| Render | 30s | 15s | /health |
| Railway | 100s | 10s | /health |
| Fly.io | 30s | 10s | /health |

---

## Troubleshooting

### Build Failures

    python --version  # Check 3.11+
    docker build -t test-build .
    pip install -r requirements.txt

### Health Check Failures

    python services/api_server.py &
    curl http://localhost:8000/health

### Environment Variables

Verify secrets:
- Render: Dashboard - Environment
- Railway: railway variables
- Fly.io: flyctl secrets list

### WebSocket Issues (Fly.io)

In fly.toml:
    [http_service]
      internal_port = 8080
      force_https = true

### DHT/Bootstrap Connectivity

- Ensure port 8468 exposed
- Check firewall settings
- Verify BOOTSTRAP_HOST and BOOTSTRAP_PORT

### Platform Debugging

Render: Dashboard logs
Railway: railway logs --follow
Fly.io: flyctl logs && flyctl ssh console

### Documentation

- Render: https://render.com/docs
- Railway: https://docs.railway.app
- Fly.io: https://fly.io/docs

---

## CI/CD Workflows

File: .github/workflows/deploy-production.yml

Manual Trigger:
1. Actions tab - Deploy to Production
2. Run workflow
3. Choose platform: render, railway, or flyio

Auto Trigger: Push to main deploys to Render

Verification:
    curl https://your-domain.com/health
    curl https://your-domain.com/api/v0/agents

---

## Production Checklist

- Set all required secrets in GitHub
- Configure custom domain (optional)
- Enable HTTPS (automatic)
- Set up monitoring/alerts
- Configure backup for persistent data
- Test health endpoints
- Verify WebSocket functionality
- Run integration tests
- Document rollback procedure

---

## Migration Between Platforms

### Render to Railway

1. Export env vars from Render Dashboard
2. Create new Railway project
3. Import GitHub repo
4. Set environment variables
5. Deploy and verify

### Railway to Fly.io

1. Run flyctl launch in repo root
2. Copy environment variables
3. Update fly.toml
4. Deploy with flyctl deploy

---

Last Updated: 2026-02-01
Version: 1.0
