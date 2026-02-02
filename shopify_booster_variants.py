#!/usr/bin/env python3
from __future__ import annotations

"""
shopify_booster_variants.py

PLAN mode (default):
- Fetch products from collection 444116140283
- Select any product that DOES NOT contain "One Piece" in the title (case-insensitive)
- Only plan for products that still look "unsplit":
    - exactly 1 variant
    - and does NOT already have option "Type" with "Booster Box"/"Booster Pack"
- Use CURRENT Shopify variant price as Booster Box price
- Compute Booster Pack price = (box_price / packs_per_box) * 1.20, rounded by your psych rule
- Write:
    data/booster_variant_plan_<timestamp>.json
    data/booster_variant_plan_latest.json

APPLY mode (APPLY_CHANGES=1 + CONFIRM_PLAN=<path or omitted>):
- Loads plan and applies:
  1) productUpdate: title -> base_title (plan provides; typically unchanged now)
  2) productOptionUpdate: rename single option to "Type" and add option values
  3) productVariantsBulkUpdate: existing variant -> Type=Booster Box, price=box price
  4) productVariantsBulkCreate: new variant -> Type=Booster Pack, price=pack price
  5) Cleanup: delete "Default Title" option value if unused (best-effort)

This supports preorders too (no exclusions).
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
PLAN_FILE = DATA_DIR / f"booster_variant_plan_{STAMP}.json"
PLAN_LATEST = DATA_DIR / "booster_variant_plan_latest.json"
AUDIT_FILE = DATA_DIR / f"booster_variant_audit_{STAMP}.json"

# =============================================================================
# Shopify config
# =============================================================================
SHOP_ENV = "SHOPIFY_SHOP"
TOKEN_ENV = "SHOPIFY_TOKEN"
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-01")

COLLECTION_NUMERIC_ENV = "SHOPIFY_COLLECTION_NUMERIC_ID"
DEFAULT_COLLECTION_NUMERIC_ID = "444116140283"

APPLY_ENV = "APPLY_CHANGES"
CONFIRM_PLAN_ENV = "CONFIRM_PLAN"

# =============================================================================
# Selection rules
# =============================================================================
EXCLUDE_TITLE_SUBSTRING = "one piece"  # case-insensitive

# =============================================================================
# Booster pack logic
# =============================================================================
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

OPTION_NAME = "Type"
BOX_VARIANT_VALUE = "Booster Box"
PACK_VARIANT_VALUE = "Booster Pack"

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


def detect_packs_per_box(title: str) -> int:
    t = (title or "").strip().lower()
    for kw, cnt in SPECIAL_PACK_COUNTS:
        if kw in t:
            return cnt
    return DEFAULT_PACKS_PER_BOX


def round_price_psych(n: float) -> int:
    """
    Your rounding:
      - Ceil
      - If within xx00..xx09 and >=100 => round DOWN to ...99 (e.g. 205 -> 199)
      - Else if ends with 5 or 9 => keep
      - Else round UP to next ending in 5 or 9
    """
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


# =============================================================================
# GraphQL docs
# =============================================================================
Q_COLLECTION_PRODUCTS = """
query CollectionProducts($id: ID!, $first: Int!, $after: String) {
  collection(id: $id) {
    id
    title
    products(first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      nodes {
        id
        title
        handle
        templateSuffix
        variants(first: 50) {
          nodes {
            id
            title
            price
            compareAtPrice
            inventoryQuantity
            availableForSale
            selectedOptions { name value }
          }
        }
        options {
          id
          name
          position
          values
          optionValues { id name hasVariants }
        }
      }
    }
  }
}
"""

Q_PRODUCT = """
query ProductGet($id: ID!) {
  product(id: $id) {
    id
    title
    options {
      id
      name
      position
      values
      optionValues { id name hasVariants }
    }
    variants(first: 50) {
      nodes {
        id
        title
        price
        compareAtPrice
        selectedOptions { name value }
      }
    }
  }
}
"""

M_PRODUCT_UPDATE_TITLE = """
mutation ProductUpdateTitle($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id title }
    userErrors { field message }
  }
}
"""

M_PRODUCT_OPTION_UPDATE = """
mutation UpdateOption(
  $productId: ID!,
  $option: OptionUpdateInput!,
  $optionValuesToAdd: [OptionValueCreateInput!],
  $optionValuesToUpdate: [OptionValueUpdateInput!],
  $optionValuesToDelete: [ID!],
  $variantStrategy: ProductOptionUpdateVariantStrategy
) {
  productOptionUpdate(
    productId: $productId,
    option: $option,
    optionValuesToAdd: $optionValuesToAdd,
    optionValuesToUpdate: $optionValuesToUpdate,
    optionValuesToDelete: $optionValuesToDelete,
    variantStrategy: $variantStrategy
  ) {
    userErrors { field message }
    product {
      id
      title
      options {
        id
        name
        position
        values
        optionValues { id name hasVariants }
      }
      variants(first: 50) {
        nodes {
          id
          title
          price
          selectedOptions { name value }
        }
      }
    }
  }
}
"""

M_VARIANTS_BULK_UPDATE = """
mutation VariantsBulkUpdate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkUpdate(productId: $productId, variants: $variants) {
    productVariants { id title price selectedOptions { name value } }
    userErrors { field message }
  }
}
"""

M_VARIANTS_BULK_CREATE = """
mutation VariantsBulkCreate($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
  productVariantsBulkCreate(productId: $productId, variants: $variants) {
    productVariants { id title price selectedOptions { name value } }
    userErrors { field message }
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
    old_title: str
    base_title: str
    packs_per_box: int
    booster_box_variant_id: str
    booster_box_price: float
    booster_pack_price: int


def find_option(product: dict[str, Any], name: str) -> Optional[dict[str, Any]]:
    opts = product.get("options")
    if not isinstance(opts, list):
        return None
    n = name.strip().lower()
    for o in opts:
        if isinstance(o, dict) and str(o.get("name") or "").strip().lower() == n:
            return o
    return None


def option_value_id(option: dict[str, Any], value_name: str) -> Optional[str]:
    ovs = option.get("optionValues")
    if not isinstance(ovs, list):
        return None
    target = value_name.strip().lower()
    for ov in ovs:
        if not isinstance(ov, dict):
            continue
        if str(ov.get("name") or "").strip().lower() == target:
            return str(ov.get("id")) if ov.get("id") else None
    return None


def has_booster_split_already(p: dict[str, Any]) -> bool:
    """
    Returns True if product already has a "Type" option including Booster Box / Booster Pack
    OR it already has two variants with those labels.
    """
    opt = find_option(p, OPTION_NAME)
    if opt:
        if option_value_id(opt, BOX_VARIANT_VALUE) or option_value_id(opt, PACK_VARIANT_VALUE):
            return True

    variants = (p.get("variants") or {}).get("nodes") if isinstance(p.get("variants"), dict) else []
    if not isinstance(variants, list):
        return False

    titles = {str(v.get("title") or "").strip().lower() for v in variants if isinstance(v, dict)}
    if BOX_VARIANT_VALUE.lower() in titles and PACK_VARIANT_VALUE.lower() in titles:
        return True

    return False


def get_only_variant(variants: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    vs = [v for v in variants if isinstance(v, dict)]
    return vs[0] if len(vs) == 1 else None


def build_plan(products: list[dict[str, Any]]) -> dict[str, Any]:
    items: list[PlanItem] = []
    skipped: list[dict[str, Any]] = []

    for p in products:
        title = str(p.get("title") or "").strip()
        if EXCLUDE_TITLE_SUBSTRING in title.lower():
            skipped.append({"product_id": gid_to_numeric(str(p.get("id") or "")), "reason": "excluded (One Piece)"})
            continue

        if has_booster_split_already(p):
            skipped.append({"product_id": gid_to_numeric(str(p.get("id") or "")), "reason": "already split"})
            continue

        variants = (p.get("variants") or {}).get("nodes") if isinstance(p.get("variants"), dict) else []
        if not isinstance(variants, list) or not variants:
            skipped.append({"product_id": gid_to_numeric(str(p.get("id") or "")), "reason": "no variants"})
            continue

        only = get_only_variant(variants)
        if not only:
            skipped.append({"product_id": gid_to_numeric(str(p.get("id") or "")), "reason": "not exactly 1 variant"})
            continue

        product_gid = str(p.get("id") or "")
        product_id = gid_to_numeric(product_gid)
        if not product_id:
            skipped.append({"product_id": None, "reason": "no product id"})
            continue

        try:
            box_price = float(only.get("price") or 0.0)
        except Exception:
            box_price = 0.0

        if box_price <= 0:
            skipped.append({"product_id": product_id, "reason": "invalid box price"})
            continue

        packs = detect_packs_per_box(title)
        pack_raw = (box_price / float(packs)) * PACK_MARKUP
        pack_price = round_price_psych(pack_raw)

        items.append(
            PlanItem(
                product_id=product_id,
                product_gid=product_gid,
                old_title=title,
                base_title=title,  # titles already normalized now; keep unchanged
                packs_per_box=packs,
                booster_box_variant_id=str(only.get("id") or ""),
                booster_box_price=box_price,
                booster_pack_price=pack_price,
            )
        )

    return {
        "generated_at_utc": utc_now(),
        "api_version": API_VERSION,
        "rules": {
            "select": f"in collection {DEFAULT_COLLECTION_NUMERIC_ID} AND title does NOT contain 'One Piece'",
            "plan_only_if": "not already split AND exactly 1 variant",
            "packs_default": DEFAULT_PACKS_PER_BOX,
            "special_packs": SPECIAL_PACK_COUNTS,
            "pack_markup": PACK_MARKUP,
            "rounding": "ceil; xx00..xx09 -> ...99; else keep 5/9; else move up to 5/9",
        },
        "counts": {"planned": len(items), "skipped": len(skipped)},
        "items": [asdict(x) for x in items],
        "skipped": skipped,
    }


# =============================================================================
# APPLY helpers
# =============================================================================
def fetch_product(session: requests.Session, shop: str, token: str, product_gid: str) -> dict[str, Any]:
    data = gql_call(session, shop, token, Q_PRODUCT, {"id": product_gid})
    p = data.get("product")
    if not isinstance(p, dict):
        raise RuntimeError("Product not found")
    return p


def update_title(session: requests.Session, shop: str, token: str, product_gid: str, base_title: str) -> None:
    data = gql_call(session, shop, token, M_PRODUCT_UPDATE_TITLE, {"input": {"id": product_gid, "title": base_title}})
    payload = data.get("productUpdate") or {}
    ue = payload.get("userErrors") or []
    if ue:
        raise RuntimeError(f"productUpdate userErrors: {ue}")


def find_single_option(product: dict[str, Any]) -> Optional[dict[str, Any]]:
    opts = product.get("options")
    if not isinstance(opts, list):
        return None
    opts = [o for o in opts if isinstance(o, dict)]
    return opts[0] if len(opts) == 1 else None


def ensure_type_option(session: requests.Session, shop: str, token: str, product: dict[str, Any]) -> dict[str, Any]:
    """
    Ensures an option named "Type" exists and includes values Booster Box/Booster Pack.
    Renames the single option to "Type" if needed.
    """
    type_opt = find_option(product, OPTION_NAME)
    product_id = str(product["id"])

    if type_opt:
        to_add = []
        if not option_value_id(type_opt, BOX_VARIANT_VALUE):
            to_add.append({"name": BOX_VARIANT_VALUE})
        if not option_value_id(type_opt, PACK_VARIANT_VALUE):
            to_add.append({"name": PACK_VARIANT_VALUE})
        if not to_add:
            return product

        data = gql_call(
            session, shop, token,
            M_PRODUCT_OPTION_UPDATE,
            {
                "productId": product_id,
                "option": {"id": str(type_opt["id"]), "name": OPTION_NAME, "position": int(type_opt.get("position") or 1)},
                "optionValuesToAdd": to_add,
                "optionValuesToUpdate": None,
                "optionValuesToDelete": None,
                "variantStrategy": "LEAVE_AS_IS",
            },
        )
        payload = data.get("productOptionUpdate") or {}
        ue = payload.get("userErrors") or []
        if ue:
            raise RuntimeError(f"productOptionUpdate userErrors: {ue}")
        return payload.get("product") or product

    single = find_single_option(product)
    if not single:
        raise RuntimeError("Product has multiple options; cannot auto-convert safely.")

    to_add = []
    if not option_value_id(single, BOX_VARIANT_VALUE):
        to_add.append({"name": BOX_VARIANT_VALUE})
    if not option_value_id(single, PACK_VARIANT_VALUE):
        to_add.append({"name": PACK_VARIANT_VALUE})

    data = gql_call(
        session, shop, token,
        M_PRODUCT_OPTION_UPDATE,
        {
            "productId": product_id,
            "option": {"id": str(single["id"]), "name": OPTION_NAME, "position": int(single.get("position") or 1)},
            "optionValuesToAdd": to_add if to_add else None,
            "optionValuesToUpdate": None,
            "optionValuesToDelete": None,
            "variantStrategy": "LEAVE_AS_IS",
        },
    )
    payload = data.get("productOptionUpdate") or {}
    ue = payload.get("userErrors") or []
    if ue:
        raise RuntimeError(f"productOptionUpdate userErrors: {ue}")
    return payload.get("product") or product


def set_box_variant(session: requests.Session, shop: str, token: str, product: dict[str, Any], box_variant_gid: str, box_price: float) -> None:
    opt = find_option(product, OPTION_NAME)
    if not opt:
        raise RuntimeError("Missing Type option")
    opt_id = str(opt["id"])

    data = gql_call(
        session, shop, token,
        M_VARIANTS_BULK_UPDATE,
        {
            "productId": str(product["id"]),
            "variants": [
                {
                    "id": box_variant_gid,
                    "price": float(box_price),
                    "optionValues": [{"optionId": opt_id, "name": BOX_VARIANT_VALUE}],
                }
            ],
        },
    )
    payload = data.get("productVariantsBulkUpdate") or {}
    ue = payload.get("userErrors") or []
    if ue:
        raise RuntimeError(f"productVariantsBulkUpdate userErrors: {ue}")


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
    vs = (product.get("variants") or {}).get("nodes") if isinstance(product.get("variants"), dict) else None
    if not isinstance(vs, list):
        return None
    for v in vs:
        if isinstance(v, dict) and variant_has_selected(v, opt_name, opt_value):
            return v
    return None


def create_pack_variant_if_missing(session: requests.Session, shop: str, token: str, product: dict[str, Any], pack_price: float) -> None:
    if find_variant_by_option(product, OPTION_NAME, PACK_VARIANT_VALUE):
        return

    opt = find_option(product, OPTION_NAME)
    if not opt:
        raise RuntimeError("Missing Type option")
    opt_id = str(opt["id"])

    data = gql_call(
        session, shop, token,
        M_VARIANTS_BULK_CREATE,
        {
            "productId": str(product["id"]),
            "variants": [
                {
                    "price": float(pack_price),
                    "optionValues": [{"optionId": opt_id, "name": PACK_VARIANT_VALUE}],
                }
            ],
        },
    )
    payload = data.get("productVariantsBulkCreate") or {}
    ue = payload.get("userErrors") or []
    if ue:
        raise RuntimeError(f"productVariantsBulkCreate userErrors: {ue}")


def cleanup_default_title_value(session: requests.Session, shop: str, token: str, product: dict[str, Any]) -> None:
    opt = find_option(product, OPTION_NAME)
    if not opt:
        return
    default_id = option_value_id(opt, "Default Title")
    if not default_id:
        return
    if find_variant_by_option(product, OPTION_NAME, "Default Title"):
        return

    data = gql_call(
        session, shop, token,
        M_PRODUCT_OPTION_UPDATE,
        {
            "productId": str(product["id"]),
            "option": {"id": str(opt["id"]), "name": OPTION_NAME, "position": int(opt.get("position") or 1)},
            "optionValuesToAdd": None,
            "optionValuesToUpdate": None,
            "optionValuesToDelete": [default_id],
            "variantStrategy": "LEAVE_AS_IS",
        },
    )
    payload = data.get("productOptionUpdate") or {}
    ue = payload.get("userErrors") or []
    if ue:
        # Non-fatal cleanup
        return


# =============================================================================
# Main
# =============================================================================
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

    print("=== Booster variants ===")
    print(f"Shop: {shop}")
    print(f"API: {API_VERSION}")
    print(f"Collection: {collection_gid}")
    print(f"Mode: {'APPLY' if apply_mode else 'PLAN'}")
    print(f"Excluding titles containing: 'One Piece'")
    print()

    with requests.Session() as s:
        if not apply_mode:
            # PLAN mode
            data = gql_call(s, shop, token, Q_COLLECTION_PRODUCTS, {"id": collection_gid, "first": 200, "after": None})
            coll = data.get("collection") or {}
            products = ((coll.get("products") or {}).get("nodes")) if isinstance(coll.get("products"), dict) else []
            if not isinstance(products, list):
                products = []

            payload = build_plan(products)
            atomic_write_json(PLAN_FILE, payload)
            atomic_write_json(PLAN_LATEST, payload)

            print("Plan created:")
            print(f"  {PLAN_FILE}")
            print(f"  {PLAN_LATEST}")
            print(json.dumps(payload.get("counts", {}), indent=2))
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

        for it in items:
            try:
                product_gid = str(it["product_gid"])
                product_id = int(it["product_id"])
                old_title = str(it.get("old_title") or "")
                base_title = str(it.get("base_title") or "")
                box_variant_gid = str(it.get("booster_box_variant_id") or "")
                box_price = float(it.get("booster_box_price") or 0.0)
                pack_price = float(it.get("booster_pack_price") or 0.0)

                if not product_gid or not base_title or not box_variant_gid or box_price <= 0 or pack_price <= 0:
                    summary["skipped"] += 1
                    details.append({"product_id": product_id, "status": "skipped", "reason": "invalid plan row"})
                    continue

                product = fetch_product(s, shop, token, product_gid)
                cur_title = str(product.get("title") or "").strip()

                # Exclusion safety (One Piece)
                if EXCLUDE_TITLE_SUBSTRING in cur_title.lower():
                    summary["skipped"] += 1
                    details.append({"product_id": product_id, "status": "skipped", "reason": "excluded (One Piece)"})
                    continue

                # Safety: if title changed since plan and is not the same, skip (prevents surprises)
                if old_title and cur_title != old_title and cur_title != base_title:
                    summary["skipped"] += 1
                    details.append(
                        {
                            "product_id": product_id,
                            "status": "skipped",
                            "reason": "title mismatch vs plan",
                            "plan_old_title": old_title,
                            "current_title": cur_title,
                        }
                    )
                    continue

                # Apply
                update_title(s, shop, token, product_gid, base_title)
                time.sleep(SLEEP_BETWEEN_MUTATIONS_SEC)

                product = fetch_product(s, shop, token, product_gid)
                product = ensure_type_option(s, shop, token, product)
                time.sleep(SLEEP_BETWEEN_MUTATIONS_SEC)

                product = fetch_product(s, shop, token, product_gid)
                set_box_variant(s, shop, token, product, box_variant_gid, box_price)
                time.sleep(SLEEP_BETWEEN_MUTATIONS_SEC)

                product = fetch_product(s, shop, token, product_gid)
                create_pack_variant_if_missing(s, shop, token, product, pack_price)
                time.sleep(SLEEP_BETWEEN_MUTATIONS_SEC)

                product = fetch_product(s, shop, token, product_gid)
                cleanup_default_title_value(s, shop, token, product)

                summary["applied"] += 1
                details.append({"product_id": product_id, "status": "applied", "base_title": base_title})

            except Exception as e:
                summary["failed"] += 1
                details.append({"product_id": it.get("product_id"), "status": "failed", "reason": str(e)})

            time.sleep(0.25)

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
