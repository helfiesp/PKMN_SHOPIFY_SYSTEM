/**
 * /api/v1/config — user-editable runtime config (DB-backed, env-fallback).
 * See src/lib/config.ts for the full key list.
 */
import { Hono } from "hono";
import type { AppContext } from "../lib/env.js";
import { CONFIG_KEYS, getAllConfig, setConfig, type ConfigKey } from "../lib/config.js";

export const config = new Hono<AppContext>();

config.get("/", async (c) => {
  const values = await getAllConfig(c.env);
  return c.json({
    items: CONFIG_KEYS.map((meta) => ({
      ...meta,
      value: values[meta.key],
      isSecret: false,
    })),
  });
});

config.put("/", async (c) => {
  const body = await c.req.json<Record<string, string>>();
  const updated: string[] = [];
  for (const meta of CONFIG_KEYS) {
    const v = body[meta.key];
    if (v == null) continue;
    await setConfig(c.env, meta.key as ConfigKey, v);
    updated.push(meta.key);
  }
  return c.json({ ok: true, updated });
});
