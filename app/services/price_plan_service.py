"""Price plan service - handles price update plan generation and application."""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, timezone
import requests
import math
import sys

from app.models import PricePlan, PricePlanItem, Product, Variant, SnkrdunkMapping
from app.config import settings


class PricePlanService:
    """Service for price plan operations."""
    
    ALLOWED_ENDINGS = (25, 49, 75, 99)
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
    DEFAULT_PACKS_PER_BOX = 30
    PACK_MARKUP = 1.20
    
    def fetch_jpy_to_nok_rate(self) -> float:
        """Fetch current JPY to NOK exchange rate from Frankfurter API."""
        try:
            r = requests.get(
                "https://api.frankfurter.dev/v1/latest",
                params={"base": "JPY", "symbols": "NOK"},
                timeout=10
            )
            r.raise_for_status()
            data = r.json()
            rate = data.get("rates", {}).get("NOK")
            if rate:
                return float(rate)
        except Exception as e:
            print(f"Error fetching exchange rate: {e}")
        return 0.063  # Fallback rate
    
    def round_up_to_allowed_ending(self, amount: float) -> int:
        """Round up NOK price to psychological ending (25/49/75/99)."""
        n = int(amount)
        if amount > n:
            n += 1
        base = (n // 100) * 100
        tail = n - base
        for e in self.ALLOWED_ENDINGS:
            if tail <= e:
                return base + e
        return base + 100 + self.ALLOWED_ENDINGS[0]
    
    def detect_packs_per_box(self, title: str) -> int:
        """Detect number of packs per box based on product title."""
        t = (title or "").strip().lower()
        for keyword, count in self.SPECIAL_PACK_COUNTS:
            if keyword in t:
                return count
        return self.DEFAULT_PACKS_PER_BOX
    
    def round_pack_price_psych(self, n: float) -> int:
        """Round pack price with psychological pricing."""
        x = int(n) if float(n).is_integer() else int(n) + 1
        
        if x >= 100 and (x % 100) <= 9:
            return (x // 100) * 100 - 1
        
        if x % 10 in (5, 9):
            return x
        
        for d in range(1, 30):
            y = x + d
            if y % 10 in (5, 9):
                return y
        return x
    
    def compute_recommended_prices(
        self,
        cost_basis_nok_ex_vat: float,
        min_margin: float,
        vat_rate: float
    ) -> tuple[float, int]:
        """Calculate recommended net and gross prices."""
        required_net = cost_basis_nok_ex_vat / (1.0 - min_margin)
        required_gross = required_net * (1.0 + vat_rate)
        rounded_gross = self.round_up_to_allowed_ending(required_gross)
        net_from_rounded = round(rounded_gross / (1.0 + vat_rate), 2)
        return net_from_rounded, rounded_gross
    
    async def generate_price_plan(
        self,
        db: Session,
        variant_type: str = "box",  # "box" or "pack"
        exchange_rate: Optional[float] = None,
        shipping_cost_jpy: int = 500,
        min_margin_pct: float = 20.0,
        vat_pct: float = 25.0,
        pack_markup_pct: float = 20.0,  # Markup for pack pricing (10-20% typical)
        min_change_threshold: float = 5.0,  # Minimum price change in NOK
        plan_type: str = "price_update"
    ) -> PricePlan:
        """
        Generate a new price update plan.
        
        Uses SNKRDUNK mappings and prices to calculate recommended Shopify prices.
        """
        # Get exchange rate
        fx_rate = exchange_rate if exchange_rate else self.fetch_jpy_to_nok_rate()
        min_margin = min_margin_pct / 100.0
        vat_rate = vat_pct / 100.0
        
        # Get all SNKRDUNK mappings
        mappings = db.query(SnkrdunkMapping).all()
        
        plan = PricePlan(
            plan_type=plan_type,
            collection_id="444175384827",  # Pokemon JP collection
            status="pending",
            generated_at=datetime.now(timezone.utc),
            total_items=0,
            fx_rate=fx_rate,
            pricing_adjustments={
                "variant_type": variant_type,
                "shipping_cost_jpy": shipping_cost_jpy,
                "min_margin_pct": min_margin_pct,
                "vat_pct": vat_pct,
                "pack_markup_pct": pack_markup_pct,
                "min_change_threshold": min_change_threshold
            }
        )
        
        db.add(plan)
        db.flush()
        
        plan_items = []
        
        # Get SNKRDUNK products once
        from app.services.snkrdunk_service import SnkrdunkService
        snkr_service = SnkrdunkService()
        snkr_products = snkr_service.get_cached_products(db, translate=False)
        
        # Process each mapping
        for mapping in mappings:
            # Find SNKRDUNK product for this mapping
            snkr_product = next(
                (p for p in snkr_products if str(p["id"]) == mapping.snkrdunk_key),
                None
            )
            
            if not snkr_product:
                continue
            
            min_price_jpy = snkr_product.get("minPriceJpy")
            if not min_price_jpy:
                continue
            
            # Get Shopify product
            product = db.query(Product).filter(
                Product.shopify_id == mapping.product_shopify_id
            ).first()
            
            if not product:
                continue
            
            # Get Booster Box variant (primary pricing variant)
            box_variant = None
            pack_variant = None
            for variant in product.variants:
                if variant.title and "booster box" in variant.title.lower():
                    box_variant = variant
                elif variant.title and "booster pack" in variant.title.lower():
                    pack_variant = variant
            
            # Select variant based on user choice
            if variant_type == "box":
                target_variant = box_variant or (product.variants[0] if product.variants else None)
                variant_name = "Booster Box"
            else:  # pack
                target_variant = pack_variant
                variant_name = "Booster Pack"
            
            if not target_variant:
                continue
            
            # Calculate recommended price
            if variant_type == "box":
                # Box pricing: based on SNKRDUNK price
                estimated_nok = round(min_price_jpy * fx_rate, 2)
                estimated_with_shipping = round((min_price_jpy + shipping_cost_jpy) * fx_rate, 2)
                cost_basis_ex_vat = estimated_with_shipping
                
                rec_net, rec_gross = self.compute_recommended_prices(
                    cost_basis_ex_vat, min_margin, vat_rate
                )
            else:  # pack
                # Pack pricing: derived from box price
                if not box_variant:
                    continue
                    
                box_price = float(box_variant.price) if box_variant.price else 0.0
                if box_price == 0:
                    continue
                    
                packs_per_box = self.detect_packs_per_box(product.title or "")
                markup_multiplier = 1 + (pack_markup_pct / 100)
                pack_raw = (box_price / float(packs_per_box)) * markup_multiplier
                rec_gross = int(self.round_pack_price_psych(pack_raw))
                rec_net = round(rec_gross / (1.0 + vat_rate), 2)
            
            current_price = float(target_variant.price) if target_variant.price else 0.0
            delta = rec_gross - current_price
            
            # Determine threshold based on variant type
            min_change = min_change_threshold if variant_type == "pack" else 25
            
            # Debug logging for threshold
            print(f"[Price Plan] {product.title} - {variant_name}: current={current_price}, new={rec_gross}, delta={delta}, threshold={min_change}, abs(delta)={abs(delta)}")
            
            # Only create plan item if change is significant
            if abs(delta) >= min_change:
                plan_item = PricePlanItem(
                    plan_id=plan.id,
                    product_shopify_id=product.shopify_id,
                    variant_shopify_id=target_variant.shopify_id,
                    current_title=f"{product.title} - {variant_name}",
                    current_price=current_price,
                    current_compare_at=float(target_variant.compare_at_price) if target_variant.compare_at_price else None,
                    new_price=float(rec_gross),
                    new_compare_at=None,
                    snkrdunk_key=mapping.snkrdunk_key,
                    snkrdunk_price_jpy=float(min_price_jpy) if variant_type == "box" else None,
                    snkrdunk_link=f"https://snkrdunk.com/apparels/{mapping.snkrdunk_key}",
                    applied=False
                )
                plan_items.append(plan_item)
                db.add(plan_item)
        
        plan.total_items = len(plan_items)
        db.commit()
        db.refresh(plan)
        
        return plan
    
    async def generate_price_plan_from_items(
        self,
        db: Session,
        items: List[Dict],
        plan_type: str = "price_update"
    ) -> PricePlan:
        """
        Generate a price plan from pre-calculated items.
        Used for strategies like 'match_competition'.
        
        Expected item format:
        {
            'product_id': int,
            'product_title': str,
            'variant_id': int,
            'variant_title': str,
            'current_price': float,
            'new_price': float
        }
        """
        plan = PricePlan(
            plan_type=plan_type,
            collection_id="444175384827",  # Pokemon JP collection
            status="pending",
            generated_at=datetime.now(timezone.utc),
            total_items=0,
            pricing_adjustments={
                "strategy": "match_competition"
            }
        )
        
        db.add(plan)
        db.flush()
        
        plan_items = []
        
        for item_data in items:
            # Get variant from database
            variant = db.query(Variant).filter(
                Variant.id == item_data.get('variant_id')
            ).first()
            
            if not variant:
                continue
            
            # Get product
            product = db.query(Product).filter(
                Product.id == item_data.get('product_id')
            ).first()
            
            if not product:
                continue
            
            # Create plan item
            plan_item = PricePlanItem(
                plan_id=plan.id,
                product_shopify_id=product.shopify_id,
                variant_shopify_id=variant.shopify_id,
                current_title=item_data.get('product_title', product.title),
                current_price=float(item_data.get('current_price', variant.price)),
                current_compare_at=float(variant.compare_at_price) if variant.compare_at_price else None,
                new_price=float(item_data.get('new_price', 0)),
                new_compare_at=None,
                snkrdunk_key=None,
                snkrdunk_price_jpy=None,
                snkrdunk_link=None,
                applied=False
            )
            plan_items.append(plan_item)
            db.add(plan_item)
        
        plan.total_items = len(plan_items)
        db.commit()
        db.refresh(plan)
        
        return plan
    
    async def apply_price_plan(
        self,
        db: Session,
        plan_id: int
    ) -> dict:
        """
        Apply price plan to Shopify.
        
        Replicates shopify_price_updater_confirmed.py apply logic:
        - Groups variants by product_id
        - Verifies current price matches snapshot
        - Uses productVariantsBulkUpdate GraphQL mutation
        """
        # Write logs to file
        import os
        from datetime import datetime
        log_file = os.path.join(os.path.dirname(__file__), '..', '..', 'apply_log.txt')
        
        def log(msg):
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n")
                f.flush()
        
        log(f"\n========== STARTING APPLY FOR PLAN {plan_id} ==========")
        
        plan = db.query(PricePlan).filter(PricePlan.id == plan_id).first()
        
        log(f"Found plan: {plan}")
        
        if not plan:
            raise ValueError("Plan not found")
        
        if plan.status == "applied":
            raise ValueError("Plan already applied")
        
        # Get all items for this plan
        items = db.query(PricePlanItem).filter(PricePlanItem.plan_id == plan_id).all()
        
        log(f"Found {len(items)} items for plan {plan_id}")
        
        if not items:
            plan.status = "applied"
            plan.applied_at = datetime.now(timezone.utc)
            plan.applied_items = 0
            db.commit()
            return {
                "plan_id": plan_id,
                "status": "applied",
                "applied_items": 0,
                "failed_items": 0,
                "skipped_items": 0,
                "errors": []
            }
        
        # GraphQL queries
        QUERY_VARIANT_GET = """
        query($id: ID!) {
          productVariant(id: $id) {
            id
            price
            compareAtPrice
            product { id title handle }
            title
          }
        }
        """
        
        MUTATION_PRODUCT_VARIANTS_BULK_UPDATE = """
        mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
          productVariantsBulkUpdate(productId: $productId, variants: $variants) {
            productVariants { id price compareAtPrice }
            userErrors { field message }
          }
        }
        """
        
        def graphql_request(query: str, variables: dict) -> dict:
            """Make GraphQL request to Shopify."""
            url = f"https://{settings.get_shopify_shop()}/admin/api/{settings.shopify_api_version}/graphql.json"
            headers = {
                "X-Shopify-Access-Token": settings.get_shopify_token(),
                "Content-Type": "application/json"
            }
            response = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                error_msg = f"GraphQL errors: {data['errors']}"
                log(f"ERROR: {error_msg}")
                raise RuntimeError(error_msg)
            
            return data.get("data", {})
        
        # Group items by product
        from collections import defaultdict
        grouped_items = defaultdict(list)
        for item in items:
            grouped_items[item.product_shopify_id].append(item)
        
        applied_count = 0
        failed_count = 0
        skipped_count = 0
        errors = []
        
        log(f"Starting application with {len(grouped_items)} products")
        
        # Process each product's variants
        for product_shopify_id, product_items in grouped_items.items():
            log(f"\nProcessing product {product_shopify_id} with {len(product_items)} items")
            variant_inputs = []
            items_to_mark = []
            
            # Check each variant's current price
            for item in product_items:
                try:
                    log(f"  Item {item.id}: {item.variant_shopify_id} current={item.current_price} -> new={item.new_price}")
                    
                    # Query current variant state
                    result = graphql_request(QUERY_VARIANT_GET, {"id": item.variant_shopify_id})
                    live_variant = result.get("productVariant")
                    
                    if not live_variant:
                        error_msg = "Variant not found in Shopify"
                        log(f"  Item {item.id} ERROR: {error_msg}")
                        item.error_message = error_msg
                        errors.append(f"Item {item.id}: {error_msg}")
                        skipped_count += 1
                        continue
                    
                    live_price = float(live_variant.get("price", 0))
                    live_compare = float(live_variant.get("compareAtPrice") or 0) if live_variant.get("compareAtPrice") else None
                    
                    # Verify price hasn't changed since plan was generated
                    expected_price = float(item.current_price) if item.current_price else 0
                    expected_compare = float(item.current_compare_at) if item.current_compare_at else None
                    
                    if abs(live_price - expected_price) > 0.01:
                        item.error_message = f"Price changed: expected {expected_price}, got {live_price}"
                        skipped_count += 1
                        continue
                    
                    if (live_compare is None) != (expected_compare is None):
                        item.error_message = f"Compare-at price changed"
                        skipped_count += 1
                        continue
                    
                    if live_compare and expected_compare and abs(live_compare - expected_compare) > 0.01:
                        item.error_message = f"Compare-at price changed: expected {expected_compare}, got {live_compare}"
                        skipped_count += 1
                        continue
                    
                    # Add to bulk update
                    variant_input = {
                        "id": item.variant_shopify_id,
                        "price": str(item.new_price),
                    }
                    
                    if item.new_compare_at:
                        variant_input["compareAtPrice"] = str(item.new_compare_at)
                    
                    variant_inputs.append(variant_input)
                    items_to_mark.append(item)
                    log(f"  Item {item.id} ✓ Added to batch")
                    
                except Exception as e:
                    error_detail = f"Error checking variant: {str(e)}"
                    log(f"  Item {item.id} ERROR: {error_detail}")
                    item.error_message = error_detail
                    errors.append(f"Item {item.id}: {error_detail}")
                    failed_count += 1
            
            # Apply bulk update if we have valid variants
            if variant_inputs:
                log(f"  Bulk Update: Applying {len(variant_inputs)} variants")
                try:
                    result = graphql_request(
                        MUTATION_PRODUCT_VARIANTS_BULK_UPDATE,
                        {
                            "productId": product_shopify_id,
                            "variants": variant_inputs
                        }
                    )
                    
                    bulk_result = result.get("productVariantsBulkUpdate", {})
                    user_errors = bulk_result.get("userErrors", [])
                    
                    if user_errors:
                        error_msg = "; ".join([f"{e.get('field', 'unknown')}: {e.get('message', 'unknown')}" for e in user_errors])
                        log(f"  Bulk Update ✗ USER ERRORS: {error_msg}")
                        for item in items_to_mark:
                            item.error_message = error_msg
                        errors.append(f"Product {product_shopify_id}: {error_msg}")
                        failed_count += len(items_to_mark)
                    else:
                        log(f"  Bulk Update ✓ Successfully applied {len(items_to_mark)} items")
                        # Mark all items as applied and update variant prices in database
                        for item in items_to_mark:
                            item.applied = True
                            # Update the variant price in database using shopify_id
                            variant = db.query(Variant).filter(Variant.shopify_id == item.variant_shopify_id).first()
                            if variant:
                                variant.price = float(item.new_price)
                                variant.updated_at = datetime.now(timezone.utc)
                                log(f"    Updated variant {variant.id} price to {variant.price}")
                        applied_count += len(items_to_mark)
                
                except Exception as e:
                    error_msg = str(e)
                    log(f"  Bulk Update ✗ EXCEPTION: {error_msg}")
                    for item in items_to_mark:
                        item.error_message = error_msg
                    errors.append(f"Product {product_shopify_id}: {error_msg}")
                    failed_count += len(items_to_mark)
        
        # Update plan status
        plan.status = "applied"
        plan.applied_at = datetime.now(timezone.utc)
        plan.applied_items = applied_count
        db.commit()
        
        log(f"\n========== SUMMARY ==========")
        log(f"Applied: {applied_count}, Failed: {failed_count}, Skipped: {skipped_count}")
        if errors:
            log(f"ERRORS ({len(errors)}):")
            for i, error in enumerate(errors[:10], 1):
                log(f"  {i}. {error}")
            if len(errors) > 10:
                log(f"  ... and {len(errors) - 10} more errors")
        log(f"========== END ==========\n")
        
        return {
            "plan_id": plan_id,
            "status": "applied",
            "applied_items": applied_count,
            "failed_items": failed_count,
            "skipped_items": skipped_count,
            "errors": errors
        }
    
    def get_plans(
        self,
        db: Session,
        status: Optional[str] = None,
        plan_type: Optional[str] = None,
        skip: int = 0,
        limit: int = 50
    ) -> List[PricePlan]:
        """Get price plans."""
        query = db.query(PricePlan)
        
        if status:
            query = query.filter(PricePlan.status == status)
        if plan_type:
            query = query.filter(PricePlan.plan_type == plan_type)
        
        return query.order_by(PricePlan.generated_at.desc()).offset(skip).limit(limit).all()
    
    def get_plan_by_id(self, db: Session, plan_id: int) -> Optional[PricePlan]:
        """Get a specific plan by ID."""
        return db.query(PricePlan).filter(PricePlan.id == plan_id).first()
    
    def delete_plan(self, db: Session, plan_id: int) -> bool:
        """Delete a plan."""
        plan = db.query(PricePlan).filter(PricePlan.id == plan_id).first()
        if plan:
            db.delete(plan)
            db.commit()
            return True
        return False
    
    async def verify_price_plan(self, db: Session, plan_id: int) -> dict:
        """Verify that prices were actually applied in Shopify."""
        plan = db.query(PricePlan).filter(PricePlan.id == plan_id).first()
        
        if not plan:
            raise ValueError("Plan not found")
        
        if plan.status != "applied":
            raise ValueError("Plan must be applied before verification")
        
        # Get all applied items
        items = db.query(PricePlanItem).filter(
            PricePlanItem.plan_id == plan_id,
            PricePlanItem.applied == True
        ).all()
        
        if not items:
            return {
                "plan_id": plan_id,
                "status": "verified",
                "verified_items": 0,
                "mismatched_items": 0,
                "message": "No items to verify"
            }
        
        QUERY_VARIANT_GET = """
        query($id: ID!) {
          productVariant(id: $id) {
            id
            price
            compareAtPrice
          }
        }
        """
        
        def graphql_request(query: str, variables: dict) -> dict:
            url = f"https://{settings.SHOPIFY_SHOP}/admin/api/{settings.SHOPIFY_API_VERSION}/graphql.json"
            headers = {
                "X-Shopify-Access-Token": settings.SHOPIFY_ACCESS_TOKEN,
                "Content-Type": "application/json"
            }
            response = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()
            
            if "errors" in data:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")
            
            return data.get("data", {})
        
        verified_count = 0
        mismatched_count = 0
        mismatches = []
        
        # Check each item
        for item in items:
            try:
                result = graphql_request(QUERY_VARIANT_GET, {"id": item.variant_shopify_id})
                live_variant = result.get("productVariant")
                
                if not live_variant:
                    mismatched_count += 1
                    mismatches.append(f"Item {item.id}: Variant not found")
                    continue
                
                live_price = float(live_variant.get("price", 0))
                expected_price = float(item.new_price)
                
                # Check if price matches (with small tolerance for floating point)
                if abs(live_price - expected_price) < 0.01:
                    verified_count += 1
                else:
                    mismatched_count += 1
                    mismatches.append(
                        f"Item {item.id} ({item.current_title}): Expected {expected_price}, got {live_price}"
                    )
            
            except Exception as e:
                mismatched_count += 1
                mismatches.append(f"Item {item.id}: Error - {str(e)}")
        
        # If any mismatches, revert plan status to pending
        if mismatched_count > 0:
            plan.status = "pending"
            plan.applied_at = None
            plan.applied_items = 0
            
            # Mark all items as not applied
            for item in items:
                item.applied = False
            
            db.commit()
            
            return {
                "plan_id": plan_id,
                "status": "reverted",
                "verified_items": verified_count,
                "mismatched_items": mismatched_count,
                "mismatches": mismatches,
                "message": "Verification failed. Plan reverted to pending status."
            }
        
        return {
            "plan_id": plan_id,
            "status": "verified",
            "verified_items": verified_count,
            "mismatched_items": 0,
            "message": f"All {verified_count} items verified successfully"
        }
    
    def cancel_plan(self, db: Session, plan_id: int) -> Optional[PricePlan]:
        """Cancel a pending plan."""
        plan = db.query(PricePlan).filter(PricePlan.id == plan_id).first()
        if plan and plan.status == "pending":
            plan.status = "cancelled"
            db.commit()
            db.refresh(plan)
            return plan
        return None


price_plan_service = PricePlanService()
