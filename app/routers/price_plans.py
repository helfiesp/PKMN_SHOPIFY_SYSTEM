"""Price plans router."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    PricePlanResponse,
    PricePlanSummary,
    GeneratePricePlanRequest,
    ApplyPlanRequest,
    ApplyPlanResponse
)
from app.services import price_plan_service

router = APIRouter()


@router.post("/generate", response_model=PricePlanResponse)
async def generate_price_plan(
    request: GeneratePricePlanRequest,
    db: Session = Depends(get_db)
):
    """
    Generate a new price update plan.
    
    Supports two strategies:
    - Normal: Generates plan based on SNKRDUNK data and current Shopify prices
    - Match Competition: Creates plan to match lowest competitor prices
    """
    try:
        # If strategy is match_competition, use pre-calculated items
        if request.strategy == 'match_competition' and request.items:
            plan = await price_plan_service.generate_price_plan_from_items(
                db=db,
                items=request.items,
                plan_type=request.plan_type
            )
        else:
            # Normal price plan generation
            plan = await price_plan_service.generate_price_plan(
                db=db,
                variant_type=request.variant_type,
                exchange_rate=request.exchange_rate,
                shipping_cost_jpy=request.shipping_cost_jpy or 500,
                min_margin_pct=request.min_margin_pct or 20.0,
                vat_pct=request.vat_pct or 25.0,
                pack_markup_pct=request.pack_markup_pct or 20.0,
                min_change_threshold=request.min_change_threshold or 5.0,
                plan_type=request.plan_type
            )
        return plan
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("", response_model=List[PricePlanSummary])
async def list_price_plans(
    status: Optional[str] = None,
    plan_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List all price plans."""
    plans = price_plan_service.get_plans(
        db=db,
        status=status,
        plan_type=plan_type,
        skip=skip,
        limit=limit
    )
    return plans


@router.get("/{plan_id}", response_model=PricePlanResponse)
async def get_price_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific price plan with all items."""
    plan = price_plan_service.get_plan_by_id(db=db, plan_id=plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Price plan not found")
    return plan


@router.post("/{plan_id}/apply", response_model=ApplyPlanResponse)
async def apply_price_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """
    Apply a price plan to Shopify.
    
    This replaces the apply functionality in shopify_price_updater_confirmed.py.
    Updates prices on Shopify and marks items as applied.
    """
    import sys
    print(f"[ROUTER] ========== APPLY ENDPOINT CALLED FOR PLAN {plan_id} ==========", flush=True)
    sys.stdout.flush()
    try:
        print(f"[ROUTER] About to call price_plan_service.apply_price_plan", flush=True)
        sys.stdout.flush()
        result = await price_plan_service.apply_price_plan(
            db=db,
            plan_id=plan_id
        )
        print(f"[ROUTER] Service returned result: {result}", flush=True)
        sys.stdout.flush()
        return result
    except Exception as e:
        print(f"[ROUTER] Exception caught: {e}", flush=True)
        sys.stdout.flush()
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{plan_id}")
async def delete_price_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Delete a price plan."""
    success = price_plan_service.delete_plan(db=db, plan_id=plan_id)
    if not success:
        raise HTTPException(status_code=404, detail="Price plan not found")
    return {"message": "Price plan deleted successfully"}


@router.post("/{plan_id}/verify")
async def verify_price_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Verify that prices were actually applied in Shopify."""
    try:
        result = await price_plan_service.verify_price_plan(
            db=db,
            plan_id=plan_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{plan_id}/cancel")
async def cancel_price_plan(
    plan_id: int,
    db: Session = Depends(get_db)
):
    """Cancel a pending price plan."""
    plan = price_plan_service.cancel_plan(db=db, plan_id=plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Price plan not found")
    return {"message": "Price plan cancelled", "plan_id": plan_id, "status": plan.status}
