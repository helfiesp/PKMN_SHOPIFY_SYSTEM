-- Seed the config.* settings rows so they appear in the UI even before the
-- user has touched them. NULL values let getConfig() fall through to env.
-- Use INSERT OR IGNORE so re-runs are no-ops.
INSERT OR IGNORE INTO settings (key, value, description) VALUES
  ('config.SHOPIFY_SHOP',                  NULL, 'Shop domain (e.g. yourstore.myshopify.com)'),
  ('config.SHOPIFY_LOCATION_ID',           NULL, 'Numeric Location ID for inventory ops'),
  ('config.SHOPIFY_API_VERSION',           NULL, 'Shopify Admin API version'),
  ('config.SHOPIFY_DEFAULT_COLLECTION_ID', NULL, 'Default collection ID for sync'),
  ('config.SHOPIFY_BOOSTER_COLLECTION_ID', NULL, 'Booster collection ID'),
  ('config.EMAIL_FROM',                    NULL, 'Resend "from" address'),
  ('config.EMAIL_TO',                      NULL, 'Default email recipient'),
  ('config.COMPANY_NAME',                  NULL, 'Company name on receipts'),
  ('config.COMPANY_ORG_NR',                NULL, 'Org. nr. on receipts'),
  ('config.VAT_RATE_PCT',                  NULL, 'Standard VAT rate, default 25');
