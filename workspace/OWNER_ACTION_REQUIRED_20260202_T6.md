# OWNER ACTION REQUIRED - T-6h Critical

**Time:** 2026-02-02 01:10 JST (T-6h to PH Launch)
**Priority:** CRITICAL
**Issue:** Marketplace services not showing in API

## Problem Summary

API `/marketplace/stats` returns 0 services despite data being present in registry files.

**Root Cause:**
API server loaded empty data at startup. Needs restart to reload synchronized data files.

## Files Synchronized (All now contain 5 services)
- data/marketplace/registry.json
- data/marketplace_registry.json
- data/services/registry.json

## Required Action

RESTART GCP API SERVER to reload data from disk.

### Via GCP Console:
1. Go to https://console.cloud.google.com/run
2. Find service: messaging-api
3. Click "Restart"

### Verification:
curl http://34.134.116.148:8080/marketplace/stats

Should return: total_services: 5

## Impact if Not Fixed
- Product Hunt demo will show empty marketplace
- Critical for launch credibility

**Reported by:** Entity A (Orchestrator)
