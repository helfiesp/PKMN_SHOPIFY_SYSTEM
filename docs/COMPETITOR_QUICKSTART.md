# Quick Start: Competitor Scanner

## Get Started in 5 Minutes

### Step 1: Ensure Server is Running
```powershell
cd c:\Users\cmhag\Documents\Projects\Shopify
python run.py
```
You should see: `Uvicorn running on http://0.0.0.0:8000`

### Step 2: Open Browser
Navigate to: **http://localhost:8000**

### Step 3: Click Competitors Tab
Click the **🔍 Competitors** button in the navigation bar

### Step 4: Start Scanning
You have three options:

**Option A: Scan One Site**
Click any of these buttons:
- 🇳🇴 Booster Pakker (Norwegian supplier)
- 🎴 HataMonTCG (TCG specialist)
- 📦 Laboge (Card retailer)
- 🃏 LCG Cards (Living card games)

**Option B: Scan All Sites at Once**
Click **Scan All Sites** button

### Step 5: Wait for Completion
A status message shows the scan is in progress. Each scan takes 2-5 minutes depending on the website.

### Step 6: View Results
Once complete, the **Competitor Products** section below will show:
- Website name
- Product name (raw and normalized)
- Category (auto-detected: booster_box, booster_pack, etc.)
- Price in NOK
- Stock status
- A "Map" button for each product

## Using Filters

**After scanning, you can filter products:**

1. **Category Filter**: Choose from
   - All Categories
   - Booster Box
   - Booster Pack
   - Elite Trainer Box
   - Theme Deck

2. **Website Filter**: Show only from specific site
   - All Websites
   - Booster Pakker
   - HataMonTCG
   - Laboge
   - LCG Cards

3. **Brand Filter**: Type a brand name (e.g., "Pokémon")

Press Enter or click elsewhere to apply filters.

## Mapping Products

### See Unmapped Products
1. Click **Show Unmapped** button
2. View products that don't have mappings yet
3. System shows suggested Shopify products (based on name similarity)
4. System shows suggested SNKRDUNK products

### Map a Product
1. Click **Map** button next to any product
2. (Coming soon) Select or search for the correct Shopify/SNKRDUNK product
3. Click Save

**Tip**: The more products you map, the better the system can provide price comparison insights!

## Using the API

### Get All Competitors (via command line)
```bash
curl "http://localhost:8000/api/v1/competitors/"
```

### Get Competitors in a Category
```bash
curl "http://localhost:8000/api/v1/competitors/?category=booster_box"
```

### Get Price Statistics for a Product
```bash
curl "http://localhost:8000/api/v1/competitors/stats/booster%20pack%20shiny%20treasure"
```

### View Interactive API Docs
Open: **http://localhost:8000/docs**

Click "Try it out" on any endpoint to test it!

## Understanding Prices

**Prices in the system are stored and displayed in NOK (Norwegian Krone)**

- 1 NOK = 100 øre
- In the database, prices are stored in øre (e.g., 129900 = 1299,00 kr)
- In the UI, automatically converted to readable format (e.g., "1299.00 kr")

## Common Questions

**Q: How often should I scan?**
A: As often as you want! Daily scans help track price trends. Start with weekly scans to get a sense of competitor prices.

**Q: Do scans happen automatically?**
A: Not yet, but you can trigger them manually anytime. Automatic scheduled scanning coming in next update!

**Q: Why are some products "unmapped"?**
A: They haven't been linked to your Shopify or SNKRDUNK products yet. The system suggests matches, but you can manually map them too.

**Q: Can I use competitor prices in my price plans?**
A: Yes! Once products are mapped, the price comparison API shows you competitor average prices. Integration with price planning is coming next.

**Q: How long do scans take?**
A: Typically 2-5 minutes per site depending on how many products they have.

**Q: What if a scraper fails?**
A: It will show an error message. Check that:
- Your internet connection is working
- The competitor website is online
- Chromium/Chrome is installed on your PC

## Tips & Tricks

**Tip 1: Find Unmapped Products Quickly**
Click "Show Unmapped" to see exactly which products need mapping, with suggested matches.

**Tip 2: Filter Before Analyzing**
Use the filters to focus on specific categories or brands, making it easier to spot pricing patterns.

**Tip 3: Regular Scans = Better Data**
More scan history = better trend data. Consider scanning at regular intervals (weekly is good to start).

**Tip 4: Use API for Integration**
If you want to integrate competitor prices into your own systems, all data is available via REST API.

## Supported Websites

| Website | URL | Category |
|---------|-----|----------|
| Booster Pakker | boosterpakker.no | Norwegian supplier |
| HataMonTCG | hatamontcg.com | TCG specialist |
| Laboge | laboge.dk | Danish retailer |
| LCG Cards | lcgcards.com | Living card games |

## Need Help?

1. **Check the full documentation**: `COMPETITOR_SYSTEM.md`
2. **View API docs**: http://localhost:8000/docs (while server running)
3. **Check logs**: `apply_log.txt` for detailed error information

---

**Ready to start?** Click the 🔍 Competitors tab and begin scanning! 🚀
