"""Booster inventory router."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    BoosterInventoryPlanResponse,
    ApplyPlanResponse
)
from app.services import booster_inventory_service

router = APIRouter()


@router.post("/generate-plan", response_model=BoosterInventoryPlanResponse)
async def generate_booster_inventory_plan(
    collection_id: str,
    location_id: str = None,
    db: Session = Depends(get_db)
):
    """
    Generate booster inventory split plan.
    
    This replaces the plan generation in shopify_booster_inventory_split.py.
    Identifies products where box inventory can be converted to pack inventory.
    """
    try:
        plan = await booster_inventory_service.generate_inventory_plan(
            db=db,
            collection_id=collection_id,
            location_id=location_id
        )
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans", response_model=List[BoosterInventoryPlanResponse])
async def list_booster_inventory_plans(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all booster inventory plans."""
    plans = booster_inventory_service.get_plans(
        db=db,
        status=status,
        skip=skip,
        limit=limit
    )
    return plans


@router.get("/plans/{plan_id}", response_model=BoosterInventoryPlanResponse)
async def get_booster_inventory_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific booster inventory plan."""
    plan = booster_inventory_service.get_plan_by_id(db=db, plan_id=plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/plans/{plan_id}/apply", response_model=ApplyPlanResponse)
async def apply_booster_inventory_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Apply booster inventory plan to Shopify.
    
    This replaces the apply functionality in shopify_booster_inventory_split.py.
    Adjusts inventory levels on Shopify.
    """
    try:
        result = await booster_inventory_service.apply_inventory_plan(
            db=db,
            plan_id=plan_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/plans/{plan_id}")
async def delete_booster_inventory_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Delete a booster inventory plan."""
    success = booster_inventory_service.delete_plan(db=db, plan_id=plan_id)
    if not success:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"message": "Plan deleted successfully"}
