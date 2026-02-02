#!/bin/bash
# GCP Frontend Deployment Script
# Deploy Streamlit frontend to existing GCP instance

set -e

API_HOST="34.134.116.148"
FRONTEND_PORT="8501"
API_PORT="8080"

echo "=========================================="
echo "GCP Frontend Deployment"
echo "=========================================="

# Check if running on GCP instance
if [ -f /etc/hostname ]; then
    echo "Running on GCP instance"
    LOCAL_DEPLOY=true
else
    echo "Running locally - will use SSH"
    LOCAL_DEPLOY=false
fi

# Install dependencies
echo "[1/4] Installing dependencies..."
pip install streamlit pandas requests -q

# Create systemd service file
echo "[2/4] Creating systemd service..."
sudo tee /etc/systemd/system/openentity-frontend.service > /dev/null <<EOF
[Unit]
Description=Open Entity Marketplace Frontend
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/workspace/frontend
Environment="API_BASE_URL=http://${API_HOST}:${API_PORT}"
Environment="STREAMLIT_SERVER_PORT=${FRONTEND_PORT}"
Environment="STREAMLIT_SERVER_ADDRESS=0.0.0.0"
ExecStart=/usr/local/bin/streamlit run marketplace_app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Enable and start service
echo "[3/4] Enabling service..."
sudo systemctl daemon-reload
sudo systemctl enable openentity-frontend
sudo systemctl start openentity-frontend

# Check status
echo "[4/4] Checking status..."
sleep 3
if sudo systemctl is-active --quiet openentity-frontend; then
    echo "✅ Frontend is running!"
    echo "URL: http://${API_HOST}:${FRONTEND_PORT}"
else
    echo "❌ Failed to start frontend"
    sudo systemctl status openentity-frontend --no-pager
    exit 1
fi

echo "=========================================="
echo "Deployment complete!"
echo "Frontend: http://${API_HOST}:${FRONTEND_PORT}"
echo "API: http://${API_HOST}:${API_PORT}"
echo "=========================================="
