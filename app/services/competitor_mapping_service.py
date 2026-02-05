"""Service for mapping competitor products to Shopify and SNKRDUNK products."""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.models import (
    CompetitorProduct,
    CompetitorProductMapping,
    Product,
    Variant,
    SnkrdunkMapping,
)
from app.services.competitor_service import competitor_service


class CompetitorMappingService:
    """Service for mapping competitor products to internal products."""
    
    def find_matching_shopify_product(
        self,
        db: Session,
        normalized_name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None
    ) -> Optional[Product]:
        """Find matching Shopify product by normalized name and category."""
        # Build query based on title matching
        query = db.query(Product)
        
        # Search in product title
        search_terms = normalized_name.lower().split()
        filters = [Product.title.ilike(f"%{term}%") for term in search_terms if len(term) > 2]
        
        if filters:
            query = query.filter(or_(*filters))
        
        products = query.all()
        
        if not products:
            return None
        
        # If only one match, return it
        if len(products) == 1:
            return products[0]
        
        # If multiple matches, try to find the best one
        # Prefer exact substring matches of the full normalized name
        for product in products:
            if normalized_name.lower() in product.title.lower():
                return product
        
        # Return first match as fallback
        return products[0] if products else None
    
    def find_matching_snkrdunk_product(
        self,
        db: Session,
        normalized_name: str,
        category: Optional[str] = None,
        brand: Optional[str] = None
    ) -> Optional[SnkrdunkMapping]:
        """Find matching SNKRDUNK product by normalized name."""
        # Search SNKRDUNK mappings
        search_terms = normalized_name.lower().split()
        
        query = db.query(SnkrdunkMapping)
        
        filters = [SnkrdunkMapping.snkrdunk_product_name.ilike(f"%{term}%") for term in search_terms if len(term) > 2]
        
        if filters:
            query = query.filter(or_(*filters))
        
        mappings = query.all()
        
        if not mappings:
            return None
        
        if len(mappings) == 1:
            return mappings[0]
        
        # Prefer exact substring matches
        for mapping in mappings:
            if normalized_name.lower() in mapping.snkrdunk_product_name.lower():
                return mapping
        
        return mappings[0] if mappings else None
    
    def map_competitor_to_shopify(
        self,
        db: Session,
        competitor_id: int,
        shopify_product_id: int
    ) -> Dict[str, Any]:
        """
        Manually map a competitor product to a Shopify product.
        This stores the mapping information in the competitor product.
        """
        competitor = db.query(CompetitorProduct).filter(
            CompetitorProduct.id == competitor_id
        ).first()
        
        if not competitor:
            raise ValueError(f"Competitor product {competitor_id} not found")
        
        shopify_product = db.query(Product).filter(
            Product.id == shopify_product_id
        ).first()
        
        if not shopify_product:
            raise ValueError(f"Shopify product {shopify_product_id} not found")
        
        mapping = db.query(CompetitorProductMapping).filter(
            CompetitorProductMapping.competitor_product_id == competitor_id
        ).first()

        if not mapping:
            mapping = CompetitorProductMapping(
                competitor_product_id=competitor_id,
                shopify_product_id=shopify_product_id
            )
            db.add(mapping)
        else:
            mapping.shopify_product_id = shopify_product_id

        db.commit()
        db.refresh(mapping)

        return {
            "competitor_product_id": competitor_id,
            "competitor_name": competitor.raw_name,
            "shopify_product_id": shopify_product_id,
            "shopify_product_name": shopify_product.title,
            "mapped": True
        }
    
    def map_competitor_to_snkrdunk(
        self,
        db: Session,
        competitor_id: int,
        snkrdunk_mapping_id: int
    ) -> Dict[str, Any]:
        """
        Manually map a competitor product to a SNKRDUNK product.
        """
        competitor = db.query(CompetitorProduct).filter(
            CompetitorProduct.id == competitor_id
        ).first()
        
        if not competitor:
            raise ValueError(f"Competitor product {competitor_id} not found")
        
        snkrdunk = db.query(SnkrdunkMapping).filter(
            SnkrdunkMapping.id == snkrdunk_mapping_id
        ).first()
        
        if not snkrdunk:
            raise ValueError(f"SNKRDUNK mapping {snkrdunk_mapping_id} not found")
        
        mapping = db.query(CompetitorProductMapping).filter(
            CompetitorProductMapping.competitor_product_id == competitor_id
        ).first()

        if not mapping:
            mapping = CompetitorProductMapping(
                competitor_product_id=competitor_id,
                snkrdunk_mapping_id=snkrdunk_mapping_id
            )
            db.add(mapping)
        else:
            mapping.snkrdunk_mapping_id = snkrdunk_mapping_id

        db.commit()
        db.refresh(mapping)

        return {
            "competitor_product_id": competitor_id,
            "competitor_name": competitor.raw_name,
            "snkrdunk_mapping_id": snkrdunk_mapping_id,
            "snkrdunk_product_name": snkrdunk.handle,
            "mapped": True
        }
    
    def get_unmapped_competitors(
        self,
        db: Session,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get competitor products that haven't been mapped to Shopify products."""
        competitors = competitor_service.get_competitor_products(
            db, category=category, brand=brand, limit=limit
        )
        
        unmapped = []
        for competitor in competitors:
            existing_mapping = db.query(CompetitorProductMapping).filter(
                CompetitorProductMapping.competitor_product_id == competitor.id
            ).first()
            if existing_mapping and existing_mapping.shopify_product_id:
                continue

            # Check if has shopify mapping
            shopify_match = self.find_matching_shopify_product(
                db, 
                competitor.normalized_name or competitor.raw_name,
                competitor.category,
                competitor.brand
            )
            
            snkrdunk_match = self.find_matching_snkrdunk_product(
                db,
                competitor.normalized_name or competitor.raw_name,
                competitor.category,
                competitor.brand
            )
            
            unmapped.append({
                "competitor_id": competitor.id,
                "competitor_name": competitor.raw_name,
                "normalized_name": competitor.normalized_name,
                "category": competitor.category,
                "brand": competitor.brand,
                "website": competitor.website,
                "price_nok": competitor.price_ore / 100 if competitor.price_ore else 0,
                "suggested_shopify_match": {
                    "id": shopify_match.id,
                    "title": shopify_match.title
                } if shopify_match else None,
                "suggested_snkrdunk_match": {
                    "id": snkrdunk_match.id,
                    "name": snkrdunk_match.snkrdunk_product_name
                } if snkrdunk_match else None
            })
        
        return unmapped

    def get_mapped_competitors(
        self,
        db: Session,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """Get mapped competitor products with Shopify details, grouped by Shopify product."""
        from sqlalchemy.orm import aliased
        
        # Use aliased tables to avoid conflicts
        DirectProduct = aliased(Product)
        SnkrdunkProduct = aliased(Product)
        
        rows = (
            db.query(CompetitorProductMapping, CompetitorProduct, DirectProduct, SnkrdunkMapping, SnkrdunkProduct)
            .join(CompetitorProduct, CompetitorProductMapping.competitor_product_id == CompetitorProduct.id)
            .outerjoin(DirectProduct, CompetitorProductMapping.shopify_product_id == DirectProduct.id)
            .outerjoin(SnkrdunkMapping, CompetitorProductMapping.snkrdunk_mapping_id == SnkrdunkMapping.id)
            .outerjoin(SnkrdunkProduct, SnkrdunkMapping.product_shopify_id == SnkrdunkProduct.shopify_id)
            .order_by(CompetitorProductMapping.updated_at.desc())
            .limit(limit)
            .all()
        )

        # Group by Shopify product
        grouped = {}
        for mapping, competitor, direct_prod, snkrdunk, snkrdunk_prod in rows:
            final_product = direct_prod or snkrdunk_prod
            
            # Use product title as key, or "Unmapped" if no product
            product_key = f"{final_product.title}|{final_product.id}" if final_product else "unmapped"
            
            if product_key not in grouped:
                variants_data = []
                if final_product and final_product.variants:
                    variants_data = [{"id": v.id, "price": float(v.price), "inventory_quantity": v.inventory_quantity or 0} for v in final_product.variants]
                
                grouped[product_key] = {
                    "shopify_product_id": final_product.id if final_product else None,
                    "shopify_product_title": final_product.title if final_product else "Unmapped",
                    "shopify_product_handle": final_product.handle if final_product else None,
                    "shopify_variants": variants_data,
                    "competitors": []
                }
            
            # Add competitor to this product's list
            grouped[product_key]["competitors"].append({
                "mapping_id": mapping.id,
                "competitor_product_id": competitor.id,
                "competitor_name": competitor.raw_name,
                "competitor_normalized": competitor.normalized_name,
                "competitor_website": competitor.website,
                "competitor_price_ore": competitor.price_ore,
                "competitor_link": competitor.product_link,
                "competitor_stock": competitor.stock_status,
                "competitor_stock_amount": competitor.stock_amount,
                "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
            })

        # Convert grouped dict to list
        results = list(grouped.values())
        return results
    
    def get_competitive_price_comparison(
        self,
        db: Session,
        shopify_product_id: int
    ) -> Dict[str, Any]:
        """
        Get price comparison between a Shopify product and competitors.
        """
        shopify_product = db.query(Product).filter(
            Product.id == shopify_product_id
        ).first()
        
        if not shopify_product:
            raise ValueError(f"Shopify product {shopify_product_id} not found")
        
        # Get our current price (use first variant as reference)
        our_price_nok = None
        if shopify_product.variants:
            our_price_nok = shopify_product.variants[0].price
        
        # Find competitor prices for this product
        competitors = competitor_service.get_price_statistics(
            db, 
            shopify_product.title,
            None,
            None
        )
        
        return {
            "shopify_product_id": shopify_product_id,
            "shopify_product_name": shopify_product.title,
            "our_price_nok": our_price_nok,
            "competitor_prices": competitors,
            "price_position": self._calculate_price_position(
                our_price_nok,
                competitors.get('prices_by_website', {})
            )
        }
    
    def _calculate_price_position(self, our_price: Optional[float], competitor_prices: Dict[str, float]) -> str:
        """Calculate whether we're underpriced, competitive, or overpriced."""
        if not our_price or not competitor_prices:
            return "unknown"
        
        prices = list(competitor_prices.values())
        if not prices:
            return "unknown"
        
        avg_competitor = sum(prices) / len(prices)
        
        if our_price < avg_competitor * 0.95:
            return "underpriced"
        elif our_price > avg_competitor * 1.10:
            return "overpriced"
        else:
            return "competitive"
    
    def jaccard_similarity(self, s1: str, s2: str) -> float:
        """Calculate Jaccard similarity between two strings (word-level)."""
        set1 = set(s1.lower().split())
        set2 = set(s2.lower().split())
        
        if not set1 or not set2:
            return 0.0
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
    
    def auto_map_competitors(self, db: Session) -> Dict[str, Any]:
        """Automatically map unmapped competitors to Shopify booster_box products."""
        # Get all unmapped competitor products (ones with no mapping record)
        unmapped = db.query(CompetitorProduct).outerjoin(
            CompetitorProductMapping,
            CompetitorProduct.id == CompetitorProductMapping.competitor_product_id
        ).filter(
            CompetitorProductMapping.id.is_(None),
            CompetitorProduct.category == 'booster_box'  # Only map booster boxes
        ).all()
        
        # Get all Shopify products (not SNKRDUNK) to match against
        # Note: Status is uppercase in database (ACTIVE, not active)
        shopify_products = db.query(Product).filter(
            Product.status == 'ACTIVE'
        ).all()
        
        mapped_count = 0
        failed_count = 0
        results = []
        
        for competitor_product in unmapped:
            best_match = None
            best_similarity = 0.0
            best_field = None  # Track which field had best match
            
            # Use normalized name for matching
            competitor_name = (competitor_product.normalized_name or competitor_product.raw_name or '').lower().strip()
            
            if not competitor_name:
                failed_count += 1
                results.append({
                    "competitor_id": competitor_product.id,
                    "competitor_name": competitor_product.raw_name,
                    "status": "no_match",
                    "error": "Empty competitor name"
                })
                continue
            
            # Try to match against Shopify products
            for shopify_product in shopify_products:
                # Try multiple fields: title, handle (both common sources for product names)
                fields_to_check = [
                    shopify_product.title,
                    shopify_product.handle
                ]
                
                for field_value in fields_to_check:
                    if not field_value:
                        continue
                    
                    shopify_name = field_value.lower().strip()
                    similarity = self.jaccard_similarity(competitor_name, shopify_name)
                    
                    # Keep track of best match (no minimum threshold initially)
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_match = shopify_product
                        best_field = field_value
            
            # If we found a match with >20% similarity, create mapping
            if best_match and best_similarity >= 0.2:
                try:
                    mapping = CompetitorProductMapping(
                        competitor_product_id=competitor_product.id,
                        shopify_product_id=best_match.id
                    )
                    db.add(mapping)
                    mapped_count += 1
                    results.append({
                        "competitor_id": competitor_product.id,
                        "competitor_name": competitor_product.raw_name,
                        "shopify_name": best_match.title,
                        "shopify_handle": best_match.handle,
                        "matched_field": best_field,
                        "similarity": round(best_similarity, 3),
                        "status": "mapped"
                    })
                except Exception as e:
                    failed_count += 1
                    results.append({
                        "competitor_id": competitor_product.id,
                        "competitor_name": competitor_product.raw_name,
                        "status": "failed",
                        "error": str(e)
                    })
            else:
                failed_count += 1
                results.append({
                    "competitor_id": competitor_product.id,
                    "competitor_name": competitor_product.raw_name,
                    "best_similarity": round(best_similarity, 3) if best_match else 0,
                    "status": "no_match"
                })
        
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise
        
        return {
            "total_unmapped": len(unmapped),
            "mapped": mapped_count,
            "failed": failed_count,
            "results": results
        }


# Create singleton instance
competitor_mapping_service = CompetitorMappingService()
