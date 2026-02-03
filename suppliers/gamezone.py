"""
Gamezone.no supplier scraper for Pokemon TCG products.
Website: https://gamezone.no/samlekort/pokemon
"""

import logging
import time
from typing import List, Dict, Optional
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from suppliers.base_scraper import BaseSupplierScraper

logger = logging.getLogger(__name__)


class GamezoneScraper(BaseSupplierScraper):
    """Scraper for Gamezone.no Pokemon products."""
    
    def __init__(self, website_id: int):
        super().__init__(
            website_id=website_id,
            base_url="https://gamezone.no/samlekort/pokemon"
        )
    
    def scrape_products(self) -> List[Dict]:
        """
        Scrape all Pokemon products from Gamezone.no.
        
        Returns:
            List of product dictionaries with keys:
            - product_url: Full URL to product page
            - name: Product name
            - in_stock: Boolean stock status
            - price: Float price (optional)
            - sku: Product SKU/number
            - image_url: Product image URL
            - stock_quantity: Integer stock count (optional)
            - category: Product category (optional)
        """
        products = []
        page = 1
        
        while True:
            logger.info(f"Scraping page {page}")
            
            # Build page URL (first page has no ?page=1, subsequent pages do)
            if page == 1:
                url = self.base_url
            else:
                url = f"{self.base_url}?page={page}"
            
            self.driver.get(url)
            time.sleep(2)  # Wait for page load
            
            # Wait for product cards to load
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "div.WebPubElement.pub-productlisting"))
                )
            except Exception as e:
                logger.warning(f"No products found on page {page}: {e}")
                break
            
            # Find all product cards
            product_cards = self.driver.find_elements(By.CSS_SELECTOR, "div.WebPubElement.pub-productlisting")
            
            if not product_cards:
                logger.info(f"No more products found on page {page}")
                break
            
            logger.info(f"Found {len(product_cards)} product cards on page {page}")
            
            # Extract data from each card
            for card in product_cards:
                try:
                    product_data = self.extract_product_data_from_card(card)
                    if product_data:
                        products.append(product_data)
                except Exception as e:
                    logger.error(f"Error extracting product data: {e}")
                    continue
            
            # Check if there's a next page
            try:
                # Look for pagination - next page button or active page indicator
                next_buttons = self.driver.find_elements(By.CSS_SELECTOR, "a.page-link[rel='next']")
                if not next_buttons:
                    logger.info("No next page button found, reached last page")
                    break
            except Exception as e:
                logger.info(f"No more pages: {e}")
                break
            
            page += 1
            time.sleep(1)  # Be nice to the server
        
        logger.info(f"Total products scraped: {len(products)}")
        return products
    
    def extract_product_data_from_card(self, card) -> Optional[Dict]:
        """
        Extract product data from a single product card element.
        
        Args:
            card: Selenium WebElement for the product card
            
        Returns:
            Dictionary with product data or None if extraction fails
        """
        try:
            # Get metadata container which has many useful attributes
            meta_data = card.find_element(By.CSS_SELECTOR, "div.ad-meta-data")
            
            # SKU from productnumber attribute
            sku = meta_data.get_attribute("productnumber")
            if not sku:
                logger.warning("Product has no SKU, skipping")
                return None
            
            # Product URL from link
            product_link = card.find_element(By.CSS_SELECTOR, "div.AddHeaderContainer a.AdProductLink")
            product_url_path = product_link.get_attribute("href")
            
            # Ensure full URL
            if product_url_path.startswith("/"):
                product_url = f"https://gamezone.no{product_url_path}"
            else:
                product_url = product_url_path
            
            # Product name - combine AddHeader1 and productdescription2
            name_part1 = meta_data.get_attribute("productdescription1") or ""
            name_part2 = meta_data.get_attribute("productdescription2") or ""
            
            if name_part2 and name_part2.strip():
                name = f"{name_part1} {name_part2}".strip()
            else:
                name = name_part1.strip()
            
            if not name:
                logger.warning(f"Product {sku} has no name, skipping")
                return None
            
            # Price from AddPriceLabel span
            price = None
            try:
                price_elem = card.find_element(By.CSS_SELECTOR, "span.AddPriceLabel")
                price_text = price_elem.text.strip()
                # Remove spaces and convert "499,-" or "1 398,-" to float
                price_text = price_text.replace(" ", "").replace(",-", "").replace(",", ".")
                price = float(price_text)
            except Exception as e:
                logger.debug(f"Could not extract price for {sku}: {e}")
            
            # In stock status from metadata attribute
            in_stock_str = meta_data.get_attribute("instock")
            in_stock = in_stock_str == "True"
            
            # Stock quantity from AddStockContainer
            stock_quantity = None
            if in_stock:
                try:
                    stock_container = card.find_element(By.CSS_SELECTOR, "div.AddStockContainer div.DynamicStockTooltipContainer")
                    # Find the span that contains just the number (not the text "Antall på lager:")
                    stock_spans = stock_container.find_elements(By.TAG_NAME, "span")
                    for span in stock_spans:
                        span_text = span.text.strip()
                        if span_text.isdigit():
                            stock_quantity = int(span_text)
                            break
                except Exception as e:
                    logger.debug(f"Could not extract stock quantity for {sku}: {e}")
            
            # Image URL
            image_url = None
            try:
                img_elem = card.find_element(By.CSS_SELECTOR, "div.AddProductImage img")
                image_url = img_elem.get_attribute("src")
                # Ensure full URL
                if image_url and image_url.startswith("/"):
                    image_url = f"https://gamezone.no{image_url}"
            except Exception as e:
                logger.debug(f"Could not extract image for {sku}: {e}")
            
            # Category from product group levels
            category = None
            try:
                level1 = meta_data.get_attribute("productgrouplevel1") or ""
                level2 = meta_data.get_attribute("productgrouplevel2") or ""
                level3 = meta_data.get_attribute("productgrouplevel3") or ""
                
                category_parts = [p for p in [level1, level2, level3] if p and p.strip()]
                if category_parts:
                    category = " > ".join(category_parts)
            except Exception as e:
                logger.debug(f"Could not extract category for {sku}: {e}")
            
            return {
                "product_url": product_url,
                "name": name,
                "in_stock": in_stock,
                "price": price,
                "sku": sku,
                "image_url": image_url,
                "stock_quantity": stock_quantity,
                "category": category
            }
            
        except Exception as e:
            logger.error(f"Error extracting product data from card: {e}")
            return None
