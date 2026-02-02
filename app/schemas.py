"""Pydantic schemas for request/response validation."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ============================================================================
# Product Schemas
# ============================================================================

class VariantBase(BaseModel):
    title: str
    sku: Optional[str] = None
    price: float
    compare_at_price: Optional[float] = None
    inventory_quantity: int = 0
    available_for_sale: bool = True
    option_name: Optional[str] = None
    option_value: Optional[str] = None


class VariantCreate(VariantBase):
    shopify_id: str
    inventory_item_id: Optional[str] = None


class VariantResponse(VariantBase):
    id: int
    shopify_id: str
    product_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProductBase(BaseModel):
    title: str
    handle: str
    status: Optional[str] = "active"
    template_suffix: Optional[str] = None
    collection_id: Optional[str] = None
    is_preorder: bool = False


class ProductCreate(ProductBase):
    shopify_id: str


class ProductResponse(ProductBase):
    id: int
    shopify_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_synced_at: Optional[datetime] = None
    variants: List[VariantResponse] = []

    class Config:
        from_attributes = True


# ============================================================================
# SNKRDUNK Schemas
# ============================================================================

class SnkrdunkMappingBase(BaseModel):
    snkrdunk_key: str
    series_en: Optional[str] = None
    name_short: Optional[str] = None
    type_en: Optional[str] = None
    has_shrink_wrap: bool = True
    product_shopify_id: Optional[str] = None
    handle: Optional[str] = None
    disabled: bool = False
    notes: Optional[str] = None


class SnkrdunkMappingCreate(SnkrdunkMappingBase):
    pass


class SnkrdunkMappingResponse(SnkrdunkMappingBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    last_price_updated: Optional[datetime] = None

    class Config:
        from_attributes = True


class TranslationBase(BaseModel):
    japanese_text: str
    english_text: str


class TranslationCreate(TranslationBase):
    pass


class TranslationResponse(TranslationBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Price Plan Schemas
# ============================================================================

class PricePlanItemBase(BaseModel):
    product_shopify_id: str
    variant_shopify_id: str
    current_title: Optional[str] = None
    current_price: float
    current_compare_at: Optional[float] = None
    new_price: float
    new_compare_at: Optional[float] = None
    snkrdunk_key: Optional[str] = None
    snkrdunk_price_jpy: Optional[float] = None
    snkrdunk_link: Optional[str] = None


class PricePlanItemCreate(PricePlanItemBase):
    pass


class PricePlanItemResponse(PricePlanItemBase):
    id: int
    plan_id: int
    applied: bool = False
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class PricePlanBase(BaseModel):
    plan_type: str = "price_update"
    collection_id: Optional[str] = None
    fx_rate: Optional[float] = None
    pricing_adjustments: Optional[Dict[str, Any]] = None
    filters: Optional[Dict[str, Any]] = None


class PricePlanCreate(PricePlanBase):
    items: List[PricePlanItemCreate] = []


class PricePlanResponse(PricePlanBase):
    id: int
    status: str
    generated_at: datetime
    applied_at: Optional[datetime] = None
    total_items: int
    applied_items: int
    failed_items: int
    items: List[PricePlanItemResponse] = []

    class Config:
        from_attributes = True


class PricePlanSummary(BaseModel):
    id: int
    plan_type: str
    status: str
    generated_at: datetime
    applied_at: Optional[datetime] = None
    total_items: int
    applied_items: int
    failed_items: int

    class Config:
        from_attributes = True


# ============================================================================
# Booster Variant Plan Schemas
# ============================================================================

class BoosterVariantPlanItemBase(BaseModel):
    product_shopify_id: str
    product_title: str
    current_variant_id: str
    current_price: float
    packs_per_box: int
    box_price: float
    pack_price: float


class BoosterVariantPlanItemCreate(BoosterVariantPlanItemBase):
    pass


class BoosterVariantPlanItemResponse(BoosterVariantPlanItemBase):
    id: int
    plan_id: int
    applied: bool = False
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class BoosterVariantPlanBase(BaseModel):
    collection_id: str
    packs_per_box_default: int = 30
    pack_markup: float = 1.20
    special_pack_counts: Optional[List[List[Any]]] = None


class BoosterVariantPlanCreate(BoosterVariantPlanBase):
    items: List[BoosterVariantPlanItemCreate] = []


class BoosterVariantPlanResponse(BoosterVariantPlanBase):
    id: int
    status: str
    generated_at: datetime
    applied_at: Optional[datetime] = None
    total_items: int
    applied_items: int
    items: List[BoosterVariantPlanItemResponse] = []

    class Config:
        from_attributes = True


# ============================================================================
# Booster Inventory Plan Schemas
# ============================================================================

class BoosterInventoryPlanItemBase(BaseModel):
    product_shopify_id: str
    product_title: str
    box_variant_id: str
    box_inventory_item_id: str
    box_current_available: int
    box_delta: int
    pack_variant_id: str
    pack_inventory_item_id: str
    pack_current_available: int
    pack_delta: int
    packs_per_box: int


class BoosterInventoryPlanItemCreate(BoosterInventoryPlanItemBase):
    pass


class BoosterInventoryPlanItemResponse(BoosterInventoryPlanItemBase):
    id: int
    plan_id: int
    applied: bool = False
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class BoosterInventoryPlanBase(BaseModel):
    collection_id: str
    location_id: str
    location_name: str


class BoosterInventoryPlanCreate(BoosterInventoryPlanBase):
    items: List[BoosterInventoryPlanItemCreate] = []


class BoosterInventoryPlanResponse(BoosterInventoryPlanBase):
    id: int
    status: str
    generated_at: datetime
    applied_at: Optional[datetime] = None
    total_items: int
    applied_items: int
    items: List[BoosterInventoryPlanItemResponse] = []

    class Config:
        from_attributes = True


# ============================================================================
# Stock Report Schemas
# ============================================================================

class StockReportCreate(BaseModel):
    collection_id: str
    total_products: int
    total_variants: int
    report_data: Dict[str, Any]


class StockReportResponse(BaseModel):
    id: int
    collection_id: str
    generated_at: datetime
    total_products: int
    total_variants: int
    report_data: Dict[str, Any]

    class Config:
        from_attributes = True


# ============================================================================
# Audit Log Schemas
# ============================================================================

class AuditLogCreate(BaseModel):
    operation: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    user_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    success: bool = True
    error_message: Optional[str] = None


class AuditLogResponse(AuditLogCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ============================================================================
# Request/Response Schemas
# ============================================================================

class FetchCollectionRequest(BaseModel):
    collection_id: str
    exclude_title_contains: Optional[str] = None


class FetchCollectionResponse(BaseModel):
    total_products: int
    total_variants: int
    synced_at: datetime


class GeneratePricePlanRequest(BaseModel):
    variant_type: str = "box"  # "box" or "pack"
    exchange_rate: Optional[float] = None
    shipping_cost_jpy: Optional[int] = 500
    min_margin_pct: Optional[float] = 20.0
    vat_pct: Optional[float] = 25.0
    pack_markup_pct: Optional[float] = 20.0  # Markup for pack pricing (10-20% typical)
    min_change_threshold: Optional[float] = 5.0  # Minimum price change in NOK to include in plan
    plan_type: str = "price_update"
    strategy: Optional[str] = None  # "match_competition" or None for normal generation
    items: Optional[List[Dict[str, Any]]] = None  # Pre-calculated items for match_competition strategy


class ApplyPlanRequest(BaseModel):
    plan_id: int


class ApplyPlanResponse(BaseModel):
    plan_id: int
    status: str
    applied_items: int
    failed_items: int
    errors: List[str] = []


class SnkrdunkFetchRequest(BaseModel):
    pages: List[int] = Field(default=[1, 2, 3, 4, 5, 6])
    force_refresh: bool = False


class SnkrdunkMatchingResponse(BaseModel):
    total_items: int
    kept_items: int
    skipped_items: int
    new_mappings: int
    results: List[Dict[str, Any]]


# ============================================================================
# Settings Schemas
# ============================================================================

class SettingBase(BaseModel):
    key: str
    value: Optional[str] = None
    description: Optional[str] = None
    is_sensitive: bool = False


class SettingCreate(SettingBase):
    pass


class SettingUpdate(BaseModel):
    value: Optional[str] = None
    description: Optional[str] = None


class SettingResponse(BaseModel):
    id: int
    key: str
    value: Optional[str] = None  # Will be masked if sensitive
    description: Optional[str] = None
    is_sensitive: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SettingUpdateRequest(BaseModel):
    shopify_shop: Optional[str] = None
    shopify_token: Optional[str] = None
    google_translate_api_key: Optional[str] = None
