/**
 * Stock dates — manage the Shopify product metafield `custom.stock_date`.
 *
 *  setStockDate         → set a future "in-stock" date on a product
 *  clearStockDate       → remove the metafield
 *  clearExpiredStockDates → cron-friendly: clear any dates that are <= today
 */
import type { Env } from "../lib/env.js";
import { Shopify } from "../lib/shopify.js";
import { audit } from "../lib/db.js";
import { todayISO } from "../lib/utils.js";

export async function setStockDate(env: Env, productShopifyId: string, dateISO: string, triggeredBy: "manual" | "cron" = "manual"): Promise<void> {
  const shopify = new Shopify(env);
  await shopify.setProductStockDate(productShopifyId, dateISO);
  await env.DB.prepare(
    `UPDATE products SET stock_date = ?, updated_at = unixepoch() WHERE shopify_id = ?`,
  )
    .bind(dateISO, productShopifyId)
    .run();
  await env.DB.prepare(
    `INSERT INTO stock_date_log (product_shopify_id, new_stock_date, action, triggered_by) VALUES (?, ?, 'set', ?)`,
  )
    .bind(productShopifyId, dateISO, triggeredBy)
    .run();
  await audit(env, "stock_date.set", { entityType: "product", entityId: productShopifyId, details: { dateISO, triggeredBy } });
}

export async function clearStockDate(env: Env, productShopifyId: string, triggeredBy: "manual" | "cron" | "sale" = "manual"): Promise<void> {
  const shopify = new Shopify(env);
  const old = await env.DB.prepare("SELECT stock_date FROM products WHERE shopify_id = ?")
    .bind(productShopifyId)
    .first<{ stock_date: string | null }>();
  await shopify.setProductStockDate(productShopifyId, null);
  await env.DB.prepare("UPDATE products SET stock_date = NULL, updated_at = unixepoch() WHERE shopify_id = ?")
    .bind(productShopifyId)
    .run();
  await env.DB.prepare(
    `INSERT INTO stock_date_log (product_shopify_id, old_stock_date, action, triggered_by) VALUES (?, ?, 'clear', ?)`,
  )
    .bind(productShopifyId, old?.stock_date ?? null, triggeredBy)
    .run();
  await audit(env, "stock_date.clear", { entityType: "product", entityId: productShopifyId, details: { triggeredBy } });
}

/**
 * Cron entrypoint: clear any stock_date that is on or before today.
 * Returns the list of cleared product IDs for visibility.
 */
export async function clearExpiredStockDates(env: Env): Promise<{ cleared: string[] }> {
  const today = todayISO();
  const rows = await env.DB.prepare(
    `SELECT shopify_id FROM products WHERE stock_date IS NOT NULL AND stock_date <= ?`,
  )
    .bind(today)
    .all<{ shopify_id: string }>();
  const cleared: string[] = [];
  for (const r of rows.results ?? []) {
    try {
      await clearStockDate(env, r.shopify_id, "cron");
      cleared.push(r.shopify_id);
    } catch (err) {
      await audit(env, "stock_date.auto_clear_failed", {
        entityType: "product",
        entityId: r.shopify_id,
        success: false,
        errorMessage: err instanceof Error ? err.message : String(err),
      });
    }
  }
  return { cleared };
}

export async function listProductsWithStockDate(env: Env): Promise<Array<Record<string, unknown>>> {
  const r = await env.DB.prepare(
    "SELECT shopify_id, title, handle, stock_date FROM products WHERE stock_date IS NOT NULL ORDER BY stock_date",
  ).all<Record<string, unknown>>();
  return r.results ?? [];
}
