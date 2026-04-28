import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import {
  createPurchaseOrder,
  getPurchaseOrder,
  listPurchaseOrders,
  receivePurchaseOrder,
} from "../services/purchase-orders.js";

export const purchaseOrders = new Hono<AppContext>();

purchaseOrders.get("/", async (c) => {
  const status = c.req.query("status");
  const limit = Number(c.req.query("limit") ?? 100);
  const list = await listPurchaseOrders(c.env, { status: status ?? undefined, limit });
  return c.json({ items: list });
});

purchaseOrders.post("/", async (c) => {
  const body = await c.req.json<Parameters<typeof createPurchaseOrder>[1]>();
  const result = await createPurchaseOrder(c.env, body);
  return c.json({ ok: true, ...result });
});

purchaseOrders.get("/:id{[0-9]+}", async (c) => {
  const detail = await getPurchaseOrder(c.env, Number(c.req.param("id")));
  if (!detail) return c.json({ error: "not found" }, 404);
  return c.json(detail);
});

purchaseOrders.post("/:id{[0-9]+}/receive", async (c) => {
  const body = await c.req.json<{ quantities?: Record<number, number> }>().catch(() => ({}));
  const result = await receivePurchaseOrder(c.env, Number(c.req.param("id")), body.quantities);
  return c.json({ ok: true, ...result });
});
