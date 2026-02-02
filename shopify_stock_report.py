#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Output files
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
OUT_FILE = DATA_DIR / f"stock_report_{STAMP}.json"
OUT_LATEST = DATA_DIR / "stock_report_latest.json"

# Shopify config
SHOPIFY_TOKEN_ENV = "SHOPIFY_TOKEN"
SHOPIFY_SHOP_ENV = "SHOPIFY_SHOP"  # e.g. ipvqw7-yh.myshopify.com
SHOPIFY_API_VERSION_ENV = "SHOPIFY_API_VERSION"  # optional
SHOPIFY_COLLECTION_NUMERIC_ID_ENV = "SHOPIFY_COLLECTION_NUMERIC_ID"  # optional

DEFAULT_COLLECTION_NUMERIC_ID = "444175384827"
DEFAULT_API_VERSION = "2025-01"

# Optional: flag "preorder" if either templateSuffix == "preorder" OR product is in a collection titled "preorder"
PREORDER_TEMPLATE_SUFFIX = "preorder"
PREORDER_COLLECTION_TITLE = "preorder"


@dataclass(frozen=True)
class VariantStock:
    product_id: str
    product_title: str
    handle: str
    template_suffix: Optional[str]
    preorder: bool

    variant_id: str
    variant_title: str
    sku: Optional[str]
    inventory_quantity: Optional[int]
    available_for_sale: Optional[bool]
    price: Optional[str]


def die(msg: str, code: int = 1) -> None:
    print(f"\nERROR: {msg}\n")
    raise SystemExit(code)


def atomic_write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def get_env(name: str, required: bool = True, default: Optional[str] = None) -> str:
    val = os.getenv(name, "").strip()
    if not val and default is not None:
        val = default
    if required and not val:
        die(f"Missing environment variable: {name}")
    return val


def shopify_graphql_url(shop: str, api_version: str) -> str:
    return f"https://{shop}/admin/api/{api_version}/graphql.json"


def graphql(session: requests.Session, url: str, token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "stock-report/1.0",
    }
    r = session.post(url, headers=headers, json={"query": query, "variables": variables}, timeout=60)
    r.raise_for_status()
    data = r.json()
    if "errors" in data and data["errors"]:
        raise RuntimeError(f"GraphQL errors: {data['errors']}")
    return data.get("data", {})


def fetch_collection_products(
    session: requests.Session,
    url: str,
    token: str,
    collection_gid: str,
) -> list[dict[str, Any]]:
    """
    Fetch all products in a collection with pagination.
    """
    query = """
    query CollectionProducts($id: ID!, $first: Int!, $after: String) {
      collection(id: $id) {
        id
        title
        products(first: $first, after: $after) {
          pageInfo { hasNextPage endCursor }
          edges {
            node {
              id
              title
              handle
              templateSuffix
              collections(first: 20) {
                edges { node { title } }
              }
              variants(first: 100) {
                edges {
                  node {
                    id
                    title
                    sku
                    price
                    availableForSale
                    inventoryQuantity
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    all_products: list[dict[str, Any]] = []
    after: Optional[str] = None
    first = 200

    while True:
        data = graphql(session, url, token, query, {"id": collection_gid, "first": first, "after": after})
        coll = data.get("collection")
        if not coll:
            raise RuntimeError("Collection not found or access denied.")

        products = coll.get("products", {})
        edges = products.get("edges", []) or []
        for e in edges:
            node = (e or {}).get("node")
            if isinstance(node, dict):
                all_products.append(node)

        page = products.get("pageInfo", {}) or {}
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")

    return all_products


def is_preorder_product(product_node: dict[str, Any]) -> bool:
    ts = (product_node.get("templateSuffix") or "").strip().lower()
    if ts == PREORDER_TEMPLATE_SUFFIX:
        return True

    colls = product_node.get("collections", {}) or {}
    for e in (colls.get("edges") or []):
        title = (((e or {}).get("node") or {}).get("title") or "").strip().lower()
        if title == PREORDER_COLLECTION_TITLE:
            return True
    return False


def build_rows(products: list[dict[str, Any]]) -> list[VariantStock]:
    rows: list[VariantStock] = []
    for p in products:
        product_id = str(p.get("id") or "")
        title = str(p.get("title") or "")
        handle = str(p.get("handle") or "")
        template_suffix = p.get("templateSuffix") if p.get("templateSuffix") is not None else None
        preorder = is_preorder_product(p)

        variants = (p.get("variants") or {}).get("edges") or []
        for ve in variants:
            v = (ve or {}).get("node") or {}
            if not isinstance(v, dict):
                continue

            inv = v.get("inventoryQuantity")
            inv_i: Optional[int] = int(inv) if isinstance(inv, int) else None

            afs = v.get("availableForSale")
            afs_b: Optional[bool] = bool(afs) if isinstance(afs, bool) else None

            rows.append(
                VariantStock(
                    product_id=product_id,
                    product_title=title,
                    handle=handle,
                    template_suffix=str(template_suffix) if template_suffix is not None else None,
                    preorder=preorder,
                    variant_id=str(v.get("id") or ""),
                    variant_title=str(v.get("title") or ""),
                    sku=(str(v.get("sku")) if v.get("sku") else None),
                    inventory_quantity=inv_i,
                    available_for_sale=afs_b,
                    price=(str(v.get("price")) if v.get("price") is not None else None),
                )
            )

    # Stable sorting for supplier readability
    rows.sort(key=lambda r: (r.preorder, r.product_title.lower(), (r.variant_title or "").lower()))
    return rows


def main() -> int:
    token = get_env(SHOPIFY_TOKEN_ENV, required=True)
    shop = get_env(SHOPIFY_SHOP_ENV, required=True)
    api_version = get_env(SHOPIFY_API_VERSION_ENV, required=False, default=DEFAULT_API_VERSION)
    collection_numeric_id = get_env(
        SHOPIFY_COLLECTION_NUMERIC_ID_ENV, required=False, default=DEFAULT_COLLECTION_NUMERIC_ID
    )

    url = shopify_graphql_url(shop, api_version)
    collection_gid = f"gid://shopify/Collection/{collection_numeric_id}"

    print("=== Shopify stock report ===")
    print(f"Shop: {shop}")
    print(f"API: {api_version}")
    print(f"Collection: {collection_gid}")
    print(f"Output: {OUT_FILE}")

    with requests.Session() as s:
        products = fetch_collection_products(s, url, token, collection_gid)

    rows = build_rows(products)

    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "shop": shop,
        "api_version": api_version,
        "collection": {
            "numeric_id": collection_numeric_id,
            "gid": collection_gid,
        },
        "counts": {
            "products": len(products),
            "variants": len(rows),
            "preorder_variants": sum(1 for r in rows if r.preorder),
        },
        "items": [asdict(r) for r in rows],
    }

    atomic_write_json(OUT_FILE, payload)
    atomic_write_json(OUT_LATEST, payload)

    print(json.dumps(payload["counts"], indent=2))
    print(f"Saved: {OUT_FILE}")
    print(f"Saved: {OUT_LATEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
