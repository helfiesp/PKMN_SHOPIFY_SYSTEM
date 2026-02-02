import requests
r = requests.get('http://localhost:8000/api/v1/snkrdunk/products')
data = r.json()
print(f'Total items: {data["total_items"]}')
print('\nFirst 3 products:')
for item in data['items'][:3]:
    print(f"  ID: {item['id']}, Name: {item.get('nameEn', 'N/A')}, Price: {item['minPriceJpy']}, Updated: {item['last_price_updated']}")
