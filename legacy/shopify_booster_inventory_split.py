#!/usr/bin/env python3
from __future__ import annotations

"""
shopify_booster_inventory_split.py

Goal:
- For products in collection 444116140283 (excluding titles containing "One Piece"):
  - Find the Booster Box + Booster Pack variants (option "Type")
  - If Booster Box available quantity > 1 at the chosen location:
      * Decrease Booster Box by 1
      * Increase Booster Pack by packs_per_box (default 30, with special cases)
- PLAN mode (default): generate a plan json in ./data
- APPLY mode (APPLY_CHANGES=1 + CONFIRM_PLAN=<path or omitted>): apply inventoryAdjustQuantities
  - Uses InventoryAdjustQuantitiesInput (delta-based) on the "available" quantity name.

Notes:
- Inventory is location-specific. This script picks ONE active location (first returned by `locations(first: 10)`).
  If you manage multiple locations, extend selection or run per location.
"""

import json
import os
import re
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

# =============================================================================
# Paths
# =============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
PLAN_FILE = DATA_DIR / f"booster_inventory_plan_{STAMP}.json"
PLAN_LATEST = DATA_DIR / "booster_inventory_plan_latest.json"
AUDIT_FILE = DATA_DIR / f"booster_inventory_audit_{STAMP}.json"

# =============================================================================
# Shopify config
# =============================================================================
SHOP_ENV = "SHOPIFY_SHOP"
TOKEN_ENV = "SHOPIFY_TOKEN"
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-01")

# If your token/app doesn't have `read_locations`, you can supply the location id directly.
# Accepts either a full GID (gid://shopify/Location/123) or a numeric id (123).
LOCATION_ID_ENV = "81755177211"
LOCATION_NAME_ENV = "H. Halvorsens vei 5"

COLLECTION_NUMERIC_ENV = "SHOPIFY_COLLECTION_NUMERIC_ID"
DEFAULT_COLLECTION_NUMERIC_ID = "444116140283"

APPLY_ENV = "APPLY_CHANGES"
CONFIRM_PLAN_ENV = "CONFIRM_PLAN"

# =============================================================================
# Rules
# =============================================================================
EXCLUDE_TITLE_SUBSTRING = "one piece"  # case-insensitive

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

OPTION_NAME = "Type"
BOX_VALUE = "Booster Box"
PACK_VALUE = "Booster Pack"

SLEEP_BETWEEN_MUTATIONS_SEC = 0.25

# =============================================================================
# Utilities
# =============================================================================
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def die(msg: str, code: int = 1) -> None:
    print(f"\nERROR: {msg}\n", file=sys.stderr)
    raise SystemExit(code)


def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def graphql_url(shop: str) -> str:
    return f"https://{shop}/admin/api/{API_VERSION}/graphql.json"


def gql_call(session: requests.Session, shop: str, token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    url = graphql_url(shop)
    headers = {"Content-Type": "application/json", "X-Shopify-Access-Token": token}
    r = session.post(url, headers=headers, json={"query": query, "variables": variables}, timeout=60)
    r.raise_for_status()
    payload = r.json()
    if isinstance(payload.get("errors"), list) and payload["errors"]:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    if "data" not in payload:
        raise RuntimeError(f"Unexpected GraphQL response: {payload}")
    return payload["data"]


def gid_to_numeric(gid: str) -> Optional[int]:
    if not gid:
        return None
    m = re.search(r"/(\d+)$", gid)
    return int(m.group(1)) if m else None


def gid_collection(numeric_id: str) -> str:
    return f"gid://shopify/Collection/{numeric_id}"


def normalize_location_gid(raw: str) -> str:
    """Accepts either a full location GID or a numeric id and returns a location GID."""
    s = (raw or "").strip()
    if not s:
        return ""
    if s.startswith("gid://"):
        return s
    if s.isdigit():
        return f"gid://shopify/Location/{s}"
    return s


def detect_packs_per_box(title: str) -> int:
    t = (title or "").strip().lower()
    for kw, cnt in SPECIAL_PACK_COUNTS:
        if kw in t:
            return cnt
    return DEFAULT_PACKS_PER_BOX


def variant_has_selected(variant: dict[str, Any], opt_name: str, opt_value: str) -> bool:
    sels = variant.get("selectedOptions")
    if not isinstance(sels, list):
        return False
    on = opt_name.strip().lower()
    ov = opt_value.strip().lower()
    for s in sels:
        if not isinstance(s, dict):
            continue
        if str(s.get("name") or "").strip().lower() == on and str(s.get("value") or "").strip().lower() == ov:
            return True
    return False


def find_variant_by_option(product: dict[str, Any], opt_name: str, opt_value: str) -> Optional[dict[str, Any]]:
    variants = (product.get("variants") or {}).get("nodes") if isinstance(product.get("variants"), dict) else []
    if not isinstance(variants, list):
        return None
    for v in variants:
        if isinstance(v, dict) and variant_has_selected(v, opt_name, opt_value):
            return v
    return None


def get_available_from_inventory_level(inventory_level: Optional[dict[str, Any]]) -> int:
    """Reads quantities(names:["available"]) from inventoryItem.inventoryLevel(locationId: ...)."""
    if not isinstance(inventory_level, dict):
        return 0
    qs = inventory_level.get("quantities")
    if not isinstance(qs, list):
        return 0
    for q in qs:
        if not isinstance(q, dict):
            continue
        if str(q.get("name") or "").strip().lower() == "available":
            try:
                return int(q.get("quantity") or 0)
            except Exception:
                return 0
    return 0


# =============================================================================
# GraphQL
# =============================================================================
Q_LOCATIONS = """
query Locations($first: Int!) {
  locations(first: $first) {
    nodes { id name }
  }
}
"""

Q_COLLECTION_PRODUCTS = """
query CollectionProducts($id: ID!, $first: Int!, $after: String, $locationId: ID!) {
  collection(id: $id) {
    id
    title
    products(first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        title
        variants(first: 50) {
          nodes {
            id
            title
            selectedOptions { name value }
            inventoryItem {
              id
              inventoryLevel(locationId: $locationId) {
                quantities(names: [\"available\"]) { name quantity }
              }
            }
          }
        }
      }
    }
  }
}
"""

M_INVENTORY_ADJUST = """
mutation inventoryAdjustQuantities($input: InventoryAdjustQuantitiesInput!) {
  inventoryAdjustQuantities(input: $input) {
    userErrors { field message }
    inventoryAdjustmentGroup {
      createdAt
      reason
      referenceDocumentUri
      changes { name delta }
    }
  }
}
"""

# =============================================================================
# Plan schema
# =============================================================================
@dataclass(frozen=True)
class PlanItem:
    product_id: int
    product_gid: str
    title: str
    packs_per_box: int
    location_id: str
    location_name: str
    box_variant_gid: str
    pack_variant_gid: str
    box_inventory_item_id: str
    pack_inventory_item_id: str
    box_available: int
    pack_available: int
    box_delta: int
    pack_delta: int


def fetch_all_collection_products(session: requests.Session, shop: str, token: str, collection_gid: str, location_id: str) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    after = None
    while True:
        data = gql_call(
            session,
            shop,
            token,
            Q_COLLECTION_PRODUCTS,
            {"id": collection_gid, "first": 200, "after": after, "locationId": location_id},
        )
        coll = data.get("collection") or {}
        conn = coll.get("products") or {}
        nodes = conn.get("nodes") or []
        if isinstance(nodes, list):
            products.extend([p for p in nodes if isinstance(p, dict)])
        page = conn.get("pageInfo") or {}
        if not (page.get("hasNextPage") and page.get("endCursor")):
            break
        after = page.get("endCursor")
    return products


def pick_location(session: requests.Session, shop: str, token: str) -> tuple[str, str]:
    # Allow callers to provide the location id directly (works even without `read_locations`).
    env_loc = normalize_location_gid(os.getenv(LOCATION_ID_ENV, ""))
    if env_loc:
        return env_loc, (os.getenv(LOCATION_NAME_ENV, "") or "(provided)").strip()

    try:
        data = gql_call(session, shop, token, Q_LOCATIONS, {"first": 10})
    except Exception as e:
        msg = str(e)
        if "Access denied for locations field" in msg or "locations field" in msg and "ACCESS_DENIED" in msg:
            raise RuntimeError(
                "Cannot query locations(). Your Admin API token/app lacks the `read_locations` scope. "
                f"Either add `read_locations` to the app scopes and reinstall/regen the token, or set {LOCATION_ID_ENV} "
                "to your location GID (gid://shopify/Location/123) or numeric id (123)."
            ) from e
        raise

    nodes = ((data.get("locations") or {}).get("nodes")) if isinstance(data.get("locations"), dict) else []
    if not isinstance(nodes, list) or not nodes:
        raise RuntimeError("No active locations returned by locations()")
    first = nodes[0]
    return str(first.get("id") or ""), str(first.get("name") or "")


def build_plan(products: list[dict[str, Any]], location_id: str, location_name: str) -> dict[str, Any]:
    items: list[PlanItem] = []
    skipped: list[dict[str, Any]] = []

    for p in products:
        title = str(p.get("title") or "").strip()
        product_gid = str(p.get("id") or "")
        product_id = gid_to_numeric(product_gid)

        if not product_id:
            skipped.append({"product_id": None, "reason": "no product id"})
            continue

        if EXCLUDE_TITLE_SUBSTRING in title.lower():
            skipped.append({"product_id": product_id, "reason": "excluded (One Piece)"})
            continue

        # Require both variants to exist (already split)
        box_v = find_variant_by_option(p, OPTION_NAME, BOX_VALUE)
        pack_v = find_variant_by_option(p, OPTION_NAME, PACK_VALUE)
        if not box_v or not pack_v:
            skipped.append({"product_id": product_id, "reason": "missing Booster Box/Pack variants"})
            continue

        box_item = (box_v.get("inventoryItem") or {}) if isinstance(box_v.get("inventoryItem"), dict) else {}
        pack_item = (pack_v.get("inventoryItem") or {}) if isinstance(pack_v.get("inventoryItem"), dict) else {}
        box_inv_item_id = str(box_item.get("id") or "")
        pack_inv_item_id = str(pack_item.get("id") or "")
        if not box_inv_item_id or not pack_inv_item_id:
            skipped.append({"product_id": product_id, "reason": "missing inventoryItem id(s)"})
            continue

        box_level = box_item.get("inventoryLevel") if isinstance(box_item, dict) else None
        pack_level = pack_item.get("inventoryLevel") if isinstance(pack_item, dict) else None

        box_available = get_available_from_inventory_level(box_level)
        pack_available = get_available_from_inventory_level(pack_level)

        if box_available <= 1:
            skipped.append({"product_id": product_id, "reason": f"box available <= 1 at location ({box_available})"})
            continue

        packs = detect_packs_per_box(title)

        items.append(
            PlanItem(
                product_id=product_id,
                product_gid=product_gid,
                title=title,
                packs_per_box=packs,
                location_id=location_id,
                location_name=location_name,
                box_variant_gid=str(box_v.get("id") or ""),
                pack_variant_gid=str(pack_v.get("id") or ""),
                box_inventory_item_id=box_inv_item_id,
                pack_inventory_item_id=pack_inv_item_id,
                box_available=box_available,
                pack_available=pack_available,
                box_delta=-1,
                pack_delta=+packs,
            )
        )

    return {
        "generated_at_utc": utc_now(),
        "api_version": API_VERSION,
        "rules": {
            "select": f"in collection {DEFAULT_COLLECTION_NUMERIC_ID} AND title does NOT contain 'One Piece'",
            "location": {"id": location_id, "name": location_name, "selection": "first active location"},
            "plan_only_if": "product has Booster Box+Booster Pack variants AND box available > 1",
            "packs_default": DEFAULT_PACKS_PER_BOX,
            "special_packs": SPECIAL_PACK_COUNTS,
            "inventory_action": "box -1, pack +packs_per_box (available)",
        },
        "counts": {"planned": len(items), "skipped": len(skipped)},
        "items": [asdict(x) for x in items],
        "skipped": skipped,
    }


def apply_one(session: requests.Session, shop: str, token: str, it: dict[str, Any]) -> dict[str, Any]:
    # Basic validations
    product_id = int(it["product_id"])
    location_id = str(it["location_id"])
    box_item_id = str(it["box_inventory_item_id"])
    pack_item_id = str(it["pack_inventory_item_id"])
    box_delta = int(it["box_delta"])
    pack_delta = int(it["pack_delta"])

    # Safety: never move more than 1 box per product per run
    if box_delta != -1:
        raise RuntimeError(f"Invalid box_delta (expected -1): {box_delta}")
    if pack_delta <= 0 or pack_delta > 60:
        raise RuntimeError(f"Invalid pack_delta (expected 1..60): {pack_delta}")

    ref_uri = f"inventory://booster-split/{product_id}/{STAMP}"

    data = gql_call(
        session,
        shop,
        token,
        M_INVENTORY_ADJUST,
        {
            "input": {
                "reason": "correction",
                "name": "available",
                "referenceDocumentUri": ref_uri,
                "changes": [
                    {"delta": box_delta, "inventoryItemId": box_item_id, "locationId": location_id},
                    {"delta": pack_delta, "inventoryItemId": pack_item_id, "locationId": location_id},
                ],
            }
        },
    )

    payload = data.get("inventoryAdjustQuantities") or {}
    ue = payload.get("userErrors") or []
    if ue:
        raise RuntimeError(f"inventoryAdjustQuantities userErrors: {ue}")

    grp = payload.get("inventoryAdjustmentGroup") or {}
    return {"referenceDocumentUri": grp.get("referenceDocumentUri"), "changes": grp.get("changes")}


def main() -> int:
    shop = (os.getenv(SHOP_ENV) or "").strip()
    token = (os.getenv(TOKEN_ENV) or "").strip()
    if not shop:
        die(f"Missing environment variable: {SHOP_ENV}")
    if not token:
        die(f"Missing environment variable: {TOKEN_ENV}")

    collection_numeric = (os.getenv(COLLECTION_NUMERIC_ENV) or DEFAULT_COLLECTION_NUMERIC_ID).strip()
    collection_gid = gid_collection(collection_numeric)

    apply_mode = os.getenv(APPLY_ENV, "").strip() == "1"
    plan_path_env = os.getenv(CONFIRM_PLAN_ENV, "").strip()

    print("=== Booster inventory split ===")
    print(f"Shop: {shop}")
    print(f"API: {API_VERSION}")
    print(f"Collection: {collection_gid}")
    print(f"Mode: {'APPLY' if apply_mode else 'PLAN'}")
    print()

    with requests.Session() as s:
        location_id, location_name = pick_location(s, shop, token)
        if not location_id:
            die("Could not determine a location id")
        print(f"Using location: {location_name} ({location_id})\n")

        if not apply_mode:
            products = fetch_all_collection_products(s, shop, token, collection_gid, location_id)
            payload = build_plan(products, location_id, location_name)
            atomic_write_json(PLAN_FILE, payload)
            atomic_write_json(PLAN_LATEST, payload)
            print("Plan created:")
            print(f"  {PLAN_FILE}")
            print(f"  {PLAN_LATEST}")
            print(json.dumps(payload.get('counts', {}), indent=2))
            return 0

        # APPLY mode
        plan_path = Path(plan_path_env).expanduser().resolve() if plan_path_env else PLAN_LATEST
        if not plan_path.exists():
            die(f"Plan file not found: {plan_path}")

        plan = load_json(plan_path)
        if not isinstance(plan, dict):
            die("Invalid plan JSON")

        items = plan.get("items")
        if not isinstance(items, list):
            die("Plan missing items list")

        summary = {"applied": 0, "failed": 0, "skipped": 0}
        details: list[dict[str, Any]] = []

        # Safety: ensure we are using the same location as in the plan
        plan_loc = ((plan.get("rules") or {}).get("location") or {}) if isinstance(plan.get("rules"), dict) else {}
        plan_loc_id = str(plan_loc.get("id") or "")
        if plan_loc_id and plan_loc_id != location_id:
            die(
                f"Location mismatch vs plan. Plan: {plan_loc_id}, current first location: {location_id}. "
                "Regenerate the plan to proceed."
            )

        for it in items:
            try:
                product_id = int(it.get("product_id"))
                title = str(it.get("title") or "")
                # Extra safety: do not touch excluded titles, even if plan was edited manually
                if EXCLUDE_TITLE_SUBSTRING in title.lower():
                    summary["skipped"] += 1
                    details.append({"product_id": product_id, "status": "skipped", "reason": "excluded (One Piece)"})
                    continue

                res = apply_one(s, shop, token, it)
                summary["applied"] += 1
                details.append({"product_id": product_id, "status": "applied", "result": res})
            except Exception as e:
                summary["failed"] += 1
                details.append({"product_id": it.get("product_id"), "status": "failed", "reason": str(e)})

            time.sleep(SLEEP_BETWEEN_MUTATIONS_SEC)

        audit = {
            "applied_at_utc": utc_now(),
            "shop": shop,
            "api_version": API_VERSION,
            "plan_file": str(plan_path),
            "summary": summary,
            "details": details,
        }
        atomic_write_json(AUDIT_FILE, audit)

        print("=== APPLY RESULT ===")
        print(json.dumps(summary, indent=2))
        print(f"Audit: {AUDIT_FILE}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
