# Deployment Files

This folder contains deployment configurations and scripts.

## Deployment Scripts

### deploy.sh
Standard deployment script for Linux/Unix systems.

```bash
./deploy.sh
```

### deploy-robust.sh
Enhanced deployment with health checks and rollback support.

```bash
./deploy-robust.sh
```

### update.sh
Quick update script for minor changes.

```bash
./update.sh
```

## Configuration Files

### Dockerfile
Docker container configuration for the application.

```bash
docker build -t shopify-app .
docker run -p 8000:8000 shopify-app
```

### docker-compose.example.yml
Docker Compose template for multi-container deployment.

```bash
cp docker-compose.example.yml docker-compose.yml
# Edit docker-compose.yml with your settings
docker-compose up -d
```

### crontab_api.txt
Cron job configuration for scheduled tasks (competitor scraping).

```bash
crontab < crontab_api.txt
```

## Deployment Checklist

1. ✅ Update environment variables in `.env`
2. ✅ Run database migrations: `alembic upgrade head`
3. ✅ Test API endpoints: `python scripts/test_api_endpoints.py`
4. ✅ Configure cron jobs (if using scheduled scraping)
5. ✅ Set up SSL/HTTPS (production)
6. ✅ Configure firewall rules
7. ✅ Set up monitoring/logging

See [../docs/DEPLOYMENT_GUIDE.md](../docs/DEPLOYMENT_GUIDE.md) for detailed instructions.
