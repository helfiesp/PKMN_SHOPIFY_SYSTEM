"""API routes for price history operations."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.services.history_service import HistoryService

router = APIRouter(prefix="/api/v1/history", tags=["history"])
history_service = HistoryService()


@router.get("/available-dates")
async def get_available_history_dates(db: Session = Depends(get_db)):
    """
    Get all available dates where historical data exists for any data source.
    
    Returns dates in YYYY-MM-DD format for:
    - Competitor product prices
    - SNKRDUNK product prices
    - My product prices
    """
    try:
        dates = history_service.get_available_history_dates(db)
        return {
            "success": True,
            "data": dates
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competitor-prices/{date}")
async def get_competitor_prices_at_date(
    date: str,
    db: Session = Depends(get_db)
):
    """
    Get all competitor product prices for a specific date (YYYY-MM-DD).
    
    Returns the most recent price recorded for each competitor product on that date.
    """
    try:
        prices = history_service.get_competitor_prices_at_date(db, date)
        return {
            "success": True,
            "date": date,
            "count": len(prices),
            "data": prices
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competitor-prices/{competitor_id}/{date}")
async def get_competitor_price_at_date(
    competitor_id: int,
    date: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific competitor product's price for a specific date (YYYY-MM-DD).
    """
    try:
        price = history_service.get_competitor_price_at_date(db, competitor_id, date)
        if not price:
            raise HTTPException(status_code=404, detail="No price data found for this date")
        
        return {
            "success": True,
            "data": price
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snkrdunk-prices/{date}")
async def get_snkrdunk_prices_at_date(
    date: str,
    db: Session = Depends(get_db)
):
    """
    Get all SNKRDUNK product prices for a specific date (YYYY-MM-DD).
    
    Returns the most recent price recorded for each SNKRDUNK product on that date.
    """
    try:
        prices = history_service.get_snkrdunk_prices_at_date(db, date)
        return {
            "success": True,
            "date": date,
            "count": len(prices),
            "data": prices
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snkrdunk-prices/{snkrdunk_key}/{date}")
async def get_snkrdunk_price_at_date(
    snkrdunk_key: str,
    date: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific SNKRDUNK product's price for a specific date (YYYY-MM-DD).
    """
    try:
        price = history_service.get_snkrdunk_price_at_date(db, snkrdunk_key, date)
        if not price:
            raise HTTPException(status_code=404, detail="No price data found for this date")
        
        return {
            "success": True,
            "data": price
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product-prices/{date}")
async def get_product_prices_at_date(
    date: str,
    db: Session = Depends(get_db)
):
    """
    Get all product variant prices for a specific date (YYYY-MM-DD).
    
    Returns the most recent price recorded for each variant on that date.
    """
    try:
        prices = history_service.get_product_prices_at_date(db, date)
        return {
            "success": True,
            "date": date,
            "count": len(prices),
            "data": prices
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product-prices/{variant_id}/{date}")
async def get_product_price_at_date(
    variant_id: int,
    date: str,
    db: Session = Depends(get_db)
):
    """
    Get a specific product variant's price for a specific date (YYYY-MM-DD).
    """
    try:
        price = history_service.get_product_price_at_date(db, variant_id, date)
        if not price:
            raise HTTPException(status_code=404, detail="No price data found for this date")
        
        return {
            "success": True,
            "data": price
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snkrdunk/{snkrdunk_key}/last-updated")
async def get_snkrdunk_last_updated(
    snkrdunk_key: str,
    db: Session = Depends(get_db)
):
    """
    Get the timestamp when a SNKRDUNK product's price was last updated.
    """
    try:
        last_updated = history_service.get_snkrdunk_last_updated(db, snkrdunk_key)
        if not last_updated:
            return {
                "success": True,
                "data": None
            }
        
        return {
            "success": True,
            "snkrdunk_key": snkrdunk_key,
            "last_updated": last_updated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competitor/{competitor_id}/last-updated")
async def get_competitor_last_updated(
    competitor_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the timestamp when a competitor product's price was last updated.
    """
    try:
        last_updated = history_service.get_competitor_last_updated(db, competitor_id)
        if not last_updated:
            return {
                "success": True,
                "data": None
            }
        
        return {
            "success": True,
            "competitor_id": competitor_id,
            "last_updated": last_updated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/product/{variant_id}/last-updated")
async def get_product_last_updated(
    variant_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the timestamp when a product variant's price was last updated.
    """
    try:
        last_updated = history_service.get_product_last_updated(db, variant_id)
        if not last_updated:
            return {
                "success": True,
                "data": None
            }
        
        return {
            "success": True,
            "variant_id": variant_id,
            "last_updated": last_updated
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/competitor/{competitor_id}/timeline")
async def get_competitor_price_timeline(
    competitor_id: int,
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get price history timeline for a competitor product over N days.
    """
    try:
        timeline = history_service.get_price_history_timeline(db, competitor_id, days_back)
        return {
            "success": True,
            "competitor_id": competitor_id,
            "days_back": days_back,
            "count": len(timeline),
            "data": timeline
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/snkrdunk/{snkrdunk_key}/timeline")
async def get_snkrdunk_price_timeline(
    snkrdunk_key: str,
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get price history timeline for a SNKRDUNK product over N days.
    Returns one price per day (the most recent price recorded each day).
    """
    try:
        timeline = history_service.get_snkrdunk_price_timeline(db, snkrdunk_key, days_back)
        return {
            "success": True,
            "snkrdunk_key": snkrdunk_key,
            "days_back": days_back,
            "count": len(timeline),
            "data": timeline
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
