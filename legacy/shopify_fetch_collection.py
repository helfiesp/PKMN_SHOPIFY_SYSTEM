#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
SHOP = os.getenv("SHOPIFY_SHOP", "ipvqw7-yh.myshopify.com").strip()
TOKEN = os.getenv("SHOPIFY_TOKEN", "").strip()
API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-01").strip()

COLLECTION_NUMERIC_ID = os.getenv("TARGET_COLLECTION_NUMERIC_ID", "444175384827").strip()
COLLECTION_GID = f"gid://shopify/Collection/{COLLECTION_NUMERIC_ID}"

PREORDER_COLLECTION_QUERY = os.getenv("PREORDER_COLLECTION_QUERY", "title:preorder OR handle:preorder").strip()
PREORDER_TEMPLATE_SUFFIX = os.getenv("PREORDER_TEMPLATE_SUFFIX", "preorder").strip().lower()

# Optional: exclude products whose title contains any of these substrings (case-insensitive).
# Comma-separated, e.g. "one piece,deluxe"
EXCLUDE_TITLE_CONTAINS = os.getenv("EXCLUDE_TITLE_CONTAINS", "").strip()

OUT_DIR = Path(__file__).resolve().parent / "shopify"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUTFILE = OUT_DIR / f"collection_{COLLECTION_NUMERIC_ID}_active_variants.json"

GRAPHQL_ENDPOINT = f"https://{SHOP}/admin/api/{API_VERSION}/graphql.json"

REQUEST_TIMEOUT = 60
SLEEP_SEC = 0.25

if not TOKEN:
    print("ERROR: Set SHOPIFY_TOKEN env var to your Admin API access token (shpca_...)", file=sys.stderr)
    sys.exit(1)

# -----------------------------------------------------------------------------
# GraphQL helper
# -----------------------------------------------------------------------------
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
# Queries
# -----------------------------------------------------------------------------
QUERY_COLLECTION_PRODUCTS = """
query($collectionId: ID!, $first: Int!, $after: String) {
  collection(id: $collectionId) {
    id
    title
    products(first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges {
        node {
          id
          title
          handle
          status
          templateSuffix
          variants(first: 250) {
            edges {
              node {
                id
                title
                price
                compareAtPrice
                inventoryQuantity
                availableForSale
              }
            }
          }
        }
      }
    }
  }
}
"""

QUERY_FIND_PREORDER_COLLECTIONS = """
query($first: Int!, $query: String!) {
  collections(first: $first, query: $query) {
    edges { node { id title handle } }
  }
}
"""

QUERY_COLLECTION_PRODUCT_IDS = """
query($collectionId: ID!, $first: Int!, $after: String) {
  collection(id: $collectionId) {
    id
    title
    products(first: $first, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node { id } }
    }
  }
}
"""



def _excluded_title(title: str) -> bool:
    if not EXCLUDE_TITLE_CONTAINS:
        return False
    t = (title or '').lower()
    for part in EXCLUDE_TITLE_CONTAINS.split(','):
        part = part.strip().lower()
        if part and part in t:
            return True
    return False

# -----------------------------------------------------------------------------
# Fetchers
# -----------------------------------------------------------------------------
def find_preorder_collection_ids(session: requests.Session) -> list[dict[str, str]]:
    data = graphql(session, QUERY_FIND_PREORDER_COLLECTIONS, {"first": 25, "query": PREORDER_COLLECTION_QUERY})
    edges = (data.get("collections", {}).get("edges") or [])
    out: list[dict[str, str]] = []
    for e in edges:
        n = e.get("node") or {}
        cid = n.get("id")
        if cid:
            out.append({"id": cid, "title": n.get("title") or "", "handle": n.get("handle") or ""})
    return out

def fetch_product_ids_for_collection(session: requests.Session, collection_id: str) -> set[str]:
    after = None
    product_ids: set[str] = set()
    while True:
        data = graphql(session, QUERY_COLLECTION_PRODUCT_IDS, {"collectionId": collection_id, "first": 250, "after": after})
        col = data.get("collection")
        if not col:
            break
        conn = col["products"]
        for edge in conn["edges"]:
            node = edge.get("node") or {}
            pid = node.get("id")
            if pid:
                product_ids.add(pid)
        if not conn["pageInfo"]["hasNextPage"]:
            break
        after = conn["pageInfo"]["endCursor"]
        time.sleep(SLEEP_SEC)
    return product_ids

def fetch_collection_active_variants(session: requests.Session, collection_gid: str, preorder_product_ids: set[str]) -> dict[str, Any]:
    after = None

    result: dict[str, Any] = {
        "shop": SHOP,
        "api_version": API_VERSION,
        "collection": {
            "id": collection_gid,
            "numeric_id": COLLECTION_NUMERIC_ID,
            "title": None,
        },
        "preorder_detection": {
            "collection_query": PREORDER_COLLECTION_QUERY,
            "template_suffix": PREORDER_TEMPLATE_SUFFIX,
            "preorder_product_ids_count": len(preorder_product_ids),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "products": [],
    }

    while True:
        data = graphql(session, QUERY_COLLECTION_PRODUCTS, {"collectionId": collection_gid, "first": 250, "after": after})
        collection = data.get("collection")
        if not collection:
            raise RuntimeError(f"Collection not found or no access: {collection_gid}")

        result["collection"]["title"] = collection.get("title")

        products = collection["products"]
        for edge in products["edges"]:
            p = edge["node"]
            if p.get("status") != "ACTIVE":
                continue

            if _excluded_title(p.get("title") or ""):
                continue

            template_suffix = (p.get("templateSuffix") or None)
            is_preorder = (p["id"] in preorder_product_ids) or ((template_suffix or "").strip().lower() == PREORDER_TEMPLATE_SUFFIX)

            variants = []
            for vedge in (p.get("variants", {}).get("edges") or []):
                v = vedge["node"]
                variants.append(
                    {
                        "variant_id": v["id"],                 # gid://shopify/ProductVariant/...
                        "variant_title": v.get("title") or "",
                        "price": v.get("price"),
                        "compare_at_price": v.get("compareAtPrice"),
                        "inventory_quantity": v.get("inventoryQuantity"),
                        "available_for_sale": v.get("availableForSale"),
                    }
                )

            result["products"].append(
                {
                    "product_id": p["id"],                    # gid://shopify/Product/...
                    "title": p.get("title") or "",
                    "handle": p.get("handle") or "",
                    "status": p.get("status") or "",
                    "template_suffix": template_suffix,
                    "is_preorder": bool(is_preorder),
                    "variants": variants,
                }
            )

        if not products["pageInfo"]["hasNextPage"]:
            break
        after = products["pageInfo"]["endCursor"]
        time.sleep(SLEEP_SEC)

    return result

# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def main() -> int:
    with requests.Session() as s:
        preorder_cols = find_preorder_collection_ids(s)
        preorder_ids: set[str] = set()
        for c in preorder_cols:
            preorder_ids |= fetch_product_ids_for_collection(s, c["id"])

        data = fetch_collection_active_variants(s, COLLECTION_GID, preorder_ids)

    with OUTFILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Wrote {OUTFILE}")
    print(f"Products: {len(data['products'])}")
    if preorder_cols:
        print(f"Preorder collections found: {len(preorder_cols)}")
        for c in preorder_cols:
            print(f"  - {c['title']} ({c['handle']})")
        print(f"Preorder products flagged: {len(preorder_ids)}")
    else:
        print("Preorder collections found: 0")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
