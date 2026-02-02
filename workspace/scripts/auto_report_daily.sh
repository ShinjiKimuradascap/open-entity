#!/bin/bash
curl -s http://34.134.116.148:8080/health > /tmp/health_check.json 2>/dev/null
echo "Daily check done: $(date)"
