#!/usr/bin/env python3
"""Test the SNKRDUNK API endpoints."""

import requests
import time

def test_endpoints():
    print('=== TESTING SNKRDUNK API ENDPOINTS ===')
    
    # Test 1: Get scan logs
    print('\n1. TESTING /scan-logs endpoint:')
    try:
        response = requests.get('http://localhost:8000/api/v1/snkrdunk/scan-logs', timeout=10)
        if response.status_code == 200:
            logs = response.json()
            print(f'   ✅ Got {len(logs)} scan logs')
            
            # Show logs with prices
            logs_with_prices = [log for log in logs if log['total_items'] and log['total_items'] > 0]
            print(f'   Logs with data: {len(logs_with_prices)}')
            
            if logs_with_prices:
                print('   Recent logs:')
                for log in logs_with_prices[:3]:
                    print(f'     ID {log["id"]}: {log["created_at"]} - {log["total_items"]} items')
        else:
            print(f'   ❌ Failed: {response.status_code}')
            
    except Exception as e:
        print(f'   ❌ Error: {str(e)}')
    
    # Test 2: Get price history for scan 4
    print('\n2. TESTING /price-history endpoint for scan 4:')
    try:
        response = requests.get('http://localhost:8000/api/v1/snkrdunk/price-history?log_id=4&limit=5', timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f'   ✅ Got price history for scan {data["log_id"]}')
            print(f'   Items: {data["item_count"]}')
            print('   Sample prices:')
            for item in data['items'][:3]:
                print(f'     Product {item["id"]}: ¥{item["minPriceJpy"]}')
        else:
            print(f'   ❌ Failed: {response.status_code}')
            print(f'   Response: {response.text[:200]}')
            
    except Exception as e:
        print(f'   ❌ Error: {str(e)}')
    
    # Test 3: Get price history for scan 5
    print('\n3. TESTING /price-history endpoint for scan 5:')
    try:
        response = requests.get('http://localhost:8000/api/v1/snkrdunk/price-history?log_id=5&limit=5', timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f'   ✅ Got price history for scan {data["log_id"]}')
            print(f'   Items: {data["item_count"]}')
            print('   Sample prices:')
            for item in data['items'][:3]:
                print(f'     Product {item["id"]}: ¥{item["minPriceJpy"]}')
        else:
            print(f'   ❌ Failed: {response.status_code}')
            
    except Exception as e:
        print(f'   ❌ Error: {str(e)}')

if __name__ == "__main__":
    time.sleep(3)  # Wait for server
    test_endpoints()