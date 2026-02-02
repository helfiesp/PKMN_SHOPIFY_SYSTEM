#!/bin/bash

# Shopify Price Manager - Robust Ubuntu Deployment Script
# This script sets up the application on Ubuntu server with comprehensive checks

set -e  # Exit on error

echo "=================================="
echo "Shopify Price Manager Deployment"
echo "=================================="
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
APP_DIR="$SCRIPT_DIR"
APP_NAME="shopify-app"
VENV_DIR="$HOME/software/venv"

echo -e "${BLUE}Application directory: $APP_DIR${NC}"
echo -e "${BLUE}Virtual environment: $VENV_DIR${NC}"
echo ""

# Check if running as root
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}❌ Please do not run this script as root (without sudo)${NC}"
    echo "Run it as a normal user. The script will use sudo when needed."
    exit 1
fi

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print success
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print error
print_error() {
    echo -e "${RED}✗ $1${NC}"
}

# Function to print info
print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# Verify we're in the right directory
if [ ! -f "$APP_DIR/requirements.txt" ]; then
    print_error "requirements.txt not found in $APP_DIR"
    print_error "Please run this script from the PKMN_SHOPIFY_SYSTEM directory"
    exit 1
fi

if [ ! -f "$APP_DIR/run.py" ]; then
    print_error "run.py not found in $APP_DIR"
    exit 1
fi

print_success "Deployment prerequisites verified"
echo ""

# Update system packages
print_info "Updating system packages..."
sudo apt update
sudo apt upgrade -y
print_success "System packages updated"
echo ""

# Install Python 3 and pip
print_info "Installing Python 3 and dependencies..."
sudo apt install -y python3 python3-pip python3-venv python3-dev build-essential
print_success "Python 3 installed"

# Verify Python version
PYTHON_VERSION=$(python3 --version | awk '{print $2}')
print_info "Python version: $PYTHON_VERSION"
echo ""

# Install Chromium and ChromeDriver for web scraping
print_info "Installing Chromium and ChromeDriver..."
sudo apt install -y chromium-browser chromium-chromedriver

# Verify ChromeDriver installation
if command_exists chromedriver; then
    CHROMEDRIVER_VERSION=$(chromedriver --version | awk '{print $2}')
    print_success "ChromeDriver installed: $CHROMEDRIVER_VERSION"
else
    print_error "ChromeDriver installation failed"
    exit 1
fi

# Create symbolic link for chromedriver
sudo ln -sf /usr/lib/chromium-browser/chromedriver /usr/local/bin/chromedriver 2>/dev/null || true
print_success "ChromeDriver configured"
echo ""

# Install Nginx
print_info "Installing Nginx..."
sudo apt install -y nginx
print_success "Nginx installed"
echo ""

# Create/verify virtual environment
print_info "Setting up Python virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    mkdir -p "$(dirname "$VENV_DIR")"
    python3 -m venv "$VENV_DIR"
    print_success "Virtual environment created at $VENV_DIR"
else
    print_info "Using existing virtual environment at $VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"
print_success "Virtual environment activated"

# Upgrade pip
print_info "Upgrading pip..."
pip install --upgrade pip setuptools wheel
print_success "pip upgraded"
echo ""

# Install Python dependencies
print_info "Installing Python dependencies from requirements.txt..."
cd "$APP_DIR"
pip install -r requirements.txt
print_success "Python dependencies installed"

# Verify key packages
print_info "Verifying installed packages..."
FASTAPI_VERSION=$(pip show fastapi | grep Version | awk '{print $2}')
UVICORN_VERSION=$(pip show uvicorn | grep Version | awk '{print $2}')
SELENIUM_VERSION=$(pip show selenium | grep Version | awk '{print $2}')
print_info "  FastAPI: $FASTAPI_VERSION"
print_info "  Uvicorn: $UVICORN_VERSION"
print_info "  Selenium: $SELENIUM_VERSION"
echo ""

# Check if .env file exists
if [ ! -f "$APP_DIR/.env" ]; then
    print_error ".env file not found!"
    print_info "Creating .env from .env.example..."
    if [ -f "$APP_DIR/.env.example" ]; then
        cp "$APP_DIR/.env.example" "$APP_DIR/.env"
        print_success ".env file created"
        echo -e "${YELLOW}⚠ IMPORTANT: Edit .env file and add your credentials!${NC}"
        echo -e "${YELLOW}  nano $APP_DIR/.env${NC}"
        echo ""
        read -p "Press Enter after you've edited the .env file..."
    else
        print_error ".env.example not found. Please create .env manually"
        exit 1
    fi
else
    print_success ".env file exists"
fi

# Verify .env has required variables
print_info "Verifying .env configuration..."
MISSING_VARS=()
if ! grep -q "SHOPIFY_SHOP=" "$APP_DIR/.env" || grep -q "SHOPIFY_SHOP=your-shop" "$APP_DIR/.env"; then
    MISSING_VARS+=("SHOPIFY_SHOP")
fi
if ! grep -q "SHOPIFY_TOKEN=" "$APP_DIR/.env" || grep -q "SHOPIFY_TOKEN=shpca_your" "$APP_DIR/.env"; then
    MISSING_VARS+=("SHOPIFY_TOKEN")
fi

if [ ${#MISSING_VARS[@]} -gt 0 ]; then
    print_error "Missing or incomplete environment variables: ${MISSING_VARS[*]}"
    echo -e "${YELLOW}Please edit .env and set: ${MISSING_VARS[*]}${NC}"
    exit 1
fi
print_success ".env configuration verified"
echo ""

# Initialize database
print_info "Initializing database..."
python3 -c "from app.database import engine, Base; Base.metadata.create_all(engine); print('✓ Database initialized successfully')"
if [ -f "$APP_DIR/shopify_app.db" ]; then
    print_success "Database file created: shopify_app.db"
else
    print_error "Database initialization may have failed"
fi
echo ""

# Test application import
print_info "Testing application imports..."
python3 -c "from app.main import app; print('✓ Application imports successful')" || {
    print_error "Application import failed"
    exit 1
}
print_success "Application code validated"
echo ""

# Create systemd service file
print_info "Creating systemd service..."
sudo tee /etc/systemd/system/$APP_NAME.service > /dev/null <<EOF
[Unit]
Description=Shopify Price Manager API
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$APP_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/python $APP_DIR/run.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
print_success "Systemd service file created"

# Reload systemd
sudo systemctl daemon-reload
print_success "Systemd daemon reloaded"

# Enable the service
sudo systemctl enable $APP_NAME
print_success "Service enabled for auto-start"

# Start the service
print_info "Starting service..."
sudo systemctl start $APP_NAME

# Wait for service to start
sleep 3

# Check service status
if sudo systemctl is-active --quiet $APP_NAME; then
    print_success "Service started successfully"
else
    print_error "Service failed to start"
    print_info "Checking logs..."
    sudo journalctl -u $APP_NAME -n 50 --no-pager
    exit 1
fi
echo ""

# Test if application is responding and healthy
print_info "Testing application health endpoint..."
MAX_RETRIES=15
RETRY_COUNT=0
HEALTH_STATUS=""

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    sleep 2
    HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/v1/health 2>/dev/null || echo "")
    
    if [ -n "$HEALTH_RESPONSE" ]; then
        HEALTH_STATUS=$(echo "$HEALTH_RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
        DB_STATUS=$(echo "$HEALTH_RESPONSE" | grep -o '"database":"[^"]*"' | cut -d'"' -f4)
        
        if [ "$HEALTH_STATUS" = "healthy" ]; then
            print_success "Application is healthy"
            print_success "Database status: $DB_STATUS"
            break
        elif [ "$HEALTH_STATUS" = "degraded" ]; then
            print_info "Application is responding but degraded: $DB_STATUS"
            if [[ "$DB_STATUS" == "healthy" ]]; then
                print_success "Database is healthy, continuing..."
                break
            fi
        fi
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    print_info "Waiting for application to become healthy (attempt $RETRY_COUNT/$MAX_RETRIES)..."
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    print_error "Application health check failed after $MAX_RETRIES attempts"
    print_error "Last health status: $HEALTH_STATUS"
    print_info "Service logs:"
    sudo journalctl -u $APP_NAME -n 30 --no-pager
    exit 1
fi
echo ""

# Configure Nginx
print_info "Configuring Nginx..."
sudo tee /etc/nginx/sites-available/$APP_NAME > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
    }

    # Serve static files directly
    location /static {
        alias $APP_DIR/app/static;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
EOF
print_success "Nginx configuration created"

# Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/$APP_NAME /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
print_success "Nginx site enabled"

# Test Nginx configuration
print_info "Testing Nginx configuration..."
if sudo nginx -t; then
    print_success "Nginx configuration is valid"
else
    print_error "Nginx configuration test failed"
    exit 1
fi

# Restart Nginx
sudo systemctl restart nginx
print_success "Nginx restarted"
echo ""

# Configure firewall
print_info "Configuring firewall..."
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
echo "y" | sudo ufw enable || true
print_success "Firewall configured"
echo ""

# Create logs directory for cron jobs
mkdir -p "$HOME/logs"
print_success "Logs directory created at ~/logs"
echo ""

# Test full deployment
print_info "Running final deployment verification..."
SERVER_IP=$(hostname -I | awk '{print $1}')

# Test local connection
if curl -f http://localhost/ >/dev/null 2>&1; then
    print_success "Local HTTP connection successful"
else
    print_error "Local HTTP connection failed"
fi

# Test health endpoint through Nginx
if curl -f http://localhost/api/v1/health >/dev/null 2>&1; then
    print_success "Health endpoint accessible through Nginx"
else
    print_error "Health endpoint not accessible through Nginx"
fi

echo ""
echo -e "${GREEN}=========================================="
echo "🎉 Deployment Complete!"
echo -e "==========================================${NC}"
echo ""
echo -e "${GREEN}✓ Python environment: $VENV_DIR${NC}"
echo -e "${GREEN}✓ Application directory: $APP_DIR${NC}"
echo -e "${GREEN}✓ Database initialized${NC}"
echo -e "${GREEN}✓ Systemd service running${NC}"
echo -e "${GREEN}✓ Nginx configured${NC}"
echo -e "${GREEN}✓ Firewall configured${NC}"
echo ""
echo -e "${BLUE}Access your application at:${NC}"
echo -e "  ${GREEN}http://$SERVER_IP/${NC}"
echo -e "  ${GREEN}http://localhost/${NC}"
echo ""
echo -e "${YELLOW}📋 Useful Commands:${NC}"
echo ""
echo -e "${BLUE}Service Management:${NC}"
echo "  sudo systemctl status $APP_NAME      # Check service status"
echo "  sudo systemctl restart $APP_NAME     # Restart service"
echo "  sudo systemctl stop $APP_NAME        # Stop service"
echo "  sudo systemctl start $APP_NAME       # Start service"
echo "  sudo journalctl -u $APP_NAME -f      # View live logs"
echo "  sudo journalctl -u $APP_NAME -n 100  # View last 100 log lines"
echo ""
echo -e "${BLUE}Application:${NC}"
echo "  source $VENV_DIR/bin/activate        # Activate virtual environment"
echo "  cd $APP_DIR                          # Go to app directory"
echo "  python run.py                        # Run manually (testing)"
echo ""
echo -e "${BLUE}Nginx:${NC}"
echo "  sudo nginx -t                        # Test Nginx config"
echo "  sudo systemctl restart nginx         # Restart Nginx"
echo "  sudo tail -f /var/log/nginx/error.log # View Nginx errors"
echo ""
echo -e "${YELLOW}⚠ Next Steps:${NC}"
echo ""
echo "1. Set up cron jobs for automated scans:"
echo "   ${BLUE}crontab -e${NC}"
echo ""
echo "   Add these lines (or use the crontab_api.txt file):"
echo ""
echo "   ${GREEN}TZ=Europe/Oslo${NC}"
echo ""
echo "   ${GREEN}# SNKRDUNK scan every 6 hours at 0, 6, 12, 18${NC}"
echo "   ${GREEN}0 6,12,18,0 * * * curl -s -X POST 'http://localhost:8000/api/v1/snkrdunk/fetch' -H 'Content-Type: application/json' -d '{\"pages\":[1,2,3],\"force_refresh\":false}' >> ~/logs/snkrdunk_api.log 2>&1${NC}"
echo ""
echo "   ${GREEN}# Competitor scans every 6 hours${NC}"
echo "   ${GREEN}0 6,12,18,0 * * * curl -s -X POST 'http://localhost:8000/api/v1/competitors/scrape-all' >> ~/logs/competitor_api.log 2>&1${NC}"
echo ""
echo "   ${GREEN}# Lekekassen supplier scan every 6 hours at :15${NC}"
echo "   ${GREEN}15 6,12,18,0 * * * curl -s -X POST 'http://localhost:8000/api/v1/suppliers/scan' -H 'Content-Type: application/json' -d '{\"website_id\":1}' >> ~/logs/lekekassen_api.log 2>&1${NC}"
echo ""
echo "   ${GREEN}# Extra Leker supplier scan every 6 hours at :30${NC}"
echo "   ${GREEN}30 6,12,18,0 * * * curl -s -X POST 'http://localhost:8000/api/v1/suppliers/scan' -H 'Content-Type: application/json' -d '{\"website_id\":2}' >> ~/logs/extra_leker_api.log 2>&1${NC}"
echo ""
echo "   ${GREEN}# Shopify collection sync - daily at 7:00 AM${NC}"
echo "   ${GREEN}0 7 * * * curl -s -X POST 'http://localhost:8000/api/v1/shopify/sync-collection/444175384827' >> ~/logs/shopify_sync_api.log 2>&1${NC}"
echo ""
echo "   Or simply: ${BLUE}cat $APP_DIR/crontab_api.txt${NC} and paste the contents"
echo ""
echo "2. (Optional) Set up SSL certificate:"
echo "   ${BLUE}sudo apt install certbot python3-certbot-nginx${NC}"
echo "   ${BLUE}sudo certbot --nginx -d your-domain.com${NC}"
echo ""
echo "3. Test the application:"
echo "   Open ${GREEN}http://$SERVER_IP/${NC} in your browser"
echo ""
echo -e "${GREEN}✨ Your Shopify Price Manager is ready!${NC}"
echo ""
