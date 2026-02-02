"""SQLAlchemy database models."""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey, Index, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Product(Base):
    """Shopify product model."""
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(String(255), unique=True, nullable=False, index=True)
    title = Column(String(500), nullable=False)
    handle = Column(String(255), nullable=False, index=True)
    status = Column(String(50))  # active, archived, draft
    template_suffix = Column(String(100))
    collection_id = Column(String(255), index=True)
    is_preorder = Column(Boolean, default=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_synced_at = Column(DateTime(timezone=True))
    
    # Relationships
    variants = relationship("Variant", back_populates="product", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_product_collection_status', 'collection_id', 'status'),
    )


class Variant(Base):
    """Shopify product variant model."""
    __tablename__ = "variants"

    id = Column(Integer, primary_key=True, index=True)
    shopify_id = Column(String(255), unique=True, nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    
    title = Column(String(500))
    sku = Column(String(255), index=True)
    price = Column(Float, nullable=False)
    compare_at_price = Column(Float)
    
    inventory_quantity = Column(Integer, default=0)
    available_for_sale = Column(Boolean, default=True)
    inventory_item_id = Column(String(255))
    
    # Variant options (e.g., Type: Booster Box)
    option_name = Column(String(100))
    option_value = Column(String(255))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    product = relationship("Product", back_populates="variants")
    
    __table_args__ = (
        Index('idx_variant_product_option', 'product_id', 'option_value'),
    )


class SnkrdunkMapping(Base):
    """Mapping between SNKRDUNK products and Shopify products."""
    __tablename__ = "snkrdunk_mappings"

    id = Column(Integer, primary_key=True, index=True)
    snkrdunk_key = Column(String(500), unique=True, nullable=False, index=True)
    
    # SNKRDUNK data
    series_en = Column(String(255))
    name_short = Column(String(255))
    type_en = Column(String(100))
    has_shrink_wrap = Column(Boolean, default=True)
    
    # Shopify mapping
    product_shopify_id = Column(String(255), index=True)
    handle = Column(String(255))
    
    # Mapping metadata
    disabled = Column(Boolean, default=False)
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Translation(Base):
    """Japanese to English translation cache."""
    __tablename__ = "translations"

    id = Column(Integer, primary_key=True, index=True)
    japanese_text = Column(Text, unique=True, nullable=False, index=True)
    english_text = Column(Text, nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class PricePlan(Base):
    """Price update plan model."""
    __tablename__ = "price_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_type = Column(String(50), nullable=False)  # price_update, booster_price
    status = Column(String(50), default="pending")  # pending, applied, cancelled
    
    # Plan metadata
    collection_id = Column(String(255))
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    applied_at = Column(DateTime(timezone=True))
    
    # Pricing rules (stored as JSON)
    fx_rate = Column(Float)
    pricing_adjustments = Column(JSON)
    filters = Column(JSON)
    
    # Summary
    total_items = Column(Integer, default=0)
    applied_items = Column(Integer, default=0)
    failed_items = Column(Integer, default=0)
    
    # Relationships
    items = relationship("PricePlanItem", back_populates="plan", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_plan_status_type', 'status', 'plan_type'),
    )


class PricePlanItem(Base):
    """Individual item in a price plan."""
    __tablename__ = "price_plan_items"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("price_plans.id"), nullable=False)
    
    # Shopify product/variant
    product_shopify_id = Column(String(255), nullable=False, index=True)
    variant_shopify_id = Column(String(255), nullable=False)
    
    # Current state (snapshot at plan generation)
    current_title = Column(String(500))
    current_price = Column(Float)
    current_compare_at = Column(Float)
    
    # Proposed changes
    new_price = Column(Float)
    new_compare_at = Column(Float)
    
    # SNKRDUNK source data
    snkrdunk_key = Column(String(500))
    snkrdunk_price_jpy = Column(Float)
    snkrdunk_link = Column(String(500))
    
    # Application result
    applied = Column(Boolean, default=False)
    error_message = Column(Text)
    
    # Relationships
    plan = relationship("PricePlan", back_populates="items")
    
    __table_args__ = (
        Index('idx_plan_item_variant', 'plan_id', 'variant_shopify_id'),
    )


class BoosterVariantPlan(Base):
    """Plan for splitting single variants into Booster Box + Pack."""
    __tablename__ = "booster_variant_plans"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="pending")  # pending, applied, cancelled
    
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    applied_at = Column(DateTime(timezone=True))
    
    # Rules
    collection_id = Column(String(255))
    packs_per_box_default = Column(Integer, default=30)
    pack_markup = Column(Float, default=1.20)
    special_pack_counts = Column(JSON)  # e.g., [["terastal festival", 10], ...]
    
    total_items = Column(Integer, default=0)
    applied_items = Column(Integer, default=0)
    
    # Relationships
    items = relationship("BoosterVariantPlanItem", back_populates="plan", cascade="all, delete-orphan")


class BoosterVariantPlanItem(Base):
    """Individual product in booster variant split plan."""
    __tablename__ = "booster_variant_plan_items"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("booster_variant_plans.id"), nullable=False)
    
    product_shopify_id = Column(String(255), nullable=False, index=True)
    product_title = Column(String(500))
    
    # Current single variant
    current_variant_id = Column(String(255))
    current_price = Column(Float)
    
    # Computed values
    packs_per_box = Column(Integer)
    box_price = Column(Float)
    pack_price = Column(Float)
    
    applied = Column(Boolean, default=False)
    error_message = Column(Text)
    
    # Relationships
    plan = relationship("BoosterVariantPlan", back_populates="items")


class BoosterInventoryPlan(Base):
    """Plan for converting Booster Box inventory to Pack inventory."""
    __tablename__ = "booster_inventory_plans"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), default="pending")
    
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    applied_at = Column(DateTime(timezone=True))
    
    collection_id = Column(String(255))
    location_id = Column(String(255))
    location_name = Column(String(255))
    
    total_items = Column(Integer, default=0)
    applied_items = Column(Integer, default=0)
    
    # Relationships
    items = relationship("BoosterInventoryPlanItem", back_populates="plan", cascade="all, delete-orphan")


class BoosterInventoryPlanItem(Base):
    """Individual inventory adjustment in booster inventory plan."""
    __tablename__ = "booster_inventory_plan_items"

    id = Column(Integer, primary_key=True, index=True)
    plan_id = Column(Integer, ForeignKey("booster_inventory_plans.id"), nullable=False)
    
    product_shopify_id = Column(String(255), nullable=False, index=True)
    product_title = Column(String(500))
    
    # Box variant
    box_variant_id = Column(String(255))
    box_inventory_item_id = Column(String(255))
    box_current_available = Column(Integer)
    box_delta = Column(Integer)  # -1
    
    # Pack variant
    pack_variant_id = Column(String(255))
    pack_inventory_item_id = Column(String(255))
    pack_current_available = Column(Integer)
    pack_delta = Column(Integer)  # +30 or other
    
    packs_per_box = Column(Integer)
    
    applied = Column(Boolean, default=False)
    error_message = Column(Text)
    
    # Relationships
    plan = relationship("BoosterInventoryPlan", back_populates="items")


class StockReport(Base):
    """Stock report snapshot."""
    __tablename__ = "stock_reports"

    id = Column(Integer, primary_key=True, index=True)
    collection_id = Column(String(255), index=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Summary
    total_products = Column(Integer)
    total_variants = Column(Integer)
    
    # Full report data (JSON)
    report_data = Column(JSON)
    
    __table_args__ = (
        Index('idx_stock_report_collection_date', 'collection_id', 'generated_at'),
    )


class PriceChangeLog(Base):
    """Simple log for manual price changes."""
    __tablename__ = "price_change_logs"

    id = Column(Integer, primary_key=True, index=True)
    
    # Product/Variant info
    product_shopify_id = Column(String(255), nullable=False, index=True)
    variant_shopify_id = Column(String(255), nullable=False, index=True)
    product_title = Column(String(500))
    variant_title = Column(String(500))
    
    # Price change
    old_price = Column(Float, nullable=False)
    new_price = Column(Float, nullable=False)
    price_delta = Column(Float)  # new - old
    
    # Source of change
    change_type = Column(String(50), nullable=False)  # 'manual_competitor_match', 'auto_update', etc.
    competitor_name = Column(String(255))  # Which competitor was matched
    competitor_price = Column(Float)  # What their price was
    
    # Metadata
    notes = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_price_change_product', 'product_shopify_id', 'created_at'),
    )


class AuditLog(Base):
    """Audit log for all operations."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(100), nullable=False, index=True)
    entity_type = Column(String(50))  # product, variant, plan, etc.
    entity_id = Column(String(255))
    
    user_id = Column(String(100))  # For future user tracking
    details = Column(JSON)
    
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_audit_operation_date', 'operation', 'created_at'),
    )


class SnkrdunkCache(Base):
    """Cache for SNKRDUNK API responses."""
    __tablename__ = "snkrdunk_cache"

    id = Column(Integer, primary_key=True, index=True)
    page = Column(Integer, nullable=False)
    category_id = Column(Integer)
    brand_id = Column(String(100))
    
    # Cached response
    response_data = Column(JSON)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), index=True)
    
    __table_args__ = (
        Index('idx_snkrdunk_cache_page_brand', 'page', 'brand_id'),
    )


class Setting(Base):
    """Application settings and API keys."""
    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text)
    description = Column(Text)
    is_sensitive = Column(Boolean, default=False)  # For API keys
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# ============================================================================
# COMPETITOR SCRAPING MODELS
# ============================================================================

class CompetitorProduct(Base):
    """Competitor product from scraped websites."""
    __tablename__ = "competitor_products"

    id = Column(Integer, primary_key=True, index=True)
    website = Column(String(100), nullable=False, index=True)  # boosterpakker, hatamontcg, etc.
    product_link = Column(String(1000), nullable=False)
    
    # Raw data from scraper
    raw_name = Column(String(1000))
    price_ore = Column(Integer)  # Price in øre (100 øre = 1 NOK)
    stock_status = Column(String(100))
    stock_amount = Column(Integer, default=0)
    
    # Normalized/detected fields
    normalized_name = Column(String(1000), index=True)
    category = Column(String(100), index=True)  # booster_box, booster_pack, etc.
    brand = Column(String(100), index=True)  # pokemon, one_piece, lorcana, mtg
    language = Column(String(50))  # en, ja, no, etc.
    
    last_scraped_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    daily_snapshots = relationship("CompetitorProductDaily", back_populates="product", cascade="all, delete-orphan")
    snapshots = relationship("CompetitorProductSnapshot", back_populates="product", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index('idx_competitor_website_category', 'website', 'category'),
        Index('idx_competitor_normalized', 'normalized_name', 'category', 'brand'),
    )


class CompetitorProductMapping(Base):
    """Mapping between competitor products and internal products."""
    __tablename__ = "competitor_product_mappings"

    id = Column(Integer, primary_key=True, index=True)
    competitor_product_id = Column(Integer, ForeignKey("competitor_products.id"), nullable=False, index=True)
    shopify_product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    snkrdunk_mapping_id = Column(Integer, ForeignKey("snkrdunk_mappings.id"), nullable=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    competitor_product = relationship("CompetitorProduct")
    shopify_product = relationship("Product")
    snkrdunk_mapping = relationship("SnkrdunkMapping")

    __table_args__ = (
        UniqueConstraint('competitor_product_id', name='uq_competitor_product_mapping'),
    )


class CompetitorProductDaily(Base):
    """Daily snapshot of competitor product (one per day)."""
    __tablename__ = "competitor_products_daily"

    id = Column(Integer, primary_key=True, index=True)
    competitor_product_id = Column(Integer, ForeignKey("competitor_products.id"), nullable=False)
    day = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD
    
    price = Column(String(100))
    stock_status = Column(String(100))
    stock_amount = Column(Integer)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationship
    product = relationship("CompetitorProduct", back_populates="daily_snapshots")
    
    __table_args__ = (
        Index('idx_daily_product_day', 'competitor_product_id', 'day', unique=True),
    )


class CompetitorProductSnapshot(Base):
    """Historical snapshots of competitor products (every scrape)."""
    __tablename__ = "competitor_products_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    competitor_product_id = Column(Integer, ForeignKey("competitor_products.id"), nullable=False)
    
    price = Column(String(100))
    stock_status = Column(String(100))
    stock_amount = Column(Integer)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationship
    product = relationship("CompetitorProduct", back_populates="snapshots")
    
    __table_args__ = (
        Index('idx_snapshot_product_date', 'competitor_product_id', 'created_at'),
    )


class CompetitorProductOverride(Base):
    """Manual overrides for competitor product categorization."""
    __tablename__ = "competitor_product_overrides"

    id = Column(Integer, primary_key=True, index=True)
    website = Column(String(100), index=True)  # None = global override
    normalized_name = Column(String(1000), nullable=False, index=True)
    
    # Override fields
    category = Column(String(100))
    brand = Column(String(100))
    language = Column(String(50))
    
    notes = Column(Text)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_override_website_name', 'website', 'normalized_name'),
    )


# ============================================================================
# PRICE HISTORY MODELS - Track prices over time for all data sources
# ============================================================================

class SnkrdunkPriceHistory(Base):
    """Historical price tracking for SNKRDUNK products."""
    __tablename__ = "snkrdunk_price_history"

    id = Column(Integer, primary_key=True, index=True)
    scan_log_id = Column(Integer, ForeignKey('snkrdunk_scan_logs.id'), nullable=True, index=True)
    snkrdunk_key = Column(String(500), nullable=False, index=True)
    
    # Price data from SNKRDUNK API
    price_jpy = Column(Float)  # Price in JPY
    price_usd = Column(Float)  # Price in USD
    
    # Timestamp when price was recorded
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_snkrdunk_price_scan', 'scan_log_id', 'snkrdunk_key'),
    )


class CompetitorPriceHistory(Base):
    """Historical price tracking for competitor products."""
    __tablename__ = "competitor_price_history"

    id = Column(Integer, primary_key=True, index=True)
    competitor_product_id = Column(Integer, ForeignKey("competitor_products.id"), nullable=False, index=True)
    
    # Price data
    price_ore = Column(Integer)  # Price in øre (100 øre = 1 NOK)
    stock_status = Column(String(100))
    stock_amount = Column(Integer, default=0)
    
    # Timestamp when price was recorded
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationship
    competitor_product = relationship("CompetitorProduct")
    
    __table_args__ = (
        Index('idx_competitor_price_product_date', 'competitor_product_id', 'recorded_at'),
    )


class ProductPriceHistory(Base):
    """Historical price tracking for my Shopify products."""
    __tablename__ = "product_price_history"

    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, ForeignKey("variants.id"), nullable=False, index=True)
    
    # Price data
    price = Column(Float, nullable=False)
    compare_at_price = Column(Float)
    
    # Inventory
    inventory_quantity = Column(Integer, default=0)
    
    # Timestamp when price was recorded
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationship
    variant = relationship("Variant")
    
    __table_args__ = (
        Index('idx_product_price_variant_date', 'variant_id', 'recorded_at'),
    )


# Helper function for competition system
def today_oslo() -> str:
    """Get today's date in Oslo timezone as YYYY-MM-DD string."""
    from datetime import datetime
    from zoneinfo import ZoneInfo
    return datetime.now(ZoneInfo("Europe/Oslo")).strftime("%Y-%m-%d")

class ScanLog(Base):
    """Competitor scan log for tracking scraper runs."""
    __tablename__ = "scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    scraper_name = Column(String(100), nullable=False, index=True)
    status = Column(String(50), nullable=False)  # success, failed
    output = Column(Text, nullable=True)  # stdout from scraper
    error_message = Column(Text, nullable=True)  # stderr if failed
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_scan_log_scraper_date', 'scraper_name', 'created_at'),
    )


class SnkrdunkScanLog(Base):
    """SNKRDUNK price update scan log for tracking price fetches."""
    __tablename__ = "snkrdunk_scan_logs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(String(50), nullable=False)  # success, failed
    total_items = Column(Integer, nullable=True)  # number of products fetched
    output = Column(Text, nullable=True)  # description of what was fetched
    error_message = Column(Text, nullable=True)  # error details if failed
    started_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=False)
    duration_seconds = Column(Float, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_snkrdunk_scan_log_date', 'created_at'),
    )