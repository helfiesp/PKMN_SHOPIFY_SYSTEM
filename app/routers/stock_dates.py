"""Stock dates router — manage custom.stock_date metafields on Shopify products."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
import requests

from app.config import settings
from app.database import get_db
from app.models import Product

router = APIRouter()

NAMESPACE = "custom"
KEY = "stock_date"


def _rest_headers() -> dict:
    return {
        "X-Shopify-Access-Token": settings.get_shopify_token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base() -> str:
    return f"https://{settings.get_shopify_shop()}/admin/api/{settings.shopify_api_version}"


def _require_credentials():
    if not settings.get_shopify_shop() or not settings.get_shopify_token():
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")


def _get_metafield_rest(product_id: str) -> Optional[dict]:
    """Fetch the stock_date metafield for a single product via REST (needed for the numeric ID)."""
    url = f"{_base()}/products/{product_id}/metafields.json?namespace={NAMESPACE}&key={KEY}&limit=1"
    resp = requests.get(url, headers=_rest_headers(), timeout=15)
    resp.raise_for_status()
    mfs = resp.json().get("metafields", [])
    return mfs[0] if mfs else None


def _delete_metafield(metafield_id: str) -> bool:
    resp = requests.delete(
        f"{_base()}/metafields/{metafield_id}.json",
        headers=_rest_headers(),
        timeout=15,
    )
    return resp.ok


def _enrich(product: Product) -> dict:
    val = product.stock_date or ""
    today = date.today()
    try:
        stock_dt = date.fromisoformat(val)
        days_until = (stock_dt - today).days
        is_expired = days_until <= 0
    except ValueError:
        days_until = None
        is_expired = False
    # Strip the GID prefix if present to get the numeric Shopify ID
    shopify_id = product.shopify_id.split("/")[-1] if product.shopify_id else ""
    return {
        "product_id": shopify_id,
        "title": product.title,
        "metafield_id": None,  # only needed for mutations, fetched lazily
        "stock_date": val,
        "days_until": days_until,
        "is_expired": is_expired,
    }


# ─── Models ──────────────────────────────────────────────────────────────────

class UpdateStockDateRequest(BaseModel):
    stock_date: str  # ISO date YYYY-MM-DD


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
async def list_stock_dates(db: Session = Depends(get_db)):
    """Return all products that have stock_date set — reads from local DB (populated during sync)."""
    products = (
        db.query(Product)
        .filter(Product.stock_date.isnot(None), Product.stock_date != "")
        .order_by(Product.stock_date)
        .all()
    )
    return [_enrich(p) for p in products]


@router.patch("/{product_id}")
async def update_stock_date(
    product_id: str,
    body: UpdateStockDateRequest,
    db: Session = Depends(get_db),
):
    """Set or update the custom.stock_date metafield on Shopify and in the local DB."""
    _require_credentials()
    try:
        date.fromisoformat(body.stock_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    # Write to Shopify
    existing = _get_metafield_rest(product_id)
    if existing:
        url = f"{_base()}/metafields/{existing['id']}.json"
        payload = {"metafield": {"id": existing["id"], "value": body.stock_date, "type": "date"}}
        resp = requests.put(url, json=payload, headers=_rest_headers(), timeout=15)
    else:
        url = f"{_base()}/products/{product_id}/metafields.json"
        payload = {"metafield": {"namespace": NAMESPACE, "key": KEY, "value": body.stock_date, "type": "date"}}
        resp = requests.post(url, json=payload, headers=_rest_headers(), timeout=15)

    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    # Mirror to local DB
    product = db.query(Product).filter(
        Product.shopify_id.like(f"%/{product_id}")
    ).first() or db.query(Product).filter(Product.shopify_id == product_id).first()
    if product:
        product.stock_date = body.stock_date
        db.commit()

    today = date.today()
    try:
        days_until = (date.fromisoformat(body.stock_date) - today).days
    except ValueError:
        days_until = None
    return {
        "product_id": product_id,
        "stock_date": body.stock_date,
        "days_until": days_until,
        "is_expired": days_until is not None and days_until <= 0,
    }


@router.delete("/{product_id}")
async def clear_stock_date(product_id: str, db: Session = Depends(get_db)):
    """Delete the custom.stock_date metafield from Shopify and clear it in the local DB."""
    _require_credentials()
    existing = _get_metafield_rest(product_id)
    if not existing:
        # Still clear local DB in case it's out of sync
        _clear_local(db, product_id)
        return {"product_id": product_id, "message": "No stock_date metafield found on Shopify"}
    if not _delete_metafield(str(existing["id"])):
        raise HTTPException(status_code=500, detail="Failed to delete metafield from Shopify")
    _clear_local(db, product_id)
    return {"product_id": product_id, "message": "stock_date cleared"}


def _clear_local(db: Session, product_id: str):
    product = db.query(Product).filter(
        Product.shopify_id.like(f"%/{product_id}")
    ).first() or db.query(Product).filter(Product.shopify_id == product_id).first()
    if product:
        product.stock_date = None
        db.commit()


@router.post("/clear-expired")
async def clear_expired_stock_dates(db: Session = Depends(get_db)):
    """Clear stock_date for all products where the date has passed (≤ today)."""
    _require_credentials()
    today = date.today()
    expired = (
        db.query(Product)
        .filter(Product.stock_date.isnot(None), Product.stock_date != "")
        .all()
    )
    cleared, errors = [], []

    for product in expired:
        try:
            stock_dt = date.fromisoformat(product.stock_date)
        except ValueError:
            continue
        if stock_dt > today:
            continue

        # Fetch metafield ID from Shopify to delete it
        numeric_id = product.shopify_id.split("/")[-1]
        mf = _get_metafield_rest(numeric_id)
        if mf and _delete_metafield(str(mf["id"])):
            product.stock_date = None
            cleared.append({"product_id": numeric_id, "title": product.title, "stock_date": stock_dt.isoformat()})
        else:
            errors.append({"product_id": numeric_id, "title": product.title, "error": "Delete failed"})

    db.commit()
    return {
        "cleared_count": len(cleared),
        "cleared": cleared,
        "errors": errors,
        "ran_at": datetime.utcnow().isoformat(),
    }
