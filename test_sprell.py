#!/usr/bin/env python3
"""
Test script for sprell.no scraper
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent))

from suppliers.sprell import SprellScraper
from app.database import get_db
from app.models import SupplierWebsite

def test_scraper():
    """Test the Sprell scraper"""
    
    # Get or create website entry
    db = next(get_db())
    
    website = db.query(SupplierWebsite).filter(
        SupplierWebsite.name == "Sprell"
    ).first()
    
    if not website:
        print("Creating Sprell website entry...")
        website = SupplierWebsite(
            name="Sprell",
            url="https://www.sprell.no/category/leker/spill-og-puslespill/fotballkort-og-pokemonkort?brand=pok%25C3%25A9mon",
            scan_interval_hours=6,
            is_active=True
        )
        db.add(website)
        db.commit()
        db.refresh(website)
        print(f"Created website with ID: {website.id}")
    else:
        print(f"Using existing website with ID: {website.id}")
    
    db.close()
    
    # Run the scraper
    print(f"\nStarting scraper test for Sprell.no...")
    print(f"URL: {website.url}")
    print("="*60)
    
    with SprellScraper(website.id) as scraper:
        result = scraper.run()
        
        print(f"\n{'='*60}")
        print(f"Sprell.no Scan Results")
        print(f"{'='*60}")
        print(f"Status: {result['status']}")
        print(f"Products found: {result['products_found']}")
        print(f"New products: {result['new_products']}")
        print(f"Restocked: {result['restocked_products']}")
        if result['error_message']:
            print(f"Error: {result['error_message']}")
        print(f"{'='*60}")
        
        if result['status'] == 'success':
            print("\n✓ Scraper test completed successfully!")
            return 0
        else:
            print("\n✗ Scraper test failed!")
            return 1

if __name__ == "__main__":
    sys.exit(test_scraper())
