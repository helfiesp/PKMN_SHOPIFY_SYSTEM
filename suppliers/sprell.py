"""
Scraper for sprell.no - Pokemon TCG supplier
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


class SprellScraper(BaseSupplierScraper):
    """Scraper for sprell.no Pokemon TCG products."""

    def scrape_products(self) -> List[Dict]:
        """Scrape Pokemon TCG products from sprell.no."""
        products = []
        
        LOG.info(f"Navigating to: {self.website.url}")
        self.driver.get(self.website.url)
        
        # Wait for products to load
        try:
            WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.CardContainer-module_cardContainer__qolR1"))
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
            product_items = self.driver.find_elements(By.CSS_SELECTOR, "article.CardContainer-module_cardContainer__qolR1")
            LOG.info(f"Found {len(product_items)} products on page {page_num}")
            
            if not product_items:
                LOG.info("No products found, stopping pagination")
                break
            
            for item in product_items:
                try:
                    # Extract product name and URL
                    name = None
                    url = None
                    
                    try:
                        link_elem = item.find_element(By.CSS_SELECTOR, "a.ProductCard_cardProductNewAnchor__f4cCH")
                        url = link_elem.get_attribute("href")
                        
                        # Get name from h2 heading
                        name_elem = item.find_element(By.CSS_SELECTOR, "h2.ProductCardTemplate_productName__P_oN8")
                        name = self.driver.execute_script("return arguments[0].textContent", name_elem).strip()
                    except Exception as e:
                        LOG.warning(f"Could not extract name/url: {e}")
                        continue
                    
                    if not name or not url:
                        LOG.warning("Skipping product with empty name or URL")
                        continue
                    
                    # Extract price
                    price = None
                    try:
                        price_elem = item.find_element(By.CSS_SELECTOR, "p.CardPrice-module_cardPricePrice__ngXEp")
                        price_text = self.driver.execute_script("return arguments[0].textContent", price_elem).strip()
                        # Remove ",-" and any extra characters, convert to float
                        price_text = price_text.replace(",-", "").replace(",", "").strip()
                        price = float(price_text)
                    except Exception as e:
                        LOG.warning(f"Could not extract price for {name}: {e}")
                    
                    # Check stock status - ONLY products with "På nettlager" are in stock online
                    in_stock = False
                    try:
                        # Look for stock status wrapper
                        stock_wrapper = item.find_element(By.CSS_SELECTOR, "div.StockStatus_statusWrapper___i64_")
                        
                        # Check all status divs for "På nettlager" text
                        status_divs = stock_wrapper.find_elements(By.CSS_SELECTOR, "div.StockStatus_status__A4H_J")
                        for status_div in status_divs:
                            try:
                                # Check if this status has the in-stock color indicator
                                status_div.find_element(By.CSS_SELECTOR, "div.StockStatus_statusColorInStock__LsCel")
                                
                                # Check if the label says "På nettlager"
                                label_elem = status_div.find_element(By.CSS_SELECTOR, "p.StockStatus_label__KLPb9")
                                label_text = self.driver.execute_script("return arguments[0].textContent", label_elem).strip()
                                
                                if "På nettlager" in label_text:
                                    in_stock = True
                                    break
                            except:
                                continue
                    except Exception as e:
                        LOG.debug(f"Could not check stock status for {name}: {e}")
                    
                    # Skip products that are not in stock online
                    if not in_stock:
                        LOG.debug(f"Skipping {name} - not in stock online")
                        continue
                    
                    # Get SKU if available - try to extract from URL
                    sku = None
                    try:
                        # URL pattern: /product/...--CODE_no?code=CODE
                        if "?code=" in url:
                            sku = url.split("?code=")[1].split("&")[0]
                        elif "--" in url:
                            # Try to extract from URL path
                            parts = url.split("--")
                            if len(parts) > 1:
                                sku = parts[-1].split("_")[0].split("?")[0]
                    except:
                        pass
                    
                    # Get image URL
                    image_url = None
                    try:
                        img = item.find_element(By.CSS_SELECTOR, "img.CardImage-module_cardImageImage__W7YAU")
                        image_url = img.get_attribute("src")
                        # Get the highest quality image URL if available
                        if not image_url:
                            image_url = img.get_attribute("srcset")
                            if image_url:
                                # Extract the last (highest quality) URL from srcset
                                urls = [u.strip().split()[0] for u in image_url.split(",")]
                                image_url = urls[-1] if urls else None
                    except:
                        pass
                    
                    # Get brand if available
                    brand = None
                    try:
                        brand_elem = item.find_element(By.CSS_SELECTOR, "p.ProductCardTemplate_brandName__whiuc")
                        brand = self.driver.execute_script("return arguments[0].textContent", brand_elem).strip()
                    except:
                        pass
                    
                    # Detect category from name
                    category = None
                    name_lower = name.lower()
                    if "booster box" in name_lower or "booster display" in name_lower or "display" in name_lower:
                        category = "booster_box"
                    elif "booster" in name_lower or "booster-pakke" in name_lower:
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
                    LOG.info(f"  [{status}] {name} - {price} NOK {f'(Brand: {brand})' if brand else ''}")
                    
                except Exception as e:
                    LOG.warning(f"Error parsing product: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Try to go to next page using URL parameter
            try:
                # Navigate to next page using URL parameter
                # Sprell.no uses &page=N for pagination
                page_num += 1
                next_url = self.website.url
                
                if "&page=" in next_url:
                    # Replace existing page parameter
                    import re
                    next_url = re.sub(r'&page=\d+', f'&page={page_num}', next_url)
                elif "?" in next_url:
                    # Add page parameter to existing query string
                    next_url = next_url + f"&page={page_num}"
                else:
                    # Create new query string with page parameter
                    next_url = next_url + f"?page={page_num}"
                
                LOG.info(f"Going to page {page_num}: {next_url}")
                self.driver.get(next_url)
                time.sleep(3)  # Wait for page load
                
                # Check if we actually got products on this page
                new_products = self.driver.find_elements(By.CSS_SELECTOR, "article.CardContainer-module_cardContainer__qolR1")
                if not new_products:
                    LOG.info("No products found on next page, stopping pagination")
                    break
                
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
        print("Usage: python sprell.py <website_id>")
        print("\nTo create the website entry, use:")
        print('curl -X POST "http://localhost:8000/api/v1/suppliers/websites" \\')
        print('  -H "Content-Type: application/json" \\')
        print('  -d \'{"name": "Sprell", "url": "https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon", "scan_interval_hours": 6}\'')
        sys.exit(1)
    
    website_id = int(sys.argv[1])
    
    with SprellScraper(website_id) as scraper:
        result = scraper.run()
        
        print(f"\n{'='*60}")
        print(f"Sprell.no Scan Results")
        print(f"{'='*60}")
        print(f"Status: {result['status']}")
        print(f"Products found: {result['products_found']}")
        print(f"New products: {result['new_products']}")
        print(f"Restocked: {result['restocked_products']}")
        if result['error_message']:
            print(f"Error: {result['error_message']}")
        print(f"{'='*60}")
