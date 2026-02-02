# competition/pokemadness.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from driver_setup import create_chromium_driver
from database import SessionLocal

from competition.pipeline import upsert_competitor_product
from competition.pricing import parse_price_ore
from competition.scrape_utils import normalize_url


BASE = "https://www.pokemadness.no"
URL = "https://www.pokemadness.no/185-panini-samlekort"
SITE_KEY = "pokemadness"
MIN_PRICE_ORE = 1000  # 10 kr minimum (booster packs are cheap)


# ---------- scrape ----------

def scrape():
    driver = create_chromium_driver(
        headless=True,
        use_old_headless=False,
        window_size="1280,720",
    )
    db = SessionLocal()

    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 25)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.js-product-miniature")))

        cards = driver.find_elements(By.CSS_SELECTOR, "article.js-product-miniature")
        print(f"[{SITE_KEY}] found {len(cards)} products")

        for idx, card in enumerate(cards, start=1):
            try:
                # ---- Name ----
                name = ""
                title_els = card.find_elements(By.CSS_SELECTOR, "h3.s_title_block a")
                if title_els:
                    name = title_els[0].text.strip()

                if not name:
                    raise RuntimeError("Missing product name")

                # Skip booster packs - only keep boxes and displays
                if "pack" in name.lower():
                    raise RuntimeError(f"Skipping booster pack: {name}")

                # ---- Link ----
                link = ""
                link_els = card.find_elements(By.CSS_SELECTOR, "h3.s_title_block a")
                if link_els:
                    link = link_els[0].get_attribute("href")
                    if link:
                        link = normalize_url(link, base=BASE)

                if not link:
                    raise RuntimeError("Missing product_link")

                # ---- Price ----
                price_ore = None
                price_els = card.find_elements(By.CSS_SELECTOR, "span.price")
                if price_els:
                    price_text = price_els[0].text.strip()
                    price_ore = parse_price_ore(price_text)

                # Skip if price is below minimum
                if price_ore is None or price_ore < MIN_PRICE_ORE:
                    raise RuntimeError(f"Price {price_ore} below minimum {MIN_PRICE_ORE}")

                # ---- Stock Status ----
                stock_status = "På lager"
                stock_amount = 1
                button_els = card.find_elements(By.CSS_SELECTOR, "a.view_button")
                if button_els:
                    button_text = button_els[0].text.strip()
                    if "utsolgt" in button_text.lower() or "out of stock" in button_text.lower():
                        stock_status = "Utsolgt"
                        stock_amount = 0
                
                # Get exact stock from product detail page
                if link and stock_status == "På lager":
                    try:
                        # Store current window handle
                        original_window = driver.current_window_handle
                        
                        # Open product page in new tab
                        driver.execute_script(f"window.open('{link}', '_blank');")
                        driver.switch_to.window(driver.window_handles[-1])
                        
                        # Wait for product availability element to load
                        try:
                            WebDriverWait(driver, 8).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "span.product-quantities[data-stock]"))
                            )
                            
                            # Extract stock quantity from data-stock attribute
                            stock_el = driver.find_element(By.CSS_SELECTOR, "span.product-quantities[data-stock]")
                            stock_text = stock_el.get_attribute("data-stock")
                            if stock_text and stock_text.isdigit():
                                stock_amount = int(stock_text)
                                print(f"      Stock found: {stock_amount} units")
                        except:
                            # If stock element not found, keep default value of 1
                            pass
                        
                        # Close the product tab and return to original window
                        driver.close()
                        driver.switch_to.window(original_window)
                    except Exception as e:
                        # If anything goes wrong, just continue with default stock
                        try:
                            if len(driver.window_handles) > 1:
                                driver.close()
                        except:
                            pass
                        try:
                            driver.switch_to.window(driver.window_handles[0])
                        except:
                            pass

                # Insert into database
                upsert_competitor_product(
                    db,
                    website=SITE_KEY,
                    product_link=link,
                    raw_name=name,
                    price_ore=price_ore,
                    stock_status=stock_status,
                    stock_amount=stock_amount,
                )

                print(f"[{idx:02d}] {name or '(NO NAME)'} | {price_ore/100:.2f} kr | {stock_status}")

            except Exception as e:
                print(f"[!] skip {idx}: {e}")

        db.commit()

    finally:
        driver.quit()
        db.close()


if __name__ == "__main__":
    scrape()
    print("[pokemadness] Pokemadness scraper finished")