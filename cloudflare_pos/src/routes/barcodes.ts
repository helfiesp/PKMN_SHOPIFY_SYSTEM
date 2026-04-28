import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import { linkBarcode, lookupBarcode, unlinkBarcode } from "../services/barcodes.js";

export const barcodes = new Hono<AppContext>();

/** POS scan endpoint: returns the matching variant or null. */
barcodes.get("/lookup/:code", async (c) => {
  const code = c.req.param("code");
  const match = await lookupBarcode(c.env, code);
  if (!match) return c.json({ found: false }, 404);
  return c.json({ found: true, ...match });
});

/** Link a (newly scanned) code to a variant. Pushes barcode to Shopify too. */
barcodes.post("/link", async (c) => {
  const body = await c.req.json<{
    code: string;
    variantShopifyId: string;
    isPrimary?: boolean;
    notes?: string;
    pushToShopify?: boolean;
  }>();
  await linkBarcode(c.env, body.code, body.variantShopifyId, {
    isPrimary: body.isPrimary,
    notes: body.notes,
    pushToShopify: body.pushToShopify,
  });
  return c.json({ ok: true });
});

barcodes.post("/unlink", async (c) => {
  const body = await c.req.json<{ code: string; variantShopifyId: string }>();
  await unlinkBarcode(c.env, body.code, body.variantShopifyId);
  return c.json({ ok: true });
});

barcodes.get("/list/:variantId{.+}", async (c) => {
  const r = await c.env.DB.prepare(
    "SELECT * FROM barcodes WHERE variant_shopify_id = ? ORDER BY id DESC",
  )
    .bind(c.req.param("variantId"))
    .all<Record<string, unknown>>();
  return c.json({ codes: r.results ?? [] });
});
