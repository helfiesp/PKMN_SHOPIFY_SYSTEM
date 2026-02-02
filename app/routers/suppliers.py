"""API routes for supplier product tracking."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
import subprocess
import asyncio
import os

from app.database import get_db
from app.services.supplier_service import SupplierService
from app.models import SupplierWebsite, SupplierProduct, SupplierAlert, SupplierScanLog

router = APIRouter(prefix="/suppliers", tags=["suppliers"])


# ===========================================================================
# Pydantic Schemas
# ===========================================================================

class SupplierWebsiteCreate(BaseModel):
    name: str
    url: str
    scraper_type: str = "generic"
    scan_interval_hours: int = 6
    notify_on_new_products: bool = True
    notify_on_restock: bool = True
    notification_webhook: Optional[str] = None


class SupplierWebsiteResponse(BaseModel):
    id: int
    name: str
    url: str
    scraper_type: str
    is_active: bool
    scan_interval_hours: int
    notify_on_new_products: bool
    notify_on_restock: bool
    last_scan_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class SupplierProductResponse(BaseModel):
    id: int
    supplier_website_id: int
    product_url: str
    name: str
    sku: Optional[str]
    price: Optional[float]
    currency: str
    in_stock: bool
    stock_quantity: Optional[int]
    is_new: bool
    category: Optional[str]
    image_url: Optional[str]
    first_seen_at: datetime
    last_scraped_at: Optional[datetime]
    last_seen_in_stock: Optional[datetime]

    class Config:
        from_attributes = True


class SupplierAlertResponse(BaseModel):
    id: int
    supplier_product_id: int
    alert_type: str
    message: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SupplierScanLogResponse(BaseModel):
    id: int
    supplier_website_id: int
    status: str
    products_found: int
    new_products: int
    restocked_products: int
    error_message: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]
    created_at: datetime

    class Config:
        from_attributes = True


class ScanTriggerRequest(BaseModel):
    website_id: int
    force: bool = False


# ===========================================================================
# API Endpoints
# ===========================================================================

@router.post("/websites", response_model=SupplierWebsiteResponse)
def create_supplier_website(
    data: SupplierWebsiteCreate,
    db: Session = Depends(get_db)
):
    """Create a new supplier website to track."""
    website = SupplierService.create_supplier_website(
        db=db,
        name=data.name,
        url=data.url,
        scraper_type=data.scraper_type,
        scan_interval_hours=data.scan_interval_hours,
        notify_on_new_products=data.notify_on_new_products,
        notify_on_restock=data.notify_on_restock,
        notification_webhook=data.notification_webhook,
    )
    return website


@router.get("/websites", response_model=List[SupplierWebsiteResponse])
def list_supplier_websites(
    active_only: bool = Query(False),
    db: Session = Depends(get_db)
):
    """Get all supplier websites."""
    websites = SupplierService.get_supplier_websites(db, active_only=active_only)
    return websites


@router.get("/websites/{website_id}", response_model=SupplierWebsiteResponse)
def get_supplier_website(
    website_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific supplier website."""
    website = SupplierService.get_supplier_website(db, website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Supplier website not found")
    return website


@router.get("/products/new", response_model=List[SupplierProductResponse])
def get_new_products(
    website_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get new products that haven't been acknowledged."""
    products = SupplierService.get_new_products(db, website_id=website_id, limit=limit)
    return products


@router.get("/products/in-stock", response_model=List[SupplierProductResponse])
def get_in_stock_products(
    website_id: Optional[int] = Query(None),
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db)
):
    """Get products currently in stock."""
    products = SupplierService.get_in_stock_products(db, website_id=website_id, limit=limit)
    return products


@router.post("/products/{product_id}/acknowledge")
def acknowledge_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Mark a new product as acknowledged."""
    try:
        product = SupplierService.mark_product_as_acknowledged(db, product_id)
        return {"message": "Product acknowledged", "product_id": product.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/products/{product_id}/hide")
def hide_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Hide a product (mark as irrelevant)."""
    try:
        product = SupplierService.hide_product(db, product_id)
        return {"message": "Product hidden", "product_id": product.id, "name": product.name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/products/{product_id}/unhide")
def unhide_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Unhide a product."""
    try:
        product = SupplierService.unhide_product(db, product_id)
        return {"message": "Product unhidden", "product_id": product.id, "name": product.name}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/alerts", response_model=List[SupplierAlertResponse])
def get_alerts(
    unread_only: bool = Query(True),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get supplier alerts."""
    if unread_only:
        alerts = SupplierService.get_unread_alerts(db, limit=limit)
    else:
        alerts = db.query(SupplierAlert).order_by(SupplierAlert.created_at.desc()).limit(limit).all()
    return alerts


@router.post("/alerts/{alert_id}/mark-read")
def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """Mark an alert as read."""
    success = SupplierService.mark_alert_as_read(db, alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"message": "Alert marked as read", "alert_id": alert_id}


@router.get("/scan-logs", response_model=List[SupplierScanLogResponse])
def get_scan_logs(
    website_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db)
):
    """Get scan logs for supplier websites."""
    logs = SupplierService.get_scan_logs(db, website_id=website_id, limit=limit)
    return logs


@router.post("/scan")
async def trigger_supplier_scan(
    request: ScanTriggerRequest,
    db: Session = Depends(get_db)
):
    """Manually trigger a supplier scan by running the appropriate scraper."""
    website = SupplierService.get_supplier_website(db, request.website_id)
    if not website:
        raise HTTPException(status_code=404, detail="Supplier website not found")
    
    # Map website IDs to scraper modules
    scraper_map = {
        1: "suppliers.lekekassen",
        2: "suppliers.extra_leker"
    }
    
    scraper_module = scraper_map.get(request.website_id)
    if not scraper_module:
        raise HTTPException(
            status_code=400,
            detail=f"No scraper configured for website ID {request.website_id}"
        )
    
    started_at = datetime.now(timezone.utc)
    
    try:
        # Set up environment with Chrome paths
        env = os.environ.copy()
        env.setdefault("CHROMEDRIVER_PATH", "/usr/bin/chromedriver")
        
        # Run the scraper as a subprocess
        result = await asyncio.to_thread(
            subprocess.run,
            ["python", "-m", scraper_module, str(request.website_id)],
            capture_output=True,
            text=True,
            env=env,
            timeout=30 * 60  # 30 minute timeout
        )
        
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()
        
        # Parse output for statistics
        output_lines = result.stdout.split('\n') if result.stdout else []
        total_products = 0
        for line in output_lines:
            if "Total products scraped:" in line:
                try:
                    total_products = int(line.split(":")[-1].strip())
                except:
                    pass
        
        status = "success" if result.returncode == 0 else "failed"
        
        # Create scan log
        scan_log = SupplierScanLog(
            website_id=request.website_id,
            status=status,
            total_products=total_products,
            output=result.stdout if status == "success" else None,
            error_message=result.stderr if status == "failed" else None,
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(scan_log)
        db.commit()
        
        return {
            "message": f"Scan {'completed successfully' if status == 'success' else 'failed'}",
            "website_id": request.website_id,
            "website_name": website.name,
            "status": status,
            "total_products": total_products,
            "duration_seconds": duration,
            "scan_log_id": scan_log.id
        }
        
    except subprocess.TimeoutExpired:
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()
        
        scan_log = SupplierScanLog(
            website_id=request.website_id,
            status="timeout",
            error_message="Scan timed out after 30 minutes",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(scan_log)
        db.commit()
        
        raise HTTPException(status_code=408, detail="Scan timed out after 30 minutes")
    
    except Exception as e:
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()
        
        scan_log = SupplierScanLog(
            website_id=request.website_id,
            status="error",
            error_message=str(e),
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(scan_log)
        db.commit()
        
        raise HTTPException(status_code=500, detail=f"Scan failed: {str(e)}")



@router.get("/statistics")
def get_supplier_statistics(db: Session = Depends(get_db)):
    """Get overall supplier tracking statistics."""
    total_websites = db.query(SupplierWebsite).count()
    active_websites = db.query(SupplierWebsite).filter(SupplierWebsite.is_active == True).count()
    
    # Exclude hidden products from main statistics
    total_products = db.query(SupplierProduct).filter(SupplierProduct.is_hidden == False).count()
    in_stock_products = db.query(SupplierProduct).filter(
        SupplierProduct.in_stock == True,
        SupplierProduct.is_hidden == False
    ).count()
    new_products = db.query(SupplierProduct).filter(
        SupplierProduct.is_new == True,
        SupplierProduct.is_hidden == False
    ).count()
    unread_alerts = db.query(SupplierAlert).filter(SupplierAlert.is_read == False).count()
    hidden_products = db.query(SupplierProduct).filter(SupplierProduct.is_hidden == True).count()

    return {
        "total_websites": total_websites,
        "active_websites": active_websites,
        "total_products": total_products,
        "in_stock_products": in_stock_products,
        "new_products": new_products,
        "unread_alerts": unread_alerts,
        "hidden_products": hidden_products
    }
