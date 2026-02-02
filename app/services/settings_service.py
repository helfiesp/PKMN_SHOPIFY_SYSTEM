"""Settings service layer - manages application settings and API keys."""
from typing import Optional, Dict, List
from sqlalchemy.orm import Session

from app.models import Setting


class SettingsService:
    """Service for managing application settings."""
    
    def get_setting(self, db: Session, key: str) -> Optional[Setting]:
        """Get a setting by key."""
        return db.query(Setting).filter(Setting.key == key).first()
    
    def get_setting_value(self, db: Session, key: str) -> Optional[str]:
        """Get just the value of a setting."""
        setting = self.get_setting(db, key)
        return setting.value if setting else None
    
    def get_all_settings(self, db: Session, include_sensitive: bool = False) -> List[Setting]:
        """Get all settings."""
        query = db.query(Setting)
        if not include_sensitive:
            query = query.filter(Setting.is_sensitive == False)
        return query.all()
    
    def get_settings_dict(self, db: Session, mask_sensitive: bool = True) -> Dict[str, str]:
        """Get all settings as a dictionary."""
        settings = db.query(Setting).all()
        result = {}
        for setting in settings:
            if mask_sensitive and setting.is_sensitive and setting.value:
                # Mask sensitive values
                result[setting.key] = "***" + setting.value[-4:] if len(setting.value) > 4 else "****"
            else:
                result[setting.key] = setting.value
        return result
    
    def set_setting(
        self,
        db: Session,
        key: str,
        value: Optional[str],
        description: Optional[str] = None,
        is_sensitive: bool = False
    ) -> Setting:
        """Create or update a setting."""
        setting = self.get_setting(db, key)
        
        if setting:
            # Update existing
            if value is not None:
                setting.value = value
            if description is not None:
                setting.description = description
            setting.is_sensitive = is_sensitive
        else:
            # Create new
            setting = Setting(
                key=key,
                value=value,
                description=description,
                is_sensitive=is_sensitive
            )
            db.add(setting)
        
        db.commit()
        db.refresh(setting)
        return setting
    
    def update_api_keys(
        self,
        db: Session,
        shopify_shop: Optional[str] = None,
        shopify_token: Optional[str] = None,
        google_translate_api_key: Optional[str] = None
    ) -> Dict[str, bool]:
        """Update API keys. Returns which keys were updated."""
        updated = {}
        
        if shopify_shop is not None:
            self.set_setting(
                db,
                "shopify_shop",
                shopify_shop,
                "Shopify shop domain (e.g., myshop.myshopify.com)",
                is_sensitive=False
            )
            updated["shopify_shop"] = True
        
        if shopify_token is not None:
            self.set_setting(
                db,
                "shopify_token",
                shopify_token,
                "Shopify Admin API access token",
                is_sensitive=True
            )
            updated["shopify_token"] = True
        
        if google_translate_api_key is not None:
            self.set_setting(
                db,
                "google_translate_api_key",
                google_translate_api_key,
                "Google Cloud Translation API key",
                is_sensitive=True
            )
            updated["google_translate_api_key"] = True
        
        return updated
    
    def delete_setting(self, db: Session, key: str) -> bool:
        """Delete a setting."""
        setting = self.get_setting(db, key)
        if setting:
            db.delete(setting)
            db.commit()
            return True
        return False
    
    def initialize_default_settings(self, db: Session):
        """Initialize default settings if they don't exist."""
        defaults = [
            ("shopify_shop", None, "Shopify shop domain (e.g., myshop.myshopify.com)", False),
            ("shopify_token", None, "Shopify Admin API access token", True),
            ("google_translate_api_key", None, "Google Cloud Translation API key", True),
            ("shopify_api_version", "2024-01", "Shopify API version", False),
        ]
        
        for key, value, description, is_sensitive in defaults:
            existing = self.get_setting(db, key)
            if not existing:
                self.set_setting(db, key, value, description, is_sensitive)


# Singleton instance
settings_service = SettingsService()
