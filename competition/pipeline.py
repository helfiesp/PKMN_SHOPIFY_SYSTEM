from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import (
    CompetitorProduct,
    CompetitorProductDaily,
    CompetitorProductSnapshot,
    CompetitorProductOverride,
    CompetitorPriceHistory,
    today_oslo,
)

from competition.normalize import (
    normalize_name,
    detect_category,
    detect_brand,
    detect_language,
)
from competition.canonicalize import canonicalize_normalized_name


def _apply_overrides(
    db: Session,
    *,
    website: str,
    normalized_name: str | None,
    category: str | None,
    brand: str | None,
    language: str | None,
) -> tuple[str | None, str | None, str | None]:
    """
    Apply manual overrides (global first, then website-specific).

    Returns possibly updated: (category, brand, language)
    """
    if not normalized_name:
        return (category, brand, language)

    # global override
    q = (
        db.query(CompetitorProductOverride)
        .filter(CompetitorProductOverride.website.is_(None))
        .filter(CompetitorProductOverride.normalized_name == normalized_name)
    )
    if category is None:
        q = q.filter(CompetitorProductOverride.category.is_(None))
    else:
        q = q.filter(CompetitorProductOverride.category == category)

    o_global = q.order_by(CompetitorProductOverride.updated_at.desc()).first()

    # site override
    q2 = (
        db.query(CompetitorProductOverride)
        .filter(CompetitorProductOverride.website == website)
        .filter(CompetitorProductOverride.normalized_name == normalized_name)
    )
    if category is None:
        q2 = q2.filter(CompetitorProductOverride.category.is_(None))
    else:
        q2 = q2.filter(CompetitorProductOverride.category == category)

    o_site = q2.order_by(CompetitorProductOverride.updated_at.desc()).first()

    def apply(o: CompetitorProductOverride | None):
        nonlocal category, brand, language
        if not o:
            return
        if o.category is not None:
            category = o.category
        if o.brand is not None:
            brand = o.brand
        if o.language is not None:
            language = o.language

    apply(o_global)
    apply(o_site)
    return (category, brand, language)


def _upsert_daily_snapshot(
    db: Session,
    product: CompetitorProduct,
    *,
    price: str | None,
    stock_status: str | None,
    stock_amount: int | None,
):
    day = today_oslo()
    snap = (
        db.query(CompetitorProductDaily)
        .filter_by(competitor_product_id=product.id, day=day)
        .first()
    )
    if snap:
        snap.price = price
        snap.stock_status = stock_status
        snap.stock_amount = stock_amount
    else:
        db.add(
            CompetitorProductDaily(
                competitor_product_id=product.id,
                day=day,
                price=price,
                stock_status=stock_status,
                stock_amount=stock_amount,
            )
        )


def _insert_snapshot(
    db: Session,
    product: CompetitorProduct,
    *,
    price: str | None,
    stock_status: str | None,
    stock_amount: int | None,
):
    db.add(
        CompetitorProductSnapshot(
            competitor_product_id=product.id,
            price=price,
            stock_status=stock_status,
            stock_amount=stock_amount,
        )
    )
    
    # Also save to price history
    db.add(
        CompetitorPriceHistory(
            competitor_product_id=product.id,
            price_ore=product.price_ore,
            stock_status=stock_status,
            stock_amount=stock_amount,
        )
    )


def upsert_competitor_product(
    db: Session,
    *,
    website: str,
    product_link: str,
    raw_name: str,
    price_ore: int,
    stock_status: str,
    stock_amount: int | None,
) -> CompetitorProduct:
    """
    Central pipeline used by all competitor scrapers.

    Responsibilities:
      - detect brand/category/language from RAW name
      - normalize + canonicalize normalized_name
      - apply manual overrides
      - upsert CompetitorProduct (latest)
      - upsert daily snapshot (one per Oslo day)
      - insert per-run snapshot

    NOTE: Commit is handled by caller.
    """
    raw_name = (raw_name or "").strip() or "(unknown)"
    website = (website or "").strip()
    product_link = (product_link or "").strip()

    # 1) detect from RAW name (important ordering)
    brand = detect_brand(raw_name) or None
    category = detect_category(raw_name) or None
    language = detect_language(raw_name) or "en"

    # 2) normalize -> canonicalize
    normalized = normalize_name(raw_name) or None
    if normalized:
        normalized = canonicalize_normalized_name(db, normalized, category=category)

    # 3) manual overrides (persisted)
    category, brand, language = _apply_overrides(
        db,
        website=website,
        normalized_name=normalized,
        category=category,
        brand=brand,
        language=language,
    )

    # 4) persist latest row
    price = str(int(price_ore or 0))
    existing = (
        db.query(CompetitorProduct)
        .filter_by(website=website, product_link=product_link)
        .first()
    )

    if existing:
        changed = False
        fields = {
            "raw_name": raw_name,
            "normalized_name": normalized,
            "category": category,
            "brand": brand,
            "language": language,
            "price_ore": price_ore,
            "stock_status": stock_status,
            "stock_amount": stock_amount,
        }
        for field, value in fields.items():
            if getattr(existing, field, None) != value:
                setattr(existing, field, value)
                changed = True
        if changed:
            existing.last_scraped_at = datetime.utcnow()
        product_row = existing
    else:
        product_row = CompetitorProduct(
            website=website,
            product_link=product_link,
            raw_name=raw_name,
            normalized_name=normalized,
            category=category,
            brand=brand,
            language=language,
            price_ore=price_ore,
            stock_status=stock_status,
            stock_amount=stock_amount,
            last_scraped_at=datetime.utcnow(),
        )
        db.add(product_row)
        db.flush()  # get id for snapshots

    # 5) historical data
    _upsert_daily_snapshot(
        db,
        product_row,
        price=price,
        stock_status=stock_status,
        stock_amount=stock_amount,
    )
    _insert_snapshot(
        db,
        product_row,
        price=price,
        stock_status=stock_status,
        stock_amount=stock_amount,
    )

    return product_row
