# Shopify Price Manager - FastAPI Application

Complete refactor of the Shopify price management scripts into a modern FastAPI application with database persistence.

## Overview

This FastAPI application replaces the command-line scripts with a REST API, storing all data in a database instead of JSON files. It provides endpoints for:

- **Shopify Operations**: Fetch and sync product collections
- **SNKRDUNK Integration**: Fetch competitor pricing and match with Shopify products
- **Price Management**: Generate and apply price update plans
- **Booster Variants**: Split single variants into Box + Pack variants
- **Booster Inventory**: Convert box inventory to pack inventory
- **Reporting**: Generate stock reports and view audit logs
- **Mappings**: Manage SNKRDUNK to Shopify product mappings

## Architecture

```
app/
├── main.py              # FastAPI application entry point
├── config.py            # Application configuration
├── database.py          # Database setup and session management
├── models.py            # SQLAlchemy database models
├── schemas.py           # Pydantic request/response schemas
├── routers/             # API endpoint routers
│   ├── shopify.py
│   ├── snkrdunk.py
│   ├── price_plans.py
│   ├── booster_variants.py
│   ├── booster_inventory.py
│   ├── mappings.py
│   ├── reports.py
│   └── health.py
└── services/            # Business logic layer
    ├── shopify_service.py
    ├── snkrdunk_service.py
    ├── price_plan_service.py
    ├── booster_variant_service.py
    ├── booster_inventory_service.py
    ├── mapping_service.py
    └── report_service.py
```

## Database Schema

### Core Tables
- **products**: Shopify product data
- **variants**: Product variant data
- **snkrdunk_mappings**: SNKRDUNK to Shopify product mappings
- **translations**: Japanese to English translation cache

### Plan Tables
- **price_plans**: Price update plans
- **price_plan_items**: Individual price changes in a plan
- **booster_variant_plans**: Variant splitting plans
- **booster_variant_plan_items**: Individual variant splits
- **booster_inventory_plans**: Inventory adjustment plans
- **booster_inventory_plan_items**: Individual inventory adjustments

### Utility Tables
- **stock_reports**: Stock report snapshots
- **audit_logs**: Audit trail for all operations
- **snkrdunk_cache**: Cached SNKRDUNK API responses

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your Shopify and Google Translate credentials.

### 3. Initialize Database

```bash
# For SQLite (default)
python -c "from app.database import init_db; init_db()"

# For PostgreSQL/MySQL, update DATABASE_URL in .env first
```

### 4. Run the Application

```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. Access Documentation

- **Web Interface**: http://localhost:8000 (Modern UI for all operations)
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/api/v1/health

## API Endpoints

### Health & Config
- `GET /api/v1/health` - Health check
- `GET /api/v1/config` - Get configuration

### Shopify Operations
- `POST /api/v1/shopify/fetch-collection` - Fetch and store collection
- `GET /api/v1/shopify/products` - List products
- `GET /api/v1/shopify/products/{id}` - Get product
- `POST /api/v1/shopify/sync-collection/{collection_id}` - Sync collection

### SNKRDUNK Operations
- `POST /api/v1/snkrdunk/fetch` - Fetch SNKRDUNK data
- `POST /api/v1/snkrdunk/match-shopify` - Match with Shopify products
- `GET /api/v1/snkrdunk/cache-status` - Get cache status

### Price Plans
- `POST /api/v1/price-plans/generate` - Generate price plan
- `GET /api/v1/price-plans` - List price plans
- `GET /api/v1/price-plans/{id}` - Get price plan
- `POST /api/v1/price-plans/{id}/apply` - Apply price plan

### Booster Variants
- `POST /api/v1/booster-variants/generate-plan` - Generate variant plan
- `GET /api/v1/booster-variants/plans` - List plans
- `POST /api/v1/booster-variants/plans/{id}/apply` - Apply plan

### Booster Inventory
- `POST /api/v1/booster-inventory/generate-plan` - Generate inventory plan
- `GET /api/v1/booster-inventory/plans` - List plans
- `POST /api/v1/booster-inventory/plans/{id}/apply` - Apply plan

### Mappings & Translations
- `GET /api/v1/mappings/snkrdunk` - List SNKRDUNK mappings
- `POST /api/v1/mappings/snkrdunk` - Create mapping
- `PUT /api/v1/mappings/snkrdunk/{id}` - Update mapping
- `POST /api/v1/mappings/translations/batch` - Batch translate texts

### Reports
- `POST /api/v1/reports/stock` - Generate stock report
- `GET /api/v1/reports/stock` - List stock reports
- `GET /api/v1/reports/audit-logs` - Get audit logs
- `GET /api/v1/reports/statistics` - Get statistics

## Migration from Scripts

### Old Workflow → New API Workflow

**1. Fetch Shopify Collection**
```bash
# Old
python shopify_fetch_collection.py

# New
curl -X POST "http://localhost:8000/api/v1/shopify/fetch-collection" \
  -H "Content-Type: application/json" \
  -d '{"collection_id": "444175384827"}'
```

**2. Fetch SNKRDUNK Data**
```bash
# Old
python snkrdunk.py

# New
curl -X POST "http://localhost:8000/api/v1/snkrdunk/fetch" \
  -H "Content-Type: application/json" \
  -d '{"pages": [1,2,3,4,5,6]}'
```

**3. Generate Price Plan**
```bash
# Old
python shopify_price_updater_confirmed.py

# New
curl -X POST "http://localhost:8000/api/v1/price-plans/generate" \
  -H "Content-Type: application/json" \
  -d '{"collection_id": "444175384827"}'
```

**4. Apply Price Plan**
```bash
# Old
APPLY_CHANGES=1 CONFIRM_PLAN=path/to/plan.json python shopify_price_updater_confirmed.py

# New
curl -X POST "http://localhost:8000/api/v1/price-plans/1/apply"
```

### Data Migration

To migrate existing JSON data to the database:

1. **Import Mappings**: Use the mappings API to import from `mappings_snkrdunk_to_shopify.json`
2. **Import Translations**: Use the translations API to import from `translations_ja_en.json`
3. **Sync Products**: Use the Shopify sync endpoint to fetch current product data

## Development

### Running Tests

```bash
pytest
```

### Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

### Adding New Endpoints

1. Create/update service in `app/services/`
2. Add endpoint in appropriate router in `app/routers/`
3. Update schemas in `app/schemas.py` if needed
4. Update models in `app/models.py` if new tables needed

## Production Deployment

### Using Docker (Recommended)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Using PostgreSQL

1. Update `.env`:
```env
DATABASE_URL=postgresql://user:password@localhost:5432/shopify_db
```

2. Install PostgreSQL driver:
```bash
pip install psycopg2-binary
```

3. Run migrations:
```bash
alembic upgrade head
```

### Environment Variables

All configuration can be set via environment variables. See `.env.example` for available options.

## Key Differences from Original Scripts

1. **Database vs JSON Files**: All data stored in database instead of JSON files
2. **API vs CLI**: REST API instead of command-line interface
3. **Plan-Based Workflow**: Generate plans first, review, then apply (safer)
4. **Audit Trail**: All operations logged to audit_logs table
5. **Caching**: SNKRDUNK responses cached in database
6. **Stateful**: Plans, mappings, and translations persist across runs

## Troubleshooting

### Database Connection Issues

```bash
# Check database connection
curl http://localhost:8000/api/v1/health
```

### SNKRDUNK Cache Issues

```bash
# Clear cache
curl -X DELETE http://localhost:8000/api/v1/snkrdunk/cache
```

### View Logs

```bash
# Run with debug logging
DEBUG=true uvicorn app.main:app --reload
```

## Support

For issues or questions, refer to the API documentation at `/docs` or check the audit logs:

```bash
curl "http://localhost:8000/api/v1/reports/audit-logs?success=false"
```

## License

Same as original project.
