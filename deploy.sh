#!/bin/bash

# Quick deployment script for Ubuntu server
# Run this after transferring files to your Ubuntu server

set -e  # Exit on error

echo "=== Shopify App Deployment Script ==="
echo ""

# Variables - UPDATE THESE
APP_DIR="/home/$USER/shopify-app"
VENV_DIR="$APP_DIR/venv"
SERVICE_NAME="shopify-app"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}Step 1: Installing system dependencies...${NC}"
sudo apt update
sudo apt install -y python3 python3-pip python3-venv chromium-browser chromium-chromedriver nginx supervisor

echo -e "${GREEN}✓ System dependencies installed${NC}"
echo ""

echo -e "${YELLOW}Step 2: Setting up Python environment...${NC}"
cd $APP_DIR

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate and install dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
echo -e "${GREEN}✓ Python dependencies installed${NC}"
echo ""

echo -e "${YELLOW}Step 3: Setting up database...${NC}"
if [ ! -f "$APP_DIR/shopify_app.db" ]; then
    python -c "from app.database import engine, Base; Base.metadata.create_all(engine); print('Database created')"
    echo -e "${GREEN}✓ Database initialized${NC}"
else
    echo -e "${GREEN}✓ Database already exists${NC}"
fi
echo ""

echo -e "${YELLOW}Step 4: Creating systemd service...${NC}"
sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null <<EOF
[Unit]
Description=Shopify Price Management App
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME
echo -e "${GREEN}✓ Systemd service created and enabled${NC}"
echo ""

echo -e "${YELLOW}Step 5: Setting up Nginx...${NC}"
sudo tee /etc/nginx/sites-available/$SERVICE_NAME > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location /static/ {
        alias $APP_DIR/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

# Enable site
sudo ln -sf /etc/nginx/sites-available/$SERVICE_NAME /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
echo -e "${GREEN}✓ Nginx configured and restarted${NC}"
echo ""

echo -e "${YELLOW}Step 6: Configuring firewall...${NC}"
sudo ufw allow ssh
sudo ufw allow 'Nginx Full'
sudo ufw --force enable
echo -e "${GREEN}✓ Firewall configured${NC}"
echo ""

echo -e "${YELLOW}Step 7: Starting application...${NC}"
sudo systemctl start $SERVICE_NAME
sleep 3
sudo systemctl status $SERVICE_NAME --no-pager
echo -e "${GREEN}✓ Application started${NC}"
echo ""

echo -e "${GREEN}=== Deployment Complete! ===${NC}"
echo ""
echo "Your application is now running!"
echo ""
echo "Access it at:"
echo "  - Web Interface: http://$(hostname -I | awk '{print $1}')/"
echo "  - API Docs: http://$(hostname -I | awk '{print $1}')/docs"
echo ""
echo "Useful commands:"
echo "  - View logs: sudo journalctl -u $SERVICE_NAME -f"
echo "  - Restart: sudo systemctl restart $SERVICE_NAME"
echo "  - Stop: sudo systemctl stop $SERVICE_NAME"
echo "  - Status: sudo systemctl status $SERVICE_NAME"
echo ""
