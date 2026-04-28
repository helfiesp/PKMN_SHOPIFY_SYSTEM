import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import {
  clearExpiredStockDates,
  clearStockDate,
  listProductsWithStockDate,
  setStockDate,
} from "../services/stock-dates.js";

export const stockDates = new Hono<AppContext>();

stockDates.get("/", async (c) => {
  const items = await listProductsWithStockDate(c.env);
  return c.json({ items });
});

stockDates.post("/:productId{.+}", async (c) => {
  const body = await c.req.json<{ date: string }>();
  await setStockDate(c.env, c.req.param("productId"), body.date);
  return c.json({ ok: true });
});

stockDates.delete("/:productId{.+}", async (c) => {
  await clearStockDate(c.env, c.req.param("productId"));
  return c.json({ ok: true });
});

/** Manual trigger of the daily clear job (cron does this automatically). */
stockDates.post("/clear-expired", async (c) => {
  const result = await clearExpiredStockDates(c.env);
  return c.json({ ok: true, ...result });
});
