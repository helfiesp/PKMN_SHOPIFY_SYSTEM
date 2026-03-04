"""Purchase order service — create POs, update Shopify inventory, query history."""
from typing import List, Optional
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session, joinedload

from app.models import PurchaseOrder, PurchaseOrderItem, Variant, AuditLog, Setting
from app.config import settings


class PurchaseOrderService:

    def fetch_jpy_to_nok_rate(self) -> float:
        """Fetch current JPY→NOK rate from Frankfurter API."""
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
            print(f"[PO] FX rate fetch failed: {e}")
        return 0.063

    def _update_shopify_inventory(self, variant: Variant, new_quantity: int) -> dict:
        """Set absolute inventory on Shopify for a single variant."""
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()
        if not shop or not token:
            return {"success": False, "error": "Shopify credentials not configured"}
        if not variant.inventory_item_id:
            return {"success": False, "error": f"Variant {variant.id} has no inventory_item_id"}

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

        try:
            resp = requests.post(
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
                                "quantity": new_quantity,
                            }],
                        }
                    },
                },
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json()

            if "errors" in result:
                return {"success": False, "error": f"GraphQL errors: {result['errors']}"}

            user_errors = (
                result.get("data", {})
                .get("inventorySetQuantities", {})
                .get("userErrors", [])
            )
            if user_errors:
                return {"success": False, "error": f"Shopify error: {user_errors}"}

            return {"success": True, "new_quantity": new_quantity}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def _is_auto_update_enabled(self, db: Session) -> bool:
        """Check if automatic Shopify inventory update is enabled."""
        setting = db.query(Setting).filter(Setting.key == "auto_update_shopify_inventory").first()
        return setting is not None and setting.value == "true"

    async def create_purchase_order(
        self,
        db: Session,
        order_date: Optional[datetime],
        shipping_cost_jpy: float,
        total_nok: float,
        notes: Optional[str],
        items: List[dict],
    ) -> dict:
        """Create PO, optionally update Shopify inventory, return result."""
        # 1. Validate variants
        variant_map: dict[int, Variant] = {}
        for item in items:
            variant = db.query(Variant).filter(Variant.id == item["variant_id"]).first()
            if not variant:
                raise ValueError(f"Variant ID {item['variant_id']} not found")
            if not variant.inventory_item_id:
                raise ValueError(
                    f"Variant '{variant.title}' (ID {variant.id}) has no inventory_item_id. "
                    "Sync collection from Shopify first."
                )
            variant_map[item["variant_id"]] = variant

        # 2. Snapshot FX rate
        fx_rate = self.fetch_jpy_to_nok_rate()

        # 3. Check auto-update setting
        auto_update = self._is_auto_update_enabled(db)

        # 4. Create PO
        po = PurchaseOrder(
            order_date=order_date or datetime.now(timezone.utc),
            shipping_cost_jpy=shipping_cost_jpy,
            total_nok=total_nok,
            fx_rate_snapshot=fx_rate,
            status="completed",
            notes=notes,
        )
        db.add(po)
        db.flush()

        # 5. Create line items
        po_items: list[PurchaseOrderItem] = []
        for item in items:
            variant = variant_map[item["variant_id"]]
            product = variant.product
            po_item = PurchaseOrderItem(
                purchase_order_id=po.id,
                variant_id=item["variant_id"],
                quantity=item["quantity"],
                price_jpy=item["price_jpy"],
                weight_grams=item.get("weight_grams") or variant.weight_grams,
                product_title=product.title if product else None,
                variant_title=variant.title,
                sku=variant.sku,
                product_shopify_id=product.shopify_id if product else None,
            )
            po_items.append(po_item)
            db.add(po_item)
        db.flush()

        # 6. Update Shopify inventory (only if auto-update enabled)
        inventory_results = []
        for item_data, po_item in zip(items, po_items):
            variant = variant_map[item_data["variant_id"]]
            old_qty = variant.inventory_quantity or 0
            new_qty = old_qty + item_data["quantity"]

            if auto_update:
                result = self._update_shopify_inventory(variant, new_qty)
                if result["success"]:
                    variant.inventory_quantity = new_qty
                    variant.updated_at = datetime.now(timezone.utc)
                inventory_results.append({
                    "variant_id": variant.id,
                    "old_qty": old_qty,
                    "new_qty": new_qty,
                    "success": result["success"],
                    "error": result.get("error"),
                })
            else:
                # Update local DB only
                variant.inventory_quantity = new_qty
                variant.updated_at = datetime.now(timezone.utc)
                inventory_results.append({
                    "variant_id": variant.id,
                    "old_qty": old_qty,
                    "new_qty": new_qty,
                    "success": True,
                    "shopify_skipped": True,
                })

        # 7. Audit log
        db.add(AuditLog(
            operation="purchase_order_created",
            entity_type="purchase_order",
            entity_id=str(po.id),
            details={
                "total_nok": total_nok,
                "shipping_jpy": shipping_cost_jpy,
                "item_count": len(po_items),
                "total_quantity": sum(i["quantity"] for i in items),
                "auto_update_shopify": auto_update,
                "inventory_results": inventory_results,
            },
            success=all(r["success"] for r in inventory_results),
        ))

        db.commit()
        db.refresh(po)

        return {
            "purchase_order": po,
            "inventory_results": inventory_results,
            "auto_update_shopify": auto_update,
        }

    def get_purchase_orders(
        self,
        db: Session,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> List[dict]:
        """List POs with summary info."""
        query = db.query(PurchaseOrder)
        if status:
            query = query.filter(PurchaseOrder.status == status)

        pos = query.order_by(PurchaseOrder.order_date.desc()).offset(skip).limit(limit).all()

        results = []
        for po in pos:
            items = po.items
            results.append({
                "id": po.id,
                "order_date": po.order_date,
                "shipping_cost_jpy": po.shipping_cost_jpy,
                "total_nok": po.total_nok,
                "status": po.status,
                "notes": po.notes,
                "created_at": po.created_at,
                "total_items": len(items),
                "total_quantity": sum(i.quantity for i in items),
                "total_jpy": sum(i.price_jpy * i.quantity for i in items),
            })
        return results

    def get_purchase_order(self, db: Session, po_id: int) -> Optional[PurchaseOrder]:
        """Get single PO with items eagerly loaded."""
        return (
            db.query(PurchaseOrder)
            .options(joinedload(PurchaseOrder.items))
            .filter(PurchaseOrder.id == po_id)
            .first()
        )

    async def cancel_purchase_order(
        self, db: Session, po_id: int, revert_inventory: bool = False
    ) -> dict:
        """Cancel a PO, optionally reverting inventory."""
        po = (
            db.query(PurchaseOrder)
            .options(joinedload(PurchaseOrder.items))
            .filter(PurchaseOrder.id == po_id)
            .first()
        )
        if not po:
            raise ValueError("Purchase order not found")
        if po.status == "cancelled":
            raise ValueError("Purchase order already cancelled")

        inventory_results = []
        if revert_inventory:
            for po_item in po.items:
                variant = db.query(Variant).filter(Variant.id == po_item.variant_id).first()
                if not variant:
                    inventory_results.append({
                        "variant_id": po_item.variant_id,
                        "success": False,
                        "error": "Variant not found",
                    })
                    continue

                old_qty = variant.inventory_quantity or 0
                new_qty = max(0, old_qty - po_item.quantity)
                result = self._update_shopify_inventory(variant, new_qty)
                if result["success"]:
                    variant.inventory_quantity = new_qty
                    variant.updated_at = datetime.now(timezone.utc)
                inventory_results.append({
                    "variant_id": variant.id,
                    "old_qty": old_qty,
                    "new_qty": new_qty,
                    "success": result["success"],
                    "error": result.get("error"),
                })

        po.status = "cancelled"
        po.updated_at = datetime.now(timezone.utc)

        db.add(AuditLog(
            operation="purchase_order_cancelled",
            entity_type="purchase_order",
            entity_id=str(po.id),
            details={
                "revert_inventory": revert_inventory,
                "inventory_results": inventory_results,
            },
            success=True,
        ))

        db.commit()
        return {
            "message": "Purchase order cancelled",
            "po_id": po_id,
            "revert_inventory": revert_inventory,
            "inventory_results": inventory_results,
        }


purchase_order_service = PurchaseOrderService()
