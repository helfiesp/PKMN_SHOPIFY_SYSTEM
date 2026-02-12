#!/usr/bin/env python3
"""
Test script to compare live SNKRDUNK API data with database records.
This will help identify why prices aren't updating correctly.
"""

import requests
import asyncio
from datetime import datetime, timezone
from app.database import get_db
from app.models import SnkrdunkCache, SnkrdunkPriceHistory, SnkrdunkScanLog
from app.services.snkrdunk_service import SnkrdunkService

def fetch_live_api_data(page=1):
    """Fetch data directly from SNKRDUNK API without any caching."""
    print(f"=== FETCHING LIVE DATA FROM SNKRDUNK API (Page {page}) ===")
    
    url = "https://snkrdunk.com/v1/apparel/market/category"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://snkrdunk.com/",
    }
    params = {
        "page": page,
        "perPage": 25,
        "order": "popular",
        "apparelCategoryId": 14,
        "apparelSubCategoryId": 0,
        "brandId": "pokemon",
        "departmentName": "hobby"
    }
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        apparels = data.get("apparels", [])
        items = [x for x in apparels if isinstance(x, dict) and "id" in x]
        
        print(f"✅ Live API returned {len(items)} items")
        return items
    except Exception as e:
        print(f"❌ Error fetching live data: {str(e)}")
        return []

def get_cached_data():
    """Get cached data from database."""
    print("\n=== CHECKING CACHED DATA IN DATABASE ===")
    db = next(get_db())
    
    cache_entries = db.query(SnkrdunkCache).all()
    print(f"Found {len(cache_entries)} cache entries")
    
    all_cached_items = []
    for cache in cache_entries:
        apparels = cache.response_data.get("apparels", [])
        items = [x for x in apparels if isinstance(x, dict) and "id" in x]
        all_cached_items.extend(items)
        print(f"  Page {cache.page}: {len(items)} items, expires at {cache.expires_at}")
    
    return all_cached_items

def get_price_history():
    """Get most recent price history from database."""
    print("\n=== CHECKING PRICE HISTORY IN DATABASE ===")
    db = next(get_db())
    
    latest_scan = db.query(SnkrdunkScanLog).order_by(SnkrdunkScanLog.created_at.desc()).first()
    
    if not latest_scan:
        print("No scan logs found")
        return {}
    
    print(f"Latest scan: ID {latest_scan.id}, created at {latest_scan.created_at}")
    
    prices = db.query(SnkrdunkPriceHistory).filter(
        SnkrdunkPriceHistory.scan_log_id == latest_scan.id
    ).all()
    
    print(f"Found {len(prices)} price records for latest scan")
    
    price_dict = {}
    for price in prices:
        price_dict[price.snkrdunk_key] = price.price_jpy
    
    return price_dict

def compare_data(live_items, cached_items, price_history):
    """Compare live API data with cached data and price history."""
    print("\n" + "="*80)
    print("COMPARISON RESULTS")
    print("="*80)
    
    # Create lookup dictionaries
    live_dict = {str(item['id']): item for item in live_items}
    cached_dict = {str(item['id']): item for item in cached_items}
    
    print(f"\nLive API items: {len(live_dict)}")
    print(f"Cached items: {len(cached_dict)}")
    print(f"Price history items: {len(price_history)}")
    
    # Check specific products mentioned by user
    test_products = list(live_dict.keys())[:10]  # Test first 10 products
    
    print("\n" + "-"*80)
    print("DETAILED PRICE COMPARISON")
    print("-"*80)
    print(f"{'Product ID':<15} {'Live API':<15} {'Cached':<15} {'DB History':<15} {'Status':<20}")
    print("-"*80)
    
    discrepancies = []
    
    for product_id in test_products:
        live_item = live_dict.get(product_id)
        cached_item = cached_dict.get(product_id)
        history_price = price_history.get(product_id)
        
        live_price = live_item.get('minPrice') if live_item else None
        cached_price = cached_item.get('minPrice') if cached_item else None
        
        # Determine status
        if live_price and cached_price and history_price:
            if live_price == cached_price == history_price:
                status = "✅ All match"
            elif live_price != cached_price:
                status = "⚠️ Cache mismatch"
                discrepancies.append({
                    'id': product_id,
                    'issue': 'cache_mismatch',
                    'live': live_price,
                    'cached': cached_price,
                    'history': history_price
                })
            elif cached_price != history_price:
                status = "⚠️ History mismatch"
                discrepancies.append({
                    'id': product_id,
                    'issue': 'history_mismatch',
                    'live': live_price,
                    'cached': cached_price,
                    'history': history_price
                })
            elif live_price != history_price:
                status = "⚠️ API≠History"
                discrepancies.append({
                    'id': product_id,
                    'issue': 'api_history_mismatch',
                    'live': live_price,
                    'cached': cached_price,
                    'history': history_price
                })
            else:
                status = "✅ OK"
        elif not history_price:
            status = "❌ No history"
        elif not cached_price:
            status = "❌ Not cached"
        elif not live_price:
            status = "❌ Not in API"
        else:
            status = "❓ Unknown"
        
        live_str = f"¥{live_price}" if live_price else "N/A"
        cached_str = f"¥{cached_price}" if cached_price else "N/A"
        history_str = f"¥{history_price}" if history_price else "N/A"
        
        print(f"{product_id:<15} {live_str:<15} {cached_str:<15} {history_str:<15} {status:<20}")
        
        # Get product name for context
        if live_item:
            name = live_item.get('name', 'Unknown')[:40]
            print(f"  └─ {name}")
    
    # Summary of issues
    print("\n" + "="*80)
    print("ISSUE SUMMARY")
    print("="*80)
    
    if not discrepancies:
        print("✅ No discrepancies found! All prices match.")
    else:
        print(f"⚠️ Found {len(discrepancies)} discrepancies:")
        
        cache_mismatches = [d for d in discrepancies if d['issue'] == 'cache_mismatch']
        history_mismatches = [d for d in discrepancies if d['issue'] == 'history_mismatch']
        api_history_mismatches = [d for d in discrepancies if d['issue'] == 'api_history_mismatch']
        
        if cache_mismatches:
            print(f"\n  1. Cache Mismatches ({len(cache_mismatches)} products):")
            print("     - Cache is not reflecting live API prices")
            print("     - This suggests cache is not being refreshed properly")
            for d in cache_mismatches[:3]:
                print(f"       Product {d['id']}: Live=¥{d['live']} vs Cached=¥{d['cached']}")
        
        if history_mismatches:
            print(f"\n  2. History Mismatches ({len(history_mismatches)} products):")
            print("     - Price history not matching cache")
            print("     - This suggests historical save is using wrong data source")
            for d in history_mismatches[:3]:
                print(f"       Product {d['id']}: Cached=¥{d['cached']} vs History=¥{d['history']}")
        
        if api_history_mismatches:
            print(f"\n  3. API-History Mismatches ({len(api_history_mismatches)} products):")
            print("     - Database history doesn't match current live API")
            print("     - This is expected if API prices changed since last scan")
            for d in api_history_mismatches[:3]:
                print(f"       Product {d['id']}: Live=¥{d['live']} vs History=¥{d['history']}")
    
    return discrepancies

async def test_service_layer():
    """Test the service layer to see what it returns."""
    print("\n" + "="*80)
    print("TESTING SERVICE LAYER")
    print("="*80)
    
    db = next(get_db())
    service = SnkrdunkService()
    
    print("\n1. Testing with force_refresh=FALSE (should use cache):")
    result_cached = await service.fetch_and_cache_snkrdunk_data(
        db=db,
        pages=[1],
        force_refresh=False
    )
    print(f"   Returned {len(result_cached.get('items', []))} items")
    if result_cached.get('items'):
        first_item = result_cached['items'][0]
        print(f"   First item: ID={first_item.get('id')}, Price=¥{first_item.get('minPrice')}")
    
    print("\n2. Testing with force_refresh=TRUE (should fetch fresh):")
    result_fresh = await service.fetch_and_cache_snkrdunk_data(
        db=db,
        pages=[1],
        force_refresh=True
    )
    print(f"   Returned {len(result_fresh.get('items', []))} items")
    if result_fresh.get('items'):
        first_item = result_fresh['items'][0]
        print(f"   First item: ID={first_item.get('id')}, Price=¥{first_item.get('minPrice')}")
    
    # Compare the two
    if result_cached.get('items') and result_fresh.get('items'):
        cached_first = result_cached['items'][0]
        fresh_first = result_fresh['items'][0]
        
        if cached_first.get('minPrice') != fresh_first.get('minPrice'):
            print(f"\n   ⚠️ PRICE DIFFERENCE DETECTED!")
            print(f"   Cached: ¥{cached_first.get('minPrice')}")
            print(f"   Fresh:  ¥{fresh_first.get('minPrice')}")
        else:
            print(f"\n   ✅ Cached and fresh prices match")

def main():
    """Run all tests."""
    print("\n" + "="*80)
    print("SNKRDUNK PRICE DEBUGGING TEST")
    print("="*80)
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    # Step 1: Fetch live data
    live_items = fetch_live_api_data(page=1)
    
    # Step 2: Get cached data
    cached_items = get_cached_data()
    
    # Step 3: Get price history
    price_history = get_price_history()
    
    # Step 4: Compare everything
    discrepancies = compare_data(live_items, cached_items, price_history)
    
    # Step 5: Test service layer
    print("\n\nTesting service layer...")
    asyncio.run(test_service_layer())
    
    # Final recommendations
    print("\n" + "="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    
    if discrepancies:
        print("\nBased on the issues found:")
        print("1. Clear the cache completely and re-fetch")
        print("2. Verify the router is using force_refresh=True when you click 'Refresh SNKRDUNK Data'")
        print("3. Check that the price history is saving from the FRESH API response, not cache")
        print("4. Ensure the frontend is displaying prices from the correct source")
    else:
        print("\n✅ No issues detected in the data pipeline")
        print("The problem might be in the frontend display logic")
    
    print("\n" + "="*80)

if __name__ == "__main__":
    main()
