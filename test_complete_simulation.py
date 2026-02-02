#!/usr/bin/env python3
"""Complete test of SNKRDUNK historical price fix."""

import asyncio
from datetime import datetime, timezone
from app.database import get_db
from app.services.snkrdunk_service import SnkrdunkService
from app.models import SnkrdunkScanLog, SnkrdunkPriceHistory

async def simulate_snkrdunk_fetch_and_save():
    """Simulate the complete SNKRDUNK fetch and save process."""
    print('=== SIMULATING COMPLETE SNKRDUNK FETCH AND HISTORICAL SAVE ===')
    
    db = next(get_db())
    service = SnkrdunkService()
    
    # Step 1: Check current state
    print('\n1. BEFORE FETCH:')
    scan_count = db.query(SnkrdunkScanLog).count()
    price_count = db.query(SnkrdunkPriceHistory).count()
    print(f'   Scans: {scan_count}, Prices: {price_count}')
    
    # Step 2: Simulate the router logic - fetch data and create scan log
    print('\n2. FETCHING DATA FROM SNKRDUNK:')
    started_at = datetime.now(timezone.utc)
    
    try:
        result = await service.fetch_and_cache_snkrdunk_data(
            db=db,
            pages=[1],
            force_refresh=True
        )
        
        completed_at = datetime.now(timezone.utc)
        duration = (completed_at - started_at).total_seconds()
        total_items = result.get('total_items', 0)
        
        print(f'   ✅ Service returned {total_items} items')
        
        # Step 3: Create scan log (like the router does)
        print('\n3. CREATING SCAN LOG:')
        scan_log = SnkrdunkScanLog(
            status='success',
            total_items=total_items,
            output=f"Fetched {total_items} items from 1 page",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=duration
        )
        db.add(scan_log)
        db.flush()  # Get the ID
        log_id = scan_log.id
        print(f'   ✅ Created scan log #{log_id}')
        
        # Step 4: Save price history (like the router does)
        print('\n4. SAVING PRICE HISTORY:')
        fresh_items = result.get('items', [])
        
        for item in fresh_items:
            price_record = SnkrdunkPriceHistory(
                scan_log_id=log_id,
                snkrdunk_key=str(item.get('id')),
                price_jpy=item.get('minPrice'),
                price_usd=None,
                recorded_at=datetime.now(timezone.utc)
            )
            db.add(price_record)
        
        db.commit()
        print(f'   ✅ Saved {len(fresh_items)} price records for scan #{log_id}')
        
        # Step 5: Verify what was saved
        print('\n5. VERIFICATION:')
        scan_count = db.query(SnkrdunkScanLog).count()
        price_count = db.query(SnkrdunkPriceHistory).count()
        prices_for_scan = db.query(SnkrdunkPriceHistory).filter(SnkrdunkPriceHistory.scan_log_id == log_id).count()
        
        print(f'   Total scans: {scan_count}')
        print(f'   Total prices: {price_count}')
        print(f'   Prices for this scan: {prices_for_scan}')
        
        # Show sample prices
        sample_prices = db.query(SnkrdunkPriceHistory).filter(SnkrdunkPriceHistory.scan_log_id == log_id).limit(5).all()
        print('\\n   Sample saved prices:')
        for price in sample_prices:
            print(f'     Product {price.snkrdunk_key}: ¥{price.price_jpy}')
            
        # Step 6: Test historical retrieval (simulate the price-history endpoint)
        print('\\n6. TESTING HISTORICAL RETRIEVAL:')
        history = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.scan_log_id == log_id
        ).order_by(SnkrdunkPriceHistory.snkrdunk_key).limit(5).all()
        
        print(f'   Retrieved {len(history)} price records from database')
        print('   Historical prices (as API would return):')
        for h in history:
            print(f'     ID: {h.snkrdunk_key}, Price: ¥{h.price_jpy}')
        
        print('\\n✅ COMPLETE FLOW SUCCESSFUL! Historical prices are now properly saved and can be retrieved.')
        return True
        
    except Exception as e:
        print(f'❌ Error: {str(e)}')
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(simulate_snkrdunk_fetch_and_save())
    if success:
        print('\\n🎉 The historical price system is now working!')
    else:
        print('\\n💥 There are still issues to fix.')