"""Report service - handles stock reports and audit logs."""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone

from app.models import StockReport, AuditLog, Product, Variant, PricePlan, SnkrdunkMapping, SnkrdunkScanLog, CompetitorProduct, CompetitorProductMapping
from app.schemas import StockReportCreate, AuditLogCreate


class ReportService:
    """Service for reports and audit logs."""
    
    async def generate_stock_report(
        self,
        db: Session,
        collection_id: str
    ) -> StockReport:
        """
        Generate stock report for a collection.
        
        Replicates shopify_stock_report.py functionality.
        """
        # Get products from collection
        products = db.query(Product).filter(
            Product.collection_id == collection_id,
            Product.status == "active"
        ).all()
        
        total_products = len(products)
        total_variants = 0
        
        report_data = {
            "collection_id": collection_id,
            "products": []
        }
        
        for product in products:
            variants = db.query(Variant).filter(Variant.product_id == product.id).all()
            total_variants += len(variants)
            
            product_data = {
                "product_id": product.shopify_id,
                "product_title": product.title,
                "handle": product.handle,
                "template_suffix": product.template_suffix,
                "preorder": product.is_preorder,
                "variants": []
            }
            
            for variant in variants:
                product_data["variants"].append({
                    "variant_id": variant.shopify_id,
                    "variant_title": variant.title,
                    "sku": variant.sku,
                    "inventory_quantity": variant.inventory_quantity,
                    "available_for_sale": variant.available_for_sale,
                    "price": variant.price
                })
            
            report_data["products"].append(product_data)
        
        # Create stock report
        stock_report = StockReport(
            collection_id=collection_id,
            generated_at=datetime.now(timezone.utc),
            total_products=total_products,
            total_variants=total_variants,
            report_data=report_data
        )
        
        db.add(stock_report)
        db.commit()
        db.refresh(stock_report)
        
        return stock_report
    
    def get_stock_reports(
        self,
        db: Session,
        collection_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 20
    ) -> List[StockReport]:
        """Get stock reports."""
        query = db.query(StockReport)
        
        if collection_id:
            query = query.filter(StockReport.collection_id == collection_id)
        
        return query.order_by(StockReport.generated_at.desc()).offset(skip).limit(limit).all()
    
    def get_stock_report_by_id(self, db: Session, report_id: int) -> Optional[StockReport]:
        """Get a specific stock report."""
        return db.query(StockReport).filter(StockReport.id == report_id).first()
    
    # Audit logs
    
    def create_audit_log(self, db: Session, log_data: AuditLogCreate) -> AuditLog:
        """Create an audit log entry."""
        audit_log = AuditLog(**log_data.model_dump())
        db.add(audit_log)
        db.commit()
        db.refresh(audit_log)
        return audit_log
    
    def get_audit_logs(
        self,
        db: Session,
        operation: Optional[str] = None,
        entity_type: Optional[str] = None,
        success: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[AuditLog]:
        """Get audit logs."""
        query = db.query(AuditLog)
        
        if operation:
            query = query.filter(AuditLog.operation == operation)
        if entity_type:
            query = query.filter(AuditLog.entity_type == entity_type)
        if success is not None:
            query = query.filter(AuditLog.success == success)
        
        return query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()
    
    def get_audit_log_by_id(self, db: Session, log_id: int) -> Optional[AuditLog]:
        """Get a specific audit log."""
        return db.query(AuditLog).filter(AuditLog.id == log_id).first()
    
    def get_statistics(self, db: Session) -> dict:
        """Get general statistics."""
        from app.models import (
            CompetitorProduct, CompetitorProductMapping, SnkrdunkMapping, PricePlan
        )
        from datetime import datetime, timezone
        
        # Get last competitor scrape time (use last_scraped_at or updated_at)
        last_competitor = db.query(CompetitorProduct).order_by(
            CompetitorProduct.last_scraped_at.desc()
        ).first()
        if not last_competitor or not last_competitor.last_scraped_at:
            # Fallback to updated_at
            last_competitor = db.query(CompetitorProduct).order_by(
                CompetitorProduct.updated_at.desc()
            ).first()
            last_competitor_scrape = last_competitor.updated_at if last_competitor else None
        else:
            last_competitor_scrape = last_competitor.last_scraped_at
        
        # Get last SNKRDUNK fetch time from scan logs
        last_snkrdunk_scan = db.query(SnkrdunkScanLog).order_by(
            SnkrdunkScanLog.created_at.desc()
        ).first()
        last_snkrdunk_fetch = last_snkrdunk_scan.created_at if last_snkrdunk_scan else None
        
        # Get last price plan applied
        last_plan = db.query(PricePlan).filter(
            PricePlan.status == "applied"
        ).order_by(PricePlan.applied_at.desc()).first()
        last_price_plan_applied = last_plan.applied_at if last_plan else None
        
        return {
            "total_products": db.query(Product).count(),
            "active_products": db.query(Product).filter(Product.status == "active").count(),
            "total_variants": db.query(Variant).count(),
            "total_snkrdunk_mappings": db.query(SnkrdunkMapping).count(),
            "total_competitor_products": db.query(CompetitorProduct).count(),
            "mapped_competitors": db.query(CompetitorProductMapping).count(),
            "pending_price_plans": db.query(PricePlan).filter(PricePlan.status == "pending").count(),
            "applied_price_plans": db.query(PricePlan).filter(PricePlan.status == "applied").count(),
            "last_competitor_scrape": last_competitor_scrape.isoformat() if last_competitor_scrape else None,
            "last_snkrdunk_fetch": last_snkrdunk_fetch.isoformat() if last_snkrdunk_fetch else None,
            "last_price_plan_applied": last_price_plan_applied.isoformat() if last_price_plan_applied else None,
        }


report_service = ReportService()
