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
    
    def scrape_products(self) -> list:
        """Scrape all products from listing pages"""
        print(f"Scraping: {self.start_url}")
        self.driver.get(self.start_url)
        self.wait(5)
        
        all_products = []
        page = 1
        max_pages = 10  # Safety limit
        
        while page <= max_pages:
            print(f"Processing page {page}...")
            
            # Find all product cards
            product_cards = self.driver.find_elements("css selector", "div[data-js-pagination-item]")
            print(f"Found {len(product_cards)} products on page {page}")
            
            for card in product_cards:
                try:
                    product_data = self.extract_product_data_from_card(card)
                    if product_data:
                        all_products.append(product_data)
                except Exception as e:
                    print(f"Error extracting product card: {e}")
                    continue
            
            # Check for next page
            try:
                if page >= max_pages:
                    break
                
                # Try to navigate to next page by updating URL
                current_url = self.driver.current_url
                if 'page=' in current_url:
                    next_page_url = re.sub(r'page=\d+', f'page={page+1}', current_url)
                else:
                    next_page_url = current_url + f"&page={page+1}"
                
                self.driver.get(next_page_url)
                self.wait(5)
                
                # Check if we got new products (if not, we've reached the end)
                new_cards = self.driver.find_elements("css selector", "div[data-js-pagination-item]")
                if len(new_cards) == 0:
                    break
                    
                page += 1
            except Exception:
                break
        
        print(f"Total products found: {len(all_products)}")
        return all_products
    
    def extract_product_data_from_card(self, card) -> dict:
        """Extract product data from a product card element"""
        try:
            # Get product URL
            link_elem = card.find_element("css selector", "a[href*='/i/']")
            url = link_elem.get_attribute("href")
            
            if not url:
                print("No URL found, skipping product")
                return None
            
            # Extract product name
            name_elem = card.find_element("css selector", "h3.m-product-card__name")
            name = self.get_element_text(name_elem).strip()
            
            if not name:
                print(f"No name found for {url}, skipping")
                return None
            
            # Clean up name - remove quotes and extra whitespace
            name = name.replace('„', '').replace('"', '').replace('  ', ' ').strip()
            
            # Extract price
            price = None
            try:
                price_elem = card.find_element("css selector", "span.m-product-card__price-text")
                price_text = self.get_element_text(price_elem).strip()
                # Remove spaces, thousand separator dots, and convert comma to decimal
                price_text = price_text.replace(' ', '').replace('.', '').replace(',', '.')
                price = float(price_text)
            except Exception as e:
                print(f"Could not extract price for {name}: {e}")
            
            # Extract SKU
            sku = None
            try:
                sku_elem = card.find_element("css selector", "span[itemprop*='sku']")
                sku = self.get_element_text(sku_elem).strip()
            except Exception:
                pass
            
            # Check stock status
            in_stock = False
            try:
                # Look for stock indicator
                card.find_element("css selector", "span.stock.green")
                in_stock = True
            except Exception:
                in_stock = False
            
            # Extract image URL
            image_url = None
            try:
                img_elem = card.find_element("css selector", "div.m-product-card__image img")
                image_url = img_elem.get_attribute("src")
                if image_url and image_url.startswith('//'):
                    image_url = 'https:' + image_url
                # Skip placeholder images
                if image_url and 'data:image' in image_url:
                    image_url = None
            except Exception:
                pass
            
            return {
                'product_url': url,
                'name': name,
                'price': price,
                'sku': sku,
                'in_stock': in_stock,
                'image_url': image_url,
                'stock_quantity': None,
                'category': None,
            }
        
        except Exception as e:
            print(f"Error extracting card data: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def wait(self, seconds: int):
        """Wait for a specified number of seconds"""
        import time
        time.sleep(seconds)
    
    def get_element_text(self, element):
        """Get text content from an element using JavaScript"""
        return self.driver.execute_script("return arguments[0].textContent;", element)


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
