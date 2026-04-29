/**
 * Kvitteringer (receipts) — local POS sales.
 *
 * Two flows:
 *   1. Cash-and-carry sale at the POS terminal: createReceipt → decrement
 *      Shopify inventory + render PDF → store in R2.
 *   2. Mirror of an existing Shopify order: import via shopifyOrderToReceipt
 *      (used when the customer paid online and we hand them the package).
 */
import type { Env } from "../lib/env.js";
import { Shopify } from "../lib/shopify.js";
import { audit, makeReference, nextSequence } from "../lib/db.js";
import { round2 } from "../lib/utils.js";
import { getConfig } from "../lib/config.js";

export interface ReceiptInput {
  customerName?: string;
  customerEmail?: string;
  paymentMethod?: "card" | "cash" | "vipps" | "other";
  cashierId?: string;
  discountNok?: number;
  notes?: string;
  items: Array<{
    variantShopifyId?: string;
    barcode?: string;
    description: string;
    quantity: number;
    unitPriceNok: number;
    isMarginVat?: boolean;
    marginVatPurchaseId?: number;
    vatRatePct?: number;
  }>;
}

export interface ReceiptResult {
  id: number;
  receiptNumber: string;
  totalNok: number;
}

export async function createReceipt(env: Env, input: ReceiptInput): Promise<ReceiptResult> {
  const year = new Date().getFullYear();
  const seq = await nextSequence(env, "receipt");
  const receiptNumber = makeReference("KVT", year, seq);

  let subtotal = 0;
  let vatTotal = 0;
  let marginVatTotal = 0;

  const defaultVatPct = Number(await getConfig(env, "VAT_RATE_PCT")) || 25;
  const computed = input.items.map((item) => {
    const lineGross = item.quantity * item.unitPriceNok;
    let vatAmount = 0;
    if (item.isMarginVat && item.marginVatPurchaseId) {
      // VAT will be looked up from margin_vat_items.vat_amount_nok at finalize step.
      vatAmount = 0; // placeholder, fixed below
    } else {
      const vatRate = item.vatRatePct ?? defaultVatPct;
      vatAmount = lineGross - lineGross / (1 + vatRate / 100);
    }
    return { item, lineGross: round2(lineGross), vatAmount: round2(vatAmount) };
  });

  for (const c of computed) {
    subtotal += c.lineGross;
    if (c.item.isMarginVat) marginVatTotal += c.vatAmount;
    else vatTotal += c.vatAmount;
  }
  const discount = input.discountNok ?? 0;
  const total = round2(subtotal - discount);

  const ins = await env.DB.prepare(
    `INSERT INTO receipts
      (receipt_number, customer_name, customer_email, payment_method,
       subtotal_nok, vat_total_nok, margin_vat_total_nok, discount_nok, total_nok,
       cashier_id, status, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?)`,
  )
    .bind(
      receiptNumber,
      input.customerName ?? null,
      input.customerEmail ?? null,
      input.paymentMethod ?? "card",
      round2(subtotal),
      round2(vatTotal),
      round2(marginVatTotal),
      discount,
      total,
      input.cashierId ?? null,
      input.notes ?? null,
    )
    .run();
  const receiptId = Number(ins.meta.last_row_id);

  // Insert line items (with margin VAT lookup if needed).
  for (const c of computed) {
    let vatAmount = c.vatAmount;
    if (c.item.isMarginVat && c.item.marginVatPurchaseId) {
      const mvItem = await env.DB.prepare(
        `SELECT vat_amount_nok FROM margin_vat_items
          WHERE purchase_id = ? AND variant_shopify_id = ?
          ORDER BY id LIMIT 1`,
      )
        .bind(c.item.marginVatPurchaseId, c.item.variantShopifyId ?? "")
        .first<{ vat_amount_nok: number | null }>();
      vatAmount = round2((mvItem?.vat_amount_nok ?? 0) * c.item.quantity);
    }

    await env.DB.prepare(
      `INSERT INTO receipt_items
        (receipt_id, variant_shopify_id, barcode, description, quantity,
         unit_price_nok, vat_rate_pct, is_margin_vat, margin_vat_purchase_id,
         vat_amount_nok, line_total_nok)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    )
      .bind(
        receiptId,
        c.item.variantShopifyId ?? null,
        c.item.barcode ?? null,
        c.item.description,
        c.item.quantity,
        c.item.unitPriceNok,
        c.item.vatRatePct ?? defaultVatPct,
        c.item.isMarginVat ? 1 : 0,
        c.item.marginVatPurchaseId ?? null,
        vatAmount,
        c.lineGross,
      )
      .run();
  }

  // Decrement Shopify inventory for each variant line.
  await decrementInventoryForReceipt(env, input.items);

  // Mark margin-VAT items as sold (so they're not re-used).
  for (const c of computed) {
    if (c.item.isMarginVat && c.item.marginVatPurchaseId && c.item.variantShopifyId) {
      await env.DB.prepare(
        `UPDATE margin_vat_items
            SET sold_receipt_id = ?, sold_at = unixepoch()
          WHERE purchase_id = ? AND variant_shopify_id = ? AND sold_receipt_id IS NULL`,
      )
        .bind(receiptId, c.item.marginVatPurchaseId, c.item.variantShopifyId)
        .run();
    }
  }

  // Render PDF (HTML for now — Workers-friendly; user can attach a print stylesheet).
  const html = await renderReceiptHtml(env, receiptId);
  const pdfKey = `receipts/${year}/${receiptNumber}.html`;
  await env.STORAGE.put(pdfKey, html, {
    httpMetadata: { contentType: "text/html; charset=utf-8" },
  });
  await env.DB.prepare("UPDATE receipts SET pdf_r2_key = ? WHERE id = ?")
    .bind(pdfKey, receiptId)
    .run();

  await audit(env, "receipt.create", {
    entityType: "receipt",
    entityId: receiptNumber,
    details: { total, items: input.items.length },
  });

  return { id: receiptId, receiptNumber, totalNok: total };
}

async function decrementInventoryForReceipt(
  env: Env,
  items: ReceiptInput["items"],
): Promise<void> {
  const locationId = await getConfig(env, "SHOPIFY_LOCATION_ID");
  if (!locationId) return;
  const locationGid = `gid://shopify/Location/${locationId.replace(/^gid:\/\/.*\//, "")}`;
  const shopify = new Shopify(env);
  for (const item of items) {
    if (!item.variantShopifyId || item.quantity <= 0) continue;
    const v = await env.DB.prepare(
      "SELECT inventory_item_id FROM variants WHERE shopify_id = ?",
    )
      .bind(item.variantShopifyId)
      .first<{ inventory_item_id: string | null }>();
    if (!v?.inventory_item_id) continue;
    try {
      await shopify.adjustInventory(v.inventory_item_id, locationGid, -item.quantity, "sale");
      await env.DB.prepare(
        "UPDATE variants SET inventory_quantity = inventory_quantity - ?, updated_at = unixepoch() WHERE shopify_id = ?",
      )
        .bind(item.quantity, item.variantShopifyId)
        .run();
    } catch (err) {
      // Log but don't fail the sale — inventory desync is recoverable, lost sale is not.
      await audit(env, "receipt.inventory_decrement_failed", {
        entityType: "variant",
        entityId: item.variantShopifyId,
        success: false,
        errorMessage: err instanceof Error ? err.message : String(err),
      });
    }
  }
}

export async function getReceipt(env: Env, id: number): Promise<{
  receipt: Record<string, unknown>;
  items: Array<Record<string, unknown>>;
} | null> {
  const receipt = await env.DB.prepare("SELECT * FROM receipts WHERE id = ?")
    .bind(id)
    .first<Record<string, unknown>>();
  if (!receipt) return null;
  const items = await env.DB.prepare("SELECT * FROM receipt_items WHERE receipt_id = ?")
    .bind(id)
    .all<Record<string, unknown>>();
  return { receipt, items: items.results ?? [] };
}

export async function listReceipts(env: Env, limit = 100): Promise<Array<Record<string, unknown>>> {
  const r = await env.DB.prepare(
    "SELECT * FROM receipts ORDER BY id DESC LIMIT ?",
  )
    .bind(Math.min(limit, 500))
    .all<Record<string, unknown>>();
  return r.results ?? [];
}

export async function renderReceiptHtml(env: Env, id: number): Promise<string> {
  const data = await getReceipt(env, id);
  if (!data) throw new Error(`receipt ${id} not found`);
  const { receipt: r, items } = data;

  const itemRows = items
    .map((it) => {
      const i = it as Record<string, unknown>;
      const desc = String(i.description);
      const qty = Number(i.quantity);
      const unit = Number(i.unit_price_nok).toFixed(2);
      const total = Number(i.line_total_nok).toFixed(2);
      const tag = Number(i.is_margin_vat) === 1 ? `<small style="color:#888"> (avansemoms)</small>` : "";
      return `<tr><td>${qty}×</td><td>${escapeHtml(desc)}${tag}</td><td style="text-align:right">${unit}</td><td style="text-align:right">${total}</td></tr>`;
    })
    .join("");

  const created = new Date(Number(r.created_at) * 1000).toLocaleString("nb-NO");
  const standardVat = Number(r.vat_total_nok).toFixed(2);
  const marginVat = Number(r.margin_vat_total_nok).toFixed(2);

  const companyName = (await getConfig(env, "COMPANY_NAME")) || "Pokelageret";
  const companyOrgNr = await getConfig(env, "COMPANY_ORG_NR");

  return `<!doctype html>
<html lang="nb"><head><meta charset="utf-8"><title>Kvittering ${r.receipt_number}</title>
<style>
  body{font-family:-apple-system,BlinkMacSystemFont,sans-serif;color:#111;max-width:480px;margin:24px auto;padding:0 16px;}
  h1{font-size:18px;margin:0;}
  .meta{color:#666;font-size:12px;margin:4px 0 16px;}
  table{width:100%;border-collapse:collapse;font-size:13px;}
  th,td{padding:4px 6px;}
  thead th{border-bottom:1px solid #ccc;text-align:left;}
  tfoot td{border-top:1px solid #ccc;font-weight:600;}
  .right{text-align:right;}
  .small{font-size:11px;color:#666;}
  @media print{body{margin:0;}}
</style></head><body>
  <h1>${escapeHtml(companyName)}</h1>
  <div class="meta">${companyOrgNr ? `Org.nr ${escapeHtml(companyOrgNr)} · ` : ""}${created}</div>
  <div class="meta">Kvittering <strong>${r.receipt_number}</strong> · ${escapeHtml(String(r.payment_method))}${r.customer_name ? ` · ${escapeHtml(String(r.customer_name))}` : ""}</div>

  <table>
    <thead><tr><th>Ant</th><th>Vare</th><th class="right">Pris</th><th class="right">Sum</th></tr></thead>
    <tbody>${itemRows}</tbody>
    <tfoot>
      <tr><td colspan="3" class="right">Sum</td><td class="right">${Number(r.subtotal_nok).toFixed(2)}</td></tr>
      ${Number(r.discount_nok) > 0 ? `<tr><td colspan="3" class="right">Rabatt</td><td class="right">-${Number(r.discount_nok).toFixed(2)}</td></tr>` : ""}
      <tr><td colspan="3" class="right">Totalt</td><td class="right">${Number(r.total_nok).toFixed(2)}</td></tr>
    </tfoot>
  </table>

  <p class="small">
    Herav MVA 25%: ${standardVat} kr${Number(marginVat) > 0 ? ` · Avansemoms: ${marginVat} kr` : ""}
  </p>
</body></html>`;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
