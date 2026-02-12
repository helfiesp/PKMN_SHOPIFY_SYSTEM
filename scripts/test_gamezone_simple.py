"""
Simple test script for Gamezone scraper.
Tests data extraction without database operations.
"""

import logging
from driver_setup import create_chromium_driver
from suppliers.gamezone import GamezoneScraper

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

def main():
    """Test the Gamezone scraper."""
    logger.info("Starting Gamezone scraper test")
    
    # Create driver
    driver = create_chromium_driver()
    
    try:
        # Create scraper instance (website_id doesn't matter for testing)
        scraper = GamezoneScraper(website_id=999)
        scraper.driver = driver
        
        # Scrape products
        logger.info("Scraping products from Gamezone...")
        products = scraper.scrape_products()
        
        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info(f"SCRAPING COMPLETE")
        logger.info(f"{'='*60}")
        logger.info(f"Total products found: {len(products)}")
        
        # Count in-stock vs out-of-stock
        in_stock_count = sum(1 for p in products if p['in_stock'])
        out_of_stock_count = len(products) - in_stock_count
        
        logger.info(f"In stock: {in_stock_count}")
        logger.info(f"Out of stock: {out_of_stock_count}")
        
        # Show first 3 products as examples
        if products:
            logger.info(f"\n{'='*60}")
            logger.info("SAMPLE PRODUCTS (first 3):")
            logger.info(f"{'='*60}")
            
            for i, product in enumerate(products[:3], 1):
                logger.info(f"\nProduct {i}:")
                logger.info(f"  Name: {product['name']}")
                logger.info(f"  SKU: {product['sku']}")
                logger.info(f"  Price: {product['price']}")
                logger.info(f"  In Stock: {product['in_stock']}")
                logger.info(f"  Stock Qty: {product['stock_quantity']}")
                logger.info(f"  Category: {product['category']}")
                logger.info(f"  URL: {product['product_url']}")
                logger.info(f"  Image: {product['image_url'][:80] if product['image_url'] else None}...")
        
        # Verify data structure
        logger.info(f"\n{'='*60}")
        logger.info("DATA STRUCTURE VALIDATION:")
        logger.info(f"{'='*60}")
        
        required_fields = ['product_url', 'name', 'in_stock', 'sku']
        for i, product in enumerate(products):
            for field in required_fields:
                if field not in product or product[field] is None:
                    logger.error(f"Product {i} missing required field: {field}")
                    logger.error(f"Product data: {product}")
                    
        logger.info("All products have required fields ✓")
        
    finally:
        driver.quit()
        logger.info("Driver closed")

if __name__ == "__main__":
    main()
