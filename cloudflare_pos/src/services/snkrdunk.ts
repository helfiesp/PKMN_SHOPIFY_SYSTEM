/**
 * Snkrdunk — direct port of app/routers/snkrdunk.py + app/services/snkrdunk_service.py.
 *
 * The pricing math, rounding, threshold rules, and pagination behaviour mirror
 * the Python implementation 1:1 — see the inline comments referencing the
 * source line numbers when in doubt.
 */
import type { Env } from "../lib/env.js";
import { Shopify } from "../lib/shopify.js";
import { audit, getSetting, setSetting } from "../lib/db.js";
import { fetchWithRetry, sleep } from "../lib/utils.js";
import { sendEmail } from "./email.js";
import { translateJaToEn } from "./translation.js";

// ============================================================================
// Constants — must match Python (snkrdunk_service.py L17-30, snkrdunk.py L178)
// ============================================================================
const SNKRDUNK_API_URL = "https://snkrdunk.com/v1/apparel/market/category";
const SNKRDUNK_SINGLE_API_URL = "https://snkrdunk.com/v1/apparels";
const SNKRDUNK_HEADERS: Record<string, string> = {
  "User-Agent":
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  Accept: "application/json, text/plain, */*",
  Referer: "https://snkrdunk.com/",
};
const PER_PAGE = 25;
const VAT = 0.25;
const FX_FALLBACK = 0.063;

// Thresholds for "should we push this price change?" (snkrdunk.py L323/L332).
const BOX_THRESHOLD_NOK = 25;
const PACK_THRESHOLD_NOK = 10;

// snkrdunk.py L178-187 — special-case packs-per-box for known sets.
const SPECIAL_PACK_COUNTS: Array<[string, number]> = [
  ["terastal festival", 10],
  ["mega dream", 10],
  ["vstar universe", 10],
  ["shiny treasure ex", 10],
  ["shiny treasure", 10],
  ["pokemon 151", 20],
  ["black bolt", 20],
  ["white flare", 20],
];

// SNK_SETTING_KEYS from snkrdunk.py L24-31.
export const SNK_SETTING_KEYS: Record<string, [string, string]> = {
  snk_shipping_jpy:      ["500",   "Shipping cost in JPY"],
  snk_margin_pct:        ["20",    "Minimum margin percentage"],
  snk_pack_markup_pct:   ["10",    "Pack price markup over box per-unit price (%)"],
  snk_auto_update:       ["false", "Auto-update prices on Shopify after fetch"],
  snk_max_pages:         ["20",    "Max pages to fetch from SNKRDUNK (25 products/page)"],
  snk_last_jpy_nok_rate: ["0.063", "Last fetched JPY→NOK rate (auto-updated, read-only)"],
};

// ============================================================================
// Helpers — pure functions, ported 1:1 from snkrdunk.py
// ============================================================================

/** snkrdunk.py L190-195. */
export function detectPacksPerBox(title: string | null | undefined): number {
  const t = (title ?? "").trim().toLowerCase();
  for (const [keyword, count] of SPECIAL_PACK_COUNTS) {
    if (t.includes(keyword)) return count;
  }
  return 30;
}

/**
 * snkrdunk.py L198-210.
 *   n = ceil(amount)
 *   if n % 100 == 0:           return n - 1                 // 1000 → 999
 *   r = n + (9 - n % 10)                                    // up to next X9
 *   if r % 100 == 9 and (r // 10) % 10 == 0:  r += 10       // 309 → 319
 *   return r
 */
export function roundUpNok(amount: number): number {
  let n = Math.trunc(amount);
  if (amount > n) n += 1;
  if (n % 100 === 0) return n - 1;
  let r = n + (9 - (n % 10));
  if (r % 100 === 9 && Math.trunc(r / 10) % 10 === 0) r += 10;
  return r;
}

/** snkrdunk.py L213-215 — pack rounding is the same function. */
export function roundPackPriceNok(amount: number): number {
  return roundUpNok(amount);
}

/** snkrdunk_service.py L320-353. */
export function shouldIncludeProduct(name: string | null | undefined): boolean {
  if (!name) return false;
  const lower = name.toLowerCase().trim();
  if (!lower.endsWith("box")) return false;
  if (lower.endsWith("pack")) return false;
  if (lower.includes("[no shrink")) return false;
  if (lower.includes("no shrink wrap")) return false;
  if (lower.includes("deluxe")) return false;
  return true;
}

/** snkrdunk_service.py L355-378. */
export function extractQuotedName(name: string | null | undefined): string {
  if (!name) return "";
  const dq = name.match(/"([^"]+)"/);
  if (dq && dq[1]) return dq[1].trim();
  const sq = name.match(/'([^']+)'/);
  if (sq && sq[1]) return sq[1].trim();
  return "";
}

// ============================================================================
// Settings I/O
// ============================================================================
export async function getSnkSetting(env: Env, key: string): Promise<string> {
  const v = await getSetting(env, key);
  if (v != null && v !== "") return v;
  return SNK_SETTING_KEYS[key]?.[0] ?? "";
}

export async function getAllSnkSettings(env: Env): Promise<Record<string, string>> {
  const out: Record<string, string> = {};
  for (const key of Object.keys(SNK_SETTING_KEYS)) {
    out[key] = await getSnkSetting(env, key);
  }
  return out;
}

export async function saveSnkSettings(env: Env, payload: Record<string, string | undefined>): Promise<string[]> {
  const updated: string[] = [];
  for (const key of Object.keys(SNK_SETTING_KEYS)) {
    const v = payload[key];
    if (v == null) continue;
    await setSetting(env, key, v, SNK_SETTING_KEYS[key]?.[1]);
    updated.push(key);
  }
  return updated;
}

// ============================================================================
// FX rate (live)
// ============================================================================

/** snkrdunk.py L162-175 — frankfurter.dev with 0.063 fallback. */
export async function fetchJpyNokRate(env: Env): Promise<number> {
  try {
    const r = await fetchWithRetry(
      "https://api.frankfurter.dev/v1/latest?base=JPY&symbols=NOK",
      { method: "GET" },
      2,
    );
    const data = (await r.json()) as { rates?: { NOK?: number } };
    const rate = data.rates?.NOK;
    if (rate && Number.isFinite(rate)) {
      await setSetting(env, "snk_last_jpy_nok_rate", String(rate), "Last fetched JPY→NOK rate");
      return rate;
    }
  } catch (err) {
    console.warn("[SNKRDUNK] FX rate fetch failed, using fallback:", err);
  }
  return FX_FALLBACK;
}

// ============================================================================
// Snkrdunk API
// ============================================================================

interface ApparelItem {
  id: number | string;
  name?: string;
  minPrice?: number;
  maxPrice?: number;
  regularPrice?: number;
  brands?: Array<{ name?: string }>;
  primaryMedia?: { imageUrl?: string };
  localizedName?: string;
  [k: string]: unknown;
}
interface CategoryResponse {
  apparels?: ApparelItem[];
}

async function snkrdunkFetchCategoryPage(page: number): Promise<CategoryResponse> {
  const params = new URLSearchParams({
    page: String(page),
    perPage: String(PER_PAGE),
    order: "popular",
    apparelCategoryId: "14",
    apparelSubCategoryId: "0",
    brandId: "pokemon",
    departmentName: "hobby",
  });
  const url = `${SNKRDUNK_API_URL}?${params.toString()}`;
  const res = await fetch(url, { headers: SNKRDUNK_HEADERS });
  if (!res.ok) throw new Error(`Snkrdunk page ${page} → ${res.status}`);
  return (await res.json()) as CategoryResponse;
}

async function snkrdunkFetchSingleProduct(productId: number): Promise<ApparelItem> {
  const url = `${SNKRDUNK_SINGLE_API_URL}/${productId}`;
  const res = await fetch(url, { headers: SNKRDUNK_HEADERS });
  if (!res.ok) {
    if (res.status === 404) throw new Error(`Product ${productId} not found on SNKRDUNK`);
    throw new Error(`Snkrdunk single ${productId} → ${res.status}`);
  }
  const data = (await res.json()) as ApparelItem;
  if (!data || !data.id) throw new Error(`SNKRDUNK returned no data for product ${productId}`);
  return data;
}

// ============================================================================
// Cache I/O — D1 mirror of SnkrdunkCache table (page+brand_id PK)
// ============================================================================

interface CacheRow {
  page: number;
  brand_id: string;
  response_data: string;
  created_at: number;
  expires_at: number | null;
}

async function readCache(env: Env, page: number, brandId: string, validAtSec: number): Promise<CacheRow | null> {
  return await env.DB.prepare(
    `SELECT page, brand_id, response_data, created_at, expires_at
       FROM snkrdunk_cache
      WHERE page = ? AND brand_id = ? AND (expires_at IS NULL OR expires_at > ?)`,
  )
    .bind(page, brandId, validAtSec)
    .first<CacheRow>();
}

async function writeCache(
  env: Env,
  page: number,
  brandId: string,
  categoryId: number,
  data: unknown,
  ttlHours: number,
): Promise<void> {
  const expiresAt = Math.floor(Date.now() / 1000) + ttlHours * 3600;
  await env.DB.prepare(
    `INSERT INTO snkrdunk_cache (page, brand_id, category_id, response_data, created_at, expires_at)
     VALUES (?, ?, ?, ?, unixepoch(), ?)
     ON CONFLICT(page, brand_id) DO UPDATE SET
       response_data = excluded.response_data,
       category_id = excluded.category_id,
       created_at = unixepoch(),
       expires_at = excluded.expires_at`,
  )
    .bind(page, brandId, categoryId, JSON.stringify(data), expiresAt)
    .run();
}

// ============================================================================
// Manual products
// ============================================================================

export async function fetchAndCacheSingleProduct(env: Env, productId: number): Promise<{
  id: number;
  name: string;
  nameEn: string;
  minPriceJpy: number | null;
  regularPrice: number | null;
  imageUrl: string | null;
}> {
  const data = await snkrdunkFetchSingleProduct(productId);
  const ttl = Number(await getSnkSetting(env, "snk_cache_ttl_hours")) || 6;
  await writeCache(env, productId, "manual", 0, { apparels: [data] }, ttl);

  const nameJa = (data.name as string) || (data.localizedName as string) || "";
  if (nameJa) await translateJaToEn(env, nameJa);

  return {
    id: Number(data.id),
    name: nameJa,
    nameEn: (data.name as string) ?? "",
    minPriceJpy: typeof data.minPrice === "number" ? data.minPrice : null,
    regularPrice: typeof data.regularPrice === "number" ? data.regularPrice : null,
    imageUrl: (data.primaryMedia as { imageUrl?: string } | undefined)?.imageUrl ?? null,
  };
}

async function refreshManualProducts(env: Env): Promise<number> {
  const rows = await env.DB.prepare(
    `SELECT page FROM snkrdunk_cache WHERE brand_id = 'manual'`,
  ).all<{ page: number }>();
  let refreshed = 0;
  for (const r of rows.results ?? []) {
    try {
      await fetchAndCacheSingleProduct(env, r.page);
      refreshed++;
    } catch (err) {
      console.warn(`[SNKRDUNK] manual refresh failed for ${r.page}:`, err);
    }
  }
  return refreshed;
}

export async function listManualProducts(env: Env): Promise<Array<Record<string, unknown>>> {
  const rows = await env.DB.prepare(
    `SELECT page, response_data, created_at, expires_at
       FROM snkrdunk_cache WHERE brand_id = 'manual' ORDER BY created_at DESC`,
  ).all<CacheRow>();
  const items: Array<Record<string, unknown>> = [];
  for (const r of rows.results ?? []) {
    try {
      const data = JSON.parse(r.response_data) as { apparels?: ApparelItem[] };
      const item = data.apparels?.[0];
      if (!item) continue;
      items.push({
        id: item.id,
        name: item.name,
        minPriceJpy: item.minPrice,
        regularPrice: item.regularPrice,
        imageUrl: (item.primaryMedia as { imageUrl?: string } | undefined)?.imageUrl,
        cached_at: r.created_at,
        expires_at: r.expires_at,
      });
    } catch {
      // skip
    }
  }
  return items;
}

export async function removeManualProduct(env: Env, snkrdunkKey: number): Promise<boolean> {
  const del = await env.DB.prepare(
    `DELETE FROM snkrdunk_cache WHERE brand_id = 'manual' AND page = ?`,
  )
    .bind(snkrdunkKey)
    .run();
  await env.DB.prepare(`DELETE FROM snkrdunk_mappings WHERE snkrdunk_key = ?`)
    .bind(String(snkrdunkKey))
    .run();
  return (del.meta.changes ?? 0) > 0;
}

// ============================================================================
// Fetch & cache — main pipeline, mirrors fetch_and_cache_snkrdunk_data
// ============================================================================

export interface FetchResult {
  total_items: number;
  pages_fetched: number;
  manual_refreshed: number;
  cached_at: string;
  items: ApparelItem[];
}

export async function fetchAndCacheSnkrdunk(
  env: Env,
  pages: number[] = [1],
  forceRefresh = false,
): Promise<FetchResult> {
  const ttlHours = Number(await getSnkSetting(env, "snk_cache_ttl_hours")) || 6;
  const maxPages = Number(await getSnkSetting(env, "snk_max_pages")) || 20;

  // Auto-paginate when forcing a refresh from the default starting point
  // (matches Python: pages == [1] or pages == [1, 2, 3]).
  const isDefaultPages =
    (pages.length === 1 && pages[0] === 1) ||
    (pages.length === 3 && pages[0] === 1 && pages[1] === 2 && pages[2] === 3);
  const autoPaginate = forceRefresh && isDefaultPages;
  const pageList = autoPaginate ? Array.from({ length: maxPages }, (_, i) => i + 1) : pages;

  const allItems: ApparelItem[] = [];
  let pagesFetched = 0;
  const nowSec = Math.floor(Date.now() / 1000);

  for (const page of pageList) {
    let data: CategoryResponse | null = null;

    if (!forceRefresh) {
      const cached = await readCache(env, page, "pokemon", nowSec);
      if (cached) {
        try {
          data = JSON.parse(cached.response_data) as CategoryResponse;
        } catch {
          data = null;
        }
        if (data) {
          const items = (data.apparels ?? []).filter((x) => x && typeof x === "object" && "id" in x);
          allItems.push(...items);
          pagesFetched++;
          if (autoPaginate && items.length < PER_PAGE) break;
          continue;
        }
      }
    }

    // Cache miss / forced — hit the live API.
    try {
      data = await snkrdunkFetchCategoryPage(page);
    } catch (err) {
      console.error(`[SNKRDUNK] page ${page} fetch failed:`, err);
      throw err;
    }
    await writeCache(env, page, "pokemon", 14, data, ttlHours);

    const items = (data.apparels ?? []).filter((x) => x && typeof x === "object" && "id" in x);
    allItems.push(...items);
    pagesFetched++;
    if (autoPaginate && items.length < PER_PAGE) {
      console.info(`[SNKRDUNK] page ${page} returned ${items.length} (< ${PER_PAGE}), stopping`);
      break;
    }
    // Mild courtesy delay between live fetches.
    await sleep(150);
  }

  // Bump updated_at on all mappings (mirrors the Python "last fetched" marker).
  await env.DB.prepare(`UPDATE snkrdunk_mappings SET updated_at = unixepoch()`).run();

  // Translate names (best-effort, cached in Translation table).
  for (const item of allItems) {
    const name = (item.name ?? "").toString().trim();
    if (name) await translateJaToEn(env, name);
  }

  // Refresh manual products.
  const manualRefreshed = await refreshManualProducts(env);

  // Add manual cache entries to the returned items list.
  const manualRows = await env.DB.prepare(
    `SELECT response_data FROM snkrdunk_cache WHERE brand_id = 'manual'`,
  ).all<{ response_data: string }>();
  for (const row of manualRows.results ?? []) {
    try {
      const parsed = JSON.parse(row.response_data) as CategoryResponse;
      for (const item of parsed.apparels ?? []) {
        if (item && typeof item === "object" && "id" in item) allItems.push(item);
      }
    } catch {
      // skip
    }
  }

  // Dedupe by id.
  const seen = new Set<string>();
  const unique: ApparelItem[] = [];
  for (const item of allItems) {
    const id = String(item.id);
    if (!seen.has(id)) {
      seen.add(id);
      unique.push(item);
    }
  }

  return {
    total_items: unique.length,
    pages_fetched: pagesFetched,
    manual_refreshed: manualRefreshed,
    cached_at: new Date().toISOString(),
    items: unique,
  };
}

// ============================================================================
// get_cached_products — normalized list with translations + price changes
// ============================================================================

export interface NormalizedProduct {
  id: number | string;
  name: string;
  nameEn: string;
  minPriceJpy: number | null;
  maxPriceJpy: number | null;
  regularPrice: number | null;
  brand: { name?: string } | null;
  imageUrl: string | null;
  last_price_updated: string | null;
  price_change: number;
  _cached_at: string | null;
  _page: number;
  _manual: boolean;
  _raw: ApparelItem;
}

export async function getCachedProducts(
  env: Env,
  opts: { includeExpired?: boolean; translate?: boolean; scanLogId?: number | null } = {},
): Promise<NormalizedProduct[]> {
  const includeExpired = !!opts.includeExpired;
  const doTranslate = opts.translate !== false;
  const scanLogId = opts.scanLogId ?? null;
  const nowSec = Math.floor(Date.now() / 1000);

  const cacheQuery = includeExpired
    ? `SELECT page, brand_id, response_data, created_at, expires_at FROM snkrdunk_cache`
    : `SELECT page, brand_id, response_data, created_at, expires_at FROM snkrdunk_cache
        WHERE expires_at IS NULL OR expires_at > ?`;
  const stmt = includeExpired
    ? env.DB.prepare(cacheQuery)
    : env.DB.prepare(cacheQuery).bind(nowSec);
  const caches = await stmt.all<CacheRow>();

  // Pre-load translations.
  const trMap = new Map<string, string>();
  if (doTranslate) {
    const t = await env.DB.prepare(
      `SELECT source_text, translated_text FROM translations WHERE target_lang = 'en'`,
    ).all<{ source_text: string; translated_text: string }>();
    for (const row of t.results ?? []) trMap.set(row.source_text, row.translated_text);
  }

  // Compute price_change vs the previous scan log (matches Python logic).
  const priceChanges = await computePriceChanges(env, scanLogId);

  const out: NormalizedProduct[] = [];
  for (const row of caches.results ?? []) {
    const isManual = row.brand_id === "manual";
    let parsed: CategoryResponse;
    try {
      parsed = JSON.parse(row.response_data) as CategoryResponse;
    } catch {
      continue;
    }
    for (const item of parsed.apparels ?? []) {
      if (!item || typeof item !== "object" || !("id" in item)) continue;
      const nameJa = (item.name ?? "").toString();

      let displayName = "";
      if (isManual) {
        displayName = nameJa || "Unknown";
        const extracted = extractQuotedName(nameJa);
        if (extracted) displayName = extracted;
      } else {
        if (!shouldIncludeProduct(nameJa)) continue;
        const extracted = extractQuotedName(nameJa);
        if (!extracted) continue;
        displayName = extracted;
      }

      const productId = String(item.id);
      const cachedAtISO = row.created_at ? new Date(row.created_at * 1000).toISOString() : null;

      const norm: NormalizedProduct = {
        id: item.id,
        name: nameJa,
        nameEn: displayName,
        minPriceJpy: typeof item.minPrice === "number" ? item.minPrice : null,
        maxPriceJpy: typeof item.maxPrice === "number" ? item.maxPrice : null,
        regularPrice: typeof item.regularPrice === "number" ? item.regularPrice : null,
        brand: Array.isArray(item.brands) && item.brands[0] ? item.brands[0] : null,
        imageUrl: (item.primaryMedia as { imageUrl?: string } | undefined)?.imageUrl ?? null,
        last_price_updated: cachedAtISO,
        price_change: priceChanges.get(productId) ?? 0,
        _cached_at: cachedAtISO,
        _page: row.page,
        _manual: isManual,
        _raw: item,
      };

      // Override price from a specific scan if requested.
      if (scanLogId) {
        const hist = await env.DB.prepare(
          `SELECT price_jpy FROM snkrdunk_price_history WHERE scan_log_id = ? AND snkrdunk_key = ? LIMIT 1`,
        )
          .bind(scanLogId, productId)
          .first<{ price_jpy: number }>();
        if (hist) norm.minPriceJpy = hist.price_jpy;
      }

      // Apply translation overrides.
      if (doTranslate && nameJa) {
        const translated = trMap.get(nameJa);
        if (translated) {
          const extractedT = extractQuotedName(translated);
          if (extractedT) norm.nameEn = extractedT;
          else if (isManual) norm.nameEn = translated;
        }
      }

      out.push(norm);
    }
  }
  return out;
}

async function computePriceChanges(env: Env, scanLogId: number | null): Promise<Map<string, number>> {
  const changes = new Map<string, number>();
  try {
    let currentScanId: number | null = null;
    let previousScanId: number | null = null;
    if (scanLogId) {
      const scans = await env.DB.prepare(
        `SELECT id FROM snkrdunk_scan_logs ORDER BY started_at DESC`,
      ).all<{ id: number }>();
      const list = scans.results ?? [];
      const idx = list.findIndex((s) => s.id === scanLogId);
      if (idx >= 0 && idx < list.length - 1) {
        currentScanId = list[idx]!.id;
        previousScanId = list[idx + 1]!.id;
      }
    } else {
      const latest = await env.DB.prepare(
        `SELECT id FROM snkrdunk_scan_logs ORDER BY started_at DESC LIMIT 2`,
      ).all<{ id: number }>();
      const list = latest.results ?? [];
      if (list.length >= 2) {
        currentScanId = list[0]!.id;
        previousScanId = list[1]!.id;
      }
    }
    if (!currentScanId || !previousScanId) return changes;

    const cur = await env.DB.prepare(
      `SELECT snkrdunk_key, price_jpy FROM snkrdunk_price_history WHERE scan_log_id = ?`,
    )
      .bind(currentScanId)
      .all<{ snkrdunk_key: string; price_jpy: number }>();
    const prev = await env.DB.prepare(
      `SELECT snkrdunk_key, price_jpy FROM snkrdunk_price_history WHERE scan_log_id = ?`,
    )
      .bind(previousScanId)
      .all<{ snkrdunk_key: string; price_jpy: number }>();

    const prevMap = new Map<string, number>();
    for (const r of prev.results ?? []) prevMap.set(r.snkrdunk_key, r.price_jpy);
    for (const r of cur.results ?? []) {
      const p = prevMap.get(r.snkrdunk_key);
      if (p && r.price_jpy && r.price_jpy !== p) changes.set(r.snkrdunk_key, r.price_jpy - p);
    }
  } catch (err) {
    console.warn("computePriceChanges failed:", err);
  }
  return changes;
}

// ============================================================================
// Auto-update — calculate & push, mirrors _execute_auto_update (snkrdunk.py L227+)
// ============================================================================

export interface ItemResult {
  product: string;
  product_shopify_id: string;
  snkrdunk_key: string;
  jpy: number;
  rate: number;
  box_old?: number;
  box_new?: number;
  box_skip?: string;
  pack_old?: number;
  pack_new?: number;
  pack_skip?: string;
  packs_per_box?: number;
  pushed?: boolean;
  shopify_error?: unknown;
  imageUrl?: string | null;
  inventory_quantity?: number | null;
  variant_box_id?: string | null;
  variant_pack_id?: string | null;
}

export interface AutoUpdateResult {
  rate: number;
  shipping_jpy: number;
  margin_pct: number;
  pack_markup_pct: number;
  total_mappings: number;
  processed: number;
  pushed: number;
  errors: Array<{ product: string; error?: string; errors?: unknown }>;
  details: ItemResult[];
}

export async function executeAutoUpdate(env: Env): Promise<AutoUpdateResult> {
  const shipping = Number(await getSnkSetting(env, "snk_shipping_jpy"));
  const margin = Number(await getSnkSetting(env, "snk_margin_pct")) / 100;
  const packMarkup = Number(await getSnkSetting(env, "snk_pack_markup_pct")) / 100;
  const rate = await fetchJpyNokRate(env);

  const products = await getCachedProducts(env, { includeExpired: false, translate: true });
  const snkById = new Map<string, NormalizedProduct>();
  for (const p of products) snkById.set(String(p.id), p);

  const mappings = await env.DB.prepare(
    `SELECT * FROM snkrdunk_mappings
      WHERE disabled = 0 AND product_shopify_id IS NOT NULL`,
  ).all<{
    snkrdunk_key: string;
    product_shopify_id: string;
    packs_per_box: number | null;
    variant_shopify_id: string | null;
  }>();

  const results: ItemResult[] = [];
  const errors: Array<{ product: string; error?: string; errors?: unknown }> = [];
  const shopify = new Shopify(env);

  for (const m of mappings.results ?? []) {
    const snk = snkById.get(String(m.snkrdunk_key));
    if (!snk) continue;
    const jpy = snk.minPriceJpy ?? 0;
    if (!jpy || jpy <= 0) continue;

    // Box price: (jpy + shipping) * rate / (1 - margin) * 1.25 → roundUpNok
    const nokCost = (jpy + shipping) * rate;
    const boxPrice = roundUpNok((nokCost / (1 - margin)) * (1 + VAT));

    const product = await env.DB.prepare(
      `SELECT id, title FROM products WHERE shopify_id = ?`,
    )
      .bind(m.product_shopify_id)
      .first<{ id: number; title: string }>();
    if (!product) continue;

    const packs = m.packs_per_box ?? detectPacksPerBox(product.title);
    const packRaw = (boxPrice / packs) * (1 + packMarkup);
    const packPrice = roundPackPriceNok(packRaw);

    // Find box / pack variants (snkrdunk.py L296-310).
    const variants = await env.DB.prepare(
      `SELECT shopify_id, title, sku, price, option_value, inventory_quantity
         FROM variants WHERE product_id = ?`,
    )
      .bind(product.id)
      .all<{
        shopify_id: string;
        title: string | null;
        sku: string | null;
        price: number | null;
        option_value: string | null;
        inventory_quantity: number;
      }>();

    type V = (typeof variants.results)[number];
    let boxVariant: V | null = null;
    let packVariant: V | null = null;
    for (const v of variants.results ?? []) {
      const opt = (v.option_value ?? v.title ?? "").toLowerCase();
      if (opt.includes("box")) boxVariant = v;
      else if (opt.includes("pack")) packVariant = v;
    }
    if (!boxVariant && !packVariant && (variants.results?.length ?? 0) === 1) {
      boxVariant = variants.results![0]!;
    }

    const item: ItemResult = {
      product: product.title,
      product_shopify_id: m.product_shopify_id,
      snkrdunk_key: String(m.snkrdunk_key),
      jpy,
      rate,
      imageUrl: snk.imageUrl ?? null,
      inventory_quantity: boxVariant?.inventory_quantity ?? null,
      variant_box_id: boxVariant?.shopify_id ?? null,
      variant_pack_id: packVariant?.shopify_id ?? null,
    };
    const updates: Array<{ id: string; price: number }> = [];

    if (boxVariant) {
      const oldBox = Number(boxVariant.price ?? 0);
      if (Math.abs(oldBox - boxPrice) >= BOX_THRESHOLD_NOK) {
        updates.push({ id: boxVariant.shopify_id, price: boxPrice });
        item.box_old = oldBox;
        item.box_new = boxPrice;
      } else {
        item.box_skip = `no change (${oldBox})`;
      }
    }
    if (packVariant) {
      const oldPack = Number(packVariant.price ?? 0);
      if (Math.abs(oldPack - packPrice) >= PACK_THRESHOLD_NOK) {
        updates.push({ id: packVariant.shopify_id, price: packPrice });
        item.pack_old = oldPack;
        item.pack_new = packPrice;
        item.packs_per_box = packs;
      } else {
        item.pack_skip = `no change (${oldPack})`;
      }
    }

    if (updates.length > 0) {
      try {
        await shopify.productVariantsBulkUpdate(
          m.product_shopify_id,
          updates.map((u) => ({ id: u.id, price: u.price.toFixed(2), compareAtPrice: undefined })),
        );
        for (const u of updates) {
          const oldPrice = u.id === boxVariant?.shopify_id ? Number(boxVariant.price ?? 0) : Number(packVariant?.price ?? 0);
          await env.DB.prepare(
            `UPDATE variants SET price = ?, updated_at = unixepoch() WHERE shopify_id = ?`,
          )
            .bind(u.price, u.id)
            .run();
          await env.DB.prepare(
            `INSERT INTO price_change_logs (variant_shopify_id, product_shopify_id, old_price, new_price, change_type, source, applied)
             VALUES (?, ?, ?, ?, 'snkrdunk_auto_update', ?, 1)`,
          )
            .bind(u.id, m.product_shopify_id, oldPrice, u.price, m.snkrdunk_key)
            .run();
        }
        item.pushed = true;
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        errors.push({ product: product.title, error: msg });
        item.shopify_error = msg;
      }
    }

    results.push(item);
  }

  // Email digest (non-blocking).
  try {
    await sendPriceUpdateEmail(env, {
      results,
      errors,
      settingsSummary: {
        rate,
        shipping_jpy: shipping,
        margin_pct: margin * 100,
        pack_markup_pct: packMarkup * 100,
      },
    });
  } catch (err) {
    console.warn("[SNKRDUNK] email send failed:", err);
  }

  await audit(env, "snkrdunk.auto_update", {
    details: {
      total_mappings: mappings.results?.length ?? 0,
      processed: results.length,
      pushed: results.filter((r) => r.pushed).length,
      errors: errors.length,
    },
  });

  return {
    rate,
    shipping_jpy: shipping,
    margin_pct: margin * 100,
    pack_markup_pct: packMarkup * 100,
    total_mappings: mappings.results?.length ?? 0,
    processed: results.length,
    pushed: results.filter((r) => r.pushed).length,
    errors,
    details: results,
  };
}

// ============================================================================
// Cron entry point — fetch, record price history, optionally auto-update + email
// ============================================================================

export interface CronRunResult {
  scanLogId: number;
  totalItems: number;
  pagesFetched: number;
  fxRate: number;
  autoUpdate?: AutoUpdateResult;
  durationMs: number;
}

export async function runSnkrdunkCronCycle(env: Env, trigger: "cron" | "manual" = "cron"): Promise<CronRunResult> {
  const startedAt = Date.now();
  const ins = await env.DB.prepare(
    `INSERT INTO snkrdunk_scan_logs (status, trigger, started_at) VALUES ('running', ?, unixepoch())`,
  )
    .bind(trigger)
    .run();
  const scanLogId = Number(ins.meta.last_row_id);

  try {
    const result = await fetchAndCacheSnkrdunk(env, [1], true);

    // Record price snapshot.
    const snaps = result.items
      .filter((i) => typeof i.minPrice === "number" && (i.minPrice as number) > 0)
      .map((i) =>
        env.DB.prepare(
          `INSERT INTO snkrdunk_price_history (scan_log_id, snkrdunk_key, price_jpy) VALUES (?, ?, ?)`,
        ).bind(scanLogId, String(i.id), i.minPrice as number),
      );
    for (let i = 0; i < snaps.length; i += 50) {
      await env.DB.batch(snaps.slice(i, i + 50));
    }

    const fxRate = await fetchJpyNokRate(env);
    let autoUpdate: AutoUpdateResult | undefined;

    if ((await getSnkSetting(env, "snk_auto_update")) === "true") {
      autoUpdate = await executeAutoUpdate(env);
    }

    const durationMs = Date.now() - startedAt;
    await env.DB.prepare(
      `UPDATE snkrdunk_scan_logs
          SET status = 'success', completed_at = unixepoch(),
              duration_ms = ?, total_items = ?, matched_items = ?, updated_items = ?,
              fx_rate_jpy_nok = ?, email_sent = ?
        WHERE id = ?`,
    )
      .bind(
        durationMs,
        result.total_items,
        autoUpdate?.processed ?? null,
        autoUpdate?.pushed ?? null,
        fxRate,
        autoUpdate ? 1 : 0,
        scanLogId,
      )
      .run();

    return {
      scanLogId,
      totalItems: result.total_items,
      pagesFetched: result.pages_fetched,
      fxRate,
      autoUpdate,
      durationMs,
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await env.DB.prepare(
      `UPDATE snkrdunk_scan_logs SET status = 'failed', completed_at = unixepoch(),
        error_message = ?, duration_ms = ? WHERE id = ?`,
    )
      .bind(msg, Date.now() - startedAt, scanLogId)
      .run();
    await audit(env, "snkrdunk.cron", { success: false, errorMessage: msg, details: { trigger } });
    throw err;
  }
}

// ============================================================================
// Email digest — mirrors send_price_update_email from email_service.py
// ============================================================================

interface EmailContext {
  results: ItemResult[];
  errors: Array<{ product: string; error?: string; errors?: unknown }>;
  settingsSummary: {
    rate: number;
    shipping_jpy: number;
    margin_pct: number;
    pack_markup_pct: number;
  };
}

async function sendPriceUpdateEmail(env: Env, ctx: EmailContext): Promise<void> {
  if ((await getSetting(env, "email_notifications_enabled")) !== "true") return;
  const recipient = (await getSetting(env, "notification_email")) || env.EMAIL_TO;
  if (!recipient) return;

  const pushed = ctx.results.filter((r) => r.pushed);
  const skipped = ctx.results.filter((r) => !r.pushed && !r.shopify_error);
  const failed = ctx.results.filter((r) => r.shopify_error);

  // Low-stock alert: box variants with qty <= 5 on active products.
  const lowStock = await env.DB.prepare(
    `SELECT v.shopify_id, v.title, v.sku, v.inventory_quantity, p.title AS product_title, p.image_url
       FROM variants v
       JOIN products p ON p.id = v.product_id
      WHERE p.status = 'ACTIVE'
        AND v.inventory_quantity <= 5
        AND LOWER(COALESCE(v.option_value, v.title, '')) LIKE '%box%'
      ORDER BY v.inventory_quantity ASC LIMIT 50`,
  ).all<{
    product_title: string;
    title: string | null;
    sku: string | null;
    inventory_quantity: number;
    image_url: string | null;
  }>();

  const subject = `Pokelageret: ${pushed.length} price(s) updated | ${lowStock.results?.length ?? 0} low stock`;

  const stat = (label: string, value: string | number, color: string) => `
    <td style="padding:14px;text-align:center;border-radius:8px;background:${color};color:#fff;min-width:80px;">
      <div style="font-size:24px;font-weight:700;">${value}</div>
      <div style="font-size:11px;opacity:.85;text-transform:uppercase;letter-spacing:.05em;">${label}</div>
    </td>`;

  const params = `
    <table style="font-size:13px;border-collapse:collapse;margin:8px 0;">
      <tr><td style="padding:3px 12px 3px 0;color:#666;">FX (JPY→NOK)</td><td><b>${ctx.settingsSummary.rate.toFixed(5)}</b></td></tr>
      <tr><td style="padding:3px 12px 3px 0;color:#666;">Shipping</td><td><b>${ctx.settingsSummary.shipping_jpy} JPY</b></td></tr>
      <tr><td style="padding:3px 12px 3px 0;color:#666;">Margin</td><td><b>${ctx.settingsSummary.margin_pct}%</b></td></tr>
      <tr><td style="padding:3px 12px 3px 0;color:#666;">Pack markup</td><td><b>${ctx.settingsSummary.pack_markup_pct}%</b></td></tr>
      <tr><td style="padding:3px 12px 3px 0;color:#666;">VAT</td><td><b>25%</b></td></tr>
      <tr><td style="padding:3px 12px 3px 0;color:#666;">Min change</td><td><b>${BOX_THRESHOLD_NOK} kr (box) / ${PACK_THRESHOLD_NOK} kr (pack)</b></td></tr>
    </table>`;

  const pushedRows = pushed
    .flatMap((r) => {
      const rows: string[] = [];
      const img = r.imageUrl
        ? `<img src="${escapeHtml(r.imageUrl)}" style="width:48px;height:48px;border-radius:6px;object-fit:cover;vertical-align:middle;margin-right:10px;">`
        : "";
      if (r.box_new != null) {
        const delta = (r.box_new ?? 0) - (r.box_old ?? 0);
        const deltaColor = delta > 0 ? "#2e7d32" : "#c62828";
        rows.push(`<tr>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;">${img}<b>${escapeHtml(r.product)}</b><br><small style="color:#888;">Booster Box · ${r.jpy} JPY</small></td>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;"><span style="text-decoration:line-through;color:#999;">${(r.box_old ?? 0).toFixed(0)} kr</span></td>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;"><b>${r.box_new.toFixed(0)} kr</b></td>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;color:${deltaColor};font-weight:600;">${delta > 0 ? "+" : ""}${delta.toFixed(0)} kr</td>
        </tr>`);
      }
      if (r.pack_new != null) {
        const delta = (r.pack_new ?? 0) - (r.pack_old ?? 0);
        const deltaColor = delta > 0 ? "#2e7d32" : "#c62828";
        rows.push(`<tr>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;">${img}<b>${escapeHtml(r.product)}</b><br><small style="color:#888;">Booster Pack · ${r.packs_per_box ?? "?"} per box</small></td>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;"><span style="text-decoration:line-through;color:#999;">${(r.pack_old ?? 0).toFixed(0)} kr</span></td>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;"><b>${r.pack_new.toFixed(0)} kr</b></td>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;color:${deltaColor};font-weight:600;">${delta > 0 ? "+" : ""}${delta.toFixed(0)} kr</td>
        </tr>`);
      }
      return rows;
    })
    .join("");

  const lowStockRows = (lowStock.results ?? [])
    .map((s) => {
      const qty = s.inventory_quantity;
      const color = qty <= 0 ? "#c62828" : qty <= 3 ? "#ed6c02" : "#f9a825";
      const img = s.image_url
        ? `<img src="${escapeHtml(s.image_url)}" style="width:40px;height:40px;border-radius:6px;object-fit:cover;vertical-align:middle;margin-right:10px;">`
        : "";
      return `<tr>
        <td style="padding:8px 10px;border-bottom:1px solid #eee;">${img}${escapeHtml(s.product_title)}<br><small style="color:#888;">${escapeHtml(s.title ?? "")} · ${escapeHtml(s.sku ?? "")}</small></td>
        <td style="padding:8px 10px;border-bottom:1px solid #eee;text-align:right;"><span style="background:${color};color:#fff;padding:4px 10px;border-radius:999px;font-weight:600;font-size:12px;">${qty}</span></td>
      </tr>`;
    })
    .join("");

  const errorRows = failed
    .map(
      (r) =>
        `<tr>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;">${escapeHtml(r.product)}</td>
          <td style="padding:8px 10px;border-bottom:1px solid #eee;color:#c62828;">${escapeHtml(JSON.stringify(r.shopify_error))}</td>
        </tr>`,
    )
    .join("");

  const html = `
  <div style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:0 auto;color:#333;">
    <div style="background:linear-gradient(135deg,#d62828 0%,#7a1818 100%);color:#fff;padding:24px;border-radius:10px 10px 0 0;">
      <h1 style="margin:0;font-size:22px;">Snkrdunk price update</h1>
      <div style="opacity:.85;margin-top:4px;font-size:13px;">${new Date().toISOString()}</div>
    </div>

    <div style="background:#fff;padding:20px;border:1px solid #e3e6ea;border-top:none;">
      <table style="width:100%;border-collapse:separate;border-spacing:8px;margin-bottom:16px;">
        <tr>
          ${stat("Updated", pushed.length, "#2e7d32")}
          ${stat("Skipped", skipped.length, "#6b7280")}
          ${stat("Errors", failed.length, "#c62828")}
          ${stat("Total", ctx.results.length, "#1976d2")}
        </tr>
      </table>

      <h3 style="margin:16px 0 4px;font-size:13px;color:#666;text-transform:uppercase;letter-spacing:.05em;">Pricing parameters</h3>
      ${params}

      ${pushedRows ? `
        <h3 style="margin:16px 0 8px;">Pushed price changes</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead><tr style="background:#fafafa;">
            <th style="padding:8px 10px;text-align:left;">Product</th>
            <th style="padding:8px 10px;text-align:right;">Old</th>
            <th style="padding:8px 10px;text-align:right;">New</th>
            <th style="padding:8px 10px;text-align:right;">Δ</th>
          </tr></thead>
          <tbody>${pushedRows}</tbody>
        </table>` : `<p style="color:#666;">No price changes pushed.</p>`}

      ${lowStockRows ? `
        <h3 style="margin:24px 0 8px;">Low stock alert (≤ 5 boxes)</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead><tr style="background:#fafafa;">
            <th style="padding:8px 10px;text-align:left;">Product</th>
            <th style="padding:8px 10px;text-align:right;">Qty</th>
          </tr></thead>
          <tbody>${lowStockRows}</tbody>
        </table>` : ""}

      ${errorRows ? `
        <h3 style="margin:24px 0 8px;color:#c62828;">Errors</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead><tr style="background:#fde8e8;">
            <th style="padding:8px 10px;text-align:left;">Product</th>
            <th style="padding:8px 10px;text-align:left;">Error</th>
          </tr></thead>
          <tbody>${errorRows}</tbody>
        </table>` : ""}
    </div>

    <div style="background:#fafafa;padding:14px;border:1px solid #e3e6ea;border-top:none;border-radius:0 0 10px 10px;text-align:center;color:#999;font-size:12px;">
      Pokelageret POS · Cloudflare Workers · cron 0 */6 * * *
    </div>
  </div>`;

  await sendEmail(env, { to: recipient, subject, html });
}

export async function sendTestEmail(env: Env): Promise<{ success: boolean; message: string }> {
  const recipient = (await getSetting(env, "notification_email")) || env.EMAIL_TO;
  if (!recipient) return { success: false, message: "No notification_email configured" };
  const r = await sendEmail(env, {
    to: recipient,
    subject: "Pokelageret POS — test email",
    html: `<p>This is a Resend test email from the POS at ${new Date().toISOString()}.</p>`,
  });
  return { success: r.ok, message: r.ok ? `Sent to ${recipient}` : (r.error ?? "Unknown") };
}

// ============================================================================
// Hide / unhide / packs override
// ============================================================================
export async function hideProduct(env: Env, snkrdunkKey: string): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO snkrdunk_mappings (snkrdunk_key, disabled) VALUES (?, 1)
     ON CONFLICT(snkrdunk_key) DO UPDATE SET disabled = 1, updated_at = unixepoch()`,
  )
    .bind(snkrdunkKey)
    .run();
}

export async function unhideProduct(env: Env, snkrdunkKey: string): Promise<void> {
  await env.DB.prepare(
    `UPDATE snkrdunk_mappings SET disabled = 0, updated_at = unixepoch() WHERE snkrdunk_key = ?`,
  )
    .bind(snkrdunkKey)
    .run();
}

export async function listHiddenKeys(env: Env): Promise<string[]> {
  const r = await env.DB.prepare(
    `SELECT snkrdunk_key FROM snkrdunk_mappings WHERE disabled = 1`,
  ).all<{ snkrdunk_key: string }>();
  return (r.results ?? []).map((x) => x.snkrdunk_key);
}

export async function setMappingPacks(env: Env, snkrdunkKey: string, packsPerBox: number | null): Promise<void> {
  const exists = await env.DB.prepare(
    `SELECT id FROM snkrdunk_mappings WHERE snkrdunk_key = ?`,
  )
    .bind(snkrdunkKey)
    .first<{ id: number }>();
  if (!exists) throw new Error("Mapping not found");
  await env.DB.prepare(
    `UPDATE snkrdunk_mappings SET packs_per_box = ?, updated_at = unixepoch() WHERE snkrdunk_key = ?`,
  )
    .bind(packsPerBox, snkrdunkKey)
    .run();
}

// ============================================================================
// add-pack-variant — Shopify GraphQL flow (snkrdunk.py L609-738)
// ============================================================================
export async function addPackVariant(
  env: Env,
  productShopifyId: string,
  packPrice: number,
): Promise<{ ok: true; pack_variant_id: string }> {
  const shopify = new Shopify(env);

  // 1. Fetch product + options + variants.
  const data = await shopify.graphql<{
    product: {
      id: string;
      title: string;
      options: Array<{ id: string; name: string; values: string[]; optionValues?: Array<{ id: string; name: string }> }>;
      variants: { edges: Array<{ node: { id: string; title: string; price: string; selectedOptions: Array<{ name: string; value: string }> } }> };
    };
  }>(
    `query($id: ID!) {
      product(id: $id) {
        id title
        options(first: 5) { id name values optionValues { id name } }
        variants(first: 50) {
          edges { node { id title price selectedOptions { name value } } }
        }
      }
    }`,
    { id: productShopifyId },
  );

  if (!data.product) throw new Error("Product not found in Shopify");

  // 2. Ensure a "Type" option exists; rename "Title" → "Type" if needed.
  const opts = data.product.options;
  let typeOption = opts.find((o) => o.name.toLowerCase() === "type");
  if (!typeOption) {
    const titleOpt = opts.find((o) => o.name.toLowerCase() === "title");
    if (titleOpt) {
      await shopify.graphql(
        `mutation($productId: ID!, $option: OptionUpdateInput!) {
          productOptionUpdate(productId: $productId, option: $option) {
            userErrors { field message }
          }
        }`,
        { productId: productShopifyId, option: { id: titleOpt.id, name: "Type" } },
      );
      await sleep(300);
      typeOption = { ...titleOpt, name: "Type" };
    } else {
      throw new Error("No Title or Type option present on product");
    }
  }

  // 3. Add option values "Booster Box" and "Booster Pack" if missing.
  const existingValues = new Set((typeOption!.values ?? []).map((v) => v.toLowerCase()));
  const valuesToAdd: string[] = [];
  if (!existingValues.has("booster box")) valuesToAdd.push("Booster Box");
  if (!existingValues.has("booster pack")) valuesToAdd.push("Booster Pack");
  if (valuesToAdd.length > 0) {
    await shopify.graphql(
      `mutation($productId: ID!, $option: OptionUpdateInput!, $optionValuesToAdd: [OptionValueCreateInput!]) {
        productOptionUpdate(productId: $productId, option: $option, optionValuesToAdd: $optionValuesToAdd) {
          userErrors { field message }
        }
      }`,
      {
        productId: productShopifyId,
        option: { id: typeOption!.id },
        optionValuesToAdd: valuesToAdd.map((name) => ({ name })),
      },
    );
    await sleep(300);
  }

  // 4. Update existing variant(s) → "Booster Box".
  const firstVariant = data.product.variants.edges[0]?.node;
  if (firstVariant) {
    const currentVal = firstVariant.selectedOptions[0]?.value ?? "";
    if (currentVal.toLowerCase() !== "booster box") {
      await shopify.graphql(
        `mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
          productVariantsBulkUpdate(productId: $productId, variants: $variants) {
            userErrors { field message }
          }
        }`,
        {
          productId: productShopifyId,
          variants: [
            {
              id: firstVariant.id,
              optionValues: [{ optionId: typeOption!.id, name: "Booster Box" }],
            },
          ],
        },
      );
      await sleep(300);
    }
  }

  // 5. Create new "Booster Pack" variant.
  const create = await shopify.graphql<{
    productVariantsBulkCreate: {
      productVariants: Array<{ id: string }>;
      userErrors: Array<{ field: string[]; message: string }>;
    };
  }>(
    `mutation($productId: ID!, $variants: [ProductVariantsBulkInput!]!) {
      productVariantsBulkCreate(productId: $productId, variants: $variants) {
        productVariants { id }
        userErrors { field message }
      }
    }`,
    {
      productId: productShopifyId,
      variants: [
        {
          price: packPrice.toFixed(2),
          optionValues: [{ optionId: typeOption!.id, name: "Booster Pack" }],
          inventoryItem: { tracked: true },
        },
      ],
    },
  );
  const errs = create.productVariantsBulkCreate.userErrors;
  if (errs.length) throw new Error(`Shopify userErrors: ${JSON.stringify(errs)}`);
  const newVariantId = create.productVariantsBulkCreate.productVariants[0]?.id;
  if (!newVariantId) throw new Error("Shopify did not return new variant id");

  // 6. Cleanup "Default Title" option value if present.
  const defaultVal = typeOption!.optionValues?.find((ov) => ov.name === "Default Title");
  if (defaultVal) {
    await shopify.graphql(
      `mutation($productId: ID!, $option: OptionUpdateInput!, $optionValuesToDelete: [ID!]) {
        productOptionUpdate(productId: $productId, option: $option, optionValuesToDelete: $optionValuesToDelete) {
          userErrors { field message }
        }
      }`,
      {
        productId: productShopifyId,
        option: { id: typeOption!.id },
        optionValuesToDelete: [defaultVal.id],
      },
    );
  }

  // 7. Sync the new variant into local DB.
  const fullVariant = await shopify.getVariant(newVariantId);
  if (fullVariant) {
    const product = await env.DB.prepare(`SELECT id FROM products WHERE shopify_id = ?`)
      .bind(productShopifyId)
      .first<{ id: number }>();
    if (product) {
      await env.DB.prepare(
        `INSERT OR REPLACE INTO variants
          (shopify_id, shopify_numeric_id, product_id, inventory_item_id, title, sku, barcode,
           price, compare_at_price, inventory_quantity, option_name, option_value, updated_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Type', 'Booster Pack', unixepoch())`,
      )
        .bind(
          fullVariant.id,
          fullVariant.id.split("/").pop() ?? null,
          product.id,
          fullVariant.inventoryItem?.id ?? null,
          fullVariant.title,
          fullVariant.sku,
          fullVariant.barcode,
          Number(fullVariant.price),
          fullVariant.compareAtPrice ? Number(fullVariant.compareAtPrice) : null,
          fullVariant.inventoryQuantity ?? 0,
        )
        .run();
    }
  }

  await audit(env, "snkrdunk.add_pack_variant", {
    entityType: "product",
    entityId: productShopifyId,
    details: { pack_price: packPrice, new_variant_id: newVariantId },
  });
  return { ok: true, pack_variant_id: newVariantId };
}

// ============================================================================
// Cache wipe
// ============================================================================
export async function clearAllSnkrdunkCache(env: Env): Promise<number> {
  const r = await env.DB.prepare(`DELETE FROM snkrdunk_cache`).run();
  return r.meta.changes ?? 0;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
