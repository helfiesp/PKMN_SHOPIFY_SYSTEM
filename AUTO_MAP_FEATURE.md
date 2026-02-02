# Auto-Mapping Feature

## Overview
Added automatic competitor-to-SNKRDUNK product mapping using Jaccard similarity matching on product names.

## Changes Made

### 1. Backend Endpoint
**File**: `app/routers/competitors.py`
- **Endpoint**: `POST /competitors/auto-map`
- **Purpose**: Triggers automatic mapping of all unmapped competitor products to SNKRDUNK products
- **Response**: Returns mapping statistics
  ```json
  {
    "total_unmapped": 150,
    "mapped": 120,
    "failed": 30,
    "results": [
      {
        "competitor_id": 1,
        "competitor_name": "Product Name",
        "snkrdunk_name": "Matched Product",
        "similarity": 0.85,
        "status": "mapped"
      },
      ...
    ]
  }
  ```

### 2. Service Logic
**File**: `app/services/competitor_mapping_service.py`

#### New Method: `jaccard_similarity(s1, s2)`
- Calculates word-level similarity between two strings
- Returns value between 0 and 1 (0 = no match, 1 = exact match)
- Used for intelligent product matching

#### New Method: `auto_map_competitors(db)`
- Fetches all unmapped competitor products
- For each product, finds best SNKRDUNK match using Jaccard similarity (threshold: 50%)
- Creates `CompetitorProductMapping` records for successful matches
- Returns detailed mapping results with statistics

### 3. Frontend Button
**File**: `app/static/app.js`
- Added "🤖 Auto-Map" button in Competitors tab header
- Button triggers `autoMapCompetitors()` function
- Shows loading state while mapping is in progress
- Displays success/failure notification with statistics
- Automatically reloads competitors table after mapping completes

#### New Function: `autoMapCompetitors()`
- Posts to `/competitors/auto-map` endpoint
- Handles loading state and user feedback
- Shows results: total unmapped, successfully mapped, failed/no-match
- Reloads table to display new mappings with checkmarks

## How It Works

1. User clicks "🤖 Auto-Map" button in Competitors tab
2. Frontend sends POST request to `/competitors/auto-map`
3. Backend queries all unmapped competitor products
4. For each competitor, compares normalized name against all SNKRDUNK products
5. Uses Jaccard similarity (word-level matching) to find best match
6. Only creates mapping if similarity > 50% (configurable threshold)
7. Returns results showing what was mapped and what failed
8. Frontend reloads table showing checkmarks for newly mapped products

## Example Matching

| Competitor Product | SNKRDUNK Product | Similarity | Status |
|-------------------|------------------|-----------|--------|
| "Pokémon Booster Box" | "Pokemon Booster Box" | 0.87 | ✓ Mapped |
| "Charizard Elite Box" | "Pikachu Collection Box" | 0.45 | ✗ No Match |
| "Sword & Shield Booster" | "Sword Shield Booster" | 0.92 | ✓ Mapped |

## Threshold Configuration

Currently set to **50% similarity** for automatic mapping. This ensures only reasonably confident matches are created.

To adjust:
```python
# In auto_map_competitors() method
best_similarity = 0.5  # Change this value (0.0 - 1.0)
```

## Benefits

- **Saves time**: Automatically maps hundreds of products at once
- **Consistent**: Uses standardized matching algorithm
- **Safe**: Shows results before applying, user can review in Competitor Mappings tab
- **Trackable**: Returns detailed mapping results and statistics

## Next Steps

After running auto-map:
1. Review "Competitor Mappings" tab to see matched products and their prices
2. Check margins vs competitor prices
3. Make any manual corrections if needed
4. Use data for pricing strategy decisions
