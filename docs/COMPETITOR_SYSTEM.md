# Competitor System Integration Guide

## Overview
The competitor scanning system has been fully integrated into your Shopify Price Manager. You can now:
- Scan competitor websites for product pricing and inventory
- Automatically map competitor products to your Shopify and SNKRDUNK products
- Compare competitor prices against your pricing
- Use competitor data to inform pricing strategies

## What Was Added

### Backend Components

#### 1. **API Endpoints** (`app/routers/competitors.py`)
New REST endpoints for competitor management:

**Scanning & Data**
- `POST /api/v1/competitors/scrape/{website}` - Run a specific scraper (boosterpakker, hatamontcg, laboge, lcg_cards)
- `POST /api/v1/competitors/scrape-all` - Run all scrapers simultaneously
- `GET /api/v1/competitors/` - List competitor products with filters (category, brand, website)
- `GET /api/v1/competitors/by-category/{category}` - Get all products in a category

**Analysis & Statistics**
- `GET /api/v1/competitors/stats/{normalized_name}` - Get price statistics (min/max/avg/median)
- `GET /api/v1/competitors/availability/{normalized_name}` - Get stock availability across sites

**Mapping**
- `GET /api/v1/competitors/unmapped` - List unmapped competitors with suggested matches
- `POST /api/v1/competitors/map-to-shopify` - Map competitor to Shopify product
- `POST /api/v1/competitors/map-to-snkrdunk` - Map competitor to SNKRDUNK product
- `GET /api/v1/competitors/price-comparison/{shopify_product_id}` - Compare prices

**Management**
- `POST /api/v1/competitors/override/{normalized_name}` - Create manual categorization overrides

#### 2. **Services**
**competitor_service.py**
- `get_competitor_products()` - Query with filters
- `get_price_statistics()` - Min/max/avg/median prices by website
- `get_availability_status()` - Stock status analysis
- `get_competitor_products_by_category()` - Category-based queries
- `create_override()` - Manual categorization corrections

**competitor_mapping_service.py**
- `find_matching_shopify_product()` - Auto-match by normalized name
- `find_matching_snkrdunk_product()` - Match to SNKRDUNK products
- `map_competitor_to_shopify()` - Store manual mappings
- `map_competitor_to_snkrdunk()` - Store SNKRDUNK mappings
- `get_unmapped_competitors()` - Find products without mapping
- `get_competitive_price_comparison()` - Price position analysis (underpriced/competitive/overpriced)

#### 3. **Database Models** (additions to `app/models.py`)
- `CompetitorProduct` - Core competitor product data
  - website, product_link, raw_name, normalized_name
  - price_ore, category, brand, language
  - stock_status, stock_amount

- `CompetitorProductDaily` - Daily snapshots for trend analysis
  - One record per product per calendar day
  - Tracks price, stock status, available amount

- `CompetitorProductSnapshot` - Full history of all scrapes
  - Timestamps for historical analysis

- `CompetitorProductOverride` - Manual corrections
  - Override normalized_name, category, brand, language
  - Notes for documentation

- Helper function: `today_oslo()` - Returns date in Oslo timezone

### Frontend Components

#### 1. **Competitors Tab** (new navigation option)
Access via "🔍 Competitors" button in the tab navigation

#### 2. **Competitor Scanner Section**
- **Quick Scan Buttons**: Run individual scrapers
  - 🇳🇴 Booster Pakker
  - 🎴 HataMonTCG
  - 📦 Laboge
  - 🃏 LCG Cards
- **Bulk Operations**: Scan all sites or show unmapped products
- **Status Display**: Real-time scanning status and progress

#### 3. **Competitor Products Table**
Display all scraped products with:
- Website (which competitor)
- Product name (raw and normalized)
- Category (booster_pack, booster_box, elite_trainer_box, theme_deck, etc)
- Price in NOK (converted from øre)
- Stock status
- Action buttons for mapping

#### 4. **Filters**
- Category: booster_box, booster_pack, elite_trainer_box, theme_deck
- Website: boosterpakker, hatamontcg, laboge, lcg_cards
- Brand: Text search (e.g., "Pokémon")

#### 5. **Product Mapping Section**
- Shows unmapped competitor products
- Suggests matching Shopify products (based on name similarity)
- Suggests matching SNKRDUNK products
- Map buttons to establish mappings

#### 6. **JavaScript Functions** (`app/static/app.js`)
- `loadCompetitors()` - Load and display competitor products
- `filterCompetitorProducts()` - Apply filter changes
- `runCompetitorScraper(website)` - Trigger single scraper
- `runAllCompetitorScrapers()` - Trigger all scrapers
- `loadUnmappedCompetitors()` - Show products without mapping
- `mapCompetitorProduct(id)` - Map a competitor product (UI hook)

## How to Use

### 1. **Run Competitor Scans**
```
Frontend: Click "🔍 Competitors" tab → Click any scraper button
OR: Click "Scan All Sites" to run all scrapers at once
OR: Use API: POST http://localhost:8000/api/v1/competitors/scrape/boosterpakker
```

**Supported Websites:**
- **Booster Pakker** (boosterpakker.no) - Norwegian booster product supplier
- **HataMonTCG** (hatamontcg.com) - TCG specialist
- **Laboge** - Card game retailer
- **LCG Cards** - Living card game specialist

### 2. **View Competitor Data**
```
Frontend: "Competitors" tab → "Competitor Products" section
- All products from recent scans are displayed
- Use filters to narrow down by category/website/brand
- Price is automatically converted from øre to NOK
```

### 3. **Map Products**
```
Frontend: "Competitors" tab → "Product Mapping" section
OR: Click "Show Unmapped" button

- System automatically suggests Shopify matches based on product name
- System suggests SNKRDUNK matches
- Click "Map" to establish a mapping
- Mapped products help with price comparison
```

### 4. **Analyze Competitor Prices**
```
API: GET /api/v1/competitors/price-comparison/{shopify_product_id}

Returns:
- Your Shopify price
- Competitor average, min, max prices
- Price position: "underpriced", "competitive", "overpriced"
- Suggested price adjustments
```

### 5. **View Price Statistics**
```
Frontend: Can be accessed via API or integrated into price planning
GET /api/v1/competitors/stats/{product_name}

Returns:
- Min/max/avg/median prices
- Prices by individual website
- Number of competitors selling the product
```

## Data Storage

All competitor data is stored in SQLite database with these tables:
- `competitor_product` - Core product data
- `competitor_product_daily` - Daily snapshots for price trends
- `competitor_product_snapshot` - Full history of all scans
- `competitor_product_override` - Manual categorization corrections

## Integrated Scrapers

The system uses existing scrapers from the `competition/` folder:
- `competition/boosterpakker.py` - Uses Selenium to scrape boosterpakker.no
- `competition/hatamontcg.py` - Scrapes HataMonTCG
- `competition/laboge.py` - Scrapes Laboge
- `competition/lcg_cards.py` - Scrapes LCG Cards

Each scraper:
1. Opens website in headless Chromium browser
2. Extracts product data (name, price, stock)
3. Normalizes prices to øre (Norwegian cents)
4. Detects product category and brand
5. Stores in database via `competition/pipeline.py`

## API Examples

### Run a scraper
```bash
curl -X POST http://localhost:8000/api/v1/competitors/scrape/boosterpakker
```

### Get all competitor products in a category
```bash
curl "http://localhost:8000/api/v1/competitors/?category=booster_box&limit=50"
```

### Get price statistics for a product
```bash
curl "http://localhost:8000/api/v1/competitors/stats/booster%20pack%20shiny%20treasure"
```

### Get unmapped competitors with suggestions
```bash
curl "http://localhost:8000/api/v1/competitors/unmapped?limit=20"
```

### Map a competitor product to Shopify
```bash
curl -X POST http://localhost:8000/api/v1/competitors/map-to-shopify \
  -H "Content-Type: application/json" \
  -d '{"competitor_id": 123, "shopify_product_id": 456}'
```

## Next Steps

### Coming Soon
1. **Enhanced Product Mapping UI**
   - Modal dialog for selecting Shopify/SNKRDUNK products
   - Search and filter for products
   - Save mapping with one click

2. **Price Comparison in Price Planning**
   - When generating price plans, show competitor average prices
   - Suggest adjustments to stay competitive
   - Add competitor price column to plan view

3. **Price History & Trends**
   - Track competitor price changes over time
   - Alert when competitor prices drop significantly
   - Analyze competitor pricing strategies

4. **Scheduled Scans**
   - Set up automatic daily/weekly scans
   - Get notified of major price changes
   - Export price history reports

## Troubleshooting

### Scrapers not running
- Check that Chromium/Chrome is installed on your system
- Verify network connectivity to competitor websites
- Check `apply_log.txt` for detailed error messages

### No competitor data showing
- Run a scan first: "Scan All Sites" button
- Wait for scan to complete (may take 5-10 minutes)
- Refresh the Competitors tab

### Products not mapping
- Run a scan to ensure products exist
- Click "Show Unmapped" to see products without mapping
- Manual mapping coming in next update

## Technical Notes

- Prices are stored in øre (1/100th of NOK) for precision
- Product names are normalized using fuzzy matching (Jaccard similarity)
- Categories auto-detected from product names and descriptions
- Mappings are bidirectional (competitor ↔ Shopify ↔ SNKRDUNK)
- All timestamps are in Oslo timezone (CET/CEST)

## Files Modified/Created

**New Files:**
- `app/routers/competitors.py` - API endpoint definitions
- `app/services/competitor_service.py` - Data analysis logic
- `app/services/competitor_mapping_service.py` - Product mapping logic
- `app/static/competitors.html` section in index.html (via replace)

**Modified Files:**
- `app/models.py` - Added 4 new database models + helper function
- `app/main.py` - Registered competitors router
- `app/templates/index.html` - Added Competitors tab and UI
- `app/static/app.js` - Added competitor functions
- `competition/pipeline.py` - Updated import (app.models)
- `competition/canonicalize.py` - Updated import (app.models)
- `competition/lcg_cards.py` - Updated import (app.models)

## Questions?

Check the API documentation at `http://localhost:8000/docs` while the server is running - all competitor endpoints are documented with interactive examples.
