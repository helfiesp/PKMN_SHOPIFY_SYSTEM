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


@router.get("/export/json")
async def export_margin_vat(include_proofs: bool = True, db: Session = Depends(get_db)):
    """
    Full JSON dump of every margin-VAT purchase + items + (optionally) proof
    images base64-encoded inline. Intended for migration to the Cloudflare
    POS app's POST /api/v1/margin-vat/import endpoint.

    Pass ?include_proofs=false for a smaller file when migrating just the
    structured data.
    """
    import base64
    import os
    from pathlib import Path
    from datetime import datetime, timezone
    from app.models import MarginVatPurchase

    purchases = (
        db.query(MarginVatPurchase)
          .order_by(MarginVatPurchase.created_at.asc(), MarginVatPurchase.id.asc())
          .all()
    )

    # Resolve the proof-image upload root (mirrors main.py StaticFiles mount).
    upload_root = Path(__file__).resolve().parent.parent.parent / "uploads"

    out = []
    for p in purchases:
        items = []
        for it in p.items:
            items.append({
                "description": it.description,
                "quantity": it.quantity,
                "unit_purchase_price_nok": it.unit_price_nok,
                "product_shopify_id": it.product_shopify_id,
                "variant_shopify_id": it.variant_shopify_id,
                "product_title": it.product_title,
                "variant_title": it.variant_title,
                "sku": it.sku,
                "image_url": it.image_url,
                "selling_price_nok": it.selling_price_nok,
                "margin_nok": it.margin_nok,
                "vat_amount_nok": it.vat_amount_nok,
                "effective_rate_pct": it.effective_rate_pct,
                "bucket_rate_pct": it.bucket_rate_pct,
                "tax_collection_id": it.tax_collection_id,
                "tax_collection_name": it.tax_collection_name,
                "needs_reassignment": bool(it.needs_reassignment),
                "status": it.status or "active",
            })

        proofs = []
        for img in p.proof_images:
            proof = {
                "filename": img.filename,
                "stored_filename": img.stored_filename,
                "content_type": img.content_type,
                "file_size_bytes": img.file_size_bytes,
                "description": img.description,
            }
            if include_proofs:
                # Resolve disk path: img.file_path is relative to uploads/
                disk = upload_root / img.file_path
                if disk.exists() and disk.is_file():
                    try:
                        with open(disk, "rb") as f:
                            proof["data_base64"] = base64.b64encode(f.read()).decode("ascii")
                    except Exception as e:
                        proof["read_error"] = str(e)
                else:
                    proof["read_error"] = "file not found on disk"
            proofs.append(proof)

        out.append({
            "source_id": p.id,
            "reference": f"MV-{p.purchase_date.year if p.purchase_date else 2024}-{p.id:04d}",
            "seller": p.seller,
            "purchase_date": p.purchase_date.isoformat() if p.purchase_date else None,
            "notes": p.notes,
            "status": p.status or "active",
            "created_at": p.created_at.isoformat() if p.created_at else None,
            "total_purchase_nok": sum((it.unit_price_nok or 0) * (it.quantity or 0) for it in p.items),
            "items": items,
            "proof_images": proofs,
        })

    return {
        "version": 1,
        "kind": "margin_vat",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(out),
        "include_proofs": include_proofs,
        "purchases": out,
    }
