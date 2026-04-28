/**
 * Full surface of /api/v1/snkrdunk/* — mirrors app/routers/snkrdunk.py.
 */
import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import {
  addPackVariant,
  clearAllSnkrdunkCache,
  executeAutoUpdate,
  fetchAndCacheSingleProduct,
  fetchAndCacheSnkrdunk,
  fetchJpyNokRate,
  getAllSnkSettings,
  getCachedProducts,
  hideProduct,
  listHiddenKeys,
  listManualProducts,
  removeManualProduct,
  runSnkrdunkCronCycle,
  saveSnkSettings,
  sendTestEmail,
  setMappingPacks,
  unhideProduct,
} from "../services/snkrdunk.js";

export const snkrdunk = new Hono<AppContext>();

// ── Settings ────────────────────────────────────────────────────────────────
snkrdunk.get("/settings", async (c) => c.json(await getAllSnkSettings(c.env)));

snkrdunk.put("/settings", async (c) => {
  const body = await c.req.json<Record<string, string | undefined>>();
  const updated = await saveSnkSettings(c.env, body);
  return c.json({ updated });
});

// ── Exchange rate ───────────────────────────────────────────────────────────
snkrdunk.get("/exchange-rate", async (c) => {
  const rate = await fetchJpyNokRate(c.env);
  return c.json({ rate });
});

// ── Hide / unhide ───────────────────────────────────────────────────────────
snkrdunk.post("/hide/:key", async (c) => {
  await hideProduct(c.env, c.req.param("key"));
  return c.json({ snkrdunk_key: c.req.param("key"), hidden: true });
});

snkrdunk.post("/unhide/:key", async (c) => {
  await unhideProduct(c.env, c.req.param("key"));
  return c.json({ snkrdunk_key: c.req.param("key"), hidden: false });
});

snkrdunk.get("/hidden", async (c) => c.json(await listHiddenKeys(c.env)));

// ── Mapping packs override ──────────────────────────────────────────────────
snkrdunk.put("/mappings/:key/packs", async (c) => {
  const body = await c.req.json<{ packs_per_box: number | null }>();
  try {
    await setMappingPacks(c.env, c.req.param("key"), body.packs_per_box);
  } catch (err) {
    return c.json({ error: (err as Error).message }, 404);
  }
  return c.json({ snkrdunk_key: c.req.param("key"), packs_per_box: body.packs_per_box });
});

// ── Mapping create / list / delete ──────────────────────────────────────────
snkrdunk.get("/mappings", async (c) => {
  const r = await c.env.DB.prepare(
    `SELECT m.*, p.title AS product_title, p.image_url AS product_image
       FROM snkrdunk_mappings m
       LEFT JOIN products p ON p.shopify_id = m.product_shopify_id
       ORDER BY m.id DESC`,
  ).all<Record<string, unknown>>();
  return c.json({ mappings: r.results ?? [] });
});

snkrdunk.post("/mappings", async (c) => {
  const body = await c.req.json<{
    snkrdunk_key: string;
    product_shopify_id: string;
    variant_shopify_id?: string;
    series_en?: string;
    name_short?: string;
    type_en?: string;
    packs_per_box?: number;
    notes?: string;
  }>();
  await c.env.DB.prepare(
    `INSERT INTO snkrdunk_mappings
      (snkrdunk_key, product_shopify_id, variant_shopify_id, series_en, name_short, type_en, packs_per_box, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(snkrdunk_key) DO UPDATE SET
       product_shopify_id = excluded.product_shopify_id,
       variant_shopify_id = excluded.variant_shopify_id,
       series_en = excluded.series_en,
       name_short = excluded.name_short,
       type_en = excluded.type_en,
       packs_per_box = excluded.packs_per_box,
       notes = excluded.notes,
       disabled = 0,
       updated_at = unixepoch()`,
  )
    .bind(
      body.snkrdunk_key,
      body.product_shopify_id,
      body.variant_shopify_id ?? null,
      body.series_en ?? null,
      body.name_short ?? null,
      body.type_en ?? null,
      body.packs_per_box ?? null,
      body.notes ?? null,
    )
    .run();
  return c.json({ ok: true });
});

snkrdunk.delete("/mappings/:id{[0-9]+}", async (c) => {
  await c.env.DB.prepare(`DELETE FROM snkrdunk_mappings WHERE id = ?`)
    .bind(Number(c.req.param("id")))
    .run();
  return c.json({ ok: true });
});

// ── Auto-update ────────────────────────────────────────────────────────────
snkrdunk.post("/auto-update", async (c) => c.json(await executeAutoUpdate(c.env)));

// ── Fetch (cache + auto-paginate + optional auto-update) ────────────────────
snkrdunk.post("/fetch", async (c) => {
  const body = await c.req
    .json<{ pages?: number[]; force_refresh?: boolean }>()
    .catch(() => ({ pages: [1], force_refresh: false }));
  const pages = body.pages ?? [1];
  const forceRefresh = body.force_refresh ?? false;

  const startedAt = Date.now();
  const ins = await c.env.DB.prepare(
    `INSERT INTO snkrdunk_scan_logs (status, trigger, started_at) VALUES ('running', 'manual', unixepoch())`,
  ).run();
  const scanLogId = Number(ins.meta.last_row_id);

  try {
    const result = await fetchAndCacheSnkrdunk(c.env, pages, forceRefresh);

    // Snapshot prices into history.
    const stmts = result.items
      .filter((i) => typeof i.minPrice === "number" && (i.minPrice as number) > 0)
      .map((i) =>
        c.env.DB.prepare(
          `INSERT INTO snkrdunk_price_history (scan_log_id, snkrdunk_key, price_jpy) VALUES (?, ?, ?)`,
        ).bind(scanLogId, String(i.id), i.minPrice as number),
      );
    for (let i = 0; i < stmts.length; i += 50) {
      await c.env.DB.batch(stmts.slice(i, i + 50));
    }

    let autoUpdate: Awaited<ReturnType<typeof executeAutoUpdate>> | undefined;
    if ((await c.env.DB.prepare(`SELECT value FROM settings WHERE key = 'snk_auto_update'`).first<{ value: string }>())?.value === "true") {
      autoUpdate = await executeAutoUpdate(c.env);
    }

    const durationMs = Date.now() - startedAt;
    await c.env.DB.prepare(
      `UPDATE snkrdunk_scan_logs
          SET status = 'success', completed_at = unixepoch(),
              duration_ms = ?, total_items = ?, matched_items = ?, updated_items = ?,
              email_sent = ?
        WHERE id = ?`,
    )
      .bind(
        durationMs,
        result.total_items,
        autoUpdate?.processed ?? null,
        autoUpdate?.pushed ?? null,
        autoUpdate ? 1 : 0,
        scanLogId,
      )
      .run();

    return c.json({
      total_items: result.total_items,
      pages_fetched: result.pages_fetched,
      manual_refreshed: result.manual_refreshed,
      cached_at: result.cached_at,
      log_id: scanLogId,
      auto_update: autoUpdate
        ? { pushed: autoUpdate.pushed, errors: autoUpdate.errors.length }
        : undefined,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    await c.env.DB.prepare(
      `UPDATE snkrdunk_scan_logs SET status = 'failed', completed_at = unixepoch(),
        error_message = ?, duration_ms = ? WHERE id = ?`,
    )
      .bind(msg, Date.now() - startedAt, scanLogId)
      .run();
    return c.json({ error: msg }, 500);
  }
});

// Convenience: full cron cycle (fetch + auto-update + email)
snkrdunk.post("/run", async (c) => c.json(await runSnkrdunkCronCycle(c.env, "manual")));

// ── Test email ─────────────────────────────────────────────────────────────
snkrdunk.post("/test-email", async (c) => {
  const r = await sendTestEmail(c.env);
  if (!r.success) return c.json(r, 400);
  return c.json(r);
});

// ── Manual products ────────────────────────────────────────────────────────
snkrdunk.post("/add-manual", async (c) => {
  const body = await c.req.json<{ url?: string; snkrdunk_id?: string }>();
  let productId: number | null = null;

  if (body.url) {
    const m = body.url.match(/\/apparels\/(\d+)/);
    if (m && m[1]) productId = Number(m[1]);
    else if (/^\d+$/.test(body.url.trim())) productId = Number(body.url.trim());
  } else if (body.snkrdunk_id) {
    const s = body.snkrdunk_id.trim();
    if (/^\d+$/.test(s)) productId = Number(s);
  }
  if (!productId) {
    return c.json(
      {
        error: "Could not parse a SNKRDUNK product ID. Provide a URL like https://snkrdunk.com/apparels/550896 or a numeric ID.",
      },
      400,
    );
  }

  const existed = await c.env.DB.prepare(
    `SELECT 1 FROM snkrdunk_cache WHERE brand_id = 'manual' AND page = ?`,
  )
    .bind(productId)
    .first();

  try {
    const result = await fetchAndCacheSingleProduct(c.env, productId);
    return c.json({
      message: `Product added: ${result.nameEn || productId}`,
      product: result,
      already_existed: existed != null,
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    if (msg.includes("not found")) return c.json({ error: msg }, 404);
    return c.json({ error: `Failed to fetch product: ${msg}` }, 500);
  }
});

snkrdunk.delete("/manual/:key{[0-9]+}", async (c) => {
  const key = Number(c.req.param("key"));
  const removed = await removeManualProduct(c.env, key);
  if (!removed) return c.json({ error: `Manual product ${key} not found` }, 404);
  return c.json({ removed: true });
});

snkrdunk.get("/manual", async (c) => {
  const items = await listManualProducts(c.env);
  return c.json({ items, total: items.length });
});

// ── Cached products (normalized) ───────────────────────────────────────────
snkrdunk.get("/products", async (c) => {
  const includeExpired = c.req.query("include_expired") === "true";
  const translate = c.req.query("translate") !== "false";
  const scanLogIdQ = c.req.query("scan_log_id");
  const scanLogId = scanLogIdQ ? Number(scanLogIdQ) : null;
  const items = await getCachedProducts(c.env, { includeExpired, translate, scanLogId });
  return c.json({ total_items: items.length, items });
});

// ── Scan logs ──────────────────────────────────────────────────────────────
snkrdunk.get("/scan-logs", async (c) => {
  const limit = Math.min(Number(c.req.query("limit") ?? 50), 200);
  const r = await c.env.DB.prepare(
    `SELECT * FROM snkrdunk_scan_logs ORDER BY id DESC LIMIT ?`,
  )
    .bind(limit)
    .all<Record<string, unknown>>();
  return c.json(r.results ?? []);
});

snkrdunk.get("/scan-logs/:id{[0-9]+}", async (c) => {
  const r = await c.env.DB.prepare(`SELECT * FROM snkrdunk_scan_logs WHERE id = ?`)
    .bind(Number(c.req.param("id")))
    .first<Record<string, unknown>>();
  if (!r) return c.json({ error: "not found" }, 404);
  return c.json(r);
});

// ── Price history ──────────────────────────────────────────────────────────
snkrdunk.get("/price-history", async (c) => {
  const logIdQ = c.req.query("log_id");
  if (!logIdQ) return c.json({ error: "log_id required" }, 400);
  const logId = Number(logIdQ);
  const limit = Math.min(Number(c.req.query("limit") ?? 200), 1000);
  const log = await c.env.DB.prepare(`SELECT * FROM snkrdunk_scan_logs WHERE id = ?`)
    .bind(logId)
    .first<Record<string, unknown>>();
  if (!log) return c.json({ error: "log not found" }, 404);
  const items = await c.env.DB.prepare(
    `SELECT snkrdunk_key, price_jpy, recorded_at
       FROM snkrdunk_price_history WHERE scan_log_id = ? ORDER BY id ASC LIMIT ?`,
  )
    .bind(logId, limit)
    .all<Record<string, unknown>>();
  return c.json({
    log_id: logId,
    scan_date: log.started_at,
    item_count: items.results?.length ?? 0,
    items: items.results ?? [],
  });
});

// ── Add pack variant (Shopify variant split) ───────────────────────────────
snkrdunk.post("/add-pack-variant", async (c) => {
  const body = await c.req.json<{ product_shopify_id: string; pack_price: number }>();
  if (!body.product_shopify_id || typeof body.pack_price !== "number") {
    return c.json({ error: "product_shopify_id and pack_price required" }, 400);
  }
  try {
    const r = await addPackVariant(c.env, body.product_shopify_id, body.pack_price);
    return c.json(r);
  } catch (err) {
    return c.json({ error: (err as Error).message }, 500);
  }
});

// ── Cache wipe ─────────────────────────────────────────────────────────────
snkrdunk.delete("/cache", async (c) => {
  const removed = await clearAllSnkrdunkCache(c.env);
  return c.json({ ok: true, removed });
});
