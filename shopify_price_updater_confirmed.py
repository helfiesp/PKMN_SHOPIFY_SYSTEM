#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
SHOP = os.getenv("SHOPIFY_SHOP", "ipvqw7-yh.myshopify.com").strip()
TOKEN = os.getenv("SHOPIFY_TOKEN", "").strip()
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-01").strip()
GRAPHQL_ENDPOINT = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"

APPLY_CHANGES = os.getenv("APPLY_CHANGES", "").strip() == "1"
CONFIRM_PLAN = os.getenv("CONFIRM_PLAN", "").strip()  # required for APPLY

MIN_PRICE_CHANGE_NOK = 25.0
PACK_MIN_PRICE_CHANGE_NOK = 10.0
MASSIVE_CHANGE_NOK = float(os.getenv("MASSIVE_CHANGE_NOK", "500").strip() or "500")
ALLOWED_ENDINGS = (25, 49, 75, 99)

# --------------------------------------------------------------------------
# Booster split support
# --------------------------------------------------------------------------
# If a product has been split into Type=Booster Box / Booster Pack variants,
# the pipeline should treat the Booster Box as the "primary" variant for
# SNKRDUNK mapping + pricing, and ALSO keep the Booster Pack price in sync
# whenever the box price changes.

BOOSTER_BOX_TITLE = "Booster Box"
BOOSTER_PACK_TITLE = "Booster Pack"

# Keep pack pricing aligned with your booster split script:
_SPECIAL_PACK_COUNTS = [
    ("terastal festival", 10),
    ("mega dream", 10),
    ("vstar universe", 10),
    ("shiny treasure ex", 10),
    ("shiny treasure", 10),
    ("pokemon 151", 20),
    ("black bolt", 20),
    ("white flare", 20),
]
_DEFAULT_PACKS_PER_BOX = 30
_PACK_MARKUP = 1.20

def _detect_packs_per_box(title: str) -> int:
    t = (title or "").strip().lower()
    for kw, cnt in _SPECIAL_PACK_COUNTS:
        if kw in t:
            return cnt
    return _DEFAULT_PACKS_PER_BOX

def _round_pack_price_psych(n: float) -> int:
    """Same psych rounding as shopify_booster_variants.py."""
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

def _select_booster_box_variant(variants: list[dict[str, Any]]) -> dict[str, Any]:
    """Prefer Booster Box variant if present, else fall back to first."""
    for v in variants:
        if str(v.get("variant_title") or "").strip().lower() == BOOSTER_BOX_TITLE.lower():
            return v
    return variants[0]

def _find_variant_by_title(variants: list[dict[str, Any]], title: str) -> Optional[dict[str, Any]]:
    for v in variants:
        if str(v.get("variant_title") or "").strip().lower() == title.strip().lower():
            return v
    return None


REQUEST_TIMEOUT = 60
SLEEP_SEC = 0.25

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_RESULTS_FILE = DATA_DIR / "results.json"
DEFAULT_SHOPIFY_SNAPSHOT = SCRIPT_DIR / "shopify" / "collection_444175384827_active_variants.json"
# Optional overrides (used by booster box pipeline)
RESULTS_FILE = Path(os.getenv("RESULTS_FILE", str(DEFAULT_RESULTS_FILE))).expanduser()
SHOPIFY_SNAPSHOT = Path(os.getenv("SHOPIFY_SNAPSHOT_FILE", str(DEFAULT_SHOPIFY_SNAPSHOT))).expanduser()
# Optional: prefix for plan/apply output filenames
PLAN_PREFIX = os.getenv("PLAN_PREFIX", "price_update").strip() or "price_update"
# -----------------------------------------------------------------------------
# GraphQL
# -----------------------------------------------------------------------------
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

def graphql(session: requests.Session, query: str, variables: dict | None = None) -> dict:
    r = session.post(
        GRAPHQL_ENDPOINT,
        headers={"X-Shopify-Access-Token": TOKEN, "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=REQUEST_TIMEOUT,
    )
    r.raise_for_status()
    payload = r.json()
    if "errors" in payload:
        raise RuntimeError(f"GraphQL errors: {payload['errors']}")
    if payload.get("data") is None:
        raise RuntimeError(f"Unexpected response: {payload}")
    return payload["data"]

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def now_utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def parse_float_or_none(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None

def to_money_str(v: float | int) -> str:
    return f"{float(v):.2f}"

def round_up_to_allowed_ending(amount: float) -> int:
    """
    Forces integer NOK to end with 25/49/75/99 (rounding UP).
    """
    n = int(amount)
    if amount > n:
        n += 1
    base = (n // 100) * 100
    tail = n - base
    for e in ALLOWED_ENDINGS:
        if tail <= e:
            return base + e
    return base + 100 + ALLOWED_ENDINGS[0]

def build_snapshot_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Returns dict keyed by product_id:
      {
        product_id: {
          "product": {...},
          "variant": first variant dict,
        }
      }
    """
    idx: dict[str, dict[str, Any]] = {}
    for p in (snapshot.get("products") or []):
        if not isinstance(p, dict):
            continue
        if (p.get("status") or "").upper() != "ACTIVE":
            continue
        variants = p.get("variants") or []
        if not variants:
            continue
        primary = _select_booster_box_variant(variants) if variants else None
        idx[str(p["product_id"])] = {"product": p, "variant": primary, "variants": variants}
    return idx

# -----------------------------------------------------------------------------
# Plan generation
# -----------------------------------------------------------------------------
def generate_plan(results: dict[str, Any], snapshot_idx: dict[str, dict[str, Any]]) -> dict[str, Any]:
    items = results.get("items") or []
    plan_items: list[dict[str, Any]] = []

    skipped = {"no_match": 0, "preorder": 0, "no_variant": 0, "no_reco": 0, "no_change": 0}

    for it in items:
        shop = (it.get("shopify") or {})
        if not isinstance(shop, dict) or not shop.get("matched"):
            skipped["no_match"] += 1
            continue

        product_id = shop.get("product_id")
        if not product_id or product_id not in snapshot_idx:
            skipped["no_match"] += 1
            continue

        snap_prod = snapshot_idx[product_id]["product"]
        snap_var = snapshot_idx[product_id]["variant"]

        if bool(snap_prod.get("is_preorder")):
            skipped["preorder"] += 1
            continue
        if (snap_prod.get("template_suffix") or "").strip().lower() == "preorder":
            skipped["preorder"] += 1
            continue

        variant_id = snap_var.get("variant_id")
        if not variant_id:
            skipped["no_variant"] += 1
            continue

        current_price = parse_float_or_none(snap_var.get("price"))
        current_compare = parse_float_or_none(snap_var.get("compare_at_price"))

        reco = it.get("recommended_sale_price_nok_inc_vat")
        if reco is None:
            skipped["no_reco"] += 1
            continue

        target = round_up_to_allowed_ending(float(reco))
        delta = (target - float(current_price)) if current_price is not None else None
        if current_price is None or delta is None:
            skipped["no_variant"] += 1
            continue

        if abs(delta) < MIN_PRICE_CHANGE_NOK:
            skipped["no_change"] += 1
            continue

        reason = "increase" if delta > 0 else "decrease"
        new_compare = float(current_price) if reason == "decrease" else None

        row_box = {
            "product_id": product_id,
            "product_title": snap_prod.get("title"),
            "handle": snap_prod.get("handle"),
            "variant_id": variant_id,
            "variant_title": snap_var.get("variant_title"),
            "snkrdunk_apparel_id": it.get("apparel_id"),
            "snkrdunk_link": it.get("link"),
            "snapshot_old_price": current_price,
            "snapshot_old_compare_at_price": current_compare,
            "recommended_raw": float(reco),
            "recommended_adjusted": int(target),
            "new_price": float(target),
            "new_compare_at_price": new_compare,
            "delta": float(delta),
            "massive_change": bool(abs(delta) >= MASSIVE_CHANGE_NOK),
            "reason": reason,
        }
        plan_items.append(row_box)

        # If this product has been split, also update the Booster Pack price derived from the NEW box price.
        variants_all = snapshot_idx[product_id].get("variants") or []
        pack_v = _find_variant_by_title(variants_all, BOOSTER_PACK_TITLE) if isinstance(variants_all, list) else None
        if pack_v and pack_v.get("variant_id"):
            pack_current = parse_float_or_none(pack_v.get("price"))
            pack_compare = parse_float_or_none(pack_v.get("compare_at_price"))

            packs_per_box = _detect_packs_per_box(str(snap_prod.get("title") or ""))
            pack_raw = (float(target) / float(packs_per_box)) * _PACK_MARKUP
            pack_target = float(_round_pack_price_psych(pack_raw))

            pack_delta = (pack_target - float(pack_current)) if pack_current is not None else None
            # NOTE: Pack pricing is derived from the *new* box price. We generally want to keep packs in sync
            # even for small changes, so we use PACK_MIN_PRICE_CHANGE_NOK (default 0) instead of MIN_PRICE_CHANGE_NOK.
            if pack_current is not None and pack_delta is not None and abs(pack_delta) >= PACK_MIN_PRICE_CHANGE_NOK:
                pack_reason = "increase" if pack_delta > 0 else "decrease"
                pack_new_compare = float(pack_current) if pack_reason == "decrease" else None

                plan_items.append(
                    {
                        "product_id": product_id,
                        "product_title": snap_prod.get("title"),
                        "handle": snap_prod.get("handle"),
                        "variant_id": str(pack_v["variant_id"]),
                        "variant_title": str(pack_v.get("variant_title") or ""),
                        "snkrdunk_apparel_id": it.get("apparel_id"),
                        "snkrdunk_link": it.get("link"),
                        "snapshot_old_price": pack_current,
                        "snapshot_old_compare_at_price": pack_compare,
                        "recommended_raw": float(reco),
                        "recommended_adjusted": int(pack_target),
                        "new_price": float(pack_target),
                        "new_compare_at_price": pack_new_compare,
                        "delta": float(pack_delta),
                        "massive_change": bool(abs(pack_delta) >= MASSIVE_CHANGE_NOK),
                        "reason": pack_reason,
                    }
                )

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "shop": SHOP,
        "api_version": API_VERSION,
        "min_price_change_nok": MIN_PRICE_CHANGE_NOK,
        "allowed_endings": list(ALLOWED_ENDINGS),
        "massive_change_nok": MASSIVE_CHANGE_NOK,
        "counts": {
            "planned_changes": len(plan_items),
            "massive": sum(1 for x in plan_items if x["massive_change"]),
            "skipped": skipped,
        },
        "items": plan_items,
    }

# -----------------------------------------------------------------------------
# Apply plan with confirmation
# -----------------------------------------------------------------------------
def apply_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """
    Applies updates ONLY if live variant price/compareAt still match snapshot in plan.
    Updates grouped by product_id using productVariantsBulkUpdate.
    """
    results = {
        "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        "applied": 0,
        "failed": 0,
        "skipped_price_changed": 0,
        "skipped_missing_live": 0,
        "items": [],
    }

    # group by product_id
    grouped: dict[str, list[dict[str, Any]]] = {}
    meta_by_variant: dict[str, dict[str, Any]] = {}

    for row in (plan.get("items") or []):
        grouped.setdefault(row["product_id"], []).append(row)
        meta_by_variant[row["variant_id"]] = row

    with requests.Session() as s:
        for product_id, rows in grouped.items():
            # build variant inputs for those that still match live snapshot
            inputs = []
            to_record = []

            for row in rows:
                variant_id = row["variant_id"]
                try:
                    live = graphql(s, QUERY_VARIANT_GET, {"id": variant_id}).get("productVariant")
                    if not isinstance(live, dict):
                        results["skipped_missing_live"] += 1
                        row = dict(row)
                        row["apply_status"] = "skipped_missing_live"
                        results["items"].append(row)
                        continue

                    live_price = parse_float_or_none(live.get("price"))
                    live_compare = parse_float_or_none(live.get("compareAtPrice"))

                    # Confirm against the snapshot the plan was built from
                    if (live_price != row["snapshot_old_price"]) or (live_compare != row["snapshot_old_compare_at_price"]):
                        results["skipped_price_changed"] += 1
                        row = dict(row)
                        row["apply_status"] = "skipped_price_changed"
                        row["live_price"] = live_price
                        row["live_compare_at_price"] = live_compare
                        results["items"].append(row)
                        continue

                    inputs.append(
                        {
                            "id": variant_id,
                            "price": to_money_str(row["new_price"]),
                            "compareAtPrice": to_money_str(row["new_compare_at_price"]) if row["new_compare_at_price"] is not None else None,
                        }
                    )
                    to_record.append(row)

                except Exception as e:
                    row = dict(row)
                    row["apply_status"] = "failed_live_read"
                    row["error"] = str(e)
                    results["items"].append(row)
                    results["failed"] += 1

            if not inputs:
                continue

            # Apply mutation
            try:
                resp = graphql(s, MUTATION_PRODUCT_VARIANTS_BULK_UPDATE, {"productId": product_id, "variants": inputs})
                out = resp.get("productVariantsBulkUpdate") or {}
                errs = out.get("userErrors") or []
                if errs:
                    msg = f"userErrors: {errs}"
                    for row in to_record:
                        r2 = dict(row)
                        r2["apply_status"] = "failed_user_errors"
                        r2["error"] = msg
                        results["items"].append(r2)
                    results["failed"] += len(to_record)
                else:
                    for row in to_record:
                        r2 = dict(row)
                        r2["apply_status"] = "applied"
                        results["items"].append(r2)
                    results["applied"] += len(to_record)

            except Exception as e:
                for row in to_record:
                    r2 = dict(row)
                    r2["apply_status"] = "failed_mutation"
                    r2["error"] = str(e)
                    results["items"].append(r2)
                results["failed"] += len(to_record)

            time.sleep(SLEEP_SEC)

    return results

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> int:
    if not TOKEN:
        print("ERROR: Set SHOPIFY_TOKEN env var to your Admin API access token (shpca_...)", file=sys.stderr)
        return 1

    results = load_json(RESULTS_FILE)
    if not isinstance(results, dict):
        print(f"ERROR: Missing/invalid {RESULTS_FILE}. Run: python snkrdunk.py", file=sys.stderr)
        return 1

    snapshot = load_json(SHOPIFY_SNAPSHOT)
    if not isinstance(snapshot, dict):
        print(f"ERROR: Missing/invalid {SHOPIFY_SNAPSHOT}. Run: python shopify_fetch_collection.py", file=sys.stderr)
        return 1

    snapshot_idx = build_snapshot_index(snapshot)

    if APPLY_CHANGES:
        if not CONFIRM_PLAN:
            print("ERROR: APPLY_CHANGES=1 requires CONFIRM_PLAN=/path/to/*_plan_*.json", file=sys.stderr)
            return 1
        plan_path = Path(CONFIRM_PLAN)
        plan = load_json(plan_path)
        if not isinstance(plan, dict) or "items" not in plan:
            print(f"ERROR: Invalid plan file: {plan_path}", file=sys.stderr)
            return 1

        print("=== APPLY MODE ===")
        print(f"Using plan: {plan_path}")
        applied = apply_plan(plan)

        out_path = DATA_DIR / f"{PLAN_PREFIX}_apply_{now_utc_stamp()}.json"
        atomic_write_json(out_path, {"plan_file": str(plan_path), **applied})

        print(f"Apply report: {out_path}")
        print(json.dumps({k: applied[k] for k in ["applied", "failed", "skipped_price_changed", "skipped_missing_live"]}, indent=2))
        return 0

    # PLAN MODE
    print("=== PLAN MODE (no updates) ===")
    plan = generate_plan(results, snapshot_idx)

    plan_path = DATA_DIR / f"{PLAN_PREFIX}_plan_{now_utc_stamp()}.json"
    atomic_write_json(plan_path, plan)

    print(f"Plan written: {plan_path}")
    print(json.dumps(plan["counts"], indent=2))

    # Make massive changes very visible
    massive = [x for x in plan["items"] if x.get("massive_change")]
    if massive:
        print("\n!!! MASSIVE CHANGES !!!")
        for x in sorted(massive, key=lambda r: abs(r.get("delta", 0)), reverse=True):
            print(f"- {x.get('product_title')} | {x.get('snapshot_old_price')} -> {x.get('new_price')} (Δ {x.get('delta')})")

    print("\nTo apply THIS plan:")
    print('  PowerShell:  $env:APPLY_CHANGES="1"; $env:CONFIRM_PLAN="' + str(plan_path) + '"; python .\\shopify_price_updater_confirmed.py')
    print("  CMD:         set APPLY_CHANGES=1 && set CONFIRM_PLAN=" + str(plan_path) + " && python shopify_price_updater_confirmed.py")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
