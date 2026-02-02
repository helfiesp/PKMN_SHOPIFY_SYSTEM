"""Booster variants router."""
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    BoosterVariantPlanResponse,
    ApplyPlanResponse
)
from app.services import booster_variant_service

router = APIRouter()


@router.post("/generate-plan", response_model=BoosterVariantPlanResponse)
async def generate_booster_variant_plan(
    collection_id: str,
    db: Session = Depends(get_db)
):
    """
    Generate booster variant split plan.
    
    This replaces the plan generation in shopify_booster_variants.py.
    Identifies products that need to be split into Box + Pack variants.
    """
    try:
        plan = await booster_variant_service.generate_variant_plan(
            db=db,
            collection_id=collection_id
        )
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/plans", response_model=List[BoosterVariantPlanResponse])
async def list_booster_variant_plans(
    status: str = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all booster variant plans."""
    plans = booster_variant_service.get_plans(
        db=db,
        status=status,
        skip=skip,
        limit=limit
    )
    return plans


@router.get("/plans/{plan_id}", response_model=BoosterVariantPlanResponse)
async def get_booster_variant_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific booster variant plan."""
    plan = booster_variant_service.get_plan_by_id(db=db, plan_id=plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan


@router.post("/plans/{plan_id}/apply", response_model=ApplyPlanResponse)
async def apply_booster_variant_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Apply booster variant plan to Shopify.
    
    This replaces the apply functionality in shopify_booster_variants.py.
    Creates Box and Pack variants for products.
    """
    try:
        result = await booster_variant_service.apply_variant_plan(
            db=db,
            plan_id=plan_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/plans/{plan_id}")
async def delete_booster_variant_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Delete a booster variant plan."""
    success = booster_variant_service.delete_plan(db=db, plan_id=plan_id)
    if not success:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"message": "Plan deleted successfully"}
