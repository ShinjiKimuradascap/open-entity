#!/bin/bash
# Deploy Streamlit Frontend to GCP Instance

set -e

echo "🚀 Deploying Open Entity Marketplace Frontend..."

# Configuration
REMOTE_HOST="34.134.116.148"
REMOTE_USER="moco"
FRONTEND_DIR="/home/moco/workspace/frontend"
SERVICE_NAME="open-entity-frontend"

# Create remote directory
echo "📁 Creating remote directory..."
ssh ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p ${FRONTEND_DIR}"

# Copy files
echo "📤 Copying files..."
scp frontend/marketplace_app.py ${REMOTE_USER}@${REMOTE_HOST}:${FRONTEND_DIR}/
scp frontend/requirements.txt ${REMOTE_USER}@${REMOTE_HOST}:${FRONTEND_DIR}/

# Install dependencies and setup systemd service
echo "⚙️ Setting up service..."
ssh ${REMOTE_USER}@${REMOTE_HOST} << 'EOF'
    cd /home/moco/workspace/frontend
    
    # Install requirements
    pip3 install -r requirements.txt --user
    
    # Create systemd service file
    sudo tee /etc/systemd/system/open-entity-frontend.service > /dev/null << 'SERVICE'
[Unit]
Description=Open Entity Marketplace Frontend
After=network.target

[Service]
Type=simple
User=moco
WorkingDirectory=/home/moco/workspace/frontend
Environment=PYTHONUNBUFFERED=1
Environment=STREAMLIT_SERVER_PORT=8501
Environment=STREAMLIT_SERVER_ADDRESS=0.0.0.0
ExecStart=/usr/local/bin/streamlit run marketplace_app.py --server.port=8501 --server.address=0.0.0.0
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICE

    # Reload and start service
    sudo systemctl daemon-reload
    sudo systemctl enable open-entity-frontend
    sudo systemctl restart open-entity-frontend
    
    echo "✅ Service status:"
    sudo systemctl status open-entity-frontend --no-pager
EOF

echo "✅ Deployment complete!"
echo ""
echo "🌐 Frontend URL: http://${REMOTE_HOST}:8501"
echo "🔌 API URL: http://${REMOTE_HOST}:8080"
