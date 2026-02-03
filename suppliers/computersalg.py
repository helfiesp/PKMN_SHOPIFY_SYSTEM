#!/usr/bin/env python3
"""
Computersalg.no Pokemon TCG scraper
"""
import sys
import re
from suppliers.base_scraper import BaseSupplierScraper


class ComputersalgScraper(BaseSupplierScraper):
    """Scraper for computersalg.no Pokemon products"""
    
    def __init__(self, website_id: int):
        super().__init__(website_id)
        self.base_url = "https://www.computersalg.no"
        # Start URL for Pokemon trading cards
        self.start_url = "https://www.computersalg.no/l/4979/byttekort?f=c72d38dc-9dd6-4d3f-93cc-44bfd26b97aa&p=1&sq=&csstock=0"
    
    def get_product_urls(self) -> list:
        """Get all product URLs from the listing page"""
        print(f"Scraping: {self.start_url}")
        self.driver.get(self.start_url)
        self.wait_for_page_load()
        
        product_urls = []
        page = 1
        max_pages = 10  # Safety limit
        
        while page <= max_pages:
            print(f"Processing page {page}...")
            
            # Find all product cards
            product_cards = self.driver.find_elements("css selector", "div[data-js-pagination-item]")
            print(f"Found {len(product_cards)} products on page {page}")
            
            for card in product_cards:
                try:
                    # Get product link
                    link_elem = card.find_element("css selector", "a[href*='/i/']")
                    href = link_elem.get_attribute("href")
                    if href and href not in product_urls:
                        product_urls.append(href)
                except Exception as e:
                    print(f"Error extracting product URL: {e}")
                    continue
            
            # Check for next page button
            try:
                # Look for pagination - the page parameter in URL
                current_url = self.driver.current_url
                if f"page={page+1}" in current_url or page >= max_pages:
                    break
                
                # Try to navigate to next page by updating URL
                next_page_url = re.sub(r'page=\d+', f'page={page+1}', current_url)
                if 'page=' not in current_url:
                    next_page_url = current_url + f"&page={page+1}"
                
                self.driver.get(next_page_url)
                self.wait_for_page_load()
                page += 1
            except Exception:
                break
        
        print(f"Total products found: {len(product_urls)}")
        return product_urls
    
    def extract_product_data(self, url: str) -> dict:
        """Extract product data from product page"""
        self.driver.get(url)
        self.wait_for_page_load()
        
        try:
            # Extract product name
            name_elem = self.driver.find_element("css selector", "h3.m-product-card__name")
            name = self.get_text_content(name_elem).strip()
            
            # Clean up name - remove quotes and extra whitespace
            name = name.replace('„', '').replace('"', '').replace('  ', ' ').strip()
            
            # Extract price
            price = None
            try:
                price_elem = self.driver.find_element("css selector", "span.m-product-card__price-text")
                price_text = self.get_text_content(price_elem).strip()
                # Remove thousand separator and convert to float
                price_text = price_text.replace('.', '').replace(',', '.').replace(' ', '')
                price = float(price_text)
            except Exception as e:
                print(f"Could not extract price: {e}")
            
            # Extract SKU
            sku = None
            try:
                sku_elem = self.driver.find_element("css selector", "span[itemprop*='sku']")
                sku = self.get_text_content(sku_elem).strip()
            except Exception:
                pass
            
            # Check stock status
            in_stock = False
            try:
                # Look for stock indicator
                stock_elem = self.driver.find_element("css selector", "span.stock.green")
                in_stock = True
            except Exception:
                # If green stock not found, check for red (out of stock)
                try:
                    self.driver.find_element("css selector", "span.stock.red")
                    in_stock = False
                except Exception:
                    # Default to False if no stock indicator found
                    in_stock = False
            
            # Extract image URL
            image_url = None
            try:
                img_elem = self.driver.find_element("css selector", "div.m-product-card__image img")
                image_url = img_elem.get_attribute("src")
            except Exception:
                pass
            
            return {
                'name': name,
                'price': price,
                'sku': sku,
                'in_stock': in_stock,
                'image_url': image_url,
                'currency': 'NOK',
            }
        
        except Exception as e:
            print(f"Error extracting product data from {url}: {e}")
            return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python computersalg.py <website_id>")
        sys.exit(1)
    
    website_id = int(sys.argv[1])
    scraper = ComputersalgScraper(website_id)
    
    try:
        scraper.run()
        print(f"\nScan completed successfully!")
        print(f"Total products scraped: {scraper.products_scraped}")
        print(f"New products: {scraper.new_products}")
        print(f"Restocked products: {scraper.restocked_products}")
    except Exception as e:
        print(f"\nScan failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
