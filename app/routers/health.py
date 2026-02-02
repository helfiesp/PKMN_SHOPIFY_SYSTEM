"""Health check and status endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.config import settings
from app.scheduler import scheduler

router = APIRouter()


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Check API and database health."""
    try:
        # Test database connection
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {str(e)}"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "database": db_status,
        "shopify_configured": bool(settings.shopify_shop and settings.shopify_token),
        "google_translate_configured": bool(settings.google_translate_api_key)
    }


@router.get("/config")
async def get_config():
    """Get current configuration (non-sensitive)."""
    return {
        "shopify_shop": settings.shopify_shop,
        "shopify_api_version": settings.shopify_api_version,
        "default_collection_id": settings.default_collection_id,
        "booster_collection_id": settings.booster_collection_id,
        "location_id": settings.location_id,
        "location_name": settings.location_name,
        "pricing_rules": {
            "shipping_cost_jpy": settings.shipping_cost_jpy,
            "min_margin": settings.min_margin,
            "vat_rate": settings.vat_rate,
            "round_up_step_nok": settings.round_up_step_nok
        },
        "booster_rules": {
            "default_packs_per_box": settings.default_packs_per_box,
            "pack_markup": settings.pack_markup
        }
    }


@router.get("/scheduler/status")
async def get_scheduler_status():
    """Get scheduler status and last run times."""
    return scheduler.get_status()


@router.post("/scrape/competitors")
async def trigger_competitor_scrape():
    """Trigger competitor scraping immediately."""
    return scheduler.trigger_competitor_scrape()

