import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import { Shopify } from "../lib/shopify.js";
import { syncCollection } from "../services/shopify-sync.js";
import { getConfig } from "../lib/config.js";

export const shopify = new Hono<AppContext>();

shopify.post("/sync/:collectionId", async (c) => {
  const collectionId = c.req.param("collectionId");
  const result = await syncCollection(c.env, collectionId);
  return c.json({ ok: true, ...result });
});

shopify.post("/sync/default", async (c) => {
  const collectionId = await getConfig(c.env, "SHOPIFY_DEFAULT_COLLECTION_ID");
  if (!collectionId) return c.json({ error: "SHOPIFY_DEFAULT_COLLECTION_ID not configured" }, 400);
  const result = await syncCollection(c.env, collectionId);
  return c.json({ ok: true, ...result });
});

shopify.get("/products", async (c) => {
  const search = c.req.query("q") ?? "";
  const limit = Math.min(Number(c.req.query("limit") ?? 50), 200);
  const stmt = search
    ? c.env.DB.prepare(
        `SELECT p.shopify_id, p.title, p.handle, p.image_url, p.stock_date,
                v.shopify_id AS variant_id, v.title AS variant_title, v.sku, v.barcode,
                v.price, v.inventory_quantity
           FROM products p
           JOIN variants v ON v.product_id = p.id
          WHERE p.title LIKE ? OR v.sku LIKE ? OR v.barcode LIKE ?
          ORDER BY p.title LIMIT ?`,
      ).bind(`%${search}%`, `%${search}%`, `%${search}%`, limit)
    : c.env.DB.prepare(
        `SELECT p.shopify_id, p.title, p.handle, p.image_url, p.stock_date,
                v.shopify_id AS variant_id, v.title AS variant_title, v.sku, v.barcode,
                v.price, v.inventory_quantity
           FROM products p
           JOIN variants v ON v.product_id = p.id
          ORDER BY p.title LIMIT ?`,
      ).bind(limit);
  const r = await stmt.all<Record<string, unknown>>();
  return c.json({ items: r.results ?? [] });
});

shopify.get("/variant/:gid{.+}", async (c) => {
  const gid = c.req.param("gid");
  const v = await new Shopify(c.env).getVariant(gid);
  if (!v) return c.json({ error: "not found" }, 404);
  return c.json(v);
});

shopify.post("/variant/:gid{.+}/price", async (c) => {
  const gid = c.req.param("gid");
  const body = await c.req.json<{ price: number; productId: string }>();
  await new Shopify(c.env).productVariantsBulkUpdate(body.productId, [
    { id: gid, price: body.price.toFixed(2) },
  ]);
  await c.env.DB.prepare("UPDATE variants SET price = ? WHERE shopify_id = ?")
    .bind(body.price, gid)
    .run();
  await c.env.DB.prepare(
    `INSERT INTO price_change_logs (variant_shopify_id, product_shopify_id, new_price, change_type)
     VALUES (?, ?, ?, 'manual')`,
  )
    .bind(gid, body.productId, body.price)
    .run();
  return c.json({ ok: true });
});

shopify.post("/variant/:gid{.+}/inventory", async (c) => {
  const gid = c.req.param("gid");
  const body = await c.req.json<{ quantity: number; mode?: "set" | "adjust" }>();
  const locationId = await getConfig(c.env, "SHOPIFY_LOCATION_ID");
  if (!locationId) return c.json({ error: "SHOPIFY_LOCATION_ID not configured" }, 400);
  const locationGid = `gid://shopify/Location/${locationId.replace(/^gid:\/\/.*\//, "")}`;
  const v = await c.env.DB.prepare("SELECT inventory_item_id FROM variants WHERE shopify_id = ?")
    .bind(gid)
    .first<{ inventory_item_id: string | null }>();
  if (!v?.inventory_item_id) return c.json({ error: "inventory_item_id missing — sync the collection first" }, 400);
  const shopify = new Shopify(c.env);
  if (body.mode === "adjust") {
    await shopify.adjustInventory(v.inventory_item_id, locationGid, body.quantity, "correction");
    await c.env.DB.prepare(
      "UPDATE variants SET inventory_quantity = inventory_quantity + ?, updated_at = unixepoch() WHERE shopify_id = ?",
    )
      .bind(body.quantity, gid)
      .run();
  } else {
    await shopify.setInventoryQuantity(v.inventory_item_id, locationGid, body.quantity, "correction");
    await c.env.DB.prepare(
      "UPDATE variants SET inventory_quantity = ?, updated_at = unixepoch() WHERE shopify_id = ?",
    )
      .bind(body.quantity, gid)
      .run();
  }
  return c.json({ ok: true });
});
