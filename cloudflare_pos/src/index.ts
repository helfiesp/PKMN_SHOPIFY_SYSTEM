/**
 * Cloudflare Worker entry — Pokelageret POS.
 *
 *  fetch handler   → Hono app, mounting /api/v1/* routes and serving static
 *                    assets via the [assets] binding for everything else.
 *  scheduled       → cron trigger (every 6h) running the Snkrdunk price update
 *                    + the daily-ish stock-date clear.
 */
import { Hono } from "hono";
import { cors } from "hono/cors";
import { logger } from "hono/logger";

import type { AppContext } from "./lib/env.js";
import { requireAuth } from "./lib/auth.js";

import { auth } from "./routes/auth.js";
import { shopify } from "./routes/shopify.js";
import { snkrdunk } from "./routes/snkrdunk.js";
import { barcodes } from "./routes/barcodes.js";
import { purchaseOrders } from "./routes/purchase-orders.js";
import { receipts } from "./routes/receipts.js";
import { marginVat } from "./routes/margin-vat.js";
import { stockDates } from "./routes/stock-dates.js";
import { settings } from "./routes/settings.js";

import { runSnkrdunkCronCycle } from "./services/snkrdunk.js";
import { clearExpiredStockDates } from "./services/stock-dates.js";

const app = new Hono<AppContext>();

app.use("*", logger());
app.use("/api/*", cors({ origin: "*", credentials: true, maxAge: 86400 }));

app.get("/api/v1/health", (c) =>
  c.json({ ok: true, ts: Date.now(), shop: c.env.SHOPIFY_SHOP }),
);

// Public auth endpoint (login).
app.route("/api/v1/auth", auth);

// Everything else is gated by the POS PIN session cookie.
const api = new Hono<AppContext>();
api.use("*", requireAuth);
api.route("/shopify", shopify);
api.route("/snkrdunk", snkrdunk);
api.route("/barcodes", barcodes);
api.route("/purchase-orders", purchaseOrders);
api.route("/receipts", receipts);
api.route("/margin-vat", marginVat);
api.route("/stock-dates", stockDates);
api.route("/settings", settings);
app.route("/api/v1", api);

// Static assets fall through to the Pages-style ASSETS binding.
app.all("*", async (c) => c.env.ASSETS.fetch(c.req.raw));

export default {
  fetch: app.fetch,

  /**
   * Cron handler. Configured in wrangler.toml as `0 */6 * * *`.
   *
   * Runs the Snkrdunk price update + email digest every 6 hours.
   * Once a day (at 00:xx), also clears expired stock dates.
   */
  async scheduled(event: ScheduledController, env: AppContext["Bindings"], ctx: ExecutionContext) {
    const hour = new Date(event.scheduledTime).getUTCHours();
    ctx.waitUntil(
      (async () => {
        try {
          await runSnkrdunkCronCycle(env, "cron");
        } catch (err) {
          console.error("snkrdunk cron failed:", err);
        }
        if (hour === 0) {
          try {
            await clearExpiredStockDates(env);
          } catch (err) {
            console.error("stock-date clear failed:", err);
          }
        }
      })(),
    );
  },
};
