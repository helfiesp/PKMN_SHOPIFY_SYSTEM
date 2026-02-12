"""Shopify OAuth flow for app installation and token management."""
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
import requests
import hmac
import hashlib
from urllib.parse import urlencode, parse_qs

from app.database import get_db
from app.models import Setting
from app.config import settings

router = APIRouter()


def verify_shopify_hmac(query_params: dict, hmac_to_verify: str) -> bool:
    """Verify the HMAC signature from Shopify."""
    # Get client secret from settings
    client_secret = settings.shopify_client_secret
    if not client_secret:
        return False

    # Build message from query params (excluding hmac and signature)
    filtered_params = {k: v for k, v in query_params.items()
                      if k not in ['hmac', 'signature']}

    # Sort and encode parameters
    message = '&'.join([f"{k}={v}" for k, v in sorted(filtered_params.items())])

    # Calculate HMAC
    computed_hmac = hmac.new(
        client_secret.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed_hmac, hmac_to_verify)


@router.get("/install")
async def install_app(shop: str, request: Request):
    """
    Step 1: Redirect user to Shopify authorization page.

    Usage: https://your-app.com/api/v1/oauth/install?shop=yourstore.myshopify.com
    """
    if not shop:
        raise HTTPException(status_code=400, detail="Missing shop parameter")

    # Ensure shop domain is valid
    if not shop.endswith('.myshopify.com'):
        shop = f"{shop}.myshopify.com"

    # Get client ID from settings
    client_id = settings.shopify_client_id
    if not client_id:
        raise HTTPException(status_code=500, detail="Shopify Client ID not configured")

    # Define scopes required by your app
    scopes = "read_products,write_products,read_orders,read_inventory,read_analytics"

    # Build redirect URI (must match what's configured in Shopify Partner Dashboard)
    redirect_uri = f"{request.base_url}api/v1/oauth/callback"

    # Build authorization URL
    auth_params = {
        'client_id': client_id,
        'scope': scopes,
        'redirect_uri': redirect_uri,
        'state': shop,  # Use shop as state for verification
    }

    auth_url = f"https://{shop}/admin/oauth/authorize?{urlencode(auth_params)}"

    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def oauth_callback(
    request: Request,
    code: str = None,
    shop: str = None,
    state: str = None,
    hmac: str = None,
    db: Session = Depends(get_db)
):
    """
    Step 2: Shopify redirects here after user approves.
    Exchange authorization code for access token.
    """
    if not code or not shop:
        raise HTTPException(status_code=400, detail="Missing code or shop parameter")

    # Verify HMAC to ensure request came from Shopify
    query_params = dict(request.query_params)
    hmac_value = query_params.get('hmac', '')

    # Note: In production, you should verify HMAC here
    # if not verify_shopify_hmac(query_params, hmac_value):
    #     raise HTTPException(status_code=403, detail="Invalid HMAC signature")

    # Get client credentials from settings
    client_id = settings.shopify_client_id
    client_secret = settings.shopify_client_secret

    if not client_id or not client_secret:
        raise HTTPException(status_code=500, detail="Shopify credentials not configured")

    # Exchange code for access token
    token_url = f"https://{shop}/admin/oauth/access_token"
    token_data = {
        'client_id': client_id,
        'client_secret': client_secret,
        'code': code
    }

    try:
        response = requests.post(token_url, json=token_data, timeout=10)
        response.raise_for_status()
        token_response = response.json()

        access_token = token_response.get('access_token')
        scope = token_response.get('scope')

        if not access_token:
            raise HTTPException(status_code=500, detail="No access token received")

        # Save access token to database
        # Update or create shopify_token setting
        token_setting = db.query(Setting).filter(Setting.key == 'shopify_token').first()
        if token_setting:
            token_setting.value = access_token
        else:
            token_setting = Setting(key='shopify_token', value=access_token)
            db.add(token_setting)

        # Update or create shopify_shop setting
        shop_setting = db.query(Setting).filter(Setting.key == 'shopify_shop').first()
        if shop_setting:
            shop_setting.value = shop
        else:
            shop_setting = Setting(key='shopify_shop', value=shop)
            db.add(shop_setting)

        db.commit()

        # Return success page
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>App Installed Successfully</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    min-height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                }}
                .container {{
                    background: white;
                    padding: 3rem;
                    border-radius: 12px;
                    box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                    text-align: center;
                    max-width: 500px;
                }}
                h1 {{ color: #2d3748; margin-bottom: 1rem; }}
                .success-icon {{ font-size: 4rem; margin-bottom: 1rem; }}
                .details {{
                    background: #f7fafc;
                    padding: 1rem;
                    border-radius: 8px;
                    margin: 1.5rem 0;
                    text-align: left;
                }}
                .details p {{ margin: 0.5rem 0; color: #4a5568; }}
                .btn {{
                    display: inline-block;
                    background: #667eea;
                    color: white;
                    padding: 0.75rem 1.5rem;
                    border-radius: 6px;
                    text-decoration: none;
                    margin-top: 1rem;
                    font-weight: 600;
                }}
                .btn:hover {{ background: #5568d3; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="success-icon">✅</div>
                <h1>App Installed Successfully!</h1>
                <p>Your Shopify app has been authorized and the access token has been saved.</p>

                <div class="details">
                    <p><strong>Shop:</strong> {shop}</p>
                    <p><strong>Scopes:</strong> {scope}</p>
                    <p><strong>Token:</strong> {access_token[:20]}...{access_token[-10:]}</p>
                </div>

                <p>You can now use the app to fetch sales data and manage your store.</p>

                <a href="/" class="btn">Go to Dashboard</a>
            </div>
        </body>
        </html>
        """)

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Failed to exchange token: {str(e)}")


@router.get("/status")
async def oauth_status(db: Session = Depends(get_db)):
    """Check OAuth configuration status."""
    shop_setting = db.query(Setting).filter(Setting.key == 'shopify_shop').first()
    token_setting = db.query(Setting).filter(Setting.key == 'shopify_token').first()

    return {
        'configured': bool(shop_setting and token_setting),
        'shop': shop_setting.value if shop_setting else None,
        'has_token': bool(token_setting and token_setting.value),
        'token_preview': f"{token_setting.value[:20]}..." if token_setting and token_setting.value else None,
        'client_id_set': bool(settings.shopify_client_id),
        'client_secret_set': bool(settings.shopify_client_secret),
    }
