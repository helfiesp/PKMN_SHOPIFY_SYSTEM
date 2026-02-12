# Project Structure Overview

## Complete FastAPI Application Structure

```
Shopify/
├── app/                              # Main application package
│   ├── __init__.py                  # Package init
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # Configuration management
│   ├── database.py                  # Database setup & session
│   ├── models.py                    # SQLAlchemy database models
│   ├── schemas.py                   # Pydantic request/response schemas
│   │
│   ├── routers/                     # API endpoint routers
│   │   ├── __init__.py
│   │   ├── health.py               # Health & config endpoints
│   │   ├── shopify.py              # Shopify operations
│   │   ├── snkrdunk.py             # SNKRDUNK operations
│   │   ├── price_plans.py          # Price plan management
│   │   ├── booster_variants.py     # Booster variant splitting
│   │   ├── booster_inventory.py    # Booster inventory management
│   │   ├── mappings.py             # Mappings & translations
│   │   └── reports.py              # Reports & audit logs
│   │
│   └── services/                    # Business logic layer
│       ├── __init__.py
│       ├── shopify_service.py      # Shopify GraphQL operations
│       ├── snkrdunk_service.py     # SNKRDUNK integration
│       ├── price_plan_service.py   # Price plan logic
│       ├── booster_variant_service.py    # Variant splitting logic
│       ├── booster_inventory_service.py  # Inventory adjustment logic
│       ├── mapping_service.py      # Mapping & translation logic
│       └── report_service.py       # Reporting logic
│
├── alembic/                         # Database migrations
│   └── versions/
│       └── 001_initial.py
│
├── data/                            # Legacy JSON files (reference)
│   ├── mappings_snkrdunk_to_shopify.json
│   ├── translations_ja_en.json
│   └── *.json (historical data)
│
├── shopify/                         # Legacy Shopify snapshots (reference)
│   └── collection_*.json
│
├── Legacy Scripts (reference only):
│   ├── main.py                      # Old CLI menu
│   ├── shopify_fetch_collection.py
│   ├── snkrdunk.py
│   ├── shopify_price_updater_confirmed.py
│   ├── shopify_booster_variants.py
│   ├── shopify_booster_inventory_split.py
│   └── shopify_stock_report.py
│
├── Configuration Files:
│   ├── requirements.txt             # Python dependencies
│   ├── .env.example                # Environment variables template
│   ├── .gitignore                  # Git ignore rules
│   ├── alembic.ini                 # Alembic configuration
│   └── run.py                      # Startup script
│
└── Documentation:
    ├── README_API.md               # Full API documentation
    └── QUICKSTART.md               # Quick start guide
```

## Database Schema Summary

### Products & Variants
- **products**: Shopify products (id, shopify_id, title, handle, status, collection_id, etc.)
- **variants**: Product variants (id, shopify_id, product_id, price, sku, inventory, etc.)

### Mappings & Translations
- **snkrdunk_mappings**: SNKRDUNK key → Shopify product mapping
- **translations**: Japanese → English translation cache

### Plans
- **price_plans**: Price update plans (metadata, status, fx_rate, rules)
- **price_plan_items**: Individual price changes in plan
- **booster_variant_plans**: Variant splitting plans
- **booster_variant_plan_items**: Individual variant splits
- **booster_inventory_plans**: Inventory adjustment plans
- **booster_inventory_plan_items**: Individual inventory adjustments

### Reporting & Caching
- **stock_reports**: Stock report snapshots
- **audit_logs**: Complete audit trail
- **snkrdunk_cache**: Cached SNKRDUNK API responses

## API Endpoint Summary

### Base URL: `http://localhost:8000/api/v1`

#### Health & Configuration
- `GET /health` - Check API health
- `GET /config` - Get configuration

#### Shopify Operations  
- `POST /shopify/fetch-collection` - Fetch & store collection
- `GET /shopify/products` - List products
- `GET /shopify/products/{id}` - Get product
- `POST /shopify/sync-collection/{id}` - Sync collection

#### SNKRDUNK Operations
- `POST /snkrdunk/fetch` - Fetch SNKRDUNK data
- `POST /snkrdunk/match-shopify` - Match with Shopify
- `GET /snkrdunk/cache-status` - Cache status
- `DELETE /snkrdunk/cache` - Clear cache

#### Price Plans
- `POST /price-plans/generate` - Generate plan
- `GET /price-plans` - List plans
- `GET /price-plans/{id}` - Get plan details
- `POST /price-plans/{id}/apply` - Apply plan
- `POST /price-plans/{id}/cancel` - Cancel plan
- `DELETE /price-plans/{id}` - Delete plan

#### Booster Variants
- `POST /booster-variants/generate-plan` - Generate plan
- `GET /booster-variants/plans` - List plans
- `GET /booster-variants/plans/{id}` - Get plan
- `POST /booster-variants/plans/{id}/apply` - Apply plan

#### Booster Inventory
- `POST /booster-inventory/generate-plan` - Generate plan
- `GET /booster-inventory/plans` - List plans
- `GET /booster-inventory/plans/{id}` - Get plan
- `POST /booster-inventory/plans/{id}/apply` - Apply plan

#### Mappings & Translations
- `GET /mappings/snkrdunk` - List mappings
- `POST /mappings/snkrdunk` - Create mapping
- `PUT /mappings/snkrdunk/{id}` - Update mapping
- `DELETE /mappings/snkrdunk/{id}` - Delete mapping
- `GET /mappings/translations` - List translations
- `POST /mappings/translations/batch` - Batch translate

#### Reports
- `POST /reports/stock` - Generate stock report
- `GET /reports/stock` - List stock reports
- `GET /reports/audit-logs` - View audit logs
- `GET /reports/statistics` - Get statistics

## Key Features

### 1. Database Persistence
- All data stored in database (SQLite/PostgreSQL/MySQL)
- No more JSON file management
- Proper relationships and constraints
- Transaction support

### 2. Plan-Based Workflow
- Generate plans first (review before applying)
- Plans stored in database for audit
- Can apply, cancel, or delete plans
- Track application status per item

### 3. Comprehensive Audit Trail
- Every operation logged to audit_logs table
- Track success/failure
- Store detailed operation data
- Query by operation, entity, date, etc.

### 4. API-First Design
- RESTful API endpoints
- Interactive documentation (Swagger UI)
- Request/response validation
- Proper error handling

### 5. Caching
- SNKRDUNK responses cached in database
- Translation cache
- Configurable TTL

### 6. Service Layer Architecture
- Clean separation of concerns
- Routers handle HTTP
- Services handle business logic
- Models define data structure

## Migration Path

### Phase 1: Setup
1. Install dependencies: `pip install -r requirements.txt`
2. Configure `.env` file with credentials
3. Initialize database: `python -c "from app.database import init_db; init_db()"`

### Phase 2: Data Migration (Optional)
1. Import mappings from JSON to database
2. Import translations from JSON to database
3. Sync products from Shopify

### Phase 3: Testing
1. Start API: `python run.py`
2. Test endpoints with Swagger UI: http://localhost:8000/docs
3. Verify operations work correctly

### Phase 4: Deployment
1. Switch to PostgreSQL for production
2. Set up proper environment variables
3. Run behind reverse proxy (nginx)
4. Set up monitoring and logging

## Next Steps

### Immediate
1. Test the API locally
2. Verify Shopify operations work
3. Test SNKRDUNK fetching
4. Review generated plans before applying

### Short Term
1. Implement remaining TODO items in service files
2. Add authentication/authorization
3. Add rate limiting
4. Implement proper error handling for all edge cases

### Long Term
1. Add automated tests
2. Set up CI/CD pipeline
3. Add monitoring/alerting
4. Build web UI on top of API
5. Add webhooks for Shopify events

## Development Workflow

### Adding New Features
1. Define data model in `models.py`
2. Create Pydantic schemas in `schemas.py`
3. Implement business logic in appropriate service
4. Add endpoints in appropriate router
5. Test via Swagger UI
6. Document in README

### Making Database Changes
1. Update models in `models.py`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review migration file
4. Apply: `alembic upgrade head`

## Support & Documentation

- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/api/v1/health
- **Configuration**: http://localhost:8000/api/v1/config
- **README**: README_API.md
- **Quick Start**: QUICKSTART.md
