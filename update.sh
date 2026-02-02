#!/bin/bash

# Update script - run this when you need to deploy new changes

set -e

APP_DIR="/home/$USER/shopify-app"
SERVICE_NAME="shopify-app"

echo "=== Updating Shopify App ==="

cd $APP_DIR

# Pull latest changes (if using git)
if [ -d ".git" ]; then
    echo "Pulling latest changes from git..."
    git pull
fi

# Activate virtual environment
source venv/bin/activate

# Update dependencies
echo "Updating dependencies..."
pip install -r requirements.txt

# Run any database migrations if needed
# alembic upgrade head

# Restart service
echo "Restarting application..."
sudo systemctl restart $SERVICE_NAME

# Wait and check status
sleep 3
sudo systemctl status $SERVICE_NAME --no-pager

echo ""
echo "✓ Update complete!"
echo ""
echo "Check logs: sudo journalctl -u $SERVICE_NAME -f"
