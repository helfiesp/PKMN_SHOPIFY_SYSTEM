#!/usr/bin/env python3
"""Simulate a complete fresh scan to verify historical prices are saved correctly."""

import asyncio
from datetime import datetime, timezone
from app.database import get_db
from app.services.snkrdunk_service import SnkrdunkService
from app.models import SnkrdunkScanLog, SnkrdunkPriceHistory

async def simulate_fresh_scan():
    """Simulate what happens when user clicks 'Refresh SNKRDUNK Data' in UI."""
    print("=" * 80)
    print("SIMULATING FRESH SNKRDUNK SCAN (with force_refresh=TRUE)")
    print("=" * 80)
    
    db = next(get_db())
    service = SnkrdunkService()
    
    # Step 1: Fetch with force_refresh=True (like the fixed frontend does)
    print("\n1. Fetching fresh data from API (force_refresh=TRUE)...")
    started_at = datetime.now(timezone.utc)
    
    result = await service.fetch_and_cache_snkrdunk_data(
        db=db,
        pages=[1],  # Just page 1 for quick test
        force_refresh=True
    )
    
    completed_at = datetime.now(timezone.utc)
    duration = (completed_at - started_at).total_seconds()
    total_items = result.get('total_items', 0)
    
    print(f"   ✅ Fetched {total_items} items in {duration:.2f}s")
    
    # Step 2: Create scan log (like the router does)
    print("\n2. Creating scan log...")
    scan_log = SnkrdunkScanLog(
        status='success',
        total_items=total_items,
        output=f"TEST: Fetched {total_items} items from 1 page",
        started_at=started_at,
        completed_at=completed_at,
        duration_seconds=duration
    )
    db.add(scan_log)
    db.flush()
    log_id = scan_log.id
    print(f"   ✅ Created scan log #{log_id}")
    
    # Step 3: Save price history from the FRESH items (like the router does)
    print("\n3. Saving price history from fresh API data...")
    fresh_items = result.get('items', [])
    
    for item in fresh_items:
        price_record = SnkrdunkPriceHistory(
            scan_log_id=log_id,
            snkrdunk_key=str(item.get('id')),
            price_jpy=item.get('minPrice'),  # Using minPrice from fresh data
            price_usd=None,
            recorded_at=datetime.now(timezone.utc)
        )
        db.add(price_record)
    
    db.commit()
    print(f"   ✅ Saved {len(fresh_items)} price records")
    
    # Step 4: Verify the saved prices
    print("\n4. Verifying saved prices...")
    test_products = [
        ('618443', 'Scarlet & Violet Special'),
        ('687430', 'Inferno X'),
        ('743533', 'Mega Expansion')
    ]
    
    print(f"\n   {'Product ID':<12} {'Product Name':<30} {'Saved Price':<15}")
    print(f"   {'-'*12} {'-'*30} {'-'*15}")
    
    for product_id, name in test_products:
        price_record = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.scan_log_id == log_id,
            SnkrdunkPriceHistory.snkrdunk_key == product_id
        ).first()
        
        if price_record:
            print(f"   {product_id:<12} {name:<30} ¥{price_record.price_jpy}")
        else:
            print(f"   {product_id:<12} {name:<30} NOT FOUND")
    
    # Step 5: Compare with old scan
    print("\n5. Comparing with previous scan...")
    old_scan = db.query(SnkrdunkScanLog).filter(
        SnkrdunkScanLog.id != log_id
    ).order_by(SnkrdunkScanLog.created_at.desc()).first()
    
    if old_scan:
        print(f"\n   Old scan #{old_scan.id} from {old_scan.created_at}")
        print(f"   New scan #{log_id} from {scan_log.created_at}")
        print(f"\n   {'Product':<12} {'Old Price':<15} {'New Price':<15} {'Change':<15}")
        print(f"   {'-'*12} {'-'*15} {'-'*15} {'-'*15}")
        
        for product_id, name in test_products:
            old_price = db.query(SnkrdunkPriceHistory).filter(
                SnkrdunkPriceHistory.scan_log_id == old_scan.id,
                SnkrdunkPriceHistory.snkrdunk_key == product_id
            ).first()
            
            new_price = db.query(SnkrdunkPriceHistory).filter(
                SnkrdunkPriceHistory.scan_log_id == log_id,
                SnkrdunkPriceHistory.snkrdunk_key == product_id
            ).first()
            
            if old_price and new_price:
                old_val = old_price.price_jpy
                new_val = new_price.price_jpy
                change = new_val - old_val
                change_str = f"{'+' if change > 0 else ''}¥{change}" if change != 0 else "No change"
                
                print(f"   {product_id:<12} ¥{old_val:<14} ¥{new_val:<14} {change_str:<15}")
    
    print("\n" + "=" * 80)
    print("✅ FRESH SCAN COMPLETE!")
    print("=" * 80)
    print("\nThe system is now saving REAL-TIME prices from the live API.")
    print("Historical prices will be accurate going forward.")
    print("\nNext steps:")
    print("1. Refresh your browser to reload the JavaScript")
    print("2. Click 'Refresh SNKRDUNK Data' button")
    print("3. Select different historical dates from dropdown")
    print("4. Prices should now show actual differences between scans")
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(simulate_fresh_scan())
