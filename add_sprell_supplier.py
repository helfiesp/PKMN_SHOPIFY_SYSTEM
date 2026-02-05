#!/usr/bin/env python3
"""
Helper script to add Sprell.no to the supplier database
"""
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

from app.database import get_db
from app.models import SupplierWebsite

def add_sprell_supplier():
    """Add Sprell.no as a supplier website"""
    
    db = next(get_db())
    
    try:
        # Check if already exists
        existing = db.query(SupplierWebsite).filter(
            SupplierWebsite.name == "Sprell"
        ).first()
        
        if existing:
            print(f"✓ Sprell supplier already exists with ID: {existing.id}")
            print(f"  Name: {existing.name}")
            print(f"  URL: {existing.url}")
            print(f"  Active: {existing.is_active}")
            print(f"  Scan interval: {existing.scan_interval_hours} hours")
            return existing.id
        
        # Create new entry
        print("Creating new Sprell supplier entry...")
        website = SupplierWebsite(
            name="Sprell",
            url="https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon",
            scan_interval_hours=6,
            is_active=True
        )
        
        db.add(website)
        db.commit()
        db.refresh(website)
        
        print(f"\n✓ Successfully created Sprell supplier!")
        print(f"  ID: {website.id}")
        print(f"  Name: {website.name}")
        print(f"  URL: {website.url}")
        print(f"  Scan interval: {website.scan_interval_hours} hours")
        
        print(f"\nNext steps:")
        print(f"1. Test the scraper:")
        print(f"   python test_sprell_simple.py")
        print(f"\n2. Run a full scan:")
        print(f"   python suppliers/sprell.py {website.id}")
        print(f"\n3. Add to crontab (replace website_id with {website.id}):")
        print(f"   45 6,12,18,0 * * * curl -s -X POST 'http://localhost:8000/api/v1/suppliers/scan' -H 'Content-Type: application/json' -d '{{\"website_id\":{website.id}}}' >> ~/logs/sprell_api.log 2>&1")
        
        return website.id
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    website_id = add_sprell_supplier()
    sys.exit(0 if website_id else 1)
