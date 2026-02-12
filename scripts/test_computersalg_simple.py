#!/usr/bin/env python3
"""
Simple test script to verify computersalg scraper data extraction
"""
import json
import sys
import re
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from driver_setup import create_chromium_driver
import time

def main():
    print("="*80)
    print("COMPUTERSALG DATA VERIFICATION TEST")
    print("="*80)
    print()
    
    # Setup driver
    print("[1/3] Initializing WebDriver...")
    driver = create_chromium_driver(headless=True)
    
    all_products = []
    
    try:
        # Scrape products
        print("\n[2/3] Scraping products from computersalg.no...")
        start_url = "https://www.computersalg.no/l/4979/byttekort?f=c72d38dc-9dd6-4d3f-93cc-44bfd26b97aa&p=1&sq=&csstock=0"
        print(f"URL: {start_url}")
        
        driver.get(start_url)
        time.sleep(5)
        
        page = 1
        max_pages = 10
        
        while page <= max_pages:
            print(f"\n  Page {page}...")
            
            # Find product cards
            product_cards = driver.find_elements("css selector", "div[data-js-pagination-item]")
            print(f"  Found {len(product_cards)} product cards")
            
            if not product_cards:
                print("  No more products, stopping")
                break
            
            # Extract data from each card
            page_products = 0
            for card in product_cards:
                try:
                    # Get product URL
                    link_elem = card.find_element("css selector", "a[href*='/i/']")
                    url = link_elem.get_attribute("href")
                    
                    if not url:
                        continue
                    
                    # Extract product name
                    name_elem = card.find_element("css selector", "h3.m-product-card__name")
                    name = driver.execute_script("return arguments[0].textContent;", name_elem).strip()
                    
                    if not name:
                        continue
                    
                    # Clean up name
                    name = name.replace('„', '').replace('"', '').replace('  ', ' ').strip()
                    
                    # Extract price
                    price = None
                    try:
                        price_elem = card.find_element("css selector", "span.m-product-card__price-text")
                        price_text = driver.execute_script("return arguments[0].textContent;", price_elem).strip()
                        price_text = price_text.replace(' ', '').replace('.', '').replace(',', '.')
                        price = float(price_text)
                    except Exception:
                        pass
                    
                    # Extract SKU
                    sku = None
                    try:
                        sku_elem = card.find_element("css selector", "span[itemprop*='sku']")
                        sku = driver.execute_script("return arguments[0].textContent;", sku_elem).strip()
                    except Exception:
                        pass
                    
                    # Check stock status
                    in_stock = False
                    try:
                        card.find_element("css selector", "span.stock.green")
                        in_stock = True
                    except Exception:
                        pass
                    
                    # Extract image URL
                    image_url = None
                    try:
                        img_elem = card.find_element("css selector", "div.m-product-card__image img")
                        image_url = img_elem.get_attribute("src")
                        if image_url and image_url.startswith('//'):
                            image_url = 'https:' + image_url
                        if image_url and 'data:image' in image_url:
                            image_url = None
                    except Exception:
                        pass
                    
                    product_data = {
                        'product_url': url,
                        'name': name,
                        'price': price,
                        'sku': sku,
                        'in_stock': in_stock,
                        'image_url': image_url,
                        'stock_quantity': None,
                        'category': None,
                    }
                    
                    all_products.append(product_data)
                    page_products += 1
                    
                except Exception as e:
                    print(f"    ERROR extracting product: {e}")
                    continue
            
            print(f"  Extracted {page_products} products from page {page}")
            
            # Navigate to next page
            if page >= max_pages:
                break
            
            current_url = driver.current_url
            if 'page=' in current_url:
                next_page_url = re.sub(r'page=\d+', f'page={page+1}', current_url)
            else:
                next_page_url = current_url + f"&page={page+1}"
            
            driver.get(next_page_url)
            time.sleep(5)
            
            # Check if we got new products
            new_cards = driver.find_elements("css selector", "div[data-js-pagination-item]")
            if len(new_cards) == 0:
                break
                
            page += 1
        
        print(f"\n  Total products scraped: {len(all_products)}")
        
    finally:
        driver.quit()
    
    # Save to JSON
    print("\n[3/3] Saving data...")
    output_file = "test_computersalg_output.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_products, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved {len(all_products)} products to {output_file}")
    
    # Print sample data
    if all_products:
        print("\n" + "="*80)
        print("SAMPLE DATA (First 3 products):")
        print("="*80)
        for i, product in enumerate(all_products[:3], 1):
            print(f"\n--- Product {i} ---")
            for key, value in product.items():
                if key == 'name' and value:
                    value = value[:60] + '...' if len(value) > 60 else value
                elif key == 'product_url' and value:
                    value = value[:70] + '...' if len(value) > 70 else value
                print(f"  {key:15}: {value}")
    
    # Summary statistics
    print("\n" + "="*80)
    print("SUMMARY STATISTICS:")
    print("="*80)
    print(f"  Total products:  {len(all_products)}")
    print(f"  In stock:        {sum(1 for p in all_products if p['in_stock'])}")
    print(f"  Out of stock:    {sum(1 for p in all_products if not p['in_stock'])}")
    print(f"  With price:      {sum(1 for p in all_products if p['price'] is not None)}")
    print(f"  With SKU:        {sum(1 for p in all_products if p['sku'] is not None)}")
    print(f"  With image:      {sum(1 for p in all_products if p['image_url'] is not None)}")
    print()
    print("="*80)
    print("TEST COMPLETE!")
    print("="*80)

if __name__ == "__main__":
    main()
