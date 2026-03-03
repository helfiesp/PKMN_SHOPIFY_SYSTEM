#!/usr/bin/env python3
"""
Cron: sync Shopify product catalog.

Runs the Shopify service directly — no HTTP server dependency.
Add to crontab via:  crontab -e
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.services.shopify_service import shopify_service
from app.config import settings

# Collection IDs to sync (add more if needed)
COLLECTION_IDS = [
    settings.default_collection_id,
    settings.booster_collection_id,
]


def main() -> None:
    ts = datetime.now(ZoneInfo("Europe/Oslo")).strftime("%Y-%m-%d %H:%M:%S %Z")
    db = SessionLocal()
    try:
        for col_id in COLLECTION_IDS:
            print(f"[{ts}] Syncing collection {col_id}...")
            result = asyncio.run(
                shopify_service.fetch_and_store_collection(db, collection_id=col_id)
            )
            synced = getattr(result, "products_synced", None) or result
            print(f"[{ts}] Collection {col_id} done — {synced}")
    except Exception as exc:
        print(f"[{ts}] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
