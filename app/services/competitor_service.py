"""Competitor product service for analyzing competitor pricing and availability."""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone, date, timedelta
import statistics
from sqlalchemy import or_, desc

from app.models import (
    CompetitorProduct, 
    CompetitorProductDaily,
    CompetitorProductSnapshot,
    CompetitorProductOverride,
    CompetitorSalesVelocity,
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
    
    def calculate_sales_velocity(
        self,
        db: Session,
        competitor_product_id: int,
        days_back: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate sales velocity metrics for a competitor product.
        Analyzes stock changes over time to estimate sales rate.
        """
        from datetime import date, timedelta
        
        cutoff_date = date.today() - timedelta(days=days_back)
        
        # Get all daily snapshots for this product in the period
        snapshots = db.query(CompetitorProductDaily).filter(
            CompetitorProductDaily.competitor_product_id == competitor_product_id,
            CompetitorProductDaily.day >= cutoff_date.isoformat()
        ).order_by(CompetitorProductDaily.day).all()
        
        if len(snapshots) < 2:
            return {
                'insufficient_data': True,
                'days_tracked': len(snapshots),
                'avg_daily_sales': 0,
                'total_units_sold': 0,
                'total_units_restocked': 0,
                'weekly_sales_estimate': 0,
                'days_until_sellout': None,
                'times_restocked': 0,
                'times_sold_out': 0,
                'sell_through_rate': 0,
                'current_stock': snapshots[-1].stock_amount if snapshots else 0
            }
        
        # Track changes
        total_sold = 0
        total_restocked = 0
        times_restocked = 0
        times_sold_out = 0
        days_in_stock = 0
        days_out_of_stock = 0
        stock_levels = []
        price_when_high_velocity = None
        max_velocity = 0
        
        for i in range(1, len(snapshots)):
            prev = snapshots[i-1]
            curr = snapshots[i]
            
            prev_stock = prev.stock_amount or 0
            curr_stock = curr.stock_amount or 0
            
            stock_levels.append(curr_stock)
            
            # Track availability
            is_in_stock = curr_stock > 0
            if is_in_stock:
                days_in_stock += 1
            else:
                days_out_of_stock += 1
                times_sold_out += 1 if prev_stock > 0 else 0
            
            # Calculate stock delta
            stock_delta = curr_stock - prev_stock
            
            if stock_delta < 0:
                # Stock decreased - items were sold
                total_sold += abs(stock_delta)
                
                # Track velocity at this point
                daily_velocity = abs(stock_delta)
                if daily_velocity > max_velocity:
                    max_velocity = daily_velocity
                    try:
                        # Parse price
                        price_str = curr.price or "0"
                        if ',' in price_str or '.' in price_str:
                            price_str = price_str.replace(',', '.').replace(' ', '')
                            price_str = ''.join(c for c in price_str if c.isdigit() or c == '.')
                            price_when_high_velocity = float(price_str) if price_str else None
                        else:
                            price_str = ''.join(c for c in price_str if c.isdigit())
                            price_when_high_velocity = (float(price_str) / 100.0) if price_str else None
                    except:
                        pass
                        
            elif stock_delta > 0:
                # Stock increased - restock occurred
                total_restocked += stock_delta
                times_restocked += 1
        
        # Calculate metrics
        days_tracked = len(snapshots) - 1
        avg_daily_sales = total_sold / days_tracked if days_tracked > 0 else 0
        weekly_sales_estimate = avg_daily_sales * 7
        
        current_stock = snapshots[-1].stock_amount or 0
        days_until_sellout = (current_stock / avg_daily_sales) if avg_daily_sales > 0 else None
        
        # Sell-through rate (percentage of inventory sold)
        max_stock = max(stock_levels) if stock_levels else 0
        sell_through_rate = (total_sold / max_stock * 100) if max_stock > 0 else 0
        
        return {
            'insufficient_data': False,
            'days_tracked': days_tracked,
            'avg_daily_sales': round(avg_daily_sales, 2),
            'total_units_sold': total_sold,
            'total_units_restocked': total_restocked,
            'weekly_sales_estimate': round(weekly_sales_estimate, 1),
            'days_until_sellout': round(days_until_sellout, 1) if days_until_sellout else None,
            'times_restocked': times_restocked,
            'times_sold_out': times_sold_out,
            'sell_through_rate': round(sell_through_rate, 1),
            'current_stock': current_stock,
            'days_in_stock': days_in_stock,
            'days_out_of_stock': days_out_of_stock,
            'price_at_peak_velocity': price_when_high_velocity,
            'peak_daily_velocity': max_velocity
        }


# Create singleton instance
competitor_service = CompetitorService()
