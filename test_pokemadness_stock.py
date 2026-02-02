#!/usr/bin/env python3
import os
os.environ['CHROMEDRIVER_PATH'] = r'C:\Users\cmhag\Documents\Projects\Shopify\chromedriver-win64\chromedriver.exe'

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver_setup import create_chromium_driver

driver = create_chromium_driver(headless=True, use_old_headless=False, window_size='1280,720')
url = 'https://www.pokemadness.no/185-panini-samlekort'
driver.get(url)

wait = WebDriverWait(driver, 25)
wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'article.js-product-miniature')))

cards = driver.find_elements(By.CSS_SELECTOR, 'article.js-product-miniature')
print(f'Found {len(cards)} cards\n')

# Get first product URL
first_card = cards[0]
link_els = first_card.find_elements(By.CSS_SELECTOR, 'h3.s_title_block a')
if link_els:
    product_url = link_els[0].get_attribute('href')
    print(f'Visiting first product: {product_url}\n')
    
    driver.get(product_url)
    
    # Wait for product page to load
    try:
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '[data-stock], [data-quantity], .stock')))
    except:
        pass
    
    # Look for stock info
    import re
    page_html = driver.page_source
    
    # Search for stock/quantity in page
    patterns = [
        r'stock["\']?\s*[=:]\s*(["\']?)(\d+)\1',
        r'quantity["\']?\s*[=:]\s*(["\']?)(\d+)\1',
        r'available["\']?\s*[=:]\s*(["\']?)(\d+)\1',
        r'<span[^>]*class="[^"]*stock[^"]*"[^>]*>([^<]+)</span>',
        r'(in stock|out of stock|en stock|utsolgt)',
    ]
    
    print('Looking for stock patterns in product page...\n')
    for pattern in patterns:
        matches = re.findall(pattern, page_html, re.IGNORECASE)
        if matches:
            print(f'Pattern found: {pattern}')
            print(f'Matches: {matches}\n')

driver.quit()
