# Sprell.no Integration - Summary

## What Was Done

Added a new supplier scraper for **Sprell.no** to the Pokemon TCG scraper system. This allows automatic monitoring and price tracking of Pokemon products from Sprell.no.

## Files Created

1. **`suppliers/sprell.py`** (249 lines)
   - Main scraper class `SprellScraper` extending `BaseSupplierScraper`
   - Extracts: name, price, URL, SKU, stock status, category, image URL
   - Only includes products with "På nettlager" (in stock online)
   - Handles pagination automatically
   - Includes detailed logging and error handling

2. **`test_sprell_simple.py`** (112 lines)
   - Standalone test without database
   - Tests first 10 products from the page
   - Shows browser window for debugging (headless=False)
   - Verifies stock status detection logic

3. **`test_sprell.py`** (54 lines)
   - Full integration test with database
   - Creates supplier website entry if needed
   - Runs full scraper workflow
   - Shows scan results summary

4. **`SPRELL_INTEGRATION.md`**
   - Complete documentation
   - Setup instructions
   - API usage examples
   - Troubleshooting guide
   - HTML structure reference

## Files Modified

1. **`app/routers/suppliers.py`**
   - Added `4: "suppliers/sprell.py"` to `scraper_map`
   - Enables API endpoint to trigger Sprell scans

## Key Features

### Stock Filtering
- **Only** scrapes products with "På nettlager" (in stock online)
- Ignores products that are:
  - Out of stock online
  - Only available in physical stores
  - Completely sold out

### Stock Detection Logic
```python
# Product is in stock online if:
1. Has green indicator: div.StockStatus_statusColorInStock__LsCel
2. Label text contains: "På nettlager"
```

### Category Auto-Detection
- Booster Box: "booster box", "display"
- Booster Pack: "booster", "booster-pakke"
- Elite Trainer: "elite trainer", "etb"
- Collection Box: "collection", "samleboks"

### Pagination
- Automatically navigates through all pages
- Maximum 50 pages (safety limit)
- Handles disabled "next" buttons

## How to Use

### 1. Create Database Entry
```bash
curl -X POST "http://localhost:8000/api/v1/suppliers/websites" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sprell",
    "url": "https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon",
    "scan_interval_hours": 6
  }'
```

### 2. Test the Scraper
```bash
# Simple test (no database)
python test_sprell_simple.py

# Full test (with database)
python test_sprell.py

# Manual run
python suppliers/sprell.py 4
```

### 3. Set Up Automated Scans
Add to crontab:
```bash
# Sprell supplier scan every 6 hours at :45
45 6,12,18,0 * * * curl -s -X POST "http://localhost:8000/api/v1/suppliers/scan" -H "Content-Type: application/json" -d '{"website_id":4}' >> ~/logs/sprell_api.log 2>&1
```

### 4. Trigger Manual Scan via API
```bash
curl -X POST "http://localhost:8000/api/v1/suppliers/scan" \
  -H "Content-Type: application/json" \
  -d '{"website_id":4}'
```

## Example Output

```
Found 24 products on page 1

1. [✓ IN STOCK] Liten boks med fotballkort 1 stk - FIFA 365 Adrenalyn XL 2026
   Price: 229 NOK | Stock: På nettlager
   URL: https://www.sprell.no/product/liten-boks-med-fotballkort...

2. [✗ OUT OF STOCK] Booster-pakke, Temporal Forces
   Price: 79 NOK | Stock: Utsolgt i butikk
   URL: https://www.sprell.no/product/pokemon-booster-pakke...

Summary:
  Products found: 24
  In stock online (På nettlager): 8
  Out of stock / In stores only: 16
```

## Data Extracted Per Product

```python
{
    "product_url": "https://www.sprell.no/product/...",
    "name": "Pokémon - Booster Pack",
    "in_stock": True,              # Only True if "På nettlager"
    "price": 79.0,                 # Float, in NOK
    "sku": "820650856396",         # From URL
    "category": "booster_pack",    # Auto-detected
    "image_url": "https://cdn.sprell-no.getadigital.cloud/..."
}
```

## Architecture

```
suppliers/
├── base_scraper.py          # Base class with common functionality
├── lekekassen.py           # Lekekassen scraper
├── extra_leker.py          # Extra Leker scraper
├── computersalg.py         # Computersalg scraper
└── sprell.py               # NEW: Sprell scraper

test_sprell_simple.py       # Standalone test
test_sprell.py              # Integration test

app/routers/suppliers.py    # API endpoints (updated)
```

## Integration with Existing System

The scraper follows the exact same pattern as existing scrapers:

1. **Extends BaseSupplierScraper**
   - Inherits driver management
   - Automatic database integration
   - Standardized error handling

2. **Uses Same Data Model**
   - Compatible with SupplierProduct model
   - Works with existing API endpoints
   - Integrates with price comparison system

3. **Same Logging & Monitoring**
   - Logs to same system
   - Viewable in web interface
   - Same scan result structure

## Next Steps

1. **Create the website entry** in the database (step 1 above)
2. **Run test** to verify it works: `python test_sprell_simple.py`
3. **Add to crontab** for automatic scanning
4. **Monitor** first few scans to ensure stability

## Notes

- Website ID `4` is assumed - adjust if different in your database
- URL contains URL-encoded brand filter: `brand=pok%25C3%25A9mon`
- Scraper runs in headless mode by default (browser not visible)
- First scan may take longer as it builds initial product database

## Comparison with Other Scrapers

| Feature | Lekekassen | Extra Leker | Computersalg | **Sprell** |
|---------|------------|-------------|--------------|------------|
| Platform | Magento | Magento | Custom | Custom (React) |
| Stock Check | `div.stock.unavailable` | `span.online-stock-status` | `span.stock.green` | `div.StockStatus_statusColorInStock__LsCel` + text |
| Pagination | URL param `?p=X` | URL param `?p=X` | URL param `&page=X` | Next button click |
| Price Format | `XXX,-` | `XXX kr` | `XXX,XX` | `XXX,-` |
| SKU Source | Form data-attr | Link data-attr | Span itemprop | URL extraction |

## Troubleshooting

### Issue: No products found
**Solution**: Check if page loads correctly, verify CSS selectors haven't changed

### Issue: Stock status wrong
**Solution**: Verify "På nettlager" text is exact match, check for class changes

### Issue: Pagination not working
**Solution**: Inspect "next" button structure, may need to adjust selectors

### Issue: Price parsing errors
**Solution**: Check if price format has changed from "XXX,-" format

## Contact

For issues or questions about the Sprell scraper, refer to:
- `SPRELL_INTEGRATION.md` - Full documentation
- `suppliers/sprell.py` - Source code with comments
- `test_sprell_simple.py` - Example usage
