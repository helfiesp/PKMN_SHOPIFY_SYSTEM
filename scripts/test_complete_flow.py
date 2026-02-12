#!/usr/bin/env python3
"""Test the complete fixed SNKRDUNK historical price system."""

import requests
import time
from app.database import get_db
from app.models import SnkrdunkScanLog, SnkrdunkPriceHistory

def test_complete_flow():
    print('=== TESTING COMPLETE SNKRDUNK HISTORICAL PRICE FLOW ===')
    
    # Step 1: Check current state
    db = next(get_db())
    print('\n1. BEFORE FETCH:')
    scan_count = db.query(SnkrdunkScanLog).count()
    price_count = db.query(SnkrdunkPriceHistory).count()
    print(f'   Scans: {scan_count}, Prices: {price_count}')
    
    # Step 2: Make a fresh fetch
    print('\n2. MAKING FRESH FETCH:')
    try:
        response = requests.post('http://localhost:8000/api/v1/snkrdunk/fetch', 
                                json={'pages': [1], 'force_refresh': True},
                                headers={'Content-Type': 'application/json'},
                                timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f'   ✅ Fetch successful!')
            print(f'   Total items: {data.get("total_items")}')
            print(f'   Log ID: {data.get("log_id")}')
            new_log_id = data.get("log_id")
        else:
            print(f'   ❌ Fetch failed: {response.status_code}')
            print(f'   Response: {response.text[:200]}...')
            return
            
    except Exception as e:
        print(f'   ❌ Error testing fetch: {str(e)}')
        return
    
    # Step 3: Check database after fetch
    time.sleep(1)  # Give it a moment to commit
    db = next(get_db())  # Fresh session
    print('\n3. AFTER FETCH:')
    scan_count = db.query(SnkrdunkScanLog).count()
    price_count = db.query(SnkrdunkPriceHistory).count()
    print(f'   Scans: {scan_count}, Prices: {price_count}')
    
    if new_log_id:
        prices_for_scan = db.query(SnkrdunkPriceHistory).filter(SnkrdunkPriceHistory.scan_log_id == new_log_id).count()
        print(f'   Prices for new scan #{new_log_id}: {prices_for_scan}')
        
        # Show sample prices
        sample_prices = db.query(SnkrdunkPriceHistory).filter(SnkrdunkPriceHistory.scan_log_id == new_log_id).limit(3).all()
        print('   Sample prices:')
        for price in sample_prices:
            print(f'     Product {price.snkrdunk_key}: ¥{price.price_jpy}')
    
    # Step 4: Test price history API
    if new_log_id:
        print('\n4. TESTING PRICE HISTORY API:')
        try:
            response = requests.get(f'http://localhost:8000/api/v1/snkrdunk/price-history?log_id={new_log_id}&limit=5')
            if response.status_code == 200:
                data = response.json()
                print(f'   ✅ Price history API successful!')
                print(f'   Log ID: {data.get("log_id")}')
                print(f'   Item count: {data.get("item_count")}')
                
                items = data.get('items', [])
                if items:
                    print('   Sample items from API:')
                    for i, item in enumerate(items[:3]):
                        print(f'     {i+1}. ID: {item.get("id")}, Price: ¥{item.get("minPriceJpy")}')
            else:
                print(f'   ❌ Price history API failed: {response.status_code}')
        except Exception as e:
            print(f'   ❌ Error testing price history API: {str(e)}')

if __name__ == "__main__":
    test_complete_flow()