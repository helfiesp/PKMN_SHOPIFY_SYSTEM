/**
 * Margin VAT (Norwegian avansemoms / brukmomsordningen).
 *
 * Used when buying second-hand goods from private sellers — VAT is paid only on
 * the margin (selling price - purchase price), not the full sale price.
 *
 * Math (matches the Python implementation):
 *   margin           = max(0, selling - purchase)
 *   vat_amount       = margin × 25 / 125
 *   effective_rate   = 100 × margin / (5 × selling - margin)   (% of selling price)
 *   bucket_rate      = min(25, effective_rate)                  (capped for Shopify)
 */
import type { Env } from "../lib/env.js";
import { audit, makeReference, nextSequence } from "../lib/db.js";
import { computeMarginVat, round2 } from "../lib/utils.js";

export interface MarginVatPurchaseInput {
  seller: string;
  sellerId?: string;
  purchaseDate: string;        // YYYY-MM-DD
  notes?: string;
  items: Array<{
    description: string;
    quantity: number;
    unitPurchasePriceNok: number;
    variantShopifyId?: string;
    sellingPriceNok?: number;
  }>;
}

export async function createMarginVatPurchase(
  env: Env,
  input: MarginVatPurchaseInput,
): Promise<{ id: number; reference: string; totalPurchaseNok: number }> {
  const year = new Date(input.purchaseDate).getFullYear();
  const seq = await nextSequence(env, "margin_vat");
  const reference = makeReference("MV", year, seq);

  const totalPurchaseNok = round2(
    input.items.reduce((s, i) => s + i.quantity * i.unitPurchasePriceNok, 0),
  );

  const ins = await env.DB.prepare(
    `INSERT INTO margin_vat_purchases
      (reference, seller, seller_id, purchase_date, total_purchase_nok, status, notes)
     VALUES (?, ?, ?, ?, ?, 'pending', ?)`,
  )
    .bind(
      reference,
      input.seller,
      input.sellerId ?? null,
      input.purchaseDate,
      totalPurchaseNok,
      input.notes ?? null,
    )
    .run();
  const id = Number(ins.meta.last_row_id);

  for (const item of input.items) {
    const calc = item.sellingPriceNok != null
      ? computeMarginVat(item.unitPurchasePriceNok, item.sellingPriceNok)
      : null;
    await env.DB.prepare(
      `INSERT INTO margin_vat_items
        (purchase_id, description, quantity, unit_purchase_price_nok, variant_shopify_id,
         selling_price_nok, margin_nok, vat_amount_nok, effective_rate_pct, bucket_rate_pct)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        id,
        item.description,
        item.quantity,
        item.unitPurchasePriceNok,
        item.variantShopifyId ?? null,
        item.sellingPriceNok ?? null,
        calc?.margin ?? null,
        calc?.vatAmount ?? null,
        calc?.effectiveRatePct ?? null,
        calc?.bucketRatePct ?? null,
      )
      .run();
  }

  await audit(env, "margin_vat.create", {
    entityType: "margin_vat_purchase",
    entityId: reference,
    details: { items: input.items.length, totalPurchaseNok },
  });
  return { id, reference, totalPurchaseNok };
}

/**
 * Update the intended selling price on a margin-VAT item, recompute margin/VAT,
 * and (optionally) flag for reassignment if the variant has changed.
 */
export async function setMarginVatItemSellingPrice(
  env: Env,
  itemId: number,
  sellingPriceNok: number,
  variantShopifyId?: string | null,
): Promise<{ margin: number; vatAmount: number; effectiveRatePct: number; bucketRatePct: number }> {
  const row = await env.DB.prepare(
    "SELECT unit_purchase_price_nok, variant_shopify_id FROM margin_vat_items WHERE id = ?",
  )
    .bind(itemId)
    .first<{ unit_purchase_price_nok: number; variant_shopify_id: string | null }>();
  if (!row) throw new Error(`margin VAT item ${itemId} not found`);

  const calc = computeMarginVat(row.unit_purchase_price_nok, sellingPriceNok);
  const reassign = variantShopifyId && row.variant_shopify_id && variantShopifyId !== row.variant_shopify_id ? 1 : 0;

  await env.DB.prepare(
    `UPDATE margin_vat_items
        SET selling_price_nok = ?, margin_nok = ?, vat_amount_nok = ?,
            effective_rate_pct = ?, bucket_rate_pct = ?, variant_shopify_id = COALESCE(?, variant_shopify_id),
            needs_reassignment = ?
      WHERE id = ?`,
  )
    .bind(
      sellingPriceNok,
      calc.margin,
      calc.vatAmount,
      calc.effectiveRatePct,
      calc.bucketRatePct,
      variantShopifyId ?? null,
      reassign,
      itemId,
    )
    .run();
  return calc;
}

export async function attachProofImage(
  env: Env,
  purchaseId: number,
  filename: string,
  contentType: string,
  body: ArrayBuffer | ReadableStream,
): Promise<{ r2Key: string; size: number }> {
  const safeName = filename.replace(/[^a-zA-Z0-9._-]/g, "_");
  const r2Key = `margin-vat/${purchaseId}/${Date.now()}-${safeName}`;
  const put = await env.STORAGE.put(r2Key, body as ArrayBuffer, {
    httpMetadata: { contentType },
  });
  const size = put?.size ?? 0;
  await env.DB.prepare(
    `INSERT INTO margin_vat_proof_images (purchase_id, filename, r2_key, content_type, file_size_bytes)
     VALUES (?, ?, ?, ?, ?)`,
  )
    .bind(purchaseId, filename, r2Key, contentType, size)
    .run();
  return { r2Key, size };
}

export async function getMarginVatPurchase(env: Env, id: number): Promise<{
  purchase: Record<string, unknown>;
  items: Array<Record<string, unknown>>;
  proofs: Array<Record<string, unknown>>;
} | null> {
  const purchase = await env.DB.prepare("SELECT * FROM margin_vat_purchases WHERE id = ?")
    .bind(id)
    .first<Record<string, unknown>>();
  if (!purchase) return null;
  const items = await env.DB.prepare("SELECT * FROM margin_vat_items WHERE purchase_id = ? ORDER BY id")
    .bind(id)
    .all<Record<string, unknown>>();
  const proofs = await env.DB.prepare("SELECT * FROM margin_vat_proof_images WHERE purchase_id = ?")
    .bind(id)
    .all<Record<string, unknown>>();
  return { purchase, items: items.results ?? [], proofs: proofs.results ?? [] };
}

export async function listMarginVatPurchases(env: Env, limit = 100): Promise<Array<Record<string, unknown>>> {
  const r = await env.DB.prepare(
    "SELECT * FROM margin_vat_purchases ORDER BY id DESC LIMIT ?",
  )
    .bind(Math.min(limit, 500))
    .all<Record<string, unknown>>();
  return r.results ?? [];
}
