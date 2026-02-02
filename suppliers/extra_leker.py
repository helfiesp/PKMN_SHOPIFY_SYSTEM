"""
Scraper for extra-leker.no - Pokemon TCG supplier
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


class ExtraLekerScraper(BaseSupplierScraper):
    """Scraper for extra-leker.no Pokemon TCG products."""

    def scrape_products(self) -> List[Dict]:
        """Scrape Pokemon TCG products from extra-leker.no."""
        products = []
        
        LOG.info(f"Navigating to: {self.website.url}")
        self.driver.get(self.website.url)
        
        # Wait for products to load
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "li.item.product.product-item"))
            )
            # Extra wait for JavaScript to populate content
            time.sleep(3)
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
            product_items = self.driver.find_elements(By.CSS_SELECTOR, "li.item.product.product-item")
            LOG.info(f"Found {len(product_items)} products on page {page_num}")
            
            if not product_items:
                LOG.info("No products found, stopping pagination")
                break
            
            for item in product_items:
                try:
                    # Wait a bit for any lazy-loaded content
                    time.sleep(0.5)
                    
                    # Extract product name and URL - try multiple methods
                    name = None
                    url = None
                    
                    try:
                        link_elem = item.find_element(By.CSS_SELECTOR, "a.product-item-link")
                        # Use textContent or innerHTML instead of .text for better reliability
                        name = self.driver.execute_script("return arguments[0].textContent", link_elem).strip()
                        url = link_elem.get_attribute("href")
                    except Exception as e:
                        LOG.warning(f"Could not extract name/url: {e}")
                        continue
                    
                    if not name or not url:
                        LOG.warning("Skipping product with empty name or URL")
                        continue
                    
                    # Extract price
                    price = None
                    try:
                        price_elem = item.find_element(By.CSS_SELECTOR, "span.price")
                        # Use JavaScript to get textContent
                        price_text = self.driver.execute_script("return arguments[0].textContent", price_elem).strip()
                        # Remove "kr", spaces, and convert comma to dot
                        price_text = price_text.replace("kr", "").replace("\xa0", "").replace(" ", "").replace(",", ".")
                        price = float(price_text)
                    except Exception as e:
                        LOG.warning(f"Could not extract price for {name}: {e}")
                    
                    # Check stock status - look for available or unavailable class
                    in_stock = False
                    try:
                        # Check if "available" stock status exists
                        item.find_element(By.CSS_SELECTOR, "span.online-stock-status.available")
                        in_stock = True
                    except:
                        # If not found, check for unavailable
                        try:
                            item.find_element(By.CSS_SELECTOR, "span.online-stock-status.unavailable")
                            in_stock = False
                        except:
                            # Default to out of stock if we can't determine
                            in_stock = False
                    
                    # Get SKU if available (from data attributes)
                    sku = None
                    try:
                        photo_link = item.find_element(By.CSS_SELECTOR, "a.product.photo.product-item-photo")
                        sku = photo_link.get_attribute("data-simple-id")
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
                    elif "booster" in name_lower or "blisterpakke" in name_lower:
                        category = "booster_pack"
                    elif "elite trainer" in name_lower or "etb" in name_lower:
                        category = "elite_trainer"
                    elif "collection" in name_lower or "samleboks" in name_lower or "collector" in name_lower:
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
                # Look for "next" button/link in pagination
                next_button = self.driver.find_element(By.CSS_SELECTOR, "a.action.next")
                button_class = next_button.get_attribute("class") or ""
                if "disabled" in button_class:
                    LOG.info("Last page reached (next button disabled)")
                    break
                
                # Navigate to next page using URL parameter
                page_num += 1
                next_url = self.website.url
                if "?" in next_url:
                    next_url = next_url.split("?")[0] + f"?p={page_num}"
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
        print("Usage: python extra_leker.py <website_id>")
        print("\nTo create the website entry, use:")
        print('curl -X POST "http://localhost:8000/api/v1/suppliers/websites" \\')
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"name": "Extra Leker", "url": "https://www.extra-leker.no/pokemon/pokemon-tcg-samlekort", "scan_interval_hours": 6}\'')
        sys.exit(1)
    
    website_id = int(sys.argv[1])
    
    with ExtraLekerScraper(website_id) as scraper:
        result = scraper.run()
        
        print(f"\n{'='*60}")
        print(f"Extra-Leker.no Scan Results")
        print(f"{'='*60}")
        print(f"Status: {result['status']}")
        print(f"Products found: {result['products_found']}")
        print(f"New products: {result['new_products']}")
        print(f"Restocked: {result['restocked_products']}")
        if result['error_message']:
            print(f"Error: {result['error_message']}")
        print(f"{'='*60}")
