"""Purchase orders router."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderSummary,
)
from app.services.purchase_order_service import purchase_order_service

router = APIRouter()


@router.post("")
async def create_purchase_order(
    request: PurchaseOrderCreate,
    db: Session = Depends(get_db),
):
    """Create a new purchase order and update Shopify inventory."""
    try:
        result = await purchase_order_service.create_purchase_order(
            db=db,
            order_date=request.order_date,
            shipping_cost_jpy=request.shipping_cost_jpy,
            total_nok=request.total_nok,
            notes=request.notes,
            items=[item.model_dump() for item in request.items],
        )
        po = result["purchase_order"]
        return {
            "id": po.id,
            "order_date": po.order_date,
            "shipping_cost_jpy": po.shipping_cost_jpy,
            "total_nok": po.total_nok,
            "fx_rate_snapshot": po.fx_rate_snapshot,
            "status": po.status,
            "notes": po.notes,
            "created_at": po.created_at,
            "updated_at": po.updated_at,
            "items": [
                {
                    "id": i.id,
                    "purchase_order_id": i.purchase_order_id,
                    "variant_id": i.variant_id,
                    "quantity": i.quantity,
                    "price_jpy": i.price_jpy,
                    "product_title": i.product_title,
                    "variant_title": i.variant_title,
                    "sku": i.sku,
                    "created_at": i.created_at,
                }
                for i in po.items
            ],
            "total_items": len(po.items),
            "total_quantity": sum(i.quantity for i in po.items),
            "total_jpy": sum(i.price_jpy * i.quantity for i in po.items),
            "inventory_results": result["inventory_results"],
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def list_purchase_orders(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List all purchase orders with summaries."""
    return purchase_order_service.get_purchase_orders(
        db=db, status=status, skip=skip, limit=limit,
    )


@router.get("/{po_id}")
async def get_purchase_order(po_id: int, db: Session = Depends(get_db)):
    """Get a single purchase order with all line items."""
    po = purchase_order_service.get_purchase_order(db=db, po_id=po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return {
        "id": po.id,
        "order_date": po.order_date,
        "shipping_cost_jpy": po.shipping_cost_jpy,
        "total_nok": po.total_nok,
        "fx_rate_snapshot": po.fx_rate_snapshot,
        "status": po.status,
        "notes": po.notes,
        "created_at": po.created_at,
        "updated_at": po.updated_at,
        "items": [
            {
                "id": i.id,
                "purchase_order_id": i.purchase_order_id,
                "variant_id": i.variant_id,
                "quantity": i.quantity,
                "price_jpy": i.price_jpy,
                "product_title": i.product_title,
                "variant_title": i.variant_title,
                "sku": i.sku,
                "created_at": i.created_at,
            }
            for i in po.items
        ],
    }


@router.post("/{po_id}/cancel")
async def cancel_purchase_order(
    po_id: int,
    revert_inventory: bool = False,
    db: Session = Depends(get_db),
):
    """Cancel a purchase order, optionally reverting inventory."""
    try:
        return await purchase_order_service.cancel_purchase_order(
            db=db, po_id=po_id, revert_inventory=revert_inventory,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
