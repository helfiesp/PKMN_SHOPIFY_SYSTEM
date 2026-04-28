import { Hono } from "hono";
import { setCookie, deleteCookie } from "hono/cookie";
import type { AppContext } from "../lib/env.js";
import { signSession, SESSION_COOKIE_NAME } from "../lib/auth.js";

const SEVEN_DAYS_MS = 7 * 24 * 3600 * 1000;

export const auth = new Hono<AppContext>();

auth.post("/login", async (c) => {
  const body = await c.req.json<{ pin?: string }>().catch(() => ({}));
  const expected = c.env.POS_PIN ?? "";
  if (!expected || body.pin !== expected) {
    return c.json({ error: "invalid pin" }, 401);
  }
  const expiresAt = Date.now() + SEVEN_DAYS_MS;
  const token = await signSession(c.env, expiresAt);
  setCookie(c, SESSION_COOKIE_NAME, token, {
    httpOnly: true,
    secure: true,
    sameSite: "Strict",
    path: "/",
    maxAge: Math.floor(SEVEN_DAYS_MS / 1000),
  });
  return c.json({ ok: true });
});

auth.post("/logout", (c) => {
  deleteCookie(c, SESSION_COOKIE_NAME, { path: "/" });
  return c.json({ ok: true });
});
