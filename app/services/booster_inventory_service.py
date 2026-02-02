"""Booster inventory service - handles inventory splitting logic."""
from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models import BoosterInventoryPlan, BoosterInventoryPlanItem
from app.config import settings


class BoosterInventoryService:
    """Service for booster inventory operations."""
    
    async def generate_inventory_plan(
        self,
        db: Session,
        collection_id: str,
        location_id: Optional[str] = None
    ) -> BoosterInventoryPlan:
        """
        Generate booster inventory split plan.
        
        Replicates shopify_booster_inventory_split.py plan generation logic.
        """
        plan = BoosterInventoryPlan(
            status="pending",
            generated_at=datetime.now(timezone.utc),
            collection_id=collection_id,
            location_id=location_id or settings.location_id,
            location_name=settings.location_name,
            total_items=0
        )
        
        db.add(plan)
        db.flush()
        
        # TODO: Implement full plan generation
        # 1. Get products with Type=Booster Box and Type=Booster Pack
        # 2. Check inventory levels at location
        # 3. If Box available > 1, plan to move 1 box to packs
        # 4. Create BoosterInventoryPlanItem for each
        
        db.commit()
        db.refresh(plan)
        
        return plan
    
    async def apply_inventory_plan(
        self,
        db: Session,
        plan_id: int
    ) -> dict:
        """
        Apply inventory plan to Shopify.
        
        Replicates shopify_booster_inventory_split.py apply logic.
        """
        plan = db.query(BoosterInventoryPlan).filter(
            BoosterInventoryPlan.id == plan_id
        ).first()
        
        if not plan:
            raise ValueError("Plan not found")
        
        # TODO: Implement full apply logic
        # 1. Use inventoryAdjustQuantities mutation
        # 2. Decrease box by 1
        # 3. Increase pack by packs_per_box
        # 4. Mark items as applied
        
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
    ) -> List[BoosterInventoryPlan]:
        """Get booster inventory plans."""
        query = db.query(BoosterInventoryPlan)
        
        if status:
            query = query.filter(BoosterInventoryPlan.status == status)
        
        return query.order_by(BoosterInventoryPlan.generated_at.desc()).offset(skip).limit(limit).all()
    
    def get_plan_by_id(self, db: Session, plan_id: int) -> Optional[BoosterInventoryPlan]:
        """Get a specific plan."""
        return db.query(BoosterInventoryPlan).filter(BoosterInventoryPlan.id == plan_id).first()
    
    def delete_plan(self, db: Session, plan_id: int) -> bool:
        """Delete a plan."""
        plan = db.query(BoosterInventoryPlan).filter(BoosterInventoryPlan.id == plan_id).first()
        if plan:
            db.delete(plan)
            db.commit()
            return True
        return False


booster_inventory_service = BoosterInventoryService()
