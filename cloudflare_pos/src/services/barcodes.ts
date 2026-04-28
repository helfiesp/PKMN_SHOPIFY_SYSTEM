/**
 * Barcode → variant linking.
 *
 * Lookup order:
 *   1. Local `barcodes` table (fast, indexed)
 *   2. Local `variants.barcode` (mirror from Shopify)
 *   3. Local `variants.sku` (some scanners encode SKU as a code-128)
 *   4. Shopify GraphQL search — last-resort fallback (also pulls latest data)
 *
 * Linking:
 *   - linkBarcode: stores in local table AND pushes to Shopify variant.barcode.
 *     Shopify is the source of truth for printed labels, so we always sync.
 */
import type { Env } from "../lib/env.js";
import { Shopify } from "../lib/shopify.js";
import { audit } from "../lib/db.js";

export interface BarcodeMatch {
  source: "local_barcode" | "local_variant_barcode" | "local_variant_sku" | "shopify";
  variantShopifyId: string;
  productShopifyId: string;
  productTitle: string;
  variantTitle: string | null;
  sku: string | null;
  barcode: string | null;
  price: number | null;
  inventoryQuantity: number;
  imageUrl: string | null;
}

export async function lookupBarcode(env: Env, code: string): Promise<BarcodeMatch | null> {
  const trimmed = code.trim();
  if (!trimmed) return null;

  // 1. barcodes table
  const local = await env.DB.prepare(
    `SELECT b.variant_shopify_id,
            b.product_shopify_id,
            v.title  AS v_title,
            v.sku    AS v_sku,
            v.barcode AS v_barcode,
            v.price  AS v_price,
            v.inventory_quantity AS v_qty,
            p.title  AS p_title,
            p.image_url AS p_image
       FROM barcodes b
       LEFT JOIN variants v ON v.shopify_id = b.variant_shopify_id
       LEFT JOIN products p ON p.shopify_id = b.product_shopify_id
      WHERE b.code = ?
      LIMIT 1`,
  )
    .bind(trimmed)
    .first<LookupRow>();

  if (local && local.variant_shopify_id) {
    return rowToMatch(local, "local_barcode");
  }

  // 2. variants.barcode mirror
  const v1 = await env.DB.prepare(
    `SELECT v.shopify_id AS variant_shopify_id,
            p.shopify_id AS product_shopify_id,
            v.title AS v_title, v.sku AS v_sku, v.barcode AS v_barcode,
            v.price AS v_price, v.inventory_quantity AS v_qty,
            p.title AS p_title, p.image_url AS p_image
       FROM variants v JOIN products p ON p.id = v.product_id
      WHERE v.barcode = ? LIMIT 1`,
  )
    .bind(trimmed)
    .first<LookupRow>();
  if (v1) return rowToMatch(v1, "local_variant_barcode");

  // 3. variants.sku
  const v2 = await env.DB.prepare(
    `SELECT v.shopify_id AS variant_shopify_id,
            p.shopify_id AS product_shopify_id,
            v.title AS v_title, v.sku AS v_sku, v.barcode AS v_barcode,
            v.price AS v_price, v.inventory_quantity AS v_qty,
            p.title AS p_title, p.image_url AS p_image
       FROM variants v JOIN products p ON p.id = v.product_id
      WHERE v.sku = ? LIMIT 1`,
  )
    .bind(trimmed)
    .first<LookupRow>();
  if (v2) return rowToMatch(v2, "local_variant_sku");

  // 4. Shopify fallback
  const shopify = new Shopify(env);
  const remote = (await shopify.findVariantByBarcode(trimmed)) ?? (await shopify.findVariantBySku(trimmed));
  if (!remote) return null;

  // Cache it so future scans hit local.
  await env.DB.prepare(
    `INSERT OR IGNORE INTO barcodes (code, variant_shopify_id, product_shopify_id, source)
     VALUES (?, ?, ?, 'shopify')`,
  )
    .bind(trimmed, remote.id, remote.product.id)
    .run();

  return {
    source: "shopify",
    variantShopifyId: remote.id,
    productShopifyId: remote.product.id,
    productTitle: remote.product.title,
    variantTitle: remote.title,
    sku: remote.sku,
    barcode: remote.barcode,
    price: remote.price ? Number(remote.price) : null,
    inventoryQuantity: remote.inventoryQuantity ?? 0,
    imageUrl: remote.product.featuredImage?.url ?? null,
  };
}

interface LookupRow {
  variant_shopify_id: string;
  product_shopify_id: string;
  v_title: string | null;
  v_sku: string | null;
  v_barcode: string | null;
  v_price: number | null;
  v_qty: number;
  p_title: string;
  p_image: string | null;
}

function rowToMatch(r: LookupRow, source: BarcodeMatch["source"]): BarcodeMatch {
  return {
    source,
    variantShopifyId: r.variant_shopify_id,
    productShopifyId: r.product_shopify_id,
    productTitle: r.p_title,
    variantTitle: r.v_title,
    sku: r.v_sku,
    barcode: r.v_barcode,
    price: r.v_price,
    inventoryQuantity: r.v_qty ?? 0,
    imageUrl: r.p_image,
  };
}

export async function linkBarcode(
  env: Env,
  code: string,
  variantShopifyId: string,
  opts: { isPrimary?: boolean; notes?: string; pushToShopify?: boolean } = {},
): Promise<void> {
  const variant = await env.DB.prepare(
    `SELECT v.shopify_id, p.shopify_id AS product_shopify_id
       FROM variants v JOIN products p ON p.id = v.product_id
      WHERE v.shopify_id = ?`,
  )
    .bind(variantShopifyId)
    .first<{ shopify_id: string; product_shopify_id: string }>();

  if (!variant) throw new Error(`Variant not found locally: ${variantShopifyId}`);

  await env.DB.prepare(
    `INSERT INTO barcodes (code, variant_shopify_id, product_shopify_id, is_primary, source, notes)
     VALUES (?, ?, ?, ?, 'manual', ?)
     ON CONFLICT(code, variant_shopify_id) DO UPDATE SET
       is_primary = excluded.is_primary,
       notes = excluded.notes,
       updated_at = unixepoch()`,
  )
    .bind(code, variantShopifyId, variant.product_shopify_id, opts.isPrimary === false ? 0 : 1, opts.notes ?? null)
    .run();

  if (opts.pushToShopify !== false) {
    const shopify = new Shopify(env);
    await shopify.productVariantsBulkUpdate(variant.product_shopify_id, [
      { id: variantShopifyId, barcode: code },
    ]);
    await env.DB.prepare("UPDATE variants SET barcode = ?, updated_at = unixepoch() WHERE shopify_id = ?")
      .bind(code, variantShopifyId)
      .run();
  }

  await audit(env, "barcode.link", {
    entityType: "variant",
    entityId: variantShopifyId,
    details: { code, pushed: opts.pushToShopify !== false },
  });
}

export async function unlinkBarcode(env: Env, code: string, variantShopifyId: string): Promise<void> {
  await env.DB.prepare(
    `DELETE FROM barcodes WHERE code = ? AND variant_shopify_id = ?`,
  )
    .bind(code, variantShopifyId)
    .run();
  await audit(env, "barcode.unlink", {
    entityType: "variant",
    entityId: variantShopifyId,
    details: { code },
  });
}
