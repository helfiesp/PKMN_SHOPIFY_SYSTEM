"""Translation operations router."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime, timezone

from app.database import get_db
from app.models import Translation

router = APIRouter()


class TranslationCreate(BaseModel):
    japanese_text: str
    english_text: str


class TranslationResponse(BaseModel):
    id: int
    japanese_text: str
    english_text: str
    created_at: datetime
    
    class Config:
        from_attributes = True


@router.post("/", response_model=TranslationResponse)
async def create_or_update_translation(
    translation: TranslationCreate,
    db: Session = Depends(get_db)
):
    """Create or update a translation."""
    # Check if translation already exists
    existing = db.query(Translation).filter(
        Translation.japanese_text == translation.japanese_text
    ).first()
    
    if existing:
        # Update existing translation
        existing.english_text = translation.english_text
        existing.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Create new translation
        new_translation = Translation(
            japanese_text=translation.japanese_text,
            english_text=translation.english_text,
            created_at=datetime.now(timezone.utc)
        )
        db.add(new_translation)
        db.commit()
        db.refresh(new_translation)
        return new_translation


@router.get("/", response_model=list[TranslationResponse])
async def get_all_translations(
    limit: int = 1000,
    db: Session = Depends(get_db)
):
    """Get all translations."""
    translations = db.query(Translation).limit(limit).all()
    return translations


@router.get("/{translation_id}", response_model=TranslationResponse)
async def get_translation(
    translation_id: int,
    db: Session = Depends(get_db)
):
    """Get a specific translation by ID."""
    translation = db.query(Translation).filter(Translation.id == translation_id).first()
    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")
    return translation


@router.delete("/{translation_id}")
async def delete_translation(
    translation_id: int,
    db: Session = Depends(get_db)
):
    """Delete a translation."""
    translation = db.query(Translation).filter(Translation.id == translation_id).first()
    if not translation:
        raise HTTPException(status_code=404, detail="Translation not found")
    
    db.delete(translation)
    db.commit()
    return {"message": "Translation deleted successfully"}
