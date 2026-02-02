# competition/hatamontcg.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from driver_setup import create_chromium_driver
from database import SessionLocal

from competition.pipeline import upsert_competitor_product
from competition.pricing import parse_price_ore, format_ore
from competition.scrape_utils import el_text, normalize_url


BASE = "https://hatamontcg.com"
START_URL = "https://hatamontcg.com/collections/alle-produkter"
SITE_KEY = "hatamontcg"


# ---------- site helpers ----------

def infer_stock_status(card) -> str:
    """
    Infer stock from visible labels/badges.
    - "Utsolgt" => sold out
    - "Få igjen" => in stock (low)
    If no info found, assume in stock.
    """
    txt = (el_text(card) or "").lower()
    if "utsolgt" in txt or "sold out" in txt:
        return "Utsolgt"
    if "få igjen" in txt or "fa igjen" in txt or "low stock" in txt:
        return "På lager"
    return "På lager"


def extract_name(card) -> str:
    # 1) zoom-out details header
    els = card.find_elements(By.CSS_SELECTOR, ".product-grid-view-zoom-out--details h3.h4")
    if els:
        return el_text(els[0]).strip()

    # 2) product title link text
    els = card.find_elements(By.CSS_SELECTOR, "a[ref='productTitleLink'] p")
    if els:
        return el_text(els[0]).strip()

    # 3) hidden name
    els = card.find_elements(By.CSS_SELECTOR, "a.product-card__link span.visually-hidden")
    if els:
        return el_text(els[0]).strip()

    return ""


def extract_price(card) -> str:
    selectors = [
        ".product-grid-view-zoom-out--details span.price",
        "product-price span.price",
        "span.price",
    ]
    for sel in selectors:
        els = card.find_elements(By.CSS_SELECTOR, sel)
        if els:
            val = el_text(els[0]).strip()
            if val:
                return val
    return ""


def extract_link(card) -> str:
    els = card.find_elements(By.CSS_SELECTOR, "a.product-card__link[href]")
    if els:
        return els[0].get_attribute("href") or ""

    els = card.find_elements(By.CSS_SELECTOR, "a[ref='productTitleLink'][href]")
    if els:
        return els[0].get_attribute("href") or ""

    els = card.find_elements(By.CSS_SELECTOR, "a[href*='/products/']")
    if els:
        return els[0].get_attribute("href") or ""

    return ""


def find_next_page(driver) -> str | None:
    els = driver.find_elements(By.CSS_SELECTOR, "link[rel='next'][href]")
    if els:
        return els[0].get_attribute("href")

    els = driver.find_elements(By.CSS_SELECTOR, "a[rel='next'][href]")
    if els:
        return els[0].get_attribute("href")

    els = driver.find_elements(
        By.CSS_SELECTOR,
        "nav.pagination a[aria-label='Next'][href], .pagination__item--next a[href]"
    )
    if els:
        return els[0].get_attribute("href")

    return None


# ---------- scrape ----------

def scrape():
    driver = create_chromium_driver(headless=True, use_old_headless=False, window_size="1280,720")
    db = SessionLocal()

    try:
        wait = WebDriverWait(driver, 25)

        url = START_URL
        page = 1
        seen_links: set[str] = set()
        touched = 0

        while True:
            driver.get(url)

            wait.until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "product-card.product-card, li.product-grid__item")
                )
            )
            time.sleep(0.5)

            cards = driver.find_elements(By.CSS_SELECTOR, "li.product-grid__item product-card.product-card")
            if not cards:
                cards = driver.find_elements(By.CSS_SELECTOR, "product-card.product-card")

            if not cards:
                print(f"[{SITE_KEY}] no products found on page {page}")
                break

            print(f"[{SITE_KEY}] page {page}: {len(cards)} products")

            for idx, card in enumerate(cards, start=1):
                try:
                    name = extract_name(card)

                    href = extract_link(card)
                    product_link = normalize_url(href, base=BASE)
                    if not product_link:
                        raise RuntimeError("Missing product link")

                    if product_link in seen_links:
                        continue
                    seen_links.add(product_link)

                    price_text = extract_price(card)
                    price_ore = parse_price_ore(price_text)

                    stock_status = infer_stock_status(card)
                    stock_amount = None  # no numeric stock on grid

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

                    touched += 1
                    pretty = format_ore(price_ore)
                    print(f"[{idx:02d}] {name or '(NO NAME)'} | {pretty} | {stock_status}")

                except Exception as e:
                    print(f"[!] skip {idx} p{page}: {e}")

            db.commit()

            next_url = find_next_page(driver)
            if next_url:
                url = next_url
                page += 1
                continue

            break

        print(f"[{SITE_KEY}] total unique products: {len(seen_links)} (rows touched: {touched})")

    finally:
        driver.quit()
        db.close()


if __name__ == "__main__":
    scrape()
