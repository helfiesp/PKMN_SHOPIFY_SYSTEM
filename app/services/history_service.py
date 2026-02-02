"""Service for querying and managing price history data."""
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.models import (
    SnkrdunkPriceHistory,
    CompetitorPriceHistory,
    ProductPriceHistory,
    CompetitorProduct,
    SnkrdunkMapping,
    Variant,
    Product
)


class HistoryService:
    """Service for price history operations."""
    
    def get_available_history_dates(self, db: Session) -> Dict[str, List[str]]:
        """
        Get all available dates where historical data exists.
        
        Returns:
            {
                "competitor_dates": ["2026-01-29", "2026-01-28", ...],
                "snkrdunk_dates": ["2026-01-29", ...],
                "product_dates": ["2026-01-29", ...]
            }
        """
        # Get competitor history dates (CAST to date)
        competitor_dates = db.query(
            func.date(CompetitorPriceHistory.recorded_at).label("date")
        ).distinct().order_by(desc(func.date(CompetitorPriceHistory.recorded_at))).all()
        
        # Get SNKRDUNK history dates
        snkrdunk_dates = db.query(
            func.date(SnkrdunkPriceHistory.recorded_at).label("date")
        ).distinct().order_by(desc(func.date(SnkrdunkPriceHistory.recorded_at))).all()
        
        # Get product history dates
        product_dates = db.query(
            func.date(ProductPriceHistory.recorded_at).label("date")
        ).distinct().order_by(desc(func.date(ProductPriceHistory.recorded_at))).all()
        
        # Convert dates to ISO format strings, handling both date objects and strings
        def format_date(d):
            if not d:
                return None
            if isinstance(d, str):
                return d
            return d.isoformat() if hasattr(d, 'isoformat') else str(d)
        
        return {
            "competitor_dates": [format_date(d[0]) for d in competitor_dates],
            "snkrdunk_dates": [format_date(d[0]) for d in snkrdunk_dates],
            "product_dates": [format_date(d[0]) for d in product_dates]
        }
    
    def get_competitor_price_at_date(
        self,
        db: Session,
        competitor_product_id: int,
        date_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get competitor product price for a specific date.
        Returns the most recent price on that date.
        """
        target_date = datetime.fromisoformat(date_str).date()
        next_date = target_date + timedelta(days=1)
        
        history = db.query(CompetitorPriceHistory).filter(
            CompetitorPriceHistory.competitor_product_id == competitor_product_id,
            func.date(CompetitorPriceHistory.recorded_at) == target_date
        ).order_by(desc(CompetitorPriceHistory.recorded_at)).first()
        
        if not history:
            return None
        
        return {
            "competitor_product_id": history.competitor_product_id,
            "price_ore": history.price_ore,
            "stock_status": history.stock_status,
            "stock_amount": history.stock_amount,
            "recorded_at": history.recorded_at.isoformat()
        }
    
    def get_competitor_prices_at_date(
        self,
        db: Session,
        date_str: str
    ) -> List[Dict[str, Any]]:
        """
        Get all competitor products prices for a specific date.
        Returns the most recent price for each product on that date.
        """
        target_date = datetime.fromisoformat(date_str).date()
        
        # Get latest price per product on target date
        subquery = db.query(
            CompetitorPriceHistory.competitor_product_id,
            func.max(CompetitorPriceHistory.id).label("max_id")
        ).filter(
            func.date(CompetitorPriceHistory.recorded_at) == target_date
        ).group_by(CompetitorPriceHistory.competitor_product_id).subquery()
        
        histories = db.query(CompetitorPriceHistory).join(
            subquery,
            CompetitorPriceHistory.id == subquery.c.max_id
        ).all()
        
        return [
            {
                "competitor_product_id": h.competitor_product_id,
                "price_ore": h.price_ore,
                "stock_status": h.stock_status,
                "stock_amount": h.stock_amount,
                "recorded_at": h.recorded_at.isoformat(),
                "product_info": {
                    "website": h.competitor_product.website,
                    "normalized_name": h.competitor_product.normalized_name,
                    "category": h.competitor_product.category,
                    "brand": h.competitor_product.brand
                }
            }
            for h in histories
        ]
    
    def get_snkrdunk_price_at_date(
        self,
        db: Session,
        snkrdunk_key: str,
        date_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get SNKRDUNK product price for a specific date.
        Returns the most recent price on that date.
        """
        target_date = datetime.fromisoformat(date_str).date()
        
        history = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.snkrdunk_key == snkrdunk_key,
            func.date(SnkrdunkPriceHistory.recorded_at) == target_date
        ).order_by(desc(SnkrdunkPriceHistory.recorded_at)).first()
        
        if not history:
            return None
        
        return {
            "snkrdunk_key": history.snkrdunk_key,
            "price_jpy": history.price_jpy,
            "price_usd": history.price_usd,
            "recorded_at": history.recorded_at.isoformat()
        }
    
    def get_snkrdunk_prices_at_date(
        self,
        db: Session,
        date_str: str
    ) -> List[Dict[str, Any]]:
        """
        Get all SNKRDUNK products prices for a specific date.
        Returns the most recent price for each product on that date.
        """
        target_date = datetime.fromisoformat(date_str).date()
        
        # Get latest price per snkrdunk_key on target date
        subquery = db.query(
            SnkrdunkPriceHistory.snkrdunk_key,
            func.max(SnkrdunkPriceHistory.id).label("max_id")
        ).filter(
            func.date(SnkrdunkPriceHistory.recorded_at) == target_date
        ).group_by(SnkrdunkPriceHistory.snkrdunk_key).subquery()
        
        histories = db.query(SnkrdunkPriceHistory).join(
            subquery,
            SnkrdunkPriceHistory.id == subquery.c.max_id
        ).all()
        
        return [
            {
                "snkrdunk_key": h.snkrdunk_key,
                "price_jpy": h.price_jpy,
                "price_usd": h.price_usd,
                "recorded_at": h.recorded_at.isoformat()
            }
            for h in histories
        ]
    
    def get_product_price_at_date(
        self,
        db: Session,
        variant_id: int,
        date_str: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get product variant price for a specific date.
        Returns the most recent price on that date.
        """
        target_date = datetime.fromisoformat(date_str).date()
        
        history = db.query(ProductPriceHistory).filter(
            ProductPriceHistory.variant_id == variant_id,
            func.date(ProductPriceHistory.recorded_at) == target_date
        ).order_by(desc(ProductPriceHistory.recorded_at)).first()
        
        if not history:
            return None
        
        variant = db.query(Variant).filter(Variant.id == variant_id).first()
        product = db.query(Product).filter(Product.id == variant.product_id).first() if variant else None
        
        return {
            "variant_id": history.variant_id,
            "price": history.price,
            "compare_at_price": history.compare_at_price,
            "inventory_quantity": history.inventory_quantity,
            "recorded_at": history.recorded_at.isoformat(),
            "variant_info": {
                "title": variant.title,
                "sku": variant.sku
            } if variant else None,
            "product_info": {
                "title": product.title,
                "handle": product.handle
            } if product else None
        }
    
    def get_product_prices_at_date(
        self,
        db: Session,
        date_str: str
    ) -> List[Dict[str, Any]]:
        """
        Get all product variant prices for a specific date.
        Returns the most recent price for each variant on that date.
        """
        target_date = datetime.fromisoformat(date_str).date()
        
        # Get latest price per variant on target date
        subquery = db.query(
            ProductPriceHistory.variant_id,
            func.max(ProductPriceHistory.id).label("max_id")
        ).filter(
            func.date(ProductPriceHistory.recorded_at) == target_date
        ).group_by(ProductPriceHistory.variant_id).subquery()
        
        histories = db.query(ProductPriceHistory).join(
            subquery,
            ProductPriceHistory.id == subquery.c.max_id
        ).all()
        
        results = []
        for h in histories:
            variant = db.query(Variant).filter(Variant.id == h.variant_id).first()
            product = db.query(Product).filter(Product.id == variant.product_id).first() if variant else None
            
            results.append({
                "variant_id": h.variant_id,
                "price": h.price,
                "compare_at_price": h.compare_at_price,
                "inventory_quantity": h.inventory_quantity,
                "recorded_at": h.recorded_at.isoformat(),
                "variant_info": {
                    "title": variant.title,
                    "sku": variant.sku
                } if variant else None,
                "product_info": {
                    "title": product.title,
                    "handle": product.handle
                } if product else None
            })
        
        return results
    
    def get_snkrdunk_last_updated(self, db: Session, snkrdunk_key: str) -> Optional[str]:
        """
        Get the timestamp when a SNKRDUNK product price was last updated.
        """
        latest = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.snkrdunk_key == snkrdunk_key
        ).order_by(desc(SnkrdunkPriceHistory.recorded_at)).first()
        
        if not latest:
            return None
        
        return latest.recorded_at.isoformat()
    
    def get_competitor_last_updated(self, db: Session, competitor_product_id: int) -> Optional[str]:
        """
        Get the timestamp when a competitor product price was last updated.
        """
        latest = db.query(CompetitorPriceHistory).filter(
            CompetitorPriceHistory.competitor_product_id == competitor_product_id
        ).order_by(desc(CompetitorPriceHistory.recorded_at)).first()
        
        if not latest:
            return None
        
        return latest.recorded_at.isoformat()
    
    def get_product_last_updated(self, db: Session, variant_id: int) -> Optional[str]:
        """
        Get the timestamp when a product variant price was last updated.
        """
        latest = db.query(ProductPriceHistory).filter(
            ProductPriceHistory.variant_id == variant_id
        ).order_by(desc(ProductPriceHistory.recorded_at)).first()
        
        if not latest:
            return None
        
        return latest.recorded_at.isoformat()
    
    def get_price_history_timeline(
        self,
        db: Session,
        competitor_product_id: int,
        days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get price history timeline for a competitor product over N days.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        histories = db.query(CompetitorPriceHistory).filter(
            CompetitorPriceHistory.competitor_product_id == competitor_product_id,
            CompetitorPriceHistory.recorded_at >= cutoff
        ).order_by(CompetitorPriceHistory.recorded_at).all()
        
        return [
            {
                "date": h.recorded_at.isoformat(),
                "price_ore": h.price_ore,
                "stock_status": h.stock_status,
                "stock_amount": h.stock_amount
            }
            for h in histories
        ]
    
    def get_snkrdunk_price_timeline(
        self,
        db: Session,
        snkrdunk_key: str,
        days_back: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get price history timeline for a SNKRDUNK product over N days.
        Returns all price scans (not grouped by day) to show intraday price changes.
        """
        from datetime import datetime, timedelta, timezone
        
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
        
        # Get all price records for this product within the date range
        histories = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.snkrdunk_key == snkrdunk_key,
            SnkrdunkPriceHistory.recorded_at >= cutoff
        ).order_by(SnkrdunkPriceHistory.recorded_at).all()
        
        # Return all data points with timestamp
        return [
            {
                "timestamp": h.recorded_at.isoformat(),
                "date": h.recorded_at.date().isoformat(),
                "price_jpy": h.price_jpy,
                "scan_log_id": h.scan_log_id
            }
            for h in histories
        ]
