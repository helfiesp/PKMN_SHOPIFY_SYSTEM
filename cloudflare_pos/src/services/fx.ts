/**
 * FX rates (JPY → NOK). Cached in KV for 1 hour, with a fallback constant.
 * Same source as the Python version: frankfurter.dev (free, no auth, ECB-based).
 */
import type { Env } from "../lib/env.js";
import { setSetting } from "../lib/db.js";

const FALLBACK_JPY_NOK = 0.063;
const KV_KEY = "fx:jpy_nok";

export async function getJpyToNokRate(env: Env): Promise<number> {
  const cached = await env.CACHE.get(KV_KEY);
  if (cached) {
    const n = Number(cached);
    if (Number.isFinite(n) && n > 0) return n;
  }

  try {
    const res = await fetch("https://api.frankfurter.dev/v1/latest?base=JPY&symbols=NOK");
    if (!res.ok) throw new Error(`fx http ${res.status}`);
    const data = (await res.json()) as { rates?: { NOK?: number } };
    const rate = data.rates?.NOK;
    if (!rate || !Number.isFinite(rate)) throw new Error("missing NOK rate");
    await env.CACHE.put(KV_KEY, String(rate), { expirationTtl: 3600 });
    await setSetting(env, "snk_last_jpy_nok_rate", String(rate));
    return rate;
  } catch {
    return FALLBACK_JPY_NOK;
  }
}
