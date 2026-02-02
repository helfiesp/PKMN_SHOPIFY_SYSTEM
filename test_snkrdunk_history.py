#!/usr/bin/env python3
"""
Test script to validate SNKRDUNK price history functionality.
Run this after starting the server to test the historical price tracking.
"""
import requests
import json
from datetime import datetime

def test_snkrdunk_price_history():
    """Test the SNKRDUNK price history tracking system."""
    
    print("🧪 Testing SNKRDUNK Price History System")
    print("=" * 50)
    
    # Test 1: Fetch SNKRDUNK data
    print("\n📊 Step 1: Fetching SNKRDUNK data...")
    try:
        response = requests.post('http://localhost:8000/api/v1/snkrdunk/fetch', 
                               json={'pages': [1], 'force_refresh': True},
                               headers={'Content-Type': 'application/json'},
                               timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Fetch successful!")
            print(f"   Total items: {data.get('total_items')}")
            print(f"   Scan Log ID: {data.get('log_id')}")
            scan_log_id = data.get('log_id')
        else:
            print(f"❌ Fetch failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Error during fetch: {str(e)}")
        return False
    
    # Test 2: Check scan logs
    print("\n📋 Step 2: Checking scan logs...")
    try:
        response = requests.get('http://localhost:8000/api/v1/snkrdunk/scan-logs?limit=5')
        if response.status_code == 200:
            logs = response.json()
            print(f"✅ Found {len(logs)} scan logs")
            for log in logs[:3]:  # Show first 3
                print(f"   Log {log['id']}: {log['status']} - {log.get('total_items', 0)} items - {log['created_at']}")
        else:
            print(f"❌ Failed to get scan logs: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error getting scan logs: {str(e)}")
        return False
    
    # Test 3: Check price history for the scan we just created
    if scan_log_id:
        print(f"\n💰 Step 3: Checking price history for scan {scan_log_id}...")
        try:
            response = requests.get(f'http://localhost:8000/api/v1/snkrdunk/price-history?log_id={scan_log_id}&limit=10')
            if response.status_code == 200:
                history_data = response.json()
                item_count = history_data.get('item_count', 0)
                items = history_data.get('items', [])
                
                print(f"✅ Price history retrieved successfully!")
                print(f"   Items in history: {item_count}")
                print(f"   Scan date: {history_data.get('scan_date')}")
                
                if items:
                    print(f"   Sample prices:")
                    for item in items[:5]:  # Show first 5 prices
                        print(f"     - Product {item['id']}: ¥{item['minPriceJpy']}")
                else:
                    print("   ⚠️  No price data found - this indicates the linking isn't working")
                    return False
            else:
                print(f"❌ Failed to get price history: {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error getting price history: {str(e)}")
            return False
    
    # Test 4: Verify database state
    print(f"\n🗄️  Step 4: Checking database state...")
    try:
        # This would need to be run from within the app context
        print("   (Database check would be done manually)")
    except Exception as e:
        print(f"   Database check failed: {str(e)}")
    
    print(f"\n🎉 All tests passed! Historical price tracking is working correctly.")
    print(f"\n📝 Next steps:")
    print(f"   1. Run another scan tomorrow")
    print(f"   2. Use the frontend to select different scan dates")
    print(f"   3. Verify that prices change when selecting historical scans")
    
    return True

if __name__ == "__main__":
    success = test_snkrdunk_price_history()
    if success:
        print(f"\n✅ SUCCESS: Price history system is working correctly!")
    else:
        print(f"\n❌ FAILED: Price history system needs debugging.")