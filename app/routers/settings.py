"""Settings and configuration router."""
from typing import List, Dict
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import (
    SettingResponse,
    SettingCreate,
    SettingUpdate,
    SettingUpdateRequest
)
from app.services.settings_service import settings_service

router = APIRouter()


@router.get("/", response_model=List[SettingResponse])
async def get_all_settings(
    include_sensitive: bool = False,
    db: Session = Depends(get_db)
):
    """
    Get all settings.
    Sensitive values will be masked unless include_sensitive=True.
    """
    settings = settings_service.get_all_settings(db, include_sensitive=include_sensitive)
    
    # Mask sensitive values
    result = []
    for setting in settings:
        setting_dict = {
            "id": setting.id,
            "key": setting.key,
            "value": setting.value,
            "description": setting.description,
            "is_sensitive": setting.is_sensitive,
            "created_at": setting.created_at,
            "updated_at": setting.updated_at
        }
        
        # Mask sensitive values
        if setting.is_sensitive and setting.value and not include_sensitive:
            setting_dict["value"] = "***" + setting.value[-4:] if len(setting.value) > 4 else "****"
        
        result.append(setting_dict)
    
    return result


@router.get("/dict", response_model=Dict[str, str])
async def get_settings_dict(
    mask_sensitive: bool = True,
    db: Session = Depends(get_db)
):
    """Get all settings as a key-value dictionary."""
    return settings_service.get_settings_dict(db, mask_sensitive=mask_sensitive)


@router.get("/{key}", response_model=SettingResponse)
async def get_setting(
    key: str,
    db: Session = Depends(get_db)
):
    """Get a specific setting by key."""
    setting = settings_service.get_setting(db, key)
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    
    # Mask sensitive value
    setting_dict = {
        "id": setting.id,
        "key": setting.key,
        "value": setting.value,
        "description": setting.description,
        "is_sensitive": setting.is_sensitive,
        "created_at": setting.created_at,
        "updated_at": setting.updated_at
    }
    
    if setting.is_sensitive and setting.value:
        setting_dict["value"] = "***" + setting.value[-4:] if len(setting.value) > 4 else "****"
    
    return setting_dict


@router.post("/", response_model=SettingResponse)
async def create_setting(
    setting: SettingCreate,
    db: Session = Depends(get_db)
):
    """Create or update a setting."""
    result = settings_service.set_setting(
        db,
        key=setting.key,
        value=setting.value,
        description=setting.description,
        is_sensitive=setting.is_sensitive
    )
    return result


@router.put("/{key}", response_model=SettingResponse)
async def update_setting(
    key: str,
    update: SettingUpdate,
    db: Session = Depends(get_db)
):
    """Update a setting."""
    setting = settings_service.get_setting(db, key)
    if not setting:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    
    result = settings_service.set_setting(
        db,
        key=key,
        value=update.value,
        description=update.description,
        is_sensitive=setting.is_sensitive
    )
    return result


@router.put("/api-keys/update")
async def update_api_keys(
    request: SettingUpdateRequest,
    db: Session = Depends(get_db)
):
    """Update API keys (Shopify and Google Translate)."""
    updated = settings_service.update_api_keys(
        db,
        shopify_shop=request.shopify_shop,
        shopify_token=request.shopify_token,
        google_translate_api_key=request.google_translate_api_key
    )
    
    return {
        "message": "API keys updated successfully",
        "updated": updated
    }


@router.delete("/{key}")
async def delete_setting(
    key: str,
    db: Session = Depends(get_db)
):
    """Delete a setting."""
    success = settings_service.delete_setting(db, key)
    if not success:
        raise HTTPException(status_code=404, detail=f"Setting '{key}' not found")
    
    return {"message": f"Setting '{key}' deleted successfully"}


@router.post("/initialize")
async def initialize_defaults(db: Session = Depends(get_db)):
    """Initialize default settings."""
    settings_service.initialize_default_settings(db)
    return {"message": "Default settings initialized"}
