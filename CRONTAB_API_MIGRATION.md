# Crontab Migration Guide: API-Based Scheduling

## Overview
This guide explains how to migrate from direct script execution to API-based cron jobs. This approach provides better logging, error handling, and monitoring through the centralized API framework.

## Benefits of API-Based Cron Jobs
1. **Centralized Logging**: All scan activities logged through the API's SupplierScanLog system
2. **Better Error Handling**: Consistent error tracking and reporting
3. **Database Integration**: Automatic scan log creation with timing and statistics
4. **Monitoring**: View scan history through the web interface
5. **Consistency**: Same code path whether triggered manually or via cron

## Prerequisites
- FastAPI application must be running on the server
- Default port: 8000 (configured in `run.py`)
- API should be started on boot or via systemd

## Installation Steps

### 1. Ensure API is Running
```bash
# Check if API is running
curl http://localhost:8000/api/v1/health

# If not running, start it (use systemd for production)
cd ~/software/PKMN_SHOPIFY_SYSTEM
source ~/software/venv/bin/activate
nohup python run.py > ~/logs/api.log 2>&1 &
```

### 2. Install New Crontab
```bash
# Backup existing crontab
crontab -l > ~/crontab_backup_$(date +%Y%m%d).txt

# Edit crontab
crontab -e

# Paste the contents from crontab_api.txt
# Save and exit
```

### 3. Verify Cron Jobs Are Scheduled
```bash
# List active cron jobs
crontab -l

# Check cron logs (varies by system)
grep CRON /var/log/syslog
```

## Updated Cron Schedule

### SNKRDUNK Scan (Every 6 hours at 0, 6, 12, 18)
```bash
0 6,12,18,0 * * * curl -X POST "http://localhost:8000/api/v1/snkrdunk/fetch" -H "Content-Type: application/json" -d '{"pages":[1,2,3],"force_refresh":false}' >> ~/logs/snkrdunk_api_cron.log 2>&1
```
- **Endpoint**: `/api/v1/snkrdunk/fetch`
- **Method**: POST
- **Payload**: `{"pages":[1,2,3],"force_refresh":false}`
- **Log**: `~/logs/snkrdunk_api_cron.log`

### Competitor Scan (Every 6 hours at 0, 6, 12, 18)
```bash
0 6,12,18,0 * * * curl -X POST "http://localhost:8000/api/v1/competitors/scrape-all" >> ~/logs/competitor_api_cron.log 2>&1
```
- **Endpoint**: `/api/v1/competitors/scrape-all`
- **Method**: POST
- **Log**: `~/logs/competitor_api_cron.log`

### Lekekassen Supplier Scan (Every 6 hours at :15)
```bash
15 6,12,18,0 * * * curl -X POST "http://localhost:8000/api/v1/suppliers/scan" -H "Content-Type: application/json" -d '{"website_id":1}' >> ~/logs/lekekassen_api_cron.log 2>&1
```
- **Endpoint**: `/api/v1/suppliers/scan`
- **Method**: POST
- **Payload**: `{"website_id":1}` (Lekekassen)
- **Log**: `~/logs/lekekassen_api_cron.log`

### Extra Leker Supplier Scan (Every 6 hours at :30)
```bash
30 6,12,18,0 * * * curl -X POST "http://localhost:8000/api/v1/suppliers/scan" -H "Content-Type: application/json" -d '{"website_id":2}' >> ~/logs/extra_leker_api_cron.log 2>&1
```
- **Endpoint**: `/api/v1/suppliers/scan`
- **Method**: POST
- **Payload**: `{"website_id":2}` (Extra Leker)
- **Log**: `~/logs/extra_leker_api_cron.log`

### Shopify Stock Sync (Daily at 7 AM)
```bash
0 7 * * * cd ~/software/PKMN_SHOPIFY_SYSTEM && source ~/software/venv/bin/activate && python shopify_stock_report.py >> ~/logs/shopify_sync_cron.log 2>&1
```
- **Note**: Still uses direct script execution (no API endpoint yet)

### Log Cleanup (Daily at 3 AM)
```bash
0 3 * * * find ~/logs -name "*.log" -type f -mtime +30 -delete
```
- Removes log files older than 30 days

## Monitoring

### Check API Logs
```bash
# View real-time API logs
tail -f ~/logs/api.log

# View specific cron job logs
tail -f ~/logs/lekekassen_api_cron.log
tail -f ~/logs/extra_leker_api_cron.log
tail -f ~/logs/competitor_api_cron.log
tail -f ~/logs/snkrdunk_api_cron.log
```

### Check Scan Logs via API
```bash
# View recent supplier scans
curl http://localhost:8000/api/v1/suppliers/scan-logs

# View specific scan log
curl http://localhost:8000/api/v1/suppliers/scan-logs/{log_id}

# View competitor scan logs
curl http://localhost:8000/api/v1/competitors/scan-logs

# View SNKRDUNK scan logs
curl http://localhost:8000/api/v1/snkrdunk/scan-logs
```

### Web Interface
Navigate to `http://your-server:8000` and check the supplier/competitor sections for scan history.

## Troubleshooting

### Cron Job Not Running
```bash
# Check if cron service is running
systemctl status cron

# Check cron logs
grep CRON /var/log/syslog | tail -20

# Test the curl command manually
curl -X POST "http://localhost:8000/api/v1/suppliers/scan" \
  -H "Content-Type: application/json" \
  -d '{"website_id":1}'
```

### API Not Responding
```bash
# Check if API is running
ps aux | grep "python run.py"

# Check API port
netstat -tlnp | grep 8000

# Restart API
cd ~/software/PKMN_SHOPIFY_SYSTEM
source ~/software/venv/bin/activate
pkill -f "python run.py"
nohup python run.py > ~/logs/api.log 2>&1 &
```

### No Scan Logs in Database
1. Check cron log files for curl errors
2. Verify API is accessible: `curl http://localhost:8000/api/v1/health`
3. Check API logs: `tail -f ~/logs/api.log`
4. Ensure database is writable
5. Check ChromeDriver path in environment

### Scan Timing Out
- Default timeout: 30 minutes per supplier scan
- Check `~/logs/lekekassen_api_cron.log` or `~/logs/extra_leker_api_cron.log`
- Verify ChromeDriver is working: `/usr/bin/chromedriver --version`
- Check website accessibility

## Environment Variables

The API automatically sets these defaults, but they can be overridden:

```bash
# On Ubuntu server
export CHROMEDRIVER_PATH=/usr/bin/chromedriver

# On Windows (for testing)
export CHROMEDRIVER_PATH="C:\\Users\\cmhag\\Documents\\Projects\\Shopify\\chromedriver-win64\\chromedriver.exe"
```

## Systemd Service (Recommended for Production)

For auto-starting the API on boot, create a systemd service:

```bash
sudo nano /etc/systemd/system/shopify-api.service
```

```ini
[Unit]
Description=Shopify Price Manager API
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/home/your-username/software/PKMN_SHOPIFY_SYSTEM
Environment="PATH=/home/your-username/software/venv/bin"
Environment="CHROMEDRIVER_PATH=/usr/bin/chromedriver"
ExecStart=/home/your-username/software/venv/bin/python run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable shopify-api
sudo systemctl start shopify-api
sudo systemctl status shopify-api
```

## Migration Checklist

- [ ] API is running and accessible on port 8000
- [ ] Backup existing crontab
- [ ] Install new crontab from `crontab_api.txt`
- [ ] Verify cron jobs are scheduled: `crontab -l`
- [ ] Test one endpoint manually with curl
- [ ] Wait for next scheduled run and check logs
- [ ] Verify scan logs appear in database
- [ ] Monitor for 24 hours to ensure all scans run
- [ ] Set up systemd service for API auto-start (optional but recommended)

## Rollback

If issues occur, restore the old crontab:

```bash
crontab ~/crontab_backup_YYYYMMDD.txt
```

## Next Steps

1. **Create Shopify Sync API Endpoint**: Convert `shopify_stock_report.py` to an API endpoint
2. **Add Health Checks**: Monitor API uptime and scan success rates
3. **Alerting**: Set up email/webhook notifications for failed scans
4. **Dashboard**: Add scan status visualization to web interface
