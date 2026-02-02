#!/bin/bash
# Launch monitoring script - run every 30 minutes during launch period

echo "Starting launch monitoring..."

# Track KPIs
python3 scripts/launch_kpi_tracker.py

# Check API health
HEALTH=$(curl -s http://34.134.116.148:8080/health | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

if [ "$HEALTH" != "healthy" ]; then
    echo "⚠️ API health check failed!"
    # Could send alert here
fi

echo "Monitor cycle complete: $(date)"
