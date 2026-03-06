#!/usr/bin/env python3
"""
Cron: sync Shopify product catalog and clear expired stock dates.

Runs the Shopify service directly — no HTTP server dependency.
Add to crontab via:  crontab -e
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.models import Product
from app.services.shopify_service import shopify_service
from app.config import settings

# Collection IDs to sync (add more if needed)
COLLECTION_IDS = [
    settings.default_collection_id,
    settings.booster_collection_id,
]


def clear_expired_stock_dates(db) -> dict:
    """Clear stock_date on Shopify and in DB for all products where date ≤ today."""
    import requests

    today = date.today()
    token = settings.get_shopify_token()
    shop = settings.get_shopify_shop()
    base = f"https://{shop}/admin/api/{settings.shopify_api_version}"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    expired = (
        db.query(Product)
        .filter(Product.stock_date.isnot(None), Product.stock_date != "")
        .all()
    )
    cleared, errors = [], []

    for product in expired:
        try:
            stock_dt = date.fromisoformat(product.stock_date)
        except ValueError:
            continue
        if stock_dt > today:
            continue

        numeric_id = product.shopify_id.split("/")[-1]
        # Fetch the metafield ID from Shopify
        mf_url = f"{base}/products/{numeric_id}/metafields.json?namespace=custom&key=stock_date&limit=1"
        mf_resp = requests.get(mf_url, headers=headers, timeout=15)
        mfs = mf_resp.json().get("metafields", []) if mf_resp.ok else []
        if not mfs:
            # Date already gone from Shopify — just clear locally
            product.stock_date = None
            cleared.append(numeric_id)
            continue

        del_resp = requests.delete(f"{base}/metafields/{mfs[0]['id']}.json", headers=headers, timeout=15)
        if del_resp.ok:
            product.stock_date = None
            cleared.append(numeric_id)
        else:
            errors.append(numeric_id)

    db.commit()
    return {"cleared": len(cleared), "errors": len(errors)}


def main() -> None:
    ts = datetime.now(ZoneInfo("Europe/Oslo")).strftime("%Y-%m-%d %H:%M:%S %Z")
    db = SessionLocal()
    try:
        # 1. Sync collections
        for col_id in COLLECTION_IDS:
            print(f"[{ts}] Syncing collection {col_id}...")
            result = asyncio.run(
                shopify_service.fetch_and_store_collection(db, collection_id=col_id)
            )
            synced = getattr(result, "products_synced", None) or result
            print(f"[{ts}] Collection {col_id} done — {synced}")

        # 2. Clear expired stock dates
        print(f"[{ts}] Clearing expired stock dates...")
        result = clear_expired_stock_dates(db)
        print(f"[{ts}] Stock dates cleared: {result['cleared']}, errors: {result['errors']}")

    except Exception as exc:
        print(f"[{ts}] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
