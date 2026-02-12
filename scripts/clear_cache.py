from app.database import get_db, engine
from app.models import SnkrdunkCache
from sqlalchemy import text

db = next(get_db())
# Clear all SNKRDUNK caches
db.query(SnkrdunkCache).delete()
db.commit()

print('SNKRDUNK cache cleared')

# Check it's empty
count = db.query(SnkrdunkCache).count()
print(f'Remaining caches: {count}')
