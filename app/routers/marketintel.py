"""MarketIntel competitor intelligence proxy router."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

from app.services import marketintel_service

router = APIRouter()


@router.get("/competitors")
def list_competitors():
    """All competitor domains being tracked."""
    try:
        return marketintel_service.get_competitors()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MarketIntel error: {e}")


@router.get("/competitor-products/{competitor_product_id}")
def get_competitor_product(competitor_product_id: int):
    """Fetch a single competitor product by ID."""
    try:
        return marketintel_service.get_competitor_product_by_id(competitor_product_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MarketIntel error: {e}")


@router.get("/competitor-products")
def list_competitor_products(
    domain: Optional[str] = None,
    competitor_id: Optional[int] = None,
    search: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Products from competitor catalogs, filterable by domain, competitor ID, or search term."""
    try:
        return marketintel_service.get_competitor_products(
            domain=domain,
            competitor_id=competitor_id,
            search=search,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MarketIntel error: {e}")


@router.get("/price-history/{competitor_product_id}")
def get_price_history(
    competitor_product_id: int,
    limit: int = Query(default=100, ge=1, le=500),
):
    """Price and stock snapshots for a single competitor product, newest first."""
    try:
        return marketintel_service.get_price_history(competitor_product_id, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MarketIntel error: {e}")


@router.get("/alerts")
def list_alerts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Recent alerts (price changes, stock changes, new products), newest first."""
    try:
        return marketintel_service.get_alerts(limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MarketIntel error: {e}")


@router.get("/matched-products")
def list_matched_products(
    limit: int = Query(default=200, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Own products matched to competitor products for price comparison."""
    try:
        return marketintel_service.get_matched_products(limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"MarketIntel error: {e}")
