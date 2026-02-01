# L0-1: Production Deployment Checklist

## Goal: Deploy tools to production - 24/7 infrastructure

## Phase 1: Pre-Deployment (Ready)

- [x] Docker environment verified
- [x] docker-compose.yml created
- [x] Dockerfile multi-stage build
- [x] Deploy scripts created
- [x] Systemd service config created

## Phase 2: Server Setup

- [ ] VPS/Server (Recommended: 4vCPU, 8GB RAM, 100GB SSD)
- [ ] OS: Ubuntu 22.04 LTS
- [ ] SSH key authentication
- [ ] Firewall (Ports: 8000, 8001, 8002, 6379, 9090, 3000)
- [ ] Docker & Docker Compose installed

## Phase 3: Configuration

- [ ] Create and configure .env file
- [ ] SSL/TLS certificates (Let's Encrypt)
- [ ] Domain setup

## Phase 4: Deploy

- [ ] Deploy code (git clone or scp)
- [ ] Run: ./scripts/deploy_production.sh
- [ ] Health check
- [ ] Enable systemd service

## Phase 5: Monitoring

- [ ] Grafana dashboard
- [ ] Alert setup (Slack)
- [ ] Log collection
- [ ] Backup configuration

## Cost Estimate (Monthly)

- VPS: $20-40
- Domain: $10-15/year
- SSL: Free (Let's Encrypt)
- Total: ~$30-50/month
