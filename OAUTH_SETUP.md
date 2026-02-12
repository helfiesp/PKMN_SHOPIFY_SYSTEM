# Shopify OAuth Setup Guide

I've implemented OAuth flow for your app so it can automatically exchange your Client ID and Secret for an access token!

## How It Works

1. **User visits install URL** → App redirects to Shopify for authorization
2. **User approves scopes** → Shopify redirects back with authorization code
3. **App exchanges code for token** → Token is automatically saved to database
4. **Ready to use!** → Sales analytics and all features work

## Setup Steps

### Step 1: Configure Client Credentials

1. **Copy your Client ID and Secret** from the screenshot you showed me

2. **Update your `.env` file:**
   ```bash
   SHOPIFY_CLIENT_ID=101eeef854342433b9710534461839261
   SHOPIFY_CLIENT_SECRET=your_secret_from_screenshot
   ```

3. **Restart your server:**
   ```bash
   # SSH into your server
   ssh root@192.168.0.100

   # Restart the service
   systemctl restart shopify-app
   # OR if running manually:
   # pkill -f uvicorn
   # python run.py
   ```

### Step 2: Configure Redirect URI in Shopify Partner Dashboard

1. **Go to your Shopify Partner Dashboard**
   - Apps → Your App → Configuration

2. **Add Allowed Redirection URLs:**
   ```
   http://192.168.0.100:8000/api/v1/oauth/callback
   ```

   **If you have a domain:**
   ```
   https://yourdomain.com/api/v1/oauth/callback
   ```

3. **Save changes**

### Step 3: Install the App

1. **Visit the install URL:**
   ```
   http://192.168.0.100:8000/api/v1/oauth/install?shop=yourstorename.myshopify.com
   ```

   Replace `yourstorename` with your actual shop name

2. **Approve the permissions** when Shopify asks

3. **You'll be redirected to a success page** showing:
   - Shop name
   - Scopes granted
   - Access token (preview)

4. **Done!** The access token is now saved in your database

### Step 4: Verify It Works

1. **Check OAuth status:**
   ```bash
   curl http://192.168.0.100:8000/api/v1/oauth/status
   ```

   Should return:
   ```json
   {
     "configured": true,
     "shop": "yourstore.myshopify.com",
     "has_token": true,
     "token_preview": "shpat_abc123...",
     "client_id_set": true,
     "client_secret_set": true
   }
   ```

2. **Test orders endpoint:**
   ```bash
   curl http://192.168.0.100:8000/api/v1/analytics/test-orders
   ```

   Should return your recent orders (not an error!)

3. **Test diagnostics:**
   ```bash
   curl http://192.168.0.100:8000/api/v1/analytics/diagnostics?days_back=30
   ```

## Quick Start (TL;DR)

```bash
# 1. Add credentials to .env
echo "SHOPIFY_CLIENT_ID=101eeef854342433b9710534461839261" >> .env
echo "SHOPIFY_CLIENT_SECRET=your_secret_here" >> .env

# 2. Restart server
systemctl restart shopify-app

# 3. Visit install URL in browser
# http://192.168.0.100:8000/api/v1/oauth/install?shop=yourstore.myshopify.com

# 4. Approve permissions

# 5. Done! Check status:
curl http://192.168.0.100:8000/api/v1/oauth/status
```

## Scopes Included

The OAuth flow requests these scopes automatically:
- ✅ `read_products` - Read product information
- ✅ `write_products` - Update product prices
- ✅ `read_orders` - **Fetch sales data**
- ✅ `read_inventory` - Track inventory levels
- ✅ `read_analytics` - Access analytics data

## Troubleshooting

### "Redirect URI mismatch"
- Make sure you added `http://192.168.0.100:8000/api/v1/oauth/callback` to your Partner Dashboard allowed redirects

### "Client credentials not configured"
- Check your `.env` file has `SHOPIFY_CLIENT_ID` and `SHOPIFY_CLIENT_SECRET` set
- Restart the server after changing `.env`

### "Invalid client_id"
- Verify you copied the correct Client ID from Shopify
- Make sure there are no extra spaces in the `.env` file

### Token not saved
- Check database write permissions
- Check server logs for errors: `journalctl -u shopify-app -f`

## What Happens Behind the Scenes

1. When you visit `/api/v1/oauth/install?shop=yourstore.myshopify.com`:
   - App redirects you to: `https://yourstore.myshopify.com/admin/oauth/authorize?client_id=...&scope=...`

2. You click "Install" on Shopify:
   - Shopify redirects to: `http://192.168.0.100:8000/api/v1/oauth/callback?code=xyz&shop=...`

3. App receives the callback:
   - Extracts the `code` parameter
   - Makes POST to Shopify: `https://yourstore.myshopify.com/admin/oauth/access_token`
   - Receives access token in response
   - Saves token to database in `settings` table

4. Token is ready to use:
   - All API calls now use this token
   - Token doesn't expire (unless you uninstall/reinstall the app)

## Alternative: Using Custom App Access Token

If you prefer NOT to use OAuth and just want to copy/paste a token:

1. **In Shopify Admin**, check if you can see "Admin API access token" field
2. **Copy the token** (should start with `shpat_`)
3. **Update via Settings UI:**
   - Go to http://192.168.0.100:8000
   - Click Settings tab
   - Paste token in "Shopify Access Token" field
   - Save

This is simpler but only works if you have a Custom App (not a Partner App).
