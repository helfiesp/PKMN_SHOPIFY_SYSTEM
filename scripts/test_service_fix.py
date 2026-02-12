#!/usr/bin/env python3
"""Test the SNKRDUNK service fix."""

import asyncio
from app.database import get_db
from app.services.snkrdunk_service import SnkrdunkService

async def test_service():
    db = next(get_db())
    service = SnkrdunkService()
    
    print('=== TESTING SERVICE DIRECTLY ===')
    try:
        result = await service.fetch_and_cache_snkrdunk_data(
            db=db,
            pages=[1],
            force_refresh=True
        )
        
        print('✅ Service call successful!')
        print(f'Total items: {result.get("total_items")}')
        print(f'Pages fetched: {result.get("pages_fetched")}')
        print(f'Items in result: {len(result.get("items", []))}')
        
        items = result.get('items', [])
        if items:
            print('\nFirst 3 items:')
            for i, item in enumerate(items[:3]):
                item_id = item.get('id', 'N/A')
                item_name = item.get('name', 'N/A')[:30]  # Truncate name
                item_price = item.get('minPriceJpy', 'N/A')
                print(f'  {i+1}. ID: {item_id}, Name: {item_name}, Price: ¥{item_price}')
        
        return result
    except Exception as e:
        print(f'❌ Service error: {str(e)}')
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(test_service())