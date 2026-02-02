# competition/boosterpakker.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from driver_setup import create_chromium_driver
from database import SessionLocal

from competition.pipeline import upsert_competitor_product
from competition.pricing import parse_price_ore, format_ore
from competition.scrape_utils import el_text, normalize_url


BASE = "https://boosterpakker.no"
URL = "https://boosterpakker.no/butikk/booster-bokser"
SITE_KEY = "boosterpakker"


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
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.productlist__product")))

        root_candidates = driver.find_elements(By.CSS_SELECTOR, "section.productlist, .productlist")
        root = root_candidates[0] if root_candidates else driver

        cards = root.find_elements(By.CSS_SELECTOR, "article.productlist__product")
        print(f"[{SITE_KEY}] found {len(cards)} products")

        for idx, card in enumerate(cards, start=1):
            try:
                # ---- Name ----
                name = ""
                els = card.find_elements(By.CSS_SELECTOR, "h3.productlist__product__headline")
                if els:
                    name = el_text(els[0])
                if not name:
                    els = card.find_elements(By.CSS_SELECTOR, '[itemprop="name"]')
                    if els:
                        name = el_text(els[0])

                # ---- Link ----
                a = card.find_element(By.CSS_SELECTOR, "a.productlist__product-wrap")
                href = (a.get_attribute("href") or a.get_attribute("data-href") or "").strip()
                if not href:
                    meta_url = card.find_elements(By.CSS_SELECTOR, 'meta[itemprop="url"][content]')
                    href = (meta_url[0].get_attribute("content") or "").strip() if meta_url else ""

                product_link = normalize_url(href, base=BASE)
                if not product_link:
                    raise RuntimeError("Missing product_link")

                # ---- Price (øre) ----
                price_val = ""
                price_meta = card.find_elements(By.CSS_SELECTOR, '[itemprop="price"][content]')
                if price_meta:
                    price_val = (price_meta[0].get_attribute("content") or "").strip()
                if not price_val:
                    disp = card.find_elements(By.CSS_SELECTOR, ".price__display, .price")
                    price_val = el_text(disp[0]) if disp else ""

                price_ore = parse_price_ore(price_val)

                # ---- Stock (COUNT) ----
                stock_amount = 0
                metas = card.find_elements(By.CSS_SELECTOR, "meta[id^='stock-status-']")
                if metas:
                    stock_meta = metas[0]
                    ds = (stock_meta.get_attribute("data-stock") or "").strip()
                    content = (stock_meta.get_attribute("content") or "").strip()
                    digits = "".join(ch for ch in (ds or content) if ch.isdigit())
                    stock_amount = int(digits) if digits else 0

                stock_status = "På lager" if stock_amount > 0 else "Utsolgt"

                # ---- Persist (centralized normalization + canonicalization + snapshots) ----
                upsert_competitor_product(
                    db,
                    website=SITE_KEY,
                    product_link=product_link,
                    raw_name=name,
                    price_ore=price_ore,
                    stock_status=stock_status,
                    stock_amount=stock_amount,
                )

                # ---- Print ----
                pretty = format_ore(price_ore)
                print(f"[{idx:02d}] {name or '(NO NAME)'} | {pretty} | {stock_status} [{stock_amount}]")

            except Exception as e:
                print(f"[!] skip {idx}: {e}")

        db.commit()

    finally:
        driver.quit()
        db.close()


if __name__ == "__main__":
    scrape()
