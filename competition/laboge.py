# competition/laboge.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import time
from selenium.common.exceptions import TimeoutException

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from driver_setup import create_chromium_driver
from database import SessionLocal

from competition.pipeline import upsert_competitor_product
from competition.pricing import parse_price_ore, format_ore
from competition.scrape_utils import el_text, normalize_url


BASE = "https://laboge.no"
START_URL = "https://laboge.no/collections/sealed"
SITE_KEY = "laboge"


# ---------- site helpers ----------

def extract_price_text(item) -> str:
    selectors = [
        ".price__sale .price-item--sale.price-item--last",
        ".price__regular .price-item--regular",
        ".price .price-item--last",
        ".price .price-item--regular",
        ".price",
    ]
    for sel in selectors:
        els = item.find_elements(By.CSS_SELECTOR, sel)
        if els:
            t = el_text(els[0]).strip()
            if t:
                return t
    return ""


def infer_sold_out(item) -> bool:
    # badge-based first
    for sel in [".card__badge", ".badge", ".price__badge-sold-out", ".badge--sold-out"]:
        for b in item.find_elements(By.CSS_SELECTOR, sel):
            txt = (el_text(b) or "").lower()
            if "utsolgt" in txt or "sold out" in txt:
                return True

    # fallback: any text
    txt = (el_text(item) or "").lower()
    return ("utsolgt" in txt) or ("sold out" in txt)


def has_next_page(driver) -> bool:
    return bool(driver.find_elements(By.CSS_SELECTOR, "link[rel='next'][href], a[rel='next'][href]"))


# ---------- scrape ----------

def scrape():
    driver = create_chromium_driver(headless=True, use_old_headless=False, window_size="1280,720")
    db = SessionLocal()

    try:
        wait = WebDriverWait(driver, 25)

        page = 1
        seen_links: set[str] = set()

        while True:
            url = START_URL if page == 1 else f"{START_URL}?page={page}"
            driver.get(url)

            try:
                wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "ul#product-grid, li.grid__item, .card-wrapper")
                    )
                )
            except TimeoutException:
                print(f"[{SITE_KEY}] page {page}: no product grid found (end/blocked) -> stopping")
                break

            time.sleep(0.4)

            items = driver.find_elements(
                By.CSS_SELECTOR,
                "ul#product-grid > li.grid__item, li.grid__item, .card-wrapper.product-card-wrapper",
            )
            # only keep cards that actually link to a product
            items = [it for it in items if it.find_elements(By.CSS_SELECTOR, "a.full-unstyled-link")]

            if not items:
                print(f"[{SITE_KEY}] page {page}: 0 products -> stopping")
                break

            print(f"[{SITE_KEY}] page {page}: {len(items)} products")

            for idx, it in enumerate(items, start=1):
                try:
                    link_el = it.find_elements(By.CSS_SELECTOR, "a.full-unstyled-link")[0]
                    name = el_text(link_el).strip()

                    href = link_el.get_attribute("href") or ""
                    product_link = normalize_url(href, base=BASE)
                    if not product_link or product_link in seen_links:
                        continue
                    seen_links.add(product_link)

                    # Price (øre)
                    price_text = extract_price_text(it)
                    price_ore = parse_price_ore(price_text)

                    # Stock (no numeric count on grid)
                    sold_out = infer_sold_out(it)
                    stock_status = "Utsolgt" if sold_out else "På lager"
                    stock_amount = None

                    # Persist (centralized normalization + canonicalization + snapshots)
                    upsert_competitor_product(
                        db,
                        website=SITE_KEY,
                        product_link=product_link,
                        raw_name=name,
                        price_ore=price_ore,
                        stock_status=stock_status,
                        stock_amount=stock_amount,
                    )

                    print(f"[{idx:02d}] {name or '(NO NAME)'} | {format_ore(price_ore)} | {stock_status}")

                except Exception as e:
                    print(f"[!] skip {idx} p{page}: {e}")

            db.commit()

            if has_next_page(driver):
                page += 1
                continue

            break

        print(f"[{SITE_KEY}] total unique products: {len(seen_links)}")

    finally:
        driver.quit()
        db.close()


if __name__ == "__main__":
    scrape()
