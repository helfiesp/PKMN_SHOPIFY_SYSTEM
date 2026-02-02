"""Competitor product service for analyzing competitor pricing and availability."""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import statistics
from sqlalchemy import or_

from app.models import (
    CompetitorProduct, 
    CompetitorProductDaily,
    CompetitorProductSnapshot,
    CompetitorProductOverride,
    today_oslo
)
from app.config import settings
from competition.normalize import normalize_name, detect_category, detect_brand, detect_language
from competition.canonicalize import canonicalize_normalized_name
from competition.pipeline import _apply_overrides


class CompetitorService:
    """Service for managing competitor data."""
    
    def get_competitor_products(
        self,
        db: Session,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        website: Optional[str] = None,
        limit: int = 1000
    ) -> List[CompetitorProduct]:
        """Get competitor products with optional filters."""
        query = db.query(CompetitorProduct)
        
        if category:
            query = query.filter(CompetitorProduct.category == category)
        if brand:
            query = query.filter(CompetitorProduct.brand == brand)
        if website:
            query = query.filter(CompetitorProduct.website == website)
        
        return query.limit(limit).all()
    
    def get_product_by_canonical_name(
        self,
        db: Session,
        normalized_name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None
    ) -> List[CompetitorProduct]:
        """Find all competitor products matching a canonical product name."""
        query = db.query(CompetitorProduct).filter(
            CompetitorProduct.normalized_name == normalized_name
        )
        
        if category:
            query = query.filter(CompetitorProduct.category == category)
        if brand:
            query = query.filter(CompetitorProduct.brand == brand)
        
        return query.all()
    
    def get_price_statistics(
        self,
        db: Session,
        normalized_name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        days_back: int = 7
    ) -> Dict[str, Any]:
        """
        Get price statistics for a product across competitors.
        
        Returns: {
            'min_price_nok': float,
            'max_price_nok': float,
            'avg_price_nok': float,
            'median_price_nok': float,
            'num_competitors': int,
            'prices_by_website': {'website': price_nok, ...}
        }
        """
        products = self.get_product_by_canonical_name(
            db, normalized_name, category, brand
        )
        
        if not products:
            return {
                'min_price_nok': 0,
                'max_price_nok': 0,
                'avg_price_nok': 0,
                'median_price_nok': 0,
                'num_competitors': 0,
                'prices_by_website': {}
            }
        
        prices_nok = []
        prices_by_website = {}
        
        # Get latest price for each product
        for product in products:
            # Try to get today's snapshot first
            today = today_oslo()
            daily = db.query(CompetitorProductDaily).filter(
                CompetitorProductDaily.competitor_product_id == product.id,
                CompetitorProductDaily.day == today
            ).first()
            
            # Fall back to most recent snapshot
            if not daily:
                daily = db.query(CompetitorProductDaily).filter(
                    CompetitorProductDaily.competitor_product_id == product.id
                ).order_by(CompetitorProductDaily.day.desc()).first()
            
            price_ore = None
            if daily and daily.price:
                try:
                    # Parse price if it's a string
                    price_ore = int(daily.price) if isinstance(daily.price, (int, str)) else daily.price
                except:
                    price_ore = product.price_ore
            else:
                price_ore = product.price_ore
            
            if price_ore:
                price_nok = price_ore / 100  # Convert øre to NOK
                prices_nok.append(price_nok)
                prices_by_website[product.website] = price_nok
        
        if not prices_nok:
            return {
                'min_price_nok': 0,
                'max_price_nok': 0,
                'avg_price_nok': 0,
                'median_price_nok': 0,
                'num_competitors': 0,
                'prices_by_website': {}
            }
        
        return {
            'min_price_nok': min(prices_nok),
            'max_price_nok': max(prices_nok),
            'avg_price_nok': statistics.mean(prices_nok),
            'median_price_nok': statistics.median(prices_nok),
            'num_competitors': len(prices_nok),
            'prices_by_website': prices_by_website
        }
    
    def get_average_competitor_price_nok(
        self,
        db: Session,
        normalized_name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None
    ) -> float:
        """Get average competitor price for a product in NOK."""
        stats = self.get_price_statistics(db, normalized_name, category, brand)
        return stats.get('avg_price_nok', 0)
    
    def get_competitor_products_by_category(
        self,
        db: Session,
        category: str,
        brand: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all competitor products in a category with price stats."""
        products = self.get_competitor_products(
            db, category=category, brand=brand, limit=5000
        )
        
        # Group by normalized name and get stats for each
        by_name = {}
        for product in products:
            name = product.normalized_name or product.raw_name
            if name not in by_name:
                by_name[name] = {
                    'normalized_name': product.normalized_name,
                    'raw_names': set(),
                    'category': product.category,
                    'brand': product.brand,
                    'products': []
                }
            by_name[name]['raw_names'].add(product.raw_name)
            by_name[name]['products'].append(product)
        
        # Build results with stats
        results = []
        for name, data in by_name.items():
            stats = self.get_price_statistics(
                db, name, category, brand
            )
            results.append({
                'normalized_name': name,
                'raw_names': list(data['raw_names']),
                'category': data['category'],
                'brand': data['brand'],
                'num_products': len(data['products']),
                'price_stats': stats
            })
        
        return sorted(results, key=lambda x: x['price_stats']['avg_price_nok'], reverse=True)
    
    def create_override(
        self,
        db: Session,
        normalized_name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        language: Optional[str] = None,
        website: Optional[str] = None,
        notes: Optional[str] = None
    ) -> CompetitorProductOverride:
        """Create or update a competitor product override."""
        override = db.query(CompetitorProductOverride).filter(
            CompetitorProductOverride.normalized_name == normalized_name,
            CompetitorProductOverride.website == website
        ).first()
        
        if override:
            if category is not None:
                override.category = category
            if brand is not None:
                override.brand = brand
            if language is not None:
                override.language = language
            if notes is not None:
                override.notes = notes
            override.updated_at = datetime.now(timezone.utc)
        else:
            override = CompetitorProductOverride(
                normalized_name=normalized_name,
                category=category,
                brand=brand,
                language=language,
                website=website,
                notes=notes
            )
            db.add(override)
        
        db.commit()
        db.refresh(override)
        return override

    def reprocess_competitor_products(
        self,
        db: Session,
        website: Optional[str] = None,
        only_missing: bool = False,
        remove_non_pokemon: bool = False,
    ) -> Dict[str, int]:
        """Recompute category/brand/language/normalized_name for competitor products."""
        query = db.query(CompetitorProduct)
        if website:
            query = query.filter(CompetitorProduct.website == website)
        if only_missing:
            query = query.filter(
                or_(
                    CompetitorProduct.normalized_name.is_(None),
                    CompetitorProduct.category.is_(None),
                    CompetitorProduct.brand.is_(None),
                    CompetitorProduct.language.is_(None),
                )
            )

        products = query.all()
        updated = 0
        removed = 0

        banned_keywords = [
            "one piece",
            "pokemon center",
            "naruto",
        ]

        for product in products:
            raw_name = (product.raw_name or "").strip() or "(unknown)"
            website_key = (product.website or "").strip()

            raw_lower = raw_name.lower()
            if remove_non_pokemon:
                if any(k in raw_lower for k in banned_keywords):
                    db.delete(product)
                    removed += 1
                    continue

            brand = detect_brand(raw_name) or None
            category = detect_category(raw_name) or None
            language = detect_language(raw_name) or "en"

            normalized = normalize_name(raw_name) or None
            if normalized:
                normalized = canonicalize_normalized_name(db, normalized, category=category)

            category, brand, language = _apply_overrides(
                db,
                website=website_key,
                normalized_name=normalized,
                category=category,
                brand=brand,
                language=language,
            )

            if remove_non_pokemon and brand and brand != "pokemon":
                db.delete(product)
                removed += 1
                continue

            changed = False
            if only_missing:
                if not product.normalized_name and product.normalized_name != normalized:
                    product.normalized_name = normalized
                    changed = True
                if not product.category and product.category != category:
                    product.category = category
                    changed = True
                if not product.brand and product.brand != brand:
                    product.brand = brand
                    changed = True
                if not product.language and product.language != language:
                    product.language = language
                    changed = True
            else:
                if product.normalized_name != normalized:
                    product.normalized_name = normalized
                    changed = True
                if product.category != category:
                    product.category = category
                    changed = True
                if product.brand != brand:
                    product.brand = brand
                    changed = True
                if product.language != language:
                    product.language = language
                    changed = True

            if changed:
                updated += 1

        if updated or removed:
            db.commit()

        return {"total": len(products), "updated": updated, "removed": removed}
    
    def get_availability_status(
        self,
        db: Session,
        normalized_name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get availability status across competitors."""
        products = self.get_product_by_canonical_name(
            db, normalized_name, category, brand
        )
        
        in_stock = 0
        out_of_stock = 0
        by_website = {}
        
        today = today_oslo()
        for product in products:
            daily = db.query(CompetitorProductDaily).filter(
                CompetitorProductDaily.competitor_product_id == product.id,
                CompetitorProductDaily.day == today
            ).first()
            
            status = daily.stock_status if daily else product.stock_status
            stock_amount = daily.stock_amount if daily else product.stock_amount
            
            by_website[product.website] = {
                'status': status,
                'amount': stock_amount
            }
            
            if status and 'i lager' in status.lower():
                in_stock += 1
            else:
                out_of_stock += 1
        
        return {
            'in_stock_count': in_stock,
            'out_of_stock_count': out_of_stock,
            'by_website': by_website
        }


# Create singleton instance
competitor_service = CompetitorService()
