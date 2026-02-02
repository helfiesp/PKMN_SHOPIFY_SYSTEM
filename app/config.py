"""Application configuration."""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings


def get_db_setting(key: str, default: str = "") -> str:
    """Get setting from database with fallback to environment variable."""
    try:
        from app.database import SessionLocal
        from app.models import Setting
        
        db = SessionLocal()
        try:
            setting = db.query(Setting).filter(Setting.key == key).first()
            if setting and setting.value:
                return setting.value
        finally:
            db.close()
    except:
        # Database might not be initialized yet
        pass
    
    # Fallback to environment variable
    return os.getenv(key.upper(), default)


class Settings(BaseSettings):
    # App settings
    app_name: str = "Shopify Price Manager API"
    app_version: str = "1.0.0"
    debug: bool = False
    
    # Database
    database_url: str = "sqlite:///./shopify_app.db"
    
    # Shopify - will be overridden by get_shopify_* methods
    shopify_shop: str = ""
    shopify_token: str = ""
    shopify_api_version: str = "2026-01"
    
    # Google Translate - will be overridden by get_google_api_key
    google_translate_api_key: str = ""
    
    def get_shopify_shop(self) -> str:
        """Get Shopify shop from DB or env."""
        return get_db_setting("shopify_shop", self.shopify_shop)
    
    def get_shopify_token(self) -> str:
        """Get Shopify token from DB or env."""
        return get_db_setting("shopify_token", self.shopify_token)
    
    def get_google_api_key(self) -> str:
        """Get Google API key from DB or env."""
        return get_db_setting("google_translate_api_key", self.google_translate_api_key)
    
    # SNKRDUNK
    snkrdunk_cache_ttl_hours: int = 6
    
    # Default collection IDs
    default_collection_id: str = "444175384827"
    booster_collection_id: str = "444116140283"
    
    # Location
    location_id: str = "81755177211"
    location_name: str = "H. Halvorsens vei 5"
    
    # Pricing rules
    shipping_cost_jpy: float = 500.0
    min_margin: float = 0.20
    vat_rate: float = 0.25
    round_up_step_nok: int = 25
    min_price_change_nok: float = 25.0
    pack_min_price_change_nok: float = 10.0
    massive_change_nok: float = 500.0
    
    # Booster rules
    default_packs_per_box: int = 30
    pack_markup: float = 1.20
    
    # Filtering
    exclude_title_substring: str = "one piece"
    disregard_box_if_no_shrink: bool = True
    pack_title_max_jpy: int = 2000
    
    # Matching
    shopify_match_threshold: float = 0.62
    price_ok_band_nok: int = 25
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
