"""Booster variant service - handles variant splitting logic."""
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models import BoosterVariantPlan, BoosterVariantPlanItem, Product, Variant
from app.config import settings


class BoosterVariantService:
    """Service for booster variant operations."""
    
    SPECIAL_PACK_COUNTS = [
        ("terastal festival", 10),
        ("mega dream", 10),
        ("vstar universe", 10),
        ("shiny treasure ex", 10),
        ("shiny treasure", 10),
        ("pokemon 151", 20),
        ("black bolt", 20),
        ("white flare", 20),
    ]
    
    async def generate_variant_plan(
        self,
        db: Session,
        collection_id: str
    ) -> BoosterVariantPlan:
        """
        Generate booster variant split plan.
        
        Replicates shopify_booster_variants.py plan generation logic.
        This is a stub - full implementation would:
        - Find products with single variant
        - Calculate box and pack prices
        - Create plan items
        """
        plan = BoosterVariantPlan(
            status="pending",
            generated_at=datetime.now(timezone.utc),
            collection_id=collection_id,
            packs_per_box_default=settings.default_packs_per_box,
            pack_markup=settings.pack_markup,
            special_pack_counts=self.SPECIAL_PACK_COUNTS,
            total_items=0
        )
        
        db.add(plan)
        db.flush()
        
        # TODO: Implement full plan generation
        # 1. Get products from collection (exclude "One Piece")
        # 2. Filter to products with single variant
        # 3. Calculate packs_per_box based on title
        # 4. Calculate pack price with markup
        # 5. Create BoosterVariantPlanItem for each
        
        db.commit()
        db.refresh(plan)
        
        return plan
    
    async def apply_variant_plan(
        self,
        db: Session,
        plan_id: int
    ) -> dict:
        """
        Apply variant plan to Shopify.
        
        Replicates shopify_booster_variants.py apply logic.
        """
        plan = db.query(BoosterVariantPlan).filter(
            BoosterVariantPlan.id == plan_id
        ).first()
        
        if not plan:
            raise ValueError("Plan not found")
        
        # TODO: Implement full apply logic
        # 1. productUpdate (if needed)
        # 2. productOptionUpdate (add "Type" option)
        # 3. productVariantsBulkUpdate (update existing to "Booster Box")
        # 4. productVariantsBulkCreate (create "Booster Pack" variant)
        # 5. Clean up "Default Title" option value
        
        plan.status = "applied"
        plan.applied_at = datetime.now(timezone.utc)
        db.commit()
        
        return {
            "plan_id": plan_id,
            "status": "applied",
            "applied_items": 0,
            "failed_items": 0,
            "errors": []
        }
    
    def get_plans(
        self,
        db: Session,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[BoosterVariantPlan]:
        """Get booster variant plans."""
        query = db.query(BoosterVariantPlan)
        
        if status:
            query = query.filter(BoosterVariantPlan.status == status)
        
        return query.order_by(BoosterVariantPlan.generated_at.desc()).offset(skip).limit(limit).all()
    
    def get_plan_by_id(self, db: Session, plan_id: int) -> Optional[BoosterVariantPlan]:
        """Get a specific plan."""
        return db.query(BoosterVariantPlan).filter(BoosterVariantPlan.id == plan_id).first()
    
    def delete_plan(self, db: Session, plan_id: int) -> bool:
        """Delete a plan."""
        plan = db.query(BoosterVariantPlan).filter(BoosterVariantPlan.id == plan_id).first()
        if plan:
            db.delete(plan)
            db.commit()
            return True
        return False


booster_variant_service = BoosterVariantService()
