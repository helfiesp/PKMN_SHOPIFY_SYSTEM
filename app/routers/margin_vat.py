"""Margin VAT router — CRUD, proof images, recalculation, and Shopify sync."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    MarginVatProductCreate,
    MarginVatProductUpdate,
    MarginVatProductResponse,
    MarginVatCalculation,
    MarginVatSyncResult,
    MarginVatProofImageResponse,
    MarginVatBucketSummary,
)
from app.services.margin_vat_service import margin_vat_service

router = APIRouter()


@router.get("", response_model=List[MarginVatProductResponse])
async def list_margin_vat_products(
    status: Optional[str] = None,
    needs_reassignment: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    """List all margin VAT products."""
    return margin_vat_service.get_list(db, status=status, needs_reassignment=needs_reassignment)


@router.get("/summary", response_model=List[MarginVatBucketSummary])
async def get_bucket_summary(db: Session = Depends(get_db)):
    """Get bucket summary grouped by tax rate."""
    return margin_vat_service.get_bucket_summary(db)


@router.get("/calculate")
async def calculate_rate(selling_price: float, purchase_price: float):
    """Preview VAT calculation without saving."""
    if selling_price <= 0:
        raise HTTPException(status_code=400, detail="Selling price must be positive")
    if purchase_price < 0:
        raise HTTPException(status_code=400, detail="Purchase price cannot be negative")

    calc = margin_vat_service.calculate_effective_rate(selling_price, purchase_price)
    return MarginVatCalculation(
        selling_price=selling_price,
        purchase_price=purchase_price,
        **calc,
    )


@router.get("/{mvp_id}", response_model=MarginVatProductResponse)
async def get_margin_vat_product(mvp_id: int, db: Session = Depends(get_db)):
    """Get a single margin VAT product."""
    mvp = margin_vat_service.get(db, mvp_id)
    if not mvp:
        raise HTTPException(status_code=404, detail="Product not found")
    return mvp


@router.post("", response_model=MarginVatProductResponse)
async def create_margin_vat_product(
    data: MarginVatProductCreate,
    db: Session = Depends(get_db),
):
    """Register a product under the margin VAT scheme."""
    try:
        return margin_vat_service.create(db, data.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{mvp_id}", response_model=MarginVatProductResponse)
async def update_margin_vat_product(
    mvp_id: int,
    data: MarginVatProductUpdate,
    db: Session = Depends(get_db),
):
    """Update a margin VAT product."""
    mvp = margin_vat_service.update(db, mvp_id, data.model_dump(exclude_unset=True))
    if not mvp:
        raise HTTPException(status_code=404, detail="Product not found")
    return mvp


@router.delete("/{mvp_id}")
async def delete_margin_vat_product(mvp_id: int, db: Session = Depends(get_db)):
    """Delete a margin VAT product and its proof images."""
    success = margin_vat_service.delete(db, mvp_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Deleted"}


# ── Proof Images ─────────────────────────────────────────────────────────

@router.post("/{mvp_id}/proof-images", response_model=MarginVatProofImageResponse)
async def upload_proof_image(
    mvp_id: int,
    file: UploadFile = File(...),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a proof-of-purchase image."""
    try:
        img = margin_vat_service.upload_proof_image(db, mvp_id, file, description)
        if not img:
            raise HTTPException(status_code=404, detail="Product not found")
        return img
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/proof-images/{image_id}")
async def delete_proof_image(image_id: int, db: Session = Depends(get_db)):
    """Delete a proof image."""
    success = margin_vat_service.delete_proof_image(db, image_id)
    if not success:
        raise HTTPException(status_code=404, detail="Image not found")
    return {"message": "Deleted"}


# ── Recalculation & Sync ────────────────────────────────────────────────

@router.post("/recalculate")
async def recalculate_all(db: Session = Depends(get_db)):
    """Recalculate VAT rates for all active products."""
    return margin_vat_service.recalculate_all(db)


@router.post("/sync-collections", response_model=MarginVatSyncResult)
async def sync_collections(db: Session = Depends(get_db)):
    """Sync products to their correct Shopify tax-override collections."""
    try:
        return margin_vat_service.sync_collections(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Shopify Product Management ───────────────────────────────────────────

@router.get("/product-detail")
async def get_product_detail(shopify_id: str):
    """Fetch full product details from Shopify for templating."""
    try:
        return margin_vat_service.fetch_product_detail(shopify_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-product")
async def create_shopify_product(
    data: dict,
    db: Session = Depends(get_db),
):
    """Create a new draft product on Shopify and optionally register it for margin VAT."""
    try:
        result = margin_vat_service.create_shopify_product(db, data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-product")
async def update_shopify_product(
    data: dict,
    db: Session = Depends(get_db),
):
    """Update a product on Shopify (title, status, price)."""
    product_shopify_id = data.pop("product_shopify_id", None)
    if not product_shopify_id:
        raise HTTPException(status_code=400, detail="product_shopify_id required")
    try:
        result = margin_vat_service.update_shopify_product(db, product_shopify_id, data)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
