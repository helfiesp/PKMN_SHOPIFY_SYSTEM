from app.database import get_db
from app.models import SnkrdunkPriceHistory, SnkrdunkCache, SnkrdunkScanLog

db = next(get_db())

# Check what's in the price history
prices = db.query(SnkrdunkPriceHistory).filter(SnkrdunkPriceHistory.scan_log_id == 3).limit(10).all()
print('=== Price History for Scan Log 3 ===')
for p in prices:
    print(f'snkrdunk_key={p.snkrdunk_key}, price_jpy={p.price_jpy}')

print('\n=== All Scan Logs ===')
scans = db.query(SnkrdunkScanLog).all()
for s in scans:
    count = db.query(SnkrdunkPriceHistory).filter(SnkrdunkPriceHistory.scan_log_id == s.id).count()
    print(f'Scan {s.id}: {s.created_at} - {count} prices')

# Check SnkrdunkCache to see what current prices are
print('\n=== Current Cache Prices ===')
caches = db.query(SnkrdunkCache).all()
for cache in caches:
    apparels = cache.response_data.get('apparels', [])
    print(f'Cache page {cache.page}: {len(apparels)} items')
    for item in apparels[:3]:
        print(f"  id={item.get('id')}, minPrice={item.get('minPrice')}")

# Get specific products to compare
print('\n=== Specific Products ===')
test_ids = ['687430', '743533', '721913']
for test_id in test_ids:
    # Current price from cache
    current_price = None
    for cache in caches:
        for item in cache.response_data.get('apparels', []):
            if str(item.get('id')) == test_id:
                current_price = item.get('minPrice')
    
    # Historical prices
    hist_prices = {}
    for scan in scans:
        hist = db.query(SnkrdunkPriceHistory).filter(
            SnkrdunkPriceHistory.scan_log_id == scan.id,
            SnkrdunkPriceHistory.snkrdunk_key == test_id
        ).first()
        if hist:
            hist_prices[scan.id] = hist.price_jpy
    
    print(f'Product {test_id}:')
    print(f'  Current (cache): {current_price}')
    print(f'  Historical: {hist_prices}')
