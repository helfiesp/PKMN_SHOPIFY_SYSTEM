from app.database import get_db
from app.models import SnkrdunkCache

db = next(get_db())
caches = db.query(SnkrdunkCache).all()
print(f'Total cached SNKRDUNK pages: {len(caches)}')

for cache in caches[:2]:
    apparels = cache.response_data.get('apparels', [])
    print(f'\nPage {cache.page}: {len(apparels)} apparels')
    if apparels:
        for idx, item in enumerate(apparels[:2]):
            print(f'  Item {idx}:')
            print(f'    Keys: {list(item.keys())[:15]}')
            print(f'    id: {item.get("id")}')
            print(f'    regularPrice: {item.get("regularPrice")}')
            print(f'    minPrice: {item.get("minPrice")}')
