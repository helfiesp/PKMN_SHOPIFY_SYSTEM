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

router = APIRouter()


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
        query = (
            db.query(Product, Variant, CompetitorProductMapping)
            .join(Variant, Product.id == Variant.product_id)
            .join(CompetitorProductMapping, CompetitorProductMapping.shopify_product_id == Product.id)
            .filter(Product.status == 'ACTIVE')
        )

        if product_id:
            query = query.filter(Product.id == product_id)

        mapped_products = query.all()

        cutoff_date = datetime.now() - timedelta(days=days_back)
        sales_data = []

        for product, variant, mapping in mapped_products:
            # Calculate MY sales from inventory history
            inventory_history = (
                db.query(ProductPriceHistory)
                .filter(
                    ProductPriceHistory.variant_id == variant.id,
                    ProductPriceHistory.recorded_at >= cutoff_date
                )
                .order_by(ProductPriceHistory.recorded_at.asc())
                .all()
            )

            my_sales = 0
            my_daily_sales = []

            if len(inventory_history) >= 2:
                for i in range(1, len(inventory_history)):
                    prev = inventory_history[i-1]
                    curr = inventory_history[i]

                    # Inventory decreased = sales (ignore increases as they're restocks)
                    if prev.inventory_quantity > curr.inventory_quantity:
                        units_sold = prev.inventory_quantity - curr.inventory_quantity
                        my_sales += units_sold

                        my_daily_sales.append({
                            'date': curr.recorded_at.date().isoformat(),
                            'units_sold': units_sold,
                            'remaining_stock': curr.inventory_quantity
                        })

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

        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Get inventory history
        history = (
            db.query(ProductPriceHistory)
            .filter(
                ProductPriceHistory.variant_id == variant.id,
                ProductPriceHistory.recorded_at >= cutoff_date
            )
            .order_by(ProductPriceHistory.recorded_at.asc())
            .all()
        )

        daily_data = []
        cumulative_sales = 0

        for i in range(1, len(history)):
            prev = history[i-1]
            curr = history[i]

            if prev.inventory_quantity > curr.inventory_quantity:
                units_sold = prev.inventory_quantity - curr.inventory_quantity
                cumulative_sales += units_sold

                daily_data.append({
                    'date': curr.recorded_at.date().isoformat(),
                    'units_sold': units_sold,
                    'cumulative_sales': cumulative_sales,
                    'stock_remaining': curr.inventory_quantity,
                    'price': float(curr.price) if curr.price else 0
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


@router.get("/top-sellers")
async def get_top_sellers(
    days_back: int = Query(30, description="Number of days to look back"),
    limit: int = Query(10, description="Number of top sellers to return"),
    db: Session = Depends(get_db)
):
    """Get top selling products with competitor mappings."""
    try:
        cutoff_date = datetime.now() - timedelta(days=days_back)

        # Get all products with competitor mappings
        mapped_products = (
            db.query(Product, Variant)
            .join(Variant, Product.id == Variant.product_id)
            .join(CompetitorProductMapping, CompetitorProductMapping.shopify_product_id == Product.id)
            .filter(Product.status == 'ACTIVE')
            .distinct(Product.id)
            .all()
        )

        sellers = []

        for product, variant in mapped_products:
            inventory_history = (
                db.query(ProductPriceHistory)
                .filter(
                    ProductPriceHistory.variant_id == variant.id,
                    ProductPriceHistory.recorded_at >= cutoff_date
                )
                .order_by(ProductPriceHistory.recorded_at.asc())
                .all()
            )

            total_sales = 0
            if len(inventory_history) >= 2:
                for i in range(1, len(inventory_history)):
                    prev = inventory_history[i-1]
                    curr = inventory_history[i]

                    if prev.inventory_quantity > curr.inventory_quantity:
                        total_sales += prev.inventory_quantity - curr.inventory_quantity

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
