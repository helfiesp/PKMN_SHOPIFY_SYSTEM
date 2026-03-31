"""Shopify operations router."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import requests

from app.database import get_db
from app.config import settings
from app.schemas import (
    ProductResponse,
    FetchCollectionRequest,
    FetchCollectionResponse
)
from app.services import shopify_service


class SetInventoryRequest(BaseModel):
    quantity: int

router = APIRouter()


@router.post("/fetch-collection", response_model=FetchCollectionResponse)
async def fetch_collection(
    request: FetchCollectionRequest,
    db: Session = Depends(get_db)
):
    """
    Fetch products from a Shopify collection and store in database.
    
    This replaces the shopify_fetch_collection.py script functionality.
    """
    shop = settings.get_shopify_shop()
    if not shop:
        raise HTTPException(
            status_code=500,
            detail="shopify_shop is not set. Go to Settings and save the shop domain."
        )
    try:
        collection_id = request.collection_id or settings.default_collection_id
        result = await shopify_service.fetch_and_store_collection(
            db=db,
            collection_id=collection_id,
            exclude_title_contains=request.exclude_title_contains
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"[shop: {shop}] {e}")


@router.post("/fetch-all-products", response_model=FetchCollectionResponse)
async def fetch_all_products(db: Session = Depends(get_db)):
    """Fetch ALL products from the Shopify store (entire catalogue)."""
    shop = settings.get_shopify_shop()
    if not shop:
        raise HTTPException(status_code=500, detail="shopify_shop is not set.")
    try:
        result = await shopify_service.fetch_all_products(db=db)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"[shop: {shop}] {e}")


@router.get("/products", response_model=List[ProductResponse])
async def get_products(
    collection_id: Optional[str] = None,
    status: Optional[str] = None,
    template_suffix: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """Get products from database."""
    products = shopify_service.get_products(
        db=db,
        collection_id=collection_id,
        template_suffix=template_suffix,
        status=status,
        search=search,
        skip=skip,
        limit=limit
    )
    return products


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get a single product by ID."""
    product = shopify_service.get_product_by_id(db=db, product_id=product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/products/shopify/{shopify_id}", response_model=ProductResponse)
async def get_product_by_shopify_id(
    shopify_id: str,
    db: Session = Depends(get_db)
):
    """Get a product by Shopify ID."""
    product = shopify_service.get_product_by_shopify_id(db=db, shopify_id=shopify_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("/sync-collection/{collection_id}")
async def sync_collection(
    collection_id: str,
    exclude_title_contains: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Sync a collection from Shopify to local database.
    Updates existing products and adds new ones.
    """
    try:
        result = await shopify_service.sync_collection(
            db=db,
            collection_id=collection_id,
            exclude_title_contains=exclude_title_contains
        )
        return {
            "message": "Collection synced successfully",
            "collection_id": collection_id,
            **result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/products/{product_id}")
async def delete_product(
    product_id: int,
    db: Session = Depends(get_db)
):
    """Delete a product from database."""
    success = shopify_service.delete_product(db=db, product_id=product_id)
    if not success:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deleted successfully"}


@router.put("/variants/{variant_id}")
async def update_variant_price(
    variant_id: int,
    price: Optional[float] = None,
    competitor_name: Optional[str] = Query(None),
    competitor_price: Optional[float] = Query(None),
    change_type: Optional[str] = Query("manual_update"),
    db: Session = Depends(get_db)
):
    """Update a variant price in both database and Shopify, with logging."""
    from app.models import Variant, PriceChangeLog
    
    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    
    old_price = variant.price
    
    if price is not None:
        # Update Shopify first using GraphQL mutation
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()
        
        if not shop or not token:
            raise HTTPException(status_code=500, detail="Shopify credentials not configured")
        
        graphql_url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
        
        mutation = """
        mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
          productVariantsBulkUpdate(productId: $productId, variants: $variants) {
            productVariants { id price compareAtPrice }
            userErrors { field message }
          }
        }
        """
        
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json"
        }
        
        # Get the product's Shopify ID
        product = variant.product
        
        response = requests.post(
            graphql_url,
            json={
                "query": mutation,
                "variables": {
                    "productId": product.shopify_id,
                    "variants": [
                        {
                            "id": variant.shopify_id,
                            "price": str(price),
                            "compareAtPrice": None
                        }
                    ]
                }
            },
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        
        if "errors" in result:
            raise HTTPException(status_code=500, detail=f"GraphQL errors: {result['errors']}")
        
        # Check for user errors from the mutation
        bulk_result = result.get("data", {}).get("productVariantsBulkUpdate", {})
        user_errors = bulk_result.get("userErrors", [])
        if user_errors:
            raise HTTPException(status_code=500, detail=f"Shopify update failed: {user_errors}")
        
        # Update local database
        variant.price = price
        variant.updated_at = datetime.utcnow()
        
        # Log the price change
        log_entry = PriceChangeLog(
            product_shopify_id=product.shopify_id,
            variant_shopify_id=variant.shopify_id,
            product_title=product.title,
            variant_title=variant.title,
            old_price=old_price,
            new_price=price,
            price_delta=price - old_price,
            change_type=change_type,
            competitor_name=competitor_name,
            competitor_price=competitor_price
        )
        db.add(log_entry)
        
        db.commit()
    
    return {
        "message": "Variant updated successfully",
        "variant_id": variant_id,
        "price": variant.price,
        "old_price": old_price,
        "log_id": log_entry.id if price is not None else None
    }

@router.patch("/variants/{variant_id}/weight")
async def update_variant_weight(
    variant_id: int,
    weight_grams: float = Query(..., ge=0),
    db: Session = Depends(get_db)
):
    """Update a variant's weight_grams locally."""
    from app.models import Variant
    from datetime import datetime, timezone

    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")

    variant.weight_grams = weight_grams
    variant.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"variant_id": variant_id, "weight_grams": weight_grams}


@router.get("/variants/{variant_id}")
async def get_variant(
    variant_id: int,
    db: Session = Depends(get_db)
):
    """Get a variant by ID."""
    from app.models import Variant
    
    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    
    return {
        "id": variant.id,
        "shopify_id": variant.shopify_id,
        "product_id": variant.product_id,
        "price": float(variant.price) if variant.price else None,
        "compare_at_price": float(variant.compare_at_price) if variant.compare_at_price else None,
        "title": variant.title,
        "updated_at": variant.updated_at.isoformat() if variant.updated_at else None
    }


@router.post("/refresh-all-prices")
async def refresh_all_prices(db: Session = Depends(get_db)):
    """Refresh prices for all variants from Shopify GraphQL API."""
    from app.models import Variant, Product
    
    shop = settings.get_shopify_shop()
    token = settings.get_shopify_token()
    
    if not shop or not token:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")
    
    graphql_url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
    
    # Get all products with variants
    products = db.query(Product).all()
    if not products:
        return {
            "message": "No products to refresh",
            "updated_count": 0,
            "error_count": 0
        }
    
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }
    
    updated_count = 0
    error_count = 0
    
    # Fetch prices for each product
    for product in products:
        try:
            query = """
            query($id: ID!) {
              product(id: $id) {
                variants(first: 100) {
                  edges {
                    node {
                      id
                      price
                      compareAtPrice
                      inventoryQuantity
                    }
                  }
                }
              }
            }
            """
            
            response = requests.post(
                graphql_url,
                json={
                    "query": query,
                    "variables": {"id": product.shopify_id}
                },
                headers=headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if "errors" in result:
                error_count += 1
                continue
            
            # Update variant prices in database
            product_data = result.get("data", {}).get("product", {})
            variants_data = product_data.get("variants", {}).get("edges", [])
            
            for variant_edge in variants_data:
                variant_node = variant_edge.get("node", {})
                shopify_variant_id = variant_node.get("id", "")
                price = variant_node.get("price")
                compare_at_price = variant_node.get("compareAtPrice")
                inventory_quantity = variant_node.get("inventoryQuantity")
                
                # Find and update the variant in database
                variant = db.query(Variant).filter(
                    Variant.shopify_id == shopify_variant_id
                ).first()
                
                if variant and price is not None:
                    variant.price = float(price)
                    if compare_at_price:
                        variant.compare_at_price = float(compare_at_price)
                    if inventory_quantity is not None:
                        variant.inventory_quantity = int(inventory_quantity)
                    variant.updated_at = datetime.utcnow()
                    db.commit()
                    updated_count += 1
        
        except Exception as e:
            error_count += 1
            continue
    
    return {
        "message": "Prices refreshed from Shopify",
        "updated_count": updated_count,
        "error_count": error_count
    }


@router.post("/refresh-mapped-prices")
async def refresh_mapped_prices(db: Session = Depends(get_db)):
    """Refresh Shopify prices for all SNKRDUNK-mapped products only (fast)."""
    from app.models import Variant, Product, SnkrdunkMapping

    shop = settings.get_shopify_shop()
    token = settings.get_shopify_token()
    if not shop or not token:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")

    # Get unique product shopify IDs from active mappings
    mappings = db.query(SnkrdunkMapping).filter(SnkrdunkMapping.disabled == False).all()
    product_ids = list(set(m.product_shopify_id for m in mappings if m.product_shopify_id))
    if not product_ids:
        return {"updated_count": 0, "error_count": 0}

    graphql_url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    updated_count = 0
    error_count = 0

    for pid in product_ids:
        try:
            query = """
            query($id: ID!) {
              product(id: $id) {
                variants(first: 100) {
                  edges { node { id price compareAtPrice inventoryQuantity } }
                }
              }
            }
            """
            response = requests.post(
                graphql_url,
                json={"query": query, "variables": {"id": pid}},
                headers=headers, timeout=30
            )
            response.raise_for_status()
            result = response.json()
            if "errors" in result:
                error_count += 1
                continue

            for edge in result.get("data", {}).get("product", {}).get("variants", {}).get("edges", []):
                vn = edge["node"]
                variant = db.query(Variant).filter(Variant.shopify_id == vn["id"]).first()
                if variant and vn.get("price"):
                    variant.price = float(vn["price"])
                    if vn.get("compareAtPrice"):
                        variant.compare_at_price = float(vn["compareAtPrice"])
                    if vn.get("inventoryQuantity") is not None:
                        variant.inventory_quantity = int(vn["inventoryQuantity"])
                    updated_count += 1
        except Exception:
            error_count += 1

    db.commit()
    return {"updated_count": updated_count, "error_count": error_count}


@router.post("/products/{product_id}/refresh")
async def refresh_product(product_id: int, db: Session = Depends(get_db)):
    """Refresh prices and inventory for a single product from Shopify GraphQL."""
    from app.models import Variant, Product

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    shop = settings.get_shopify_shop()
    token = settings.get_shopify_token()
    if not shop or not token:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")

    graphql_url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    query = """
    query($id: ID!) {
      product(id: $id) {
        variants(first: 100) {
          edges {
            node { id price compareAtPrice inventoryQuantity }
          }
        }
      }
    }
    """

    response = requests.post(
        graphql_url,
        json={"query": query, "variables": {"id": product.shopify_id}},
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    result = response.json()

    if "errors" in result:
        raise HTTPException(status_code=500, detail=f"GraphQL errors: {result['errors']}")

    variants_data = result.get("data", {}).get("product", {}).get("variants", {}).get("edges", [])
    updated_count = 0

    for edge in variants_data:
        node = edge.get("node", {})
        variant = db.query(Variant).filter(Variant.shopify_id == node.get("id")).first()
        if variant and node.get("price") is not None:
            variant.price = float(node["price"])
            if node.get("compareAtPrice") is not None:
                variant.compare_at_price = float(node["compareAtPrice"])
            if node.get("inventoryQuantity") is not None:
                variant.inventory_quantity = int(node["inventoryQuantity"])
            variant.updated_at = datetime.utcnow()
            updated_count += 1

    db.commit()
    return {"message": "Product refreshed", "product_id": product_id, "updated_count": updated_count}


@router.post("/variants/{variant_id}/set-inventory")
async def set_variant_inventory(
    variant_id: int,
    body: SetInventoryRequest,
    db: Session = Depends(get_db)
):
    """Set inventory quantity for a variant on Shopify and update local DB."""
    from app.models import Variant

    variant = db.query(Variant).filter(Variant.id == variant_id).first()
    if not variant:
        raise HTTPException(status_code=404, detail="Variant not found")
    if not variant.inventory_item_id:
        raise HTTPException(status_code=400, detail="Variant has no inventory_item_id; sync collection first")

    shop = settings.get_shopify_shop()
    token = settings.get_shopify_token()
    if not shop or not token:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")

    graphql_url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    location_gid = f"gid://shopify/Location/{settings.location_id}"

    mutation = """
    mutation($input: InventorySetQuantitiesInput!) {
      inventorySetQuantities(input: $input) {
        inventoryAdjustmentGroup {
          changes { name quantityAfterChange }
        }
        userErrors { field message }
      }
    }
    """

    response = requests.post(
        graphql_url,
        json={
            "query": mutation,
            "variables": {
                "input": {
                    "name": "available",
                    "reason": "correction",
                    "quantities": [{
                        "inventoryItemId": variant.inventory_item_id,
                        "locationId": location_gid,
                        "quantity": body.quantity
                    }]
                }
            }
        },
        headers=headers,
        timeout=30
    )
    response.raise_for_status()
    result = response.json()

    if "errors" in result:
        raise HTTPException(status_code=500, detail=f"GraphQL errors: {result['errors']}")

    user_errors = result.get("data", {}).get("inventorySetQuantities", {}).get("userErrors", [])
    if user_errors:
        raise HTTPException(status_code=500, detail=f"Shopify error: {user_errors}")

    old_qty = variant.inventory_quantity
    variant.inventory_quantity = body.quantity
    variant.updated_at = datetime.utcnow()
    db.commit()

    return {"message": "Inventory updated", "variant_id": variant_id, "old_quantity": old_qty, "new_quantity": body.quantity}


@router.post("/clear-compare-at-prices")
async def clear_compare_at_prices(db: Session = Depends(get_db)):
    """Clear compare_at_price for all Booster Box variants on Shopify and in the local DB."""
    from app.models import Variant, Product
    from collections import defaultdict

    # Find all booster box variants that have a compare_at_price set
    variants = (
        db.query(Variant)
        .filter(Variant.title.ilike('%booster box%'))
        .filter(Variant.compare_at_price.isnot(None))
        .all()
    )

    if not variants:
        return {"message": "No booster box variants with compare-at prices found", "cleared": 0, "errors": []}

    shop = settings.get_shopify_shop()
    token = settings.get_shopify_token()
    if not shop or not token:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")

    graphql_url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
    headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}

    mutation = """
    mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkUpdate(productId: $productId, variants: $variants) {
        productVariants { id price compareAtPrice }
        userErrors { field message }
      }
    }
    """

    # Group variants by product for bulk updates
    grouped = defaultdict(list)
    for v in variants:
        grouped[v.product_id].append(v)

    cleared = 0
    errors = []

    for product_id, prod_variants in grouped.items():
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            errors.append(f"Product id={product_id} not found in DB")
            continue

        variant_inputs = [
            {"id": v.shopify_id, "price": str(v.price), "compareAtPrice": None}
            for v in prod_variants
        ]

        try:
            resp = requests.post(
                graphql_url,
                json={"query": mutation, "variables": {"productId": product.shopify_id, "variants": variant_inputs}},
                headers=headers,
                timeout=60
            )
            resp.raise_for_status()
            result = resp.json()

            if "errors" in result:
                errors.append(f"{product.title}: GraphQL errors: {result['errors']}")
                continue

            user_errors = result.get("data", {}).get("productVariantsBulkUpdate", {}).get("userErrors", [])
            if user_errors:
                errors.append(f"{product.title}: {user_errors}")
                continue

            for v in prod_variants:
                v.compare_at_price = None
                v.updated_at = datetime.utcnow()
            db.commit()
            cleared += len(prod_variants)

        except Exception as e:
            errors.append(f"{product.title}: {str(e)}")

    return {"message": "Compare-at prices cleared", "cleared": cleared, "errors": errors}


@router.get("/price-change-history")
async def get_price_change_history(
    product_id: Optional[str] = None,
    change_type: Optional[str] = None,
    limit: int = Query(100, le=500),
    skip: int = 0,
    db: Session = Depends(get_db)
):
    """Get price change history logs."""
    from app.models import PriceChangeLog
    
    query = db.query(PriceChangeLog).order_by(PriceChangeLog.created_at.desc())
    
    if product_id:
        query = query.filter(PriceChangeLog.product_shopify_id == product_id)
    
    if change_type:
        query = query.filter(PriceChangeLog.change_type == change_type)
    
    total = query.count()
    logs = query.offset(skip).limit(limit).all()
    
    return {
        "total": total,
        "logs": [
            {
                "id": log.id,
                "product_title": log.product_title,
                "variant_title": log.variant_title,
                "old_price": log.old_price,
                "new_price": log.new_price,
                "price_delta": log.price_delta,
                "change_type": log.change_type,
                "competitor_name": log.competitor_name,
                "competitor_price": log.competitor_price,
                "created_at": log.created_at.isoformat() if log.created_at else None
            }
            for log in logs
        ]
    }