#!/usr/bin/env python3
"""Investigate SNKRDUNK API response structure."""

import asyncio
import json
from app.database import get_db
from app.services.snkrdunk_service import SnkrdunkService

async def investigate_response():
    db = next(get_db())
    service = SnkrdunkService()
    
    print('=== INVESTIGATING SNKRDUNK API RESPONSE ===')
    try:
        result = await service.fetch_and_cache_snkrdunk_data(
            db=db,
            pages=[1],
            force_refresh=True
        )
        
        items = result.get('items', [])
        if items:
            print(f'Got {len(items)} items')
            print('\nFirst item structure:')
            first_item = items[0]
            print(json.dumps(first_item, indent=2))
            
            print('\nChecking for price fields:')
            for key, value in first_item.items():
                if 'price' in key.lower() or 'min' in key.lower():
                    print(f'  {key}: {value}')
        
        return result
    except Exception as e:
        print(f'❌ Error: {str(e)}')
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    result = asyncio.run(investigate_response())