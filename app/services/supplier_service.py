"""Service for managing supplier product tracking."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models import (
    SupplierWebsite,
    SupplierProduct,
    SupplierAvailabilityHistory,
    SupplierScanLog,
    SupplierAlert,
)


class SupplierService:
    """Service for managing supplier websites and products."""

    @staticmethod
    def create_supplier_website(
        db: Session,
        name: str,
        url: str,
        scraper_type: str = "generic",
        scan_interval_hours: int = 6,
        notify_on_new_products: bool = True,
        notify_on_restock: bool = True,
        notification_webhook: Optional[str] = None,
    ) -> SupplierWebsite:
        """Create a new supplier website."""
        website = SupplierWebsite(
            name=name,
            url=url,
            scraper_type=scraper_type,
            scan_interval_hours=scan_interval_hours,
            notify_on_new_products=notify_on_new_products,
            notify_on_restock=notify_on_restock,
            notification_webhook=notification_webhook,
            is_active=True,
        )
        db.add(website)
        db.commit()
        db.refresh(website)
        return website

    @staticmethod
    def get_supplier_websites(
        db: Session,
        active_only: bool = False
    ) -> List[SupplierWebsite]:
        """Get all supplier websites."""
        query = db.query(SupplierWebsite)
        if active_only:
            query = query.filter(SupplierWebsite.is_active == True)
        return query.order_by(SupplierWebsite.name).all()

    @staticmethod
    def get_supplier_website(db: Session, website_id: int) -> Optional[SupplierWebsite]:
        """Get a supplier website by ID."""
        return db.query(SupplierWebsite).filter(SupplierWebsite.id == website_id).first()

    @staticmethod
    def update_or_create_product(
        db: Session,
        website_id: int,
        product_url: str,
        name: str,
        in_stock: bool,
        price: Optional[float] = None,
        stock_quantity: Optional[int] = None,
        sku: Optional[str] = None,
        category: Optional[str] = None,
        image_url: Optional[str] = None,
        description: Optional[str] = None,
        external_id: Optional[str] = None,
    ) -> tuple[SupplierProduct, bool, bool]:
        """
        Create or update a supplier product.
        Returns: (product, is_new_product, is_restocked)
        """
        # Check if product exists
        existing = db.query(SupplierProduct).filter(
            SupplierProduct.supplier_website_id == website_id,
            SupplierProduct.product_url == product_url
        ).first()

        now = datetime.now(ZoneInfo("Europe/Oslo"))
        is_new_product = False
        is_restocked = False

        if existing:
            # Check for restock
            was_out_of_stock = not existing.in_stock
            is_restocked = was_out_of_stock and in_stock

            # Update existing product
            existing.name = name
            existing.in_stock = in_stock
            existing.stock_quantity = stock_quantity
            existing.price = price
            existing.sku = sku
            existing.category = category
            existing.image_url = image_url
            existing.description = description
            existing.external_id = external_id
            existing.last_scraped_at = now

            if in_stock:
                existing.last_seen_in_stock = now

            # Track availability changes
            SupplierService._record_availability_snapshot(db, existing, is_restocked, False)

            product = existing
        else:
            # Create new product
            product = SupplierProduct(
                supplier_website_id=website_id,
                product_url=product_url,
                name=name,
                in_stock=in_stock,
                stock_quantity=stock_quantity,
                price=price,
                sku=sku,
                category=category,
                image_url=image_url,
                description=description,
                external_id=external_id,
                last_scraped_at=now,
                last_seen_in_stock=now if in_stock else None,
                is_new=True,
            )
            db.add(product)
            db.flush()  # Get product.id
            is_new_product = True

            # Record initial availability
            SupplierService._record_availability_snapshot(db, product, False, False)

        db.commit()
        db.refresh(product)

        return product, is_new_product, is_restocked

    @staticmethod
    def _record_availability_snapshot(
        db: Session,
        product: SupplierProduct,
        stock_changed: bool,
        price_changed: bool
    ):
        """Record availability history snapshot."""
        history = SupplierAvailabilityHistory(
            supplier_product_id=product.id,
            in_stock=product.in_stock,
            stock_quantity=product.stock_quantity,
            price=product.price,
            stock_changed=stock_changed,
            price_changed=price_changed,
        )
        db.add(history)

    @staticmethod
    def create_alert(
        db: Session,
        product_id: int,
        alert_type: str,
        message: str
    ) -> SupplierAlert:
        """Create a new supplier alert."""
        alert = SupplierAlert(
            supplier_product_id=product_id,
            alert_type=alert_type,
            message=message,
            is_read=False,
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        return alert

    @staticmethod
    def get_unread_alerts(db: Session, limit: int = 50) -> List[SupplierAlert]:
        """Get unread alerts."""
        return db.query(SupplierAlert).filter(
            SupplierAlert.is_read == False
        ).order_by(
            desc(SupplierAlert.created_at)
        ).limit(limit).all()

    @staticmethod
    def mark_alert_as_read(db: Session, alert_id: int) -> bool:
        """Mark an alert as read."""
        alert = db.query(SupplierAlert).filter(SupplierAlert.id == alert_id).first()
        if alert:
            alert.is_read = True
            db.commit()
            return True
        return False

    @staticmethod
    def mark_product_as_acknowledged(db: Session, product_id: int) -> SupplierProduct:
        """Mark a new product as acknowledged (no longer 'new')."""
        product = db.query(SupplierProduct).filter(SupplierProduct.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")
        product.is_new = False
        db.commit()
        db.refresh(product)
        return product
    
    @staticmethod
    def hide_product(db: Session, product_id: int) -> SupplierProduct:
        """Hide a product (mark as irrelevant)."""
        product = db.query(SupplierProduct).filter(SupplierProduct.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")
        product.is_hidden = True
        product.is_new = False  # Also mark as acknowledged
        db.commit()
        db.refresh(product)
        return product
    
    @staticmethod
    def unhide_product(db: Session, product_id: int) -> SupplierProduct:
        """Unhide a product."""
        product = db.query(SupplierProduct).filter(SupplierProduct.id == product_id).first()
        if not product:
            raise ValueError(f"Product {product_id} not found")
        product.is_hidden = False
        db.commit()
        db.refresh(product)
        return product

    @staticmethod
    def get_new_products(
        db: Session,
        website_id: Optional[int] = None,
        limit: int = 50,
        include_hidden: bool = False
    ) -> List[SupplierProduct]:
        """Get new products that haven't been acknowledged."""
        query = db.query(SupplierProduct).filter(SupplierProduct.is_new == True)
        if not include_hidden:
            query = query.filter(SupplierProduct.is_hidden == False)
        if website_id:
            query = query.filter(SupplierProduct.supplier_website_id == website_id)
        return query.order_by(desc(SupplierProduct.created_at)).limit(limit).all()

    @staticmethod
    def get_in_stock_products(
        db: Session,
        website_id: Optional[int] = None,
        limit: int = 100,
        include_hidden: bool = False
    ) -> List[SupplierProduct]:
        """Get products currently in stock."""
        query = db.query(SupplierProduct).filter(SupplierProduct.in_stock == True)
        if not include_hidden:
            query = query.filter(SupplierProduct.is_hidden == False)
        if website_id:
            query = query.filter(SupplierProduct.supplier_website_id == website_id)
        return query.order_by(desc(SupplierProduct.last_seen_in_stock)).limit(limit).all()

    @staticmethod
    def create_scan_log(
        db: Session,
        website_id: int,
        status: str,
        products_found: int = 0,
        new_products: int = 0,
        restocked_products: int = 0,
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> SupplierScanLog:
        """Create a scan log entry."""
        now = datetime.now(ZoneInfo("Europe/Oslo"))
        started = started_at or now
        completed = completed_at or now

        log = SupplierScanLog(
            supplier_website_id=website_id,
            status=status,
            products_found=products_found,
            new_products=new_products,
            restocked_products=restocked_products,
            error_message=error_message,
            started_at=started,
            completed_at=completed,
            duration_seconds=(completed - started).total_seconds() if completed and started else None,
        )
        db.add(log)
        db.commit()
        db.refresh(log)

        # Update website last_scan_at
        website = db.query(SupplierWebsite).filter(SupplierWebsite.id == website_id).first()
        if website:
            website.last_scan_at = now
            db.commit()

        return log

    @staticmethod
    def get_scan_logs(
        db: Session,
        website_id: Optional[int] = None,
        limit: int = 50
    ) -> List[SupplierScanLog]:
        """Get scan logs."""
        query = db.query(SupplierScanLog)
        if website_id:
            query = query.filter(SupplierScanLog.supplier_website_id == website_id)
        return query.order_by(desc(SupplierScanLog.created_at)).limit(limit).all()

    @staticmethod
    def get_product_availability_history(
        db: Session,
        product_id: int,
        limit: int = 100
    ) -> List[SupplierAvailabilityHistory]:
        """Get availability history for a product."""
        return db.query(SupplierAvailabilityHistory).filter(
            SupplierAvailabilityHistory.supplier_product_id == product_id
        ).order_by(
            desc(SupplierAvailabilityHistory.recorded_at)
        ).limit(limit).all()
