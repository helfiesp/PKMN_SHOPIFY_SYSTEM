import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import {
  attachProofImage,
  createMarginVatPurchase,
  getMarginVatPurchase,
  listMarginVatPurchases,
  setMarginVatItemSellingPrice,
} from "../services/margin-vat.js";

export const marginVat = new Hono<AppContext>();

marginVat.get("/", async (c) => {
  const items = await listMarginVatPurchases(c.env, Number(c.req.query("limit") ?? 100));
  return c.json({ items });
});

marginVat.post("/", async (c) => {
  const body = await c.req.json<Parameters<typeof createMarginVatPurchase>[1]>();
  const result = await createMarginVatPurchase(c.env, body);
  return c.json({ ok: true, ...result });
});

marginVat.get("/:id{[0-9]+}", async (c) => {
  const detail = await getMarginVatPurchase(c.env, Number(c.req.param("id")));
  if (!detail) return c.json({ error: "not found" }, 404);
  return c.json(detail);
});

marginVat.put("/items/:id{[0-9]+}/selling-price", async (c) => {
  const body = await c.req.json<{ sellingPriceNok: number; variantShopifyId?: string | null }>();
  const calc = await setMarginVatItemSellingPrice(
    c.env,
    Number(c.req.param("id")),
    body.sellingPriceNok,
    body.variantShopifyId ?? null,
  );
  return c.json({ ok: true, ...calc });
});

/** Upload proof image (multipart/form-data, field "file"). Stored in R2. */
marginVat.post("/:id{[0-9]+}/proofs", async (c) => {
  const id = Number(c.req.param("id"));
  const form = await c.req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) return c.json({ error: "file required" }, 400);
  const buf = await file.arrayBuffer();
  const result = await attachProofImage(c.env, id, file.name, file.type || "application/octet-stream", buf);
  return c.json({ ok: true, ...result });
});

/** Stream proof image from R2. */
marginVat.get("/proofs/:r2Key{.+}", async (c) => {
  const r2Key = c.req.param("r2Key");
  const obj = await c.env.STORAGE.get(r2Key);
  if (!obj) return c.json({ error: "not found" }, 404);
  return new Response(obj.body, {
    headers: {
      "Content-Type": obj.httpMetadata?.contentType ?? "application/octet-stream",
      "Cache-Control": "private, max-age=300",
    },
  });
});
