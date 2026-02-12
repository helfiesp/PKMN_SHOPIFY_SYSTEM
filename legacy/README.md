# Legacy Scripts

This folder contains archived CLI scripts from before the FastAPI migration. These are kept for reference but should **not be used** in production.

## ⚠️ Deprecation Notice

All functionality from these legacy scripts has been reimplemented in the modern FastAPI application (`../app/`).

## Scripts

- **main.py** - Legacy interactive menu system
- **snkrdunk.py** - SNKRDUNK data fetcher (replaced by `app/services/snkrdunk_service.py`)
- **shopify_price_updater_confirmed.py** - Price updater (replaced by `app/services/price_plan_service.py`)
- **shopify_booster_variants.py** - Variant splitter (replaced by `app/services/booster_variant_service.py`)
- **shopify_booster_inventory_split.py** - Inventory converter
- **shopify_fetch_collection.py** - Collection fetcher (replaced by `app/services/shopify_service.py`)
- **shopify_stock_report.py** - Stock reporter (replaced by `app/routers/reports.py`)

## Migration Status

✅ All legacy scripts have been successfully migrated to the FastAPI application.

Use the web interface at http://localhost:8000 or the REST API instead.
