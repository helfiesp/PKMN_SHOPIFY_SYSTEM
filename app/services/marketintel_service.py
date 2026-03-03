"""MarketIntel competitor intelligence API client."""
import requests
from typing import Optional
from app.config import settings


def _headers() -> dict:
    return {"Authorization": f"Bearer {settings.marketintel_api_key}"}


def _base() -> str:
    return settings.marketintel_base_url.rstrip("/")


def get_competitors() -> list:
    """Return all tracked competitor domains."""
    r = requests.get(f"{_base()}/competitors", headers=_headers(), timeout=10)
    r.raise_for_status()
    return r.json()


def get_competitor_products(
    domain: Optional[str] = None,
    competitor_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
) -> list:
    """Return products from competitor catalog with optional domain/id/search filter."""
    params: dict = {"limit": limit, "offset": offset}
    if domain:
        params["domain"] = domain
    if competitor_id is not None:
        params["competitor_id"] = competitor_id
    if search:
        params["search"] = search
    r = requests.get(f"{_base()}/competitor-products", headers=_headers(), params=params, timeout=15)
    r.raise_for_status()
    return r.json()


def get_competitor_product_by_id(competitor_product_id: int) -> dict:
    """Return a single competitor product by ID."""
    r = requests.get(
        f"{_base()}/competitor-products/{competitor_product_id}",
        headers=_headers(),
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_price_history(competitor_product_id: int, limit: int = 100) -> list:
    """Return price/stock snapshots for a single competitor product, newest first."""
    r = requests.get(
        f"{_base()}/price-history/{competitor_product_id}",
        headers=_headers(),
        params={"limit": limit},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_alerts(limit: int = 50, offset: int = 0) -> list:
    """Return recent alerts (price changes, stock changes, new products), newest first."""
    r = requests.get(
        f"{_base()}/alerts",
        headers=_headers(),
        params={"limit": limit, "offset": offset},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def get_matched_products(limit: int = 200, offset: int = 0) -> list:
    """Return own products matched to competitor products for price comparison."""
    r = requests.get(
        f"{_base()}/matched-products",
        headers=_headers(),
        params={"limit": limit, "offset": offset},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()
