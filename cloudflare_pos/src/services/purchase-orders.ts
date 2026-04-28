/**
 * Purchase orders — supplier purchases, JPY-denominated, FX snapshot per PO.
 * On status='received' we adjust Shopify inventory by the received quantity.
 */
import type { Env } from "../lib/env.js";
import { Shopify } from "../lib/shopify.js";
import { audit, makeReference, nextSequence } from "../lib/db.js";
import { getJpyToNokRate } from "./fx.js";
import { round2 } from "../lib/utils.js";

export interface PurchaseOrderInput {
  supplier?: string;
  orderDate: string;        // YYYY-MM-DD
  shippingCostJpy?: number;
  customsCostNok?: number;
  notes?: string;
  items: Array<{
    variantShopifyId?: string;
    description: string;
    quantity: number;
    unitPriceJpy: number;
    weightGrams?: number;
  }>;
}

export async function createPurchaseOrder(env: Env, input: PurchaseOrderInput): Promise<{
  id: number;
  reference: string;
  totalJpy: number;
  totalNok: number;
  fxRate: number;
}> {
  const fxRate = await getJpyToNokRate(env);
  const itemsTotalJpy = input.items.reduce((s, i) => s + i.quantity * i.unitPriceJpy, 0);
  const totalJpy = itemsTotalJpy + (input.shippingCostJpy ?? 0);
  const totalNok = round2(totalJpy * fxRate + (input.customsCostNok ?? 0));

  const year = new Date(input.orderDate).getFullYear();
  const seq = await nextSequence(env, "purchase_order");
  const reference = makeReference("PO", year, seq);

  const ins = await env.DB.prepare(
    `INSERT INTO purchase_orders
      (reference, supplier, order_date, shipping_cost_jpy, customs_cost_nok,
       total_jpy, total_nok, fx_rate_snapshot, status, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?)`,
  )
    .bind(
      reference,
      input.supplier ?? null,
      input.orderDate,
      input.shippingCostJpy ?? 0,
      input.customsCostNok ?? 0,
      totalJpy,
      totalNok,
      fxRate,
      input.notes ?? null,
    )
    .run();
  const id = Number(ins.meta.last_row_id);

  for (const item of input.items) {
    await env.DB.prepare(
      `INSERT INTO purchase_order_items
        (purchase_order_id, variant_shopify_id, description, quantity, unit_price_jpy, weight_grams)
       VALUES (?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        id,
        item.variantShopifyId ?? null,
        item.description,
        item.quantity,
        item.unitPriceJpy,
        item.weightGrams ?? null,
      )
      .run();
  }

  await audit(env, "po.create", { entityType: "purchase_order", entityId: reference, details: { totalJpy, totalNok, fxRate } });
  return { id, reference, totalJpy, totalNok, fxRate };
}

export async function getPurchaseOrder(env: Env, id: number): Promise<{
  order: Record<string, unknown>;
  items: Array<Record<string, unknown>>;
} | null> {
  const order = await env.DB.prepare("SELECT * FROM purchase_orders WHERE id = ?")
    .bind(id)
    .first<Record<string, unknown>>();
  if (!order) return null;
  const items = await env.DB.prepare("SELECT * FROM purchase_order_items WHERE purchase_order_id = ?")
    .bind(id)
    .all<Record<string, unknown>>();
  return { order, items: items.results ?? [] };
}

export async function listPurchaseOrders(
  env: Env,
  opts: { status?: string; limit?: number } = {},
): Promise<Array<Record<string, unknown>>> {
  const limit = Math.min(opts.limit ?? 100, 500);
  if (opts.status) {
    const r = await env.DB.prepare(
      "SELECT * FROM purchase_orders WHERE status = ? ORDER BY id DESC LIMIT ?",
    )
      .bind(opts.status, limit)
      .all<Record<string, unknown>>();
    return r.results ?? [];
  }
  const r = await env.DB.prepare("SELECT * FROM purchase_orders ORDER BY id DESC LIMIT ?")
    .bind(limit)
    .all<Record<string, unknown>>();
  return r.results ?? [];
}

/**
 * Mark PO as received and push inventory adjustments to Shopify.
 * Pass `receivedQuantities` to override (partial receive); otherwise full quantities.
 */
export async function receivePurchaseOrder(
  env: Env,
  id: number,
  receivedQuantities?: Record<number, number>,
): Promise<{ updatedItems: number; shopifyAdjustments: number }> {
  const detail = await getPurchaseOrder(env, id);
  if (!detail) throw new Error(`PO ${id} not found`);
  const items = detail.items as Array<{
    id: number;
    variant_shopify_id: string | null;
    quantity: number;
  }>;

  const shopify = new Shopify(env);
  const locationGid = env.SHOPIFY_LOCATION_ID
    ? `gid://shopify/Location/${env.SHOPIFY_LOCATION_ID.replace(/^gid:\/\/.*\//, "")}`
    : null;

  let updated = 0;
  let adjusted = 0;

  for (const item of items) {
    const qty = receivedQuantities?.[item.id] ?? item.quantity;
    await env.DB.prepare(
      "UPDATE purchase_order_items SET received_quantity = ? WHERE id = ?",
    )
      .bind(qty, item.id)
      .run();
    updated++;

    if (item.variant_shopify_id && locationGid && qty > 0) {
      // Need inventory_item_id from local cache.
      const v = await env.DB.prepare(
        "SELECT inventory_item_id FROM variants WHERE shopify_id = ?",
      )
        .bind(item.variant_shopify_id)
        .first<{ inventory_item_id: string | null }>();
      if (v?.inventory_item_id) {
        await shopify.adjustInventory(v.inventory_item_id, locationGid, qty, "received");
        await env.DB.prepare(
          "UPDATE variants SET inventory_quantity = inventory_quantity + ?, updated_at = unixepoch() WHERE shopify_id = ?",
        )
          .bind(qty, item.variant_shopify_id)
          .run();
        adjusted++;
      }
    }
  }

  await env.DB.prepare(
    "UPDATE purchase_orders SET status = 'received', received_at = unixepoch(), updated_at = unixepoch() WHERE id = ?",
  )
    .bind(id)
    .run();

  await audit(env, "po.receive", {
    entityType: "purchase_order",
    entityId: String(id),
    details: { updated, adjusted },
  });
  return { updatedItems: updated, shopifyAdjustments: adjusted };
}
