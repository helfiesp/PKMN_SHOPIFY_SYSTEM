"""Mappings and translations router."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.database import get_db
from app.schemas import (
    SnkrdunkMappingResponse,
    SnkrdunkMappingCreate,
    TranslationResponse,
    TranslationCreate
)
from app.services import mapping_service
from app.services.history_service import HistoryService

router = APIRouter()
history_service = HistoryService()


def _enrich_mapping_with_price_history(mapping, db: Session):
    """Add price history information to a mapping."""
    last_updated = history_service.get_snkrdunk_last_updated(db, mapping.snkrdunk_key)
    if last_updated:
        mapping.last_price_updated = datetime.fromisoformat(last_updated)
    return mapping


# ============================================================================
# SNKRDUNK Mappings
# ============================================================================

@router.get("/snkrdunk", response_model=List[SnkrdunkMappingResponse])
async def list_snkrdunk_mappings(
    disabled: Optional[bool] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all SNKRDUNK to Shopify mappings with price update timestamps."""
    mappings = mapping_service.get_mappings(
        db=db,
        disabled=disabled,
        skip=skip,
        limit=limit
    )
    # Enrich with price history
    return [_enrich_mapping_with_price_history(m, db) for m in mappings]


@router.get("/snkrdunk/{mapping_id}", response_model=SnkrdunkMappingResponse)
async def get_snkrdunk_mapping(
    mapping_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific mapping with price update timestamp."""
    mapping = mapping_service.get_mapping_by_id(db=db, mapping_id=mapping_id)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return _enrich_mapping_with_price_history(mapping, db)


@router.post("/snkrdunk", response_model=SnkrdunkMappingResponse)
async def create_snkrdunk_mapping(
    mapping: SnkrdunkMappingCreate,
    db: Session = Depends(get_db)
):
    """Create a new SNKRDUNK to Shopify mapping."""
    try:
        new_mapping = mapping_service.create_mapping(db=db, mapping=mapping)
        return _enrich_mapping_with_price_history(new_mapping, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/snkrdunk/{mapping_id}", response_model=SnkrdunkMappingResponse)
async def update_snkrdunk_mapping(
    mapping_id: int,
    mapping: SnkrdunkMappingCreate,
    db: Session = Depends(get_db)
):
    """Update an existing mapping."""
    updated = mapping_service.update_mapping(
        db=db,
        mapping_id=mapping_id,
        mapping_data=mapping
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return _enrich_mapping_with_price_history(updated, db)


@router.delete("/snkrdunk/{mapping_id}")
async def delete_snkrdunk_mapping(
    mapping_id: int,
    db: Session = Depends(get_db)
):
    """Delete a mapping."""
    success = mapping_service.delete_mapping(db=db, mapping_id=mapping_id)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"message": "Mapping deleted successfully"}


@router.get("/snkrdunk/search/{snkrdunk_key}", response_model=SnkrdunkMappingResponse)
async def search_mapping_by_key(
    snkrdunk_key: str,
    db: Session = Depends(get_db)
):
    """Search for a mapping by SNKRDUNK key."""
    mapping = mapping_service.get_mapping_by_key(db=db, snkrdunk_key=snkrdunk_key)
    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return mapping


# ============================================================================
# Translations
# ============================================================================

@router.get("/translations", response_model=List[TranslationResponse])
async def list_translations(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """List all translations."""
    translations = mapping_service.get_translations(
        db=db,
        skip=skip,
        limit=limit
    )
    return translations


@router.post("/translations", response_model=TranslationResponse)
async def create_translation(
    translation: TranslationCreate,
    db: Session = Depends(get_db)
):
    """Create a new translation."""
    new_translation = mapping_service.create_translation(
        db=db,
        translation=translation
    )
    return new_translation


@router.post("/translations/batch")
async def batch_translate(
    texts: List[str],
    db: Session = Depends(get_db)
):
    """
    Translate multiple Japanese texts to English.
    Uses cache when available, calls Google Translate API for new texts.
    """
    try:
        translations = await mapping_service.batch_translate(
            db=db,
            texts=texts
        )
        return {"translations": translations}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/translations/search")
async def search_translation(
    japanese_text: str,
    db: Session = Depends(get_db)
):
    """Search for a translation by Japanese text."""
    translation = mapping_service.get_translation_by_text(
        db=db,
        japanese_text=japanese_text
    )
    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")
    return translation
