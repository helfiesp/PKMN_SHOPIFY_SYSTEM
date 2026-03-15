"""Receipt router — order listing and receipt generation."""
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from typing import Optional

from app.services.receipt_service import receipt_service

router = APIRouter()


@router.get("/orders")
async def list_orders(
    limit: int = Query(50, ge=1, le=250),
    cursor: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    """List recent Shopify orders."""
    try:
        return receipt_service.fetch_orders(
            limit=limit,
            cursor=cursor,
            query_filter=search,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/generate/{order_gid:path}", response_class=HTMLResponse)
async def generate_receipt(order_gid: str):
    """Generate a printable receipt HTML for a given order GID."""
    if not order_gid.startswith("gid://"):
        order_gid = f"gid://shopify/Order/{order_gid}"
    try:
        order = receipt_service.fetch_order_by_id(order_gid)
        html = receipt_service.generate_receipt_html(order)
        return HTMLResponse(content=html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
