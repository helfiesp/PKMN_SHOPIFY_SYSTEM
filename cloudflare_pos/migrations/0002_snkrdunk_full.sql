-- Snkrdunk full port — adds DB-backed cache that mirrors the Python
-- SnkrdunkCache table exactly: keyed on (page, brand_id), where
--   brand_id = 'pokemon' → category page (page = page number)
--   brand_id = 'manual'  → individual product (page = product id)

CREATE TABLE IF NOT EXISTS snkrdunk_cache (
  page          INTEGER NOT NULL,
  brand_id      TEXT NOT NULL,
  category_id   INTEGER,
  response_data TEXT NOT NULL,        -- JSON-encoded {apparels: [...]}
  created_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  expires_at    INTEGER,
  PRIMARY KEY (page, brand_id)
);
CREATE INDEX IF NOT EXISTS idx_snk_cache_brand ON snkrdunk_cache(brand_id);
CREATE INDEX IF NOT EXISTS idx_snk_cache_expires ON snkrdunk_cache(expires_at);

-- Default Snkrdunk settings (mirror SNK_SETTING_KEYS in the Python router).
INSERT OR IGNORE INTO settings (key, value, description) VALUES
  ('snk_shipping_jpy',      '500',   'Shipping cost in JPY'),
  ('snk_margin_pct',        '20',    'Minimum margin percentage'),
  ('snk_pack_markup_pct',   '10',    'Pack price markup over box per-unit price (%)'),
  ('snk_auto_update',       'false', 'Auto-update prices on Shopify after fetch'),
  ('snk_max_pages',         '20',    'Max pages to fetch from SNKRDUNK (25 products/page)'),
  ('snk_last_jpy_nok_rate', '0.063', 'Last fetched JPY→NOK rate (auto-updated, read-only)'),
  ('snk_cache_ttl_hours',   '6',     'Cache TTL for snkrdunk_cache rows'),
  ('email_notifications_enabled', 'false', 'Toggle Resend email digest after auto-update'),
  ('notification_email',     '',     'Recipient for price update emails'),
  ('notification_from_email','onboarding@resend.dev', 'From address for Resend');
