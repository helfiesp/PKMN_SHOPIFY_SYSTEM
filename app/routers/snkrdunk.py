"""SNKRDUNK operations router."""
from typing import List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import SnkrdunkFetchRequest, SnkrdunkMatchingResponse
from app.services import snkrdunk_service
from app.models import SnkrdunkScanLog, SnkrdunkPriceHistory

router = APIRouter()


@router.post("/fetch", response_model=dict)
async def fetch_snkrdunk_data(
    request: SnkrdunkFetchRequest,
    db: Session = Depends(get_db)
):
    """
    Fetch product data from SNKRDUNK API.
    
    This replaces the SNKRDUNK fetching part of snkrdunk.py.
    Caches results in database for efficiency.
    Creates a SnkrdunkScanLog entry to track when prices were fetched.
    """
    started_at = datetime.now(ZoneInfo("Europe/Oslo"))
    log_id = None
    
    try:
        result = await snkrdunk_service.fetch_and_cache_snkrdunk_data(
            db=db,
            pages=request.pages,
            force_refresh=request.force_refresh
        )
        
        print(f"[SNKRDUNK FETCH] Service returned: total_items={result.get('total_items')}")
        
        completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
        duration = (completed_at - started_at).total_seconds()
        total_items = result.get('total_items', 0)
        
        # Create a SnkrdunkScanLog entry to track this fetch
        scan_log = SnkrdunkScanLog(
            status='success',
            total_items=total_items,
            output=f"Fetched {total_items} items from {len(request.pages)} pages",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(scan_log)
        db.flush()  # Flush to get the ID without committing
        log_id = scan_log.id
        
        # Save current prices directly from the API response to SnkrdunkPriceHistory
        # This captures what the prices WERE at this exact moment
        from app.models import SnkrdunkPriceHistory
        fresh_items = result.get('items', [])
        
        print(f"[SNKRDUNK FETCH] Saving {len(fresh_items)} fresh prices for scan #{log_id}")
        for item in fresh_items:
            price_record = SnkrdunkPriceHistory(
                scan_log_id=log_id,
                snkrdunk_key=str(item.get('id')),
                price_jpy=item.get('minPrice'),  # Use minPrice instead of minPriceJpy
                price_usd=None,  # Not available in fresh response
                recorded_at=datetime.now(ZoneInfo("Europe/Oslo"))
            )
            db.add(price_record)
        
        db.commit()
        
        # Include the log_id in response
        result['log_id'] = log_id
        print(f"[SNKRDUNK] Successfully created SnkrdunkScanLog #{log_id} with {len(fresh_items)} prices")
        return result
    except Exception as e:
        print(f"[SNKRDUNK] Error during fetch: {str(e)}")
        import traceback
        traceback.print_exc()
        
        completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
        duration = (completed_at - started_at).total_seconds()
        
        try:
            # Create failed SnkrdunkScanLog entry
            scan_log = SnkrdunkScanLog(
                status='failed',
                output=None,
                error_message=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration
            )
            db.add(scan_log)
            db.flush()
            log_id = scan_log.id
            db.commit()
            print(f"[SNKRDUNK] Created failed SnkrdunkScanLog #{log_id}")
        except Exception as log_error:
            print(f"[SNKRDUNK] Failed to create error log: {log_error}")
        
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/match-shopify", response_model=SnkrdunkMatchingResponse)
async def match_with_shopify(
    collection_id: str,
    db: Session = Depends(get_db)
):
    """
    Match SNKRDUNK products with Shopify products and generate price recommendations.
    
    This replaces the matching logic in snkrdunk.py.
    Uses cached SNKRDUNK data and local Shopify products.
    """
    try:
        result = await snkrdunk_service.match_and_calculate_prices(
            db=db,
            collection_id=collection_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-history")
async def get_price_history(
    log_id: int,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    """
    Get historical SNKRDUNK prices for a specific scan log.
    
    Returns all prices that were recorded during that scan.
    """
    try:
        # Query for prices from this specific scan log
        history = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.scan_log_id == log_id
        ).order_by(SnkrdunkPriceHistory.snkrdunk_key).limit(limit).all()
        
        # Get scan log for reference
        scan_log = db.query(SnkrdunkScanLog).filter(
            SnkrdunkScanLog.id == log_id
        ).first()
        
        return {
            "log_id": log_id,
            "scan_date": scan_log.created_at.isoformat() if scan_log else None,
            "item_count": len(history),
            "items": [
                {
                    "id": h.snkrdunk_key,
                    "minPriceJpy": h.price_jpy,  # Frontend expects minPriceJpy
                    "minPrice": h.price_jpy,     # Also provide minPrice for consistency
                    "price_usd": h.price_usd,
                    "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None
                }
                for h in history
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-logs")
async def get_snkrdunk_scan_logs(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get SNKRDUNK price update scan logs."""
    try:
        logs = db.query(SnkrdunkScanLog).order_by(SnkrdunkScanLog.created_at.desc()).limit(limit).all()
        
        return [
            {
                "id": log.id,
                "status": log.status,
                "total_items": log.total_items,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "duration_seconds": log.duration_seconds,
                "output": log.output,
                "error_message": log.error_message,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-logs/{log_id}")
async def get_snkrdunk_scan_log(
    log_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific SNKRDUNK scan log."""
    try:
        log = db.query(SnkrdunkScanLog).filter(SnkrdunkScanLog.id == log_id).first()
        if not log:
            raise HTTPException(status_code=404, detail="Scan log not found")
        
        return {
            "id": log.id,
            "status": log.status,
            "total_items": log.total_items,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "duration_seconds": log.duration_seconds,
            "output": log.output,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products")
async def get_cached_products(
    include_expired: bool = False,
    translate: bool = True,
    scan_log_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all cached SNKRDUNK products with optional translation."""
    products = snkrdunk_service.get_cached_products(
        db=db,
        include_expired=include_expired,
        translate=translate,
        scan_log_id=scan_log_id
    )
    return {
        "total_items": len(products),
        "items": products
    }


@router.delete("/cache")
async def clear_cache(db: Session = Depends(get_db)):
    """Clear SNKRDUNK cache."""
    snkrdunk_service.clear_cache(db=db)
    return {"message": "Cache cleared successfully"}
