"""SNKRDUNK service layer - handles SNKRDUNK API and matching logic."""
import requests
import html
import time
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime, timezone, timedelta

from app.models import SnkrdunkCache, SnkrdunkMapping, Translation, Product, Variant, SnkrdunkPriceHistory
from app.config import settings


class SnkrdunkService:
    """Service for SNKRDUNK operations."""
    
    SNKRDUNK_API_URL = "https://snkrdunk.com/v1/apparel/market/category"
    GOOGLE_TRANSLATE_V2_URL = "https://translation.googleapis.com/language/translate/v2"
    
    # Required headers to avoid 403 Forbidden
    SNKRDUNK_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://snkrdunk.com/",
    }
    
    async def fetch_and_cache_snkrdunk_data(
        self,
        db: Session,
        pages: List[int],
        force_refresh: bool = False
    ) -> dict:
        """
        Fetch SNKRDUNK data and cache in database.
        
        When force_refresh=True, ALWAYS fetches fresh data from API and updates cache.
        When force_refresh=False, uses cache if available and not expired.
        """
        cache_ttl = timedelta(hours=settings.snkrdunk_cache_ttl_hours)
        now = datetime.now(timezone.utc)
        
        all_items = []
        
        for page in pages:
            should_fetch = force_refresh
            
            # If not forcing refresh, check if cache is valid
            if not force_refresh:
                cached = db.query(SnkrdunkCache).filter(
                    SnkrdunkCache.page == page,
                    SnkrdunkCache.brand_id == "pokemon",
                    SnkrdunkCache.expires_at > now
                ).first()
                
                if cached:
                    # Use cached data
                    apparels = cached.response_data.get("apparels", [])
                    all_items.extend([x for x in apparels if isinstance(x, dict) and "id" in x])
                    continue
                else:
                    # Cache expired or doesn't exist, need to fetch
                    should_fetch = True
            
            # Fetch from API (either forced or cache miss/expired)
            if should_fetch:
                params = {
                    "page": page,
                    "perPage": 25,
                    "order": "popular",
                    "apparelCategoryId": 14,
                    "apparelSubCategoryId": 0,
                    "brandId": "pokemon",
                    "departmentName": "hobby"
                }
                
                response = requests.get(
                    self.SNKRDUNK_API_URL, 
                    params=params, 
                    headers=self.SNKRDUNK_HEADERS,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                
                # Update or create cache entry
                cache_entry = db.query(SnkrdunkCache).filter(
                    SnkrdunkCache.page == page,
                    SnkrdunkCache.brand_id == "pokemon"
                ).first()
                
                if cache_entry:
                    cache_entry.response_data = data
                    cache_entry.created_at = now
                    cache_entry.expires_at = now + cache_ttl
                else:
                    cache_entry = SnkrdunkCache(
                        page=page,
                        category_id=14,
                        brand_id="pokemon",
                        response_data=data,
                        created_at=now,
                        expires_at=now + cache_ttl
                    )
                    db.add(cache_entry)
                
                # Extract items from FRESH API response
                apparels = data.get("apparels", [])
                all_items.extend([x for x in apparels if isinstance(x, dict) and "id" in x])
        
        db.commit()
        
        # Update the updated_at timestamp on all SnkrdunkMapping records to track when SNKRDUNK was last fetched
        db.query(SnkrdunkMapping).update(
            {SnkrdunkMapping.updated_at: now},
            synchronize_session=False
        )
        db.commit()
        
        # Price history is now handled by the router with proper scan log linking
        
        # Translate all product names (in background)
        if all_items:
            for item in all_items:
                name = item.get("name", "").strip()
                if name:
                    # This will cache translations for later use
                    self.translate_text(db, name)
        
        return {
            "total_items": len(all_items),
            "pages_fetched": len(pages),
            "cached_at": now.isoformat(),
            "items": all_items
        }
    
    async def match_and_calculate_prices(
        self,
        db: Session,
        collection_id: str
    ) -> dict:
        """
        Match SNKRDUNK products with Shopify and calculate prices.
        
        Replicates the matching and pricing logic from snkrdunk.py.
        This is a stub - full implementation would include:
        - FX rate fetching
        - Product matching algorithm
        - Price calculation with margins
        - Mapping table updates
        """
        # TODO: Implement full matching logic
        # 1. Get cached SNKRDUNK data
        # 2. Get Shopify products for collection
        # 3. Translate Japanese names (using Translation cache)
        # 4. Match products using similarity algorithm
        # 5. Calculate prices with FX rates and margins
        # 6. Update SnkrdunkMapping table
        
        return {
            "total_items": 0,
            "kept_items": 0,
            "skipped_items": 0,
            "new_mappings": 0,
            "results": []
        }
    
    def get_cache_status(self, db: Session) -> dict:
        """Get SNKRDUNK cache status."""
        now = datetime.now(timezone.utc)
        
        total_cached = db.query(SnkrdunkCache).count()
        valid_cached = db.query(SnkrdunkCache).filter(
            SnkrdunkCache.expires_at > now
        ).count()
        
        return {
            "total_cached_pages": total_cached,
            "valid_cached_pages": valid_cached,
            "expired_pages": total_cached - valid_cached
        }
    
    def _should_include_product(self, name: str) -> bool:
        """
        Determine if a product should be included based on its name.
        
        Rules:
        - Must end with "Box" (case-insensitive)
        - Must not end with "Pack"
        - Must not contain "[No shrink]" or similar variations
        - Must not contain "Deluxe" (case-insensitive)
        """
        if not name:
            return False
        
        name_lower = name.lower()
        
        # Must end with "Box"
        if not name_lower.strip().endswith("box"):
            return False
        
        # Must not end with "Pack"
        if name_lower.strip().endswith("pack"):
            return False
        
        # Must not contain [No shrink] or similar
        if "[no shrink" in name_lower:
            return False
        if "no shrink wrap" in name_lower:
            return False
        
        # Must not contain "Deluxe"
        if "deluxe" in name_lower:
            return False
        
        return True
    
    def _extract_quoted_name(self, name: str) -> str:
        """
        Extract text within quotes from product name.
        
        Example:
            'Pokemon Card Game MEGA Expansion Pack "Inferno X" Box' -> 'Inferno X'
        
        If no quotes found, return empty string (will be filtered out).
        """
        if not name:
            return ""
        
        # Try to find text within double quotes
        match = re.search(r'"([^"]+)"', name)
        if match:
            return match.group(1).strip()
        
        # Try single quotes
        match = re.search(r"'([^']+)'", name)
        if match:
            return match.group(1).strip()
        
        # No quotes found, return empty string to filter out
        return ""
    
    def translate_text(self, db: Session, text: str, source: str = "ja", target: str = "en") -> str:
        """Translate text using Google Translate API with database caching."""
        text = (text or "").strip()
        if not text:
            return ""
        
        # Only support JA to EN for now (matches Translation model)
        if source != "ja" or target != "en":
            return text
        
        # Check translation cache
        cached = db.query(Translation).filter(
            Translation.japanese_text == text
        ).first()
        
        if cached:
            return cached.english_text
        
        # Get API key from settings
        api_key = settings.get_google_api_key()
        if not api_key:
            # Return original text if no API key
            return text
        
        # Translate via Google API
        payload = {
            "q": text,
            "source": source,
            "target": target,
            "format": "text",
            "key": api_key
        }
        
        translated = ""
        for attempt in range(1, 4):
            try:
                response = requests.post(
                    self.GOOGLE_TRANSLATE_V2_URL,
                    data=payload,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()
                translated_raw = data.get("data", {}).get("translations", [{}])[0].get("translatedText", "")
                translated = html.unescape((translated_raw or "").strip())
                break
            except Exception:
                time.sleep(0.6 * attempt)
        
        if not translated:
            translated = text
        
        # Cache the translation
        translation = Translation(
            japanese_text=text,
            english_text=translated,
            created_at=datetime.now(timezone.utc)
        )
        db.add(translation)
        db.commit()
        
        # Rate limit
        time.sleep(0.15)
        
        return translated
    
    def get_cached_products(self, db: Session, include_expired: bool = False, translate: bool = True, scan_log_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get all cached SNKRDUNK products with normalized fields and translations."""
        now = datetime.now(timezone.utc)
        
        query = db.query(SnkrdunkCache)
        if not include_expired:
            query = query.filter(SnkrdunkCache.expires_at > now)
        
        caches = query.all()
        
        # Pre-load all translations in one query if translate=True
        existing_translations = {}
        if translate:
            translations = db.query(Translation).all()
            existing_translations = {t.japanese_text: t.english_text for t in translations}
        
        # Get price changes comparing selected scan vs previous scan
        from app.models import SnkrdunkScanLog, SnkrdunkPriceHistory
        price_changes = {}
        try:
            if scan_log_id:
                # User selected a specific scan - compare it against the previous one
                all_scans = db.query(SnkrdunkScanLog).order_by(
                    SnkrdunkScanLog.created_at.desc()
                ).all()
                
                # Find the selected scan's position
                selected_index = None
                for i, scan in enumerate(all_scans):
                    if scan.id == scan_log_id:
                        selected_index = i
                        break
                
                if selected_index is not None and selected_index < len(all_scans) - 1:
                    current_scan = all_scans[selected_index]
                    previous_scan = all_scans[selected_index + 1]
                else:
                    # No previous scan available
                    current_scan = None
                    previous_scan = None
            else:
                # No scan selected - use the latest two scans
                latest_scans = db.query(SnkrdunkScanLog).order_by(
                    SnkrdunkScanLog.created_at.desc()
                ).limit(2).all()
                
                if len(latest_scans) >= 2:
                    current_scan = latest_scans[0]
                    previous_scan = latest_scans[1]
                else:
                    current_scan = None
                    previous_scan = None
            
            if current_scan and previous_scan:
                
                # Get prices from both scans
                current_prices = {
                    str(p.snkrdunk_key): p.price_jpy 
                    for p in db.query(SnkrdunkPriceHistory).filter(
                        SnkrdunkPriceHistory.scan_log_id == current_scan.id
                    ).all()
                }
                
                previous_prices = {
                    str(p.snkrdunk_key): p.price_jpy 
                    for p in db.query(SnkrdunkPriceHistory).filter(
                        SnkrdunkPriceHistory.scan_log_id == previous_scan.id
                    ).all()
                }
                
                # Calculate changes
                for product_id, current_price in current_prices.items():
                    if product_id in previous_prices and current_price and previous_prices[product_id]:
                        change = float(current_price) - float(previous_prices[product_id])
                        if change != 0:
                            price_changes[product_id] = change
        except Exception as e:
            print(f"Warning: Failed to calculate price changes: {str(e)}")
        
        all_items = []
        for cache in caches:
            apparels = cache.response_data.get("apparels", [])
            for item in apparels:
                if isinstance(item, dict) and "id" in item:
                    name_ja = item.get("name", "")
                    
                    # Filter: Only include products that end with "Box" and meet criteria
                    if not self._should_include_product(name_ja):
                        continue
                    
                    # Extract quoted name for display
                    extracted_name = self._extract_quoted_name(name_ja)
                    
                    # Skip products without quoted names (generic descriptions)
                    if not extracted_name:
                        continue
                    
                    product_id = str(item.get("id"))
                    
                    # Normalize field names for frontend compatibility
                    normalized_item = {
                        "id": item.get("id"),
                        "name": name_ja,  # Keep full original name
                        "nameEn": extracted_name,  # Use extracted name, will be replaced by translation if available
                        "minPriceJpy": item.get("minPrice"),
                        "maxPriceJpy": item.get("maxPrice"),
                        "regularPrice": item.get("regularPrice"),
                        "brand": item.get("brands", [{}])[0] if item.get("brands") else None,
                        "last_price_updated": cache.created_at.isoformat() if cache.created_at else None,
                        "price_change": price_changes.get(product_id, 0),  # Add price change
                        "_cached_at": cache.created_at.isoformat() if cache.created_at else None,
                        "_page": cache.page,
                        "_raw": item  # Keep original data
                    }
                    
                    # Use pre-loaded translation if available, otherwise use extracted name
                    # (translations happen in background fetch, not on every GET)
                    if translate and name_ja:
                        translated = existing_translations.get(name_ja, "")
                        if translated:
                            # If we have a translation, also extract quoted text from it
                            normalized_item["nameEn"] = self._extract_quoted_name(translated)
                        # else: keep the extracted_name from original
                    
                    all_items.append(normalized_item)
        
        return all_items
    
    def clear_cache(self, db: Session):
        """Clear all SNKRDUNK cache."""
        db.query(SnkrdunkCache).delete()
        db.commit()


snkrdunk_service = SnkrdunkService()
