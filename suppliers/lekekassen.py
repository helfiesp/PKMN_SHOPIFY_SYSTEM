"""
Scraper for lekekassen.no - Pokemon TCG supplier
"""
from __future__ import annotations

import time
import logging
from typing import List, Dict
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from suppliers.base_scraper import BaseSupplierScraper

LOG = logging.getLogger(__name__)


class LekekassenScraper(BaseSupplierScraper):
    """Scraper for lekekassen.no Pokemon TCG products."""

    def scrape_products(self) -> List[Dict]:
        """Scrape Pokemon TCG products from lekekassen.no."""
        products = []
        
        LOG.info(f"Navigating to: {self.website.url}")
        self.driver.get(self.website.url)
        
        # Wait for products to load
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "product-item"))
            )
        except Exception as e:
            LOG.error(f"Products not found: {e}")
            return products
        
        # Handle pagination
        page_num = 1
        max_pages = 50  # Safety limit to prevent infinite loops
        
        while page_num <= max_pages:
            LOG.info(f"Scraping page {page_num}")
            time.sleep(2)  # Let page load
            
            # Find all product items
            product_items = self.driver.find_elements(By.CSS_SELECTOR, "li.product-item")
            LOG.info(f"Found {len(product_items)} products on page {page_num}")
            
            if not product_items:
                LOG.info("No products found, stopping pagination")
                break
            
            for item in product_items:
                try:
                    # Extract product name and URL
                    link_elem = item.find_element(By.CLASS_NAME, "product-item-link")
                    name = link_elem.text.strip()
                    url = link_elem.get_attribute("href")
                    
                    # Extract price
                    price = None
                    try:
                        price_elem = item.find_element(By.CSS_SELECTOR, "span.price")
                        price_text = price_elem.text.strip()
                        # Remove ",-" and convert to float
                        price = float(price_text.replace(",-", "").replace(",", "").strip())
                    except Exception as e:
                        LOG.warning(f"Could not extract price for {name}: {e}")
                    
                    # Check stock status - if div.stock.unavailable exists, it's OUT OF STOCK
                    in_stock = True
                    try:
                        # If this element exists, the product is out of stock
                        item.find_element(By.CSS_SELECTOR, "div.stock.unavailable")
                        in_stock = False
                    except:
                        # Element not found means it's in stock
                        in_stock = True
                    
                    # Get SKU if available
                    sku = None
                    try:
                        form = item.find_element(By.CSS_SELECTOR, "form[data-product-sku]")
                        sku = form.get_attribute("data-product-sku")
                    except:
                        pass
                    
                    # Get image URL
                    image_url = None
                    try:
                        img = item.find_element(By.CSS_SELECTOR, "img.product-image-photo")
                        image_url = img.get_attribute("src")
                    except:
                        pass
                    
                    # Detect category from name
                    category = None
                    name_lower = name.lower()
                    if "booster box" in name_lower or "booster display" in name_lower:
                        category = "booster_box"
                    elif "booster" in name_lower and "pakker" in name_lower:
                        category = "booster_pack"
                    elif "elite trainer" in name_lower or "etb" in name_lower:
                        category = "elite_trainer"
                    elif "collection" in name_lower or "samleboks" in name_lower:
                        category = "collection_box"
                    
                    product_data = {
                        "product_url": url,
                        "name": name,
                        "in_stock": in_stock,
                        "price": price,
                        "sku": sku,
                        "category": category,
                        "image_url": image_url,
                    }
                    
                    products.append(product_data)
                    
                    status = "IN STOCK" if in_stock else "OUT OF STOCK"
                    LOG.info(f"  [{status}] {name} - {price} NOK")
                    
                except Exception as e:
                    LOG.warning(f"Error parsing product: {e}")
                    continue
            
            # Try to go to next page
            try:
                # Look for "next" button
                next_button = self.driver.find_element(By.CSS_SELECTOR, "a.action.next")
                button_class = next_button.get_attribute("class") or ""
                if "disabled" in button_class:
                    LOG.info("Last page reached (next button disabled)")
                    break
                
                # Navigate to next page using URL parameter instead of clicking
                # This avoids cookie popups and other click issues
                page_num += 1
                next_url = self.website.url
                if "?" in next_url:
                    next_url = next_url.split("?")[0] + f"?p={page_num}&" + next_url.split("?")[1]
                else:
                    next_url = next_url + f"?p={page_num}"
                
                LOG.info(f"Going to page {page_num}: {next_url}")
                self.driver.get(next_url)
                time.sleep(2)  # Wait for page load
                
            except Exception as e:
                LOG.info(f"No more pages or pagination error: {e}")
                break
        
        LOG.info(f"Total products scraped: {len(products)}")
        return products


if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    # Add parent directory to path for imports
    sys.path.append(str(Path(__file__).resolve().parent.parent))
    
    if len(sys.argv) < 2:
        print("Usage: python lekekassen.py <website_id>")
        print("\nTo create the website entry, use:")
        print('curl -X POST "http://localhost:8000/api/v1/suppliers/websites" \\')
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"name": "Lekekassen", "url": "https://lekekassen.no/catalogsearch/result/index/?q=Pokemon+tcg", "scan_interval_hours": 6}\'')
        sys.exit(1)
    
    website_id = int(sys.argv[1])
    
    with LekekassenScraper(website_id) as scraper:
        result = scraper.run()
        
        print(f"\n{'='*60}")
        print(f"Lekekassen.no Scan Results")
        print(f"{'='*60}")
        print(f"Status: {result['status']}")
        print(f"Products found: {result['products_found']}")
        print(f"New products: {result['new_products']}")
        print(f"Restocked: {result['restocked_products']}")
        if result['error_message']:
            print(f"Error: {result['error_message']}")
        print(f"{'='*60}")
