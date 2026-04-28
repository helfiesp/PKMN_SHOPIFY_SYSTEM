import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import { getSetting, setSetting } from "../lib/db.js";

export const settings = new Hono<AppContext>();

settings.get("/", async (c) => {
  const r = await c.env.DB.prepare(
    "SELECT key, value, description, updated_at FROM settings ORDER BY key",
  ).all<Record<string, unknown>>();
  return c.json({ items: r.results ?? [] });
});

settings.get("/:key", async (c) => {
  const v = await getSetting(c.env, c.req.param("key"));
  if (v === null) return c.json({ error: "not found" }, 404);
  return c.json({ key: c.req.param("key"), value: v });
});

settings.put("/:key", async (c) => {
  const body = await c.req.json<{ value: string; description?: string }>();
  await setSetting(c.env, c.req.param("key"), body.value, body.description);
  return c.json({ ok: true });
});
