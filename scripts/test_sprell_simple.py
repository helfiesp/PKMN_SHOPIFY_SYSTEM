#!/usr/bin/env python3
"""
Simple standalone test for sprell.no scraper - no database required
"""
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver_setup import create_chromium_driver

def test_sprell_scraper_simple():
    """Test scraping sprell.no without database"""
    
    url = "https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon"
    
    print(f"Testing Sprell.no scraper")
    print(f"URL: {url}")
    print("="*80)
    
    driver = None
    try:
        # Create driver
        print("\nInitializing browser...")
        driver = create_chromium_driver(headless=True)  # Headless for server compatibility
        
        # Navigate to page
        print(f"Navigating to: {url}")
        driver.get(url)
        
        # Wait for products to load
        print("Waiting for products to load...")
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.CardContainer-module_cardContainer__qolR1"))
        )
        time.sleep(3)  # Extra wait for JS
        
        # Find all product items
        product_items = driver.find_elements(By.CSS_SELECTOR, "article.CardContainer-module_cardContainer__qolR1")
        print(f"\nFound {len(product_items)} products on page")
        
        in_stock_count = 0
        out_of_stock_count = 0
        
        print("\nProcessing products...\n")
        
        for idx, item in enumerate(product_items[:10], 1):  # Test first 10 products
            try:
                # Get name
                name_elem = item.find_element(By.CSS_SELECTOR, "h2.ProductCardTemplate_productName__P_oN8")
                name = driver.execute_script("return arguments[0].textContent", name_elem).strip()
                
                # Get URL
                link_elem = item.find_element(By.CSS_SELECTOR, "a.ProductCard_cardProductNewAnchor__f4cCH")
                url = link_elem.get_attribute("href")
                
                # Get price
                price_elem = item.find_element(By.CSS_SELECTOR, "p.CardPrice-module_cardPricePrice__ngXEp")
                price_text = driver.execute_script("return arguments[0].textContent", price_elem).strip()
                price = price_text.replace(",-", "").replace(",", "").strip()
                
                # Check stock status - ONLY products with "På nettlager" are in stock online
                in_stock = False
                stock_status_text = ""
                try:
                    stock_wrapper = item.find_element(By.CSS_SELECTOR, "div.StockStatus_statusWrapper___i64_")
                    status_divs = stock_wrapper.find_elements(By.CSS_SELECTOR, "div.StockStatus_status__A4H_J")
                    
                    for status_div in status_divs:
                        try:
                            # Check if this status has the in-stock color indicator
                            status_div.find_element(By.CSS_SELECTOR, "div.StockStatus_statusColorInStock__LsCel")
                            
                            # Get the label text
                            label_elem = status_div.find_element(By.CSS_SELECTOR, "p.StockStatus_label__KLPb9")
                            label_text = driver.execute_script("return arguments[0].textContent", label_elem).strip()
                            
                            if "På nettlager" in label_text:
                                in_stock = True
                                stock_status_text = "På nettlager"
                                break
                            elif stock_status_text == "":
                                stock_status_text = label_text
                        except:
                            continue
                except Exception as e:
                    stock_status_text = "Could not determine"
                
                if in_stock:
                    in_stock_count += 1
                    status_display = "✓ IN STOCK"
                else:
                    out_of_stock_count += 1
                    status_display = "✗ OUT OF STOCK"
                
                print(f"{idx}. [{status_display}] {name}")
                print(f"   Price: {price} NOK | Stock: {stock_status_text}")
                print(f"   URL: {url[:80]}...")
                print()
                
            except Exception as e:
                print(f"{idx}. ERROR: Could not parse product - {e}")
                print()
        
        print("="*80)
        print(f"\nSummary:")
        print(f"  Products found: {len(product_items)}")
        print(f"  In stock online (På nettlager): {in_stock_count}")
        print(f"  Out of stock / In stores only: {out_of_stock_count}")
        print(f"\n✓ Test completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    finally:
        if driver:
            print("\nClosing browser...")
            driver.quit()
    
    return 0

if __name__ == "__main__":
    sys.exit(test_sprell_scraper_simple())
