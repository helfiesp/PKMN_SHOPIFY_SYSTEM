"""
Base scraper class for supplier websites.
Extend this class to create custom scrapers for specific suppliers.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Dict, Optional
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.database import get_db
from app.services.supplier_service import SupplierService
from app.models import SupplierWebsite
from driver_setup import create_chromium_driver

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger(__name__)


class BaseSupplierScraper(ABC):
    """Base class for supplier website scrapers."""

    def __init__(self, website_id: int):
        """
        Initialize scraper.
        
        Args:
            website_id: ID of the SupplierWebsite to scrape
        """
        self.website_id = website_id
        self.driver = None
        self.db = next(get_db())
        
        # Load website config
        self.website = SupplierService.get_supplier_website(self.db, website_id)
        if not self.website:
            raise ValueError(f"Supplier website {website_id} not found")
        
        LOG.info(f"Initialized scraper for {self.website.name}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup driver."""
        if self.driver:
            try:
                self.driver.quit()
            except Exception as e:
                LOG.warning(f"Error closing driver: {e}")
        
        if self.db:
            self.db.close()

    def run(self) -> Dict:
        """
        Run the scraper.
        
        Returns:
            Dict with scan results
        """
        started_at = datetime.now(timezone.utc)
        products_found = 0
        new_products = 0
        restocked_products = 0
        error_message = None
        status = "success"

        try:
            LOG.info(f"Starting scan of {self.website.name}")
            
            # Initialize browser
            self.driver = create_chromium_driver(headless=True)
            
            # Scrape products
            products = self.scrape_products()
            products_found = len(products)
            
            LOG.info(f"Found {products_found} products")
            
            # Process each product
            for product_data in products:
                product, is_new, is_restocked = SupplierService.update_or_create_product(
                    db=self.db,
                    website_id=self.website_id,
                    **product_data
                )
                
                if is_new:
                    new_products += 1
                    LOG.info(f"NEW: {product.name}")
                    
                    # Create alert
                    if self.website.notify_on_new_products:
                        SupplierService.create_alert(
                            db=self.db,
                            product_id=product.id,
                            alert_type="new_product",
                            message=f"New product found: {product.name}"
                        )
                
                if is_restocked:
                    restocked_products += 1
                    LOG.info(f"RESTOCKED: {product.name}")
                    
                    # Create alert
                    if self.website.notify_on_restock:
                        SupplierService.create_alert(
                            db=self.db,
                            product_id=product.id,
                            alert_type="restock",
                            message=f"Product restocked: {product.name}"
                        )
            
        except Exception as e:
            LOG.error(f"Error during scan: {e}", exc_info=True)
            status = "failed"
            error_message = str(e)
        
        finally:
            # Record scan log
            completed_at = datetime.now(timezone.utc)
            log = SupplierService.create_scan_log(
                db=self.db,
                website_id=self.website_id,
                status=status,
                products_found=products_found,
                new_products=new_products,
                restocked_products=restocked_products,
                error_message=error_message,
                started_at=started_at,
                completed_at=completed_at,
            )
            
            LOG.info(f"Scan complete: {status}")
            LOG.info(f"Products found: {products_found}, New: {new_products}, Restocked: {restocked_products}")
        
        return {
            "status": status,
            "products_found": products_found,
            "new_products": new_products,
            "restocked_products": restocked_products,
            "error_message": error_message,
        }

    @abstractmethod
    def scrape_products(self) -> List[Dict]:
        """
        Scrape products from the supplier website.
        
        Must be implemented by subclasses.
        
        Returns:
            List of product dicts with keys:
                - product_url (str, required)
                - name (str, required)
                - in_stock (bool, required)
                - price (float, optional)
                - stock_quantity (int, optional)
                - sku (str, optional)
                - category (str, optional)
                - image_url (str, optional)
                - description (str, optional)
                - external_id (str, optional)
        """
        pass

    def wait_for_element(self, by: By, value: str, timeout: int = 10):
        """Wait for an element to be present."""
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )


# ===========================================================================
# Example scraper implementation
# ===========================================================================

class ExampleSupplierScraper(BaseSupplierScraper):
    """Example scraper - customize this for your specific supplier."""

    def scrape_products(self) -> List[Dict]:
        """Scrape products from example supplier."""
        products = []
        
        # Navigate to the products page
        self.driver.get(self.website.url)
        
        # TODO: Customize this logic for your specific supplier
        # This is just an example structure
        
        # Wait for products to load
        # product_elements = self.wait_for_element(By.CLASS_NAME, "product-card")
        
        # Example: Find all product cards
        # for element in self.driver.find_elements(By.CLASS_NAME, "product-card"):
        #     try:
        #         name = element.find_element(By.CLASS_NAME, "product-name").text
        #         url = element.find_element(By.TAG_NAME, "a").get_attribute("href")
        #         price_text = element.find_element(By.CLASS_NAME, "price").text
        #         price = float(price_text.replace("kr", "").replace(",", "").strip())
        #         
        #         in_stock = "in stock" in element.text.lower()
        #         
        #         products.append({
        #             "product_url": url,
        #             "name": name,
        #             "in_stock": in_stock,
        #             "price": price,
        #             "currency": "NOK",
        #         })
        #     except Exception as e:
        #         LOG.warning(f"Error parsing product: {e}")
        #         continue
        
        LOG.warning("ExampleSupplierScraper.scrape_products() not implemented")
        LOG.warning("Create a custom scraper class for your specific supplier")
        
        return products


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python base_scraper.py <website_id>")
        sys.exit(1)
    
    website_id = int(sys.argv[1])
    
    with ExampleSupplierScraper(website_id) as scraper:
        result = scraper.run()
        print(f"\nScan Results:")
        print(f"  Status: {result['status']}")
        print(f"  Products found: {result['products_found']}")
        print(f"  New products: {result['new_products']}")
        print(f"  Restocked: {result['restocked_products']}")
        if result['error_message']:
            print(f"  Error: {result['error_message']}")
