# Sprell.no Quick Reference

## Quick Start (3 Steps)

```bash
# 1. Add supplier to database
python add_sprell_supplier.py

# 2. Test the scraper
python test_sprell_simple.py

# 3. Run first scan (use website_id from step 1)
python suppliers/sprell.py 4
```

## Important Details

**URL**: https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon

**Stock Filter**: Only products with "På nettlager" (in stock online)

**Website ID**: 4 (adjust if different in your database)

## Files Created

- `suppliers/sprell.py` - Main scraper
- `test_sprell_simple.py` - Standalone test
- `test_sprell.py` - Integration test
- `add_sprell_supplier.py` - Database setup helper
- `SPRELL_INTEGRATION.md` - Full documentation
- `SPRELL_SUMMARY.md` - Detailed summary

## API Endpoints

### Add Supplier (if not using add_sprell_supplier.py)
```bash
curl -X POST "http://localhost:8000/api/v1/suppliers/websites" \
  -H "Content-Type: application/json" \
  -d '{"name": "Sprell", "url": "https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon", "scan_interval_hours": 6}'
```

### Trigger Scan
```bash
curl -X POST "http://localhost:8000/api/v1/suppliers/scan" \
  -H "Content-Type: application/json" \
  -d '{"website_id":4}'
```

### View Scan Results
```bash
curl "http://localhost:8000/api/v1/suppliers/scans?website_id=4"
```

## Crontab Entry

```bash
# Sprell supplier scan every 6 hours at :45
45 6,12,18,0 * * * curl -s -X POST "http://localhost:8000/api/v1/suppliers/scan" -H "Content-Type: application/json" -d '{"website_id":4}' >> ~/logs/sprell_api.log 2>&1
```

## Commands Cheat Sheet

```bash
# Add to database
python add_sprell_supplier.py

# Test without database
python test_sprell_simple.py

# Test with database
python test_sprell.py

# Manual scan
python suppliers/sprell.py 4

# Check syntax
python -m py_compile suppliers/sprell.py

# View logs
tail -f ~/logs/sprell_api.log
```

## Stock Status Logic

✓ **INCLUDED**: "På nettlager" + Green indicator  
✗ **EXCLUDED**: Out of stock online  
✗ **EXCLUDED**: Only in physical stores  

## Product Data Structure

```python
{
    "product_url": str,    # Full URL
    "name": str,           # Product name
    "in_stock": bool,      # True = "På nettlager"
    "price": float,        # NOK
    "sku": str,            # From URL
    "category": str,       # Auto-detected
    "image_url": str       # Image URL
}
```

## Categories

- `booster_box` - "booster box", "display"
- `booster_pack` - "booster", "booster-pakke"
- `elite_trainer` - "elite trainer", "etb"
- `collection_box` - "collection", "samleboks"

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No products found | Check CSS selectors, verify page loads |
| Wrong stock status | Verify "På nettlager" text exact match |
| Price errors | Check format is still "XXX,-" |
| Pagination fails | Inspect "next" button structure |

## Integration Points

- **Router**: `app/routers/suppliers.py` (scraper_map)
- **Base Class**: `suppliers/base_scraper.py`
- **Database**: Uses `SupplierProduct` model
- **Driver**: Uses `driver_setup.create_chromium_driver()`

## Monitoring

- Web UI: http://localhost:8000 → Suppliers → Scan Logs
- API: GET `/api/v1/suppliers/scans?website_id=4`
- Logs: `~/logs/sprell_api.log`

## Related Scrapers

1. Lekekassen (ID: 1) - `suppliers/lekekassen.py`
2. Extra Leker (ID: 2) - `suppliers/extra_leker.py`
3. Computersalg (ID: 3) - `suppliers/computersalg.py`
4. **Sprell (ID: 4)** - `suppliers/sprell.py` ← NEW
