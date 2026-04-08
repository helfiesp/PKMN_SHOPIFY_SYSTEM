"""SNKRDUNK operations router."""
from typing import List, Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
import requests

from app.database import get_db
from app.schemas import SnkrdunkFetchRequest, SnkrdunkMatchingResponse
from app.services import snkrdunk_service
from app.models import (
    SnkrdunkScanLog, SnkrdunkPriceHistory, SnkrdunkMapping, SnkrdunkCache,
    Setting, Product, Variant, PriceChangeLog,
)
from app.config import settings as app_settings
from app.services.email_service import send_price_update_email, send_test_email

router = APIRouter()


# ── SNKRDUNK Settings keys ──────────────────────────────────────────────
SNK_SETTING_KEYS = {
    "snk_shipping_jpy":       ("500",   "Shipping cost in JPY"),
    "snk_margin_pct":         ("20",    "Minimum margin percentage"),
    "snk_pack_markup_pct":    ("10",    "Pack price markup over box per-unit price (%)"),
    "snk_auto_update":        ("false", "Auto-update prices on Shopify after fetch"),
    "snk_max_pages":          ("20",    "Max pages to fetch from SNKRDUNK (25 products/page)"),
    "snk_last_jpy_nok_rate":  ("0.063", "Last fetched JPY→NOK rate (auto-updated, read-only)"),
}


class SnkSettingsPayload(BaseModel):
    snk_shipping_jpy: Optional[str] = None
    snk_margin_pct: Optional[str] = None
    snk_pack_markup_pct: Optional[str] = None
    snk_auto_update: Optional[str] = None
    snk_max_pages: Optional[str] = None


class SnkAddPackVariantRequest(BaseModel):
    product_shopify_id: str
    pack_price: float


class SnkMappingPacksUpdate(BaseModel):
    packs_per_box: Optional[int] = None


# ── Settings endpoints ───────────────────────────────────────────────────

@router.get("/settings")
async def get_snk_settings(db: Session = Depends(get_db)):
    """Return all SNKRDUNK-specific settings."""
    result = {}
    for key, (default, _desc) in SNK_SETTING_KEYS.items():
        row = db.query(Setting).filter(Setting.key == key).first()
        result[key] = row.value if row and row.value else default
    return result


@router.put("/settings")
async def save_snk_settings(payload: SnkSettingsPayload, db: Session = Depends(get_db)):
    """Save SNKRDUNK-specific settings."""
    updated = []
    for key, (default, desc) in SNK_SETTING_KEYS.items():
        val = getattr(payload, key, None)
        if val is None:
            continue
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = val
        else:
            db.add(Setting(key=key, value=val, description=desc))
        updated.append(key)
    db.commit()
    return {"updated": updated}


# ── Per-mapping packs_per_box ────────────────────────────────────────────

@router.put("/mappings/{snkrdunk_key}/packs")
async def update_mapping_packs(
    snkrdunk_key: str,
    body: SnkMappingPacksUpdate,
    db: Session = Depends(get_db),
):
    """Set packs_per_box for a specific SNKRDUNK mapping."""
    mapping = db.query(SnkrdunkMapping).filter(
        SnkrdunkMapping.snkrdunk_key == snkrdunk_key
    ).first()
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    mapping.packs_per_box = body.packs_per_box
    db.commit()
    return {"snkrdunk_key": snkrdunk_key, "packs_per_box": mapping.packs_per_box}


# ── Hide / unhide products ──────────────────────────────────────────────

@router.post("/hide/{snkrdunk_key}")
async def hide_product(snkrdunk_key: str, db: Session = Depends(get_db)):
    """Hide a SNKRDUNK product. Creates a disabled mapping if none exists."""
    mapping = db.query(SnkrdunkMapping).filter(
        SnkrdunkMapping.snkrdunk_key == snkrdunk_key
    ).first()
    if mapping:
        mapping.disabled = True
    else:
        mapping = SnkrdunkMapping(snkrdunk_key=snkrdunk_key, disabled=True)
        db.add(mapping)
    db.commit()
    return {"snkrdunk_key": snkrdunk_key, "hidden": True}


@router.post("/unhide/{snkrdunk_key}")
async def unhide_product(snkrdunk_key: str, db: Session = Depends(get_db)):
    """Unhide a SNKRDUNK product."""
    mapping = db.query(SnkrdunkMapping).filter(
        SnkrdunkMapping.snkrdunk_key == snkrdunk_key
    ).first()
    if mapping:
        mapping.disabled = False
        db.commit()
    return {"snkrdunk_key": snkrdunk_key, "hidden": False}


@router.get("/hidden")
async def get_hidden_products(db: Session = Depends(get_db)):
    """Get all hidden SNKRDUNK product keys."""
    hidden = db.query(SnkrdunkMapping.snkrdunk_key).filter(
        SnkrdunkMapping.disabled == True
    ).all()
    return [h[0] for h in hidden]


# ── Exchange rate ────────────────────────────────────────────────────────

@router.get("/exchange-rate")
async def get_exchange_rate(db: Session = Depends(get_db)):
    """Fetch live JPY→NOK rate and persist it."""
    rate = _fetch_jpy_nok_rate()
    row = db.query(Setting).filter(Setting.key == "snk_last_jpy_nok_rate").first()
    if row:
        row.value = str(rate)
    else:
        db.add(Setting(key="snk_last_jpy_nok_rate", value=str(rate), description="Last fetched JPY→NOK rate"))
    db.commit()
    return {"rate": rate}


# ── Auto-update: calculate & push prices ─────────────────────────────────

def _get_snk_setting(db: Session, key: str) -> str:
    row = db.query(Setting).filter(Setting.key == key).first()
    if row and row.value:
        return row.value
    return SNK_SETTING_KEYS.get(key, ("", ""))[0]


def _fetch_jpy_nok_rate() -> float:
    try:
        r = requests.get(
            "https://api.frankfurter.dev/v1/latest",
            params={"base": "JPY", "symbols": "NOK"},
            timeout=10,
        )
        r.raise_for_status()
        rate = r.json().get("rates", {}).get("NOK")
        if rate:
            return float(rate)
    except Exception as e:
        print(f"[SNKRDUNK] FX rate fetch failed, using fallback: {e}")
    return 0.063


SPECIAL_PACK_COUNTS = [
    ("terastal festival", 10),
    ("mega dream", 10),
    ("vstar universe", 10),
    ("shiny treasure ex", 10),
    ("shiny treasure", 10),
    ("pokemon 151", 20),
    ("black bolt", 20),
    ("white flare", 20),
]


def _detect_packs_per_box(title: str) -> int:
    t = (title or "").strip().lower()
    for keyword, count in SPECIAL_PACK_COUNTS:
        if keyword in t:
            return count
    return 30


def _round_up_nok(amount: float) -> int:
    """Round up to the next number ending in 9, skip x09 → x19.
    Exact hundreds (1000, 1100) → previous 99 (999, 1099).
    """
    n = int(amount)
    if amount > n:
        n += 1
    if n % 100 == 0:
        return n - 1
    result = n + (9 - n % 10)
    if result % 100 == 9 and (result // 10) % 10 == 0:
        result += 10
    return result


def _round_pack_price_psych(n: float) -> int:
    """Round pack price up to nearest ending in 25, 49, 75, or 99."""
    return _round_up_nok(n)


import math


@router.post("/auto-update")
async def run_auto_update_endpoint(db: Session = Depends(get_db)):
    """API endpoint wrapper for auto-update."""
    return _execute_auto_update(db)


def _execute_auto_update(db: Session):
    """
    Calculate recommended prices from cached SNKRDUNK data and push
    both Booster Box and Booster Pack variant prices to Shopify.
    """
    # Load settings
    shipping = float(_get_snk_setting(db, "snk_shipping_jpy"))
    margin = float(_get_snk_setting(db, "snk_margin_pct")) / 100
    pack_markup_pct = float(_get_snk_setting(db, "snk_pack_markup_pct")) / 100
    VAT = 0.25

    # Always fetch live exchange rate
    rate = _fetch_jpy_nok_rate()
    # Persist for UI display
    row = db.query(Setting).filter(Setting.key == "snk_last_jpy_nok_rate").first()
    if row:
        row.value = str(rate)
    else:
        db.add(Setting(key="snk_last_jpy_nok_rate", value=str(rate), description="Last fetched JPY→NOK rate"))
    print(f"[SNKRDUNK AUTO-UPDATE] rate={rate}, shipping={shipping}, margin={margin}, pack_markup={pack_markup_pct}")

    # Get cached SNKRDUNK products
    snk_products = snkrdunk_service.get_cached_products(db=db, include_expired=False, translate=True)

    # Get all active mappings
    mappings = db.query(SnkrdunkMapping).filter(
        SnkrdunkMapping.disabled == False,
        SnkrdunkMapping.product_shopify_id.isnot(None),
    ).all()

    snk_by_id = {str(p["id"]): p for p in snk_products}

    shop = app_settings.get_shopify_shop()
    token = app_settings.get_shopify_token()
    if not shop or not token:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")

    graphql_url = f"https://{shop}/admin/api/{app_settings.shopify_api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    results = []
    errors = []

    for mapping in mappings:
        snk = snk_by_id.get(str(mapping.snkrdunk_key))
        if not snk:
            continue

        jpy = snk.get("minPrice") or snk.get("minPriceJpy") or 0
        if jpy <= 0:
            continue

        # Calculate box price: (jpy + shipping) * rate / (1 - margin) * 1.25 rounded up to 25
        nok_cost = (jpy + shipping) * rate
        box_price = _round_up_nok((nok_cost / (1 - margin)) * (1 + VAT))

        # Determine packs per box
        product = db.query(Product).filter(
            Product.shopify_id == mapping.product_shopify_id
        ).first()
        if not product:
            continue

        packs = mapping.packs_per_box or _detect_packs_per_box(product.title or "")

        # Pack price = (box_price / packs) * (1 + markup), rounded psychologically
        pack_raw = (box_price / packs) * (1 + pack_markup_pct)
        pack_price = _round_pack_price_psych(pack_raw)

        # Find box and pack variants
        variants = db.query(Variant).filter(Variant.product_id == product.id).all()
        box_variant = None
        pack_variant = None
        for v in variants:
            opt = (v.option_value or v.title or "").lower()
            if "box" in opt:
                box_variant = v
            elif "pack" in opt:
                pack_variant = v

        if not box_variant and not pack_variant:
            # Single variant product — treat as box
            if len(variants) == 1:
                box_variant = variants[0]

        updates_to_push = []
        item_result = {
            "product": product.title,
            "product_shopify_id": product.shopify_id,
            "snkrdunk_key": mapping.snkrdunk_key,
            "jpy": jpy,
            "rate": rate,
        }

        if box_variant:
            old_box = float(box_variant.price) if box_variant.price else 0
            if abs(old_box - box_price) >= 25:
                updates_to_push.append((box_variant, box_price, old_box, "box"))
                item_result["box_old"] = old_box
                item_result["box_new"] = box_price
            else:
                item_result["box_skip"] = f"no change ({old_box})"

        if pack_variant:
            old_pack = float(pack_variant.price) if pack_variant.price else 0
            if abs(old_pack - pack_price) >= 10:
                updates_to_push.append((pack_variant, pack_price, old_pack, "pack"))
                item_result["pack_old"] = old_pack
                item_result["pack_new"] = pack_price
                item_result["packs_per_box"] = packs
            else:
                item_result["pack_skip"] = f"no change ({old_pack})"

        # Push to Shopify
        if updates_to_push:
            mutation = """
            mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants { id price }
                userErrors { field message }
              }
            }
            """
            variant_inputs = []
            for var, new_price, _old, _vtype in updates_to_push:
                variant_inputs.append({
                    "id": var.shopify_id,
                    "price": str(new_price),
                    "compareAtPrice": None,
                })

            try:
                resp = requests.post(
                    graphql_url,
                    json={
                        "query": mutation,
                        "variables": {
                            "productId": product.shopify_id,
                            "variants": variant_inputs,
                        },
                    },
                    headers=headers,
                    timeout=60,
                )
                resp.raise_for_status()
                gql = resp.json()
                user_errors = (
                    gql.get("data", {})
                    .get("productVariantsBulkUpdate", {})
                    .get("userErrors", [])
                )
                if user_errors:
                    errors.append({"product": product.title, "errors": user_errors})
                    item_result["shopify_error"] = user_errors
                else:
                    # Update local DB + log
                    for var, new_price, old_price, _vtype in updates_to_push:
                        var.price = new_price
                        var.updated_at = datetime.now(ZoneInfo("Europe/Oslo"))
                        db.add(PriceChangeLog(
                            product_shopify_id=product.shopify_id,
                            variant_shopify_id=var.shopify_id,
                            product_title=product.title,
                            variant_title=var.option_value or var.title,
                            old_price=old_price,
                            new_price=new_price,
                            price_delta=new_price - old_price,
                            change_type="snkrdunk_auto_update",
                        ))
                    item_result["pushed"] = True
            except Exception as e:
                errors.append({"product": product.title, "error": str(e)})
                item_result["shopify_error"] = str(e)

        results.append(item_result)

    db.commit()

    # Send email notification (non-blocking, never raises)
    send_price_update_email(
        db,
        results=results,
        settings_summary={
            "rate": rate,
            "shipping_jpy": shipping,
            "margin_pct": margin * 100,
            "pack_markup_pct": pack_markup_pct * 100,
        },
        errors=errors,
    )

    return {
        "rate": rate,
        "shipping_jpy": shipping,
        "margin_pct": margin * 100,
        "pack_markup_pct": pack_markup_pct * 100,
        "total_mappings": len(mappings),
        "processed": len(results),
        "pushed": sum(1 for r in results if r.get("pushed")),
        "errors": errors,
        "details": results,
    }


# ── Test email endpoint ────────────────────────────────────────────────

@router.post("/test-email")
async def test_email_endpoint(db: Session = Depends(get_db)):
    """Send a test email to verify Resend configuration."""
    result = send_test_email(db)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


# ── Manual SNKRDUNK product endpoints ─────────────────────────────────────

class ManualSnkrdunkRequest(BaseModel):
    url: Optional[str] = None
    snkrdunk_id: Optional[str] = None


@router.post("/add-manual")
async def add_manual_snkrdunk(request: ManualSnkrdunkRequest, db: Session = Depends(get_db)):
    """Add a SNKRDUNK product manually by URL or product ID."""
    import re as _re

    product_id = None

    if request.url:
        # Parse product ID from URL like https://snkrdunk.com/apparels/550896
        match = _re.search(r'/apparels/(\d+)', request.url)
        if match:
            product_id = int(match.group(1))
        else:
            # Maybe they pasted just a number
            stripped = request.url.strip()
            if stripped.isdigit():
                product_id = int(stripped)
    elif request.snkrdunk_id:
        stripped = request.snkrdunk_id.strip()
        if stripped.isdigit():
            product_id = int(stripped)

    if not product_id:
        raise HTTPException(status_code=400, detail="Could not parse a SNKRDUNK product ID. Provide a URL like https://snkrdunk.com/apparels/550896 or a numeric ID.")

    # Check if already exists in cache
    existing = db.query(SnkrdunkCache).filter(
        SnkrdunkCache.brand_id == "manual",
        SnkrdunkCache.page == product_id,
    ).first()

    try:
        result = snkrdunk_service.fetch_single_product(db, product_id)
    except requests.exceptions.HTTPError as e:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found on SNKRDUNK")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch product: {e}")

    return {
        "message": f"Product added: {result.get('nameEn', product_id)}",
        "product": result,
        "already_existed": existing is not None,
    }


@router.delete("/manual/{snkrdunk_key}")
async def remove_manual_snkrdunk(snkrdunk_key: int, db: Session = Depends(get_db)):
    """Remove a manually-added SNKRDUNK product."""
    cache = db.query(SnkrdunkCache).filter(
        SnkrdunkCache.brand_id == "manual",
        SnkrdunkCache.page == snkrdunk_key,
    ).first()

    if not cache:
        raise HTTPException(status_code=404, detail=f"Manual product {snkrdunk_key} not found")

    db.delete(cache)

    # Also remove mapping if exists
    mapping = db.query(SnkrdunkMapping).filter(
        SnkrdunkMapping.snkrdunk_key == str(snkrdunk_key)
    ).first()
    if mapping:
        db.delete(mapping)

    db.commit()
    return {"message": f"Removed manual product {snkrdunk_key}"}


@router.get("/manual")
async def list_manual_snkrdunk(db: Session = Depends(get_db)):
    """List all manually-added SNKRDUNK product IDs."""
    entries = db.query(SnkrdunkCache).filter(
        SnkrdunkCache.brand_id == "manual"
    ).all()

    items = []
    for entry in entries:
        apparels = entry.response_data.get("apparels", [])
        for item in apparels:
            items.append({
                "id": item.get("id"),
                "name": item.get("name", ""),
                "minPrice": item.get("minPrice"),
            })

    return {"items": items, "total": len(items)}


# ── Add Booster Pack variant to a product ────────────────────────────────

# GraphQL mutations for variant management
_M_PRODUCT_OPTION_UPDATE = """
mutation UpdateOption(
  $productId: ID!,
  $option: OptionUpdateInput!,
  $optionValuesToAdd: [OptionValueCreateInput!],
  $optionValuesToDelete: [ID!],
  $variantStrategy: ProductOptionUpdateVariantStrategy
) {
  productOptionUpdate(
    productId: $productId, option: $option,
    optionValuesToAdd: $optionValuesToAdd,
    optionValuesToDelete: $optionValuesToDelete,
    variantStrategy: $variantStrategy
  ) {
    userErrors { field message }
    product {
      id options { id name position values optionValues { id name hasVariants } }
      variants(first: 50) { nodes { id title price selectedOptions { name value } } }
    }
  }
}
"""

_M_VARIANTS_BULK_UPDATE = """
mutation VariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id title price selectedOptions { name value } }
    userErrors { field message }
  }
}
"""

_M_VARIANTS_BULK_CREATE = """
mutation VariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkCreate(productId: $productId, variants: $variants) {
    productVariants { id title price selectedOptions { name value } }
    userErrors { field message }
  }
}
"""

_Q_PRODUCT = """
query ProductGet($id: ID!) {
  product(id: $id) {
    id title
    options { id name position values optionValues { id name hasVariants } }
    variants(first: 50) {
      nodes { id title price selectedOptions { name value } }
    }
  }
}
"""

import time


def _gql_call(shop: str, token: str, query: str, variables: dict) -> dict:
    """Execute a Shopify GraphQL call."""
    url = f"https://{shop}/admin/api/{app_settings.shopify_api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
    r = requests.post(url, json={"query": query, "variables": variables}, headers=headers, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload.get("errors"), list) and payload["errors"]:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    return payload.get("data", {})


@router.post("/add-pack-variant")
async def add_pack_variant(body: SnkAddPackVariantRequest, db: Session = Depends(get_db)):
    """
    Add a Booster Pack variant to a product that only has a box variant.
    Steps: ensure "Type" option → label existing as "Booster Box" → create "Booster Pack".
    """
    shop = app_settings.get_shopify_shop()
    token = app_settings.get_shopify_token()
    if not shop or not token:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")

    product = db.query(Product).filter(Product.shopify_id == body.product_shopify_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found in local DB")

    product_gid = product.shopify_id
    if not product_gid.startswith("gid://"):
        product_gid = f"gid://shopify/Product/{product_gid}"

    # Step 1: Fetch current product state from Shopify
    gql_product = _gql_call(shop, token, _Q_PRODUCT, {"id": product_gid}).get("product")
    if not gql_product:
        raise HTTPException(status_code=404, detail="Product not found on Shopify")

    # Find or identify the single option
    options = gql_product.get("options", [])
    if not options:
        raise HTTPException(status_code=400, detail="Product has no options")

    opt = options[0]  # use first (usually only) option
    opt_id = str(opt["id"])

    # Check if "Booster Pack" value already exists
    existing_values = [ov["name"] for ov in (opt.get("optionValues") or [])]
    has_box = any("booster box" in v.lower() for v in existing_values)
    has_pack = any("booster pack" in v.lower() for v in existing_values)

    if has_pack:
        return {"message": "Booster Pack variant already exists", "skipped": True}

    # Step 2: Add option values (rename option to "Type", add Booster Box + Booster Pack)
    to_add = []
    if not has_box:
        to_add.append({"name": "Booster Box"})
    to_add.append({"name": "Booster Pack"})

    data = _gql_call(shop, token, _M_PRODUCT_OPTION_UPDATE, {
        "productId": product_gid,
        "option": {"id": opt_id, "name": "Type", "position": int(opt.get("position") or 1)},
        "optionValuesToAdd": to_add if to_add else None,
        "optionValuesToDelete": None,
        "variantStrategy": "LEAVE_AS_IS",
    })
    ue = (data.get("productOptionUpdate") or {}).get("userErrors", [])
    if ue:
        raise HTTPException(status_code=500, detail=f"Option update failed: {ue}")

    updated_product = (data.get("productOptionUpdate") or {}).get("product") or gql_product
    time.sleep(0.3)

    # Step 3: Set existing variant to "Booster Box"
    variants_nodes = (updated_product.get("variants") or {}).get("nodes", [])
    if variants_nodes:
        box_gid = variants_nodes[0]["id"]  # first variant is the box
        # Find the Type option ID from updated product
        type_opt = None
        for o in (updated_product.get("options") or []):
            if o["name"].lower() == "type":
                type_opt = o
                break
        if type_opt:
            type_opt_id = str(type_opt["id"])
            data = _gql_call(shop, token, _M_VARIANTS_BULK_UPDATE, {
                "productId": product_gid,
                "variants": [{
                    "id": box_gid,
                    "optionValues": [{"optionId": type_opt_id, "name": "Booster Box"}],
                }],
            })
            ue = (data.get("productVariantsBulkUpdate") or {}).get("userErrors", [])
            if ue:
                raise HTTPException(status_code=500, detail=f"Box variant update failed: {ue}")
            time.sleep(0.3)

            # Step 4: Create Booster Pack variant
            data = _gql_call(shop, token, _M_VARIANTS_BULK_CREATE, {
                "productId": product_gid,
                "variants": [{
                    "price": float(body.pack_price),
                    "compareAtPrice": None,
                    "optionValues": [{"optionId": type_opt_id, "name": "Booster Pack"}],
                }],
            })
            ue = (data.get("productVariantsBulkCreate") or {}).get("userErrors", [])
            if ue:
                raise HTTPException(status_code=500, detail=f"Pack variant create failed: {ue}")

            # Step 5: Clean up "Default Title" option value if present
            time.sleep(0.3)
            default_val_id = None
            for ov in (type_opt.get("optionValues") or []):
                if ov["name"] == "Default Title":
                    default_val_id = ov["id"]
                    break
            if default_val_id:
                try:
                    _gql_call(shop, token, _M_PRODUCT_OPTION_UPDATE, {
                        "productId": product_gid,
                        "option": {"id": type_opt_id, "name": "Type", "position": int(type_opt.get("position") or 1)},
                        "optionValuesToAdd": None,
                        "optionValuesToDelete": [default_val_id],
                        "variantStrategy": "LEAVE_AS_IS",
                    })
                except Exception:
                    pass  # non-fatal cleanup

            # Sync new variant to local DB
            new_variants = (data.get("productVariantsBulkCreate") or {}).get("productVariants", [])
            for nv in new_variants:
                local_variant = Variant(
                    product_id=product.id,
                    shopify_id=nv["id"],
                    title=nv.get("title", "Booster Pack"),
                    option_value="Booster Pack",
                    price=float(nv.get("price", body.pack_price)),
                )
                db.add(local_variant)
            db.commit()

    return {"message": f"Booster Pack variant added at kr {body.pack_price}", "product": product.title}


@router.post("/fetch", response_model=dict)
async def fetch_snkrdunk_data(
    request: SnkrdunkFetchRequest,
    db: Session = Depends(get_db)
):
    """
    Fetch product data from SNKRDUNK API.
    
    This replaces the SNKRDUNK fetching part of snkrdunk.py.
    Caches results in database for efficiency.
    Creates a SnkrdunkScanLog entry to track when prices were fetched.
    """
    started_at = datetime.now(ZoneInfo("Europe/Oslo"))
    log_id = None
    
    try:
        max_pages = int(_get_snk_setting(db, "snk_max_pages") or 20)
        result = await snkrdunk_service.fetch_and_cache_snkrdunk_data(
            db=db,
            pages=request.pages,
            force_refresh=request.force_refresh,
            max_pages=max_pages,
        )
        
        print(f"[SNKRDUNK FETCH] Service returned: total_items={result.get('total_items')}")
        
        completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
        duration = (completed_at - started_at).total_seconds()
        total_items = result.get('total_items', 0)
        
        # Create a SnkrdunkScanLog entry to track this fetch
        scan_log = SnkrdunkScanLog(
            status='success',
            total_items=total_items,
            output=f"Fetched {total_items} items from {len(request.pages)} pages",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(scan_log)
        db.flush()  # Flush to get the ID without committing
        log_id = scan_log.id
        
        # Save current prices directly from the API response to SnkrdunkPriceHistory
        # This captures what the prices WERE at this exact moment
        from app.models import SnkrdunkPriceHistory
        fresh_items = result.get('items', [])
        
        print(f"[SNKRDUNK FETCH] Saving {len(fresh_items)} fresh prices for scan #{log_id}")
        for item in fresh_items:
            price_record = SnkrdunkPriceHistory(
                scan_log_id=log_id,
                snkrdunk_key=str(item.get('id')),
                price_jpy=item.get('minPrice'),  # Use minPrice instead of minPriceJpy
                price_usd=None,  # Not available in fresh response
                recorded_at=datetime.now(ZoneInfo("Europe/Oslo"))
            )
            db.add(price_record)
        
        db.commit()
        
        # Include the log_id in response
        result['log_id'] = log_id
        print(f"[SNKRDUNK] Successfully created SnkrdunkScanLog #{log_id} with {len(fresh_items)} prices")

        # Server-side auto-update: push prices to Shopify if enabled
        auto_update = _get_snk_setting(db, "snk_auto_update")
        if auto_update == "true":
            print("[SNKRDUNK FETCH] Auto-update enabled, triggering price push...")
            try:
                update_result = _execute_auto_update(db)
                result['auto_update'] = {
                    "pushed": update_result.get("pushed", 0),
                    "errors": len(update_result.get("errors", [])),
                }
                print(f"[SNKRDUNK FETCH] Auto-update done: {result['auto_update']}")
            except Exception as au_err:
                print(f"[SNKRDUNK FETCH] Auto-update failed: {au_err}")
                result['auto_update'] = {"error": str(au_err)}

        return result
    except Exception as e:
        print(f"[SNKRDUNK] Error during fetch: {str(e)}")
        import traceback
        traceback.print_exc()
        
        completed_at = datetime.now(ZoneInfo("Europe/Oslo"))
        duration = (completed_at - started_at).total_seconds()
        
        try:
            # Create failed SnkrdunkScanLog entry
            scan_log = SnkrdunkScanLog(
                status='failed',
                output=None,
                error_message=str(e),
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration
            )
            db.add(scan_log)
            db.flush()
            log_id = scan_log.id
            db.commit()
            print(f"[SNKRDUNK] Created failed SnkrdunkScanLog #{log_id}")
        except Exception as log_error:
            print(f"[SNKRDUNK] Failed to create error log: {log_error}")
        
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/match-shopify", response_model=SnkrdunkMatchingResponse)
async def match_with_shopify(
    collection_id: str,
    db: Session = Depends(get_db)
):
    """
    Match SNKRDUNK products with Shopify products and generate price recommendations.
    
    This replaces the matching logic in snkrdunk.py.
    Uses cached SNKRDUNK data and local Shopify products.
    """
    try:
        result = await snkrdunk_service.match_and_calculate_prices(
            db=db,
            collection_id=collection_id
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/price-history")
async def get_price_history(
    log_id: int,
    limit: int = 200,
    db: Session = Depends(get_db)
):
    """
    Get historical SNKRDUNK prices for a specific scan log.
    
    Returns all prices that were recorded during that scan.
    """
    try:
        # Query for prices from this specific scan log
        history = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.scan_log_id == log_id
        ).order_by(SnkrdunkPriceHistory.snkrdunk_key).limit(limit).all()
        
        # Get scan log for reference
        scan_log = db.query(SnkrdunkScanLog).filter(
            SnkrdunkScanLog.id == log_id
        ).first()
        
        return {
            "log_id": log_id,
            "scan_date": scan_log.created_at.isoformat() if scan_log else None,
            "item_count": len(history),
            "items": [
                {
                    "id": h.snkrdunk_key,
                    "minPriceJpy": h.price_jpy,  # Frontend expects minPriceJpy
                    "minPrice": h.price_jpy,     # Also provide minPrice for consistency
                    "price_usd": h.price_usd,
                    "recorded_at": h.recorded_at.isoformat() if h.recorded_at else None
                }
                for h in history
            ]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-logs")
async def get_snkrdunk_scan_logs(
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """Get SNKRDUNK price update scan logs."""
    try:
        logs = db.query(SnkrdunkScanLog).order_by(SnkrdunkScanLog.created_at.desc()).limit(limit).all()
        
        return [
            {
                "id": log.id,
                "status": log.status,
                "total_items": log.total_items,
                "started_at": log.started_at.isoformat() if log.started_at else None,
                "completed_at": log.completed_at.isoformat() if log.completed_at else None,
                "duration_seconds": log.duration_seconds,
                "output": log.output,
                "error_message": log.error_message,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scan-logs/{log_id}")
async def get_snkrdunk_scan_log(
    log_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific SNKRDUNK scan log."""
    try:
        log = db.query(SnkrdunkScanLog).filter(SnkrdunkScanLog.id == log_id).first()
        if not log:
            raise HTTPException(status_code=404, detail="Scan log not found")
        
        return {
            "id": log.id,
            "status": log.status,
            "total_items": log.total_items,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "duration_seconds": log.duration_seconds,
            "output": log.output,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/products")
async def get_cached_products(
    include_expired: bool = False,
    translate: bool = True,
    scan_log_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """Get all cached SNKRDUNK products with optional translation."""
    products = snkrdunk_service.get_cached_products(
        db=db,
        include_expired=include_expired,
        translate=translate,
        scan_log_id=scan_log_id
    )
    return {
        "total_items": len(products),
        "items": products
    }


@router.delete("/cache")
async def clear_cache(db: Session = Depends(get_db)):
    """Clear SNKRDUNK cache."""
    snkrdunk_service.clear_cache(db=db)
    return {"message": "Cache cleared successfully"}
