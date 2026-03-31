"""Margin VAT router — purchases, items, proof images, Shopify sync."""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    MarginVatPurchaseCreate, MarginVatPurchaseResponse, MarginVatItemUpdate,
    MarginVatItemResponse, MarginVatCalculation, MarginVatSyncResult,
    MarginVatProofImageResponse, MarginVatBucketSummary,
)
from app.services.margin_vat_service import margin_vat_service

router = APIRouter()


# ── Purchases ────────────────────────────────────────────────────────────

@router.get("/purchases", response_model=List[MarginVatPurchaseResponse])
async def list_purchases(status: Optional[str] = None, db: Session = Depends(get_db)):
    purchases = margin_vat_service.get_purchases(db, status=status)
    result = []
    for p in purchases:
        pr = MarginVatPurchaseResponse.model_validate(p)
        pr.total_nok = sum(i.quantity * i.unit_price_nok for i in p.items)
        result.append(pr)
    return result


@router.get("/purchases/{purchase_id}", response_model=MarginVatPurchaseResponse)
async def get_purchase(purchase_id: int, db: Session = Depends(get_db)):
    p = margin_vat_service.get_purchase(db, purchase_id)
    if not p:
        raise HTTPException(status_code=404, detail="Purchase not found")
    pr = MarginVatPurchaseResponse.model_validate(p)
    pr.total_nok = sum(i.quantity * i.unit_price_nok for i in p.items)
    return pr


@router.post("/purchases", response_model=MarginVatPurchaseResponse)
async def create_purchase(data: MarginVatPurchaseCreate, db: Session = Depends(get_db)):
    try:
        p = margin_vat_service.create_purchase(db, data.model_dump())
        pr = MarginVatPurchaseResponse.model_validate(p)
        pr.total_nok = sum(i.quantity * i.unit_price_nok for i in p.items)
        return pr
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/purchases/{purchase_id}")
async def delete_purchase(purchase_id: int, db: Session = Depends(get_db)):
    if not margin_vat_service.delete_purchase(db, purchase_id):
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


# ── Items ────────────────────────────────────────────────────────────────

@router.get("/items", response_model=List[MarginVatItemResponse])
async def list_items(status: Optional[str] = None, needs_reassignment: Optional[bool] = None, db: Session = Depends(get_db)):
    return margin_vat_service.get_all_items(db, status=status, needs_reassignment=needs_reassignment)


@router.patch("/items/{item_id}", response_model=MarginVatItemResponse)
async def update_item(item_id: int, data: MarginVatItemUpdate, db: Session = Depends(get_db)):
    item = margin_vat_service.update_item(db, item_id, data.model_dump(exclude_unset=True))
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


# ── Proof Images ─────────────────────────────────────────────────────────

@router.post("/purchases/{purchase_id}/proof-images", response_model=MarginVatProofImageResponse)
async def upload_proof_image(purchase_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        img = margin_vat_service.upload_proof_image(db, purchase_id, file)
        if not img:
            raise HTTPException(status_code=404, detail="Purchase not found")
        return img
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/proof-images/{image_id}")
async def delete_proof_image(image_id: int, db: Session = Depends(get_db)):
    if not margin_vat_service.delete_proof_image(db, image_id):
        raise HTTPException(status_code=404, detail="Not found")
    return {"message": "Deleted"}


# ── Calculation, Recalc, Sync ────────────────────────────────────────────

@router.get("/calculate")
async def calculate_rate(selling_price: float, purchase_price: float):
    if selling_price <= 0:
        raise HTTPException(status_code=400, detail="Selling price must be positive")
    calc = margin_vat_service.calculate_effective_rate(selling_price, purchase_price)
    return MarginVatCalculation(selling_price=selling_price, purchase_price=purchase_price, **calc)


@router.get("/summary", response_model=List[MarginVatBucketSummary])
async def get_bucket_summary(db: Session = Depends(get_db)):
    return margin_vat_service.get_bucket_summary(db)


@router.post("/recalculate")
async def recalculate_all(db: Session = Depends(get_db)):
    return margin_vat_service.recalculate_all(db)


@router.post("/sync-collections", response_model=MarginVatSyncResult)
async def sync_collections(db: Session = Depends(get_db)):
    try:
        return margin_vat_service.sync_collections(db)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Shopify Product Operations ───────────────────────────────────────────

@router.get("/product-detail")
async def get_product_detail(shopify_id: str):
    try:
        return margin_vat_service.fetch_product_detail(shopify_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/create-product")
async def create_shopify_product(data: dict, db: Session = Depends(get_db)):
    try:
        return margin_vat_service.create_shopify_product(db, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/update-product")
async def update_shopify_product(data: dict, db: Session = Depends(get_db)):
    pid = data.pop("product_shopify_id", None)
    if not pid:
        raise HTTPException(status_code=400, detail="product_shopify_id required")
    try:
        return margin_vat_service.update_shopify_product(db, pid, data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
