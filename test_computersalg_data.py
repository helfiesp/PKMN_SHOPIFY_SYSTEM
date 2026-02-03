#!/usr/bin/env python3
"""
Test script to scrape computersalg.no and save raw data to JSON
This allows us to verify data structure before database insertion
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time


def get_element_text(driver, element, selector):
    """Get text content from element using JavaScript"""
    try:
        el = element.find_element(By.CSS_SELECTOR, selector)
        return driver.execute_script("return arguments[0].textContent;", el).strip()
    except:
        return None


def extract_product_data_from_card(driver, card):
    """Extract product data from a card element on listing page"""
    try:
        # Get product URL and name
        title_link = card.find_element(By.CSS_SELECTOR, "a.product-link")
        product_url = title_link.get_attribute("href")
        name = get_element_text(driver, card, "h2.product-title")
        
        # Validate required fields
        if not product_url or not name:
            print(f"    ⚠ Skipping product: missing URL or name")
            return None
        
        # Get price
        price_text = get_element_text(driver, card, "span.price")
        price = None
        if price_text:
            price_clean = price_text.replace('kr', '').replace(',', '').replace('.', '').strip()
            try:
                price = float(price_clean) / 100
            except ValueError:
                pass
        
        # Get SKU
        sku = get_element_text(driver, card, "span.product-number")
        
        # Get stock status
        in_stock = False
        try:
            stock_span = card.find_element(By.CSS_SELECTOR, "span.stock")
            stock_class = stock_span.get_attribute("class")
            in_stock = "green" in stock_class
        except:
            pass
        
        # Get image URL
        image_url = None
        try:
            img = card.find_element(By.CSS_SELECTOR, "img.product-image")
            image_url = img.get_attribute("src")
            # Skip placeholder images
            if image_url and 'data:image' in image_url:
                image_url = None
        except:
            pass
        
        return {
            'product_url': product_url,
            'name': name,
            'price': price,
            'sku': sku,
            'in_stock': in_stock,
            'image_url': image_url,
            'stock_quantity': None,  # Not available on listing page
            'category': None,  # Not available on listing page
        }
    except Exception as e:
        print(f"    ⚠ Error extracting product data: {e}")
        import traceback
        traceback.print_exc()
        return None


def scrape_computersalg():
    """Scrape products from computersalg.no"""
    products = []
    
    # Setup Chrome driver
    print("\n[SETUP] Initializing Chrome WebDriver...")
    service = Service()
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    driver = webdriver.Chrome(service=service, options=options)
    
    try:
        base_url = "https://www.computersalg.no/l/4979/byttekort?f=c72d38dc-9dd6-4d3f-93cc-44bfd26b97aa&p={page}&sq=&csstock=0"
        max_pages = 10
        
        for page in range(1, max_pages + 1):
            url = base_url.format(page=page)
            print(f"\n[PAGE {page}] Fetching: {url}")
            
            driver.get(url)
            time.sleep(2)
            
            # Find product cards
            try:
                cards = driver.find_elements(By.CSS_SELECTOR, "div[data-js-pagination-item]")
                print(f"         Found {len(cards)} product cards")
                
                if not cards:
                    print(f"         No more products, stopping at page {page}")
                    break
                
                for i, card in enumerate(cards, 1):
                    product_data = extract_product_data_from_card(driver, card)
                    if product_data:
                        products.append(product_data)
                        print(f"         [{i}/{len(cards)}] {product_data['name'][:50]}...")
                
            except Exception as e:
                print(f"         Error on page {page}: {e}")
                break
        
        print(f"\n[COMPLETE] Scraped {len(products)} total products")
        
    finally:
        driver.quit()
    
    return products


def main():
    print("=" * 80)
    print("COMPUTERSALG DATA VERIFICATION TEST")
    print("=" * 80)
    
    # Scrape products
    print(f"\n[1/3] Scraping products from computersalg.no...")
    products = scrape_computersalg()
    
    if not products:
        print("      ⚠ No products found")
        return
    
    print(f"      ✓ Successfully scraped {len(products)} products")
    
    # Analyze data structure
    print(f"\n[2/3] Analyzing data structure...")
    
    if not products:
        print("      ⚠ No products found")
        return
    
    # Check first product structure
    first_product = products[0]
    print(f"\n      Fields in first product:")
    for key, value in first_product.items():
        value_type = type(value).__name__
        value_str = str(value)[:50] + "..." if value and len(str(value)) > 50 else str(value)
        print(f"        - {key:20s}: {value_type:10s} = {value_str}")
    
    # Check for missing required fields
    required_fields = ['product_url', 'name', 'in_stock']
    missing_fields = []
    for field in required_fields:
        if field not in first_product:
            missing_fields.append(field)
    
    if missing_fields:
        print(f"\n      ⚠ WARNING: Missing required fields: {missing_fields}")
    else:
        print(f"\n      ✓ All required fields present")
    
    # Check for None/empty values in required fields
    print(f"\n      Checking data quality...")
    issues = []
    for i, product in enumerate(products):
        for field in required_fields:
            if field not in product or product[field] is None or product[field] == '':
                issues.append(f"Product {i}: {field} is missing or empty")
        
        # Check URL validity
        if 'product_url' in product and product['product_url']:
            if not product['product_url'].startswith('http'):
                issues.append(f"Product {i}: Invalid URL (no http/https): {product['product_url']}")
    
    if issues:
        print(f"      ⚠ Found {len(issues)} data quality issues:")
        for issue in issues[:10]:  # Show first 10 issues
            print(f"        - {issue}")
        if len(issues) > 10:
            print(f"        ... and {len(issues) - 10} more issues")
    
    # Save to JSON
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    output_file = Path(__file__).parent / f"test_computersalg_data_{timestamp}.json"
    
    print(f"\n[SAVE] Writing data to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            'scraper': 'Computersalg',
            'url': 'https://www.computersalg.no/l/4979/byttekort',
            'scraped_at': datetime.now().isoformat(),
            'total_products': len(products),
            'products': products
        }, f, indent=2, ensure_ascii=False)
    
    print(f"       ✓ Data saved successfully")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total products scraped: {len(products)}")
    print(f"Data quality issues: {len(issues)}")
    print(f"Output file: {output_file}")
    print("\nNext steps:")
    print("1. Review the JSON file to verify data structure")
    print("2. Check for any missing or invalid fields")
    print("3. If data looks good, proceed with database integration")
    print("=" * 80)


if __name__ == "__main__":
    main()
