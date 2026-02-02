from app.database import get_db
from app.models import SnkrdunkCache

db = next(get_db())
caches = db.query(SnkrdunkCache).all()

print(f'Total caches: {len(caches)}\n')

for cache in caches[:3]:
    print(f'Page {cache.page}:')
    print(f'  Created: {cache.created_at}')
    print(f'  Expires: {cache.expires_at}')
