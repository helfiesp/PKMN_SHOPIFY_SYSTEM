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

for idx, card in enumerate(cards):
    try:
        name_els = card.find_elements(By.CSS_SELECTOR, 'h2 a')
        name = name_els[0].text if name_els else 'N/A'
        
        price_els = card.find_elements(By.CSS_SELECTOR, 'span.price')
        price_text = price_els[0].text if price_els else 'N/A'
        
        print(f'{idx+1:2d}. Name: {name[:50]:50} | Price: "{price_text}"')
    except Exception as e:
        print(f'{idx+1:2d}. Error: {e}')

driver.quit()
