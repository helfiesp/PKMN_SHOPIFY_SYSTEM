import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import {
  createReceipt,
  getReceipt,
  listReceipts,
  renderReceiptHtml,
} from "../services/receipts.js";

export const receipts = new Hono<AppContext>();

receipts.get("/", async (c) => {
  const items = await listReceipts(c.env, Number(c.req.query("limit") ?? 100));
  return c.json({ items });
});

receipts.post("/", async (c) => {
  const body = await c.req.json<Parameters<typeof createReceipt>[1]>();
  const result = await createReceipt(c.env, body);
  return c.json({ ok: true, ...result });
});

receipts.get("/:id{[0-9]+}", async (c) => {
  const detail = await getReceipt(c.env, Number(c.req.param("id")));
  if (!detail) return c.json({ error: "not found" }, 404);
  return c.json(detail);
});

receipts.get("/:id{[0-9]+}/print", async (c) => {
  const html = await renderReceiptHtml(c.env, Number(c.req.param("id")));
  return c.html(html);
});
