# competition/lcg_cards.py

import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from sqlalchemy.orm import Session

from database import SessionLocal
from app.models import CompetitorProduct
from driver_setup import create_chromium_driver

from competition.pipeline import upsert_competitor_product
from competition.pricing import parse_price_ore, format_ore
from competition.scrape_utils import el_text, normalize_url


BASE = "https://www.lcgcards.no"
URL = "https://www.lcgcards.no/butikk/pokemon/alt-pokemon"
SITE_KEY = "lcg_cards"


def extract_name(card) -> str:
    # 1) headline
    els = card.find_elements(By.CSS_SELECTOR, "h3.productlist__product__headline")
    if els:
        t = el_text(els[0]).strip()
        if t:
            return t

    # 2) itemprop name
    els = card.find_elements(By.CSS_SELECTOR, '[itemprop="name"]')
    if els:
        t = el_text(els[0]).strip()
        if t:
            return t

    # 3) anchor title/aria-label fallback
    a_els = card.find_elements(By.CSS_SELECTOR, "a.productlist__product-wrap")
    if a_els:
        a = a_els[0]
        return (a.get_attribute("title") or a.get_attribute("aria-label") or "").strip()

    return ""


def extract_product_link(card) -> str:
    a = card.find_element(By.CSS_SELECTOR, "a.productlist__product-wrap")
    href = (a.get_attribute("href") or a.get_attribute("data-href") or "").strip()
    if href:
        return normalize_url(href, base=BASE)

    meta_url = card.find_elements(By.CSS_SELECTOR, 'meta[itemprop="url"][content]')
    if meta_url:
        return normalize_url(meta_url[0].get_attribute("content") or "", base=BASE)

    return ""


def extract_price_ore(card) -> int:
    # Prefer schema meta price content
    price_meta = card.find_elements(By.CSS_SELECTOR, '[itemprop="price"][content]')
    if price_meta:
        price_val = (price_meta[0].get_attribute("content") or "").strip()
        return parse_price_ore(price_val)

    # Fallback visible price
    price_els = card.find_elements(By.CSS_SELECTOR, ".price__display, .price")
    price_val = el_text(price_els[0]).strip() if price_els else ""
    return parse_price_ore(price_val)


def extract_stock(card) -> tuple[str, int]:
    stock_amount = 0
    metas = card.find_elements(By.CSS_SELECTOR, "meta[id^='stock-status-']")
    if metas:
        stock_meta = metas[0]
        ds = (stock_meta.get_attribute("data-stock") or "").strip()
        content = (stock_meta.get_attribute("content") or "").strip()
        digits = "".join(ch for ch in (ds or content) if ch.isdigit())
        stock_amount = int(digits) if digits else 0

    stock_status = "På lager" if stock_amount > 0 else "Utsolgt"
    return stock_status, stock_amount


def scrape_lcg_cards():
    driver = create_chromium_driver(headless=True, use_old_headless=False, window_size="1280,720")
    db: Session = SessionLocal()

    new_products: list[CompetitorProduct] = []
    restocked_products: list[CompetitorProduct] = []

    try:
        driver.get(URL)
        wait = WebDriverWait(driver, 25)
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "article.productlist__product")))

        cards = driver.find_elements(By.CSS_SELECTOR, "article.productlist__product")
        print(f"[{SITE_KEY}] found {len(cards)} products")

        for idx, card in enumerate(cards, start=1):
            try:
                name = extract_name(card)
                product_link = extract_product_link(card)
                if not product_link:
                    raise RuntimeError("Missing product_link")

                price_ore = extract_price_ore(card)
                stock_status, stock_amount = extract_stock(card)

                # --- alert detection (based on DB state BEFORE upsert) ---
                existing: CompetitorProduct | None = (
                    db.query(CompetitorProduct)
                    .filter_by(website=SITE_KEY, product_link=product_link)
                    .first()
                )

                if existing:
                    prev_status = (existing.stock_status or "").strip()
                    if prev_status == "Utsolgt" and stock_amount > 0:
                        # same SQLAlchemy object will be updated by pipeline, so this stays valid
                        restocked_products.append(existing)

                # --- persist (centralized normalization + canonicalization + daily/snapshot) ---
                upsert_competitor_product(
                    db,
                    website=SITE_KEY,
                    product_link=product_link,
                    raw_name=name,
                    price_ore=price_ore,
                    stock_status=stock_status,
                    stock_amount=stock_amount,
                )

                # If it didn't exist, it was just created
                if existing is None:
                    created = (
                        db.query(CompetitorProduct)
                        .filter_by(website=SITE_KEY, product_link=product_link)
                        .first()
                    )
                    if created:
                        new_products.append(created)

                print(
                    f"[{idx:02d}] {name or '(NO NAME)'} | {format_ore(price_ore)} | {stock_status} [{stock_amount}]"
                )

            except Exception as e:
                print(f"[!] Skipped product {idx} due to error: {e}")

        db.commit()

    finally:
        driver.quit()
        db.close()


if __name__ == "__main__":
    scrape_lcg_cards()
