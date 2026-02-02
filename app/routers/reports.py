"""Reports router."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import StockReportResponse, AuditLogResponse
from app.services import report_service

router = APIRouter()


@router.post("/stock", response_model=StockReportResponse)
async def generate_stock_report(
    collection_id: str,
    db: Session = Depends(get_db)
):
    """
    Generate stock report for a collection.
    
    This replaces the shopify_stock_report.py functionality.
    """
    try:
        report = await report_service.generate_stock_report(
            db=db,
            collection_id=collection_id
        )
        return report
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stock", response_model=List[StockReportResponse])
async def list_stock_reports(
    collection_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    """List all stock reports."""
    reports = report_service.get_stock_reports(
        db=db,
        collection_id=collection_id,
        skip=skip,
        limit=limit
    )
    return reports


@router.get("/stock/{report_id}", response_model=StockReportResponse)
async def get_stock_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific stock report."""
    report = report_service.get_stock_report_by_id(db=db, report_id=report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/audit-logs", response_model=List[AuditLogResponse])
async def get_audit_logs(
    operation: Optional[str] = None,
    entity_type: Optional[str] = None,
    success: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get audit logs with optional filtering."""
    logs = report_service.get_audit_logs(
        db=db,
        operation=operation,
        entity_type=entity_type,
        success=success,
        skip=skip,
        limit=limit
    )
    return logs


@router.get("/audit-logs/{log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    log_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific audit log."""
    log = report_service.get_audit_log_by_id(db=db, log_id=log_id)
    if not log:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return log


@router.get("/statistics")
async def get_statistics(db: Session = Depends(get_db)):
    """Get general statistics about the system."""
    stats = report_service.get_statistics(db=db)
    return stats
