# Deployment Guide: Moving Webapp to Ubuntu Server

## Overview
This guide walks you through deploying your Shopify webapp from Windows to Ubuntu server.

---

## Part 1: Transfer Files to Ubuntu

### Option A: Using Git (Recommended)

```bash
# On Windows - commit and push your code
git init
git add .
git commit -m "Initial commit for deployment"
git remote add origin <your-repo-url>
git push -u origin main

# On Ubuntu - clone the repository
cd /var/www
sudo mkdir shopify-app
sudo chown $USER:$USER shopify-app
cd shopify-app
git clone <your-repo-url> .
```

### Option B: Using SCP/SFTP

```bash
# On Windows (PowerShell) - transfer files
# Replace USER and SERVER_IP with your Ubuntu server details
scp -r C:\Users\cmhag\Documents\Projects\Shopify USER@SERVER_IP:/home/USER/shopify-app

# Or use WinSCP / FileZilla GUI for easier transfer
```

### Option C: Using rsync (if available)

```bash
# On Windows with WSL or rsync installed
rsync -avz --exclude='__pycache__' --exclude='*.db' --exclude='venv/' \
  /mnt/c/Users/cmhag/Documents/Projects/Shopify/ \
  USER@SERVER_IP:/home/USER/shopify-app/
```

---

## Part 2: Set Up Ubuntu Server

### 1. Connect to Your Ubuntu Server

```bash
ssh USER@SERVER_IP
```

### 2. Install System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.11+ and pip
sudo apt install python3 python3-pip python3-venv -y

# Install Chrome/Chromium for Selenium (for competitor scraping)
sudo apt install chromium-browser chromium-chromedriver -y

# Install nginx (web server/reverse proxy)
sudo apt install nginx -y

# Install supervisor (process manager)
sudo apt install supervisor -y
```

### 3. Navigate to Your App Directory

```bash
cd /home/USER/shopify-app
# Or wherever you transferred the files
```

### 4. Create Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

### 5. Set Up Environment Variables

```bash
# Create .env file
nano .env
```

Add your environment variables:

```env
# Shopify API
SHOPIFY_SHOP_URL=your-shop.myshopify.com
SHOPIFY_ACCESS_TOKEN=your_access_token

# Database (optional - defaults to SQLite)
DATABASE_URL=sqlite:///./shopify_app.db

# Server
HOST=0.0.0.0
PORT=8000

# Chrome driver (for competitor scraping)
CHROMEDRIVER_PATH=/usr/bin/chromedriver
```

### 6. Initialize Database

```bash
# Activate venv if not already
source venv/bin/activate

# Create database
python -c "from app.database import engine, Base; Base.metadata.create_all(engine); print('Database created')"
```

---

## Part 3: Configure System Services

### 1. Create Systemd Service File

```bash
sudo nano /etc/systemd/system/shopify-app.service
```

Add this content (adjust paths as needed):

```ini
[Unit]
Description=Shopify Price Management App
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/shopify-app
Environment="PATH=/home/YOUR_USERNAME/shopify-app/venv/bin"
ExecStart=/home/YOUR_USERNAME/shopify-app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Important:** Replace `YOUR_USERNAME` with your actual Ubuntu username.

### 2. Enable and Start the Service

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable service to start on boot
sudo systemctl enable shopify-app

# Start the service
sudo systemctl start shopify-app

# Check status
sudo systemctl status shopify-app

# View logs
sudo journalctl -u shopify-app -f
```

---

## Part 4: Configure Nginx Reverse Proxy

### 1. Create Nginx Configuration

```bash
sudo nano /etc/nginx/sites-available/shopify-app
```

Add this configuration:

```nginx
server {
    listen 80;
    server_name YOUR_DOMAIN_OR_IP;

    client_max_body_size 10M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support (if needed)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Static files (optional - serves them directly)
    location /static/ {
        alias /home/YOUR_USERNAME/shopify-app/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }
}
```

### 2. Enable the Site

```bash
# Create symbolic link
sudo ln -s /etc/nginx/sites-available/shopify-app /etc/nginx/sites-enabled/

# Test nginx configuration
sudo nginx -t

# Restart nginx
sudo systemctl restart nginx
```

---

## Part 5: Set Up SSL (Optional but Recommended)

```bash
# Install certbot
sudo apt install certbot python3-certbot-nginx -y

# Get SSL certificate (replace with your domain)
sudo certbot --nginx -d your-domain.com

# Auto-renewal is set up automatically
# Test renewal:
sudo certbot renew --dry-run
```

---

## Part 6: Firewall Configuration

```bash
# Enable UFW firewall
sudo ufw enable

# Allow SSH (IMPORTANT - do this first!)
sudo ufw allow ssh

# Allow HTTP and HTTPS
sudo ufw allow 'Nginx Full'

# Check status
sudo ufw status
```

---

## Part 7: Useful Management Commands

### Restart the App

```bash
sudo systemctl restart shopify-app
```

### View Logs

```bash
# Real-time logs
sudo journalctl -u shopify-app -f

# Last 100 lines
sudo journalctl -u shopify-app -n 100

# Today's logs
sudo journalctl -u shopify-app --since today
```

### Stop/Start the App

```bash
sudo systemctl stop shopify-app
sudo systemctl start shopify-app
```

### Update the App

```bash
cd /home/YOUR_USERNAME/shopify-app

# Pull latest code (if using git)
git pull

# Activate venv
source venv/bin/activate

# Update dependencies if needed
pip install -r requirements.txt

# Restart service
sudo systemctl restart shopify-app
```

---

## Part 8: Troubleshooting

### App Won't Start

1. Check logs:
   ```bash
   sudo journalctl -u shopify-app -n 50
   ```

2. Test manually:
   ```bash
   cd /home/YOUR_USERNAME/shopify-app
   source venv/bin/activate
   uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

3. Check permissions:
   ```bash
   ls -la /home/YOUR_USERNAME/shopify-app
   ```

### Database Issues

```bash
# Check database file
ls -la shopify_app.db

# Reset database (WARNING: deletes all data)
rm shopify_app.db
python -c "from app.database import engine, Base; Base.metadata.create_all(engine)"
```

### Nginx Issues

```bash
# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log
```

### Port Already in Use

```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill process
sudo kill -9 <PID>
```

---

## Part 9: Production Best Practices

### 1. Set Up Log Rotation

```bash
sudo nano /etc/logrotate.d/shopify-app
```

Add:

```
/var/log/shopify-app/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 YOUR_USERNAME YOUR_USERNAME
    sharedscripts
}
```

### 2. Set Up Automated Backups

```bash
# Create backup script
nano ~/backup-shopify.sh
```

Add:

```bash
#!/bin/bash
BACKUP_DIR="/home/YOUR_USERNAME/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# Backup database
cp /home/YOUR_USERNAME/shopify-app/shopify_app.db "$BACKUP_DIR/db_$DATE.db"

# Backup data files
tar -czf "$BACKUP_DIR/data_$DATE.tar.gz" /home/YOUR_USERNAME/shopify-app/data/

# Keep only last 30 days
find $BACKUP_DIR -type f -mtime +30 -delete

echo "Backup completed: $DATE"
```

Make executable and add to cron:

```bash
chmod +x ~/backup-shopify.sh

# Edit crontab
crontab -e

# Add daily backup at 2 AM
0 2 * * * /home/YOUR_USERNAME/backup-shopify.sh
```

### 3. Monitor Application

```bash
# Install monitoring tools
sudo apt install htop iotop -y

# Monitor resources
htop
```

---

## Quick Command Reference

```bash
# Service Management
sudo systemctl start shopify-app      # Start
sudo systemctl stop shopify-app       # Stop
sudo systemctl restart shopify-app    # Restart
sudo systemctl status shopify-app     # Status
sudo journalctl -u shopify-app -f     # Logs

# Nginx Management
sudo systemctl restart nginx          # Restart nginx
sudo nginx -t                         # Test config

# Application Updates
cd /home/YOUR_USERNAME/shopify-app
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart shopify-app
```

---

## Access Your App

After successful deployment, access your app at:

- **HTTP:** `http://YOUR_SERVER_IP/`
- **HTTPS (if SSL configured):** `https://YOUR_DOMAIN/`

Your FastAPI docs will be at:
- `http://YOUR_SERVER_IP/docs`
- `http://YOUR_SERVER_IP/redoc`

---

## Need Help?

Common issues:
1. **502 Bad Gateway:** App not running - check `sudo systemctl status shopify-app`
2. **Connection refused:** Firewall blocking - check `sudo ufw status`
3. **Database errors:** Permissions issue - check file ownership
4. **Selenium/Chrome errors:** Install chromium - `sudo apt install chromium-browser chromium-chromedriver`
