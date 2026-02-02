#!/bin/bash
# Docker Entrypoint Script - Initialize data if empty

set -e

# Initialize marketplace data if not exists
if [ ! -f "/app/data/marketplace/registry.json" ]; then
    echo "[entrypoint] Initializing marketplace data..."
    mkdir -p /app/data/marketplace
    if [ -f "/app/data_backup/marketplace/registry.json" ]; then
        cp /app/data_backup/marketplace/registry.json /app/data/marketplace/
        echo "[entrypoint] Marketplace data copied from backup"
    fi
fi

# Initialize services registry if not exists
if [ ! -f "/app/data/services/registry.json" ]; then
    echo "[entrypoint] Initializing services registry..."
    mkdir -p /app/data/services
    if [ -f "/app/data_backup/services/registry.json" ]; then
        cp /app/data_backup/services/registry.json /app/data/services/
        echo "[entrypoint] Services registry copied from backup"
    fi
fi

# Execute the main command
exec "$@"
