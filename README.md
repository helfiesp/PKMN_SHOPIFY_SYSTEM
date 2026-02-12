# Shopify E-Commerce Pricing & Inventory Management System

A FastAPI-based REST API application for managing Shopify e-commerce pricing and inventory with competitive analysis capabilities for Pokemon TCG products.

## 🚀 Quick Start

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

3. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

4. **Start the server:**
   ```bash
   python run.py
   ```

5. **Access the web interface:**
   - Main UI: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## 📁 Project Structure

```
├── app/                    # FastAPI application (main codebase)
│   ├── routers/           # API endpoints
│   ├── services/          # Business logic
│   ├── models.py          # Database models
│   ├── schemas.py         # Pydantic schemas
│   └── static/            # Frontend assets
├── competition/           # Competitor scraping modules
├── suppliers/             # Supplier tracking modules
├── alembic/              # Database migrations
├── legacy/               # Legacy CLI scripts (archived)
├── scripts/              # Utility & test scripts
├── docs/                 # Documentation files
├── deployment/           # Deployment configs & scripts
├── logs/                 # Log files
├── data/                 # Historical JSON data
├── shopify/              # Cached Shopify snapshots
├── database.py           # Database compatibility shim (required by competition/suppliers)
└── run.py                # Application entry point
```

## 🔑 Key Features

- **Automated Pricing Engine** - SNKRDUNK integration with exchange rates
- **Competitor Monitoring** - Track 7+ competitor websites
- **Booster Box/Pack Management** - Automatic variant splitting
- **Price Planning** - Review-before-apply workflow
- **Supplier Integration** - Track supplier stock and pricing
- **REST API** - Full OpenAPI documentation
- **Web Interface** - Interactive management dashboard

## 📚 Documentation

See the [docs/](docs/) folder for detailed documentation:

- [Quick Start Guide](docs/QUICKSTART.md)
- [API Documentation](docs/README_API.md)
- [Project Structure](docs/PROJECT_STRUCTURE.md)
- [Deployment Guide](docs/DEPLOYMENT_GUIDE.md)
- [Competitor System](docs/COMPETITOR_SYSTEM.md)
- [Supplier Tracking](docs/SUPPLIER_TRACKING.md)

## 🛠️ Development

### Running Tests
```bash
python scripts/test_api_endpoints.py
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head
```

## 📦 Deployment

See [deployment/](deployment/) folder for deployment scripts and configurations:

- `deploy.sh` - Standard deployment script
- `deploy-robust.sh` - Robust deployment with health checks
- `Dockerfile` - Docker container configuration
- `docker-compose.example.yml` - Docker Compose template

## 🗄️ Legacy Scripts

Legacy CLI scripts are archived in the [legacy/](legacy/) folder. The modern FastAPI application in `app/` should be used instead.

## 📄 License

Internal project - All rights reserved
