"""Mapping service - handles SNKRDUNK mappings and translations."""
import requests
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models import SnkrdunkMapping, Translation
from app.schemas import SnkrdunkMappingCreate, TranslationCreate
from app.config import settings


class MappingService:
    """Service for mappings and translations."""
    
    # Mappings
    
    def get_mappings(
        self,
        db: Session,
        disabled: Optional[bool] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[SnkrdunkMapping]:
        """Get SNKRDUNK mappings."""
        query = db.query(SnkrdunkMapping)
        
        if disabled is not None:
            query = query.filter(SnkrdunkMapping.disabled == disabled)
        
        return query.offset(skip).limit(limit).all()
    
    def get_mapping_by_id(self, db: Session, mapping_id: int) -> Optional[SnkrdunkMapping]:
        """Get mapping by ID."""
        return db.query(SnkrdunkMapping).filter(SnkrdunkMapping.id == mapping_id).first()
    
    def get_mapping_by_key(self, db: Session, snkrdunk_key: str) -> Optional[SnkrdunkMapping]:
        """Get mapping by SNKRDUNK key."""
        return db.query(SnkrdunkMapping).filter(
            SnkrdunkMapping.snkrdunk_key == snkrdunk_key
        ).first()
    
    def create_mapping(
        self,
        db: Session,
        mapping: SnkrdunkMappingCreate
    ) -> SnkrdunkMapping:
        """Create a new mapping."""
        # Check if key already exists
        existing = self.get_mapping_by_key(db, mapping.snkrdunk_key)
        if existing:
            raise ValueError(f"Mapping with key '{mapping.snkrdunk_key}' already exists")
        
        db_mapping = SnkrdunkMapping(**mapping.model_dump())
        db.add(db_mapping)
        db.commit()
        db.refresh(db_mapping)
        
        return db_mapping
    
    def update_mapping(
        self,
        db: Session,
        mapping_id: int,
        mapping_data: SnkrdunkMappingCreate
    ) -> Optional[SnkrdunkMapping]:
        """Update a mapping."""
        mapping = self.get_mapping_by_id(db, mapping_id)
        if not mapping:
            return None
        
        for key, value in mapping_data.model_dump().items():
            setattr(mapping, key, value)
        
        db.commit()
        db.refresh(mapping)
        
        return mapping
    
    def delete_mapping(self, db: Session, mapping_id: int) -> bool:
        """Delete a mapping."""
        mapping = self.get_mapping_by_id(db, mapping_id)
        if mapping:
            db.delete(mapping)
            db.commit()
            return True
        return False
    
    # Translations
    
    def get_translations(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100
    ) -> List[Translation]:
        """Get translations."""
        return db.query(Translation).offset(skip).limit(limit).all()
    
    def get_translation_by_text(self, db: Session, japanese_text: str) -> Optional[Translation]:
        """Get translation by Japanese text."""
        return db.query(Translation).filter(
            Translation.japanese_text == japanese_text
        ).first()
    
    def create_translation(
        self,
        db: Session,
        translation: TranslationCreate
    ) -> Translation:
        """Create a new translation."""
        existing = self.get_translation_by_text(db, translation.japanese_text)
        if existing:
            return existing
        
        db_translation = Translation(**translation.model_dump())
        db.add(db_translation)
        db.commit()
        db.refresh(db_translation)
        
        return db_translation
    
    async def batch_translate(
        self,
        db: Session,
        texts: List[str]
    ) -> List[dict]:
        """Batch translate Japanese texts to English."""
        results = []
        
        for text in texts:
            # Check cache
            cached = self.get_translation_by_text(db, text)
            if cached:
                results.append({
                    "japanese": text,
                    "english": cached.english_text,
                    "cached": True
                })
                continue
            
            # Call Google Translate API
            try:
                english = await self._call_google_translate(text)
                
                # Save to cache
                translation = Translation(
                    japanese_text=text,
                    english_text=english
                )
                db.add(translation)
                
                results.append({
                    "japanese": text,
                    "english": english,
                    "cached": False
                })
            except Exception as e:
                results.append({
                    "japanese": text,
                    "english": None,
                    "error": str(e)
                })
        
        db.commit()
        return results
    
    async def _call_google_translate(self, text: str) -> str:
        """Call Google Translate API."""
        if not settings.google_translate_api_key:
            raise ValueError("Google Translate API key not configured")
        
        url = "https://translation.googleapis.com/language/translate/v2"
        params = {
            "q": text,
            "source": "ja",
            "target": "en",
            "key": settings.google_translate_api_key
        }
        
        response = requests.post(url, data=params, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        translated = data["data"]["translations"][0]["translatedText"]
        
        return translated


mapping_service = MappingService()
