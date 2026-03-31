"""Margin VAT service - bruktmomsordningen (used goods margin scheme).

Manages purchases from private individuals, VAT calculations, proof images,
and Shopify tax-override collection sync.
"""
import math
import uuid
from pathlib import Path
from typing import Optional, List, Dict

import requests
from fastapi import UploadFile
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func as sa_func

from app.models import MarginVatPurchase, MarginVatItem, MarginVatProofImage, Product, Variant, Setting
from app.config import settings

UPLOADS_DIR = Path(__file__).parent.parent.parent / "uploads" / "margin_vat"
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


class MarginVatService:

    # ── VAT Calculation ──────────────────────────────────────────────────

    @staticmethod
    def calculate_effective_rate(selling_price: float, purchase_price: float) -> dict:
        """Calculate the effective Shopify tax rate for the margin scheme.

        rate = 100 * margin / (5 * selling_price - margin)
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
        bucket_rate = min(math.ceil(effective_rate), 25)
        return {
            "margin_nok": round(margin, 2),
            "vat_amount_nok": vat_amount,
            "effective_rate_pct": round(effective_rate, 4),
            "bucket_rate_pct": bucket_rate,
        }

    # ── Purchases ────────────────────────────────────────────────────────

    def create_purchase(self, db: Session, data: dict) -> MarginVatPurchase:
        """Create a purchase with line items."""
        purchase = MarginVatPurchase(
            seller=data.get("seller"),
            purchase_date=data.get("purchase_date"),
            notes=data.get("notes"),
        )
        db.add(purchase)
        db.flush()

        for item_data in data.get("items", []):
            item = MarginVatItem(
                purchase_id=purchase.id,
                description=item_data["description"],
                quantity=item_data.get("quantity", 1),
                unit_price_nok=item_data["unit_price_nok"],
            )
            db.add(item)

        db.commit()
        db.refresh(purchase)
        return purchase

    def get_purchases(self, db: Session, status: Optional[str] = None) -> List[MarginVatPurchase]:
        q = db.query(MarginVatPurchase).options(
            joinedload(MarginVatPurchase.items),
            joinedload(MarginVatPurchase.proof_images),
        )
        if status:
            q = q.filter(MarginVatPurchase.status == status)
        return q.order_by(MarginVatPurchase.created_at.desc()).all()

    def get_purchase(self, db: Session, purchase_id: int) -> Optional[MarginVatPurchase]:
        return db.query(MarginVatPurchase).options(
            joinedload(MarginVatPurchase.items),
            joinedload(MarginVatPurchase.proof_images),
        ).filter(MarginVatPurchase.id == purchase_id).first()

    def delete_purchase(self, db: Session, purchase_id: int) -> bool:
        p = self.get_purchase(db, purchase_id)
        if not p:
            return False
        for img in p.proof_images:
            fp = UPLOADS_DIR / img.stored_filename
            if fp.exists():
                fp.unlink()
        db.delete(p)
        db.commit()
        return True

    # ── Items ────────────────────────────────────────────────────────────

    def update_item(self, db: Session, item_id: int, data: dict) -> Optional[MarginVatItem]:
        item = db.query(MarginVatItem).filter(MarginVatItem.id == item_id).first()
        if not item:
            return None

        newly_linked = False
        if data.get("variant_shopify_id") and not item.variant_shopify_id:
            newly_linked = True

        for key, value in data.items():
            if value is not None and hasattr(item, key):
                setattr(item, key, value)

        # Populate cached fields when linking
        if newly_linked and item.variant_shopify_id:
            variant = db.query(Variant).filter(Variant.shopify_id == item.variant_shopify_id).first()
            if variant:
                product = db.query(Product).filter(Product.id == variant.product_id).first()
                item.variant_title = variant.title
                item.sku = variant.sku
                item.selling_price_nok = variant.price
                if product:
                    if not item.product_shopify_id:
                        item.product_shopify_id = product.shopify_id
                    item.product_title = product.title
                    item.image_url = product.image_url

        # Recalculate VAT if we have both prices
        if item.selling_price_nok and item.unit_price_nok:
            calc = self.calculate_effective_rate(item.selling_price_nok, item.unit_price_nok)
            item.margin_nok = calc["margin_nok"]
            item.vat_amount_nok = calc["vat_amount_nok"]
            item.effective_rate_pct = calc["effective_rate_pct"]
            old_bucket = item.bucket_rate_pct
            item.bucket_rate_pct = calc["bucket_rate_pct"]
            if old_bucket != calc["bucket_rate_pct"]:
                item.needs_reassignment = True

        db.commit()
        db.refresh(item)
        return item

    def get_all_items(self, db: Session, status: Optional[str] = None, needs_reassignment: Optional[bool] = None) -> List[MarginVatItem]:
        q = db.query(MarginVatItem)
        if status:
            q = q.filter(MarginVatItem.status == status)
        if needs_reassignment is not None:
            q = q.filter(MarginVatItem.needs_reassignment == needs_reassignment)
        return q.order_by(MarginVatItem.created_at.desc()).all()

    # ── Proof Images ─────────────────────────────────────────────────────

    def upload_proof_image(self, db: Session, purchase_id: int, file: UploadFile) -> Optional[MarginVatProofImage]:
        purchase = db.query(MarginVatPurchase).filter(MarginVatPurchase.id == purchase_id).first()
        if not purchase:
            return None
        content_type = file.content_type or ""
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"File type '{content_type}' not allowed.")
        ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
        ext = ext_map.get(content_type, ".bin")
        stored_filename = f"{uuid.uuid4()}{ext}"
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        content = file.file.read()
        with open(UPLOADS_DIR / stored_filename, "wb") as f:
            f.write(content)
        img = MarginVatProofImage(
            purchase_id=purchase_id,
            filename=file.filename or stored_filename,
            stored_filename=stored_filename,
            file_path=f"margin_vat/{stored_filename}",
            content_type=content_type,
            file_size_bytes=len(content),
        )
        db.add(img)
        db.commit()
        db.refresh(img)
        return img

    def delete_proof_image(self, db: Session, image_id: int) -> bool:
        img = db.query(MarginVatProofImage).filter(MarginVatProofImage.id == image_id).first()
        if not img:
            return False
        fp = UPLOADS_DIR / img.stored_filename
        if fp.exists():
            fp.unlink()
        db.delete(img)
        db.commit()
        return True

    # ── Recalculation ────────────────────────────────────────────────────

    def recalculate_all(self, db: Session) -> dict:
        items = db.query(MarginVatItem).filter(MarginVatItem.status == "active").all()
        updated = 0
        bucket_changed = 0
        for item in items:
            if item.variant_shopify_id:
                variant = db.query(Variant).filter(Variant.shopify_id == item.variant_shopify_id).first()
                if variant:
                    item.selling_price_nok = variant.price
            if item.selling_price_nok and item.unit_price_nok:
                old_bucket = item.bucket_rate_pct
                calc = self.calculate_effective_rate(item.selling_price_nok, item.unit_price_nok)
                item.margin_nok = calc["margin_nok"]
                item.vat_amount_nok = calc["vat_amount_nok"]
                item.effective_rate_pct = calc["effective_rate_pct"]
                item.bucket_rate_pct = calc["bucket_rate_pct"]
                updated += 1
                if old_bucket != calc["bucket_rate_pct"]:
                    item.needs_reassignment = True
                    bucket_changed += 1
        db.commit()
        return {"updated": updated, "bucket_changed": bucket_changed}

    def recalculate_for_variant(self, db: Session, variant_shopify_id: str, new_price: float) -> None:
        item = db.query(MarginVatItem).filter(
            MarginVatItem.variant_shopify_id == variant_shopify_id,
            MarginVatItem.status == "active",
        ).first()
        if not item:
            return
        old_bucket = item.bucket_rate_pct
        item.selling_price_nok = new_price
        calc = self.calculate_effective_rate(new_price, item.unit_price_nok)
        item.margin_nok = calc["margin_nok"]
        item.vat_amount_nok = calc["vat_amount_nok"]
        item.effective_rate_pct = calc["effective_rate_pct"]
        item.bucket_rate_pct = calc["bucket_rate_pct"]
        if old_bucket != calc["bucket_rate_pct"]:
            item.needs_reassignment = True

    # ── Bucket Summary ───────────────────────────────────────────────────

    def get_bucket_summary(self, db: Session) -> List[dict]:
        rows = (
            db.query(MarginVatItem.bucket_rate_pct, sa_func.count(MarginVatItem.id).label("cnt"))
            .filter(MarginVatItem.status == "active", MarginVatItem.bucket_rate_pct.isnot(None))
            .group_by(MarginVatItem.bucket_rate_pct)
            .order_by(MarginVatItem.bucket_rate_pct)
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
        setting = db.query(Setting).filter(Setting.key == f"mva_collection_{bucket}").first()
        return setting.value if setting else None

    def _graphql_request(self, query: str, variables: dict = None) -> dict:
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()
        if not shop or not token:
            raise Exception("Shopify credentials not configured.")
        url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
        headers = {"X-Shopify-Access-Token": token, "Content-Type": "application/json"}
        response = requests.post(url, json={"query": query, "variables": variables or {}}, headers=headers, timeout=60, allow_redirects=False)
        response.raise_for_status()
        data = response.json()
        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        return data.get("data", {})

    def _add_products_to_collection(self, collection_id: str, product_gids: List[str]) -> dict:
        mutation = """
        mutation($id: ID!, $productIds: [ID!]!) {
          collectionAddProductsV2(id: $id, productIds: $productIds) { job { id } userErrors { field message } }
        }"""
        result = self._graphql_request(mutation, {"id": f"gid://shopify/Collection/{collection_id}", "productIds": product_gids})
        errors = result.get("collectionAddProductsV2", {}).get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {errors}")
        return result

    def _remove_products_from_collection(self, collection_id: str, product_gids: List[str]) -> dict:
        mutation = """
        mutation($id: ID!, $productIds: [ID!]!) {
          collectionRemoveProducts(id: $id, productIds: $productIds) { job { id } userErrors { field message } }
        }"""
        result = self._graphql_request(mutation, {"id": f"gid://shopify/Collection/{collection_id}", "productIds": product_gids})
        errors = result.get("collectionRemoveProducts", {}).get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {errors}")
        return result

    def sync_collections(self, db: Session) -> dict:
        items = db.query(MarginVatItem).filter(
            MarginVatItem.status == "active",
            MarginVatItem.product_shopify_id.isnot(None),
            MarginVatItem.bucket_rate_pct.isnot(None),
        ).all()
        added = removed = already_correct = 0
        errors = []
        bucket_to_items: Dict[int, List[MarginVatItem]] = {}
        for item in items:
            bucket_to_items.setdefault(item.bucket_rate_pct, []).append(item)

        for bucket, bucket_items in bucket_to_items.items():
            target_coll = self._get_collection_id_for_bucket(db, bucket)
            if not target_coll:
                errors.append(f"No collection for {bucket}% bucket.")
                continue
            to_add = [it for it in bucket_items if it.tax_collection_id != target_coll or it.needs_reassignment]
            if not to_add:
                already_correct += len(bucket_items)
                continue
            # Remove from old collections
            old_colls: Dict[str, List[str]] = {}
            for it in to_add:
                if it.tax_collection_id and it.tax_collection_id != target_coll:
                    old_colls.setdefault(it.tax_collection_id, []).append(it.product_shopify_id)
            for old_cid, gids in old_colls.items():
                try:
                    self._remove_products_from_collection(old_cid, list(set(gids)))
                    removed += len(gids)
                except Exception as e:
                    errors.append(str(e))
            # Add to target
            add_gids = list(set(it.product_shopify_id for it in to_add))
            try:
                self._add_products_to_collection(target_coll, add_gids)
                added += len(add_gids)
            except Exception as e:
                errors.append(str(e))
                continue
            for it in to_add:
                it.tax_collection_id = target_coll
                it.tax_collection_name = f"{bucket}% MVA"
                it.needs_reassignment = False
        db.commit()
        return {"products_added": added, "products_removed": removed, "products_already_correct": already_correct, "errors": errors}

    # ── Shopify Product Operations ──────────────────────────────────────

    def fetch_product_detail(self, product_shopify_id: str) -> dict:
        gid = product_shopify_id if product_shopify_id.startswith("gid://") else f"gid://shopify/Product/{product_shopify_id}"
        query = """
        query($id: ID!) {
          product(id: $id) {
            id title handle status descriptionHtml vendor productType tags
            featuredImage { url }
            images(first: 20) { edges { node { url altText } } }
            variants(first: 100) { edges { node { id title price compareAtPrice sku
              inventoryItem { id measurement { weight { unit value } } }
            } } }
          }
        }"""
        data = self._graphql_request(query, {"id": gid})
        p = data.get("product")
        if not p:
            raise Exception("Product not found")
        variants = []
        for e in p.get("variants", {}).get("edges", []):
            v = e["node"]
            variants.append({"id": v["id"], "title": v.get("title"), "price": v.get("price"), "sku": v.get("sku")})
        images = [e["node"]["url"] for e in p.get("images", {}).get("edges", [])]
        return {
            "shopify_id": p["id"], "title": p["title"], "handle": p.get("handle"), "status": p.get("status"),
            "description": p.get("descriptionHtml") or "", "vendor": p.get("vendor") or "",
            "product_type": p.get("productType") or "", "tags": p.get("tags") or [],
            "image_url": (p.get("featuredImage") or {}).get("url"), "images": images, "variants": variants,
        }

    def create_shopify_product(self, db: Session, data: dict) -> dict:
        product_input = {"title": data["title"], "status": "DRAFT"}
        if data.get("product_type"):
            product_input["productType"] = data["product_type"]
        if data.get("vendor"):
            product_input["vendor"] = data["vendor"]
        if data.get("tags"):
            product_input["tags"] = data["tags"] if isinstance(data["tags"], list) else [t.strip() for t in data["tags"].split(",")]
        if data.get("description"):
            product_input["descriptionHtml"] = data["description"]

        mutation = """
        mutation($input: ProductInput!) {
          productCreate(input: $input) {
            product { id title handle status featuredImage { url }
              variants(first: 10) { edges { node { id title price sku } } } }
            userErrors { field message }
          }
        }"""
        result = self._graphql_request(mutation, {"input": product_input})
        pc = result.get("productCreate", {})
        errors = pc.get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {[e['message'] for e in errors]}")
        product = pc.get("product", {})
        shopify_id = product["id"]
        variant_edges = product.get("variants", {}).get("edges", [])
        if variant_edges and (data.get("price") or data.get("sku")):
            vi = {"id": variant_edges[0]["node"]["id"]}
            if data.get("price"):
                vi["price"] = str(data["price"])
            if data.get("sku"):
                vi["sku"] = data["sku"]
            self._graphql_request("""
            mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
              productVariantsBulkUpdate(productId: $productId, variants: $variants) {
                productVariants { id price sku } userErrors { field message } }
            }""", {"productId": shopify_id, "variants": [vi]})
            if data.get("price"):
                variant_edges[0]["node"]["price"] = str(data["price"])
            if data.get("sku"):
                variant_edges[0]["node"]["sku"] = data["sku"]
        if data.get("images"):
            try:
                self._graphql_request("""
                mutation($productId: ID!, $media: [CreateMediaInput!]!) {
                  productCreateMedia(productId: $productId, media: $media) { media { id } mediaUserErrors { field message } }
                }""", {"productId": shopify_id, "media": [{"originalSource": url, "mediaContentType": "IMAGE"} for url in data["images"] if url]})
            except Exception:
                pass
        db_product = Product(shopify_id=shopify_id, title=product["title"], handle=product["handle"], status=product["status"].lower(),
                             image_url=(product.get("featuredImage") or {}).get("url"))
        db.add(db_product)
        db.flush()
        variants_data = []
        for edge in variant_edges:
            v = edge["node"]
            db.add(Variant(shopify_id=v["id"], product_id=db_product.id, title=v.get("title", "Default Title"), price=float(v.get("price", 0)), sku=v.get("sku")))
            variants_data.append(v)
        db.commit()
        return {"product_shopify_id": shopify_id, "product_title": product["title"], "handle": product["handle"], "status": product["status"], "variants": variants_data}

    def update_shopify_product(self, db: Session, product_shopify_id: str, data: dict) -> dict:
        product_input = {"id": product_shopify_id}
        if data.get("title"):
            product_input["title"] = data["title"]
        if data.get("status"):
            product_input["status"] = data["status"].upper()
        if data.get("description") is not None:
            product_input["descriptionHtml"] = data["description"]
        result = self._graphql_request("""
        mutation($input: ProductInput!) {
          productUpdate(input: $input) { product { id title status } userErrors { field message } }
        }""", {"input": product_input})
        pu = result.get("productUpdate", {})
        errors = pu.get("userErrors", [])
        if errors:
            raise Exception(f"Shopify errors: {[e['message'] for e in errors]}")
        product = pu.get("product", {})
        db_product = db.query(Product).filter(Product.shopify_id == product_shopify_id).first()
        if db_product:
            if data.get("title"):
                db_product.title = data["title"]
            if data.get("status"):
                db_product.status = data["status"].lower()
        db.commit()
        return {"product_shopify_id": product.get("id"), "title": product.get("title"), "status": product.get("status")}


margin_vat_service = MarginVatService()
