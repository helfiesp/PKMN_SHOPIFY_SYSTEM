# Pokelageret POS — Cloudflare Workers + Pages

In-store POS + back-office for a Norwegian Pokémon/TCG shop, designed to run
entirely on Cloudflare's free / pay-as-you-go edge stack.

This is the migration target for the FastAPI app at `../app/`. It re-implements
the features the shop actually uses on the floor:

- **Shopify integration** — bidirectional product/variant cache in D1, push price
  and inventory changes back via GraphQL.
- **Barcode scanning** — POS scan endpoint + link-barcode-to-variant flow that
  writes to both the local `barcodes` table and Shopify `variant.barcode`.
- **Purchase orders** — JPY-denominated supplier purchases, FX snapshot at
  creation time, on receive → push inventory adjustment to Shopify.
- **Kvitteringer (receipts)** — local POS sales decrement Shopify stock and
  produce a printable HTML kvittering stored in R2.
- **Margin VAT (avansemoms)** — Norwegian second-hand-goods margin scheme.
  Computes margin × 25/125 and tracks effective + bucket rates per item, with
  proof-image upload to R2.
- **Stock date clearing** — manages the `custom.stock_date` metafield; daily
  cron clears expired dates.
- **Snkrdunk price updater** — runs every 6 hours via Cron Trigger. Fetches
  Japanese market prices, computes NOK selling prices (FX + shipping + margin
  + VAT + psychological rounding), diffs against Shopify, optionally pushes
  the changes, and emails an HTML digest via Resend.

## Stack

| Layer       | Choice                  | Why                                           |
|-------------|-------------------------|-----------------------------------------------|
| Runtime     | Cloudflare Workers      | Same edge for API + cron, no servers          |
| Framework   | Hono (TS)               | Express-like, Workers-native                  |
| DB          | D1 (SQLite)             | Drop-in for the existing SQLite schema        |
| KV          | Workers KV              | Snkrdunk + FX caches                          |
| Storage     | R2                      | Receipt HTMLs, margin-VAT proof images        |
| Cron        | Cron Triggers           | `0 */6 * * *` — Snkrdunk every 6 hours        |
| Static UI   | Pages-style assets      | Bundled into the same Worker via `[assets]`   |
| Email       | Resend                  | Same provider as the FastAPI version          |

## Layout

```
cloudflare_pos/
├── wrangler.toml             # Worker + bindings + cron
├── migrations/0001_initial.sql
├── src/
│   ├── index.ts              # entry: fetch handler + scheduled handler
│   ├── lib/                  # env types, D1 helpers, Shopify client, auth, utils
│   ├── services/             # business logic (one file per domain)
│   └── routes/               # Hono routers under /api/v1/*
└── public/                   # bundled SPA — served via [assets]
    ├── index.html
    └── assets/{styles.css,app.ts,app.js}
```

## First-time setup

```bash
cd cloudflare_pos
npm install

# 1. Create the D1 database, KV namespace, and R2 bucket.
wrangler d1 create pos_db                # → paste database_id into wrangler.toml
wrangler kv namespace create CACHE       # → paste id into wrangler.toml
wrangler r2 bucket create pokelageret-pos

# 2. Push the schema.
npm run db:migrate:remote
npm run db:migrate:local                 # also for `wrangler dev`

# 3. Set secrets.
wrangler secret put SHOPIFY_TOKEN        # Shopify Admin API access token
wrangler secret put RESEND_API_KEY       # Resend API key
wrangler secret put POS_PIN              # PIN for the POS terminal
wrangler secret put GOOGLE_TRANSLATE_API_KEY    # optional — JP→EN in emails

# 4. Configure non-secret env vars in wrangler.toml [vars]:
#    - SHOPIFY_SHOP, SHOPIFY_LOCATION_ID, collection IDs
#    - SNKRDUNK_* (shipping/margin/markups)
#    - EMAIL_FROM / EMAIL_TO
#    - VAT_RATE_PCT (25 in Norway)

# 5. Build the SPA and deploy.
npm run build:client
npm run deploy
```

For local dev, copy `.dev.vars.example` → `.dev.vars` and run:

```bash
npm run watch:client &     # rebuild SPA on change
npm run dev                # `wrangler dev` — local Worker + D1 + KV + R2
```

## Cron behaviour

`wrangler.toml` registers `0 */6 * * *` (00:00, 06:00, 12:00, 18:00 UTC). The
scheduled handler in `src/index.ts`:

1. Always runs `runSnkrdunkUpdate(env, "cron")`:
   - fetches Snkrdunk pages (cached in KV with `SNKRDUNK_CACHE_TTL_HOURS` TTL)
   - computes new NOK prices
   - diffs against the local Shopify variant cache
   - if `SNKRDUNK_AUTO_UPDATE=true`, pushes via `productVariantsBulkUpdate`
   - logs a row to `snkrdunk_scan_logs` and a price snapshot to
     `snkrdunk_price_history`
   - sends an HTML digest email via Resend

2. At UTC midnight only, also runs `clearExpiredStockDates(env)` to remove the
   `custom.stock_date` metafield from any Shopify product whose date has passed.

To test locally:

```bash
wrangler dev --test-scheduled
# then in another terminal:
curl "http://localhost:8787/__scheduled?cron=0+%2A%2F6+%2A+%2A+%2A"
```

## API overview

All routes are under `/api/v1` and require a valid `pos_session` cookie (issued
by `POST /api/v1/auth/login` with `{ pin }`). Exception: `/api/v1/health`.

| Method | Path                                       | Purpose                                  |
|-------:|--------------------------------------------|------------------------------------------|
| POST   | `/auth/login`                              | Exchange PIN for a session cookie        |
| POST   | `/auth/logout`                             | Clear session                            |
| GET    | `/health`                                  | Worker liveness                          |
| POST   | `/shopify/sync/default`                    | Re-pull the default collection into D1   |
| POST   | `/shopify/sync/:collectionId`              | Pull any collection                      |
| GET    | `/shopify/products?q=…`                    | Search local product cache               |
| POST   | `/shopify/variant/:gid/price`              | Update a single variant price            |
| POST   | `/shopify/variant/:gid/inventory`          | Set or adjust inventory                  |
| GET    | `/barcodes/lookup/:code`                   | POS scan endpoint                        |
| POST   | `/barcodes/link`                           | Link a code to a variant                 |
| POST   | `/snkrdunk/preview`                        | Dry-run: show pending price changes      |
| POST   | `/snkrdunk/apply`                          | Push a hand-picked subset to Shopify     |
| POST   | `/snkrdunk/run`                            | Full run + email (manual trigger)        |
| GET    | `/snkrdunk/settings`                       | Read all SNK_SETTING_KEYS                |
| PUT    | `/snkrdunk/settings`                       | Update settings (shipping, margin, ...)  |
| GET    | `/snkrdunk/exchange-rate`                  | Live JPY→NOK from frankfurter.dev        |
| POST   | `/snkrdunk/fetch`                          | Paginated fetch + cache (+auto-update)   |
| POST   | `/snkrdunk/auto-update`                    | Calculate + push prices + email          |
| POST   | `/snkrdunk/run`                            | Full cron cycle (fetch + auto-update)    |
| POST   | `/snkrdunk/test-email`                     | Send a test Resend email                 |
| POST   | `/snkrdunk/add-manual`                     | Add a single product by URL or ID        |
| GET/DELETE | `/snkrdunk/manual` / `/manual/:id`     | List / remove manual products            |
| GET    | `/snkrdunk/products`                       | Cached + normalized product list         |
| GET    | `/snkrdunk/scan-logs[/:id]`                | Run history (list / detail)              |
| GET    | `/snkrdunk/price-history?log_id=`          | Historical prices for a scan             |
| POST   | `/snkrdunk/hide/:key` `/unhide/:key`       | Hide / unhide product                    |
| GET    | `/snkrdunk/hidden`                         | List hidden snkrdunk_keys                |
| PUT    | `/snkrdunk/mappings/:key/packs`            | Override packs_per_box for a mapping     |
| GET/POST/DELETE | `/snkrdunk/mappings[/:id]`        | CRUD mappings                            |
| POST   | `/snkrdunk/add-pack-variant`               | Split product into Box + Pack variants   |
| DELETE | `/snkrdunk/cache`                          | Wipe all snkrdunk_cache rows             |
| GET/POST | `/purchase-orders`                       | List + create POs                        |
| POST   | `/purchase-orders/:id/receive`             | Receive (push inventory adjust)          |
| GET/POST | `/receipts`                              | List + create receipts                   |
| GET    | `/receipts/:id/print`                      | Printable HTML kvittering                |
| GET/POST | `/margin-vat`                            | List + create margin-VAT purchases       |
| PUT    | `/margin-vat/items/:id/selling-price`      | Recompute margin/VAT for an item         |
| POST   | `/margin-vat/:id/proofs`                   | Upload proof image to R2                 |
| GET/POST/DELETE | `/stock-dates`                    | Manage stock dates                       |
| POST   | `/stock-dates/clear-expired`               | Manual trigger of the daily cron job     |
| GET/PUT | `/settings/:key`                          | App settings                             |

## What is *not* in scope (yet)

The following parts of the FastAPI codebase are intentionally **not** ported,
because they rely on Selenium / a long-running scheduler that doesn't fit the
Workers model:

- `/competition/` — competitor-site scrapers (HataMontCG, CardCenter, etc.)
- `/suppliers/` — Sprell/LekKassen/etc. scrapers
- The desktop `chromedriver-win64/` binary

If/when these are re-introduced, run them on a separate cron-driven worker (or
a small Hetzner box) that writes results into the same D1 over HTTP.

## Notes for the migration

- The Snkrdunk math in `src/services/snkrdunk.ts:computeNokPrice` mirrors the
  Python implementation exactly so existing mappings keep producing the same
  prices. If you tune one, tune both — or migrate the canonical formula here
  and retire the Python one.
- The local barcode table is *additive* — existing Shopify-side `variant.barcode`
  values are imported on the next collection sync via `syncCollection`.
- Margin-VAT items are not deleted when sold; we set `sold_receipt_id` so the
  audit trail survives. This matters for the Norwegian Skatteetaten audit.
- `POS_PIN` auth is a single shared PIN suitable for an in-store terminal. If
  you ever expose this to the public internet, replace it with proper per-user
  auth (e.g. WorkOS, Cloudflare Access, or a Shopify embedded app).
