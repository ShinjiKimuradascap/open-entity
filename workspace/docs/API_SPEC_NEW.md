# New Services API Specification

## Services Overview

| Service | Port | Purpose |
|:--------|:-----|:--------|
| Feedback | 8081 | Feedback collection |
| Invitation | 8082 | Onboarding |
| Monitoring | 8083 | Infrastructure |
| Billing | 8084 | Rate limits |
| Multi-Tenant | 8085 | Tenant isolation |

## Feedback API (8081)

### POST /feedback/add
Request: {source, content, sentiment}
Response: {feedback_id, status}

### GET /feedback/report
Response: {summary, by_source, recent_feedback}

## Invitation API (8082)

### POST /invite/generate
Response: {invite_code}

### POST /invite/onboard
Request: {agent_id, invite_code, public_key}
Response: {agent_id, welcome_bonus, level}

## Monitoring API (8083)

### GET /
HTML dashboard

### GET /api/status
JSON status with service health

## Billing API (8084)

### GET /check-limit
Header: X-API-Key
Response: {allowed, minute_remaining, day_remaining}

### POST /upgrade
Request: {tier}
Response: {success, new_tier, monthly_cost}

## Multi-Tenant API (8085)

### POST /tenants/create
Request: {name, plan}
Response: {tenant_id, api_key, limits}

### GET /tenants/me
Header: X-Tenant-API-Key

---
Generated: 2026-02-02