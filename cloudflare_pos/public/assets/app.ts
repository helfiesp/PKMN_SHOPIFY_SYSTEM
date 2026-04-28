/**
 * Pokelageret POS frontend.
 *
 * Hash routes:
 *   #/login        — PIN entry
 *   #/sale         — barcode scan + cart + checkout (default)
 *   #/snkrdunk     — full Snkrdunk price update workspace
 *   #/po           — purchase orders (list + create)
 *   #/margin-vat   — margin VAT purchases (list + create + proof upload)
 *   #/stock-dates  — pre-orders / stock-date overview
 *   #/receipts     — recent kvitteringer
 *   #/settings     — env config + Snkrdunk run history
 */

type Route =
  | "login"
  | "sale"
  | "snkrdunk"
  | "po"
  | "margin-vat"
  | "stock-dates"
  | "receipts"
  | "settings";

const NAV: Array<[Route, string]> = [
  ["sale", "Kasse"],
  ["snkrdunk", "Snkrdunk"],
  ["po", "Innkjøp"],
  ["margin-vat", "Avansemoms"],
  ["stock-dates", "Stock dates"],
  ["receipts", "Kvitteringer"],
  ["settings", "Innstillinger"],
];

// ============================================================================
// Tiny helpers
// ============================================================================
async function api<T = unknown>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) {
    location.hash = "#/login";
    throw new Error("Not logged in");
  }
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(`${res.status} ${txt}`);
  }
  return (await res.json()) as T;
}

async function upload<T = unknown>(path: string, fd: FormData): Promise<T> {
  const res = await fetch(`/api/v1${path}`, { method: "POST", credentials: "include", body: fd });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

function toast(msg: string, error = false): void {
  const el = document.getElementById("toast")!;
  el.textContent = msg;
  el.className = "show" + (error ? " error" : "");
  setTimeout(() => el.classList.remove("show"), 2400);
}

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | EventListener | boolean | number | null> = {},
  children: Array<Node | string | null | false> = [],
): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === false) continue;
    if (k.startsWith("on") && typeof v === "function") e.addEventListener(k.slice(2), v as EventListener);
    else if (typeof v === "boolean") (e as Record<string, unknown>)[k] = v;
    else e.setAttribute(k, String(v));
  }
  for (const c of children) {
    if (c == null || c === false) continue;
    e.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  }
  return e;
}

function nb(n: number, frac = 2): string {
  return n.toLocaleString("nb-NO", { minimumFractionDigits: frac, maximumFractionDigits: frac });
}

function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ============================================================================
// Snkrdunk pricing math (mirrors src/services/snkrdunk.ts which mirrors Python)
// ============================================================================
const SNK_VAT = 0.25;
const SNK_BOX_THRESHOLD = 25;
const SNK_PACK_THRESHOLD = 10;
const SNK_SPECIAL: Array<[string, number]> = [
  ["terastal festival", 10], ["mega dream", 10], ["vstar universe", 10],
  ["shiny treasure ex", 10], ["shiny treasure", 10],
  ["pokemon 151", 20], ["black bolt", 20], ["white flare", 20],
];

function snkRoundUpNok(amount: number): number {
  let n = Math.trunc(amount);
  if (amount > n) n += 1;
  if (n % 100 === 0) return n - 1;
  let r = n + (9 - (n % 10));
  if (r % 100 === 9 && Math.trunc(r / 10) % 10 === 0) r += 10;
  return r;
}

function snkDetectPacks(title: string): number {
  const t = (title || "").toLowerCase();
  for (const [k, v] of SNK_SPECIAL) if (t.includes(k)) return v;
  return 30;
}

// ============================================================================
// Router
// ============================================================================
function getRoute(): Route {
  const hash = location.hash.replace(/^#\//, "");
  if (NAV.some(([r]) => r === hash)) return hash as Route;
  if (hash === "login") return "login";
  return "sale";
}

function renderNav(active: Route): void {
  const nav = document.getElementById("nav")!;
  nav.replaceChildren(
    ...NAV.map(([route, label]) =>
      el("a", { href: `#/${route}`, class: route === active ? "active" : "" }, [label]),
    ),
  );
  document.getElementById("user-pill")!.textContent = `POS · ${new Date().toLocaleDateString("nb-NO")}`;
}

async function render(): Promise<void> {
  const route = getRoute();
  renderNav(route);
  const main = document.getElementById("app")!;
  main.replaceChildren();
  try {
    switch (route) {
      case "login":       await renderLogin(main); break;
      case "sale":        await renderSale(main); break;
      case "snkrdunk":    await renderSnkrdunk(main); break;
      case "po":          await renderPO(main); break;
      case "margin-vat":  await renderMarginVat(main); break;
      case "stock-dates": await renderStockDates(main); break;
      case "receipts":    await renderReceipts(main); break;
      case "settings":    await renderSettings(main); break;
    }
  } catch (err) {
    main.appendChild(el("div", { class: "panel" }, [`Error: ${(err as Error).message}`]));
  }
}

window.addEventListener("hashchange", () => void render());

// ============================================================================
// Login
// ============================================================================
async function renderLogin(main: HTMLElement): Promise<void> {
  const card = el("div", { class: "panel login-card" });
  card.appendChild(el("h2", {}, ["Logg inn"]));
  const input = el("input", { type: "password", inputmode: "numeric", maxlength: "10", placeholder: "PIN", autofocus: true }) as HTMLInputElement;
  const btn = el("button", {}, ["Logg inn"]);
  card.append(input, btn);
  const submit = async () => {
    try {
      await api("POST", "/auth/login", { pin: input.value });
      location.hash = "#/sale";
    } catch {
      toast("Feil PIN", true);
    }
  };
  btn.addEventListener("click", submit);
  input.addEventListener("keydown", (e) => {
    if ((e as KeyboardEvent).key === "Enter") void submit();
  });
  main.appendChild(card);
}

// ============================================================================
// Sale (POS)
// ============================================================================
interface CartLine {
  variantShopifyId?: string;
  productShopifyId?: string;
  description: string;
  unitPriceNok: number;
  quantity: number;
  isMarginVat: boolean;
  marginVatPurchaseId?: number;
  barcode?: string;
}

let cart: CartLine[] = [];

async function renderSale(main: HTMLElement): Promise<void> {
  const scanInput = el("input", {
    type: "text", placeholder: "Scan or type barcode…", autofocus: true, autocomplete: "off",
  }) as HTMLInputElement;

  const scanBox = el("div", { class: "panel" }, [
    el("div", { class: "scan-zone" }, [
      el("div", { class: "muted", style: "margin-bottom:12px;" }, [
        "Press Enter to look up · USB scanners send Enter automatically",
      ]),
      scanInput,
    ]),
  ]);

  const cartBox = el("div", { class: "panel" }, [el("h2", {}, ["Handlekurv"])]);
  const cartList = el("div", {});
  const totalsRow = el("div", { class: "row", style: "margin-top:12px;justify-content:flex-end;" });
  cartBox.append(cartList, totalsRow);

  const checkoutBox = el("div", { class: "panel" });
  checkoutBox.appendChild(el("h2", {}, ["Betaling"]));

  const drawCart = () => {
    cartList.replaceChildren();
    if (cart.length === 0) {
      cartList.appendChild(el("p", { class: "muted" }, ["Tom"]));
    } else {
      for (let i = 0; i < cart.length; i++) {
        const line = cart[i]!;
        cartList.appendChild(el("div", { class: "cart-line" }, [
          el("div", {}, [
            line.description,
            line.barcode ? el("div", { class: "muted mono", style: "font-size:11px;" }, [line.barcode]) : null,
            line.isMarginVat ? el("span", { class: "tag", style: "margin-top:4px;" }, ["avansemoms"]) : null,
          ]),
          el("input", {
            type: "number", value: String(line.quantity), min: "1",
            onchange: (e) => { line.quantity = Math.max(1, Number((e.target as HTMLInputElement).value) || 1); drawCart(); },
          }),
          el("input", {
            type: "number", value: String(line.unitPriceNok), step: "0.01",
            onchange: (e) => { line.unitPriceNok = Number((e.target as HTMLInputElement).value) || 0; drawCart(); },
          }),
          el("div", { class: "right mono" }, [`${nb(line.unitPriceNok * line.quantity)} kr`]),
          el("button", {
            class: "ghost",
            onclick: () => { cart.splice(i, 1); drawCart(); },
          }, ["✕"]),
        ]));
      }
    }
    const total = cart.reduce((s, l) => s + l.unitPriceNok * l.quantity, 0);
    totalsRow.replaceChildren(el("strong", {}, [`Total: ${nb(total)} kr`]));
  };

  const lookup = async (code: string) => {
    if (!code.trim()) return;
    try {
      const r = await api<{
        found: boolean; productTitle?: string; variantTitle?: string;
        price?: number; variantShopifyId?: string; productShopifyId?: string;
      }>("GET", `/barcodes/lookup/${encodeURIComponent(code.trim())}`);
      if (!r.found) {
        toast("Ukjent strekkode — link først via produktside", true);
        return;
      }
      cart.push({
        variantShopifyId: r.variantShopifyId,
        productShopifyId: r.productShopifyId,
        description: `${r.productTitle ?? ""}${r.variantTitle ? ` · ${r.variantTitle}` : ""}`,
        unitPriceNok: r.price ?? 0,
        quantity: 1,
        isMarginVat: false,
        barcode: code.trim(),
      });
      drawCart();
    } catch (err) {
      toast((err as Error).message, true);
    }
  };

  scanInput.addEventListener("keydown", async (e) => {
    if ((e as KeyboardEvent).key === "Enter") {
      const code = scanInput.value;
      scanInput.value = "";
      await lookup(code);
    }
  });

  const paymentSelect = el("select", {}, [
    el("option", { value: "card" }, ["Kort"]),
    el("option", { value: "cash" }, ["Kontant"]),
    el("option", { value: "vipps" }, ["Vipps"]),
    el("option", { value: "other" }, ["Annet"]),
  ]) as HTMLSelectElement;
  const checkoutBtn = el("button", {}, ["Avslutt salg"]);
  checkoutBox.appendChild(el("div", { class: "row" }, [
    el("label", {}, ["Betaling: "]), paymentSelect, checkoutBtn,
  ]));
  checkoutBtn.addEventListener("click", async () => {
    if (cart.length === 0) return;
    try {
      const r = await api<{ receiptNumber: string; id: number; totalNok: number }>("POST", "/receipts", {
        paymentMethod: paymentSelect.value,
        items: cart.map((l) => ({
          variantShopifyId: l.variantShopifyId, barcode: l.barcode,
          description: l.description, quantity: l.quantity,
          unitPriceNok: l.unitPriceNok, isMarginVat: l.isMarginVat,
          marginVatPurchaseId: l.marginVatPurchaseId,
        })),
      });
      toast(`Kvittering ${r.receiptNumber} · ${nb(r.totalNok)} kr`);
      window.open(`/api/v1/receipts/${r.id}/print`, "_blank", "noopener");
      cart = []; drawCart(); scanInput.focus();
    } catch (err) {
      toast((err as Error).message, true);
    }
  });

  drawCart();
  main.append(scanBox, cartBox, checkoutBox);
}

// ============================================================================
// Snkrdunk — full workspace
// ============================================================================
interface SnkProduct {
  id: number | string;
  name: string;            // Japanese
  nameEn: string;          // extracted/translated
  minPriceJpy: number | null;
  maxPriceJpy: number | null;
  regularPrice: number | null;
  imageUrl: string | null;
  price_change: number;    // delta in JPY vs previous scan
  _manual: boolean;
  _cached_at: string | null;
}

interface SnkMapping {
  id: number;
  snkrdunk_key: string;
  product_shopify_id: string | null;
  variant_shopify_id: string | null;
  packs_per_box: number | null;
  disabled: number;
  product_title?: string | null;
  product_image?: string | null;
}

interface ShopifyVariantRow {
  variant_id: string;
  variant_title: string | null;
  sku: string | null;
  barcode: string | null;
  price: number | null;
  inventory_quantity: number;
  shopify_id: string;
  title: string;
  handle: string;
  image_url: string | null;
  stock_date: string | null;
}

let snkProducts: SnkProduct[] = [];
let snkMappingsByKey: Map<string, SnkMapping> = new Map();
let snkVariantsByProduct: Map<string, ShopifyVariantRow[]> = new Map();
let snkSettings: Record<string, string> = {};
let snkSortKey: string = "name";
let snkSortDir: 1 | -1 = 1;
let snkFilterMismatch = false;
let snkFilterSpike = false;

async function renderSnkrdunk(main: HTMLElement): Promise<void> {
  // Header — settings + actions
  const header = el("div", { class: "panel" });
  header.appendChild(el("h2", {}, ["Snkrdunk price update"]));

  const settingsRow = el("div", { class: "row", style: "gap:14px;flex-wrap:wrap;" });
  const inputs = {
    rate: el("input", { type: "number", step: "0.0001", id: "snk-rate", style: "width:120px;" }) as HTMLInputElement,
    shipping: el("input", { type: "number", id: "snk-shipping", style: "width:90px;" }) as HTMLInputElement,
    margin: el("input", { type: "number", id: "snk-margin", style: "width:80px;" }) as HTMLInputElement,
    pack: el("input", { type: "number", id: "snk-pack-markup", style: "width:80px;" }) as HTMLInputElement,
    autoUpdate: el("input", { type: "checkbox", id: "snk-auto" }) as HTMLInputElement,
    maxPages: el("input", { type: "number", id: "snk-max-pages", style: "width:70px;" }) as HTMLInputElement,
  };

  const fetchRateBtn = el("button", { class: "secondary" }, ["Live FX"]);
  const saveSettingsBtn = el("button", { class: "secondary" }, ["Save"]);

  settingsRow.append(
    el("label", {}, ["FX (JPY→NOK) ", inputs.rate, " ", fetchRateBtn]),
    el("label", {}, ["Shipping JPY ", inputs.shipping]),
    el("label", {}, ["Margin % ", inputs.margin]),
    el("label", {}, ["Pack markup % ", inputs.pack]),
    el("label", {}, ["Max pages ", inputs.maxPages]),
    el("label", {}, [inputs.autoUpdate, " Auto-update"]),
    saveSettingsBtn,
  );
  header.appendChild(settingsRow);

  const actionsRow = el("div", { class: "row", style: "margin-top:12px;gap:10px;flex-wrap:wrap;" });
  const fetchBtn = el("button", {}, ["Fetch SNKRDUNK"]);
  const runBtn = el("button", { class: "secondary" }, ["Auto-update + email"]);
  const testEmailBtn = el("button", { class: "ghost" }, ["Send test email"]);
  const clearCacheBtn = el("button", { class: "ghost" }, ["Clear cache"]);
  const manualUrl = el("input", { type: "text", placeholder: "snkrdunk.com/apparels/<id> or numeric id", style: "width:340px;" }) as HTMLInputElement;
  const manualBtn = el("button", { class: "secondary" }, ["Add manual"]);
  actionsRow.append(fetchBtn, runBtn, testEmailBtn, clearCacheBtn, manualUrl, manualBtn);
  header.appendChild(actionsRow);

  const summary = el("div", { class: "muted", style: "margin-top:12px;font-size:13px;" });
  header.appendChild(summary);
  main.appendChild(header);

  // Filter bar
  const filterBar = el("div", { class: "panel", style: "padding:10px 16px;" });
  const filterMis = el("input", { type: "checkbox" }) as HTMLInputElement;
  const filterSpk = el("input", { type: "checkbox" }) as HTMLInputElement;
  const searchInput = el("input", { type: "search", placeholder: "Search product…", style: "min-width:280px;" }) as HTMLInputElement;
  filterBar.appendChild(el("div", { class: "row", style: "gap:18px;" }, [
    searchInput,
    el("label", {}, [filterMis, " Mismatches only"]),
    el("label", {}, [filterSpk, " Price spikes only (>10%)"]),
  ]));
  main.appendChild(filterBar);

  // Products table panel
  const tableBox = el("div", { class: "panel" });
  const tableHeader = el("div", { class: "row", style: "justify-content:space-between;" }, [
    el("h2", { style: "margin:0;" }, ["Products"]),
  ]);
  tableBox.appendChild(tableHeader);
  const productsTable = el("table");
  tableBox.appendChild(productsTable);
  main.appendChild(tableBox);

  // Scan logs panel
  const logsBox = el("div", { class: "panel" }, [el("h2", {}, ["Recent fetch logs"])]);
  const logsTable = el("table");
  logsBox.appendChild(logsTable);
  main.appendChild(logsBox);

  // ---- Loaders ------------------------------------------------------------
  async function loadSettings() {
    snkSettings = await api<Record<string, string>>("GET", "/snkrdunk/settings");
    inputs.rate.value = snkSettings["snk_last_jpy_nok_rate"] ?? "0.063";
    inputs.shipping.value = snkSettings["snk_shipping_jpy"] ?? "500";
    inputs.margin.value = snkSettings["snk_margin_pct"] ?? "20";
    inputs.pack.value = snkSettings["snk_pack_markup_pct"] ?? "10";
    inputs.maxPages.value = snkSettings["snk_max_pages"] ?? "20";
    inputs.autoUpdate.checked = snkSettings["snk_auto_update"] === "true";
  }

  async function loadProducts() {
    const r = await api<{ total_items: number; items: SnkProduct[] }>("GET", "/snkrdunk/products");
    snkProducts = r.items;
    summary.textContent = `${r.total_items} cached Snkrdunk products · ${snkMappingsByKey.size} mappings`;
  }

  async function loadMappings() {
    const r = await api<{ mappings: SnkMapping[] }>("GET", "/snkrdunk/mappings");
    snkMappingsByKey = new Map(r.mappings.map((m) => [m.snkrdunk_key, m]));
    // Pre-load variants for all mapped products.
    snkVariantsByProduct = new Map();
    for (const m of r.mappings) {
      if (!m.product_shopify_id) continue;
      // Fetch via /shopify/products?q=… is overkill — query DB through /snkrdunk/products's mappings.
      // Instead we'll lazily look up variants from Shopify cache via a single call.
    }
  }

  async function loadVariantsForProducts(productIds: string[]) {
    if (productIds.length === 0) return;
    // Use the local Shopify product cache search.
    // The /shopify/products endpoint returns flat variant rows.
    const r = await api<{ items: ShopifyVariantRow[] }>("GET", "/shopify/products?limit=2000");
    snkVariantsByProduct = new Map();
    for (const v of r.items) {
      const list = snkVariantsByProduct.get(v.shopify_id) ?? [];
      list.push(v);
      snkVariantsByProduct.set(v.shopify_id, list);
    }
  }

  async function loadLogs() {
    const logs = await api<Array<Record<string, unknown>>>("GET", "/snkrdunk/scan-logs?limit=15");
    const tbody = el("tbody");
    for (const s of logs) {
      const fxRate = Number(s["fx_rate_jpy_nok"] ?? 0);
      tbody.appendChild(el("tr", {}, [
        el("td", { class: "mono" }, [String(s["id"])]),
        el("td", {}, [new Date(Number(s["started_at"]) * 1000).toLocaleString("nb-NO")]),
        el("td", {}, [el("span", { class: "tag" }, [String(s["status"])])]),
        el("td", {}, [String(s["trigger"])]),
        el("td", { class: "right" }, [String(s["total_items"] ?? "—")]),
        el("td", { class: "right" }, [String(s["matched_items"] ?? "—")]),
        el("td", { class: "right" }, [String(s["updated_items"] ?? "—")]),
        el("td", { class: "right mono" }, [fxRate ? fxRate.toFixed(5) : "—"]),
        el("td", {}, [Number(s["email_sent"]) === 1 ? "✓" : "—"]),
      ]));
    }
    logsTable.replaceChildren(
      el("thead", {}, [el("tr", {}, [
        el("th", {}, ["#"]), el("th", {}, ["Started"]), el("th", {}, ["Status"]),
        el("th", {}, ["Trigger"]), el("th", { class: "right" }, ["Items"]),
        el("th", { class: "right" }, ["Matched"]), el("th", { class: "right" }, ["Updated"]),
        el("th", { class: "right" }, ["FX"]), el("th", {}, ["Mail"]),
      ])]),
      tbody,
    );
  }

  // ---- Pricing per row ----------------------------------------------------
  interface RowComputed {
    p: SnkProduct;
    mapping: SnkMapping | null;
    productTitle: string;
    productImage: string | null;
    variantBox: ShopifyVariantRow | null;
    variantPack: ShopifyVariantRow | null;
    packs: number;
    boxRec: number | null;
    packRec: number | null;
    boxDiff: number | null;
    packDiff: number | null;
    boxStock: number | null;
    isHidden: boolean;
    spikePct: number | null; // percentage change from previous scan
  }

  function computeRow(p: SnkProduct): RowComputed {
    const mapping = snkMappingsByKey.get(String(p.id)) ?? null;
    const productImage = (mapping?.product_image as string | undefined) ?? p.imageUrl ?? null;
    const productTitle = mapping?.product_title ?? p.nameEn ?? p.name ?? "";

    let variantBox: ShopifyVariantRow | null = null;
    let variantPack: ShopifyVariantRow | null = null;
    if (mapping?.product_shopify_id) {
      const vs = snkVariantsByProduct.get(mapping.product_shopify_id) ?? [];
      for (const v of vs) {
        const opt = (v.variant_title ?? "").toLowerCase();
        if (opt.includes("box")) variantBox = v;
        else if (opt.includes("pack")) variantPack = v;
      }
      if (!variantBox && !variantPack && vs.length === 1) variantBox = vs[0]!;
    }

    const packs = mapping?.packs_per_box ?? snkDetectPacks(productTitle);
    const jpy = p.minPriceJpy ?? 0;
    const rate = Number(inputs.rate.value) || 0;
    const shipping = Number(inputs.shipping.value) || 0;
    const margin = (Number(inputs.margin.value) || 0) / 100;
    const packMarkup = (Number(inputs.pack.value) || 0) / 100;

    let boxRec: number | null = null;
    let packRec: number | null = null;
    if (jpy > 0 && rate > 0 && margin < 1) {
      const nokCost = (jpy + shipping) * rate;
      boxRec = snkRoundUpNok((nokCost / (1 - margin)) * (1 + SNK_VAT));
      const packRaw = (boxRec / packs) * (1 + packMarkup);
      packRec = snkRoundUpNok(packRaw);
    }

    const boxPrice = variantBox?.price ?? null;
    const packPrice = variantPack?.price ?? null;
    const boxDiff = boxPrice !== null && boxRec !== null ? boxPrice - boxRec : null;
    const packDiff = packPrice !== null && packRec !== null ? packPrice - packRec : null;

    const isHidden = mapping?.disabled === 1;

    let spikePct: number | null = null;
    if (p.price_change && p.minPriceJpy && p.minPriceJpy > 0) {
      const prev = p.minPriceJpy - p.price_change;
      if (prev > 0) spikePct = (p.price_change / prev) * 100;
    }

    return {
      p, mapping,
      productTitle, productImage,
      variantBox, variantPack,
      packs,
      boxRec, packRec, boxDiff, packDiff,
      boxStock: variantBox?.inventory_quantity ?? null,
      isHidden,
      spikePct,
    };
  }

  // ---- Table render -------------------------------------------------------
  function drawTable() {
    const rows: RowComputed[] = snkProducts.map(computeRow);

    let filtered = rows;
    const q = searchInput.value.trim().toLowerCase();
    if (q) {
      filtered = filtered.filter((r) =>
        r.productTitle.toLowerCase().includes(q) ||
        r.p.nameEn.toLowerCase().includes(q) ||
        r.p.name.toLowerCase().includes(q),
      );
    }
    if (snkFilterMismatch) {
      filtered = filtered.filter((r) =>
        (r.boxDiff !== null && Math.abs(r.boxDiff) >= SNK_BOX_THRESHOLD) ||
        (r.packDiff !== null && Math.abs(r.packDiff) >= SNK_PACK_THRESHOLD),
      );
    }
    if (snkFilterSpike) {
      filtered = filtered.filter((r) => r.spikePct !== null && Math.abs(r.spikePct) >= 10);
    }

    filtered.sort((a, b) => {
      const dir = snkSortDir;
      switch (snkSortKey) {
        case "name": return a.productTitle.localeCompare(b.productTitle) * dir;
        case "jpy": return ((a.p.minPriceJpy ?? 0) - (b.p.minPriceJpy ?? 0)) * dir;
        case "boxRec": return ((a.boxRec ?? 0) - (b.boxRec ?? 0)) * dir;
        case "boxPrice": return ((a.variantBox?.price ?? 0) - (b.variantBox?.price ?? 0)) * dir;
        case "boxDiff": return ((a.boxDiff ?? 0) - (b.boxDiff ?? 0)) * dir;
        case "boxStock": return ((a.boxStock ?? 0) - (b.boxStock ?? 0)) * dir;
        case "spike": return ((a.spikePct ?? 0) - (b.spikePct ?? 0)) * dir;
        default: return 0;
      }
    });

    const sortHeader = (key: string, label: string, right = false) => {
      const arrow = snkSortKey === key ? (snkSortDir === 1 ? " ▲" : " ▼") : "";
      const th = el("th", {
        class: right ? "right" : "",
        style: "cursor:pointer;user-select:none;",
        onclick: () => { snkSortDir = (snkSortKey === key && snkSortDir === 1) ? -1 : 1; snkSortKey = key; drawTable(); },
      }, [label + arrow]);
      return th;
    };

    const thead = el("thead", {}, [el("tr", {}, [
      sortHeader("name", "Product"),
      sortHeader("jpy", "JPY", true),
      el("th", {}, ["Type"]),
      sortHeader("boxRec", "Box rec", true),
      sortHeader("boxPrice", "Box price", true),
      sortHeader("boxDiff", "Box Δ", true),
      el("th", { class: "right" }, ["Pack rec"]),
      el("th", { class: "right" }, ["Pack price"]),
      el("th", { class: "right" }, ["Pack Δ"]),
      sortHeader("boxStock", "Stock", true),
      sortHeader("spike", "Spike", true),
      el("th", {}, ["Actions"]),
    ])]);
    const tbody = el("tbody");
    for (const row of filtered) tbody.appendChild(renderProductRow(row));

    productsTable.replaceChildren(thead, tbody);
  }

  function renderProductRow(r: RowComputed): HTMLElement {
    const { p, mapping } = r;
    const titleStyle = r.isHidden ? "opacity:.5;text-decoration:line-through;" : "";

    const productCell = el("div", { style: "display:flex;gap:10px;align-items:center;" + titleStyle }, [
      r.productImage
        ? el("img", { src: r.productImage, style: "width:40px;height:40px;border-radius:6px;object-fit:cover;" })
        : null,
      el("div", { style: "flex:1;" }, [
        el("div", {}, [
          el("strong", {}, [r.productTitle]),
          p._manual ? el("span", { class: "tag", style: "margin-left:6px;background:#fef3c7;color:#92400e;" }, ["MANUAL"]) : null,
        ]),
        el("div", { class: "muted", style: "font-size:11px;" }, [
          mapping ? `Linked` : `Not linked`,
          " · ",
          el("a", {
            href: "javascript:void(0)",
            onclick: () => openMappingModal(p),
          } as Record<string, string | EventListener>, [mapping ? "change" : "link product"]) as Node,
          mapping ? el("span", {}, [
            " · packs: ",
            renderPacksDropdown(r),
          ]) as Node : null,
          " · ",
          r.isHidden
            ? el("a", { href: "javascript:void(0)", onclick: async () => {
                await api("POST", `/snkrdunk/unhide/${encodeURIComponent(String(p.id))}`); await reloadAll();
              } } as Record<string, string | EventListener>, ["unhide"]) as Node
            : el("a", { href: "javascript:void(0)", onclick: async () => {
                await api("POST", `/snkrdunk/hide/${encodeURIComponent(String(p.id))}`); await reloadAll();
              } } as Record<string, string | EventListener>, ["hide"]) as Node,
          p._manual ? el("span", {}, [
            " · ",
            el("a", { href: "javascript:void(0)", style: "color:#c62828", onclick: async () => {
              if (!confirm("Remove manual product?")) return;
              await api("DELETE", `/snkrdunk/manual/${encodeURIComponent(String(p.id))}`);
              await reloadAll();
            } } as Record<string, string | EventListener>, ["remove"]) as Node,
          ]) as Node : null,
        ]),
      ]),
    ]);

    // Box action cell
    const boxAction = boxActionButton(r);
    const packAction = packActionButton(r);

    const diffCell = (diff: number | null, threshold: number) => {
      if (diff === null) return el("td", { class: "right muted" }, ["—"]);
      const cls = Math.abs(diff) < threshold ? "muted" : diff > 0 ? "delta-up" : "delta-down";
      const sign = diff > 0 ? "+" : "";
      return el("td", { class: `right mono ${cls}` }, [`${sign}${diff.toFixed(0)}`]);
    };

    let spikeCell: HTMLElement;
    if (r.spikePct === null) spikeCell = el("td", { class: "right muted" }, ["—"]);
    else {
      const arrow = r.spikePct > 0 ? "▲" : "▼";
      const cls = r.spikePct > 0 ? "delta-up" : "delta-down";
      spikeCell = el("td", { class: `right mono ${cls}` }, [`${arrow} ${Math.abs(r.spikePct).toFixed(1)}%`]);
    }

    return el("tr", {}, [
      el("td", { style: titleStyle }, [productCell]),
      el("td", { class: "right mono" + (titleStyle ? ";" + titleStyle : "") }, [p.minPriceJpy ? `${p.minPriceJpy.toLocaleString()} ¥` : "—"]),
      el("td", {}, [
        r.variantBox ? el("span", { class: "tag box" }, ["Box"]) : null,
        r.variantPack ? el("span", { class: "tag pack", style: "margin-left:4px;" }, ["Pack"]) : null,
      ]),
      el("td", { class: "right mono" }, [r.boxRec !== null ? `${r.boxRec}` : "—"]),
      el("td", { class: "right mono" }, [r.variantBox?.price !== undefined && r.variantBox?.price !== null ? `${r.variantBox.price.toFixed(0)}` : "—"]),
      diffCell(r.boxDiff, SNK_BOX_THRESHOLD),
      el("td", { class: "right mono" }, [r.packRec !== null ? `${r.packRec}` : "—"]),
      el("td", { class: "right mono" }, [r.variantPack?.price !== undefined && r.variantPack?.price !== null ? `${r.variantPack.price.toFixed(0)}` : "—"]),
      diffCell(r.packDiff, SNK_PACK_THRESHOLD),
      el("td", { class: "right mono" }, [r.boxStock !== null ? `${r.boxStock}` : "—"]),
      spikeCell,
      el("td", {}, [boxAction, packAction]),
    ]);
  }

  function renderPacksDropdown(r: RowComputed): HTMLElement {
    const sel = el("select", {
      style: "padding:2px 6px;font-size:11px;",
      onchange: async (e) => {
        const v = (e.target as HTMLSelectElement).value;
        const packs = v === "" ? null : Number(v);
        try {
          await api("PUT", `/snkrdunk/mappings/${encodeURIComponent(r.p.id as string | number + "")}/packs`, { packs_per_box: packs });
          if (r.mapping) r.mapping.packs_per_box = packs;
          drawTable();
        } catch (err) {
          toast((err as Error).message, true);
        }
      },
    }) as HTMLSelectElement;
    const options = [
      ["", `auto (${snkDetectPacks(r.productTitle)})`],
      ["10", "10"], ["20", "20"], ["30", "30"], ["36", "36"],
    ];
    for (const [val, label] of options) {
      const o = el("option", { value: val }, [label]) as HTMLOptionElement;
      if ((r.mapping?.packs_per_box ?? null) === (val === "" ? null : Number(val))) o.selected = true;
      sel.appendChild(o);
    }
    return sel;
  }

  function boxActionButton(r: RowComputed): HTMLElement {
    if (!r.mapping?.product_shopify_id || r.boxRec === null) return el("span", {}, []);
    if (!r.variantBox) return el("span", { class: "muted", style: "font-size:11px;" }, ["no box variant"]);
    const old = r.variantBox.price ?? 0;
    if (Math.abs(old - r.boxRec) < SNK_BOX_THRESHOLD) {
      return el("span", { class: "muted", style: "font-size:11px;" }, [`✓ Unchanged (kr ${old.toFixed(0)})`]);
    }
    return el("button", {
      style: "padding:4px 10px;font-size:11px;",
      onclick: async (e) => {
        const btn = e.currentTarget as HTMLButtonElement;
        btn.disabled = true;
        try {
          await api("POST", `/shopify/variant/${encodeURIComponent(r.variantBox!.variant_id)}/price`, {
            price: r.boxRec, productId: r.mapping!.product_shopify_id,
          });
          toast(`Box → kr ${r.boxRec}`);
          await reloadAll();
        } catch (err) { toast((err as Error).message, true); btn.disabled = false; }
      },
    }, [`Update box → kr ${r.boxRec}`]);
  }

  function packActionButton(r: RowComputed): HTMLElement {
    if (!r.mapping?.product_shopify_id || r.packRec === null) return el("span", {}, []);

    if (!r.variantPack) {
      return el("button", {
        class: "secondary",
        style: "padding:4px 10px;font-size:11px;margin-left:6px;",
        onclick: async (e) => {
          if (!confirm(`Create Booster Pack variant at kr ${r.packRec}?`)) return;
          const btn = e.currentTarget as HTMLButtonElement;
          btn.disabled = true;
          try {
            await api("POST", "/snkrdunk/add-pack-variant", {
              product_shopify_id: r.mapping!.product_shopify_id, pack_price: r.packRec,
            });
            toast(`Pack variant created at kr ${r.packRec}`);
            await reloadAll();
          } catch (err) { toast((err as Error).message, true); btn.disabled = false; }
        },
      }, [`+ Add Pack (kr ${r.packRec})`]);
    }

    const old = r.variantPack.price ?? 0;
    if (Math.abs(old - r.packRec) < SNK_PACK_THRESHOLD) {
      return el("span", { class: "muted", style: "font-size:11px;margin-left:6px;" }, [`✓ Unchanged (kr ${old.toFixed(0)})`]);
    }
    return el("button", {
      class: "secondary",
      style: "padding:4px 10px;font-size:11px;margin-left:6px;",
      onclick: async (e) => {
        const btn = e.currentTarget as HTMLButtonElement;
        btn.disabled = true;
        try {
          await api("POST", `/shopify/variant/${encodeURIComponent(r.variantPack!.variant_id)}/price`, {
            price: r.packRec, productId: r.mapping!.product_shopify_id,
          });
          toast(`Pack → kr ${r.packRec}`);
          await reloadAll();
        } catch (err) { toast((err as Error).message, true); btn.disabled = false; }
      },
    }, [`Update pack → kr ${r.packRec}`]);
  }

  // ---- Mapping modal ------------------------------------------------------
  function openMappingModal(p: SnkProduct): void {
    const overlay = el("div", { style: "position:fixed;inset:0;background:rgba(0,0,0,.4);z-index:50;display:flex;align-items:center;justify-content:center;" });
    const modal = el("div", { class: "panel", style: "max-width:700px;width:90%;max-height:80vh;overflow:auto;" });
    modal.appendChild(el("h2", {}, ["Link Snkrdunk → Shopify product"]));
    modal.appendChild(el("p", { class: "muted" }, [`Snkrdunk: ${p.nameEn} (${p.name})`]));

    const search = el("input", { type: "search", placeholder: "Search Shopify products…", autofocus: true, style: "width:100%;margin-bottom:12px;" }) as HTMLInputElement;
    modal.appendChild(search);
    const results = el("div", {});
    modal.appendChild(results);

    const close = () => overlay.remove();
    overlay.appendChild(modal);
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    document.body.appendChild(overlay);

    let timer: ReturnType<typeof setTimeout> | null = null;
    search.addEventListener("input", () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(async () => {
        const q = search.value.trim();
        if (!q) { results.replaceChildren(); return; }
        try {
          const r = await api<{ items: ShopifyVariantRow[] }>("GET", `/shopify/products?q=${encodeURIComponent(q)}&limit=30`);
          // group by product
          const byProduct = new Map<string, ShopifyVariantRow[]>();
          for (const v of r.items) {
            const arr = byProduct.get(v.shopify_id) ?? [];
            arr.push(v);
            byProduct.set(v.shopify_id, arr);
          }
          results.replaceChildren();
          for (const [pid, vs] of byProduct) {
            const v = vs[0]!;
            const item = el("div", {
              style: "padding:10px;border-bottom:1px solid var(--border);cursor:pointer;display:flex;gap:10px;align-items:center;",
              onclick: async () => {
                try {
                  await api("POST", "/snkrdunk/mappings", {
                    snkrdunk_key: String(p.id),
                    product_shopify_id: pid,
                  });
                  toast("Mapping created");
                  close();
                  await reloadAll();
                } catch (err) { toast((err as Error).message, true); }
              },
            }, [
              v.image_url ? el("img", { src: v.image_url, style: "width:40px;height:40px;border-radius:6px;object-fit:cover;" }) : null,
              el("div", {}, [
                el("strong", {}, [v.title]),
                el("div", { class: "muted", style: "font-size:11px;" }, [`${vs.length} variant${vs.length === 1 ? "" : "s"} · ${v.handle}`]),
              ]),
            ]);
            results.appendChild(item);
          }
        } catch (err) { toast((err as Error).message, true); }
      }, 250);
    });
  }

  // ---- Bind handlers ------------------------------------------------------
  async function reloadAll() {
    await loadSettings();
    await loadMappings();
    await loadProducts();
    const productIds = Array.from(snkMappingsByKey.values())
      .map((m) => m.product_shopify_id)
      .filter((x): x is string => !!x);
    await loadVariantsForProducts(productIds);
    drawTable();
    await loadLogs();
  }

  fetchRateBtn.addEventListener("click", async () => {
    fetchRateBtn.setAttribute("disabled", "true");
    try {
      const r = await api<{ rate: number }>("GET", "/snkrdunk/exchange-rate");
      inputs.rate.value = r.rate.toFixed(5);
      toast(`FX rate: ${r.rate.toFixed(5)}`);
      drawTable();
    } catch (err) { toast((err as Error).message, true); }
    fetchRateBtn.removeAttribute("disabled");
  });

  saveSettingsBtn.addEventListener("click", async () => {
    try {
      await api("PUT", "/snkrdunk/settings", {
        snk_shipping_jpy: inputs.shipping.value,
        snk_margin_pct: inputs.margin.value,
        snk_pack_markup_pct: inputs.pack.value,
        snk_max_pages: inputs.maxPages.value,
        snk_auto_update: inputs.autoUpdate.checked ? "true" : "false",
      });
      toast("Settings saved");
      drawTable();
    } catch (err) { toast((err as Error).message, true); }
  });

  fetchBtn.addEventListener("click", async () => {
    fetchBtn.setAttribute("disabled", "true");
    summary.textContent = "Fetching from Snkrdunk…";
    try {
      const r = await api<{ total_items: number; pages_fetched: number; auto_update?: { pushed: number; errors: number } }>(
        "POST", "/snkrdunk/fetch", { pages: [1], force_refresh: true },
      );
      const ext = r.auto_update ? ` · ${r.auto_update.pushed} pushed (${r.auto_update.errors} errors)` : "";
      toast(`Fetched ${r.total_items} items across ${r.pages_fetched} pages${ext}`);
      await reloadAll();
    } catch (err) { toast((err as Error).message, true); }
    fetchBtn.removeAttribute("disabled");
  });

  runBtn.addEventListener("click", async () => {
    if (!confirm("Run full Snkrdunk update + email?")) return;
    runBtn.setAttribute("disabled", "true");
    try {
      const r = await api<{ pushed: number; errors: { length?: number }[]; processed?: number }>("POST", "/snkrdunk/auto-update");
      toast(`Auto-update: ${r.pushed} pushed, ${(r.errors as unknown[]).length} errors`);
      await reloadAll();
    } catch (err) { toast((err as Error).message, true); }
    runBtn.removeAttribute("disabled");
  });

  testEmailBtn.addEventListener("click", async () => {
    try {
      const r = await api<{ success: boolean; message: string }>("POST", "/snkrdunk/test-email");
      toast(r.message, !r.success);
    } catch (err) { toast((err as Error).message, true); }
  });

  clearCacheBtn.addEventListener("click", async () => {
    if (!confirm("Clear all cached Snkrdunk data?")) return;
    try {
      const r = await api<{ removed: number }>("DELETE", "/snkrdunk/cache");
      toast(`${r.removed} cache rows removed`);
      await reloadAll();
    } catch (err) { toast((err as Error).message, true); }
  });

  manualBtn.addEventListener("click", async () => {
    const v = manualUrl.value.trim();
    if (!v) return;
    try {
      const r = await api<{ message: string }>("POST", "/snkrdunk/add-manual", { url: v });
      toast(r.message);
      manualUrl.value = "";
      await reloadAll();
    } catch (err) { toast((err as Error).message, true); }
  });

  filterMis.addEventListener("change", () => { snkFilterMismatch = filterMis.checked; drawTable(); });
  filterSpk.addEventListener("change", () => { snkFilterSpike = filterSpk.checked; drawTable(); });
  searchInput.addEventListener("input", () => drawTable());

  inputs.shipping.addEventListener("input", () => drawTable());
  inputs.margin.addEventListener("input", () => drawTable());
  inputs.pack.addEventListener("input", () => drawTable());
  inputs.rate.addEventListener("input", () => drawTable());

  await reloadAll();
}

// ============================================================================
// Purchase orders — list + create form
// ============================================================================
async function renderPO(main: HTMLElement): Promise<void> {
  const list = await api<{ items: Array<Record<string, unknown>> }>("GET", "/purchase-orders");

  // ---- Create form ----
  const formBox = el("div", { class: "panel" });
  formBox.appendChild(el("h2", {}, ["Ny innkjøpsordre"]));

  const supplier = el("input", { type: "text", placeholder: "Leverandør" }) as HTMLInputElement;
  const orderDate = el("input", { type: "date", value: new Date().toISOString().slice(0, 10) }) as HTMLInputElement;
  const shippingJpy = el("input", { type: "number", value: "0", step: "1", style: "width:120px;" }) as HTMLInputElement;
  const customsNok = el("input", { type: "number", value: "0", step: "0.01", style: "width:120px;" }) as HTMLInputElement;
  const notes = el("input", { type: "text", placeholder: "Notes" }) as HTMLInputElement;

  formBox.appendChild(el("div", { class: "row", style: "gap:12px;flex-wrap:wrap;" }, [
    el("label", {}, ["Leverandør ", supplier]),
    el("label", {}, ["Dato ", orderDate]),
    el("label", {}, ["Frakt JPY ", shippingJpy]),
    el("label", {}, ["Toll NOK ", customsNok]),
    el("label", {}, ["Notes ", notes]),
  ]));

  const itemsBox = el("div", { style: "margin-top:12px;" });
  formBox.appendChild(itemsBox);

  type Line = {
    description: string;
    quantity: number;
    unitPriceJpy: number;
    weightGrams?: number;
    variantSearch: string;
    variantShopifyId?: string;
  };
  const lines: Line[] = [{ description: "", quantity: 1, unitPriceJpy: 0, variantSearch: "" }];

  function drawLines() {
    itemsBox.replaceChildren();
    itemsBox.appendChild(el("div", { class: "row", style: "font-size:12px;color:#666;font-weight:600;padding:0 4px;" }, [
      el("div", { style: "flex:2;" }, ["Beskrivelse"]),
      el("div", { style: "width:80px;" }, ["Antall"]),
      el("div", { style: "width:120px;" }, ["JPY/stk"]),
      el("div", { style: "flex:2;" }, ["Shopify variant (valgfritt)"]),
      el("div", { style: "width:30px;" }, [""]),
    ]));
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i]!;
      const desc = el("input", { type: "text", value: l.description, style: "flex:2;",
        oninput: (e) => { l.description = (e.target as HTMLInputElement).value; },
      }) as HTMLInputElement;
      const qty = el("input", { type: "number", min: "1", value: String(l.quantity), style: "width:80px;",
        oninput: (e) => { l.quantity = Number((e.target as HTMLInputElement).value) || 1; },
      }) as HTMLInputElement;
      const price = el("input", { type: "number", min: "0", step: "1", value: String(l.unitPriceJpy), style: "width:120px;",
        oninput: (e) => { l.unitPriceJpy = Number((e.target as HTMLInputElement).value) || 0; },
      }) as HTMLInputElement;
      const variantBox = el("div", { style: "flex:2;position:relative;" });
      const variantSearch = el("input", {
        type: "search", value: l.variantSearch, placeholder: l.variantShopifyId ? "(linked)" : "Search variant…",
        style: "width:100%;",
      }) as HTMLInputElement;
      variantBox.appendChild(variantSearch);
      const dropdown = el("div", { style: "position:absolute;left:0;right:0;top:100%;background:#fff;border:1px solid #ddd;z-index:5;display:none;max-height:200px;overflow:auto;" });
      variantBox.appendChild(dropdown);
      let timer: ReturnType<typeof setTimeout> | null = null;
      variantSearch.addEventListener("input", () => {
        l.variantSearch = variantSearch.value;
        l.variantShopifyId = undefined;
        if (timer) clearTimeout(timer);
        timer = setTimeout(async () => {
          const q = variantSearch.value.trim();
          if (!q) { dropdown.style.display = "none"; return; }
          const r = await api<{ items: ShopifyVariantRow[] }>("GET", `/shopify/products?q=${encodeURIComponent(q)}&limit=12`);
          dropdown.replaceChildren();
          for (const v of r.items) {
            dropdown.appendChild(el("div", {
              style: "padding:6px 10px;cursor:pointer;border-bottom:1px solid #eee;",
              onclick: () => {
                l.variantShopifyId = v.variant_id;
                l.variantSearch = `${v.title} · ${v.variant_title ?? ""}`;
                if (!l.description) l.description = `${v.title} ${v.variant_title ?? ""}`.trim();
                drawLines();
              },
            }, [
              el("div", {}, [el("strong", {}, [v.title]), ` · ${v.variant_title ?? "—"}`]),
              el("div", { class: "muted", style: "font-size:11px;" }, [`${v.sku ?? ""} · stock ${v.inventory_quantity}`]),
            ]));
          }
          dropdown.style.display = "block";
        }, 250);
      });
      const remove = el("button", { class: "ghost", style: "width:30px;",
        onclick: () => { lines.splice(i, 1); if (lines.length === 0) lines.push({ description: "", quantity: 1, unitPriceJpy: 0, variantSearch: "" }); drawLines(); },
      }, ["✕"]);
      itemsBox.appendChild(el("div", { class: "row", style: "gap:8px;margin-top:6px;" }, [desc, qty, price, variantBox, remove]));
    }
    const addBtn = el("button", { class: "secondary", style: "margin-top:10px;",
      onclick: () => { lines.push({ description: "", quantity: 1, unitPriceJpy: 0, variantSearch: "" }); drawLines(); },
    }, ["+ Add line"]);
    itemsBox.appendChild(addBtn);

    const itemsTotal = lines.reduce((s, l) => s + l.quantity * l.unitPriceJpy, 0);
    const totalJpy = itemsTotal + Number(shippingJpy.value || 0);
    itemsBox.appendChild(el("div", { class: "muted", style: "margin-top:8px;text-align:right;" }, [`Items total: ${itemsTotal.toLocaleString()} JPY · Grand total: ${totalJpy.toLocaleString()} JPY + ${customsNok.value || 0} NOK toll`]));
  }
  drawLines();
  shippingJpy.addEventListener("input", drawLines);
  customsNok.addEventListener("input", drawLines);

  const submitBtn = el("button", { style: "margin-top:14px;" }, ["Opprett innkjøpsordre"]);
  submitBtn.addEventListener("click", async () => {
    if (lines.length === 0 || !lines.some((l) => l.description)) {
      toast("Add at least one line", true); return;
    }
    submitBtn.setAttribute("disabled", "true");
    try {
      const r = await api<{ reference: string; totalNok: number; fxRate: number }>("POST", "/purchase-orders", {
        supplier: supplier.value || undefined,
        orderDate: orderDate.value,
        shippingCostJpy: Number(shippingJpy.value) || 0,
        customsCostNok: Number(customsNok.value) || 0,
        notes: notes.value || undefined,
        items: lines.filter((l) => l.description).map((l) => ({
          description: l.description, quantity: l.quantity, unitPriceJpy: l.unitPriceJpy,
          weightGrams: l.weightGrams, variantShopifyId: l.variantShopifyId,
        })),
      });
      toast(`PO ${r.reference} · ${nb(r.totalNok)} NOK (FX ${r.fxRate.toFixed(5)})`);
      await render();
    } catch (err) { toast((err as Error).message, true); submitBtn.removeAttribute("disabled"); }
  });
  formBox.appendChild(submitBtn);
  main.appendChild(formBox);

  // ---- List ----
  const listBox = el("div", { class: "panel" });
  listBox.appendChild(el("h2", {}, ["Innkjøpsordre"]));
  const tbody = el("tbody");
  for (const po of list.items) {
    const id = Number(po["id"]);
    const status = String(po["status"]);
    tbody.appendChild(el("tr", {}, [
      el("td", { class: "mono" }, [String(po["reference"])]),
      el("td", {}, [String(po["supplier"] ?? "—")]),
      el("td", {}, [String(po["order_date"])]),
      el("td", { class: "right mono" }, [`${Number(po["total_jpy"]).toLocaleString()} ¥`]),
      el("td", { class: "right mono" }, [`${nb(Number(po["total_nok"]))} kr`]),
      el("td", {}, [el("span", { class: "tag" }, [status])]),
      el("td", {}, [
        status !== "received"
          ? el("button", {
              class: "secondary", style: "padding:4px 10px;font-size:11px;",
              onclick: async () => {
                if (!confirm("Mark as received? This pushes inventory adjustments to Shopify.")) return;
                try {
                  const r = await api<{ shopifyAdjustments: number }>("POST", `/purchase-orders/${id}/receive`, {});
                  toast(`Received · ${r.shopifyAdjustments} stock adjustments pushed`);
                  await render();
                } catch (err) { toast((err as Error).message, true); }
              },
            }, ["Receive"])
          : el("span", { class: "muted", style: "font-size:11px;" }, ["received"]),
      ]),
    ]));
  }
  listBox.appendChild(el("table", {}, [
    el("thead", {}, [el("tr", {}, [
      el("th", {}, ["Ref"]), el("th", {}, ["Leverandør"]), el("th", {}, ["Dato"]),
      el("th", { class: "right" }, ["Total JPY"]), el("th", { class: "right" }, ["Total NOK"]),
      el("th", {}, ["Status"]), el("th", {}, [""]),
    ])]),
    tbody,
  ]));
  main.appendChild(listBox);
}

// ============================================================================
// Margin VAT — list + create + proof upload
// ============================================================================
async function renderMarginVat(main: HTMLElement): Promise<void> {
  const list = await api<{ items: Array<Record<string, unknown>> }>("GET", "/margin-vat");

  // ---- Create form ----
  const formBox = el("div", { class: "panel" });
  formBox.appendChild(el("h2", {}, ["Nytt avansemoms-innkjøp"]));
  formBox.appendChild(el("p", { class: "muted" }, ["Norsk brukmomsordning — moms beregnes på margin (salg − innkjøp). VAT = margin × 25/125."]));

  const seller = el("input", { type: "text", placeholder: "Selger (privatperson)" }) as HTMLInputElement;
  const sellerId = el("input", { type: "text", placeholder: "ID (valgfritt)" }) as HTMLInputElement;
  const date = el("input", { type: "date", value: new Date().toISOString().slice(0, 10) }) as HTMLInputElement;
  const mvNotes = el("input", { type: "text", placeholder: "Notes" }) as HTMLInputElement;
  formBox.appendChild(el("div", { class: "row", style: "gap:12px;flex-wrap:wrap;" }, [
    el("label", {}, ["Selger ", seller]),
    el("label", {}, ["ID ", sellerId]),
    el("label", {}, ["Dato ", date]),
    el("label", {}, ["Notes ", mvNotes]),
  ]));

  const itemsBox = el("div", { style: "margin-top:12px;" });
  formBox.appendChild(itemsBox);

  type MVLine = {
    description: string;
    quantity: number;
    unitPurchasePriceNok: number;
    sellingPriceNok?: number;
    variantShopifyId?: string;
    variantSearch: string;
  };
  const lines: MVLine[] = [{ description: "", quantity: 1, unitPurchasePriceNok: 0, variantSearch: "" }];

  function calc(l: MVLine) {
    if (l.sellingPriceNok == null || l.sellingPriceNok <= l.unitPurchasePriceNok) {
      return { margin: 0, vat: 0, eff: 0 };
    }
    const margin = l.sellingPriceNok - l.unitPurchasePriceNok;
    const vat = margin * 25 / 125;
    const eff = (vat / l.sellingPriceNok) * 100;
    return { margin, vat, eff };
  }

  function drawLines() {
    itemsBox.replaceChildren();
    itemsBox.appendChild(el("div", { class: "row", style: "font-size:12px;color:#666;font-weight:600;padding:0 4px;" }, [
      el("div", { style: "flex:2;" }, ["Beskrivelse"]),
      el("div", { style: "width:60px;" }, ["Ant"]),
      el("div", { style: "width:100px;" }, ["Innkjøp NOK"]),
      el("div", { style: "width:100px;" }, ["Salg NOK"]),
      el("div", { style: "width:90px;" }, ["VAT"]),
      el("div", { style: "flex:2;" }, ["Variant"]),
      el("div", { style: "width:30px;" }, [""]),
    ]));
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i]!;
      const desc = el("input", { type: "text", value: l.description, style: "flex:2;",
        oninput: (e) => { l.description = (e.target as HTMLInputElement).value; },
      }) as HTMLInputElement;
      const qty = el("input", { type: "number", min: "1", value: String(l.quantity), style: "width:60px;",
        oninput: (e) => { l.quantity = Number((e.target as HTMLInputElement).value) || 1; drawLines(); },
      }) as HTMLInputElement;
      const purchase = el("input", { type: "number", min: "0", step: "0.01", value: String(l.unitPurchasePriceNok), style: "width:100px;",
        oninput: (e) => { l.unitPurchasePriceNok = Number((e.target as HTMLInputElement).value) || 0; drawLines(); },
      }) as HTMLInputElement;
      const sale = el("input", { type: "number", min: "0", step: "0.01", value: l.sellingPriceNok != null ? String(l.sellingPriceNok) : "", style: "width:100px;", placeholder: "—",
        oninput: (e) => { const v = (e.target as HTMLInputElement).value; l.sellingPriceNok = v === "" ? undefined : Number(v); drawLines(); },
      }) as HTMLInputElement;

      const c = calc(l);
      const vatCell = el("div", { class: "mono", style: "width:90px;font-size:12px;" }, [
        l.sellingPriceNok ? el("div", {}, [`${nb(c.vat)} kr`]) : null,
        l.sellingPriceNok ? el("div", { class: "muted", style: "font-size:10px;" }, [`${c.eff.toFixed(1)}% eff`]) : el("span", { class: "muted" }, ["—"]),
      ]);

      const variantBox = el("div", { style: "flex:2;position:relative;" });
      const variantSearch = el("input", {
        type: "search", value: l.variantSearch, placeholder: l.variantShopifyId ? "(linked)" : "Search variant…",
        style: "width:100%;",
      }) as HTMLInputElement;
      variantBox.appendChild(variantSearch);
      const dropdown = el("div", { style: "position:absolute;left:0;right:0;top:100%;background:#fff;border:1px solid #ddd;z-index:5;display:none;max-height:200px;overflow:auto;" });
      variantBox.appendChild(dropdown);
      let timer: ReturnType<typeof setTimeout> | null = null;
      variantSearch.addEventListener("input", () => {
        l.variantSearch = variantSearch.value;
        l.variantShopifyId = undefined;
        if (timer) clearTimeout(timer);
        timer = setTimeout(async () => {
          const q = variantSearch.value.trim();
          if (!q) { dropdown.style.display = "none"; return; }
          const r = await api<{ items: ShopifyVariantRow[] }>("GET", `/shopify/products?q=${encodeURIComponent(q)}&limit=12`);
          dropdown.replaceChildren();
          for (const v of r.items) {
            dropdown.appendChild(el("div", {
              style: "padding:6px 10px;cursor:pointer;border-bottom:1px solid #eee;",
              onclick: () => {
                l.variantShopifyId = v.variant_id;
                l.variantSearch = `${v.title} · ${v.variant_title ?? ""}`;
                if (!l.description) l.description = `${v.title} ${v.variant_title ?? ""}`.trim();
                if (l.sellingPriceNok == null && v.price) l.sellingPriceNok = v.price;
                drawLines();
              },
            }, [
              el("div", {}, [el("strong", {}, [v.title]), ` · ${v.variant_title ?? "—"}`]),
              el("div", { class: "muted", style: "font-size:11px;" }, [`SKU ${v.sku ?? ""} · stock ${v.inventory_quantity} · pris ${v.price ?? "—"}`]),
            ]));
          }
          dropdown.style.display = "block";
        }, 250);
      });

      const remove = el("button", { class: "ghost", style: "width:30px;",
        onclick: () => { lines.splice(i, 1); if (lines.length === 0) lines.push({ description: "", quantity: 1, unitPurchasePriceNok: 0, variantSearch: "" }); drawLines(); },
      }, ["✕"]);
      itemsBox.appendChild(el("div", { class: "row", style: "gap:8px;margin-top:6px;align-items:flex-start;" }, [
        desc, qty, purchase, sale, vatCell, variantBox, remove,
      ]));
    }
    itemsBox.appendChild(el("button", { class: "secondary", style: "margin-top:10px;",
      onclick: () => { lines.push({ description: "", quantity: 1, unitPurchasePriceNok: 0, variantSearch: "" }); drawLines(); },
    }, ["+ Add line"]));

    const tot = lines.reduce((s, l) => s + l.quantity * l.unitPurchasePriceNok, 0);
    const vatTot = lines.reduce((s, l) => s + calc(l).vat * l.quantity, 0);
    itemsBox.appendChild(el("div", { class: "muted", style: "margin-top:8px;text-align:right;" }, [
      `Innkjøp totalt: ${nb(tot)} kr · Forventet VAT (avansemoms): ${nb(vatTot)} kr`,
    ]));
  }
  drawLines();

  const proofFile = el("input", { type: "file", accept: "image/*,application/pdf", multiple: true }) as HTMLInputElement;
  formBox.appendChild(el("div", { style: "margin-top:12px;" }, [
    el("label", { class: "muted", style: "font-size:13px;" }, [
      "Proof images / kvitteringer: ", proofFile,
    ]),
  ]));

  const submitBtn = el("button", { style: "margin-top:14px;" }, ["Opprett innkjøp"]);
  submitBtn.addEventListener("click", async () => {
    if (!seller.value.trim()) { toast("Selger required", true); return; }
    if (!lines.some((l) => l.description)) { toast("Add at least one line", true); return; }
    submitBtn.setAttribute("disabled", "true");
    try {
      const r = await api<{ id: number; reference: string }>("POST", "/margin-vat", {
        seller: seller.value.trim(),
        sellerId: sellerId.value || undefined,
        purchaseDate: date.value,
        notes: mvNotes.value || undefined,
        items: lines.filter((l) => l.description).map((l) => ({
          description: l.description, quantity: l.quantity,
          unitPurchasePriceNok: l.unitPurchasePriceNok,
          sellingPriceNok: l.sellingPriceNok,
          variantShopifyId: l.variantShopifyId,
        })),
      });
      // Upload proofs.
      const files = proofFile.files;
      if (files && files.length) {
        for (const f of files) {
          const fd = new FormData(); fd.set("file", f);
          await upload(`/margin-vat/${r.id}/proofs`, fd);
        }
      }
      toast(`MV ${r.reference} opprettet`);
      await render();
    } catch (err) { toast((err as Error).message, true); submitBtn.removeAttribute("disabled"); }
  });
  formBox.appendChild(submitBtn);
  main.appendChild(formBox);

  // ---- List ----
  const listBox = el("div", { class: "panel" });
  listBox.appendChild(el("h2", {}, ["Avansemoms-innkjøp"]));
  const tbody = el("tbody");
  for (const mv of list.items) {
    tbody.appendChild(el("tr", {}, [
      el("td", { class: "mono" }, [String(mv["reference"])]),
      el("td", {}, [String(mv["seller"])]),
      el("td", {}, [String(mv["purchase_date"])]),
      el("td", { class: "right mono" }, [`${nb(Number(mv["total_purchase_nok"]))} kr`]),
      el("td", {}, [el("span", { class: "tag" }, [String(mv["status"])])]),
    ]));
  }
  listBox.appendChild(el("table", {}, [
    el("thead", {}, [el("tr", {}, [
      el("th", {}, ["Ref"]), el("th", {}, ["Selger"]), el("th", {}, ["Dato"]),
      el("th", { class: "right" }, ["Innkjøp NOK"]), el("th", {}, ["Status"]),
    ])]),
    tbody,
  ]));
  main.appendChild(listBox);
}

// ============================================================================
// Stock dates
// ============================================================================
async function renderStockDates(main: HTMLElement): Promise<void> {
  const list = await api<{ items: Array<Record<string, unknown>> }>("GET", "/stock-dates");
  const tbody = el("tbody");
  for (const p of list.items) {
    const productId = String(p["shopify_id"]);
    tbody.appendChild(el("tr", {}, [
      el("td", {}, [String(p["title"])]),
      el("td", { class: "mono" }, [String(p["stock_date"])]),
      el("td", {}, [
        el("button", {
          class: "secondary", style: "padding:4px 10px;font-size:11px;",
          onclick: async () => {
            await api("DELETE", `/stock-dates/${encodeURIComponent(productId)}`);
            toast("Stock date fjernet"); await render();
          },
        }, ["Fjern"]),
      ]),
    ]));
  }
  main.appendChild(el("div", { class: "panel" }, [
    el("h2", {}, ["Stock dates"]),
    el("div", { class: "row" }, [
      el("button", {
        onclick: async () => {
          const r = await api<{ cleared: string[] }>("POST", "/stock-dates/clear-expired");
          toast(`${r.cleared.length} utløpte dato(er) fjernet`);
          await render();
        },
      }, ["Clear expired now"]),
    ]),
    el("table", {}, [
      el("thead", {}, [el("tr", {}, [
        el("th", {}, ["Produkt"]), el("th", {}, ["Stock date"]), el("th", {}, [""]),
      ])]),
      tbody,
    ]),
  ]));
}

// ============================================================================
// Receipts
// ============================================================================
async function renderReceipts(main: HTMLElement): Promise<void> {
  const list = await api<{ items: Array<Record<string, unknown>> }>("GET", "/receipts");
  const tbody = el("tbody");
  for (const r of list.items) {
    const id = Number(r["id"]);
    tbody.appendChild(el("tr", {}, [
      el("td", { class: "mono" }, [String(r["receipt_number"])]),
      el("td", {}, [new Date(Number(r["created_at"]) * 1000).toLocaleString("nb-NO")]),
      el("td", {}, [String(r["payment_method"])]),
      el("td", { class: "right mono" }, [`${nb(Number(r["total_nok"]))} kr`]),
      el("td", {}, [el("a", { href: `/api/v1/receipts/${id}/print`, target: "_blank" }, ["Print"])]),
    ]));
  }
  main.appendChild(el("div", { class: "panel" }, [
    el("h2", {}, ["Kvitteringer"]),
    el("table", {}, [
      el("thead", {}, [el("tr", {}, [
        el("th", {}, ["Nr"]), el("th", {}, ["Dato"]), el("th", {}, ["Betaling"]),
        el("th", { class: "right" }, ["Total"]), el("th", {}, [""]),
      ])]),
      tbody,
    ]),
  ]));
}

// ============================================================================
// Settings (general — Snkrdunk has its own panel inline)
// ============================================================================
async function renderSettings(main: HTMLElement): Promise<void> {
  const settings = await api<{ items: Array<{ key: string; value: string; description: string | null }> }>("GET", "/settings");
  const tbody = el("tbody");
  for (const s of settings.items) {
    const input = el("input", {
      type: "text", value: s.value ?? "", style: "width:240px;",
      onchange: async (e) => {
        try {
          await api("PUT", `/settings/${encodeURIComponent(s.key)}`, { value: (e.target as HTMLInputElement).value });
          toast("Saved");
        } catch (err) { toast((err as Error).message, true); }
      },
    });
    tbody.appendChild(el("tr", {}, [
      el("td", { class: "mono" }, [s.key]),
      el("td", {}, [input]),
      el("td", { class: "muted", style: "font-size:11px;" }, [s.description ?? ""]),
    ]));
  }
  main.appendChild(el("div", { class: "panel" }, [
    el("h2", {}, ["Settings"]),
    el("table", {}, [
      el("thead", {}, [el("tr", {}, [el("th", {}, ["Key"]), el("th", {}, ["Value"]), el("th", {}, ["Description"])])]),
      tbody,
    ]),
  ]));
}

// ============================================================================
// Boot
// ============================================================================
void render();
