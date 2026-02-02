# competition/cardcenter.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import time
from urllib.parse import urlparse, urlencode, parse_qs

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from driver_setup import create_chromium_driver
from database import SessionLocal

from competition.pipeline import upsert_competitor_product
from competition.pricing import parse_price_ore, format_ore
from competition.scrape_utils import el_text, normalize_url


BASE = "https://cardcenter.no"
SITE_KEY = "cardcenter"

URLS = [
    "https://cardcenter.no/collections/pokemon",
    "https://cardcenter.no/collections/japanske-pokemonkort",
    "https://cardcenter.no/collections/kinesisk-pokemon",
    "https://cardcenter.no/collections/koreansk-pokemon",
]


# ---------- helpers ----------

def extract_name(item) -> str:
    els = item.find_elements(By.CSS_SELECTOR, "a.product-item__title")
    if els:
        return el_text(els[0]).strip()
    els = item.find_elements(By.CSS_SELECTOR, "img.product-item__primary-image")
    if els:
        return (els[0].get_attribute("alt") or "").strip()
    return ""


def extract_link(item) -> str:
    els = item.find_elements(By.CSS_SELECTOR, "a.product-item__title[href]")
    if els:
        return els[0].get_attribute("href") or ""
    els = item.find_elements(By.CSS_SELECTOR, "a.product-item__image-wrapper[href]")
    if els:
        return els[0].get_attribute("href") or ""
    return ""


def extract_price_text(item) -> str:
    sel_order = [
        ".product-item__price-list .price.price--highlight",  # sale price
        ".product-item__price-list .price",
    ]
    for sel in sel_order:
        els = item.find_elements(By.CSS_SELECTOR, sel)
        if els:
            t = el_text(els[0]).strip()
            if t:
                return t
    return ""


def infer_stock(item) -> tuple[str, int | None]:
    """
    Cardcenter grid typically only shows "På lager"/"Utsolgt" - no counts.
    We store stock_amount=None.
    """
    els = item.find_elements(By.CSS_SELECTOR, ".product-item__inventory")
    txt = (el_text(els[0]) if els else el_text(item)).lower()

    if "utsolgt" in txt or "ikke på lager" in txt or "sold out" in txt:
        return ("Utsolgt", None)

    if "på lager" in txt or "pa lager" in txt or "in stock" in txt:
        return ("På lager", None)

    return ("På lager", None)


def set_page(url: str, page: int) -> str:
    u = urlparse(url)
    q = parse_qs(u.query)
    q["page"] = [str(page)]
    return u._replace(query=urlencode(q, doseq=True)).geturl()


def has_next_page(driver) -> bool:
    if driver.find_elements(By.CSS_SELECTOR, "link[rel='next'][href]"):
        return True
    if driver.find_elements(By.CSS_SELECTOR, "a[rel='next'][href]"):
        return True
    if driver.find_elements(By.CSS_SELECTOR, "a[aria-label*='Neste'], a[aria-label*='Next']"):
        return True
    return False


# ---------- scrape ----------

def scrape_collection(driver, db, base_collection_url: str, *, seen_links: set[str]) -> int:
    wait = WebDriverWait(driver, 25)

    page = 1
    processed = 0

    while True:
        url = set_page(base_collection_url, page)
        driver.get(url)

        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.product-item.product-item--vertical")))
        time.sleep(0.4)

        items = driver.find_elements(By.CSS_SELECTOR, "div.product-item.product-item--vertical")
        if not items:
            break

        print(f"[{SITE_KEY}] {base_collection_url} page {page}: {len(items)} products")

        for idx, item in enumerate(items, start=1):
            try:
                name = extract_name(item)

                href = extract_link(item)
                product_link = normalize_url(href, base=BASE)
                if not product_link:
                    raise RuntimeError("Missing product link")

                # de-dupe across all collections
                if product_link in seen_links:
                    continue
                seen_links.add(product_link)

                price_text = extract_price_text(item)
                price_ore = parse_price_ore(price_text)

                stock_status, stock_amount = infer_stock(item)  # stock_amount = None

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

                processed += 1
                pretty = format_ore(price_ore)
                print(f"[{idx:02d}] {name or '(NO NAME)'} | {pretty} | {stock_status}")

            except Exception as e:
                print(f"[!] skip {idx} p{page}: {e}")

        db.commit()

        if not has_next_page(driver):
            break

        page += 1
        time.sleep(0.4)

    return processed


def scrape():
    driver = create_chromium_driver(headless=True, use_old_headless=False, window_size="1280,720")
    db = SessionLocal()

    try:
        total_rows_touched = 0
        seen_links: set[str] = set()

        for collection_url in URLS:
            total_rows_touched += scrape_collection(driver, db, collection_url, seen_links=seen_links)

        print(f"[{SITE_KEY}] total unique products: {len(seen_links)} (rows touched: {total_rows_touched})")

    finally:
        driver.quit()
        db.close()


if __name__ == "__main__":
    scrape()
