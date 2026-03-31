"""Margin VAT service - bruktmomsordningen (used goods margin scheme).

When buying from private individuals, Norwegian businesses only pay 25% VAT
on the profit margin, not the full selling price. This service calculates
the effective Shopify tax rate per product, manages proof-of-purchase images,
and syncs products to the correct Shopify tax-override collections.
"""
import math
import os
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any

import requests
from fastapi import UploadFile
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sa_func

from app.models import MarginVatProduct, MarginVatProofImage, Product, Variant, Setting
from app.config import settings

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads" / "margin_vat"
ALLOWED_CONTENT_TYPES = {
    "image/jpeg", "image/png", "image/webp", "application/pdf",
}


class MarginVatService:
    """Service for margin VAT scheme operations."""

    # ── VAT Calculation ──────────────────────────────────────────────────

    @staticmethod
    def calculate_effective_rate(selling_price: float, purchase_price: float) -> dict:
        """Calculate the effective Shopify tax rate for the margin scheme.

        Norway uses tax-inclusive pricing. The margin (selling - purchase) is
        considered VAT-inclusive under the scheme.

        Shopify computes tax from an inclusive price as:
            tax = price * rate / (100 + rate)
        We need that to equal the margin VAT:
            vat_amount = margin * 25 / 125
        Solving: S * r / (100 + r) = margin / 5
            r = 100 * margin / (5 * S - margin)
        Bucket = ceil(rate) to nearest 1%.
        """
        if selling_price <= 0:
            return {"margin_nok": 0, "vat_amount_nok": 0, "effective_rate_pct": 0, "bucket_rate_pct": 0}

        margin = selling_price - purchase_price
        if margin <= 0:
            return {"margin_nok": 0, "vat_amount_nok": 0, "effective_rate_pct": 0, "bucket_rate_pct": 0}

        vat_amount = round(margin * 25 / 125, 2)
        denominator = 5 * selling_price - margin
        if denominator <= 0:
            return {"margin_nok": round(margin, 2), "vat_amount_nok": vat_amount, "effective_rate_pct": 25.0, "bucket_rate_pct": 25}

        effective_rate = 100 * margin / denominator
        bucket_rate = min(math.ceil(effective_rate), 25)  # cap at 25%

        return {
            "margin_nok": round(margin, 2),
            "vat_amount_nok": vat_amount,
            "effective_rate_pct": round(effective_rate, 4),
            "bucket_rate_pct": bucket_rate,
        }

    # ── CRUD ─────────────────────────────────────────────────────────────

    def create(self, db: Session, data: dict) -> MarginVatProduct:
        """Register a product under the margin VAT scheme.

        Can be created without a Shopify link (unlinked purchase record).
        Link to a Shopify product later via update().
        """
        purchase_price = data["purchase_price_nok"]
        variant = None
        product = None
        selling_price = 0

        # If linked to a Shopify product, look up details
        if data.get("variant_shopify_id"):
            variant = db.query(Variant).filter(
                Variant.shopify_id == data["variant_shopify_id"]
            ).first()
            if variant:
                product = db.query(Product).filter(Product.id == variant.product_id).first()
                selling_price = variant.price

        calc = self.calculate_effective_rate(selling_price, purchase_price) if selling_price > 0 else {
            "margin_nok": 0, "vat_amount_nok": 0, "effective_rate_pct": 0, "bucket_rate_pct": 0
        }

        mvp = MarginVatProduct(
            product_shopify_id=data.get("product_shopify_id"),
            variant_shopify_id=data.get("variant_shopify_id"),
            product_title=data.get("product_title") or (product.title if product else None),
            variant_title=variant.title if variant else None,
            sku=variant.sku if variant else None,
            image_url=product.image_url if product else None,
            purchase_price_nok=purchase_price,
            purchase_date=data.get("purchase_date"),
            seller_description=data.get("seller_description"),
            selling_price_nok=selling_price if selling_price > 0 else None,
            margin_nok=calc["margin_nok"],
            vat_amount_nok=calc["vat_amount_nok"],
            effective_rate_pct=calc["effective_rate_pct"],
            bucket_rate_pct=calc["bucket_rate_pct"],
            needs_reassignment=True if data.get("variant_shopify_id") else False,
            status="active",
            notes=data.get("notes"),
        )
        db.add(mvp)
        db.commit()
        db.refresh(mvp)
        return mvp

    def update(self, db: Session, mvp_id: int, data: dict) -> Optional[MarginVatProduct]:
        """Update a margin VAT product. Recalculates VAT if prices changed.

        If linking to a Shopify product for the first time (setting variant_shopify_id),
        populates cached fields from the variant/product.
        """
        mvp = db.query(MarginVatProduct).filter(MarginVatProduct.id == mvp_id).first()
        if not mvp:
            return None

        recalc_needed = False
        newly_linked = False

        # Check if we're linking to a Shopify product for the first time
        if data.get("variant_shopify_id") and not mvp.variant_shopify_id:
            newly_linked = True

        for key, value in data.items():
            if value is not None and hasattr(mvp, key):
                setattr(mvp, key, value)
                if key in ("purchase_price_nok", "selling_price_nok"):
                    recalc_needed = True

        # If newly linked, populate cached fields from Shopify data
        if newly_linked and mvp.variant_shopify_id:
            variant = db.query(Variant).filter(Variant.shopify_id == mvp.variant_shopify_id).first()
            if variant:
                product = db.query(Product).filter(Product.id == variant.product_id).first()
                mvp.variant_title = variant.title
                mvp.sku = variant.sku
                mvp.selling_price_nok = variant.price
                if product:
                    if not mvp.product_shopify_id:
                        mvp.product_shopify_id = product.shopify_id
                    if not mvp.product_title or mvp.product_title == data.get("product_title"):
                        mvp.product_title = product.title
                    mvp.image_url = product.image_url
                recalc_needed = True
                mvp.needs_reassignment = True

        if recalc_needed and mvp.selling_price_nok and mvp.purchase_price_nok:
            old_bucket = mvp.bucket_rate_pct
            calc = self.calculate_effective_rate(mvp.selling_price_nok, mvp.purchase_price_nok)
            mvp.margin_nok = calc["margin_nok"]
            mvp.vat_amount_nok = calc["vat_amount_nok"]
            mvp.effective_rate_pct = calc["effective_rate_pct"]
            mvp.bucket_rate_pct = calc["bucket_rate_pct"]
            if old_bucket != calc["bucket_rate_pct"]:
                mvp.needs_reassignment = True

        db.commit()
        db.refresh(mvp)
        return mvp

    def get_list(
        self, db: Session,
        status: Optional[str] = None,
        needs_reassignment: Optional[bool] = None,
    ) -> List[MarginVatProduct]:
        """List margin VAT products with optional filters."""
        q = db.query(MarginVatProduct).options(joinedload(MarginVatProduct.proof_images))
        if status:
            q = q.filter(MarginVatProduct.status == status)
        if needs_reassignment is not None:
            q = q.filter(MarginVatProduct.needs_reassignment == needs_reassignment)
        return q.order_by(MarginVatProduct.created_at.desc()).all()

    def get(self, db: Session, mvp_id: int) -> Optional[MarginVatProduct]:
        """Get single margin VAT product with proof images."""
        return (
            db.query(MarginVatProduct)
            .options(joinedload(MarginVatProduct.proof_images))
            .filter(MarginVatProduct.id == mvp_id)
            .first()
        )

    def delete(self, db: Session, mvp_id: int) -> bool:
        """Delete a margin VAT product and its proof images from disk."""
        mvp = db.query(MarginVatProduct).options(
            joinedload(MarginVatProduct.proof_images)
        ).filter(MarginVatProduct.id == mvp_id).first()
        if not mvp:
            return False

        # Remove files from disk
        for img in mvp.proof_images:
            full_path = UPLOADS_DIR / img.stored_filename
            if full_path.exists():
                full_path.unlink()

        db.delete(mvp)
        db.commit()
        return True

    # ── Proof Images ─────────────────────────────────────────────────────

    def upload_proof_image(
        self, db: Session, mvp_id: int, file: UploadFile, description: Optional[str] = None
    ) -> Optional[MarginVatProofImage]:
        """Save an uploaded proof image and create a DB record."""
        mvp = db.query(MarginVatProduct).filter(MarginVatProduct.id == mvp_id).first()
        if not mvp:
            return None

        content_type = file.content_type or ""
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"File type '{content_type}' not allowed. Allowed: {', '.join(ALLOWED_CONTENT_TYPES)}")

        # Determine extension
        ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
        ext = ext_map.get(content_type, ".bin")

        stored_filename = f"{uuid.uuid4()}{ext}"
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        full_path = UPLOADS_DIR / stored_filename

        # Write file to disk
        content = file.file.read()
        with open(full_path, "wb") as f:
            f.write(content)

        img = MarginVatProofImage(
            margin_vat_product_id=mvp_id,
            filename=file.filename or stored_filename,
            stored_filename=stored_filename,
            file_path=f"margin_vat/{stored_filename}",
            content_type=content_type,
            file_size_bytes=len(content),
            description=description,
        )
        db.add(img)
        db.commit()
        db.refresh(img)
        return img

    def delete_proof_image(self, db: Session, image_id: int) -> bool:
        """Delete a proof image from disk and DB."""
        img = db.query(MarginVatProofImage).filter(MarginVatProofImage.id == image_id).first()
        if not img:
            return False

        full_path = UPLOADS_DIR / img.stored_filename
        if full_path.exists():
            full_path.unlink()

        db.delete(img)
        db.commit()
        return True

    # ── Recalculation ────────────────────────────────────────────────────

    def recalculate_all(self, db: Session) -> dict:
        """Recalculate VAT for all active products. Returns summary."""
        products = db.query(MarginVatProduct).filter(
            MarginVatProduct.status == "active"
        ).all()

        updated = 0
        bucket_changed = 0

        for mvp in products:
            # Refresh selling price from Variant table
            variant = db.query(Variant).filter(
                Variant.shopify_id == mvp.variant_shopify_id
            ).first()
            if variant:
                mvp.selling_price_nok = variant.price

            if mvp.selling_price_nok and mvp.purchase_price_nok:
                old_bucket = mvp.bucket_rate_pct
                calc = self.calculate_effective_rate(mvp.selling_price_nok, mvp.purchase_price_nok)
                mvp.margin_nok = calc["margin_nok"]
                mvp.vat_amount_nok = calc["vat_amount_nok"]
                mvp.effective_rate_pct = calc["effective_rate_pct"]
                mvp.bucket_rate_pct = calc["bucket_rate_pct"]
                updated += 1
                if old_bucket != calc["bucket_rate_pct"]:
                    mvp.needs_reassignment = True
                    bucket_changed += 1

        db.commit()
        return {"updated": updated, "bucket_changed": bucket_changed}

    def recalculate_for_variant(self, db: Session, variant_shopify_id: str, new_price: float) -> None:
        """Recalculate VAT for a specific variant when its price changes."""
        mvp = db.query(MarginVatProduct).filter(
            MarginVatProduct.variant_shopify_id == variant_shopify_id,
            MarginVatProduct.status == "active",
        ).first()
        if not mvp:
            return

        old_bucket = mvp.bucket_rate_pct
        mvp.selling_price_nok = new_price
        calc = self.calculate_effective_rate(new_price, mvp.purchase_price_nok)
        mvp.margin_nok = calc["margin_nok"]
        mvp.vat_amount_nok = calc["vat_amount_nok"]
        mvp.effective_rate_pct = calc["effective_rate_pct"]
        mvp.bucket_rate_pct = calc["bucket_rate_pct"]
        if old_bucket != calc["bucket_rate_pct"]:
            mvp.needs_reassignment = True

    # ── Bucket Summary ───────────────────────────────────────────────────

    def get_bucket_summary(self, db: Session) -> List[dict]:
        """Group active products by bucket and show collection status."""
        rows = (
            db.query(
                MarginVatProduct.bucket_rate_pct,
                sa_func.count(MarginVatProduct.id).label("cnt"),
            )
            .filter(MarginVatProduct.status == "active")
            .group_by(MarginVatProduct.bucket_rate_pct)
            .order_by(MarginVatProduct.bucket_rate_pct)
            .all()
        )

        result = []
        for bucket, count in rows:
            coll_id = self._get_collection_id_for_bucket(db, bucket)
            result.append({
                "bucket_rate_pct": bucket,
                "product_count": count,
                "collection_configured": coll_id is not None,
                "collection_name": f"{bucket}% MVA" if bucket is not None else None,
            })
        return result

    # ── Shopify Collection Sync ──────────────────────────────────────────

    def _get_collection_id_for_bucket(self, db: Session, bucket: int) -> Optional[str]:
        """Look up the Shopify collection ID for a given bucket rate from settings."""
        setting = db.query(Setting).filter(Setting.key == f"mva_collection_{bucket}").first()
        return setting.value if setting else None

    def _graphql_request(self, query: str, variables: dict = None) -> dict:
        """Make a GraphQL request to Shopify (reuses ShopifyService pattern)."""
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()
        if not shop or not token:
            raise Exception("Shopify credentials not configured.")

        url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json",
        }
        response = requests.post(
            url,
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=60,
            allow_redirects=False,
        )
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        return data.get("data", {})

    def _add_products_to_collection(self, collection_id: str, product_gids: List[str]) -> dict:
        """Add products to a Shopify collection."""
        mutation = """
        mutation($id: ID!, $productIds: [ID!]!) {
          collectionAddProductsV2(id: $id, productIds: $productIds) {
            job { id }
            userErrors { field message }
          }
        }
        """
        result = self._graphql_request(mutation, {
            "id": f"gid://shopify/Collection/{collection_id}",
            "productIds": product_gids,
        })
        errors = result.get("collectionAddProductsV2", {}).get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {errors}")
        return result

    def _remove_products_from_collection(self, collection_id: str, product_gids: List[str]) -> dict:
        """Remove products from a Shopify collection."""
        mutation = """
        mutation($id: ID!, $productIds: [ID!]!) {
          collectionRemoveProducts(id: $id, productIds: $productIds) {
            job { id }
            userErrors { field message }
          }
        }
        """
        result = self._graphql_request(mutation, {
            "id": f"gid://shopify/Collection/{collection_id}",
            "productIds": product_gids,
        })
        errors = result.get("collectionRemoveProducts", {}).get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {errors}")
        return result

    def sync_collections(self, db: Session) -> dict:
        """Sync all margin VAT products to their correct Shopify tax collections.

        For each product:
        1. Determine the correct bucket collection from settings
        2. If the product is already in the correct collection, skip
        3. Remove from old collection (if any)
        4. Add to new collection
        5. Update DB and clear needs_reassignment
        """
        products = db.query(MarginVatProduct).filter(
            MarginVatProduct.status == "active",
        ).all()

        added = 0
        removed = 0
        already_correct = 0
        errors = []

        # Group products by target bucket for batch operations
        bucket_to_products: Dict[int, List[MarginVatProduct]] = {}
        for mvp in products:
            bucket = mvp.bucket_rate_pct
            if bucket is None:
                continue
            bucket_to_products.setdefault(bucket, []).append(mvp)

        for bucket, mvps in bucket_to_products.items():
            target_collection_id = self._get_collection_id_for_bucket(db, bucket)
            if not target_collection_id:
                errors.append(f"No collection configured for {bucket}% bucket. Set mva_collection_{bucket} in Settings.")
                continue

            target_name = f"{bucket}% MVA"

            # Separate products that need moving vs already correct
            to_add = []
            for mvp in mvps:
                if mvp.tax_collection_id == target_collection_id and not mvp.needs_reassignment:
                    already_correct += 1
                    continue
                to_add.append(mvp)

            if not to_add:
                continue

            # Remove from old collections (group by old collection)
            old_collections: Dict[str, List[str]] = {}
            for mvp in to_add:
                if mvp.tax_collection_id and mvp.tax_collection_id != target_collection_id:
                    gid = f"gid://shopify/Product/{mvp.product_shopify_id}"
                    old_collections.setdefault(mvp.tax_collection_id, []).append(gid)

            for old_coll_id, gids in old_collections.items():
                try:
                    self._remove_products_from_collection(old_coll_id, gids)
                    removed += len(gids)
                except Exception as e:
                    errors.append(f"Failed removing from collection {old_coll_id}: {e}")

            # Add to target collection
            add_gids = [f"gid://shopify/Product/{mvp.product_shopify_id}" for mvp in to_add]
            # Deduplicate (multiple variants of same product)
            add_gids = list(set(add_gids))

            try:
                self._add_products_to_collection(target_collection_id, add_gids)
                added += len(add_gids)
            except Exception as e:
                errors.append(f"Failed adding to {target_name}: {e}")
                continue

            # Update DB records
            for mvp in to_add:
                mvp.tax_collection_id = target_collection_id
                mvp.tax_collection_name = target_name
                mvp.needs_reassignment = False

        db.commit()

        return {
            "products_added": added,
            "products_removed": removed,
            "products_already_correct": already_correct,
            "errors": errors,
        }


    # ── Shopify Product Operations ──────────────────────────────────────────

    def fetch_product_detail(self, product_shopify_id: str) -> dict:
        """Fetch full product details from Shopify for templating."""
        # Accept either a raw numeric ID or a full GID
        gid = product_shopify_id if product_shopify_id.startswith("gid://") else f"gid://shopify/Product/{product_shopify_id}"

        query = """
        query($id: ID!) {
          product(id: $id) {
            id title handle status
            descriptionHtml
            vendor
            productType
            tags
            featuredImage { url }
            images(first: 20) { edges { node { url altText } } }
            variants(first: 100) {
              edges { node {
                id title price compareAtPrice sku
                inventoryItem { id measurement { weight { unit value } } }
              } }
            }
          }
        }
        """
        data = self._graphql_request(query, {"id": gid})
        p = data.get("product")
        if not p:
            raise Exception("Product not found on Shopify")

        variants = []
        for e in p.get("variants", {}).get("edges", []):
            v = e["node"]
            weight = None
            inv = v.get("inventoryItem") or {}
            meas = inv.get("measurement") or {}
            w = meas.get("weight") or {}
            if w.get("value"):
                weight = float(w["value"])
                if w.get("unit") == "KILOGRAMS":
                    weight *= 1000
            variants.append({
                "id": v["id"], "title": v.get("title"), "price": v.get("price"),
                "compare_at_price": v.get("compareAtPrice"), "sku": v.get("sku"),
                "weight_grams": weight,
            })

        images = [e["node"]["url"] for e in p.get("images", {}).get("edges", [])]

        return {
            "shopify_id": p["id"],
            "title": p["title"],
            "handle": p.get("handle"),
            "status": p.get("status"),
            "description": p.get("descriptionHtml") or "",
            "vendor": p.get("vendor") or "",
            "product_type": p.get("productType") or "",
            "tags": p.get("tags") or [],
            "image_url": (p.get("featuredImage") or {}).get("url"),
            "images": images,
            "variants": variants,
        }

    def create_shopify_product(self, db: Session, data: dict) -> dict:
        """Create a new product on Shopify as DRAFT.

        In API 2026-01+, variants and images are NOT part of ProductInput.
        We create the product first, then update the variant price/SKU,
        then attach images via productCreateMedia.
        """
        product_input = {
            "title": data["title"],
            "status": "DRAFT",
        }
        if data.get("product_type"):
            product_input["productType"] = data["product_type"]
        if data.get("vendor"):
            product_input["vendor"] = data["vendor"]
        if data.get("tags"):
            product_input["tags"] = data["tags"] if isinstance(data["tags"], list) else [t.strip() for t in data["tags"].split(",")]
        if data.get("description"):
            product_input["descriptionHtml"] = data["description"]

        # Step 1: Create the product (comes with a default variant)
        create_mutation = """
        mutation($input: ProductInput!) {
          productCreate(input: $input) {
            product {
              id title handle status
              featuredImage { url }
              variants(first: 10) {
                edges { node { id title price sku } }
              }
            }
            userErrors { field message }
          }
        }
        """
        result = self._graphql_request(create_mutation, {"input": product_input})
        pc = result.get("productCreate", {})
        errors = pc.get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {[e['message'] for e in errors]}")

        product = pc.get("product", {})
        shopify_id = product["id"]

        # Step 2: Update the default variant with price and SKU
        variant_edges = product.get("variants", {}).get("edges", [])
        if variant_edges and (data.get("price") or data.get("sku")):
            variant_id = variant_edges[0]["node"]["id"]
            variant_input = {"id": variant_id}
            if data.get("price"):
                variant_input["price"] = str(data["price"])
            if data.get("sku"):
                variant_input["sku"] = data["sku"]

            update_mutation = """
            mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants { id price sku }
                userErrors { field message }
              }
            }
            """
            self._graphql_request(update_mutation, {
                "productId": shopify_id,
                "variants": [variant_input],
            })
            # Update the local variant data for return value
            if data.get("price"):
                variant_edges[0]["node"]["price"] = str(data["price"])
            if data.get("sku"):
                variant_edges[0]["node"]["sku"] = data["sku"]

        # Step 3: Attach images via productCreateMedia
        if data.get("images"):
            media_input = [
                {"originalSource": url, "mediaContentType": "IMAGE"}
                for url in data["images"] if url
            ]
            if media_input:
                media_mutation = """
                mutation($productId: ID!, $media: [CreateMediaInput!]!) {
                  productCreateMedia(productId: $productId, media: $media) {
                    media { id }
                    mediaUserErrors { field message }
                  }
                }
                """
                try:
                    self._graphql_request(media_mutation, {
                        "productId": shopify_id,
                        "media": media_input,
                    })
                except Exception:
                    pass  # Image attach is non-critical

        # Store in local database
        db_product = Product(
            shopify_id=shopify_id,
            title=product["title"],
            handle=product["handle"],
            status=product["status"].lower(),
            image_url=(product.get("featuredImage") or {}).get("url"),
        )
        db.add(db_product)
        db.flush()

        variants_data = []
        for edge in variant_edges:
            v = edge["node"]
            db_variant = Variant(
                shopify_id=v["id"],
                product_id=db_product.id,
                title=v.get("title", "Default Title"),
                price=float(v.get("price", 0)),
                sku=v.get("sku"),
            )
            db.add(db_variant)
            variants_data.append(v)

        db.commit()

        return {
            "product_shopify_id": shopify_id,
            "product_title": product["title"],
            "handle": product["handle"],
            "status": product["status"],
            "variants": variants_data,
            "local_product_id": db_product.id,
        }

    def update_shopify_product(self, db: Session, product_shopify_id: str, data: dict) -> dict:
        """Update an existing product on Shopify."""
        product_input = {"id": product_shopify_id}
        if data.get("title"):
            product_input["title"] = data["title"]
        if data.get("status"):
            product_input["status"] = data["status"].upper()
        if data.get("description") is not None:
            product_input["descriptionHtml"] = data["description"]
        if data.get("vendor") is not None:
            product_input["vendor"] = data["vendor"]
        if data.get("product_type") is not None:
            product_input["productType"] = data["product_type"]
        if data.get("tags") is not None:
            product_input["tags"] = data["tags"] if isinstance(data["tags"], list) else [t.strip() for t in data["tags"].split(",")]

        mutation = """
        mutation($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id title status handle }
            userErrors { field message }
          }
        }
        """
        result = self._graphql_request(mutation, {"input": product_input})
        pu = result.get("productUpdate", {})
        errors = pu.get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {[e['message'] for e in errors]}")

        product = pu.get("product", {})

        # Update price if provided
        if data.get("price") and data.get("variant_shopify_id"):
            price_mutation = """
            mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants { id price }
                userErrors { field message }
              }
            }
            """
            self._graphql_request(price_mutation, {
                "productId": product_shopify_id,
                "variants": [{"id": data["variant_shopify_id"], "price": str(data["price"])}],
            })
            variant = db.query(Variant).filter(Variant.shopify_id == data["variant_shopify_id"]).first()
            if variant:
                variant.price = float(data["price"])

        # Update local DB
        db_product = db.query(Product).filter(Product.shopify_id == product_shopify_id).first()
        if db_product:
            if data.get("title"):
                db_product.title = data["title"]
            if data.get("status"):
                db_product.status = data["status"].lower()

        db.commit()
        return {
            "product_shopify_id": product.get("id"),
            "title": product.get("title"),
            "status": product.get("status"),
        }


margin_vat_service = MarginVatService()
