-- Pokelageret POS — initial D1 schema
-- Covers: Shopify product cache, barcodes, purchase orders, kvitteringer (receipts),
-- margin VAT, stock dates, Snkrdunk price updater, settings/audit.

-- ============================================================================
-- Settings & audit
-- ============================================================================
CREATE TABLE IF NOT EXISTS settings (
  key            TEXT PRIMARY KEY,
  value          TEXT,
  description    TEXT,
  updated_at     INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  operation      TEXT NOT NULL,
  entity_type    TEXT,
  entity_id      TEXT,
  user_id        TEXT,
  details        TEXT,
  success        INTEGER NOT NULL DEFAULT 1,
  error_message  TEXT,
  created_at     INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);

-- ============================================================================
-- Shopify product cache
-- ============================================================================
CREATE TABLE IF NOT EXISTS products (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  shopify_id             TEXT UNIQUE NOT NULL,        -- gid://shopify/Product/...
  shopify_numeric_id     TEXT,                         -- bare numeric for REST
  title                  TEXT NOT NULL,
  handle                 TEXT,
  status                 TEXT,
  vendor                 TEXT,
  product_type           TEXT,
  collection_id          TEXT,
  is_preorder            INTEGER NOT NULL DEFAULT 0,
  stock_date             TEXT,                         -- YYYY-MM-DD metafield
  image_url              TEXT,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_products_handle ON products(handle);
CREATE INDEX IF NOT EXISTS idx_products_collection ON products(collection_id);
CREATE INDEX IF NOT EXISTS idx_products_stock_date ON products(stock_date);

CREATE TABLE IF NOT EXISTS variants (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  shopify_id             TEXT UNIQUE NOT NULL,         -- gid://shopify/ProductVariant/...
  shopify_numeric_id     TEXT,
  product_id             INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
  inventory_item_id      TEXT,                         -- gid://shopify/InventoryItem/...
  title                  TEXT,
  sku                    TEXT,
  barcode                TEXT,                         -- Shopify-side barcode (mirror)
  price                  REAL,
  compare_at_price       REAL,
  inventory_quantity     INTEGER NOT NULL DEFAULT 0,
  option_name            TEXT,
  option_value           TEXT,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_variants_product ON variants(product_id);
CREATE INDEX IF NOT EXISTS idx_variants_sku ON variants(sku);
CREATE INDEX IF NOT EXISTS idx_variants_barcode ON variants(barcode);

-- ============================================================================
-- Barcode → variant linking (local-first, syncs to Shopify variant.barcode)
-- ============================================================================
CREATE TABLE IF NOT EXISTS barcodes (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  code                   TEXT NOT NULL,                -- raw scanned value
  variant_shopify_id     TEXT NOT NULL,                -- target variant gid
  product_shopify_id     TEXT,                         -- denormalized for fast lookup
  is_primary             INTEGER NOT NULL DEFAULT 1,   -- multiple codes can map to one variant
  source                 TEXT NOT NULL DEFAULT 'manual', -- manual | scan | import
  notes                  TEXT,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  UNIQUE(code, variant_shopify_id)
);
CREATE INDEX IF NOT EXISTS idx_barcodes_code ON barcodes(code);
CREATE INDEX IF NOT EXISTS idx_barcodes_variant ON barcodes(variant_shopify_id);

-- ============================================================================
-- Purchase orders (supplier purchases — JPY-denominated, FX snapshot per PO)
-- ============================================================================
CREATE TABLE IF NOT EXISTS purchase_orders (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  reference              TEXT UNIQUE NOT NULL,         -- e.g. PO-2026-0001
  supplier               TEXT,
  order_date             TEXT NOT NULL,                -- YYYY-MM-DD
  shipping_cost_jpy      REAL NOT NULL DEFAULT 0,
  customs_cost_nok       REAL NOT NULL DEFAULT 0,
  total_jpy              REAL NOT NULL DEFAULT 0,
  total_nok              REAL NOT NULL DEFAULT 0,
  fx_rate_snapshot       REAL,                         -- JPY → NOK rate at create time
  status                 TEXT NOT NULL DEFAULT 'draft', -- draft | ordered | received | cancelled
  notes                  TEXT,
  received_at            INTEGER,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at             INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_order_id      INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
  variant_shopify_id     TEXT,
  description            TEXT NOT NULL,
  quantity               INTEGER NOT NULL,
  unit_price_jpy         REAL NOT NULL DEFAULT 0,
  weight_grams           REAL,
  received_quantity      INTEGER NOT NULL DEFAULT 0,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_po_items_po ON purchase_order_items(purchase_order_id);

-- ============================================================================
-- Kvitteringer (receipts — local POS sales, separate from Shopify orders)
-- ============================================================================
CREATE TABLE IF NOT EXISTS receipts (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_number         TEXT UNIQUE NOT NULL,         -- KVT-2026-0001
  shopify_order_id       TEXT,                         -- if pushed to Shopify
  customer_name          TEXT,
  customer_email         TEXT,
  payment_method         TEXT NOT NULL DEFAULT 'card', -- card | cash | vipps | other
  subtotal_nok           REAL NOT NULL DEFAULT 0,
  vat_total_nok          REAL NOT NULL DEFAULT 0,      -- standard 25% VAT total
  margin_vat_total_nok   REAL NOT NULL DEFAULT 0,      -- avansemoms total
  discount_nok           REAL NOT NULL DEFAULT 0,
  total_nok              REAL NOT NULL DEFAULT 0,
  cashier_id             TEXT,
  status                 TEXT NOT NULL DEFAULT 'completed', -- completed | refunded | void
  pdf_r2_key             TEXT,                         -- R2 object key
  notes                  TEXT,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_receipts_created ON receipts(created_at);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);

CREATE TABLE IF NOT EXISTS receipt_items (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  receipt_id             INTEGER NOT NULL REFERENCES receipts(id) ON DELETE CASCADE,
  variant_shopify_id     TEXT,
  barcode                TEXT,
  description            TEXT NOT NULL,
  quantity               INTEGER NOT NULL DEFAULT 1,
  unit_price_nok         REAL NOT NULL,
  vat_rate_pct           REAL NOT NULL DEFAULT 25,
  is_margin_vat          INTEGER NOT NULL DEFAULT 0,   -- if 1, vat_amount comes from margin scheme
  margin_vat_purchase_id INTEGER REFERENCES margin_vat_purchases(id),
  vat_amount_nok         REAL NOT NULL DEFAULT 0,
  line_total_nok         REAL NOT NULL,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_receipt_items_receipt ON receipt_items(receipt_id);

-- ============================================================================
-- Margin VAT (Norwegian avansemoms / brukmomsordningen)
-- ============================================================================
CREATE TABLE IF NOT EXISTS margin_vat_purchases (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  reference              TEXT UNIQUE NOT NULL,         -- MV-2026-0001
  seller                 TEXT NOT NULL,                -- private seller name
  seller_id              TEXT,                         -- e.g. fnr (sensitive — handle carefully)
  purchase_date          TEXT NOT NULL,
  total_purchase_nok     REAL NOT NULL DEFAULT 0,
  status                 TEXT NOT NULL DEFAULT 'pending', -- pending | completed | needs_reassignment
  notes                  TEXT,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at             INTEGER NOT NULL DEFAULT (unixepoch())
);

CREATE TABLE IF NOT EXISTS margin_vat_items (
  id                       INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id              INTEGER NOT NULL REFERENCES margin_vat_purchases(id) ON DELETE CASCADE,
  description              TEXT NOT NULL,
  quantity                 INTEGER NOT NULL DEFAULT 1,
  unit_purchase_price_nok  REAL NOT NULL,
  variant_shopify_id       TEXT,
  selling_price_nok        REAL,                       -- intended sale price
  margin_nok               REAL,                       -- selling - purchase
  vat_amount_nok           REAL,                       -- margin × 25/125
  effective_rate_pct       REAL,                       -- 100 × margin / (5 × selling - margin)
  bucket_rate_pct          REAL,                       -- capped at 25 for Shopify tax override
  needs_reassignment       INTEGER NOT NULL DEFAULT 0,
  sold_receipt_id          INTEGER REFERENCES receipts(id),
  sold_at                  INTEGER,
  created_at               INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_mv_items_purchase ON margin_vat_items(purchase_id);
CREATE INDEX IF NOT EXISTS idx_mv_items_variant ON margin_vat_items(variant_shopify_id);

CREATE TABLE IF NOT EXISTS margin_vat_proof_images (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id            INTEGER NOT NULL REFERENCES margin_vat_purchases(id) ON DELETE CASCADE,
  filename               TEXT NOT NULL,
  r2_key                 TEXT NOT NULL,                -- key in STORAGE bucket
  content_type           TEXT,
  file_size_bytes        INTEGER,
  uploaded_at            INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_mv_proof_purchase ON margin_vat_proof_images(purchase_id);

-- ============================================================================
-- Stock dates — track Shopify metafield custom.stock_date for clearing
-- ============================================================================
CREATE TABLE IF NOT EXISTS stock_date_log (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  product_shopify_id     TEXT NOT NULL,
  old_stock_date         TEXT,
  new_stock_date         TEXT,
  action                 TEXT NOT NULL,                -- set | clear | auto_clear
  triggered_by           TEXT NOT NULL DEFAULT 'manual', -- manual | cron | sale
  created_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_stock_date_log_product ON stock_date_log(product_shopify_id);

-- ============================================================================
-- Snkrdunk price updater — Japanese TCG market price → Shopify
-- ============================================================================
CREATE TABLE IF NOT EXISTS snkrdunk_mappings (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  snkrdunk_key           TEXT UNIQUE NOT NULL,         -- stable key (id or hash)
  snkrdunk_id            TEXT,
  series_en              TEXT,
  name_short             TEXT,
  type_en                TEXT,                         -- box | pack | etb | other
  has_shrink_wrap        INTEGER NOT NULL DEFAULT 1,
  product_shopify_id     TEXT,
  variant_shopify_id     TEXT,                         -- optional: pin to single variant
  packs_per_box          INTEGER,
  disabled               INTEGER NOT NULL DEFAULT 0,
  notes                  TEXT,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch()),
  updated_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_snkr_map_product ON snkrdunk_mappings(product_shopify_id);

CREATE TABLE IF NOT EXISTS snkrdunk_scan_logs (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  status                 TEXT NOT NULL,                -- running | success | failed
  trigger                TEXT NOT NULL DEFAULT 'cron', -- cron | manual
  total_items            INTEGER,
  matched_items          INTEGER,
  updated_items          INTEGER,
  fx_rate_jpy_nok        REAL,
  started_at             INTEGER NOT NULL,
  completed_at           INTEGER,
  duration_ms            INTEGER,
  email_sent             INTEGER NOT NULL DEFAULT 0,
  error_message          TEXT,
  output                 TEXT
);
CREATE INDEX IF NOT EXISTS idx_snkr_scan_status ON snkrdunk_scan_logs(status);
CREATE INDEX IF NOT EXISTS idx_snkr_scan_started ON snkrdunk_scan_logs(started_at);

CREATE TABLE IF NOT EXISTS snkrdunk_price_history (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  scan_log_id            INTEGER NOT NULL REFERENCES snkrdunk_scan_logs(id) ON DELETE CASCADE,
  snkrdunk_key           TEXT NOT NULL,
  price_jpy              REAL NOT NULL,
  recorded_at            INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_snkr_history_key ON snkrdunk_price_history(snkrdunk_key);

CREATE TABLE IF NOT EXISTS price_change_logs (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_shopify_id     TEXT NOT NULL,
  product_shopify_id     TEXT,
  old_price              REAL,
  new_price              REAL,
  change_type            TEXT NOT NULL,                -- snkrdunk | manual | competitor
  source                 TEXT,                         -- e.g. snkrdunk_key
  notes                  TEXT,
  applied                INTEGER NOT NULL DEFAULT 1,
  created_at             INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX IF NOT EXISTS idx_price_log_variant ON price_change_logs(variant_shopify_id);
CREATE INDEX IF NOT EXISTS idx_price_log_created ON price_change_logs(created_at);

CREATE TABLE IF NOT EXISTS translations (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  source_text            TEXT UNIQUE NOT NULL,
  translated_text        TEXT NOT NULL,
  source_lang            TEXT NOT NULL DEFAULT 'ja',
  target_lang            TEXT NOT NULL DEFAULT 'en',
  created_at             INTEGER NOT NULL DEFAULT (unixepoch())
);

-- ============================================================================
-- Counters for human-friendly references (PO-, KVT-, MV-)
-- ============================================================================
CREATE TABLE IF NOT EXISTS sequence_counters (
  name                   TEXT PRIMARY KEY,
  current_value          INTEGER NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO sequence_counters (name, current_value) VALUES ('purchase_order', 0);
INSERT OR IGNORE INTO sequence_counters (name, current_value) VALUES ('receipt', 0);
INSERT OR IGNORE INTO sequence_counters (name, current_value) VALUES ('margin_vat', 0);
