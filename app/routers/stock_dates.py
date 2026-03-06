"""Stock dates router — manage custom.stock_date metafields on Shopify products."""
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import requests

from app.config import settings

router = APIRouter()

NAMESPACE = "custom"
KEY = "stock_date"


def _headers() -> dict:
    return {
        "X-Shopify-Access-Token": settings.get_shopify_token(),
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _base() -> str:
    return f"https://{settings.get_shopify_shop()}/admin/api/{settings.shopify_api_version}"


def _all_products() -> list:
    """Page through all Shopify products, returning [{id, title}, ...]."""
    url = f"{_base()}/products.json?limit=250&fields=id,title"
    products = []
    while url:
        resp = requests.get(url, headers=_headers(), timeout=30)
        resp.raise_for_status()
        products.extend(resp.json().get("products", []))
        url = None
        for part in resp.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part[part.find("<") + 1:part.find(">")]
                break
    return products


def _get_metafield(product_id: str) -> Optional[dict]:
    """Return the stock_date metafield dict for a product, or None."""
    url = f"{_base()}/products/{product_id}/metafields.json?namespace={NAMESPACE}&key={KEY}&limit=1"
    resp = requests.get(url, headers=_headers(), timeout=15)
    resp.raise_for_status()
    mfs = resp.json().get("metafields", [])
    return mfs[0] if mfs else None


def _delete_metafield(metafield_id: str) -> bool:
    resp = requests.delete(f"{_base()}/metafields/{metafield_id}.json", headers=_headers(), timeout=15)
    return resp.ok


def _enrich(product_id: str, title: str, mf: dict) -> dict:
    val = mf.get("value", "")
    today = date.today()
    try:
        stock_dt = date.fromisoformat(val)
        days_until = (stock_dt - today).days
        is_expired = days_until <= 0
    except ValueError:
        days_until = None
        is_expired = False
    return {
        "product_id": str(product_id),
        "title": title,
        "metafield_id": str(mf["id"]),
        "stock_date": val,
        "days_until": days_until,
        "is_expired": is_expired,
    }


def _require_credentials():
    if not settings.get_shopify_shop() or not settings.get_shopify_token():
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")


# ─── Models ──────────────────────────────────────────────────────────────────

class UpdateStockDateRequest(BaseModel):
    stock_date: str  # ISO date YYYY-MM-DD


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.get("")
async def list_stock_dates():
    """Return all products that have a custom.stock_date metafield."""
    _require_credentials()
    products = _all_products()
    results = []
    for p in products:
        pid = str(p["id"])
        mf = _get_metafield(pid)
        if mf:
            results.append(_enrich(pid, p["title"], mf))
    results.sort(key=lambda x: x["stock_date"] or "")
    return results


@router.patch("/{product_id}")
async def update_stock_date(product_id: str, body: UpdateStockDateRequest):
    """Set or update the custom.stock_date metafield for a product."""
    _require_credentials()
    try:
        date.fromisoformat(body.stock_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, expected YYYY-MM-DD")

    existing = _get_metafield(product_id)
    if existing:
        url = f"{_base()}/metafields/{existing['id']}.json"
        payload = {"metafield": {"id": existing["id"], "value": body.stock_date, "type": "date"}}
        resp = requests.put(url, json=payload, headers=_headers(), timeout=15)
    else:
        url = f"{_base()}/products/{product_id}/metafields.json"
        payload = {"metafield": {"namespace": NAMESPACE, "key": KEY, "value": body.stock_date, "type": "date"}}
        resp = requests.post(url, json=payload, headers=_headers(), timeout=15)

    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    mf = resp.json().get("metafield", {})
    return _enrich(product_id, "", mf)


@router.delete("/{product_id}")
async def clear_stock_date(product_id: str):
    """Delete the custom.stock_date metafield from a product."""
    _require_credentials()
    existing = _get_metafield(product_id)
    if not existing:
        return {"product_id": product_id, "message": "No stock_date metafield found"}
    if not _delete_metafield(str(existing["id"])):
        raise HTTPException(status_code=500, detail="Failed to delete metafield from Shopify")
    return {"product_id": product_id, "message": "stock_date cleared"}


@router.post("/clear-expired")
async def clear_expired_stock_dates():
    """Clear stock_date metafields for all products where the date has passed (≤ today)."""
    _require_credentials()
    today = date.today()
    products = _all_products()
    cleared, errors = [], []

    for p in products:
        pid = str(p["id"])
        mf = _get_metafield(pid)
        if not mf:
            continue
        try:
            stock_dt = date.fromisoformat(mf.get("value", ""))
        except ValueError:
            continue
        if stock_dt <= today:
            if _delete_metafield(str(mf["id"])):
                cleared.append({"product_id": pid, "title": p["title"], "stock_date": mf["value"]})
            else:
                errors.append({"product_id": pid, "title": p["title"], "error": "Delete failed"})

    return {
        "cleared_count": len(cleared),
        "cleared": cleared,
        "errors": errors,
        "ran_at": datetime.utcnow().isoformat(),
    }
