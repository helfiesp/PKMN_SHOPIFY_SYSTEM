#!/usr/bin/env python3
"""
Standalone test script to verify gamezone scraper data extraction
"""
import json
import sys
import re
from pathlib import Path
from datetime import datetime
import time

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from driver_setup import create_chromium_driver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)


def extract_product_data_from_card(card):
    """Extract product data from a Gamezone product card."""
    try:
        # Get metadata container
        meta_data_div = card.find_element(By.CSS_SELECTOR, "div.ad-meta-data")
        
        # Extract basic info
        product_number = meta_data_div.get_attribute("productnumber")
        product_desc1 = meta_data_div.get_attribute("productdescription1") or ""
        product_desc2 = meta_data_div.get_attribute("productdescription2") or ""
        in_stock_attr = meta_data_div.get_attribute("instock")
        
        # Combine descriptions for name
        name = f"{product_desc1} {product_desc2}".strip()
        
        # Get product URL from the link
        try:
            link = card.find_element(By.CSS_SELECTOR, "a[href*='/produkter/']")
            product_url = link.get_attribute("href")
        except:
            return None
        
        # Stock status
        in_stock = in_stock_attr == "True"
        
        # Get price
        price = None
        try:
            price_elem = card.find_element(By.CSS_SELECTOR, "span.AddPriceLabel")
            price_text = price_elem.text.strip()
            price_match = re.search(r'([\d\s]+)', price_text.replace(',', '.'))
            if price_match:
                price = float(price_match.group(1).replace(' ', ''))
        except:
            pass
        
        # Get stock quantity if available
        stock_quantity = None
        try:
            stock_tooltip = card.find_element(By.CSS_SELECTOR, "span.DynamicStockTooltipContainer")
            stock_text = stock_tooltip.text.strip()
            stock_match = re.search(r'(\d+)', stock_text)
            if stock_match:
                stock_quantity = int(stock_match.group(1))
        except:
            pass
        
        # Get category from meta data
        category_parts = []
        try:
            level1 = meta_data_div.get_attribute("productgrouplevel1")
            level2 = meta_data_div.get_attribute("productgrouplevel2")
            level3 = meta_data_div.get_attribute("productgrouplevel3")
            
            if level1:
                category_parts.append(level1)
            if level2:
                category_parts.append(level2)
            if level3:
                category_parts.append(level3)
        except:
            pass
        
        category = " > ".join(category_parts) if category_parts else None
        
        # Get image URL
        image_url = None
        try:
            img = card.find_element(By.CSS_SELECTOR, "img[src]")
            image_url = img.get_attribute("src")
        except:
            pass
        
        product_data = {
            "product_url": product_url,
            "name": name,
            "in_stock": in_stock,
            "price": price,
            "sku": product_number,
            "image_url": image_url,
            "stock_quantity": stock_quantity,
            "category": category
        }
        
        return product_data
        
    except Exception as e:
        logger.error(f"Error extracting product: {e}")
        return None


def main():
    logger.info("Starting Gamezone scraper test")
    
    driver = create_chromium_driver(headless=True)
    all_products = []
    
    try:
        base_url = "https://gamezone.no/samlekort/pokemon"
        page = 1
        max_pages = 10
        
        while page <= max_pages:
            logger.info(f"Scraping page {page}")
            
            # Build page URL
            if page == 1:
                url = base_url
            else:
                url = f"{base_url}?page={page}"
            
            driver.get(url)
            time.sleep(2)
            
            # Wait for product cards
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.WebPubElement.pub-productlisting"))
                )
            except:
                logger.warning(f"No products found on page {page}")
                break
            
            # Find product cards
            product_cards = driver.find_elements(By.CSS_SELECTOR, "div.WebPubElement.pub-productlisting")
            
            if not product_cards:
                logger.info(f"No more products on page {page}")
                break
            
            logger.info(f"Found {len(product_cards)} product cards on page {page}")
            
            # Debug: save first card HTML to file
            if page == 1 and product_cards:
                with open("gamezone_card_sample.html", "w", encoding="utf-8") as f:
                    f.write(product_cards[0].get_attribute('outerHTML'))
                logger.info("Saved first card HTML to gamezone_card_sample.html")
            
            # Extract data from each card
            for idx, card in enumerate(product_cards):
                product_data = extract_product_data_from_card(card)
                if product_data:
                    all_products.append(product_data)
                elif idx < 3:  # Debug first 3 failures
                    logger.warning(f"Failed to extract data from card {idx}, HTML: {card.get_attribute('outerHTML')[:500]}")
            
            # Check if there's a next page
            page += 1
            
            # Safety limit
            if page > max_pages:
                logger.warning(f"Reached max pages limit ({max_pages})")
                break
        
        # Print summary
        logger.info(f"\n{'='*80}")
        logger.info("SCRAPING COMPLETE")
        logger.info(f"{'='*80}")
        logger.info(f"Total products: {len(all_products)}")
        
        in_stock = sum(1 for p in all_products if p['in_stock'])
        out_of_stock = len(all_products) - in_stock
        
        logger.info(f"In stock: {in_stock}")
        logger.info(f"Out of stock: {out_of_stock}")
        
        # Show first 5 products
        if all_products:
            logger.info(f"\n{'='*80}")
            logger.info("SAMPLE PRODUCTS (first 5):")
            logger.info(f"{'='*80}")
            
            for i, product in enumerate(all_products[:5], 1):
                logger.info(f"\nProduct {i}:")
                logger.info(f"  Name: {product['name']}")
                logger.info(f"  SKU: {product['sku']}")
                logger.info(f"  Price: {product['price']}")
                logger.info(f"  In Stock: {product['in_stock']}")
                logger.info(f"  Stock Qty: {product['stock_quantity']}")
                logger.info(f"  Category: {product['category']}")
                logger.info(f"  URL: {product['product_url'][:60]}...")
        
        # Validate data
        logger.info(f"\n{'='*80}")
        logger.info("DATA VALIDATION:")
        logger.info(f"{'='*80}")
        
        required_fields = ['product_url', 'name', 'in_stock', 'sku']
        missing_fields = []
        
        for i, product in enumerate(all_products):
            for field in required_fields:
                if field not in product or product[field] is None:
                    missing_fields.append(f"Product {i}: missing {field}")
        
        if missing_fields:
            logger.error(f"Found {len(missing_fields)} validation errors:")
            for error in missing_fields[:10]:
                logger.error(f"  {error}")
        else:
            logger.info("✓ All products have required fields")
        
        # Save to JSON
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"gamezone_test_{timestamp}.json"
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(all_products, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n✓ Saved {len(all_products)} products to {output_file}")
        
    finally:
        driver.quit()
        logger.info("Driver closed")


if __name__ == "__main__":
    main()
