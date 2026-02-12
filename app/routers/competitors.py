"""Competitor products router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import and_
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
from zoneinfo import ZoneInfo
import asyncio
import subprocess
import os

from app.database import get_db
from app.models import CompetitorProduct, CompetitorProductMapping, today_oslo
from app.services.competitor_service import competitor_service
from app.services.competitor_mapping_service import competitor_mapping_service

router = APIRouter()


class CompetitorProductResponse(BaseModel):
    id: int
    website: str
    product_link: str
    raw_name: Optional[str]
    normalized_name: Optional[str]
    category: Optional[str]
    brand: Optional[str]
    price_ore: Optional[int]
    stock_status: Optional[str]
    stock_amount: int
    language: Optional[str]
    created_at: Optional[datetime]
    last_scraped_at: Optional[datetime]
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class PriceStatsResponse(BaseModel):
    min_price_nok: float
    max_price_nok: float
    avg_price_nok: float
    median_price_nok: float
    num_competitors: int
    prices_by_website: Dict[str, float]


class AvailabilityResponse(BaseModel):
    in_stock_count: int
    out_of_stock_count: int
    by_website: Dict[str, Dict[str, Any]]


@router.get("/")
async def list_competitors(
    category: Optional[str] = None,
    brand: Optional[str] = None,
    website: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List competitor products with optional filters."""
    log_file = "competitors_debug.log"
    try:
        with open(log_file, "a") as f:
            f.write(f"\n=== REQUEST ===\n")
            f.write(f"category={category}, brand={brand}, website={website}, limit={limit}\n")
        
        products = competitor_service.get_competitor_products(
            db, category=category, brand=brand, website=website, limit=limit
        )
        
        with open(log_file, "a") as f:
            f.write(f"Got {len(products)} products\n")
        
        # Manually convert to avoid serialization issues
        result = []
        for idx, p in enumerate(products):
            try:
                item = {
                    "id": p.id,
                    "website": p.website,
                    "product_link": p.product_link,
                    "raw_name": p.raw_name,
                    "normalized_name": p.normalized_name,
                    "category": p.category,
                    "brand": p.brand,
                    "price_ore": p.price_ore,
                    "stock_status": p.stock_status,
                    "stock_amount": p.stock_amount,
                    "last_updated": p.last_scraped_at.isoformat() if p.last_scraped_at else None,
                    "price_last_changed": p.updated_at.isoformat() if p.updated_at else None,
                    "language": p.language,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "last_scraped_at": p.last_scraped_at.isoformat() if p.last_scraped_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                result.append(item)
            except Exception as e:
                with open(log_file, "a") as f:
                    f.write(f"ERROR converting product {idx}: {str(e)}\n")
                raise
        
        with open(log_file, "a") as f:
            f.write(f"Successfully converted {len(result)} products\n")
        
        return result
    except Exception as e:
        import traceback
        with open(log_file, "a") as f:
            f.write(f"EXCEPTION: {str(e)}\n")
            f.write(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to load competitors: {str(e)}")


@router.get("/stats/{normalized_name}", response_model=PriceStatsResponse)
async def get_price_stats(
    normalized_name: str,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get price statistics for a product across competitors."""
    stats = competitor_service.get_price_statistics(
        db, normalized_name, category=category, brand=brand
    )
    return stats


@router.get("/availability/{normalized_name}", response_model=AvailabilityResponse)
async def get_availability(
    normalized_name: str,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get availability status across competitors."""
    availability = competitor_service.get_availability_status(
        db, normalized_name, category=category, brand=brand
    )
    return availability


@router.get("/by-category/{category}")
async def list_by_category(
    category: str,
    brand: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all products in a category with price statistics."""
    products = competitor_service.get_competitor_products_by_category(
        db, category=category, brand=brand
    )
    return products


@router.post("/reprocess")
async def reprocess_competitors(
    website: Optional[str] = None,
    only_missing: bool = False,
    remove_non_pokemon: bool = False,
    db: Session = Depends(get_db)
):
    """Recompute normalization/category/brand/language for competitor products."""
    result = competitor_service.reprocess_competitor_products(
        db, website=website, only_missing=only_missing, remove_non_pokemon=remove_non_pokemon
    )
    return result


@router.post("/override/{normalized_name}")
async def create_override(
    normalized_name: str,
    category: Optional[str] = None,
    brand: Optional[str] = None,
    language: Optional[str] = None,
    website: Optional[str] = None,
    notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Create or update a competitor product override."""
    override = competitor_service.create_override(
        db,
        normalized_name=normalized_name,
        category=category,
        brand=brand,
        language=language,
        website=website,
        notes=notes
    )
    return {
        "id": override.id,
        "normalized_name": override.normalized_name,
        "category": override.category,
        "brand": override.brand,
        "language": override.language,
        "website": override.website,
        "notes": override.notes
    }


# ============================================================================
# SCRAPER ENDPOINTS
# ============================================================================

@router.post("/scrape/{scraper_name}")
async def run_scraper(scraper_name: str, db: Session = Depends(get_db)):
    """
    Run a specific competitor scraper.
    Supported: boosterpakker, hatamontcg, laboge, lcg_cards, pokemadness
    """
    from app.models import ScanLog
    import sys
    
    allowed_scrapers = ["boosterpakker", "hatamontcg", "laboge", "lcg_cards", "pokemadness"]
    
    if scraper_name not in allowed_scrapers:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported scraper. Allowed: {', '.join(allowed_scrapers)}"
        )
    
    started_at = datetime.now(ZoneInfo("Europe/Oslo"))
    print(f"\n[SCAN LOG] Starting scan: {scraper_name} at {started_at}", file=sys.stderr)
    
    try:
        # Run the scraper script
        env = os.environ.copy()
        env["CHROME_BINARY"] = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        env["CHROMEDRIVER_PATH"] = r"C:\Users\cmhag\Documents\Projects\Shopify\chromedriver-win64\chromedriver.exe"
        script_path = f"competition/{scraper_name}.py"
        print(f"[SCAN LOG] Running script: {script_path}", file=sys.stderr)
        print(f"[SCAN LOG] CHROMEDRIVER_PATH={env.get('CHROMEDRIVER_PATH')}", file=sys.stderr)
        
        result = await asyncio.to_thread(
            subprocess.run,
            ["python", script_path],
            capture_output=True,
            text=True,
            env=env,
            timeout=30 * 60  # 30 minute timeout
        )
        
        completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
        duration = (completed_at - started_at).total_seconds()
        
        print(f"[SCAN LOG] Completed in {duration:.2f}s. Return code: {result.returncode}", file=sys.stderr)
        print(f"[SCAN LOG] STDOUT length: {len(result.stdout)} chars", file=sys.stderr)
        print(f"[SCAN LOG] STDERR length: {len(result.stderr)} chars", file=sys.stderr)
        print(f"[SCAN LOG] STDOUT:\n{result.stdout[:500]}", file=sys.stderr)
        
        if result.returncode != 0:
            # Log failure
            log = ScanLog(
                scraper_name=scraper_name,
                status="failed",
                output=result.stdout,
                error_message=result.stderr,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration
            )
            db.add(log)
            db.commit()
            print(f"[SCAN LOG] Logged failed scan. Log ID: {log.id}", file=sys.stderr)
            
            raise HTTPException(
                status_code=500,
                detail=f"Scraper failed: {result.stderr}"
            )
        
        # Log success
        log = ScanLog(
            scraper_name=scraper_name,
            status="success",
            output=result.stdout,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(log)
        db.commit()
        print(f"[SCAN LOG] Logged successful scan. Log ID: {log.id}", file=sys.stderr)
        
        return {
            "status": "success",
            "scraper": scraper_name,
            "output": result.stdout,
            "timestamp": completed_at.isoformat(),
            "duration_seconds": duration,
            "log_id": log.id
        }
    except subprocess.TimeoutExpired:
        completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
        duration = (completed_at - started_at).total_seconds()
        log = ScanLog(
            scraper_name=scraper_name,
            status="failed",
            error_message="Scraper timed out after 30 minutes",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=504, detail="Scraper timed out")
    except Exception as e:
        completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
        duration = (completed_at - started_at).total_seconds()
        print(f"[SCAN LOG] Exception occurred: {str(e)}", file=sys.stderr)
        log = ScanLog(
            scraper_name=scraper_name,
            status="failed",
            error_message=str(e),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(log)
        db.commit()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/scrape-all")
async def run_all_scrapers(db: Session = Depends(get_db)):
    """Run all competitor scrapers."""
    from app.models import ScanLog
    
    scrapers = ["boosterpakker", "hatamontcg", "laboge", "lcg_cards", "pokemadness"]
    results = {}
    
    env = os.environ.copy()
    env.setdefault(
        "CHROME_BINARY",
        r"C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    )
    env.setdefault(
        "CHROMEDRIVER_PATH",
        r"C:\\Users\\cmhag\\Documents\\Projects\\Shopify\\chromedriver-win64\\chromedriver.exe"
    )

    for scraper_name in scrapers:
        started_at = datetime.now(ZoneInfo("Europe/Oslo"))
        try:
            script_path = f"competition/{scraper_name}.py"
            result = await asyncio.to_thread(
                subprocess.run,
                ["python", script_path],
                capture_output=True,
                text=True,
                env=env,
                timeout=20 * 60
            )
            
            completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
            duration = (completed_at - started_at).total_seconds()
            status = "success" if result.returncode == 0 else "failed"
            
            results[scraper_name] = {
                "status": status,
                "output": result.stdout,
                "error": result.stderr if result.returncode != 0 else None
            }
            
            # Create scan log entry
            scan_log = ScanLog(
                scraper_name=scraper_name,
                status=status,
                output=result.stdout if status == "success" else None,
                error_message=result.stderr if status == "failed" else None,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration
            )
            db.add(scan_log)
            
        except Exception as e:
            completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
            duration = (completed_at - started_at).total_seconds()
            
            results[scraper_name] = {
                "status": "error",
                "error": str(e)
            }
            
            # Create error scan log entry
            scan_log = ScanLog(
                scraper_name=scraper_name,
                status="failed",
                output=None,
                error_message=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration
            )
            db.add(scan_log)
    
    db.commit()
    
    return {
        "timestamp": datetime.now(ZoneInfo("Europe/Oslo")).isoformat(),
        "results": results
    }



# ============================================================================
# MAPPING ENDPOINTS
# ============================================================================

@router.get("/unmapped")
async def get_unmapped_competitors(
    category: Optional[str] = None,
    brand: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get unmapped competitor products with suggestions."""
    unmapped = competitor_mapping_service.get_unmapped_competitors(
        db, category=category, brand=brand, limit=limit
    )
    return unmapped


@router.get("/mapped")
async def get_mapped_competitors(
    limit: int = 500,
    db: Session = Depends(get_db)
):
    """Get mapped competitor products with Shopify details."""
    try:
        mapped = competitor_mapping_service.get_mapped_competitors(
            db, limit=limit
        )
        return mapped
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/map-to-shopify")
async def map_to_shopify(
    competitor_id: int,
    shopify_product_id: int,
    db: Session = Depends(get_db)
):
    """Map a competitor product to a Shopify product."""
    mapping = competitor_mapping_service.map_competitor_to_shopify(
        db, competitor_id, shopify_product_id
    )
    return mapping


@router.post("/auto-map")
async def auto_map_competitors(
    db: Session = Depends(get_db)
):
    """Automatically map unmapped competitors to SNKRDUNK products."""
    try:
        result = competitor_mapping_service.auto_map_competitors(db)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/scan-logs")
async def get_scan_logs(
    scraper_name: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get scan logs, optionally filtered by scraper name."""
    from app.models import ScanLog
    
    query = db.query(ScanLog).order_by(ScanLog.created_at.desc())
    
    if scraper_name:
        query = query.filter(ScanLog.scraper_name == scraper_name)
    
    logs = query.limit(limit).all()
    
    return [
        {
            "id": log.id,
            "scraper_name": log.scraper_name,
            "status": log.status,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "duration_seconds": log.duration_seconds,
            "output": log.output,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None
        }
        for log in logs
    ]


@router.get("/sync-status")
async def get_sync_status(db: Session = Depends(get_db)):
    """Get synchronization status from database."""
    from app.models import ScanLog, CompetitorProduct
    from sqlalchemy import func
    from datetime import datetime, timezone
    from zoneinfo import ZoneInfo
    
    # Get latest competitor scan
    latest_scrape = db.query(ScanLog).order_by(ScanLog.created_at.desc()).first()
    
    # Convert UTC to Oslo time (Europe/Oslo)
    last_scrape_oslo = None
    if latest_scrape and latest_scrape.created_at:
        # Ensure the datetime is timezone-aware
        if latest_scrape.created_at.tzinfo is None:
            utc_time = latest_scrape.created_at.replace(tzinfo=timezone.utc)
        else:
            utc_time = latest_scrape.created_at
        oslo_tz = ZoneInfo('Europe/Oslo')
        last_scrape_oslo = utc_time.astimezone(oslo_tz).isoformat()
    
    # Count competitor products by website
    products_by_website = db.query(
        CompetitorProduct.website,
        func.count(CompetitorProduct.id).label('count')
    ).group_by(
        CompetitorProduct.website
    ).all()
    
    return {
        "last_competitor_scrape": last_scrape_oslo,
        "last_scrape_status": latest_scrape.status if latest_scrape else None,
        "total_competitor_products": db.query(CompetitorProduct).count(),
        "scrapers_summary": [
            {
                "name": website,
                "status": "success",
                "product_count": count
            }
            for website, count in products_by_website
        ]
    }



@router.get("/scan-logs/{log_id}")
async def get_scan_log(
    log_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific scan log with full output."""
    from app.models import ScanLog
    
    log = db.query(ScanLog).filter(ScanLog.id == log_id).first()
    if not log:
        raise HTTPException(status_code=404, detail="Scan log not found")
    
    return {
        "id": log.id,
        "scraper_name": log.scraper_name,
        "status": log.status,
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
        "duration_seconds": log.duration_seconds,
        "output": log.output,
        "error_message": log.error_message,
        "created_at": log.created_at.isoformat() if log.created_at else None
    }

@router.post("/map-to-snkrdunk")
async def map_to_snkrdunk(
    competitor_id: int,
    snkrdunk_mapping_id: int,
    db: Session = Depends(get_db)
):
    """Map a competitor product to a SNKRDUNK product."""
    try:
        mapping = competitor_mapping_service.map_competitor_to_snkrdunk(
            db, competitor_id, snkrdunk_mapping_id
        )
        return mapping
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/mappings/{mapping_id}")
async def unmap_competitor(
    mapping_id: int,
    db: Session = Depends(get_db)
):
    """Unmap a competitor product mapping."""
    try:
        mapping = db.query(CompetitorProductMapping).filter(
            CompetitorProductMapping.id == mapping_id
        ).first()
        
        if not mapping:
            raise HTTPException(status_code=404, detail="Mapping not found")
        
        db.delete(mapping)
        db.commit()
        
        return {
            "status": "unmapped",
            "mapping_id": mapping_id,
            "message": "Mapping deleted successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/price-comparison/{shopify_product_id}")
async def get_price_comparison(
    shopify_product_id: int,
    db: Session = Depends(get_db)
):
    """Get price comparison for a Shopify product vs competitors."""
    comparison = competitor_mapping_service.get_competitive_price_comparison(
        db, shopify_product_id
    )
    return comparison


@router.get("/low-stock-alerts")
async def get_low_stock_alerts(
    db: Session = Depends(get_db)
):
    """
    Get low stock alerts for products that are mapped to competitors.
    Returns products with stock <= 10 that have competitor mappings.
    """
    from app.models import Product, Variant, CompetitorProductMapping
    from sqlalchemy import and_

    try:
        # Query for products with low stock that have competitor mappings
        low_stock_products = (
            db.query(Product, Variant)
            .join(Variant, Product.id == Variant.product_id)
            .join(CompetitorProductMapping, CompetitorProductMapping.shopify_product_id == Product.id)
            .filter(
                and_(
                    Product.status == 'ACTIVE',
                    Variant.inventory_quantity <= 10
                )
            )
            .distinct(Product.id)
            .all()
        )

        alerts = []
        for product, variant in low_stock_products:
            stock_level = variant.inventory_quantity or 0
            severity = 'critical' if stock_level == 0 else 'warning' if stock_level <= 5 else 'info'

            alerts.append({
                'product_id': product.id,
                'product_title': product.title,
                'product_handle': product.handle,
                'variant_id': variant.id,
                'variant_title': variant.title,
                'stock': stock_level,
                'severity': severity,
                'message': f"{product.title} - {stock_level} units left"
            })

        # Sort by stock level (lowest first)
        alerts.sort(key=lambda x: x['stock'])

        return {
            'total_alerts': len(alerts),
            'critical': sum(1 for a in alerts if a['severity'] == 'critical'),
            'warning': sum(1 for a in alerts if a['severity'] == 'warning'),
            'alerts': alerts
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch low stock alerts: {str(e)}")


@router.get("/price-changes")
async def get_competitor_price_changes(
    days_back: int = 30,
    competitor: Optional[str] = None,
    change_type: Optional[str] = None,  # 'price', 'stock', or 'all'
    db: Session = Depends(get_db)
):
    """
    Get competitor price and stock changes by comparing daily snapshots.
    Detects when competitors have changed their prices or stock levels.
    Includes sales velocity metrics for each product.
    """
    from app.models import CompetitorProductDaily, CompetitorProduct
    from app.services.competitor_service import competitor_service
    from sqlalchemy import func, and_, desc
    from datetime import timedelta, date
    
    try:
        # Calculate the cutoff date
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # Query all daily snapshots with product information
        query = db.query(
            CompetitorProductDaily,
            CompetitorProduct
        ).join(
            CompetitorProduct,
            CompetitorProductDaily.competitor_product_id == CompetitorProduct.id
        ).filter(
            CompetitorProductDaily.day >= cutoff_date.isoformat()
        )
        
        if competitor:
            query = query.filter(CompetitorProduct.website == competitor)
        
        # Get all snapshots ordered by product_id and day
        snapshots = query.order_by(
            CompetitorProductDaily.competitor_product_id,
            CompetitorProductDaily.day
        ).all()
        
        # Pre-calculate velocity metrics for all unique products (avoid repeated calculations)
        unique_product_ids = set()
        for daily, product in snapshots:
            unique_product_ids.add(product.id)
        
        velocity_cache = {}
        for product_id in unique_product_ids:
            try:
                velocity_cache[product_id] = competitor_service.calculate_sales_velocity(
                    db, product_id, days_back=days_back
                )
            except Exception as e:
                print(f"Velocity calculation error for product {product_id}: {e}")
                velocity_cache[product_id] = {
                    'insufficient_data': True,
                    'avg_daily_sales': 0,
                    'weekly_sales_estimate': 0,
                    'days_until_sellout': None
                }
        
        # Group by product_id to detect changes
        changes = []
        current_product_id = None
        previous_daily = None
        previous_product = None
        
        for daily, product in snapshots:
            if current_product_id != daily.competitor_product_id:
                # New product, reset tracking
                current_product_id = daily.competitor_product_id
                previous_daily = daily
                previous_product = product
                continue
            
            # Parse prices
            try:
                prev_price_str = previous_daily.price or "0"
                curr_price_str = daily.price or "0"
                
                # Handle Norwegian price format
                # If price contains comma (829,00), it's already in kroner
                # If price is just digits (82900), it's in øre and needs to be divided by 100
                if ',' in prev_price_str or '.' in prev_price_str:
                    # Price has decimal separator - treat as kroner
                    prev_price_str = prev_price_str.replace(',', '.').replace(' ', '')
                    prev_price_str = ''.join(c for c in prev_price_str if c.isdigit() or c == '.')
                    prev_price = float(prev_price_str) if prev_price_str else 0
                else:
                    # Price is just digits - assume it's in øre, divide by 100
                    prev_price_str = ''.join(c for c in prev_price_str if c.isdigit())
                    prev_price = (float(prev_price_str) / 100.0) if prev_price_str else 0
                
                if ',' in curr_price_str or '.' in curr_price_str:
                    # Price has decimal separator - treat as kroner
                    curr_price_str = curr_price_str.replace(',', '.').replace(' ', '')
                    curr_price_str = ''.join(c for c in curr_price_str if c.isdigit() or c == '.')
                    curr_price = float(curr_price_str) if curr_price_str else 0
                else:
                    # Price is just digits - assume it's in øre, divide by 100
                    curr_price_str = ''.join(c for c in curr_price_str if c.isdigit())
                    curr_price = (float(curr_price_str) / 100.0) if curr_price_str else 0
                
                # Parse stock amounts
                prev_stock = previous_daily.stock_amount or 0
                curr_stock = daily.stock_amount or 0
                
                prev_stock_status = previous_daily.stock_status or "Unknown"
                curr_stock_status = daily.stock_status or "Unknown"
                
                # Detect price change
                price_changed = abs(curr_price - prev_price) >= 0.01
                
                # Detect stock change (amount or status)
                stock_changed = (prev_stock != curr_stock) or (prev_stock_status != curr_stock_status)
                
                # Filter by change type
                should_include = False
                if not change_type or change_type == 'all':
                    should_include = price_changed or stock_changed
                elif change_type == 'price':
                    should_include = price_changed
                elif change_type == 'stock':
                    should_include = stock_changed
                
                if should_include:
                    # Get pre-calculated velocity metrics
                    velocity_metrics = velocity_cache.get(product.id, {
                        'insufficient_data': True,
                        'avg_daily_sales': 0,
                        'weekly_sales_estimate': 0,
                        'days_until_sellout': None
                    })
                    
                    change_record = {
                        "product_name": product.normalized_name or product.raw_name or "Unknown Product",
                        "product_link": product.product_link,
                        "product_id": product.id,
                        "competitor_name": product.website.replace('_', ' ').title(),
                        "previous_date": previous_daily.day,
                        "current_date": daily.day,
                        "changed_at": daily.day,
                        "category": product.category,
                        
                        # Price data
                        "price_changed": price_changed,
                        "previous_price": prev_price,
                        "current_price": curr_price,
                        
                        # Stock data
                        "stock_changed": stock_changed,
                        "previous_stock_amount": prev_stock,
                        "current_stock_amount": curr_stock,
                        "previous_stock_status": prev_stock_status,
                        "current_stock_status": curr_stock_status,
                        
                        # Current in_stock flag
                        "in_stock": "lager" in curr_stock_status.lower() or "stock" in curr_stock_status.lower(),
                        
                        # Sales velocity metrics
                        "velocity": velocity_metrics
                    }
                    changes.append(change_record)
                    
            except (ValueError, AttributeError) as e:
                # Skip if parsing fails
                print(f"Parsing error for product {product.id}: {e}")
                pass
            
            previous_daily = daily
            previous_product = product
        
        # Sort by most recent changes first
        changes.sort(key=lambda x: x['changed_at'], reverse=True)

        return changes

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch price changes: {str(e)}")


@router.get("/{competitor_product_id}/daily-snapshots")
async def get_competitor_daily_snapshots(
    competitor_product_id: int,
    days_back: int = 30,
    db: Session = Depends(get_db)
):
    """
    Get daily stock/price snapshots for a specific competitor product.
    Returns chronological data showing stock levels, prices, and changes over time.
    """
    from app.models import CompetitorProductDaily
    from datetime import timedelta, date

    try:
        # Verify competitor product exists
        competitor_product = db.query(CompetitorProduct).filter(
            CompetitorProduct.id == competitor_product_id
        ).first()

        if not competitor_product:
            raise HTTPException(status_code=404, detail=f"Competitor product {competitor_product_id} not found")

        # Calculate cutoff date
        cutoff_date = date.today() - timedelta(days=days_back)

        # Fetch daily snapshots
        snapshots = db.query(CompetitorProductDaily).filter(
            and_(
                CompetitorProductDaily.competitor_product_id == competitor_product_id,
                CompetitorProductDaily.day >= cutoff_date.isoformat()
            )
        ).order_by(CompetitorProductDaily.day).all()

        if not snapshots:
            return []

        # Convert to list of dicts with parsed prices
        result = []
        for snapshot in snapshots:
            # Parse price string to int
            price_ore = None
            if snapshot.price:
                try:
                    price_ore = int(snapshot.price) if isinstance(snapshot.price, str) else snapshot.price
                except (ValueError, TypeError):
                    price_ore = competitor_product.price_ore
            else:
                price_ore = competitor_product.price_ore

            result.append({
                'day': snapshot.day,
                'stock_amount': snapshot.stock_amount or 0,
                'price': (price_ore / 100) if price_ore else 0,
                'price_ore': price_ore,
                'stock_status': snapshot.stock_status
            })

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch daily snapshots: {str(e)}")
