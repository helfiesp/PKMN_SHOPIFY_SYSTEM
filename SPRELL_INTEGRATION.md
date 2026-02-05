# Sprell.no Supplier Integration

## Overview
Scraper for sprell.no - Norwegian toy and games retailer selling Pokemon TCG products.

## Website Details
- **Name**: Sprell
- **URL**: https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon
- **Category**: Toys and Games > Pokemon Cards
- **Stock Filter**: Only scrapes products with "På nettlager" (in stock online)

## Setup

### 1. Create Supplier Website Entry

Using the API:
```bash
curl -X POST "http://localhost:8000/api/v1/suppliers/websites" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Sprell",
    "url": "https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon",
    "scan_interval_hours": 6
  }'
```

The response will include the `id` of the created website. Note this ID for the next steps.

### 2. Test the Scraper

#### Simple Test (No Database)
```bash
python test_sprell_simple.py
```

This will:
- Navigate to the Sprell Pokemon category page
- Extract and display the first 10 products
- Show which products are in stock online
- Verify the scraper logic works

#### Full Test (With Database)
```bash
python test_sprell.py
```

Or manually:
```bash
python suppliers/sprell.py <website_id>
```

Replace `<website_id>` with the ID from step 1.

### 3. Schedule Automatic Scans

Add to crontab for automatic scanning every 6 hours:
```bash
# Sprell supplier scan every 6 hours at :45
45 6,12,18,0 * * * curl -s -X POST "http://localhost:8000/api/v1/suppliers/scan" -H "Content-Type: application/json" -d '{"website_id":4}' >> ~/logs/sprell_api.log 2>&1
```

Replace `website_id` with the actual ID from step 1.

### 4. Update API Router

Add the new scraper to `app/routers/suppliers.py`:

```python
scraper_map = {
    1: "suppliers/lekekassen.py",
    2: "suppliers/extra_leker.py",
    3: "suppliers/computersalg.py",
    4: "suppliers/sprell.py"  # Add this line
}
```

## Product Data Structure

The scraper extracts the following data for each product:

```python
{
    "product_url": str,      # Full URL to product page
    "name": str,             # Product name
    "in_stock": bool,        # True only if "På nettlager" (in stock online)
    "price": float,          # Price in NOK
    "sku": str,              # Product SKU/code (extracted from URL)
    "category": str,         # Auto-detected category (booster_pack, booster_box, etc.)
    "image_url": str         # Product image URL
}
```

## Stock Status Logic

**Important**: This scraper only includes products that are in stock online.

Sprell.no shows multiple stock statuses:
- ✓ **"På nettlager"** - In stock online → **INCLUDED**
- ✗ "Utsolgt i butikk" - Out of stock in stores → **EXCLUDED**
- ✗ "I X butikker" - Only in physical stores → **EXCLUDED**

The scraper checks for:
1. `div.StockStatus_statusColorInStock__LsCel` (green indicator)
2. Text "På nettlager" in the status label

Only products with BOTH conditions are marked as `in_stock=True`.

## HTML Structure

### Product Card
```html
<article class="CardContainer-module_cardContainer__qolR1">
  <!-- Product Name -->
  <h2 class="ProductCardTemplate_productName__P_oN8">Product Name</h2>
  
  <!-- Product URL -->
  <a class="ProductCard_cardProductNewAnchor__f4cCH" href="/product/...">
  
  <!-- Price -->
  <p class="CardPrice-module_cardPricePrice__ngXEp">229,-</p>
  
  <!-- Stock Status -->
  <div class="StockStatus_statusWrapper___i64_">
    <div class="StockStatus_status__A4H_J">
      <div class="StockStatus_statusColorInStock__LsCel"></div>
      <p class="StockStatus_label__KLPb9">På nettlager</p>
    </div>
  </div>
  
  <!-- Image -->
  <img class="CardImage-module_cardImageImage__W7YAU" src="..." />
  
  <!-- Brand (optional) -->
  <p class="ProductCardTemplate_brandName__whiuc">Pokémon</p>
</article>
```

## Category Detection

The scraper auto-detects product categories based on keywords in the name:

- **booster_box**: "booster box", "booster display", "display"
- **booster_pack**: "booster", "booster-pakke"
- **elite_trainer**: "elite trainer", "etb"
- **collection_box**: "collection", "samleboks", "collector"

## Pagination

The scraper handles pagination by:
1. Looking for "next" button with aria-label or class
2. Checking if button is disabled
3. Clicking to navigate to next page
4. Maximum of 50 pages as safety limit

## Error Handling

- Products without names or URLs are skipped
- Price extraction failures are logged but don't stop scraping
- Stock status check failures default to `in_stock=False`
- Page parsing errors are logged and scraping continues

## Logs

View scraper logs:
```bash
tail -f ~/logs/sprell_api.log
```

Or check via API:
http://localhost:8000/api/v1/suppliers/scans?website_id=4

## Monitoring

Check scan results in the web interface:
- Navigate to: http://localhost:8000
- Go to: Suppliers → Scan Logs
- Filter by "Sprell"

## Troubleshooting

### No products found
- Check if the URL is correct and accessible
- Verify the page loads product cards with class `CardContainer-module_cardContainer__qolR1`
- Run `test_sprell_simple.py` with `headless=False` to see the browser

### Stock status not detected correctly
- Verify the stock status HTML structure hasn't changed
- Check that products have `div.StockStatus_statusColorInStock__LsCel`
- Ensure the label text is exactly "På nettlager"

### Price parsing errors
- Check if price format has changed (currently expects "XXX,-")
- Verify CSS selector `p.CardPrice-module_cardPricePrice__ngXEp`

## Files Created

1. `suppliers/sprell.py` - Main scraper class
2. `test_sprell_simple.py` - Simple standalone test (no database)
3. `test_sprell.py` - Full integration test (with database)
4. `SPRELL_INTEGRATION.md` - This documentation file
