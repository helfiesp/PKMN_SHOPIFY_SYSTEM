"""Migration script: Create margin VAT tables (purchase order model).

Run this on any database (local or remote) to set up the new tables.
Safe to run multiple times — uses IF NOT EXISTS.

Usage:
    python migrate_margin_vat.py                  # Uses default shopify_app.db
    python migrate_margin_vat.py /path/to/db.db   # Specify a different database
"""
import sqlite3
import sys

db_path = sys.argv[1] if len(sys.argv) > 1 else "shopify_app.db"
print(f"Migrating: {db_path}")

conn = sqlite3.connect(db_path)

# Drop old tables if they exist (from the previous single-table model)
print("Dropping old tables (if any)...")
conn.execute("DROP TABLE IF EXISTS margin_vat_proof_images")
conn.execute("DROP TABLE IF EXISTS margin_vat_products")
conn.execute("DROP TABLE IF EXISTS margin_vat_items")
conn.execute("DROP TABLE IF EXISTS margin_vat_purchases")

# Create new tables
print("Creating margin_vat_purchases...")
conn.execute("""
CREATE TABLE IF NOT EXISTS margin_vat_purchases (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    seller VARCHAR(500),
    purchase_date DATETIME,
    notes TEXT,
    status VARCHAR(50) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
)
""")

print("Creating margin_vat_items...")
conn.execute("""
CREATE TABLE IF NOT EXISTS margin_vat_items (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES margin_vat_purchases(id),
    description VARCHAR(500) NOT NULL,
    quantity INTEGER NOT NULL DEFAULT 1,
    unit_price_nok FLOAT NOT NULL,
    product_shopify_id VARCHAR(255),
    variant_shopify_id VARCHAR(255),
    product_title VARCHAR(500),
    variant_title VARCHAR(500),
    sku VARCHAR(255),
    image_url VARCHAR(1000),
    selling_price_nok FLOAT,
    margin_nok FLOAT,
    vat_amount_nok FLOAT,
    effective_rate_pct FLOAT,
    bucket_rate_pct INTEGER,
    tax_collection_id VARCHAR(255),
    tax_collection_name VARCHAR(100),
    needs_reassignment BOOLEAN DEFAULT 0,
    status VARCHAR(50) DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME
)
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_mvi_purchase ON margin_vat_items(purchase_id)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_mvi_product ON margin_vat_items(product_shopify_id)")
conn.execute("CREATE INDEX IF NOT EXISTS idx_mvi_bucket_status ON margin_vat_items(bucket_rate_pct, status)")

print("Creating margin_vat_proof_images...")
conn.execute("""
CREATE TABLE IF NOT EXISTS margin_vat_proof_images (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    purchase_id INTEGER NOT NULL REFERENCES margin_vat_purchases(id),
    filename VARCHAR(500) NOT NULL,
    stored_filename VARCHAR(500) NOT NULL,
    file_path VARCHAR(1000) NOT NULL,
    content_type VARCHAR(100),
    file_size_bytes INTEGER,
    description VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.execute("CREATE INDEX IF NOT EXISTS idx_mvpi_purchase ON margin_vat_proof_images(purchase_id)")

conn.commit()
conn.close()

print("Done! All margin VAT tables created.")
