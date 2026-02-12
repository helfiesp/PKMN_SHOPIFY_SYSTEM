# Supplier Tracking System

Track product availability from supplier websites to know when new products are added or items come back in stock.

## Overview

This system monitors supplier websites and alerts you when:
- **New products** are added to their catalog
- **Out-of-stock items** become available again
- **Price changes** occur (optional tracking)

## Quick Start

### 1. Add a Supplier Website

```bash
curl -X POST "http://localhost:8000/api/v1/suppliers/websites" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Supplier",
    "url": "https://supplier.com/products",
    "scan_interval_hours": 6,
    "notify_on_new_products": true,
    "notify_on_restock": true
  }'
```

### 2. Create a Custom Scraper

Create a file `suppliers/my_supplier.py`:

```python
from suppliers.base_scraper import BaseSupplierScraper
from selenium.webdriver.common.by import By

class MySupplierScraper(BaseSupplierScraper):
    def scrape_products(self):
        products = []
        
        # Navigate to products page
        self.driver.get(self.website.url)
        
        # Find product elements (customize selectors)
        for card in self.driver.find_elements(By.CLASS_NAME, "product-card"):
            name = card.find_element(By.CLASS_NAME, "title").text
            url = card.find_element(By.TAG_NAME, "a").get_attribute("href")
            price_text = card.find_element(By.CLASS_NAME, "price").text
            price = float(price_text.replace("kr", "").strip())
            
            # Check stock status
            in_stock = "in stock" in card.text.lower()
            
            products.append({
                "product_url": url,
                "name": name,
                "in_stock": in_stock,
                "price": price,
                "currency": "NOK",
            })
        
        return products

if __name__ == "__main__":
    import sys
    website_id = int(sys.argv[1])
    
    with MySupplierScraper(website_id) as scraper:
        result = scraper.run()
        print(f"Found {result['new_products']} new products")
```

### 3. Run the Scraper

```bash
# Get the website ID from the API (or database)
python suppliers/my_supplier.py 1
```

### 4. Set Up Automated Scanning

Add to your crontab:

```bash
# Scan every 6 hours
0 */6 * * * cd ~/software/PKMN_SHOPIFY_SYSTEM && source ~/software/venv/bin/activate && python suppliers/my_supplier.py 1 >> ~/logs/supplier_scan.log 2>&1
```

## API Endpoints

### Supplier Websites

- `POST /api/v1/suppliers/websites` - Create new supplier
- `GET /api/v1/suppliers/websites` - List all suppliers
- `GET /api/v1/suppliers/websites/{id}` - Get supplier details

### Products

- `GET /api/v1/suppliers/products/new` - Get new unacknowledged products
- `GET /api/v1/suppliers/products/in-stock` - Get currently in-stock products
- `POST /api/v1/suppliers/products/{id}/acknowledge` - Mark product as seen

### Alerts

- `GET /api/v1/suppliers/alerts` - Get alerts (new products, restocks)
- `POST /api/v1/suppliers/alerts/{id}/mark-read` - Mark alert as read

### Scan Logs

- `GET /api/v1/suppliers/scan-logs` - Get scan history
- `POST /api/v1/suppliers/scan` - Manually trigger a scan

### Statistics

- `GET /api/v1/suppliers/statistics` - Get overview statistics

## Database Models

### SupplierWebsite
- Configuration for each supplier you track
- Scan interval, notification preferences, etc.

### SupplierProduct
- Individual products found on supplier websites
- Tracks: name, price, stock status, URL
- `is_new` flag for newly discovered products

### SupplierAvailabilityHistory
- Historical snapshots of product availability
- Tracks when items go in/out of stock
- Price change tracking

### SupplierAlert
- Notifications for important events
- Types: `new_product`, `restock`, `price_drop`
- Can be marked as read

### SupplierScanLog
- Audit trail of all scan runs
- Success/failure status, duration, products found

## Web Interface

View supplier data in your browser:

```
http://localhost:8000/
```

Navigate to the **Suppliers** section to see:
- List of tracked suppliers
- New products requiring attention
- Current in-stock products
- Recent alerts
- Scan history

## Notification Setup (Optional)

### Discord Webhook

When creating a supplier website, add a Discord webhook URL:

```json
{
  "name": "My Supplier",
  "url": "https://supplier.com",
  "notification_webhook": "https://discord.com/api/webhooks/..."
}
```

The system will send notifications when:
- New products are detected
- Out-of-stock items become available

## Advanced Usage

### Custom Product Parsing

Override the `scrape_products()` method to handle complex HTML structures:

```python
def scrape_products(self):
    products = []
    self.driver.get(self.website.url)
    
    # Handle pagination
    page = 1
    while page <= 5:  # Scrape first 5 pages
        # Extract products from current page
        for card in self.driver.find_elements(By.CLASS_NAME, "product"):
            # ... parse product
            
        # Go to next page
        try:
            next_btn = self.driver.find_element(By.CLASS_NAME, "next-page")
            next_btn.click()
            page += 1
        except:
            break  # No more pages
    
    return products
```

### Filter Products

Only track specific categories or brands:

```python
def scrape_products(self):
    all_products = []
    # ... scrape products
    
    # Filter to only Pokemon products
    filtered = [p for p in all_products if "pokemon" in p["name"].lower()]
    return filtered
```

### Add Custom Fields

Track additional product metadata:

```python
products.append({
    "product_url": url,
    "name": name,
    "in_stock": in_stock,
    "price": price,
    "category": "booster box",  # Custom category
    "external_id": product_id,   # Supplier's ID
    "description": description,  # Full description
    "image_url": image_url,      # Product image
})
```

## Troubleshooting

### Scraper Not Finding Products

1. Check the HTML structure - use browser dev tools
2. Wait for dynamic content to load:
   ```python
   self.wait_for_element(By.CLASS_NAME, "product-card", timeout=10)
   ```
3. Handle JavaScript-rendered content - Selenium executes JS

### Products Marked as "New" Every Scan

- Ensure `product_url` is consistent
- The system uses URL as unique identifier
- Check for query parameters that change (remove them)

### Rate Limiting

Add delays between requests:

```python
import time

def scrape_products(self):
    products = []
    
    for page in range(1, 6):
        # ... scrape page
        time.sleep(2)  # Wait 2 seconds between pages
    
    return products
```

## Example: Complete Custom Scraper

```python
from suppliers.base_scraper import BaseSupplierScraper
from selenium.webdriver.common.by import By
import time
import logging

LOG = logging.getLogger(__name__)

class PokeShopScraper(BaseSupplierScraper):
    """Scraper for PokeShop supplier."""
    
    def scrape_products(self):
        products = []
        base_url = self.website.url
        
        # Scrape multiple pages
        for page_num in range(1, 4):  # Pages 1-3
            page_url = f"{base_url}?page={page_num}"
            LOG.info(f"Scraping page {page_num}: {page_url}")
            
            self.driver.get(page_url)
            time.sleep(2)  # Wait for page load
            
            # Find all product cards
            cards = self.driver.find_elements(By.CSS_SELECTOR, ".product-item")
            LOG.info(f"Found {len(cards)} products on page {page_num}")
            
            for card in cards:
                try:
                    # Extract product data
                    name = card.find_element(By.CLASS_NAME, "product-name").text
                    url = card.find_element(By.TAG_NAME, "a").get_attribute("href")
                    
                    # Parse price
                    price_elem = card.find_element(By.CLASS_NAME, "price")
                    price_text = price_elem.text.replace("kr", "").replace(",", "").strip()
                    price = float(price_text)
                    
                    # Check stock
                    stock_elem = card.find_element(By.CLASS_NAME, "availability")
                    in_stock = "på lager" in stock_elem.text.lower()
                    
                    # Get image
                    img = card.find_element(By.TAG_NAME, "img")
                    image_url = img.get_attribute("src")
                    
                    # Detect category
                    category = None
                    if "booster box" in name.lower():
                        category = "booster_box"
                    elif "elite trainer" in name.lower():
                        category = "elite_trainer"
                    
                    products.append({
                        "product_url": url,
                        "name": name,
                        "in_stock": in_stock,
                        "price": price,
                        "currency": "NOK",
                        "category": category,
                        "image_url": image_url,
                    })
                    
                except Exception as e:
                    LOG.warning(f"Error parsing product: {e}")
                    continue
            
            time.sleep(1)  # Be nice to the server
        
        LOG.info(f"Total products scraped: {len(products)}")
        return products


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python pokeshop_scraper.py <website_id>")
        sys.exit(1)
    
    website_id = int(sys.argv[1])
    
    with PokeShopScraper(website_id) as scraper:
        result = scraper.run()
        print(f"\n=== Scan Results ===")
        print(f"Status: {result['status']}")
        print(f"Products found: {result['products_found']}")
        print(f"New products: {result['new_products']}")
        print(f"Restocked: {result['restocked_products']}")
```

## Next Steps

1. Create supplier website entries via API
2. Build custom scrapers for each supplier
3. Test scrapers manually
4. Set up cron jobs for automated scanning
5. Monitor alerts for new products and restocks
6. Integrate with your purchasing workflow
