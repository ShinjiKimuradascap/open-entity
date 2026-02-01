#!/bin/bash
#
# Systemd Service Setup for AI Collaboration Platform
# 24時間稼働のためのsystemdサービス設定
#
# Usage: sudo ./scripts/setup_systemd_service.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="ai-collab-platform"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    log_error "Please run as root (use sudo)"
    exit 1
fi

# Create systemd service file
log_info "Creating systemd service..."

cat > "$SERVICE_FILE" << EOF
[Unit]
Description=AI Collaboration Platform
Documentation=https://github.com/mocos-ai/collaboration-platform
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$PROJECT_DIR
User=root
Group=root

# Start command
ExecStart=/usr/local/bin/docker-compose -f $PROJECT_DIR/docker-compose.yml up -d

# Stop command
ExecStop=/usr/local/bin/docker-compose -f $PROJECT_DIR/docker-compose.yml down

# Reload command
ExecReload=/usr/local/bin/docker-compose -f $PROJECT_DIR/docker-compose.yml restart

# Restart policy
Restart=no

[Install]
WantedBy=multi-user.target
EOF

log_info "Created $SERVICE_FILE"

# Reload systemd
log_info "Reloading systemd..."
systemctl daemon-reload

# Enable service (start on boot)
log_info "Enabling service to start on boot..."
systemctl enable "$SERVICE_NAME"

# Start service
log_info "Starting service..."
systemctl start "$SERVICE_NAME"

# Check status
log_info "Checking service status..."
systemctl status "$SERVICE_NAME" --no-pager

echo ""
echo "=========================================="
echo "  Systemd Service Setup Complete!"
echo "=========================================="
echo ""
echo "Commands:"
echo "  Start:   sudo systemctl start $SERVICE_NAME"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Restart: sudo systemctl restart $SERVICE_NAME"
echo "  Status:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Auto-start on boot: ENABLED"
echo ""
echo "=========================================="
