"""Quick start guide for testing the API."""

# Quick Start Examples

## 1. Start the server
```bash
python run.py
```

## 2. Check health
```bash
curl http://localhost:8000/api/v1/health
```

## 3. Fetch Shopify collection
```bash
curl -X POST "http://localhost:8000/api/v1/shopify/fetch-collection" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_id": "444175384827",
    "exclude_title_contains": "one piece"
  }'
```

## 4. List products
```bash
curl "http://localhost:8000/api/v1/shopify/products?limit=10"
```

## 5. Fetch SNKRDUNK data
```bash
curl -X POST "http://localhost:8000/api/v1/snkrdunk/fetch" \
  -H "Content-Type: application/json" \
  -d '{
    "pages": [1, 2, 3],
    "force_refresh": false
  }'
```

## 6. Generate price plan
```bash
curl -X POST "http://localhost:8000/api/v1/price-plans/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_id": "444175384827",
    "plan_type": "price_update"
  }'
```

## 7. List price plans
```bash
curl "http://localhost:8000/api/v1/price-plans"
```

## 8. Get specific price plan
```bash
curl "http://localhost:8000/api/v1/price-plans/1"
```

## 9. Apply price plan (BE CAREFUL!)
```bash
curl -X POST "http://localhost:8000/api/v1/price-plans/1/apply"
```

## 10. Generate stock report
```bash
curl -X POST "http://localhost:8000/api/v1/reports/stock" \
  -H "Content-Type: application/json" \
  -d '{
    "collection_id": "444175384827"
  }'
```

## 11. View audit logs
```bash
curl "http://localhost:8000/api/v1/reports/audit-logs?limit=20"
```

## 12. Get statistics
```bash
curl "http://localhost:8000/api/v1/reports/statistics"
```

## Using Python requests

```python
import requests

BASE_URL = "http://localhost:8000/api/v1"

# Fetch collection
response = requests.post(
    f"{BASE_URL}/shopify/fetch-collection",
    json={
        "collection_id": "444175384827",
        "exclude_title_contains": "one piece"
    }
)
print(response.json())

# Generate price plan
response = requests.post(
    f"{BASE_URL}/price-plans/generate",
    json={
        "collection_id": "444175384827"
    }
)
plan = response.json()
print(f"Created plan ID: {plan['id']}")

# List plans
response = requests.get(f"{BASE_URL}/price-plans")
plans = response.json()
for p in plans:
    print(f"Plan {p['id']}: {p['status']} - {p['total_items']} items")
```

## Interactive API Documentation

Visit http://localhost:8000/docs for interactive Swagger UI where you can:
- Browse all endpoints
- See request/response schemas
- Try out endpoints directly in browser
- Download OpenAPI spec
