# 🎯 Quick Visual Guide - Using the Sprell Scan Button

## Step 1: Add Sprell to Database

Open your terminal and run:
```
python add_sprell_supplier.py
```

You'll see:
```
✓ Successfully created Sprell supplier!
  ID: 4
  Name: Sprell
  URL: https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon
  Scan interval: 6 hours
```

## Step 2: Open Your Website

Go to: **http://localhost:8000**

## Step 3: Click "Suppliers" Tab

```
┌─────────────────────────────────────────┐
│  Dashboard  Products  Price Plans       │
│  [SUPPLIERS] ← CLICK THIS TAB          │
│  Competitors  Mappings  Reports         │
└─────────────────────────────────────────┘
```

## Step 4: Find Sprell and Click Scan Button

You'll see a table like this:

```
Supplier Websites
┌──────────┬──────────────────┬────────┬───────────┬─────────────┐
│ Name     │ URL              │ Status │ Last Scan │ Actions     │
├──────────┼──────────────────┼────────┼───────────┼─────────────┤
│ Lekek... │ lekekassen.no... │ Active │ 2h ago    │ [🔄 Scan]  │
│ Extra... │ extra-leker.n... │ Active │ 1h ago    │ [🔄 Scan]  │
│ Compu... │ computersalg.... │ Active │ 30m ago   │ [🔄 Scan]  │
│ Sprell   │ sprell.no...     │ Active │ Never     │ [🔄 Scan]  │← CLICK
└──────────┴──────────────────┴────────┴───────────┴─────────────┘
                                                      ↑
                                                 CLICK HERE
```

## Step 5: Watch It Work!

After clicking, you'll see:

### Alert Box
```
╔════════════════════════════════╗
║  ℹ Starting supplier scan...   ║
╚════════════════════════════════╝
```

Then (after 30-60 seconds):
```
╔════════════════════════════════╗
║  ✓ Scan completed successfully!║
╚════════════════════════════════╝
```

### Updated Table
```
│ Sprell   │ sprell.no...     │ Active │ Just now  │ [🔄 Scan]  │
                                         ↑
                                    NOW SHOWS TIME
```

### Scroll Down to See "Recent Scans"
```
Supplier Scan Logs
┌──────────┬─────────┬──────────┬─────────┬───────────┐
│ Website  │ Status  │ Products │ New     │ Time      │
├──────────┼─────────┼──────────┼─────────┼───────────┤
│ Sprell   │ success │ 8        │ 8       │ Just now  │
└──────────┴─────────┴──────────┴─────────┴───────────┘
```

## Step 6: View Products Found

Click on "Supplier Products" section to see what was found:

```
Supplier Products (In Stock)
┌────────────────────────────────┬────────┬────────┬─────────┐
│ Product Name                   │ Price  │ Stock  │ Website │
├────────────────────────────────┼────────┼────────┼─────────┤
│ FIFA 365 Adrenalyn XL 2026 Tin│ 229 kr │ ✓ Yes  │ Sprell  │
│ Pokemon Booster Pack - SV      │ 89 kr  │ ✓ Yes  │ Sprell  │
│ ...                            │ ...    │ ...    │ ...     │
└────────────────────────────────┴────────┴────────┴─────────┘
```

## That's It! 🎉

You can now:
- ✓ Click the scan button anytime to update
- ✓ See all products in stock online at Sprell
- ✓ Compare prices with other suppliers
- ✓ Track stock changes over time

## Automated Scans

To scan automatically without clicking, add to crontab:

```bash
# Scans every 6 hours (6:45, 12:45, 18:45, 0:45)
45 6,12,18,0 * * * curl -s -X POST "http://localhost:8000/api/v1/suppliers/scan" -H "Content-Type: application/json" -d '{"website_id":4}' >> ~/logs/sprell_api.log 2>&1
```

## Troubleshooting

**Q: I don't see Sprell in the list**
A: Make sure you ran `python add_sprell_supplier.py` and refreshed the page (F5)

**Q: Scan button does nothing**
A: Check browser console (F12) for errors. Make sure API is running.

**Q: Scan says "failed"**
A: Look at the error message in scan logs. Common issues:
   - Website is down
   - HTML structure changed
   - Internet connection issues

**Q: No products found**
A: Run `python test_sprell_simple.py` to see what's happening

## Your System Now Has

✅ 4 Supplier Scrapers:
1. Lekekassen
2. Extra Leker
3. Computersalg
4. **Sprell** ← NEW!

✅ Each with:
- Automatic scan button
- Scheduled scans (optional)
- Product tracking
- Price comparison
- Stock monitoring

✅ Enhanced Features:
- Auto-detection of scraper files
- Dynamic supplier loading
- No code changes for future suppliers
