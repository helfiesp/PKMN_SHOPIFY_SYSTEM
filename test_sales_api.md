# Testing Sales Analytics API

## Quick Test Commands

### 1. Test Orders Connection
```bash
curl http://192.168.0.100:8000/api/v1/analytics/test-orders
```
**Expected:** Should return your recent orders (not an access denied error)

### 2. Test Sales Diagnostics
```bash
curl http://192.168.0.100:8000/api/v1/analytics/diagnostics?days_back=30
```
**Expected:** Should show orders fetched, variants with sales, etc.

### 3. Test Sales Comparison
```bash
curl http://192.168.0.100:8000/api/v1/analytics/sales-comparison?days_back=30
```
**Expected:** Should return sales data for your mapped products

### 4. Test Top Sellers
```bash
curl http://192.168.0.100:8000/api/v1/analytics/top-sellers?days_back=30&limit=10
```
**Expected:** Should return your top selling products

## In the Web UI

After updating scopes:

1. Go to the **Sales Analytics** tab
2. Click **🔍 Debug** button to see diagnostics
3. Click **Refresh** to load your sales data
4. You should see:
   - Your total sales
   - Competitor sales estimates
   - Market share
   - Product-by-product comparison

## Troubleshooting

If you still see errors after updating scopes:
- Make sure you uninstalled and reinstalled the app
- Check that the new permissions were accepted during install
- Verify your .env file has the correct SHOPIFY_SHOP and SHOPIFY_TOKEN
- Try the test endpoints above to see specific error messages
