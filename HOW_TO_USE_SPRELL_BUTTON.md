# Adding Sprell to Your Website - Simple Instructions

## Current Status ✓

Your website **already supports** the Sprell scraper! Here's what's in place:

1. ✓ Backend API updated to include Sprell (website_id: 4)
2. ✓ Frontend automatically loads all suppliers from database
3. ✓ Scan button automatically appears for each supplier

## What You Need to Do (2 Steps)

### Step 1: Add Sprell to Database

Run this command:
```bash
python add_sprell_supplier.py
```

This will create the Sprell entry in your database and show you the website_id (likely 4).

### Step 2: Refresh Your Website

Simply reload your website in the browser. Sprell will automatically appear in the Suppliers tab with a scan button.

## Using the Scan Button

1. **Open your website**: http://localhost:8000
2. **Click on "Suppliers" tab**
3. **Find "Sprell" in the list** - it will show:
   - Name: Sprell
   - URL: https://www.sprell.no/...
   - Status: Active
   - Last Scan: Never (initially)
   - **Actions: [🔄 Scan] button**
4. **Click the "🔄 Scan" button** to start scanning

## What Happens When You Click Scan

1. Browser sends request to API
2. API starts the Sprell scraper (suppliers/sprell.py)
3. Scraper visits sprell.no and extracts products
4. Only products with "På nettlager" are saved
5. Results appear in:
   - Supplier Products table
   - Supplier Scan Logs
6. Status updates to show "Last Scan: X minutes ago"

## Automated Scans (Optional)

To set up automatic scanning every 6 hours, add to your crontab:

```bash
# After running add_sprell_supplier.py, note the website_id (probably 4)
# Then add this to crontab:
45 6,12,18,0 * * * curl -s -X POST "http://localhost:8000/api/v1/suppliers/scan" -H "Content-Type: application/json" -d '{"website_id":4}' >> ~/logs/sprell_api.log 2>&1
```

## Verifying It Works

After clicking the scan button:

1. **Check Scan Logs**: Still in Suppliers tab, scroll down to "Recent Scans" section
2. **Look for Sprell entry**: Should show:
   - Website: Sprell
   - Status: success
   - Products Found: (number)
   - New Products: (number)
   - Time: Just now

3. **View Products**: Click on "Supplier Products" to see what was found

## Testing Before Adding to Database

Want to test the scraper first?

```bash
# Simple test (shows first 10 products, no database)
python test_sprell_simple.py
```

This opens a browser and shows you what the scraper finds.

## That's It!

Your system is **already set up** to handle Sprell. Just:
1. Run `python add_sprell_supplier.py`
2. Refresh your website
3. Click the scan button

The scan button will automatically appear because your frontend code dynamically loads all suppliers from the database.
