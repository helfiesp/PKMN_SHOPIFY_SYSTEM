"""Shopify service layer - handles Shopify GraphQL operations."""
import requests
from typing import Optional, List
from sqlalchemy.orm import Session
from datetime import datetime, timezone

from app.models import Product, Variant, ProductPriceHistory
from app.config import settings


class ShopifyService:
    """Service for interacting with Shopify GraphQL API."""
    
    def __init__(self):
        self.api_version = settings.shopify_api_version
    
    def _get_credentials(self):
        """Get current Shopify credentials from DB or config."""
        shop = settings.get_shopify_shop()
        token = settings.get_shopify_token()
        return shop, token
    
    def _graphql_request(self, query: str, variables: dict = None) -> dict:
        """Make a GraphQL request to Shopify."""
        shop, token = self._get_credentials()
        
        if not shop or not token:
            raise Exception("Shopify credentials not configured. Please set them in Settings.")
        
        graphql_url = f"https://{shop}/admin/api/{self.api_version}/graphql.json"
        
        headers = {
            "X-Shopify-Access-Token": token,
            "Content-Type": "application/json"
        }
        response = requests.post(
            graphql_url,
            json={"query": query, "variables": variables or {}},
            headers=headers,
            timeout=60
        )
        response.raise_for_status()
        data = response.json()
        
        if "errors" in data:
            raise Exception(f"GraphQL errors: {data['errors']}")
        
        return data.get("data", {})
    
    async def fetch_and_store_collection(
        self,
        db: Session,
        collection_id: str,
        exclude_title_contains: Optional[str] = None
    ) -> dict:
        """Fetch products from Shopify collection and store in database."""
        # Always exclude Deluxe products for Pokemon collection
        if collection_id == "444175384827":  # Pokemon JP collection
            if exclude_title_contains:
                exclude_title_contains = f"{exclude_title_contains},deluxe"
            else:
                exclude_title_contains = "deluxe"
        
        collection_gid = f"gid://shopify/Collection/{collection_id}"
        
        query = """
        query($collectionId: ID!, $first: Int!, $after: String) {
          collection(id: $collectionId) {
            id
            title
            products(first: $first, after: $after) {
              pageInfo { hasNextPage endCursor }
              edges {
                node {
                  id
                  title
                  handle
                  status
                  templateSuffix
                  variants(first: 250) {
                    edges {
                      node {
                        id
                        title
                        price
                        compareAtPrice
                        inventoryQuantity
                        availableForSale
                        sku
                        inventoryItem { id }
                      }
                    }
                  }
                }
              }
            }
          }
        }
        """
        
        exclude_keywords = []
        if exclude_title_contains:
            exclude_keywords = [k.strip().lower() for k in exclude_title_contains.split(",")]
        
        all_products = []
        has_next_page = True
        cursor = None
        
        while has_next_page:
            variables = {
                "collectionId": collection_gid,
                "first": 50,
                "after": cursor
            }
            
            result = self._graphql_request(query, variables)
            collection_data = result.get("collection", {})
            products_data = collection_data.get("products", {})
            
            for edge in products_data.get("edges", []):
                product_node = edge["node"]
                
                # Apply exclusion filter
                if exclude_keywords:
                    title_lower = product_node["title"].lower()
                    if any(kw in title_lower for kw in exclude_keywords):
                        continue
                
                all_products.append(product_node)
            
            page_info = products_data.get("pageInfo", {})
            has_next_page = page_info.get("hasNextPage", False)
            cursor = page_info.get("endCursor")
        
        # Store in database
        total_products = 0
        total_variants = 0
        
        for prod_data in all_products:
            # Upsert product
            product = db.query(Product).filter(
                Product.shopify_id == prod_data["id"]
            ).first()
            
            is_preorder = (prod_data.get("templateSuffix", "") or "").lower() == "preorder"
            
            if product:
                # Update existing
                product.title = prod_data["title"]
                product.handle = prod_data["handle"]
                product.status = prod_data["status"]
                product.template_suffix = prod_data.get("templateSuffix")
                product.collection_id = collection_id
                product.is_preorder = is_preorder
                product.last_synced_at = datetime.now(timezone.utc)
            else:
                # Create new
                product = Product(
                    shopify_id=prod_data["id"],
                    title=prod_data["title"],
                    handle=prod_data["handle"],
                    status=prod_data["status"],
                    template_suffix=prod_data.get("templateSuffix"),
                    collection_id=collection_id,
                    is_preorder=is_preorder,
                    last_synced_at=datetime.now(timezone.utc)
                )
                db.add(product)
                db.flush()
            
            total_products += 1
            
            # Upsert variants
            for var_edge in prod_data.get("variants", {}).get("edges", []):
                var_data = var_edge["node"]
                
                variant = db.query(Variant).filter(
                    Variant.shopify_id == var_data["id"]
                ).first()
                
                inventory_item_id = var_data.get("inventoryItem", {}).get("id") if var_data.get("inventoryItem") else None
                
                if variant:
                    # Check if price changed to record history
                    price_changed = (variant.price != float(var_data["price"]) or 
                                    variant.compare_at_price != (float(var_data["compareAtPrice"]) if var_data.get("compareAtPrice") else None))
                    
                    variant.title = var_data["title"]
                    variant.sku = var_data.get("sku")
                    variant.price = float(var_data["price"])
                    variant.compare_at_price = float(var_data["compareAtPrice"]) if var_data.get("compareAtPrice") else None
                    variant.inventory_quantity = var_data.get("inventoryQuantity", 0)
                    variant.available_for_sale = var_data.get("availableForSale", True)
                    variant.inventory_item_id = inventory_item_id
                    
                    # Save to price history if price changed
                    if price_changed:
                        db.add(ProductPriceHistory(
                            variant_id=variant.id,
                            price=variant.price,
                            compare_at_price=variant.compare_at_price,
                            inventory_quantity=variant.inventory_quantity
                        ))
                else:
                    variant = Variant(
                        shopify_id=var_data["id"],
                        product_id=product.id,
                        title=var_data["title"],
                        sku=var_data.get("sku"),
                        price=float(var_data["price"]),
                        compare_at_price=float(var_data["compareAtPrice"]) if var_data.get("compareAtPrice") else None,
                        inventory_quantity=var_data.get("inventoryQuantity", 0),
                        available_for_sale=var_data.get("availableForSale", True),
                        inventory_item_id=inventory_item_id
                    )
                    db.add(variant)
                    db.flush()  # Get variant ID
                    
                    # Save initial price to history
                    db.add(ProductPriceHistory(
                        variant_id=variant.id,
                        price=variant.price,
                        compare_at_price=variant.compare_at_price,
                        inventory_quantity=variant.inventory_quantity
                    ))
                
                total_variants += 1
        
        db.commit()
        
        return {
            "total_products": total_products,
            "total_variants": total_variants,
            "synced_at": datetime.now(timezone.utc)
        }
    
    async def sync_collection(
        self,
        db: Session,
        collection_id: str,
        exclude_title_contains: Optional[str] = None
    ) -> dict:
        """Alias for fetch_and_store_collection."""
        return await self.fetch_and_store_collection(db, collection_id, exclude_title_contains)
    
    def get_products(
        self,
        db: Session,
        collection_id: Optional[str] = None,
        status: Optional[str] = None,
        template_suffix: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Product]:
        """Get products from database."""
        query = db.query(Product)
        
        if collection_id:
            query = query.filter(Product.collection_id == collection_id)
        if status:
            query = query.filter(Product.status == status)
        if template_suffix:
            query = query.filter(Product.template_suffix == template_suffix)
        
        return query.offset(skip).limit(limit).all()
    
    def get_product_by_id(self, db: Session, product_id: int) -> Optional[Product]:
        """Get product by database ID."""
        return db.query(Product).filter(Product.id == product_id).first()
    
    def get_product_by_shopify_id(self, db: Session, shopify_id: str) -> Optional[Product]:
        """Get product by Shopify ID."""
        return db.query(Product).filter(Product.shopify_id == shopify_id).first()
    
    def delete_product(self, db: Session, product_id: int) -> bool:
        """Delete product from database."""
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            db.delete(product)
            db.commit()
            return True
        return False


# Singleton instance
shopify_service = ShopifyService()
