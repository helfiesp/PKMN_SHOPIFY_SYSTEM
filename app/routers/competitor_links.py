"""Local competitor link router.

Stores manual links between Shopify products and MarketIntel competitor products.
These links are independent of MarketIntel's own automatic matching — they give
the user full control over which competitor products are tracked per product.
"""
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import LocalCompetitorLink
from app.services import marketintel_service

router = APIRouter()


def _link_dict(link: LocalCompetitorLink) -> dict:
    return {
        "id":            link.id,
        "shopify_product_id": link.shopify_product_id,
        "mi_product_id": link.mi_product_id,
        "mi_domain":     link.mi_domain,
        "mi_title":      link.mi_title,
        "mi_source_url": link.mi_source_url,
        "mi_price":      link.mi_price,
        "mi_in_stock":   link.mi_in_stock,
        "mi_updated_at": link.mi_updated_at.isoformat() if link.mi_updated_at else None,
        "created_at":    link.created_at.isoformat() if link.created_at else None,
    }


# ── GET all links (for full page load) ───────────────────────────────────────
@router.get("")
def list_all_links(db: Session = Depends(get_db)):
    """Return every competitor link in the DB."""
    links = db.query(LocalCompetitorLink).order_by(
        LocalCompetitorLink.shopify_product_id,
        LocalCompetitorLink.mi_domain,
    ).all()
    return [_link_dict(l) for l in links]


# ── GET links for one product ─────────────────────────────────────────────────
@router.get("/by-product/{shopify_product_id}")
def list_links_for_product(shopify_product_id: str, db: Session = Depends(get_db)):
    """Return competitor links for a single Shopify product."""
    links = db.query(LocalCompetitorLink).filter(
        LocalCompetitorLink.shopify_product_id == shopify_product_id
    ).all()
    return [_link_dict(l) for l in links]


# ── POST create link ──────────────────────────────────────────────────────────
@router.post("")
def create_link(body: dict, db: Session = Depends(get_db)):
    """
    Create a new competitor link.

    Body fields:
      shopify_product_id  str   (required)
      mi_product_id       int   (required)
      mi_domain           str
      mi_title            str
      mi_source_url       str
      mi_price            float
      mi_in_stock         bool
    """
    shopify_id = body.get("shopify_product_id")
    mi_id      = body.get("mi_product_id")
    if not shopify_id or mi_id is None:
        raise HTTPException(status_code=400, detail="shopify_product_id and mi_product_id are required")

    existing = db.query(LocalCompetitorLink).filter(
        LocalCompetitorLink.shopify_product_id == shopify_id,
        LocalCompetitorLink.mi_product_id      == mi_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Link already exists")

    link = LocalCompetitorLink(
        shopify_product_id = shopify_id,
        mi_product_id      = mi_id,
        mi_domain          = body.get("mi_domain"),
        mi_title           = body.get("mi_title"),
        mi_source_url      = body.get("mi_source_url"),
        mi_price           = body.get("mi_price"),
        mi_in_stock        = body.get("mi_in_stock"),
        mi_updated_at      = datetime.now(timezone.utc) if body.get("mi_price") is not None else None,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _link_dict(link)


# ── DELETE link ───────────────────────────────────────────────────────────────
@router.delete("/{link_id}")
def delete_link(link_id: int, db: Session = Depends(get_db)):
    """Remove a competitor link."""
    link = db.query(LocalCompetitorLink).filter(LocalCompetitorLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    db.delete(link)
    db.commit()
    return {"ok": True, "deleted_id": link_id}


# ── POST refresh cached prices ────────────────────────────────────────────────
@router.post("/refresh-prices")
def refresh_prices(db: Session = Depends(get_db)):
    """
    Fetch current prices from MarketIntel for all linked competitor products
    and update the cached mi_price / mi_in_stock fields.

    Returns a summary of how many links were updated.
    """
    links = db.query(LocalCompetitorLink).all()
    if not links:
        return {"updated": 0, "errors": 0}

    updated = 0
    errors = 0
    now = datetime.now(timezone.utc)

    for link in links:
        try:
            p = marketintel_service.get_competitor_product_by_id(link.mi_product_id)
            link.mi_price      = p.get("price")
            link.mi_in_stock   = p.get("in_stock")
            if p.get("source_url"):
                link.mi_source_url = p["source_url"]
            link.mi_updated_at = now
            updated += 1
        except Exception:
            errors += 1

    db.commit()
    return {"updated": updated, "errors": errors, "total_links": len(links)}
