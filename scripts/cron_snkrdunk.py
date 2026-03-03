#!/usr/bin/env python3
"""
Cron: fetch and cache SNKRDUNK prices.

Runs the SNKRDUNK service directly — no HTTP server dependency.
Add to crontab via:  crontab -e
"""
import sys
from pathlib import Path

# Make sure the project root is on the path regardless of cwd
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from app.database import SessionLocal
from app.services.snkrdunk_service import snkrdunk_service

PAGES = [1, 2, 3]


def main() -> None:
    ts = datetime.now(ZoneInfo("Europe/Oslo")).strftime("%Y-%m-%d %H:%M:%S %Z")
    print(f"[{ts}] SNKRDUNK fetch starting (pages {PAGES})")
    db = SessionLocal()
    try:
        result = asyncio.run(
            snkrdunk_service.fetch_and_cache_snkrdunk_data(
                db, pages=PAGES, force_refresh=False
            )
        )
        total = result.get("total_items", 0)
        print(f"[{ts}] Done — {total} items cached")
    except Exception as exc:
        print(f"[{ts}] ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
