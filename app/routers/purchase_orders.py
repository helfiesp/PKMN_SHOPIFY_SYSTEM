"""Purchase orders router."""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.config import settings as app_settings
from app.schemas import (
    PurchaseOrderCreate,
    PurchaseOrderResponse,
    PurchaseOrderSummary,
)
from app.services.purchase_order_service import purchase_order_service

router = APIRouter()


def _serialize_item(i):
    return {
        "id": i.id,
        "purchase_order_id": i.purchase_order_id,
        "variant_id": i.variant_id,
        "quantity": i.quantity,
        "price_jpy": i.price_jpy,
        "weight_grams": i.weight_grams,
        "product_title": i.product_title,
        "variant_title": i.variant_title,
        "sku": i.sku,
        "product_shopify_id": i.product_shopify_id,
        "created_at": i.created_at,
    }


def _get_store_name():
    """Extract store name from Shopify shop domain for admin URLs."""
    shop = app_settings.get_shopify_shop()
    if shop:
        return shop.replace(".myshopify.com", "")
    return None


def _serialize_po(po, extras=None):
    data = {
        "id": po.id,
        "order_date": po.order_date,
        "shipping_cost_jpy": po.shipping_cost_jpy,
        "total_nok": po.total_nok,
        "fx_rate_snapshot": po.fx_rate_snapshot,
        "status": po.status,
        "notes": po.notes,
        "created_at": po.created_at,
        "updated_at": po.updated_at,
        "items": [_serialize_item(i) for i in po.items],
        "total_items": len(po.items),
        "total_quantity": sum(i.quantity for i in po.items),
        "total_jpy": sum(i.price_jpy * i.quantity for i in po.items),
        "store_name": _get_store_name(),
    }
    if extras:
        data.update(extras)
    return data


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
        return _serialize_po(
            result["purchase_order"],
            {
                "inventory_results": result["inventory_results"],
                "auto_update_shopify": result.get("auto_update_shopify", False),
            },
        )
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


@router.get("/cost-history")
async def get_cost_history(db: Session = Depends(get_db)):
    """Get per-product cost history from completed purchase orders."""
    return purchase_order_service.get_product_cost_history(db=db)


@router.get("/{po_id}")
async def get_purchase_order(po_id: int, db: Session = Depends(get_db)):
    """Get a single purchase order with all line items."""
    po = purchase_order_service.get_purchase_order(db=db, po_id=po_id)
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return _serialize_po(po)


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


@router.get("/export/json")
async def export_purchase_orders(db: Session = Depends(get_db)):
    """
    Full JSON dump of every purchase order + items, intended for migration
    to the Cloudflare POS app's POST /api/v1/purchase-orders/import endpoint.

    Format is intentionally flat — uses Shopify GIDs (not local DB ids) for
    variant references so the new app can resolve them against its own cache.
    """
    from datetime import datetime, timezone
    from app.models import PurchaseOrder, Variant

    orders = (
        db.query(PurchaseOrder)
          .order_by(PurchaseOrder.order_date.asc(), PurchaseOrder.id.asc())
          .all()
    )

    out = []
    for po in orders:
        items = []
        for it in po.items:
            # Translate the local variant_id FK into the Shopify variant GID
            # so the import side can resolve via its own product cache.
            variant_gid = None
            v = db.query(Variant).filter(Variant.id == it.variant_id).first()
            if v:
                variant_gid = v.shopify_id
            items.append({
                "variant_shopify_id": variant_gid,
                "product_shopify_id": it.product_shopify_id,
                "product_title": it.product_title,
                "variant_title": it.variant_title,
                "sku": it.sku,
                "quantity": it.quantity,
                "unit_price_jpy": it.price_jpy,
                "weight_grams": it.weight_grams,
            })
        out.append({
            "source_id": po.id,
            "reference": f"PO-{po.order_date.year}-{po.id:04d}" if po.order_date else f"PO-{po.id:04d}",
            "order_date": po.order_date.isoformat() if po.order_date else None,
            "shipping_cost_jpy": po.shipping_cost_jpy or 0,
            "total_nok": po.total_nok,
            "fx_rate_snapshot": po.fx_rate_snapshot,
            "status": po.status or "completed",
            "notes": po.notes,
            "created_at": po.created_at.isoformat() if po.created_at else None,
            "items": items,
        })

    return {
        "version": 1,
        "kind": "purchase_orders",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(out),
        "purchase_orders": out,
    }
