"""Analytics and sales tracking router."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from collections import defaultdict

from app.database import get_db
from app.models import (
    Product,
    Variant,
    ProductPriceHistory,
    CompetitorProductMapping,
    CompetitorProduct,
    CompetitorSalesVelocity,
    CompetitorProductDaily
)
from app.config import settings
import requests

router = APIRouter()


def fetch_shopify_orders(days_back: int = 30):
    """Fetch orders from Shopify GraphQL API."""
    shop = settings.get_shopify_shop()
    token = settings.get_shopify_token()

    if not shop or not token:
        print(f"[WARNING] Shopify credentials missing - shop: {shop}, token: {'set' if token else 'not set'}")
        return []

    cutoff_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
    print(f"[INFO] Fetching orders from {cutoff_date} onwards...")

    query = """
    query($first: Int!, $query: String, $after: String) {
        orders(first: $first, query: $query, after: $after) {
            pageInfo {
                hasNextPage
                endCursor
            }
            edges {
                node {
                    id
                    name
                    createdAt
                    lineItems(first: 100) {
                        edges {
                            node {
                                id
                                title
                                quantity
                                variant {
                                    id
                                    title
                                    product {
                                        id
                                        title
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    """

    url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json"
    }

    all_orders = []
    has_next = True
    cursor = None

    try:
        while has_next:
            variables = {
                "first": 250,
                "query": f"created_at:>={cutoff_date}",
                "after": cursor
            }

            response = requests.post(
                url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=60
            )

            if not response.ok:
                print(f"[ERROR] Shopify API request failed: {response.status_code} - {response.text}")
                break

            data = response.json()

            # Debug: Show raw response on first iteration
            if cursor is None:
                print(f"[DEBUG] First page response keys: {list(data.keys())}")
                if "data" in data:
                    print(f"[DEBUG] Data keys: {list(data.get('data', {}).keys())}")

            if "errors" in data:
                print(f"[ERROR] Shopify GraphQL errors: {data['errors']}")
                break

            orders_data = data.get("data", {}).get("orders", {})
            edges = orders_data.get("edges", [])

            print(f"[DEBUG] Page returned {len(edges)} orders")

            for edge in edges:
                all_orders.append(edge["node"])

            page_info = orders_data.get("pageInfo", {})
            has_next = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")

    except Exception as e:
        print(f"[ERROR] Exception while fetching orders: {e}")

    print(f"[INFO] Fetched {len(all_orders)} total orders")
    if all_orders:
        print(f"[INFO] Sample order: {all_orders[0].get('name', 'N/A')} with {len(all_orders[0].get('lineItems', {}).get('edges', []))} items")

    return all_orders


@router.get("/sales-comparison")
async def get_sales_comparison(
    days_back: int = Query(30, description="Number of days to look back"),
    product_id: Optional[int] = Query(None, description="Filter by specific product ID"),
    db: Session = Depends(get_db)
):
    """
    Compare sales between your Shopify products and competitor products.
    Calculates sales from inventory changes over time.
    """
    try:
        # Get all products with competitor mappings
        # Only get Booster Box variants, exclude packs
        query = (
            db.query(Product, Variant, CompetitorProductMapping)
            .join(Variant, Product.id == Variant.product_id)
            .join(CompetitorProductMapping, CompetitorProductMapping.shopify_product_id == Product.id)
            .filter(
                and_(
                    Product.status == 'ACTIVE',
                    # Exclude Booster Pack variants
                    ~Variant.title.ilike('%booster pack%')
                )
            )
        )

        if product_id:
            query = query.filter(Product.id == product_id)

        # Group by product to avoid duplicates (only take first variant per product)
        seen_products = set()
        mapped_products = []
        for product, variant, mapping in query.all():
            if product.id not in seen_products:
                seen_products.add(product.id)
                mapped_products.append((product, variant, mapping))

        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Fetch actual Shopify orders
        orders = fetch_shopify_orders(days_back)
        print(f"[INFO] Processing {len(orders)} orders for sales calculation")

        # Calculate sales from orders per variant
        sales_by_variant = defaultdict(lambda: {'total': 0, 'daily': defaultdict(int)})

        for order in orders:
            order_date = datetime.fromisoformat(order['createdAt'].replace('Z', '+00:00')).date()

            for item_edge in order.get('lineItems', {}).get('edges', []):
                item = item_edge['node']
                variant_gid = item.get('variant', {}).get('id') if item.get('variant') else None

                if variant_gid:
                    quantity = item.get('quantity', 0)
                    sales_by_variant[variant_gid]['total'] += quantity
                    sales_by_variant[variant_gid]['daily'][order_date.isoformat()] += quantity

        # Debug: Show sample variant IDs from orders vs database
        if sales_by_variant:
            sample_order_variant = list(sales_by_variant.keys())[0]
            print(f"[DEBUG] Sample variant ID from orders: {sample_order_variant}")

        if mapped_products:
            sample_db_variant = mapped_products[0][1].shopify_id
            print(f"[DEBUG] Sample variant ID from database: {sample_db_variant}")
            print(f"[DEBUG] Variant IDs match format: {sample_order_variant == sample_db_variant if sales_by_variant and mapped_products else 'N/A'}")

        print(f"[INFO] Found {len(mapped_products)} mapped products (after deduplication)")
        print(f"[INFO] Sales tracked for {len(sales_by_variant)} unique variants")

        sales_data = []

        for product, variant, mapping in mapped_products:
            # Get sales from Shopify orders
            variant_sales = sales_by_variant.get(variant.shopify_id, {'total': 0, 'daily': {}})
            my_sales = variant_sales['total']

            my_daily_sales = [
                {
                    'date': date,
                    'units_sold': units,
                    'remaining_stock': variant.inventory_quantity or 0
                }
                for date, units in sorted(variant_sales['daily'].items())
            ]

            # Get competitor sales data
            competitor_sales_total = 0
            competitor_velocity_data = []

            if mapping.competitor_product_id:
                competitor = db.query(CompetitorProduct).filter(
                    CompetitorProduct.id == mapping.competitor_product_id
                ).first()

                if competitor:
                    # Get sales velocity
                    velocity = db.query(CompetitorSalesVelocity).filter(
                        CompetitorSalesVelocity.competitor_product_id == competitor.id
                    ).first()

                    if velocity:
                        competitor_sales_total = velocity.total_sales_estimate or 0
                        competitor_velocity_data.append({
                            'website': competitor.website,
                            'avg_daily_sales': velocity.avg_daily_sales or 0,
                            'weekly_sales_estimate': velocity.weekly_sales_estimate or 0,
                            'total_sales_estimate': velocity.total_sales_estimate or 0,
                            'current_stock': competitor.stock_amount or 0,
                            'days_until_sellout': velocity.days_until_sellout
                        })

            # Get ALL mapped competitors for this product
            all_competitor_mappings = (
                db.query(CompetitorProductMapping, CompetitorProduct)
                .join(CompetitorProduct, CompetitorProductMapping.competitor_product_id == CompetitorProduct.id)
                .filter(CompetitorProductMapping.shopify_product_id == product.id)
                .all()
            )

            all_competitors_velocity = []
            total_competitor_sales = 0

            for comp_mapping, competitor in all_competitor_mappings:
                velocity = db.query(CompetitorSalesVelocity).filter(
                    CompetitorSalesVelocity.competitor_product_id == competitor.id
                ).first()

                if velocity and velocity.total_sales_estimate:
                    total_competitor_sales += velocity.total_sales_estimate

                    all_competitors_velocity.append({
                        'website': competitor.website,
                        'product_name': competitor.normalized_name or competitor.raw_name,
                        'avg_daily_sales': velocity.avg_daily_sales or 0,
                        'weekly_sales_estimate': velocity.weekly_sales_estimate or 0,
                        'total_sales_estimate': velocity.total_sales_estimate or 0,
                        'current_stock': competitor.stock_amount or 0,
                        'price': competitor.price_ore / 100 if competitor.price_ore else 0
                    })

            sales_data.append({
                'product_id': product.id,
                'product_title': product.title,
                'product_handle': product.handle,
                'variant_id': variant.id,
                'variant_title': variant.title,
                'current_stock': variant.inventory_quantity or 0,
                'current_price': float(variant.price) if variant.price else 0,

                # My sales data
                'my_sales': {
                    'total_units_sold': my_sales,
                    'daily_breakdown': my_daily_sales[-7:],  # Last 7 days
                    'avg_daily_sales': my_sales / days_back if days_back > 0 else 0
                },

                # Competitor sales data
                'competitor_sales': {
                    'total_estimated_sales': total_competitor_sales,
                    'competitors_count': len(all_competitors_velocity),
                    'by_competitor': all_competitors_velocity
                },

                # Comparison
                'comparison': {
                    'my_market_share_pct': (my_sales / (my_sales + total_competitor_sales) * 100) if (my_sales + total_competitor_sales) > 0 else 0,
                    'sales_difference': my_sales - total_competitor_sales,
                    'outperforming': my_sales > total_competitor_sales
                }
            })

        # Sort by total sales (descending)
        sales_data.sort(key=lambda x: x['my_sales']['total_units_sold'], reverse=True)

        return {
            'period_days': days_back,
            'start_date': cutoff_date.date().isoformat(),
            'end_date': datetime.now().date().isoformat(),
            'total_products': len(sales_data),
            'summary': {
                'my_total_sales': sum(item['my_sales']['total_units_sold'] for item in sales_data),
                'competitor_total_sales': sum(item['competitor_sales']['total_estimated_sales'] for item in sales_data),
                'products_outperforming': sum(1 for item in sales_data if item['comparison']['outperforming'])
            },
            'products': sales_data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate sales comparison: {str(e)}")


@router.get("/sales-trends/{product_id}")
async def get_product_sales_trend(
    product_id: int,
    days_back: int = Query(30, description="Number of days to look back"),
    db: Session = Depends(get_db)
):
    """
    Get detailed sales trend for a specific product over time.
    Shows daily sales and comparison with competitors.
    """
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

        variant = db.query(Variant).filter(Variant.product_id == product_id).first()
        if not variant:
            raise HTTPException(status_code=404, detail="No variant found for product")

        # Fetch actual Shopify orders
        orders = fetch_shopify_orders(days_back)

        # Calculate sales from orders
        daily_sales = defaultdict(int)

        for order in orders:
            order_date = datetime.fromisoformat(order['createdAt'].replace('Z', '+00:00')).date()

            for item_edge in order.get('lineItems', {}).get('edges', []):
                item = item_edge['node']
                variant_gid = item.get('variant', {}).get('id') if item.get('variant') else None

                if variant_gid == variant.shopify_id:
                    quantity = item.get('quantity', 0)
                    daily_sales[order_date.isoformat()] += quantity

        daily_data = []
        cumulative_sales = 0

        for date in sorted(daily_sales.keys()):
            units_sold = daily_sales[date]
            cumulative_sales += units_sold

            daily_data.append({
                'date': date,
                'units_sold': units_sold,
                'cumulative_sales': cumulative_sales,
                'stock_remaining': variant.inventory_quantity or 0,
                'price': float(variant.price) if variant.price else 0
            })

        return {
            'product_id': product_id,
            'product_title': product.title,
            'period_days': days_back,
            'total_sales': cumulative_sales,
            'daily_data': daily_data
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get sales trend: {str(e)}")


@router.get("/test-orders")
async def test_orders_connection():
    """
    Test endpoint to check if we can fetch ANY orders from Shopify at all.
    Fetches the 5 most recent orders without date restrictions.
    """
    try:
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()

        if not shop or not token:
            return {"error": "Shopify credentials not configured"}

        query = """
        query($first: Int!) {
            orders(first: $first, sortKey: CREATED_AT, reverse: true) {
                edges {
                    node {
                        id
                        name
                        createdAt
                        totalPriceSet {
                            shopMoney {
                                amount
                            }
                        }
                        lineItems(first: 5) {
                            edges {
                                node {
                                    title
                                    quantity
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        url = f"https://{shop}/admin/api/{settings.shopify_api_version}/graphql.json"
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json"
        }

        response = requests.post(
            url,
            json={"query": query, "variables": {"first": 5}},
            headers=headers,
            timeout=30
        )

        if not response.ok:
            return {
                "error": f"API request failed: {response.status_code}",
                "details": response.text
            }

        data = response.json()

        if "errors" in data:
            return {
                "error": "GraphQL errors",
                "details": data["errors"]
            }

        orders = data.get("data", {}).get("orders", {}).get("edges", [])

        return {
            "success": True,
            "orders_count": len(orders),
            "orders": [
                {
                    "name": order["node"]["name"],
                    "created_at": order["node"]["createdAt"],
                    "items_count": len(order["node"]["lineItems"]["edges"])
                }
                for order in orders
            ],
            "shopify_api_version": settings.shopify_api_version,
            "shop": shop
        }

    except Exception as e:
        return {"error": str(e)}


@router.get("/diagnostics")
async def get_analytics_diagnostics(
    days_back: int = Query(30, description="Number of days to look back"),
    db: Session = Depends(get_db)
):
    """
    Diagnostic endpoint to check analytics data sources and configuration.
    Helps debug why analytics might not be showing data.
    """
    try:
        diagnostics = {
            'shopify_configured': False,
            'orders_fetched': 0,
            'sample_order': None,
            'mapped_products_count': 0,
            'variants_with_sales': 0,
            'date_range': {
                'start': (datetime.now() - timedelta(days=days_back)).date().isoformat(),
                'end': datetime.now().date().isoformat()
            }
        }

        # Check Shopify credentials
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()
        diagnostics['shopify_configured'] = bool(shop and token)
        diagnostics['shop'] = shop if shop else 'NOT SET'

        # Fetch orders
        if diagnostics['shopify_configured']:
            orders = fetch_shopify_orders(days_back)
            diagnostics['orders_fetched'] = len(orders)

            if orders:
                # Include sample order (first one)
                sample = orders[0]
                diagnostics['sample_order'] = {
                    'name': sample.get('name'),
                    'created_at': sample.get('createdAt'),
                    'line_items_count': len(sample.get('lineItems', {}).get('edges', []))
                }

            # Calculate sales per variant
            sales_by_variant = defaultdict(int)
            for order in orders:
                for item_edge in order.get('lineItems', {}).get('edges', []):
                    item = item_edge['node']
                    variant_gid = item.get('variant', {}).get('id') if item.get('variant') else None
                    if variant_gid:
                        quantity = item.get('quantity', 0)
                        sales_by_variant[variant_gid] += quantity

            diagnostics['variants_with_sales'] = len(sales_by_variant)
            diagnostics['total_units_sold'] = sum(sales_by_variant.values())

        # Count mapped products
        mapped_count = (
            db.query(Product)
            .join(Variant, Product.id == Variant.product_id)
            .join(CompetitorProductMapping, CompetitorProductMapping.shopify_product_id == Product.id)
            .filter(
                and_(
                    Product.status == 'ACTIVE',
                    ~Variant.title.ilike('%booster pack%')
                )
            )
            .distinct()
            .count()
        )
        diagnostics['mapped_products_count'] = mapped_count

        return diagnostics

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagnostics failed: {str(e)}")


@router.get("/competitor-test")
async def test_competitor_endpoint():
    """Simple test endpoint"""
    return {
        "status": "working",
        "message": "Competitor analytics endpoint is accessible"
    }


@router.get("/competitor-overview")
async def get_competitor_overview(
    days_back: int = Query(30, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """
    Comprehensive competitor analytics overview.
    Shows stock changes, sales velocity, and activity per website.
    """
    try:
        print(f"[INFO] Starting competitor overview analysis for {days_back} days")

        # First, let's test with a simple return
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Get all competitors grouped by website
        print(f"[INFO] Querying distinct websites...")
        try:
            websites = db.query(CompetitorProduct.website).distinct().all()
            print(f"[INFO] Found {len(websites)} websites")
        except Exception as e:
            print(f"[ERROR] Failed to query websites: {str(e)}")
            raise

        website_analytics = []

        for (website,) in websites:
            # Get all products for this website
            products = db.query(CompetitorProduct).filter(
                CompetitorProduct.website == website
            ).all()

            if not products:
                continue

            # Calculate totals for this website
            total_products = len(products)
            total_current_stock = sum(p.stock_amount or 0 for p in products)
            total_sales_estimate = 0
            total_daily_sales = 0

            products_detail = []

            for product in products:
                # Get sales velocity
                velocity = db.query(CompetitorSalesVelocity).filter(
                    CompetitorSalesVelocity.competitor_product_id == product.id
                ).first()

                if velocity:
                    total_sales_estimate += velocity.total_sales_estimate or 0
                    total_daily_sales += velocity.avg_daily_sales or 0

                # Get stock changes from daily snapshots
                daily_snapshots = db.query(CompetitorProductDaily).filter(
                    and_(
                        CompetitorProductDaily.competitor_product_id == product.id,
                        CompetitorProductDaily.snapshot_date >= cutoff_date.date()
                    )
                ).order_by(CompetitorProductDaily.snapshot_date).all()

                # Calculate stock added/removed
                stock_added = 0
                stock_removed = 0
                price_changes = 0

                for i in range(1, len(daily_snapshots)):
                    prev = daily_snapshots[i-1]
                    curr = daily_snapshots[i]

                    stock_diff = (curr.stock_amount or 0) - (prev.stock_amount or 0)
                    if stock_diff > 0:
                        stock_added += stock_diff
                    elif stock_diff < 0:
                        stock_removed += abs(stock_diff)

                    prev_price = prev.price_ore if prev.price_ore is not None else 0
                    curr_price = curr.price_ore if curr.price_ore is not None else 0
                    if prev_price != curr_price:
                        price_changes += 1

                products_detail.append({
                    'product_id': product.id,
                    'name': product.normalized_name or product.raw_name or 'Unknown',
                    'current_stock': product.stock_amount or 0,
                    'current_price': (product.price_ore / 100) if product.price_ore else 0,
                    'stock_added': stock_added,
                    'stock_removed': stock_removed,
                    'price_changes': price_changes,
                    'avg_daily_sales': velocity.avg_daily_sales if velocity and velocity.avg_daily_sales else 0,
                    'total_sales_estimate': velocity.total_sales_estimate if velocity and velocity.total_sales_estimate else 0,
                    'days_until_sellout': velocity.days_until_sellout if velocity and velocity.days_until_sellout else None,
                    'last_updated': product.last_check_time.isoformat() if product.last_check_time else None
                })

            # Calculate website-level stock changes
            website_stock_added = sum(p['stock_added'] for p in products_detail)
            website_stock_removed = sum(p['stock_removed'] for p in products_detail)

            website_analytics.append({
                'website': website,
                'summary': {
                    'total_products': total_products,
                    'current_stock': total_current_stock,
                    'stock_added': website_stock_added,
                    'stock_removed': website_stock_removed,
                    'estimated_sales': total_sales_estimate,
                    'avg_daily_sales': total_daily_sales,
                    'total_price_changes': sum(p['price_changes'] for p in products_detail)
                },
                'products': sorted(products_detail, key=lambda x: x['stock_removed'], reverse=True)
            })

        # Sort websites by total sales volume
        website_analytics.sort(key=lambda x: x['summary']['stock_removed'], reverse=True)

        return {
            'period_days': days_back,
            'start_date': cutoff_date.date().isoformat(),
            'end_date': datetime.now().date().isoformat(),
            'websites': website_analytics,
            'totals': {
                'total_websites': len(website_analytics),
                'total_products': sum(w['summary']['total_products'] for w in website_analytics),
                'total_stock': sum(w['summary']['current_stock'] for w in website_analytics),
                'total_stock_added': sum(w['summary']['stock_added'] for w in website_analytics),
                'total_stock_removed': sum(w['summary']['stock_removed'] for w in website_analytics),
                'total_estimated_sales': sum(w['summary']['estimated_sales'] for w in website_analytics)
            }
        }

    except Exception as e:
        import traceback
        print(f"[ERROR] Competitor overview failed: {str(e)}")
        print(f"[ERROR] Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Failed to generate competitor overview: {str(e)}")


@router.get("/top-sellers")
async def get_top_sellers(
    days_back: int = Query(30, description="Number of days to look back"),
    limit: int = Query(10, description="Number of top sellers to return"),
    db: Session = Depends(get_db)
):
    """Get top selling products with competitor mappings."""
    try:
        # Fetch actual Shopify orders
        orders = fetch_shopify_orders(days_back)

        # Calculate sales from orders
        sales_by_variant = defaultdict(int)

        for order in orders:
            for item_edge in order.get('lineItems', {}).get('edges', []):
                item = item_edge['node']
                variant_gid = item.get('variant', {}).get('id') if item.get('variant') else None

                if variant_gid:
                    quantity = item.get('quantity', 0)
                    sales_by_variant[variant_gid] += quantity

        # Get all products with competitor mappings (exclude packs)
        mapped_products = (
            db.query(Product, Variant)
            .join(Variant, Product.id == Variant.product_id)
            .join(CompetitorProductMapping, CompetitorProductMapping.shopify_product_id == Product.id)
            .filter(
                and_(
                    Product.status == 'ACTIVE',
                    ~Variant.title.ilike('%booster pack%')
                )
            )
            .distinct(Product.id)
            .all()
        )

        sellers = []

        for product, variant in mapped_products:
            total_sales = sales_by_variant.get(variant.shopify_id, 0)

            if total_sales > 0:
                sellers.append({
                    'product_id': product.id,
                    'product_title': product.title,
                    'variant_title': variant.title,
                    'total_sales': total_sales,
                    'current_stock': variant.inventory_quantity or 0,
                    'current_price': float(variant.price) if variant.price else 0,
                    'revenue_estimate': total_sales * float(variant.price) if variant.price else 0
                })

        # Sort by sales
        sellers.sort(key=lambda x: x['total_sales'], reverse=True)

        return {
            'period_days': days_back,
            'total_products_sold': len(sellers),
            'top_sellers': sellers[:limit]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get top sellers: {str(e)}")
