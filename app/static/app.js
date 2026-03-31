// ─────────────────────────────────────────────────────────────────────────────
// Pokémon Price & Stock Monitor — app.js
// ─────────────────────────────────────────────────────────────────────────────

const API = '/api/v1';

// ── State ─────────────────────────────────────────────────────────────────────
let currentTab = 'dashboard';
let shopifyProducts = [];      // products (each has .variants)
let matchedProducts = [];      // MarketIntel matched-products
let miAlerts = [];             // MarketIntel alerts
let snkrdunkItems = [];        // cached SNKRDUNK products
let snkrdunkPrevItems = [];    // previous scan for spike detection
let competitors = [];          // MarketIntel competitor list

// Products tab state
let productCompLinks    = {};  // shopify_product_id → [link, ...]
let snkrdunkMappings    = [];  // SnkrdunkMapping rows
let productSearchQuery   = '';
let productActiveFilters = new Set();   // active filter-pill keys
let productSort          = 'name';
let productLeaderFilter  = null;        // null | 'self' | '<domain>'
let selectedProductId   = null;
let hiddenProductIds    = new Set(JSON.parse(localStorage.getItem('hiddenProducts') || '[]'));
let competitorMinPrice  = parseInt(localStorage.getItem('competitorMinPrice') || '600', 10);
let _selectedCompLinks  = new Set();

// Link-modal state
let linkModalProductId  = null;
let _linkSearchTimer    = null;
let _linkStaged         = [];  // [{id, domain, title, price, inStock, url}, ...]
let _linkSearchResults  = [];  // cached last search results
let _linkSortPrice      = null; // null = default, 'asc' = low→high, 'desc' = high→low

// Purchase Orders state
let poLineItems = [];
let poSearchTimer = null;
let productCostHistory = {};  // product_shopify_id → {last_unit_nok, avg_unit_nok_30d, last_po_date}

// ── Helpers ───────────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
    const res = await fetch(API + path, opts);
    if (!res.ok) {
        const err = await res.text();
        throw new Error(`${res.status}: ${err}`);
    }
    return res.json();
}

function fmt(n, decimals = 0) {
    if (n == null) return '—';
    return Number(n).toLocaleString('nb-NO', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtNok(n) {
    if (n == null) return '—';
    return `kr\u00a0${fmt(n, 0)}`;
}

function fmtDate(iso) {
    if (!iso) return '—';
    return new Date(iso).toLocaleString('nb-NO', { dateStyle: 'short', timeStyle: 'short' });
}

function deltaBadge(ownPrice, compPrice, sm = false) {
    const cls = sm ? 'badge badge-sm' : 'badge';
    if (!ownPrice || !compPrice) return `<span class="${cls} badge-neutral">—</span>`;
    const pct = ((ownPrice - compPrice) / compPrice) * 100;
    const sign = pct > 0 ? '+' : '';
    if (pct > 10)  return `<span class="${cls} badge-danger">${sign}${pct.toFixed(1)}%</span>`;
    if (pct > 3)   return `<span class="${cls} badge-warning">${sign}${pct.toFixed(1)}%</span>`;
    if (pct < -5)  return `<span class="${cls} badge-info">${sign}${pct.toFixed(1)}%</span>`;
    return `<span class="${cls} badge-success">${sign}${pct.toFixed(1)}%</span>`;
}

function severityBadge(sev) {
    const map = { info: 'badge-info', warning: 'badge-warning', critical: 'badge-danger' };
    return `<span class="badge ${map[sev] || 'badge-neutral'}">${sev}</span>`;
}

function stockClass(qty) {
    if (qty <= 0)  return 'stock-out';
    if (qty <= 5)  return 'stock-critical';
    if (qty <= 15) return 'stock-low';
    return '';
}

function toast(msg, type = 'info') {
    const c = document.getElementById('toast-container');
    if (!c) return;
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = msg;
    c.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

function showTabLoading(id) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="loading-spinner">Loading…</div>';
}

function flatVariants(products) {
    const out = [];
    for (const p of products) {
        for (const v of (p.variants || [])) {
            out.push({ ...v, productTitle: p.title });
        }
    }
    return out;
}

// ── Tab routing ───────────────────────────────────────────────────────────────
function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.nav-item').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === tab);
    });
    document.querySelectorAll('.tab-panel').forEach(p => {
        p.classList.toggle('active', p.id === `tab-${tab}`);
    });
    window.location.hash = tab;
    loadTab(tab);
}

function loadTab(tab) {
    if      (tab === 'dashboard')       loadDashboard();
    else if (tab === 'price-monitor')   loadPriceMonitor();
    else if (tab === 'products')        loadProducts();
    else if (tab === 'snkrdunk')        loadSnkrdunk();
    else if (tab === 'competitor-intel')loadCompetitorIntel();
    else if (tab === 'price-plans')     loadPricePlans();
    else if (tab === 'purchase-orders') loadPurchaseOrders();
    else if (tab === 'stock-dates')     loadStockDates();
    else if (tab === 'receipts')        loadReceiptOrders();
    else if (tab === 'margin-vat')      loadMarginVat();
    else if (tab === 'settings')        loadSettings();
}

// ─────────────────────────────────────────────────────────────────────────────
// DASHBOARD
// ─────────────────────────────────────────────────────────────────────────────
async function loadDashboard() {
    const panels = ['dash-price-actions','dash-restock','dash-comp-activity','dash-margins'];
    panels.forEach(id => showTabLoading(id));

    const [prodRes, alertsRes, snkRes, matchRes, linksRes, costRes] = await Promise.allSettled([
        api('/shopify/products?limit=500'),
        api('/marketintel/alerts?limit=100'),
        api('/snkrdunk/products'),
        api('/marketintel/matched-products?limit=200'),
        api('/competitor-links'),
        api('/purchase-orders/cost-history'),
    ]);

    shopifyProducts = prodRes.status === 'fulfilled'
        ? (prodRes.value.products || prodRes.value || []) : [];
    miAlerts = alertsRes.status === 'fulfilled' ? alertsRes.value : [];
    snkrdunkItems = snkRes.status === 'fulfilled' ? (snkRes.value.items || []) : [];
    matchedProducts = matchRes.status === 'fulfilled' ? matchRes.value : [];
    const compLinks = linksRes.status === 'fulfilled' ? linksRes.value : [];
    const costHistory = costRes.status === 'fulfilled' ? costRes.value : {};

    // ── Build product lookup ──
    const prodById = {};
    for (const p of shopifyProducts) prodById[p.shopify_id] = p;

    // ── Build competitor link map: shopify_product_id → [link, ...] ──
    const linksByProd = {};
    for (const l of compLinks) {
        (linksByProd[l.shopify_product_id] ||= []).push(l);
    }

    const variants = flatVariants(shopifyProducts);
    const outOfStock = variants.filter(v => v.inventory_quantity <= 0);
    const lowStock = variants.filter(v => v.inventory_quantity > 0 && v.inventory_quantity <= 15);

    // ── Find products where a competitor beats us on price ──
    const beatenOnPrice = [];
    for (const [pid, links] of Object.entries(linksByProd)) {
        const prod = prodById[pid];
        if (!prod) continue;
        const ourPrice = prod.variants?.[0]?.price;
        if (!ourPrice) continue;
        for (const l of links) {
            if (l.mi_price && l.mi_in_stock && l.mi_price < ourPrice) {
                const diff = ourPrice - l.mi_price;
                const pct = (diff / ourPrice) * 100;
                beatenOnPrice.push({
                    title: prod.title,
                    ourPrice,
                    compPrice: l.mi_price,
                    domain: l.mi_domain,
                    pct,
                    diff,
                    shopifyId: pid,
                });
            }
        }
    }
    beatenOnPrice.sort((a, b) => b.pct - a.pct);

    // ── Recent competitor alerts (7 days) ──
    const now = Date.now();
    const weekAgo = now - 7 * 86400000;
    const recentAlerts = miAlerts.filter(a => new Date(a.created_at).getTime() > weekAgo);
    const priceChanges = recentAlerts.filter(a => a.type === 'price_change');
    const stockChanges = recentAlerts.filter(a => a.type === 'stock_change');
    const newProducts = recentAlerts.filter(a => a.type === 'new_product');

    // ── Margin analysis from cost history ──
    const marginItems = [];
    for (const [pid, cost] of Object.entries(costHistory)) {
        const prod = prodById[pid];
        if (!prod) continue;
        const ourPrice = prod.variants?.[0]?.price;
        if (!ourPrice || !cost.last_unit_nok) continue;
        const netPrice = ourPrice / 1.25;
        const margin = ((netPrice - cost.last_unit_nok) / netPrice) * 100;
        marginItems.push({
            title: prod.title,
            ourPrice,
            cost: cost.last_unit_nok,
            avgCost: cost.avg_unit_nok_30d,
            margin,
            shopifyId: pid,
        });
    }
    marginItems.sort((a, b) => a.margin - b.margin);

    // ── Total inventory value (rough) ──
    let totalValue = 0;
    for (const v of variants) {
        if (v.inventory_quantity > 0 && v.price) totalValue += v.inventory_quantity * v.price;
    }

    // ── Stat cards ──
    const statGrid = document.getElementById('dash-stat-grid');
    statGrid.innerHTML = `
        <div class="stat-card">
            <div class="stat-value">${shopifyProducts.length}</div>
            <div class="stat-label">Products</div>
        </div>
        <div class="stat-card stat-danger">
            <div class="stat-value">${outOfStock.length}</div>
            <div class="stat-label">Out of Stock</div>
        </div>
        <div class="stat-card stat-warning">
            <div class="stat-value">${lowStock.length}</div>
            <div class="stat-label">Low Stock</div>
        </div>
        <div class="stat-card" style="--stat-accent:var(--danger)">
            <div class="stat-value" style="color:var(--danger)">${beatenOnPrice.length}</div>
            <div class="stat-label">Beaten on Price</div>
        </div>
        <div class="stat-card stat-info">
            <div class="stat-value">${priceChanges.length}</div>
            <div class="stat-label">Price Changes (7d)</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">${fmtNok(totalValue)}</div>
            <div class="stat-label">Inventory Value</div>
        </div>
    `;

    // ── Price Adjustments panel ──
    const priceEl = document.getElementById('dash-price-actions');
    document.getElementById('dash-price-count').textContent = beatenOnPrice.length;
    if (beatenOnPrice.length === 0) {
        priceEl.innerHTML = '<p class="muted" style="padding:.75rem 1rem">You\'re competitive on all linked products.</p>';
    } else {
        priceEl.innerHTML = `<div class="dash-table-wrap"><table class="data-table dash-table">
            <thead><tr>
                <th>Product</th><th>Our Price</th><th>Competitor</th><th>Their Price</th><th>Difference</th>
            </tr></thead>
            <tbody>${beatenOnPrice.slice(0, 15).map(b => `<tr class="dash-row-clickable" onclick="switchTab('products'); setTimeout(()=>selectProduct('${b.shopifyId}'),300)">
                <td><strong>${b.title}</strong></td>
                <td class="mono">${fmtNok(b.ourPrice)}</td>
                <td class="muted">${b.domain}</td>
                <td class="mono">${fmtNok(b.compPrice)}</td>
                <td><span class="badge badge-sm badge-danger">-${b.pct.toFixed(0)}% (${fmtNok(b.diff)})</span></td>
            </tr>`).join('')}</tbody>
        </table></div>`;
    }

    // ── Restock panel ──
    const restockEl = document.getElementById('dash-restock');
    const restockItems = [
        ...outOfStock.map(v => {
            const cost = costHistory[shopifyProducts.find(p => p.variants?.some(vv => vv.shopify_id === v.shopify_id))?.shopify_id];
            return { title: v.productTitle, qty: 0, cost: cost?.last_unit_nok, status: 'out' };
        }),
        ...lowStock.map(v => {
            const cost = costHistory[shopifyProducts.find(p => p.variants?.some(vv => vv.shopify_id === v.shopify_id))?.shopify_id];
            return { title: v.productTitle, qty: v.inventory_quantity, cost: cost?.last_unit_nok, status: 'low' };
        }),
    ];
    // Dedupe by title
    const seen = new Set();
    const uniqueRestock = restockItems.filter(r => { if (seen.has(r.title)) return false; seen.add(r.title); return true; });
    document.getElementById('dash-restock-count').textContent = uniqueRestock.length;
    if (uniqueRestock.length === 0) {
        restockEl.innerHTML = '<p class="muted" style="padding:.75rem 1rem">All products are well-stocked.</p>';
    } else {
        restockEl.innerHTML = `<div class="dash-table-wrap"><table class="data-table dash-table">
            <thead><tr><th>Product</th><th>Stock</th><th>Last Cost</th><th>Status</th></tr></thead>
            <tbody>${uniqueRestock.slice(0, 15).map(r => `<tr>
                <td>${r.title}</td>
                <td class="mono ${stockClass(r.qty)}">${r.qty}</td>
                <td class="mono">${r.cost ? fmtNok(r.cost) : '<span class="muted">—</span>'}</td>
                <td>${r.status === 'out'
                    ? '<span class="badge badge-sm badge-danger">Out of Stock</span>'
                    : '<span class="badge badge-sm badge-warning">Low Stock</span>'}</td>
            </tr>`).join('')}</tbody>
        </table></div>`;
    }

    // ── Competitor Activity panel ──
    const actEl = document.getElementById('dash-comp-activity');
    if (recentAlerts.length === 0) {
        actEl.innerHTML = '<p class="muted" style="padding:.75rem 1rem">No competitor activity in the last 7 days.</p>';
    } else {
        // Group by type
        let html = '';

        if (priceChanges.length > 0) {
            html += '<div class="dash-act-group"><div class="dash-act-label">Price Changes</div>';
            html += priceChanges.slice(0, 8).map(a => {
                const dropped = a.payload?.change_pct < 0;
                return `<div class="dash-act-row">
                    <span class="dash-act-title">${a.payload?.product_title || '—'}</span>
                    <span class="muted">${a.payload?.competitor_domain || ''}</span>
                    <span class="mono">${fmtNok(a.payload?.previous_price)} → ${fmtNok(a.payload?.current_price)}</span>
                    <span class="badge badge-sm ${dropped ? 'badge-danger' : 'badge-success'}">${a.payload?.change_pct?.toFixed(1)}%</span>
                </div>`;
            }).join('');
            html += '</div>';
        }

        if (stockChanges.length > 0) {
            html += '<div class="dash-act-group"><div class="dash-act-label">Stock Changes</div>';
            html += stockChanges.slice(0, 6).map(a => {
                const restocked = (a.payload?.stock_after || 0) > (a.payload?.stock_before || 0);
                return `<div class="dash-act-row">
                    <span class="dash-act-title">${a.payload?.product_title || '—'}</span>
                    <span class="muted">${a.payload?.competitor_domain || ''}</span>
                    <span>${restocked
                        ? '<span class="badge badge-sm badge-info">Restocked</span>'
                        : '<span class="badge badge-sm badge-neutral">Sold out</span>'}</span>
                </div>`;
            }).join('');
            html += '</div>';
        }

        if (newProducts.length > 0) {
            html += '<div class="dash-act-group"><div class="dash-act-label">New Competitor Products</div>';
            html += newProducts.slice(0, 5).map(a => `<div class="dash-act-row">
                <span class="dash-act-title">${a.payload?.product_title || '—'}</span>
                <span class="muted">${a.payload?.competitor_domain || ''}</span>
                <span class="mono">${fmtNok(a.payload?.current_price)}</span>
            </div>`).join('');
            html += '</div>';
        }

        actEl.innerHTML = html || '<p class="muted" style="padding:.75rem 1rem">No activity to show.</p>';
    }

    // ── Margin Watch panel ──
    const marginEl = document.getElementById('dash-margins');
    if (marginItems.length === 0) {
        marginEl.innerHTML = '<p class="muted" style="padding:.75rem 1rem">No cost data yet. Create a Purchase Order to track margins.</p>';
    } else {
        const lowMargin = marginItems.filter(m => m.margin < 25);
        const goodMargin = marginItems.filter(m => m.margin >= 25);
        let html = `<div class="dash-table-wrap"><table class="data-table dash-table">
            <thead><tr><th>Product</th><th>Price</th><th>Cost</th><th>Margin</th></tr></thead>
            <tbody>`;
        // Show low margins first (sorted worst first), then good ones
        const display = [...lowMargin.slice(0, 10), ...goodMargin.slice(0, 5)];
        html += display.map(m => {
            const bc = m.margin < 10 ? 'badge-danger' : m.margin < 20 ? 'badge-warning' : m.margin < 30 ? 'badge-neutral' : 'badge-success';
            return `<tr class="dash-row-clickable" onclick="switchTab('products'); setTimeout(()=>selectProduct('${m.shopifyId}'),300)">
                <td>${m.title}</td>
                <td class="mono">${fmtNok(m.ourPrice)}</td>
                <td class="mono">${fmtNok(m.cost)}</td>
                <td><span class="badge badge-sm ${bc}">${m.margin.toFixed(1)}%</span></td>
            </tr>`;
        }).join('');
        html += '</tbody></table></div>';

        if (lowMargin.length > 0) {
            html += `<p class="muted" style="padding:.5rem 1rem;font-size:.75rem">${lowMargin.length} product${lowMargin.length > 1 ? 's' : ''} below 25% margin</p>`;
        }
        marginEl.innerHTML = html;
    }

    // Last updated
    document.getElementById('dash-last-updated').textContent = `Updated ${new Date().toLocaleTimeString('nb-NO')}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// PRICE MONITOR
// ─────────────────────────────────────────────────────────────────────────────
let pmFilter = 'all';

async function loadPriceMonitor() {
    showTabLoading('pm-table-wrap');
    try {
        matchedProducts = await api('/marketintel/matched-products?limit=200');
        renderPriceMonitor();
    } catch (e) {
        document.getElementById('pm-table-wrap').innerHTML =
            `<p class="error">Failed to load: ${e.message}</p>`;
    }
}

function renderPriceMonitor() {
    const rows = matchedProducts.filter(m => {
        if (pmFilter === 'all') return true;
        const own  = m.own_product?.price;
        const comp = m.competitor_product?.price;
        if (!own || !comp) return false;
        const pct = ((own - comp) / comp) * 100;
        if (pmFilter === 'overpriced')  return pct > 5;
        if (pmFilter === 'underpriced') return pct < -5;
        if (pmFilter === 'ok')          return Math.abs(pct) <= 5;
        return true;
    });

    const wrap = document.getElementById('pm-table-wrap');
    document.getElementById('pm-count').textContent = `${rows.length} products`;

    if (rows.length === 0) {
        wrap.innerHTML = '<p class="muted text-center" style="padding:2rem">No matches for this filter.</p>';
        return;
    }

    wrap.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>Our Product</th>
                <th>Our Price</th>
                <th>Competitor</th>
                <th>Comp Price</th>
                <th>Delta</th>
                <th>Comp Stock</th>
                <th></th>
            </tr></thead>
            <tbody>
                ${rows.map(m => {
                    const own  = m.own_product;
                    const comp = m.competitor_product;
                    const pct  = (own?.price && comp?.price)
                        ? ((own.price - comp.price) / comp.price) * 100 : null;
                    const rc   = pct == null ? '' : pct > 10 ? 'row-danger'
                        : pct > 3 ? 'row-warning' : pct < -5 ? 'row-info' : '';
                    return `<tr class="${rc}">
                        <td>${own?.title || '—'}</td>
                        <td class="mono">${fmtNok(own?.price)}</td>
                        <td class="muted">${comp?.competitor_domain || '—'}</td>
                        <td class="mono">${fmtNok(comp?.price)}</td>
                        <td>${deltaBadge(own?.price, comp?.price)}</td>
                        <td>${comp?.in_stock
                            ? '<span class="badge badge-success">In stock</span>'
                            : '<span class="badge badge-danger">OOS</span>'}</td>
                        <td><a href="${comp?.source_url || '#'}" target="_blank" class="btn btn-xs">View</a></td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>`;
}

function setPmFilter(f) {
    pmFilter = f;
    document.querySelectorAll('.pm-filter-btn').forEach(b =>
        b.classList.toggle('active', b.dataset.filter === f));
    renderPriceMonitor();
}

// ─────────────────────────────────────────────────────────────────────────────
// STOCK MONITOR
// ─────────────────────────────────────────────────────────────────────────────
async function loadStock() {
    showTabLoading('stock-table-wrap');
    try {
        const res = await api('/shopify/products?limit=500');
        shopifyProducts = res.products || res || [];
        renderStock();
    } catch (e) {
        document.getElementById('stock-table-wrap').innerHTML =
            `<p class="error">Failed to load: ${e.message}</p>`;
    }
}

function renderStock() {
    const filter = document.getElementById('stock-filter')?.value || 'all';
    const variants = flatVariants(shopifyProducts)
        .filter(v => {
            if (filter === 'out') return v.inventory_quantity <= 0;
            if (filter === 'low') return v.inventory_quantity > 0 && v.inventory_quantity <= 15;
            return true;
        })
        .sort((a, b) => a.inventory_quantity - b.inventory_quantity);

    const wrap = document.getElementById('stock-table-wrap');
    if (variants.length === 0) {
        wrap.innerHTML = '<p class="muted">No products match this filter.</p>';
        return;
    }
    wrap.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>Product</th><th>Variant</th><th>SKU</th><th>Price</th><th>Stock</th><th>Status</th>
            </tr></thead>
            <tbody>
                ${variants.map(v => `
                    <tr class="${stockClass(v.inventory_quantity)}">
                        <td>${v.productTitle}</td>
                        <td>${v.title || '—'}</td>
                        <td class="mono">${v.sku || '—'}</td>
                        <td class="mono">${fmtNok(v.price)}</td>
                        <td class="text-center mono"><strong>${v.inventory_quantity}</strong></td>
                        <td>${v.inventory_quantity <= 0
                            ? '<span class="badge badge-danger">Out of stock</span>'
                            : v.inventory_quantity <= 5
                                ? '<span class="badge badge-danger">Critical</span>'
                                : v.inventory_quantity <= 15
                                    ? '<span class="badge badge-warning">Low</span>'
                                    : '<span class="badge badge-success">OK</span>'}</td>
                    </tr>
                `).join('')}
            </tbody>
        </table>`;
}

async function generateBoosterInventoryPlan() {
    const btn = document.getElementById('btn-booster-plan');
    if (btn) btn.disabled = true;
    try {
        const plan = await api('/booster-inventory/generate-plan', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
        });
        renderBoosterPlan(plan);
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

function renderBoosterPlan(plan) {
    const el = document.getElementById('booster-plan-result');
    if (!el) return;
    if (!plan?.items?.length) {
        el.innerHTML = '<p class="muted">No booster conversions needed.</p>';
        return;
    }
    el.innerHTML = `
        <div class="card" style="margin-top:1rem">
            <div class="card-header" style="display:flex;justify-content:space-between;align-items:center">
                <h3 style="margin:0">Booster Plan #${plan.id}</h3>
                <button class="btn btn-primary" onclick="applyBoosterPlan(${plan.id})">Apply</button>
            </div>
            <table class="data-table" style="margin-top:.5rem">
                <thead><tr><th>Product</th><th>Action</th><th>Boxes Δ</th><th>Packs Δ</th></tr></thead>
                <tbody>
                    ${plan.items.map(i => `<tr>
                        <td>${i.product_title || '—'}</td>
                        <td>${i.action || '—'}</td>
                        <td class="mono">${i.box_quantity_change ?? '—'}</td>
                        <td class="mono">${i.pack_quantity_change ?? '—'}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
}

async function applyBoosterPlan(planId) {
    try {
        await api(`/booster-inventory/${planId}/apply`, { method: 'POST' });
        toast('Booster inventory plan applied!', 'success');
        document.getElementById('booster-plan-result').innerHTML =
            '<p class="muted">Plan applied successfully.</p>';
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SNKRDUNK
// ─────────────────────────────────────────────────────────────────────────────
async function loadSnkrdunk() {
    showTabLoading('snkrdunk-table-wrap');
    try {
        // First: refresh live prices from Shopify for mapped products
        api('/shopify/refresh-mapped-prices', { method: 'POST' }).catch(() => {});

        const [snkRes, logsRes, prodRes, mapRes] = await Promise.allSettled([
            api('/snkrdunk/products'),
            api('/snkrdunk/scan-logs?limit=10'),
            api('/shopify/products?limit=2000'),
            api('/mappings/snkrdunk?limit=500'),
        ]);
        snkrdunkItems    = snkRes.status  === 'fulfilled' ? (snkRes.value.items || []) : [];
        const logs       = logsRes.status === 'fulfilled' ? logsRes.value : [];
        shopifyProducts  = prodRes.status === 'fulfilled' ? (prodRes.value.products || prodRes.value || shopifyProducts) : shopifyProducts;
        snkrdunkMappings = mapRes.status  === 'fulfilled' ? mapRes.value : snkrdunkMappings;

        // Re-fetch products after price refresh completes (may have updated by now)
        try {
            const freshProds = await api('/shopify/products?limit=2000');
            shopifyProducts = freshProds.products || freshProds || shopifyProducts;
        } catch (_) {}

        renderSnkrdunkTable();
        renderSnkrdunkLogs(logs);
    } catch (e) {
        document.getElementById('snkrdunk-table-wrap').innerHTML =
            `<p class="error">Failed: ${e.message}</p>`;
    }
}

async function fetchSnkrdunk() {
    const btn = document.getElementById('btn-fetch-snkrdunk');
    if (btn) { btn.disabled = true; btn.textContent = 'Fetching…'; }
    snkrdunkPrevItems = [...snkrdunkItems];
    try {
        const res = await api('/snkrdunk/fetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pages: [1, 2, 3], force_refresh: true }),
        });
        toast(`Fetched ${res.total_items || 0} items from SNKRDUNK`, 'success');
        await loadSnkrdunk();
    } catch (e) {
        toast(`Fetch failed: ${e.message}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Refresh Prices'; }
    }
}

function renderSnkrdunkTable() {
    const rate     = parseFloat(document.getElementById('snk-rate')?.value || '0.063');
    const shipping = parseFloat(document.getElementById('snk-shipping')?.value || '500');
    const margin   = parseFloat(document.getElementById('snk-margin')?.value || '20') / 100;
    const VAT      = 0.25;

    const prevMap = {};
    for (const p of snkrdunkPrevItems) prevMap[p.id] = p.minPrice || p.minPriceJpy;

    const snkToShopify = {};
    for (const m of snkrdunkMappings) {
        if (m.disabled) continue;
        const prod = shopifyProducts.find(p => p.shopify_id === m.product_shopify_id);
        if (prod) snkToShopify[String(m.snkrdunk_key)] = prod;
    }

    const SPIKE = 0.10;
    const rows = snkrdunkItems.map(item => {
        const jpy      = item.minPrice || item.minPriceJpy;
        const nokCost  = (jpy + shipping) * rate;
        const nokRec   = Math.ceil((nokCost / (1 - margin)) * (1 + VAT) / 25) * 25;
        const prev     = prevMap[item.id];
        const spike    = prev && Math.abs((jpy - prev) / prev) >= SPIKE;
        const spikePct = prev ? (((jpy - prev) / prev) * 100).toFixed(1) : null;

        const shopProd = snkToShopify[String(item.id)];
        let myPrice = null, variantDbId = null;
        if (shopProd) {
            const variants = shopProd.variants || [];
            const boxV = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
            const v = boxV.length ? boxV[0] : variants[0];
            if (v) {
                myPrice = v.price;
                variantDbId = v.id;
            }
        }
        const diff    = myPrice != null ? myPrice - nokRec : null;
        const diffPct = myPrice != null && nokRec ? ((diff / nokRec) * 100).toFixed(1) : null;

        return { item, jpy, nokRec, spike, spikePct, myPrice, diff, diffPct, shopProd, variantDbId };
    });

    // Filters
    const spikeOnly      = document.getElementById('snk-spikes-only')?.checked;
    const mismatchOnly   = document.getElementById('snk-mismatch-only')?.checked;
    const underpricedOnly = document.getElementById('snk-underpriced-only')?.checked;
    let filtered = rows;
    if (spikeOnly)       filtered = filtered.filter(r => r.spike);
    if (mismatchOnly)    filtered = filtered.filter(r => r.diff != null && Math.abs(r.diff) > 25);
    if (underpricedOnly) filtered = filtered.filter(r => r.diff != null && r.diff < -25);

    // Summary stats
    const mapped = rows.filter(r => r.myPrice != null);
    const underpriced = mapped.filter(r => r.diff < -25);
    const overpriced = mapped.filter(r => r.diff > 25);
    const ok = mapped.filter(r => Math.abs(r.diff || 0) <= 25);
    const summaryEl = document.getElementById('snk-summary');
    if (summaryEl) {
        summaryEl.innerHTML = `
            <div class="snk-stat-card"><div class="snk-stat-num">${rows.length}</div><div class="snk-stat-label">SNKRDUNK Products</div></div>
            <div class="snk-stat-card"><div class="snk-stat-num">${mapped.length}</div><div class="snk-stat-label">Mapped</div></div>
            <div class="snk-stat-card snk-stat-ok"><div class="snk-stat-num">${ok.length}</div><div class="snk-stat-label">Correctly Priced</div></div>
            <div class="snk-stat-card snk-stat-warn"><div class="snk-stat-num">${underpriced.length}</div><div class="snk-stat-label">Underpriced</div></div>
            <div class="snk-stat-card snk-stat-danger"><div class="snk-stat-num">${overpriced.length}</div><div class="snk-stat-label">Overpriced</div></div>
        `;
    }
    document.getElementById('snk-count').textContent = `${filtered.length} shown`;

    document.getElementById('snkrdunk-table-wrap').innerHTML = `
        <table class="data-table compact-table">
            <thead><tr>
                <th></th>
                <th>Product</th>
                <th style="text-align:right">SNKRDUNK</th>
                <th style="text-align:right">Recommended</th>
                <th style="text-align:right">Your Price</th>
                <th style="text-align:right">Difference</th>
                <th style="text-align:center">Status</th>
                <th style="text-align:center;width:140px">Action</th>
            </tr></thead>
            <tbody>
                ${filtered.length === 0
                    ? '<tr><td colspan="8" class="text-center muted" style="padding:2rem">No products match filters.</td></tr>'
                    : filtered.map(r => renderSnkRow(r)).join('')}
            </tbody>
        </table>`;
}

function renderSnkRow({ item, jpy, nokRec, spike, spikePct, myPrice, diff, diffPct, shopProd, variantDbId }) {
    const overpriced  = diff != null && diff > 25;
    const underpriced = diff != null && diff < -25;
    const imgUrl = shopProd?.image_url;
    const img = imgUrl
        ? `<img src="${imgUrl}" style="width:36px;height:36px;object-fit:cover;border-radius:4px">`
        : '<div style="width:36px;height:36px;background:var(--bg-secondary);border-radius:4px;display:flex;align-items:center;justify-content:center;font-size:.6rem;color:var(--text-secondary)">JPY</div>';

    const rowClass = overpriced ? 'snk-row-over' : underpriced ? 'snk-row-under' : '';

    // Status badge
    let statusHtml;
    if (myPrice == null) {
        statusHtml = '<span class="badge badge-neutral badge-sm">Not mapped</span>';
    } else if (overpriced) {
        statusHtml = `<span class="badge badge-danger badge-sm">+${diffPct}%</span>`;
    } else if (underpriced) {
        statusHtml = `<span class="badge badge-warning badge-sm">${diffPct}%</span>`;
    } else {
        statusHtml = '<span class="badge badge-success badge-sm">OK</span>';
    }

    // Spike indicator
    const spikeHtml = spike
        ? `<span class="snk-spike ${Number(spikePct) > 0 ? 'snk-spike-up' : 'snk-spike-down'}">${Number(spikePct) > 0 ? '▲' : '▼'}${Math.abs(spikePct)}%</span>`
        : '';

    // Action button
    let actionHtml = '';
    if (myPrice == null) {
        actionHtml = `<button class="btn btn-xs btn-sm" onclick="event.stopPropagation();snkOpenMapping('${item.id}', '${(item.nameEn || item.name || '').replace(/'/g, "\\'")}')">Map</button>`;
    } else if (Math.abs(diff) > 25 && variantDbId) {
        actionHtml = `<button class="btn btn-sm ${underpriced ? 'btn-primary' : 'btn-warning'}"
            onclick="event.stopPropagation();snkUpdatePrice(${variantDbId}, ${nokRec}, this)"
            style="font-size:.75rem;padding:.25rem .5rem">
            Update to kr ${fmtNum(nokRec)}
        </button>`;
    } else {
        actionHtml = '<span class="muted" style="font-size:.75rem">—</span>';
    }

    return `<tr class="${rowClass}" data-snk-id="${item.id}">
        <td>${img}</td>
        <td>
            <strong style="font-size:.8125rem">${item.nameEn || item.name || item.id}</strong>
            ${spikeHtml}
            ${shopProd ? `<br><span class="muted" style="font-size:.7rem">${shopProd.title}</span>` : ''}
        </td>
        <td class="mono" style="text-align:right">¥${fmt(jpy)}</td>
        <td class="mono" style="text-align:right;font-weight:600">${fmtNok(nokRec)}</td>
        <td class="mono" style="text-align:right">${myPrice != null ? fmtNok(myPrice) : '<span class="muted">—</span>'}</td>
        <td class="mono" style="text-align:right;font-weight:600;${overpriced ? 'color:var(--danger,#ef4444)' : underpriced ? 'color:var(--warning,#f59e0b)' : ''}">${diff != null ? (diff > 0 ? '+' : '') + 'kr ' + fmtNum(diff) : '<span class="muted">—</span>'}</td>
        <td style="text-align:center">${statusHtml}</td>
        <td style="text-align:center">${actionHtml}</td>
    </tr>`;
}

async function snkUpdatePrice(variantDbId, newPrice, btnEl) {
    if (!confirm(`Update price to kr ${fmtNum(newPrice)}?`)) return;
    if (btnEl) { btnEl.disabled = true; btnEl.textContent = 'Updating…'; }
    try {
        await api(`/shopify/variants/${variantDbId}?price=${newPrice}&change_type=snkrdunk_recommendation`, {
            method: 'PUT',
        });
        toast(`Price updated to kr ${fmtNum(newPrice)}`, 'success');
        // Update local state so table re-renders correctly
        for (const p of shopifyProducts) {
            for (const v of (p.variants || [])) {
                if (v.id === variantDbId) { v.price = newPrice; break; }
            }
        }
        renderSnkrdunkTable();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
        if (btnEl) { btnEl.disabled = false; btnEl.textContent = `Update to kr ${fmtNum(newPrice)}`; }
    }
}

// ── SNKRDUNK Mapping ────────────────────────────────────────────────────
let snkMappingTimeout = null;

function snkOpenMapping(snkrdunkKey, snkrdunkName) {
    // Close any existing mapping row
    document.querySelectorAll('.snk-mapping-row').forEach(el => el.remove());

    // Find the row for this item and insert a mapping row after it
    const rows = document.querySelectorAll('#snkrdunk-table-wrap tbody tr');
    let targetRow = null;
    for (const row of rows) {
        if (row.querySelector(`[data-snk-id="${snkrdunkKey}"]`) || row.innerHTML.includes(`snkOpenMapping('${snkrdunkKey}'`)) {
            targetRow = row;
            break;
        }
    }

    const mapRow = document.createElement('tr');
    mapRow.className = 'snk-mapping-row';
    mapRow.innerHTML = `
        <td colspan="8" style="background:var(--bg-secondary);padding:.75rem 1rem">
            <div style="display:flex;gap:.75rem;align-items:center;flex-wrap:wrap">
                <strong style="font-size:.8125rem">Map "${snkrdunkName}" to Shopify product:</strong>
                <div style="position:relative;flex:1;min-width:200px">
                    <input type="text" class="input-sm" id="snk-map-search-${snkrdunkKey}" style="width:100%"
                        placeholder="Search Shopify product..." oninput="snkMapSearch('${snkrdunkKey}', this.value)" autocomplete="off" />
                    <div id="snk-map-results-${snkrdunkKey}" class="mvat-dropdown"></div>
                </div>
                <button class="btn btn-xs" onclick="this.closest('tr').remove()">Cancel</button>
            </div>
        </td>
    `;

    if (targetRow && targetRow.nextSibling) {
        targetRow.parentNode.insertBefore(mapRow, targetRow.nextSibling);
    } else if (targetRow) {
        targetRow.parentNode.appendChild(mapRow);
    }

    document.getElementById(`snk-map-search-${snkrdunkKey}`)?.focus();
}

function snkMapSearch(snkrdunkKey, query) {
    clearTimeout(snkMappingTimeout);
    const el = document.getElementById(`snk-map-results-${snkrdunkKey}`);
    if (!query || query.length < 2) { el.style.display = 'none'; return; }
    snkMappingTimeout = setTimeout(async () => {
        // Search from already-loaded shopifyProducts
        const q = query.toLowerCase();
        const matches = shopifyProducts.filter(p => p.title.toLowerCase().includes(q)).slice(0, 10);
        if (!matches.length) {
            el.innerHTML = '<div class="mvat-search-item muted">No products found</div>';
            el.style.display = 'block';
            return;
        }
        el.innerHTML = matches.map(p => `
            <div class="mvat-search-item" onclick="snkMapProduct('${snkrdunkKey}', '${p.shopify_id}', '${p.title.replace(/'/g, "\\'")}')">
                ${p.image_url ? `<img src="${p.image_url}" style="width:28px;height:28px;object-fit:cover;border-radius:3px">` : ''}
                <div style="flex:1"><strong style="font-size:.8125rem">${p.title}</strong></div>
                <span class="mono" style="font-size:.75rem">kr ${fmtNum(p.variants?.[0]?.price || 0)}</span>
            </div>
        `).join('');
        el.style.display = 'block';
    }, 150);
}

async function snkMapProduct(snkrdunkKey, productShopifyId, productTitle) {
    try {
        await api('/mappings/snkrdunk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                snkrdunk_key: snkrdunkKey,
                product_shopify_id: productShopifyId,
            }),
        });
        toast(`Mapped to "${productTitle}"`, 'success');
        // Remove mapping row and reload
        document.querySelectorAll('.snk-mapping-row').forEach(el => el.remove());
        // Refresh mappings
        try {
            snkrdunkMappings = await api('/mappings/snkrdunk?limit=500');
        } catch (_) {}
        renderSnkrdunkTable();
    } catch (e) {
        toast(`Mapping failed: ${e.message}`, 'error');
    }
}

function renderSnkrdunkLogs(logs) {
    const el = document.getElementById('snkrdunk-logs');
    if (!el) return;
    if (!logs?.length) { el.innerHTML = '<p class="muted" style="padding:.75rem 1.25rem">No scan logs yet.</p>'; return; }
    el.innerHTML = `
        <table class="data-table compact-table">
            <thead><tr><th>Date</th><th>Status</th><th>Products</th><th>Duration</th></tr></thead>
            <tbody>
                ${logs.map(l => `<tr>
                    <td style="font-size:.8125rem">${fmtDate(l.created_at)}</td>
                    <td>${l.status === 'success'
                        ? '<span class="badge badge-success badge-sm">OK</span>'
                        : '<span class="badge badge-danger badge-sm">Failed</span>'}</td>
                    <td>${l.total_items ?? '—'}</td>
                    <td class="mono" style="font-size:.8125rem">${l.duration_seconds ? l.duration_seconds.toFixed(1) + 's' : '—'}</td>
                </tr>`).join('')}
            </tbody>
        </table>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// COMPETITOR INTEL
// ─────────────────────────────────────────────────────────────────────────────
let ciDomain = '';

async function loadCompetitorIntel() {
    showTabLoading('ci-alerts');
    showTabLoading('ci-products-wrap');
    try {
        competitors = await api('/marketintel/competitors');
        renderCompetitorFilter();
        await Promise.all([loadCiAlerts(), loadCiProducts()]);
    } catch (e) {
        document.getElementById('ci-alerts').innerHTML = `<p class="error">Failed: ${e.message}</p>`;
    }
}

function renderCompetitorFilter() {
    const sel = document.getElementById('ci-domain-filter');
    if (!sel) return;
    sel.innerHTML = '<option value="">All competitors</option>' +
        competitors.map(c => `<option value="${c.domain}">${c.domain}</option>`).join('');
}

async function loadCiAlerts() {
    try {
        miAlerts = await api('/marketintel/alerts?limit=50');
        renderCiAlerts();
    } catch (e) {
        document.getElementById('ci-alerts').innerHTML = `<p class="error">${e.message}</p>`;
    }
}

function renderCiAlerts() {
    const typeFilter = document.getElementById('ci-type-filter')?.value || '';
    const rows = typeFilter ? miAlerts.filter(a => a.type === typeFilter) : miAlerts;
    const el   = document.getElementById('ci-alerts');
    if (!el) return;
    if (!rows.length) { el.innerHTML = '<p class="muted">No alerts found.</p>'; return; }
    el.innerHTML = rows.map(a => `
        <div class="alert-row alert-row-${a.severity}">
            <div class="alert-row-meta">
                ${severityBadge(a.severity)}
                <span class="alert-type">${a.type.replace(/_/g, ' ')}</span>
                <span class="muted">${fmtDate(a.created_at)}</span>
                <span class="muted">· ${a.payload?.competitor_domain || ''}</span>
            </div>
            <div class="alert-row-body">
                <strong>${a.payload?.product_title || '—'}</strong>
                ${a.type === 'price_change'
                    ? `<span class="muted"> · ${fmtNok(a.payload?.previous_price)} → ${fmtNok(a.payload?.current_price)}
                       <em>(${a.payload?.change_pct?.toFixed(1)}%)</em></span>`
                    : ''}
                ${a.type === 'new_product'
                    ? `<span class="muted"> · ${fmtNok(a.payload?.current_price)} · ${a.payload?.in_stock ? 'In stock' : 'OOS'}</span>`
                    : ''}
                ${a.type === 'stock_change'
                    ? `<span class="muted"> · ${a.payload?.summary || ''}</span>`
                    : ''}
                ${a.payload?.source_url
                    ? `<a href="${a.payload.source_url}" target="_blank" class="btn btn-xs" style="margin-left:8px">View</a>`
                    : ''}
            </div>
        </div>`).join('');
}

async function loadCiProducts() {
    const wrap = document.getElementById('ci-products-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<div class="loading-spinner">Loading…</div>';
    try {
        const qs   = ciDomain ? `?domain=${encodeURIComponent(ciDomain)}&limit=100` : '?limit=100';
        const data = await api(`/marketintel/competitor-products${qs}`);
        if (!data.length) { wrap.innerHTML = '<p class="muted">No products found.</p>'; return; }
        wrap.innerHTML = `
            <table class="data-table">
                <thead><tr>
                    <th>Title</th><th>Domain</th><th>Price</th>
                    <th>Stock</th><th>Updated</th><th></th>
                </tr></thead>
                <tbody>
                    ${data.map(p => `
                        <tr>
                            <td>${p.title}</td>
                            <td class="muted">${p.competitor_domain}</td>
                            <td class="mono">${fmtNok(p.price)}</td>
                            <td>${p.in_stock
                                ? '<span class="badge badge-success">In stock</span>'
                                : '<span class="badge badge-danger">OOS</span>'}</td>
                            <td class="muted">${fmtDate(p.updated_at)}</td>
                            <td>
                                <a href="${p.source_url}" target="_blank" class="btn btn-xs">View</a>
                                <button class="btn btn-xs" onclick="toggleProductHistory(${p.id})">History</button>
                            </td>
                        </tr>
                        <tr id="hist-row-${p.id}" style="display:none">
                            <td colspan="6">
                                <div id="hist-content-${p.id}" class="history-sparkline">Loading…</div>
                            </td>
                        </tr>`).join('')}
                </tbody>
            </table>`;
    } catch (e) {
        wrap.innerHTML = `<p class="error">${e.message}</p>`;
    }
}

async function toggleProductHistory(productId) {
    const row     = document.getElementById(`hist-row-${productId}`);
    const content = document.getElementById(`hist-content-${productId}`);
    if (!row) return;
    if (row.style.display !== 'none') { row.style.display = 'none'; return; }
    row.style.display = '';
    content.innerHTML = 'Loading…';
    try {
        const hist = await api(`/marketintel/price-history/${productId}?limit=20`);
        if (!hist.length) { content.innerHTML = '<em class="muted">No history yet.</em>'; return; }
        const maxP = Math.max(...hist.map(h => h.price));
        content.innerHTML =
            `<div class="sparkline">` +
            hist.slice().reverse().map(h => {
                const pct = maxP ? Math.round((h.price / maxP) * 60) : 10;
                return `<div class="spark-bar" style="height:${pct}px"
                    title="${fmtNok(h.price)} · ${fmtDate(h.scraped_at)}"></div>`;
            }).join('') +
            `</div>
            <div class="history-chips">
                ${hist.slice(0, 8).map(h =>
                    `<span class="hist-chip">${fmtNok(h.price)} <span class="muted">${fmtDate(h.scraped_at)}</span></span>`
                ).join('')}
            </div>`;
    } catch (e) {
        content.innerHTML = `<em class="error">${e.message}</em>`;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// PRICE PLANS
// ─────────────────────────────────────────────────────────────────────────────
async function loadPricePlans() {
    showTabLoading('pp-plans-list');
    try {
        const plans = await api('/price-plans?limit=30');
        renderPlansList(plans);
    } catch (e) {
        document.getElementById('pp-plans-list').innerHTML = `<p class="error">${e.message}</p>`;
    }
}

function renderPlansList(plans) {
    const el = document.getElementById('pp-plans-list');
    if (!plans?.length) {
        el.innerHTML = '<p class="muted">No price plans yet. Generate one above.</p>';
        return;
    }
    el.innerHTML = plans.map(p => {
        const skipped = p.total_items - p.applied_items - (p.failed_items || 0);
        let summary = `${p.total_items} item${p.total_items !== 1 ? 's' : ''}`;
        if (p.status === 'applied' && p.total_items > 0) {
            summary = `<span style="color:var(--success)">${p.applied_items} applied</span>`;
            if (skipped > 0) summary += ` · <span style="color:var(--danger)">${skipped} skipped</span>`;
        }
        return `
        <div class="plan-card">
            <div class="plan-card-header">
                <span class="plan-id">#${p.id}</span>
                <span class="muted">${p.plan_type || 'standard'}</span>
                <span class="badge ${p.status === 'pending' ? 'badge-warning' : p.status === 'applied' ? 'badge-success' : 'badge-neutral'}">${p.status}</span>
                <span class="muted">${fmtDate(p.created_at)}</span>
                <span class="muted">${summary}</span>
                <div style="margin-left:auto;display:flex;gap:.5rem">
                    ${p.status === 'pending'
                        ? `<button class="btn btn-primary btn-sm" onclick="applyPlan(${p.id})">Apply</button>`
                        : ''}
                    <button class="btn btn-sm" onclick="viewPlan(${p.id})">Details</button>
                </div>
            </div>
        </div>`;
    }).join('');
}

async function generatePlan() {
    const btn = document.getElementById('btn-generate-plan');
    if (btn) btn.disabled = true;
    const variantType = document.getElementById('pp-variant-type')?.value || 'box';
    const minChange   = parseFloat(document.getElementById('pp-min-change')?.value || '5');
    try {
        const plan = await api('/price-plans/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ variant_type: variantType, min_change_threshold: minChange }),
        });
        toast(`Plan #${plan.id} generated — ${plan.items?.length || 0} items`, 'success');
        loadPricePlans();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function applyPlan(planId) {
    if (!confirm(`Apply price plan #${planId}? This will update live Shopify prices.`)) return;
    try {
        const res = await api(`/price-plans/${planId}/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
        });
        toast(`Plan #${planId} applied — ${res.applied_items || 0} prices updated`, 'success');
        loadPricePlans();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    }
}

async function viewPlan(planId) {
    try {
        const plan  = await api(`/price-plans/${planId}`);
        const modal = document.getElementById('plan-modal');
        const body  = document.getElementById('plan-modal-body');
        if (!modal || !body) return;
        const items    = plan.items || [];
        const applied  = items.filter(i => i.applied).length;
        const skipped  = items.filter(i => !i.applied && i.error_message).length;
        const pending  = items.filter(i => !i.applied && !i.error_message).length;

        body.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
                <h3 style="margin:0">Price Plan #${plan.id}
                    <span class="badge ${plan.status === 'pending' ? 'badge-warning' : 'badge-success'}">${plan.status}</span>
                </h3>
                ${plan.status === 'pending'
                    ? `<button class="btn btn-primary" onclick="applyPlan(${plan.id}); closeModal()">Apply Plan</button>`
                    : ''}
            </div>
            <p class="muted" style="margin-bottom:.75rem">${fmtDate(plan.created_at)} · ${plan.plan_type || 'standard'}
                · <span style="color:var(--success)">${applied} applied</span>
                ${skipped  ? `· <span style="color:var(--danger)">${skipped} skipped</span>` : ''}
                ${pending  ? `· <span style="color:var(--text-muted)">${pending} pending</span>` : ''}
            </p>
            <table class="data-table">
                <thead><tr><th>Product</th><th>Current</th><th>New Price</th><th>Change</th><th>Status</th></tr></thead>
                <tbody>
                    ${items.map(i => {
                        const delta = i.new_price - i.current_price;
                        const sign  = delta >= 0 ? '+' : '';
                        let statusHtml;
                        if (i.applied) {
                            statusHtml = '<span style="color:var(--success);font-weight:600">✓ Applied</span>';
                        } else if (i.error_message) {
                            statusHtml = `<span style="color:var(--danger)" title="${i.error_message}">⚠ Skipped</span>`;
                        } else {
                            statusHtml = '<span class="muted">Pending</span>';
                        }
                        return `<tr ${i.error_message ? 'style="opacity:.6"' : ''}>
                            <td>${i.current_title || '—'}</td>
                            <td class="mono">${fmtNok(i.current_price)}</td>
                            <td class="mono"><strong>${fmtNok(i.new_price)}</strong></td>
                            <td class="mono ${delta > 0 ? 'text-danger' : 'text-success'}">${sign}${fmtNok(delta)}</td>
                            <td>${statusHtml}</td>
                        </tr>
                        ${i.error_message && !i.applied ? `<tr style="opacity:.5"><td colspan="5" style="font-size:.72rem;color:var(--danger);padding-top:0">${i.error_message}</td></tr>` : ''}`;
                    }).join('')}
                </tbody>
            </table>`;
        modal.classList.add('open');
    } catch (e) {
        toast(`Failed to load plan: ${e.message}`, 'error');
    }
}

function closeModal() {
    document.getElementById('plan-modal')?.classList.remove('open');
}

// ─────────────────────────────────────────────────────────────────────────────
// STOCK DATES
// ─────────────────────────────────────────────────────────────────────────────
let _sdItems = [];
let _sdEditProductId = null;
let _sdEditMetafieldId = null;

async function loadStockDates() {
    document.getElementById('sd-table-wrap').innerHTML = '<div class="loading-spinner">Loading…</div>';
    try {
        _sdItems = await api('/stock-dates');
        renderStockDates();
    } catch (e) {
        document.getElementById('sd-table-wrap').innerHTML = `<p class="error">Failed to load: ${e.message}</p>`;
    }
}

function renderStockDates() {
    const wrap = document.getElementById('sd-table-wrap');
    const count = document.getElementById('sd-count');
    if (count) count.textContent = `${_sdItems.length} product${_sdItems.length !== 1 ? 's' : ''}`;

    if (_sdItems.length === 0) {
        wrap.innerHTML = '<p class="muted">No products have a stock date set.</p>';
        return;
    }

    const today = new Date(); today.setHours(0, 0, 0, 0);

    wrap.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>Product</th>
                <th>Stock date</th>
                <th>Days until</th>
                <th>Status</th>
                <th></th>
            </tr></thead>
            <tbody>
                ${_sdItems.map(item => {
                    const dt = item.stock_date ? new Date(item.stock_date + 'T00:00:00') : null;
                    const fmtDate = dt ? dt.toLocaleDateString('nb-NO', {day:'2-digit', month:'2-digit', year:'numeric'}) : '—';
                    const days = item.days_until;
                    let badge, rowClass = '';
                    if (item.is_expired || days === 0) {
                        badge = '<span class="badge badge-danger">Due today / expired</span>';
                        rowClass = 'stock-out';
                    } else if (days !== null && days <= 3) {
                        badge = `<span class="badge badge-warning">In ${days} day${days !== 1 ? 's' : ''}</span>`;
                        rowClass = 'stock-low';
                    } else if (days !== null) {
                        badge = `<span class="badge badge-info">${days} days</span>`;
                    } else {
                        badge = '<span class="badge">Unknown</span>';
                    }
                    return `<tr class="${rowClass}">
                        <td>${item.title}</td>
                        <td class="mono">${fmtDate}</td>
                        <td class="text-center">${days !== null ? days : '—'}</td>
                        <td>${badge}</td>
                        <td><button class="btn btn-sm" onclick="openSdModal('${item.product_id}','${item.metafield_id}','${item.title}','${item.stock_date}')">Edit</button></td>
                    </tr>`;
                }).join('')}
            </tbody>
        </table>`;
}

function openSdModal(productId, metafieldId, title, currentDate) {
    _sdEditProductId = productId;
    _sdEditMetafieldId = metafieldId;
    document.getElementById('sd-modal-title').textContent = 'Edit Stock Date';
    document.getElementById('sd-modal-product').textContent = title;
    document.getElementById('sd-modal-date').value = currentDate || '';
    document.getElementById('sd-modal').style.display = 'flex';
}

function closeSdModal() {
    document.getElementById('sd-modal').style.display = 'none';
    _sdEditProductId = null;
    _sdEditMetafieldId = null;
}

function sdAdjustDays(delta) {
    const input = document.getElementById('sd-modal-date');
    const base = input.value ? new Date(input.value + 'T00:00:00') : new Date();
    base.setDate(base.getDate() + delta);
    input.value = base.toISOString().slice(0, 10);
}

async function sdSaveDate() {
    const newDate = document.getElementById('sd-modal-date').value;
    if (!newDate) { showToast('Pick a date first', 'error'); return; }
    if (!_sdEditProductId) return;
    try {
        await api(`/stock-dates/${_sdEditProductId}`, {
            method: 'PATCH',
            body: JSON.stringify({ stock_date: newDate }),
        });
        showToast('Stock date updated', 'success');
        closeSdModal();
        loadStockDates();
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    }
}

async function sdClearDate() {
    if (!_sdEditProductId) return;
    if (!confirm('Clear stock date for this product?')) return;
    try {
        await api(`/stock-dates/${_sdEditProductId}`, { method: 'DELETE' });
        showToast('Stock date cleared', 'success');
        closeSdModal();
        loadStockDates();
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    }
}

async function clearExpiredStockDates() {
    if (!confirm('Clear all expired stock dates now?')) return;
    try {
        const res = await api('/stock-dates/clear-expired', { method: 'POST' });
        const msg = `Cleared ${res.cleared_count} date${res.cleared_count !== 1 ? 's' : ''}` +
            (res.errors.length ? ` (${res.errors.length} error${res.errors.length !== 1 ? 's' : ''})` : '');
        showToast(msg, res.errors.length ? 'warning' : 'success');
        const el = document.getElementById('sd-last-cleared');
        if (el) el.textContent = `Last cleared: ${new Date().toLocaleTimeString('nb-NO')}`;
        loadStockDates();
    } catch (e) {
        showToast(`Failed: ${e.message}`, 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// RECEIPTS
// ─────────────────────────────────────────────────────────────────────────────
let _receiptOrders = [];
let _receiptCursor = null;
let _receiptHasMore = false;

async function loadReceiptOrders() {
    const wrap = document.getElementById('receipt-orders-list');
    wrap.innerHTML = '<div class="loading-spinner">Laster ordrer&hellip;</div>';
    document.getElementById('receipt-search').value = '';
    _receiptCursor = null;
    try {
        const data = await api('/receipts/orders?limit=30');
        _receiptOrders = data.orders || [];
        _receiptCursor = data.end_cursor || null;
        _receiptHasMore = data.has_next_page || false;
        renderReceiptOrders(false);
    } catch (e) {
        wrap.innerHTML = `<p class="muted" style="padding:1rem">Feil ved lasting av ordrer: ${e.message}</p>`;
    }
}

async function searchReceiptOrders() {
    const q = document.getElementById('receipt-search').value.trim();
    if (!q) { loadReceiptOrders(); return; }
    const wrap = document.getElementById('receipt-orders-list');
    wrap.innerHTML = '<div class="loading-spinner">Søker&hellip;</div>';
    _receiptCursor = null;
    try {
        const data = await api(`/receipts/orders?limit=30&search=${encodeURIComponent(q)}`);
        _receiptOrders = data.orders || [];
        _receiptCursor = data.end_cursor || null;
        _receiptHasMore = data.has_next_page || false;
        renderReceiptOrders(false);
    } catch (e) {
        wrap.innerHTML = `<p class="muted" style="padding:1rem">Feil: ${e.message}</p>`;
    }
}

async function loadMoreReceiptOrders() {
    if (!_receiptCursor) return;
    const q = document.getElementById('receipt-search').value.trim();
    let url = `/receipts/orders?limit=30&cursor=${encodeURIComponent(_receiptCursor)}`;
    if (q) url += `&search=${encodeURIComponent(q)}`;
    try {
        const data = await api(url);
        _receiptOrders = _receiptOrders.concat(data.orders || []);
        _receiptCursor = data.end_cursor || null;
        _receiptHasMore = data.has_next_page || false;
        renderReceiptOrders(false);
    } catch (e) {
        showToast('Feil ved lasting av flere ordrer', 'error');
    }
}

function renderReceiptOrders() {
    const wrap = document.getElementById('receipt-orders-list');
    const countEl = document.getElementById('receipts-count');
    const moreBtn = document.getElementById('receipt-load-more');
    countEl.textContent = `${_receiptOrders.length} ordrer`;
    moreBtn.style.display = _receiptHasMore ? '' : 'none';

    if (!_receiptOrders.length) {
        wrap.innerHTML = '<p class="muted" style="padding:1rem;text-align:center">Ingen ordrer funnet.</p>';
        return;
    }

    let html = '<div class="receipt-orders-grid">';
    for (const o of _receiptOrders) {
        const dt = o.created_at ? new Date(o.created_at) : null;
        const dateStr = dt ? dt.toLocaleDateString('nb-NO', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';
        const custName = [o.customer?.first_name, o.customer?.last_name].filter(Boolean).join(' ') || 'Ukjent kunde';
        const total = parseFloat(o.total?.amount || 0);
        const totalStr = total.toLocaleString('nb-NO', { style: 'currency', currency: 'NOK' });
        const statusClass = o.financial_status === 'PAID' ? 'badge-success' : 'badge-warning';
        const statusText = _translateFinStatus(o.financial_status);
        const itemCount = o.line_items ? o.line_items.length : 0;

        html += `
        <div class="receipt-order-card" onclick="openReceipt('${encodeURIComponent(o.id)}')">
            <div class="receipt-order-top">
                <span class="receipt-order-name">${esc(o.name)}</span>
                <span class="badge badge-sm ${statusClass}">${esc(statusText)}</span>
            </div>
            <div class="receipt-order-details">
                <span>${esc(custName)}</span>
                <span class="muted">${dateStr}</span>
            </div>
            <div class="receipt-order-bottom">
                <span class="muted">${itemCount} ${itemCount === 1 ? 'produkt' : 'produkter'}</span>
                <span class="receipt-order-total">${totalStr}</span>
            </div>
            <button class="btn btn-primary btn-sm receipt-gen-btn" onclick="event.stopPropagation();openReceipt('${encodeURIComponent(o.id)}')">
                Generer kvittering
            </button>
        </div>`;
    }
    html += '</div>';
    wrap.innerHTML = html;
}

function openReceipt(encodedGid) {
    const gid = decodeURIComponent(encodedGid);
    // Extract numeric ID from GID for the URL path
    const numericId = gid.replace('gid://shopify/Order/', '');
    const url = `${API}/receipts/generate/gid://shopify/Order/${numericId}`;
    window.open(url, '_blank');
}

function _translateFinStatus(s) {
    const map = {
        'PAID': 'Betalt', 'PENDING': 'Venter', 'AUTHORIZED': 'Autorisert',
        'PARTIALLY_PAID': 'Delvis betalt', 'PARTIALLY_REFUNDED': 'Delvis refundert',
        'REFUNDED': 'Refundert', 'VOIDED': 'Annullert', 'EXPIRED': 'Utløpt',
    };
    return map[(s || '').toUpperCase()] || s || 'Ukjent';
}

// ─────────────────────────────────────────────────────────────────────────────
// SETTINGS
// ─────────────────────────────────────────────────────────────────────────────
async function loadSettings() {
    showTabLoading('settings-list');
    // Populate competitor min price from in-memory state
    const minInput = document.getElementById('comp-min-price-input');
    if (minInput) minInput.value = competitorMinPrice;
    try {
        const s = await api('/settings/?include_sensitive=false');
        renderSettings(s);
    } catch (e) {
        document.getElementById('settings-list').innerHTML = `<p class="error">${e.message}</p>`;
    }
    // Load auto-update toggle state
    try {
        const dict = await api('/settings/dict?mask_sensitive=false');
        const toggle = document.getElementById('toggle-auto-shopify');
        if (toggle) toggle.checked = dict['auto_update_shopify_inventory'] === 'true';
    } catch (_) { /* setting may not exist yet */ }
    // Load MVA collection IDs
    loadMvaCollectionSettings();
}

function saveCompetitorMinPrice() {
    const input = document.getElementById('comp-min-price-input');
    const val = parseInt(input?.value || '0', 10);
    if (isNaN(val) || val < 0) { toast('Enter a valid price', 'error'); return; }
    competitorMinPrice = val;
    localStorage.setItem('competitorMinPrice', String(val));
    toast(`Competitor min price set to kr ${val}`, 'success');
}

function renderSettings(settings) {
    const el = document.getElementById('settings-list');
    if (!settings?.length) {
        el.innerHTML = '<p class="muted">No settings configured.</p>';
        return;
    }
    el.innerHTML = settings.map(s => `
        <div class="setting-row">
            <div class="setting-info">
                <strong>${s.key}</strong>
                ${s.description ? `<span class="muted"> — ${s.description}</span>` : ''}
            </div>
            <div class="setting-controls">
                <input type="${s.is_sensitive ? 'password' : 'text'}"
                    class="input-sm"
                    id="setting-${s.key}"
                    value="${s.value || ''}"
                    placeholder="${s.is_sensitive ? '(hidden)' : '—'}" />
                <button class="btn btn-sm" onclick="saveSetting('${s.key}')">Save</button>
            </div>
        </div>`).join('');
}

async function saveSetting(key) {
    const input = document.getElementById(`setting-${key}`);
    if (!input) return;
    try {
        await api(`/settings/${key}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ value: input.value.trim() }),
        });
        toast(`Saved: ${key}`, 'success');
    } catch (e) {
        toast(`Failed to save ${key}: ${e.message}`, 'error');
    }
}

async function toggleAutoShopifyUpdate(enabled) {
    try {
        await api('/settings/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                key: 'auto_update_shopify_inventory',
                value: enabled ? 'true' : 'false',
                description: 'Automatically update Shopify inventory when creating purchase orders',
                is_sensitive: false,
            }),
        });
        toast(enabled ? 'Auto Shopify update enabled' : 'Auto Shopify update disabled', 'success');
    } catch (e) {
        toast(`Failed to save setting: ${e.message}`, 'error');
        // Revert toggle
        const toggle = document.getElementById('toggle-auto-shopify');
        if (toggle) toggle.checked = !enabled;
    }
}

async function clearCompareAtPrices() {
    if (!confirm('Clear all compare-at prices for Booster Box variants on Shopify?')) return;
    const btn = document.getElementById('btn-clear-compare-at');
    const status = document.getElementById('clear-compare-at-status');
    if (btn) btn.disabled = true;
    if (status) status.textContent = 'Working…';
    try {
        const res = await api('/shopify/clear-compare-at-prices', { method: 'POST' });
        const msg = `Cleared ${res.cleared} variant(s)`;
        if (status) status.textContent = msg;
        toast(msg + (res.errors?.length ? ` (${res.errors.length} error(s))` : ''), res.errors?.length ? 'warning' : 'success');
        if (res.errors?.length) console.warn('Compare-at clear errors:', res.errors);
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
        if (status) status.textContent = 'Failed';
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function syncShopify() {
    const btn = document.getElementById('btn-sync-shopify');
    if (btn) btn.disabled = true;
    try {
        const collectionId = document.getElementById('sync-collection-id')?.value.trim() || '444175384827';
        await api('/shopify/fetch-collection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_id: collectionId }),
        });
        toast('Shopify sync complete', 'success');
    } catch (e) {
        toast(`Sync failed: ${e.message}`, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function syncAllProducts() {
    if (!confirm('Sync your entire Shopify catalogue? This may take a moment.')) return;
    const btn = document.getElementById('btn-sync-all');
    if (btn) { btn.disabled = true; btn.textContent = 'Syncing...'; }
    try {
        const res = await api('/shopify/fetch-all-products', { method: 'POST' });
        toast(`Synced ${res.total_products} products, ${res.total_variants} variants`, 'success');
    } catch (e) {
        toast(`Sync failed: ${e.message}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Sync Entire Catalogue'; }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// PRODUCTS (stock + competitor links + SNKRDUNK per product)
// ─────────────────────────────────────────────────────────────────────────────

// Default pricing params (mirrors SNKRDUNK tab inputs when they exist)
function snkParams() {
    return {
        rate:     parseFloat(document.getElementById('snk-rate')?.value     || '0.063'),
        shipping: parseFloat(document.getElementById('snk-shipping')?.value  || '500'),
        margin:   parseFloat(document.getElementById('snk-margin')?.value    || '20') / 100,
    };
}

function calcSnkrdunkRec(jpy) {
    const { rate, shipping, margin } = snkParams();
    const cost = (jpy + shipping) * rate;
    return Math.ceil((cost / (1 - margin)) * 1.25 / 25) * 25;
}

// ── Auto-match helpers ────────────────────────────────────────────────────────

function titleScore(ourTitle, compTitle) {
    const stop = new Set([
        'pokemon', 'pokémon', 'japansk', 'japanese', 'display', 'booster', 'box',
        'pack', 'tcg', 'kort', 'card', 'cards', 'high', 'class', 'collection',
        'med', 'shrink', 'the', 'of', 'and', 'jp', 'jpn', 'en', 'og', 'ex',
    ]);
    const tokenize = s => s.toLowerCase()
        .replace(/[^a-zæøå0-9\s]/g, ' ')
        .split(/\s+/)
        .filter(w => w.length >= 2 && !stop.has(w));

    const ours   = new Set(tokenize(ourTitle));
    const theirs = new Set(tokenize(compTitle));
    if (!ours.size) return 0;
    let hits = 0;
    for (const w of ours) if (theirs.has(w)) hits++;
    return hits / ours.size;
}

async function autoMatchProduct(shopifyId) {
    const p = shopifyProducts.find(x => x.shopify_id === shopifyId);
    if (!p) return;

    const variants = p.variants || [];
    const boxV  = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const dispV = boxV.length ? boxV : variants;
    const ourPrice = dispV[0]?.price;
    if (!ourPrice) { toast('No price on this product', 'error'); return; }

    const btn = document.querySelector(`.btn-auto-match-single[data-id="${shopifyId}"]`);
    if (btn) { btn.disabled = true; btn.textContent = 'Matching…'; }

    try {
        const candidates = await api(`/marketintel/competitor-products?search=${encodeURIComponent(p.title)}&limit=200`);
        const good = candidates.filter(c => {
            if (c.price == null || +c.price < competitorMinPrice) return false;
            const tl = (c.title || '').toLowerCase();
            if (tl.includes('koreansk') || tl.includes('korean')) return false;
            const ratio = +c.price / +ourPrice;
            if (ratio < 0.4 || ratio > 2.0) return false;
            return titleScore(p.title, c.title || '') >= 0.5;
        });

        if (!good.length) { toast(`No matches found for "${p.title}"`, 'info'); return; }

        let created = 0;
        for (const m of good) {
            try {
                const link = await api('/competitor-links', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        shopify_product_id: p.shopify_id,
                        mi_product_id:  m.id,
                        mi_domain:      m.competitor_domain,
                        mi_title:       m.title,
                        mi_price:       m.price,
                        mi_in_stock:    m.in_stock,
                        mi_source_url:  m.source_url,
                    }),
                });
                (productCompLinks[p.shopify_id] ||= []).push(link);
                created++;
            } catch (e) {
                if (!e.message.includes('409')) console.warn('Auto-link failed:', e.message);
            }
        }
        toast(`Auto-matched "${p.title}" — ${created} link${created !== 1 ? 's' : ''} created`, created > 0 ? 'success' : 'info');
        _refreshSelectedProduct();
    } catch (e) {
        toast(`Auto-match failed: ${e.message}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'Auto-match'; }
    }
}

async function autoMatchAll() {
    const unmatched = shopifyProducts.filter(p =>
        !hiddenProductIds.has(p.shopify_id) &&
        !(productCompLinks[p.shopify_id]?.length)
    );
    if (!unmatched.length) {
        toast('All visible products already have competitor links', 'info');
        return;
    }

    const btn = document.getElementById('btn-auto-match');
    const origLabel = 'Auto-match';
    if (btn) btn.disabled = true;

    let matched = 0, skipped = 0, linksCreated = 0;

    for (let i = 0; i < unmatched.length; i++) {
        const p = unmatched[i];
        if (btn) btn.textContent = `Matching ${i + 1}/${unmatched.length}…`;

        // Use booster box price as reference
        const variants = p.variants || [];
        const boxV = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
        const dispV = boxV.length ? boxV : variants;
        const ourPrice = dispV[0]?.price;
        if (!ourPrice) { skipped++; continue; }

        try {
            const candidates = await api(`/marketintel/competitor-products?search=${encodeURIComponent(p.title)}&limit=200`);
            const good = candidates.filter(c => {
                if (c.price == null) return false;
                // Minimum price threshold (filters out card singles etc.)
                if (+c.price < competitorMinPrice) return false;
                // Exclude Korean editions
                const tl = (c.title || '').toLowerCase();
                if (tl.includes('koreansk') || tl.includes('korean')) return false;
                // Price: 40%–200% of ours (filters out wildly different items)
                const ratio = +c.price / +ourPrice;
                if (ratio < 0.4 || ratio > 2.0) return false;
                // Title: at least 50% of our keywords must be found in competitor title
                return titleScore(p.title, c.title || '') >= 0.5;
            });

            if (!good.length) { skipped++; continue; }

            for (const m of good) {
                try {
                    const link = await api('/competitor-links', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            shopify_product_id: p.shopify_id,
                            mi_product_id:  m.id,
                            mi_domain:      m.competitor_domain,
                            mi_title:       m.title,
                            mi_price:       m.price,
                            mi_in_stock:    m.in_stock,
                            mi_source_url:  m.source_url,
                        }),
                    });
                    (productCompLinks[p.shopify_id] ||= []).push(link);
                    linksCreated++;
                } catch (e) {
                    if (!e.message.includes('409')) console.warn('Auto-link failed:', e.message);
                }
            }
            matched++;
        } catch (e) {
            skipped++;
        }
    }

    // Reload all links cleanly
    const allLinks = await api('/competitor-links');
    productCompLinks = {};
    for (const lnk of allLinks) (productCompLinks[lnk.shopify_product_id] ||= []).push(lnk);

    if (btn) { btn.disabled = false; btn.textContent = origLabel; }
    renderProducts();
    toast(`Auto-matched ${matched} products · ${linksCreated} links created · ${skipped} skipped`, matched > 0 ? 'success' : 'info');
}

async function syncAndReloadProducts() {
    const btn = document.getElementById('btn-prod-sync');
    if (btn) { btn.disabled = true; btn.textContent = 'Syncing…'; }
    try {
        await api('/shopify/fetch-collection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_id: '444175384827' }),
        });
        showToast('Sync complete', 'success');
        await loadProducts();
    } catch (e) {
        showToast(`Sync failed: ${e.message}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '↻ Sync'; }
    }
}

async function loadProducts() {
    showTabLoading('products-list');
    try {
        const [prodRes, linksRes, mappingsRes, snkRes, costRes] = await Promise.allSettled([
            api('/shopify/products?limit=500'),
            api('/competitor-links'),
            api('/mappings/snkrdunk?limit=500'),
            api('/snkrdunk/products'),
            api('/purchase-orders/cost-history'),
        ]);

        shopifyProducts  = prodRes.status      === 'fulfilled' ? (prodRes.value.products || prodRes.value || []) : [];
        const allLinks   = linksRes.status     === 'fulfilled' ? linksRes.value   : [];
        snkrdunkMappings = mappingsRes.status  === 'fulfilled' ? mappingsRes.value : [];
        snkrdunkItems    = snkRes.status       === 'fulfilled' ? (snkRes.value.items || []) : [];
        productCostHistory = costRes.status    === 'fulfilled' ? costRes.value     : {};

        // Index links by shopify_product_id
        productCompLinks = {};
        for (const lnk of allLinks) {
            (productCompLinks[lnk.shopify_product_id] ||= []).push(lnk);
        }

        renderProducts();
    } catch (e) {
        document.getElementById('products-list').innerHTML = `<p class="error">${e.message}</p>`;
    }
}

function _productCompPos(p) {
    const variants = p.variants || [];
    const boxV     = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const dispV    = boxV.length ? boxV : variants;
    const boxPrice = dispV[0]?.price;
    const links    = productCompLinks[p.shopify_id] || [];
    const inStockPrices = links.filter(l => l.mi_in_stock === true && l.mi_price != null).map(l => +l.mi_price);
    const cheapestComp  = inStockPrices.length ? Math.min(...inStockPrices) : null;
    return { boxPrice, cheapestComp };
}

function _filterProducts() {
    const q       = productSearchQuery.trim().toLowerCase();
    const filters = productActiveFilters;
    let products  = shopifyProducts;

    if (filters.has('hidden')) {
        products = products.filter(p => hiddenProductIds.has(p.shopify_id));
    } else {
        products = products.filter(p => !hiddenProductIds.has(p.shopify_id));

        if (filters.size > 0) {
            products = products.filter(p => {
                const variants = p.variants || [];
                const boxV     = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
                const dispV    = boxV.length ? boxV : variants;
                const minStock = dispV.length ? Math.min(...dispV.map(v => v.inventory_quantity ?? 0)) : 0;
                const { boxPrice, cheapestComp } = _productCompPos(p);

                if (filters.has('out')          && minStock <= 0)                                      return true;
                if (filters.has('low')          && minStock > 0 && minStock <= 10)                     return true;
                if (filters.has('cheapest')     && boxPrice != null && cheapestComp != null && boxPrice <= cheapestComp) return true;
                if (filters.has('not-cheapest') && boxPrice != null && cheapestComp != null && boxPrice >  cheapestComp) return true;
                return false;
            });
        }
    }

    if (q) products = products.filter(p =>
        p.title.toLowerCase().includes(q) ||
        (p.variants || []).some(v => (v.sku || '').toLowerCase().includes(q))
    );

    // Leader filter
    if (productLeaderFilter) {
        products = products.filter(p => _getCheapestSeller(p) === productLeaderFilter);
    }

    // Sort
    products = [...products];
    if (productSort === 'price-asc' || productSort === 'price-desc') {
        const asc = productSort === 'price-asc';
        products.sort((a, b) => {
            const pa = _getBoxPrice(a) ?? (asc ? Infinity : -Infinity);
            const pb = _getBoxPrice(b) ?? (asc ? Infinity : -Infinity);
            return asc ? pa - pb : pb - pa;
        });
    } else if (productSort === 'stock-asc' || productSort === 'stock-desc') {
        const asc = productSort === 'stock-asc';
        products.sort((a, b) => {
            const sa = _getMinStock(a);
            const sb = _getMinStock(b);
            return asc ? sa - sb : sb - sa;
        });
    } else {
        products.sort((a, b) => a.title.localeCompare(b.title, 'nb'));
    }

    return products;
}

function _getBoxPrice(p) {
    const variants = p.variants || [];
    const boxV     = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const dispV    = boxV.length ? boxV : variants;
    return dispV[0]?.price ?? null;
}

function _getMinStock(p) {
    const variants = p.variants || [];
    const boxV     = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const dispV    = boxV.length ? boxV : variants;
    return dispV.length ? Math.min(...dispV.map(v => v.inventory_quantity ?? 0)) : 0;
}

// ── Price leaderboard helpers ─────────────────────────────────────────────────

function _getCheapestSeller(p) {
    const boxPrice = _getBoxPrice(p);
    const links    = productCompLinks[p.shopify_id] || [];
    const inStock  = links.filter(l => l.mi_in_stock === true && l.mi_price != null);
    if (!inStock.length) return boxPrice != null ? 'self' : null;

    let cheapestPrice  = boxPrice ?? Infinity;
    let cheapestSeller = boxPrice != null ? 'self' : null;
    for (const l of inStock) {
        if (+l.mi_price < cheapestPrice - 0.01) {
            cheapestPrice  = +l.mi_price;
            cheapestSeller = l.mi_domain;
        }
    }
    return cheapestSeller;
}

function _buildPriceLeaderboard() {
    const counts = {};
    for (const p of shopifyProducts) {
        if (hiddenProductIds.has(p.shopify_id)) continue;
        const seller = _getCheapestSeller(p);
        if (seller) counts[seller] = (counts[seller] || 0) + 1;
    }
    return counts;
}

function setLeaderFilter(seller) {
    productLeaderFilter = (productLeaderFilter === seller) ? null : seller;
    renderProducts();
}

function renderLeaderboard() {
    const el = document.getElementById('prod-leaderboard');
    if (!el) return;
    const counts = _buildPriceLeaderboard();
    const entries = Object.entries(counts).sort((a, b) => {
        if (a[0] === 'self') return -1;
        if (b[0] === 'self') return 1;
        return b[1] - a[1];
    });
    el.innerHTML = entries.map(([seller, count]) => {
        const isSelf   = seller === 'self';
        const label    = isSelf ? 'pokelageret.no' : seller;
        const isActive = productLeaderFilter === seller;
        return `<button class="leader-chip ${isSelf ? 'leader-chip-self' : 'leader-chip-comp'} ${isActive ? 'leader-chip-active' : ''}"
                    onclick="setLeaderFilter('${seller}')"
                    title="${isActive ? 'Clear filter' : `Show products where ${label} is cheapest`}">
                    ${label} <strong>${count}</strong>
                </button>`;
    }).join('');
}

function hideProduct(shopifyId, title) {
    if (!confirm(`Hide "${title || shopifyId}" from the products list?\n\nYou can show it again with the Hidden filter.`)) return;
    hiddenProductIds.add(shopifyId);
    localStorage.setItem('hiddenProducts', JSON.stringify([...hiddenProductIds]));
    if (selectedProductId === shopifyId) {
        selectedProductId = null;
        const panel = document.getElementById('prod-detail-panel');
        if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }
    }
    renderProducts();
}

function unhideProduct(shopifyId) {
    hiddenProductIds.delete(shopifyId);
    localStorage.setItem('hiddenProducts', JSON.stringify([...hiddenProductIds]));
    selectedProductId = null;
    const panel = document.getElementById('prod-detail-panel');
    if (panel) { panel.style.display = 'none'; panel.innerHTML = ''; }
    renderProducts();
}

function renderProducts() {
    const products = _filterProducts();
    const el = document.getElementById('products-list');
    document.getElementById('products-count').textContent = `${products.length} products`;

    // Build scaffold on first render (leaderboard + grid + detail)
    if (!document.getElementById('prod-card-grid')) {
        el.innerHTML = `
        <div id="prod-leaderboard" class="prod-leaderboard"></div>
        <div class="prod-grid-layout">
            <div class="prod-card-grid" id="prod-card-grid"></div>
            <div class="prod-detail-panel prod-detail-panel--side" id="prod-detail-panel" style="display:none"></div>
        </div>`;
    }

    renderLeaderboard();

    if (!products.length) {
        document.getElementById('prod-card-grid').innerHTML =
            '<p class="muted" style="padding:2rem">No products match the filter.</p>';
        return;
    }

    const grid = document.getElementById('prod-card-grid');
    grid.innerHTML = products.map(p => renderProductCard(p)).join('');

    // Restore selection
    if (selectedProductId && shopifyProducts.find(p => p.shopify_id === selectedProductId)) {
        selectProduct(selectedProductId);
    }
}

// ── Product card (grid) ───────────────────────────────────────────────────────

function renderProductCard(p) {
    const variants = p.variants || [];
    const links    = productCompLinks[p.shopify_id] || [];

    const boxV  = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const dispV = boxV.length ? boxV : variants;

    const totalStock = dispV.reduce((s, v) => s + (v.inventory_quantity ?? 0), 0);
    const minStock   = dispV.length ? Math.min(...dispV.map(v => v.inventory_quantity ?? 0)) : 0;
    const boxPrice   = dispV[0]?.price;

    const stockStatus = minStock <= 0 ? 'out' : minStock <= 5 ? 'critical' : minStock <= 10 ? 'low' : 'ok';
    const stockLabel  = minStock <= 0 ? 'Out of stock' : minStock <= 5 ? `${totalStock} left` : `${totalStock} in stock`;

    // Competitive position vs in-stock competitors
    const inStockPrices = links.filter(l => l.mi_in_stock === true && l.mi_price != null).map(l => +l.mi_price);
    const cheapestComp  = inStockPrices.length ? Math.min(...inStockPrices) : null;
    const isCheapest    = boxPrice != null && cheapestComp != null && boxPrice <= cheapestComp;
    const isOverpriced  = boxPrice != null && cheapestComp != null && !isCheapest;
    const priceDelta    = isOverpriced ? Math.round(((boxPrice - cheapestComp) / cheapestComp) * 100) : null;

    const isSelected = p.shopify_id === selectedProductId;
    const imgSrc     = p.image_url || '';

    return `
    <div class="pcard ${stockStatus === 'out' ? 'pcard-oos' : ''} ${isSelected ? 'pcard-selected' : ''}"
         data-id="${p.shopify_id}" onclick="selectProduct('${p.shopify_id}')">
        <div class="pcard-img-wrap">
            ${imgSrc
                ? `<img class="pcard-img" src="${imgSrc}" alt="${esc(p.title)}" loading="lazy">`
                : `<div class="pcard-img-placeholder">?</div>`}
            <span class="pcard-stock pcard-stock-${stockStatus}">${stockLabel}</span>
            ${isCheapest ? '<span class="pcard-cheapest-badge" title="We have the lowest price">★</span>' : ''}
        </div>
        <div class="pcard-body">
            <div class="pcard-title">${p.title}</div>
            <div class="pcard-footer">
                <span class="pcard-price ${isCheapest ? 'pcard-price-win' : isOverpriced ? 'pcard-price-lose' : ''}">${boxPrice ? fmtNok(boxPrice) : '—'}</span>
                ${isOverpriced && priceDelta ? `<span class="pcard-delta">+${priceDelta}%</span>` : ''}
            </div>
        </div>
    </div>`;
}

// ── Product detail panel (right panel) ───────────────────────────────────────

function renderProductDetail(p) {
    if (!p) return '<div class="prod-no-selection">Select a product from the list</div>';

    const variants   = p.variants || [];
    const links      = productCompLinks[p.shopify_id] || [];
    const mapping    = snkrdunkMappings.find(m => m.product_shopify_id === p.shopify_id && !m.disabled);
    const snkItem    = mapping ? snkrdunkItems.find(i => String(i.id) === String(mapping.snkrdunk_key)) : null;
    const snkJpy     = snkItem ? (snkItem.minPrice || snkItem.minPriceJpy) : null;
    const snkRec     = snkJpy  ? calcSnkrdunkRec(snkJpy) : null;
    const isHidden   = hiddenProductIds.has(p.shopify_id);
    const cost       = productCostHistory[p.shopify_id];

    // Only show box variants; fall back to all if none
    const boxVariants    = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const displayVariants = boxVariants.length ? boxVariants : variants;
    const refVariant      = displayVariants[0];

    // Stock for the reference (box) variant
    const refQty = refVariant ? (refVariant.inventory_quantity ?? 0) : 0;
    const stockSc = refQty <= 0 ? 'pdd-qty-zero' : refQty <= 10 ? 'pdd-qty-low' : 'pdd-qty-ok';

    // Margin calculation — price is inc. 25% VAT, so strip VAT before computing margin
    let marginPct = null;
    if (cost && refVariant?.price) {
        const netPrice = refVariant.price / 1.25;
        marginPct = ((netPrice - cost.last_unit_nok) / netPrice) * 100;
    }
    const marginBadge = marginPct != null
        ? `<span class="badge ${marginPct < 10 ? 'badge-danger' : marginPct < 20 ? 'badge-warning' : 'badge-success'}">${marginPct.toFixed(0)}% margin</span>`
        : '';

    // Stock date
    const sdRaw = p.stock_date || null;
    let stockDateHtml = '—';
    if (sdRaw) {
        const sdDt = new Date(sdRaw + 'T00:00:00');
        const sdFmt = sdDt.toLocaleDateString('nb-NO', {day:'2-digit', month:'2-digit', year:'numeric'});
        const daysUntil = Math.round((sdDt - new Date().setHours(0,0,0,0)) / 86400000);
        const sdClass = daysUntil <= 0 ? 'text-danger' : daysUntil <= 7 ? 'text-warning' : '';
        stockDateHtml = `<span class="${sdClass}" title="${daysUntil <= 0 ? 'Arrived/expired' : daysUntil + ' days'}">${sdFmt}</span>`;
    }

    // Key metrics row
    const metricsHtml = `
    <div class="pdd-metrics">
        <div class="pdd-metric">
            <span class="pdd-metric-value mono">${fmtNok(refVariant?.price)}</span>
            <span class="pdd-metric-label">Our price</span>
        </div>
        <div class="pdd-metric">
            <span class="pdd-metric-value ${stockSc}">${refVariant
                ? `<input type="number" class="qty-input ${stockSc}" value="${refQty}" min="0" step="1"
                       data-orig="${refQty}" style="width:3rem;text-align:center;font-size:.9375rem"
                       onkeydown="if(event.key==='Enter'){this.blur()}"
                       onblur="setInventory(${refVariant.id},this.value,this)">`
                : '—'}</span>
            <span class="pdd-metric-label">Stock</span>
        </div>
        <div class="pdd-metric">
            <span class="pdd-metric-value mono">${cost ? fmtNok(cost.last_unit_nok) : '—'}</span>
            <span class="pdd-metric-label">Last cost</span>
        </div>
        <div class="pdd-metric">
            <span class="pdd-metric-value mono">${cost ? fmtNok(cost.avg_unit_nok_30d) : '—'}</span>
            <span class="pdd-metric-label">30d avg cost</span>
        </div>
        <div class="pdd-metric">
            <span class="pdd-metric-value ${marginPct != null && marginPct < 15 ? 'text-danger' : ''}">${marginPct != null ? marginPct.toFixed(1) + '%' : '—'}</span>
            <span class="pdd-metric-label">Margin</span>
        </div>
        <div class="pdd-metric">
            <span class="pdd-metric-value mono">${snkJpy ? '¥' + fmt(snkJpy) : '—'}</span>
            <span class="pdd-metric-label">SNKRDUNK</span>
        </div>
        <div class="pdd-metric">
            <span class="pdd-metric-value mono ${snkRec && refVariant?.price && Math.abs(refVariant.price - snkRec) > 50 ? 'text-warning' : ''}">${snkRec ? fmtNok(snkRec) : '—'}</span>
            <span class="pdd-metric-label">SNK RRP</span>
        </div>
        <div class="pdd-metric">
            <span class="pdd-metric-value">${stockDateHtml}</span>
            <span class="pdd-metric-label">Stock date</span>
        </div>
    </div>`;

    // Find cheapest competitor — in-stock takes priority, fallback to any priced
    const inStockLinks    = links.filter(l => l.mi_in_stock === true && l.mi_price != null);
    const pricedLinks     = links.filter(l => l.mi_price != null);
    const cheapestLink    = inStockLinks.length
        ? inStockLinks.reduce((a, b) => +a.mi_price <= +b.mi_price ? a : b)
        : pricedLinks.length ? pricedLinks.reduce((a, b) => +a.mi_price <= +b.mi_price ? a : b) : null;
    const minInStockPrice = inStockLinks.length ? Math.min(...inStockLinks.map(l => +l.mi_price)) : null;
    const weCheapest      = refVariant && minInStockPrice != null && +refVariant.price <= minInStockPrice;

    // Sort competitors: cheapest first, then by price
    const sortedLinks = [...links].sort((a, b) => {
        if (a.mi_price == null && b.mi_price == null) return 0;
        if (a.mi_price == null) return 1;
        if (b.mi_price == null) return -1;
        return +a.mi_price - +b.mi_price;
    });

    // Competitor rows — sorted cheapest first
    const compRows = sortedLinks.length
        ? sortedLinks.map(lnk => {
            const inStock    = lnk.mi_in_stock === true;
            const oos        = lnk.mi_in_stock === false;
            const isCheapest    = !weCheapest && cheapestLink && lnk.id === cheapestLink.id;
            const delta         = refVariant && lnk.mi_price != null ? deltaBadge(refVariant.price, lnk.mi_price, true) : '';
            const ageHtml = (() => {
                if (!lnk.mi_updated_at) return '<span class="comp-age comp-age-stale" title="Never updated">—</span>';
                const hrs = (Date.now() - new Date(lnk.mi_updated_at).getTime()) / 3600000;
                if (hrs < 1)   return `<span class="comp-age comp-age-fresh" title="${new Date(lnk.mi_updated_at).toLocaleString('nb-NO')}">${Math.round(hrs*60)}m</span>`;
                if (hrs < 24)  return `<span class="comp-age comp-age-fresh" title="${new Date(lnk.mi_updated_at).toLocaleString('nb-NO')}">${Math.round(hrs)}h</span>`;
                if (hrs < 48)  return `<span class="comp-age comp-age-warn" title="${new Date(lnk.mi_updated_at).toLocaleString('nb-NO')}">1d</span>`;
                return `<span class="comp-age comp-age-stale" title="${new Date(lnk.mi_updated_at).toLocaleString('nb-NO')}">${Math.round(hrs/24)}d</span>`;
            })();
            return `
            <div class="pdd-comp-row${isCheapest ? ' pdd-comp-cheapest' : ''}" data-lid="${lnk.id}">
                <input type="checkbox" class="comp-chk" data-lid="${lnk.id}"
                    ${_selectedCompLinks.has(lnk.id) ? 'checked' : ''}
                    onchange="_compToggle(${lnk.id}, this.checked)">
                <span class="pdd-stock-dot ${inStock ? 'pdd-stock-in' : oos ? 'pdd-stock-oos' : 'pdd-stock-unknown'}"
                      title="${inStock ? 'In stock' : oos ? 'Out of stock' : 'Unknown'}"></span>
                <span class="pdd-comp-domain">${lnk.mi_domain || '—'}</span>
                <span class="pdd-comp-price">${fmtNok(lnk.mi_price)}</span>
                ${isCheapest ? '<span class="pdd-best-badge">Best</span>' : ''}
                ${delta}
                ${ageHtml}
                <span class="pdd-comp-title">${lnk.mi_title || '—'}</span>
                <div class="pdd-comp-btns">
                    ${lnk.mi_source_url ? `<a href="${lnk.mi_source_url}" target="_blank" class="btn btn-xs" title="Open listing">↗</a>` : ''}
                    ${refVariant && lnk.mi_price != null
                        ? `<button class="btn btn-xs btn-primary"
                            onclick="matchPriceComp('${p.shopify_id}','${refVariant.shopify_id}',${lnk.mi_price},'${esc(p.title)}','${esc(refVariant.title || 'Default')}',${refVariant.price},'${esc(lnk.mi_domain)}')">
                            Match</button>`
                        : ''}
                    <button class="btn btn-xs btn-danger" onclick="unlinkCompetitor(${lnk.id})" title="Unlink">×</button>
                </div>
            </div>`;
        }).join('')
        : `<div class="pdd-comp-empty">No competitors linked yet.<br>
           <button class="btn btn-sm btn-primary" style="margin-top:.75rem"
               onclick="openLinkModal('${p.shopify_id}','${esc(p.title)}')">+ Link a competitor</button>
           </div>`;

    return `
    <div class="pdd-header">
        <div class="pdd-header-left">
            <h3 class="pdd-title">${p.title}</h3>
            <div class="pdd-badges">
                ${weCheapest ? '<span class="pdd-cheapest-pill" title="Our price is the lowest among in-stock competitors">★ Lowest price</span>' : ''}
                ${marginBadge}
            </div>
        </div>
        <div class="pdd-header-actions">
            ${isHidden
                ? `<button class="btn btn-xs btn-warning" onclick="unhideProduct('${p.shopify_id}')">Unhide</button>`
                : `<button class="btn btn-xs" onclick="hideProduct('${p.shopify_id}','${esc(p.title)}')" title="Hide from list">Hide</button>`}
            <button class="btn btn-xs btn-refresh" onclick="refreshSingleProduct('${p.shopify_id}')">↻ Refresh</button>
        </div>
    </div>

    ${metricsHtml}

    <div class="pdd-comp-section">
        <div class="pdd-section-head">
            <label class="comp-select-all-label" title="Select all">
                <input type="checkbox" id="comp-chk-all" onchange="_compSelectAll(this.checked, ${JSON.stringify(sortedLinks.map(l => l.id))})">
                <span class="pdd-label">Competitors (${links.length})</span>
            </label>
            <div style="display:flex;gap:.35rem">
                <button class="btn btn-xs btn-auto-match-single" data-id="${p.shopify_id}"
                    onclick="autoMatchProduct('${p.shopify_id}')" title="Auto-match competitors for this product">Auto-match</button>
                <button class="btn btn-xs btn-primary" onclick="openLinkModal('${p.shopify_id}','${esc(p.title)}')">+ Link</button>
            </div>
        </div>
        <div id="comp-bulk-bar" class="comp-bulk-bar" style="display:none">
            <span id="comp-bulk-count">0 selected</span>
            <button class="btn btn-xs btn-danger" onclick="deleteSelectedComps()">Delete selected</button>
            <button class="btn btn-xs" onclick="_compSelectAll(false, ${JSON.stringify(sortedLinks.map(l => l.id))})">Clear</button>
        </div>
        <div class="pdd-comp-list">${compRows}</div>
    </div>

    ${cost ? `<div class="pdd-cost-note muted">Last PO: ${fmtDate(cost.last_po_date)}</div>` : ''}`;
}

function selectProduct(shopifyId) {
    selectedProductId = shopifyId;
    _selectedCompLinks.clear();
    document.querySelectorAll('.pcard').forEach(el => {
        el.classList.toggle('pcard-selected', el.dataset.id === shopifyId);
    });
    const panel   = document.getElementById('prod-detail-panel');
    const product = shopifyProducts.find(p => p.shopify_id === shopifyId);
    if (panel) {
        panel.style.display = 'flex';
        panel.innerHTML = renderProductDetail(product);
    }
}

function _refreshSelectedProduct() {
    if (!selectedProductId) return;
    const product = shopifyProducts.find(p => p.shopify_id === selectedProductId);
    const card    = document.querySelector(`.pcard[data-id="${selectedProductId}"]`);
    if (card && product) {
        const tmp = document.createElement('div');
        tmp.innerHTML = renderProductCard(product);
        card.replaceWith(tmp.firstElementChild);
    }
    const panel = document.getElementById('prod-detail-panel');
    if (panel) panel.innerHTML = renderProductDetail(product);
}

function esc(str) {
    return String(str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ── Competitor linking ────────────────────────────────────────────────────────

function openLinkModal(shopifyProductId, productTitle) {
    linkModalProductId = shopifyProductId;
    _linkStaged = [];
    _linkSearchResults = [];
    _linkSortPrice = 'desc';   // default: highest price first (boxes before singles)
    const sortBtn = document.getElementById('link-sort-btn');
    if (sortBtn) { sortBtn.textContent = 'Price ↓'; sortBtn.classList.add('btn-primary'); }
    document.getElementById('link-modal-title').textContent = `Link competitors — ${productTitle}`;
    document.getElementById('link-search-input').value = '';
    document.getElementById('link-search-results').innerHTML =
        '<p class="muted" style="padding:1.25rem;text-align:center">Search to find competitor products to link…</p>';
    _renderStaging();
    document.getElementById('link-modal').classList.add('open');
    document.getElementById('link-search-input').focus();
}

function closeLinkModal() {
    document.getElementById('link-modal')?.classList.remove('open');
    linkModalProductId = null;
    _linkStaged = [];
}

function _renderStaging() {
    const stagingEl = document.getElementById('link-staging');
    const footerEl  = document.getElementById('link-modal-footer');
    const countEl   = document.getElementById('link-staged-count');
    if (!stagingEl) return;

    if (!_linkStaged.length) {
        stagingEl.innerHTML = '';
        if (footerEl) footerEl.style.display = 'none';
        return;
    }

    if (footerEl) footerEl.style.display = '';
    if (countEl) countEl.textContent = _linkStaged.length;

    stagingEl.innerHTML = `
        <div class="link-staging-bar">
            <span class="link-staging-label">${_linkStaged.length} queued:</span>
            <div class="link-staging-chips">
                ${_linkStaged.map(s => `
                    <span class="link-staged-chip">
                        <span class="link-result-domain">${s.domain}</span>
                        <span class="link-staged-chip-title">${s.title}</span>
                        <button class="link-staged-remove" onclick="unstageLink(${s.id})">×</button>
                    </span>`).join('')}
            </div>
        </div>`;

    // Re-mark result buttons
    document.querySelectorAll('[data-link-id]').forEach(btn => {
        const id = parseInt(btn.dataset.linkId);
        const staged = _linkStaged.some(s => s.id === id);
        btn.textContent = staged ? '✓ Added' : 'Add';
        btn.classList.toggle('btn-staged', staged);
        btn.classList.toggle('btn-primary', !staged);
    });
}

function stageLinkProduct(id, domain, title, price, inStock, url) {
    if (_linkStaged.some(s => s.id === id)) {
        unstageLink(id);
        return;
    }
    _linkStaged.push({ id, domain, title, price, inStock, url });
    _renderStaging();
}

function unstageLink(id) {
    _linkStaged = _linkStaged.filter(s => s.id !== id);
    _renderStaging();
}

async function commitStagedLinks() {
    if (!linkModalProductId || !_linkStaged.length) return;

    const btn = document.getElementById('link-modal-footer')?.querySelector('button');
    if (btn) { btn.disabled = true; btn.textContent = 'Linking…'; }

    const staged = [..._linkStaged];
    let added = 0, skipped = 0;

    for (const s of staged) {
        try {
            const link = await api('/competitor-links', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    shopify_product_id: linkModalProductId,
                    mi_product_id:  s.id,
                    mi_domain:      s.domain,
                    mi_title:       s.title,
                    mi_price:       s.price,
                    mi_in_stock:    s.inStock,
                    mi_source_url:  s.url,
                }),
            });
            (productCompLinks[linkModalProductId] ||= []).push(link);
            added++;
        } catch (e) {
            if (e.message.includes('409')) skipped++;
        }
    }

    // Refresh selected product if it's the one we just linked
    if (linkModalProductId === selectedProductId || !selectedProductId) {
        selectedProductId = linkModalProductId;
        _refreshSelectedProduct();
    }

    _linkStaged = [];
    _renderStaging();
    toast(added ? `Linked ${added} competitor${added !== 1 ? 's' : ''}${skipped ? ` (${skipped} already linked)` : ''}` : 'Already linked.', added ? 'success' : 'info');
}

function searchLinkProducts() {
    const q  = (document.getElementById('link-search-input')?.value || '').trim();
    const el = document.getElementById('link-search-results');

    if (!q || q.length < 2) {
        el.innerHTML = '<p class="muted" style="padding:1.25rem;text-align:center">Type to search…</p>';
        return;
    }

    clearTimeout(_linkSearchTimer);
    el.innerHTML = '<div class="loading-spinner" style="padding:1rem;text-align:center">Searching…</div>';

    _linkSearchTimer = setTimeout(async () => {
        try {
            _linkSearchResults = await api(`/marketintel/competitor-products?search=${encodeURIComponent(q)}&limit=200`);
            renderLinkResults();
        } catch (e) {
            el.innerHTML = `<p class="error" style="padding:1rem">Search failed: ${e.message}</p>`;
        }
    }, 300);
}

function renderLinkResults() {
    const el = document.getElementById('link-search-results');
    if (!el) return;
    const filtered = _linkSearchResults.filter(r => (r.price ?? 0) >= competitorMinPrice);
    if (!filtered.length) {
        const total = _linkSearchResults.length;
        el.innerHTML = `<p class="muted" style="padding:1.25rem;text-align:center">No results above min price kr ${competitorMinPrice}${total ? ` (${total} results below threshold hidden)` : ''}.</p>`;
        return;
    }
    let results = filtered;
    if (_linkSortPrice === 'asc')  results = [...results].sort((a, b) => (a.price ?? Infinity) - (b.price ?? Infinity));
    if (_linkSortPrice === 'desc') results = [...results].sort((a, b) => (b.price ?? -Infinity) - (a.price ?? -Infinity));
    el.innerHTML = results.map(r => {
        const staged = _linkStaged.some(s => s.id === r.id);
        return `
        <div class="link-result-row">
            <div class="link-result-info">
                <span class="link-result-domain">${r.competitor_domain || '—'}</span>
                <span class="link-result-title"><strong>${r.title}</strong></span>
                <span class="mono link-result-price">${fmtNok(r.price)}</span>
                ${r.in_stock === true  ? '<span class="badge badge-success badge-sm">In stock</span>'
                : r.in_stock === false ? '<span class="badge badge-danger badge-sm">OOS</span>' : ''}
            </div>
            <button class="btn btn-sm ${staged ? 'btn-staged' : 'btn-primary'}"
                data-link-id="${r.id}"
                onclick="stageLinkProduct(${r.id},'${esc(r.competitor_domain||'')}','${esc(r.title)}',${r.price??'null'},${!!r.in_stock},'${esc(r.source_url||'')}')">
                ${staged ? '✓ Added' : 'Add'}
            </button>
        </div>`;
    }).join('');
}

function toggleLinkSort() {
    _linkSortPrice = _linkSortPrice === null ? 'asc' : _linkSortPrice === 'asc' ? 'desc' : null;
    const btn = document.getElementById('link-sort-btn');
    if (btn) {
        btn.textContent = _linkSortPrice === 'asc' ? 'Price ↑' : _linkSortPrice === 'desc' ? 'Price ↓' : 'Price ↕';
        btn.classList.toggle('btn-primary', _linkSortPrice !== null);
    }
    renderLinkResults();
}

async function unlinkCompetitor(linkId) {
    if (!confirm('Remove this competitor link?')) return;
    try {
        await api(`/competitor-links/${linkId}`, { method: 'DELETE' });
        for (const pid of Object.keys(productCompLinks)) {
            productCompLinks[pid] = productCompLinks[pid].filter(l => l.id !== linkId);
        }
        toast('Link removed', 'success');
        _refreshSelectedProduct();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    }
}

function _compToggle(linkId, checked) {
    if (checked) _selectedCompLinks.add(linkId);
    else _selectedCompLinks.delete(linkId);
    _updateCompBulkBar();
}

function _compSelectAll(checked, allIds) {
    if (checked) allIds.forEach(id => _selectedCompLinks.add(id));
    else _selectedCompLinks.clear();
    document.querySelectorAll('.comp-chk').forEach(cb => { cb.checked = checked; });
    const allChk = document.getElementById('comp-chk-all');
    if (allChk) allChk.checked = checked;
    _updateCompBulkBar();
}

function _updateCompBulkBar() {
    const bar = document.getElementById('comp-bulk-bar');
    const cnt = document.getElementById('comp-bulk-count');
    if (!bar) return;
    const n = _selectedCompLinks.size;
    if (n > 0) {
        bar.style.display = 'flex';
        if (cnt) cnt.textContent = `${n} selected`;
    } else {
        bar.style.display = 'none';
    }
    const allChk = document.getElementById('comp-chk-all');
    if (allChk) {
        const total = document.querySelectorAll('.comp-chk').length;
        allChk.indeterminate = n > 0 && n < total;
        allChk.checked = total > 0 && n === total;
    }
}

async function deleteSelectedComps() {
    const ids = [..._selectedCompLinks];
    if (!ids.length) return;
    if (!confirm(`Delete ${ids.length} competitor link${ids.length > 1 ? 's' : ''}?`)) return;
    let ok = 0, fail = 0;
    for (const id of ids) {
        try {
            await api(`/competitor-links/${id}`, { method: 'DELETE' });
            for (const pid of Object.keys(productCompLinks)) {
                productCompLinks[pid] = productCompLinks[pid].filter(l => l.id !== id);
            }
            ok++;
        } catch { fail++; }
    }
    _selectedCompLinks.clear();
    if (fail) toast(`Deleted ${ok}, failed ${fail}`, 'warning');
    else toast(`Deleted ${ok} link${ok > 1 ? 's' : ''}`, 'success');
    _refreshSelectedProduct();
}

async function refreshSingleProduct(shopifyProductId) {
    const p = shopifyProducts.find(x => x.shopify_id === shopifyProductId);
    if (!p) return;
    const btn = document.querySelector('.pdd-header-actions .btn-refresh');
    if (btn) { btn.disabled = true; btn.textContent = '…'; }
    try {
        await api(`/shopify/products/${p.id}/refresh`, { method: 'POST' });
        const [prods, allLinks] = await Promise.all([
            api('/shopify/products?limit=500'),
            api('/competitor-links'),
        ]);
        shopifyProducts = prods.products || prods || [];
        productCompLinks = {};
        for (const lnk of allLinks) (productCompLinks[lnk.shopify_product_id] ||= []).push(lnk);
        toast('Refreshed from Shopify', 'success');
        _refreshSelectedProduct();
    } catch (e) {
        toast(`Refresh failed: ${e.message}`, 'error');
    } finally {
        if (btn) { btn.disabled = false; btn.textContent = '↻ Refresh'; }
    }
}

async function setInventory(variantId, newQty, el) {
    const n = parseInt(newQty, 10);
    const orig = parseInt(el.dataset.orig, 10);
    if (isNaN(n) || n < 0) { el.value = orig; return; }
    if (n === orig) return;
    el.disabled = true;
    try {
        await api(`/shopify/variants/${variantId}/set-inventory`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ quantity: n }),
        });
        el.dataset.orig = n;
        for (const prod of shopifyProducts) {
            for (const v of (prod.variants || [])) {
                if (v.id === variantId) { v.inventory_quantity = n; break; }
            }
        }
        toast(`Stock updated to ${n}`, 'success');
        _refreshSelectedProduct();
    } catch (e) {
        el.value = orig;
        toast(`Stock update failed: ${e.message}`, 'error');
    } finally {
        el.disabled = false;
    }
}

// ── Price matching ────────────────────────────────────────────────────────────

async function matchPriceComp(productShopifyId, variantShopifyId, newPrice, productTitle, variantTitle, currentPrice, competitorDomain) {
    if (!confirm(`Match price to ${competitorDomain}?\n${productTitle} — ${variantTitle}\n${fmtNok(currentPrice)} → ${fmtNok(newPrice)}`)) return;
    await _createMatchPlan(productShopifyId, variantShopifyId, newPrice, currentPrice, productTitle, variantTitle);
}

async function matchPriceSnkrdunk(productShopifyId, variantShopifyId, newPrice, productTitle, variantTitle, currentPrice) {
    if (!confirm(`Set SNKRDUNK recommended price?\n${productTitle} — ${variantTitle}\n${fmtNok(currentPrice)} → ${fmtNok(newPrice)}`)) return;
    await _createMatchPlan(productShopifyId, variantShopifyId, newPrice, currentPrice, productTitle, variantTitle);
}

async function _createMatchPlan(productShopifyId, variantShopifyId, newPrice, currentPrice, productTitle, variantTitle) {
    try {
        const plan = await api('/price-plans/generate', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                strategy:  'match_competition',
                plan_type: 'price_update',
                items: [{
                    product_shopify_id: productShopifyId,
                    variant_shopify_id: variantShopifyId,
                    current_price:      currentPrice,
                    new_price:          newPrice,
                    current_title:      `${productTitle} — ${variantTitle}`,
                }],
            }),
        });

        // Immediately apply — no manual review needed for single-product matches
        const res = await api(`/price-plans/${plan.id}/apply`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
        });

        toast(`Price updated: ${fmtNok(currentPrice)} → ${fmtNok(newPrice)} (${res.applied_items || 0} variant updated)`, 'success');

        // Re-fetch the product so the new price shows in the panel
        try {
            const updated = await api(`/shopify/products/shopify/${productShopifyId}`);
            const idx = shopifyProducts.findIndex(p => p.shopify_id === productShopifyId);
            if (idx !== -1 && updated) shopifyProducts[idx] = updated;
        } catch (_) { /* best-effort */ }
        _refreshSelectedProduct();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// PURCHASE ORDERS
// ─────────────────────────────────────────────────────────────────────────────

// Temp cache for search results so click handler can look up by index
let _poSearchMatches = [];

async function loadPurchaseOrders() {
    showTabLoading('po-history-list');
    const dateEl = document.getElementById('po-order-date');
    if (dateEl && !dateEl.value) dateEl.value = new Date().toISOString().slice(0, 10);
    try {
        const orders = await api('/purchase-orders?limit=50');
        renderPoHistory(orders);
        document.getElementById('po-count').textContent = `${orders.length} orders`;
    } catch (e) {
        document.getElementById('po-history-list').innerHTML = `<p class="error">${e.message}</p>`;
    }
}

function renderPoHistory(orders) {
    const el = document.getElementById('po-history-list');
    if (!orders?.length) {
        el.innerHTML = '<p class="muted" style="padding:1rem 1.25rem">No purchase orders yet.</p>';
        return;
    }
    el.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>ID</th><th>Date</th><th>Items</th><th>Total Qty</th>
                <th>Total JPY</th><th>Shipping JPY</th><th>Total NOK</th>
                <th>Status</th><th></th>
            </tr></thead>
            <tbody>
                ${orders.map(o => `
                    <tr>
                        <td class="mono">#${o.id}</td>
                        <td>${fmtDate(o.order_date)}</td>
                        <td>${o.total_items}</td>
                        <td>${fmt(o.total_quantity)}</td>
                        <td class="mono">&yen;${fmt(o.total_jpy, 0)}</td>
                        <td class="mono">&yen;${fmt(o.shipping_cost_jpy, 0)}</td>
                        <td class="mono"><strong>${fmtNok(o.total_nok)}</strong></td>
                        <td><span class="badge ${o.status === 'completed' ? 'badge-success' : 'badge-neutral'}">${o.status}</span></td>
                        <td>
                            <button class="btn btn-xs" onclick="viewPurchaseOrder(${o.id})">View</button>
                            ${o.status === 'completed' ? `<button class="btn btn-xs btn-danger-outline" onclick="cancelPurchaseOrder(${o.id})">Cancel</button>` : ''}
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>`;
}

// ── Product search ───────────────────────────────────────────────────────────

function poSearchProducts() {
    clearTimeout(poSearchTimer);
    const q = document.getElementById('po-product-search')?.value?.trim();
    const resultsEl = document.getElementById('po-search-results');
    if (!q || q.length < 2) { resultsEl.style.display = 'none'; return; }

    poSearchTimer = setTimeout(async () => {
        try {
            if (!shopifyProducts.length) {
                const res = await api('/shopify/products?limit=500');
                shopifyProducts = res.products || res || [];
            }
            const qLower = q.toLowerCase();
            _poSearchMatches = [];
            for (const p of shopifyProducts) {
                for (const v of (p.variants || [])) {
                    if (
                        p.title.toLowerCase().includes(qLower) ||
                        (v.sku || '').toLowerCase().includes(qLower) ||
                        (v.title || '').toLowerCase().includes(qLower)
                    ) {
                        _poSearchMatches.push({
                            variant_id: v.id,
                            product_title: p.title,
                            variant_title: v.title || 'Default',
                            sku: v.sku || '',
                            price: v.price,
                            inventory_quantity: v.inventory_quantity || 0,
                            weight_grams: v.weight_grams || null,
                            product_shopify_id: p.shopify_id || null,
                        });
                    }
                }
            }
            if (!_poSearchMatches.length) {
                resultsEl.innerHTML = '<p class="muted" style="padding:.5rem">No variants found.</p>';
            } else {
                resultsEl.innerHTML = _poSearchMatches.slice(0, 20).map((m, idx) => `
                    <div class="po-search-item" data-po-idx="${idx}">
                        <span class="po-search-name">${m.product_title} &mdash; ${m.variant_title}</span>
                        <span class="po-search-meta">SKU: ${m.sku || '—'} &middot; Stock: ${m.inventory_quantity} &middot; ${fmtNok(m.price)}${m.weight_grams ? ` &middot; ${fmt(m.weight_grams, 0)}g` : ''}</span>
                    </div>
                `).join('');
            }
            resultsEl.style.display = 'block';
        } catch (e) {
            resultsEl.innerHTML = `<p class="error">${e.message}</p>`;
            resultsEl.style.display = 'block';
        }
    }, 300);
}

function _handlePoSearchClick(e) {
    const item = e.target.closest('.po-search-item');
    if (!item) return;
    const idx = parseInt(item.dataset.poIdx, 10);
    const m = _poSearchMatches[idx];
    if (!m) return;

    if (poLineItems.find(i => i.variant_id === m.variant_id)) {
        toast('Variant already added', 'warning');
        return;
    }
    poLineItems.push({
        variant_id: m.variant_id,
        product_title: m.product_title,
        variant_title: m.variant_title,
        sku: m.sku,
        quantity: 1,
        price_jpy: 0,
        weight_grams: m.weight_grams || 0,
        inventory_quantity: m.inventory_quantity,
        product_shopify_id: m.product_shopify_id,
    });
    document.getElementById('po-product-search').value = '';
    document.getElementById('po-search-results').style.display = 'none';
    renderPoLineItems();
}

// ── Line items ───────────────────────────────────────────────────────────────

function removePoLineItem(variantId) {
    poLineItems = poLineItems.filter(i => i.variant_id !== variantId);
    renderPoLineItems();
}

function updatePoLineItem(variantId, field, value) {
    const item = poLineItems.find(i => i.variant_id === variantId);
    if (!item) return;
    item[field] = parseFloat(value) || 0;

    // Update line total + footer in-place (no re-render, preserves focus/tab order)
    const row = document.querySelector(`tr[data-po-vid="${variantId}"]`);
    if (row) {
        const lineCell = row.querySelector('.po-line-total');
        if (lineCell) lineCell.innerHTML = `&yen;${fmt(item.quantity * item.price_jpy, 0)}`;
    }
    _updatePoFooterTotals();

    // Persist weight locally so it pre-fills on future POs
    if (field === 'weight_grams' && item[field] > 0) {
        fetch(`/api/v1/shopify/variants/${variantId}/weight?weight_grams=${item[field]}`, { method: 'PATCH' })
            .catch(err => console.warn('Failed to save weight:', err));
    }
}

function _updatePoFooterTotals() {
    const totalQty = poLineItems.reduce((s, i) => s + i.quantity, 0);
    const totalWeight = poLineItems.reduce((s, i) => s + (i.weight_grams || 0) * i.quantity, 0);
    const totalJpy = poLineItems.reduce((s, i) => s + i.quantity * i.price_jpy, 0);
    const qtyEl = document.getElementById('po-foot-qty');
    const weightEl = document.getElementById('po-foot-weight');
    const jpyEl = document.getElementById('po-foot-jpy');
    if (qtyEl) qtyEl.textContent = totalQty;
    if (weightEl) weightEl.textContent = totalWeight ? fmt(totalWeight, 0) + 'g' : '';
    if (jpyEl) jpyEl.innerHTML = `&yen;${fmt(totalJpy, 0)}`;
}

function renderPoLineItems() {
    const wrap = document.getElementById('po-line-items-wrap');
    if (!poLineItems.length) {
        wrap.innerHTML = '<p class="muted" style="font-size:.8125rem">No items added yet. Search and click a variant above.</p>';
        return;
    }
    wrap.innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>Product</th><th>Variant</th><th>SKU</th><th>Stock</th>
                <th style="width:70px">Qty</th><th style="width:110px">Price (JPY)</th>
                <th style="width:100px">Weight (g)</th><th>Line JPY</th><th></th>
            </tr></thead>
            <tbody>
                ${poLineItems.map(i => `
                    <tr data-po-vid="${i.variant_id}">
                        <td>${i.product_title}</td>
                        <td>${i.variant_title}</td>
                        <td class="mono muted">${i.sku || '—'}</td>
                        <td class="mono ${stockClass(i.inventory_quantity)}">${i.inventory_quantity}</td>
                        <td><input type="number" class="input-sm" value="${i.quantity}" min="1" style="width:65px"
                            oninput="updatePoLineItem(${i.variant_id}, 'quantity', this.value)" /></td>
                        <td><input type="number" class="input-sm" value="${i.price_jpy}" min="0" style="width:105px"
                            oninput="updatePoLineItem(${i.variant_id}, 'price_jpy', this.value)" /></td>
                        <td><input type="number" class="input-sm" value="${i.weight_grams || ''}" min="0" style="width:90px"
                            placeholder="g" oninput="updatePoLineItem(${i.variant_id}, 'weight_grams', this.value)" /></td>
                        <td class="mono po-line-total">&yen;${fmt(i.quantity * i.price_jpy, 0)}</td>
                        <td><button class="btn btn-xs btn-danger-outline" tabindex="-1" onclick="removePoLineItem(${i.variant_id})">Remove</button></td>
                    </tr>
                `).join('')}
            </tbody>
            <tfoot><tr>
                <td colspan="4" style="text-align:right"><strong>Totals:</strong></td>
                <td class="mono"><strong id="po-foot-qty">${poLineItems.reduce((s, i) => s + i.quantity, 0)}</strong></td>
                <td></td>
                <td class="mono muted" id="po-foot-weight">${fmt(poLineItems.reduce((s, i) => s + (i.weight_grams || 0) * i.quantity, 0), 0)}g</td>
                <td class="mono"><strong id="po-foot-jpy">&yen;${fmt(poLineItems.reduce((s, i) => s + i.quantity * i.price_jpy, 0), 0)}</strong></td>
                <td></td>
            </tr></tfoot>
        </table>`;
}

// ── Form controls ────────────────────────────────────────────────────────────

function togglePoForm() {
    const form = document.getElementById('po-form');
    form.style.display = form.style.display === 'none' ? 'block' : 'none';
}

function clearPoForm() {
    poLineItems = [];
    document.getElementById('po-product-search').value = '';
    document.getElementById('po-shipping-jpy').value = '0';
    document.getElementById('po-total-nok').value = '';
    document.getElementById('po-notes').value = '';
    document.getElementById('po-search-results').style.display = 'none';
    renderPoLineItems();
}

// ── Preview ──────────────────────────────────────────────────────────────────

function _poCalcRows(items, shippingJpy, totalNok) {
    const totalItemJpy = items.reduce((s, i) => s + (i.quantity || 0) * (i.price_jpy || 0), 0);
    const totalWeight = items.reduce((s, i) => s + ((i.weight_grams || 0) * (i.quantity || 0)), 0);
    const totalQty = items.reduce((s, i) => s + (i.quantity || 0), 0);
    const useWeight = totalWeight > 0;
    const grandTotalJpy = totalItemJpy + shippingJpy;

    const rows = items.map(i => {
        const lineJpy = i.quantity * i.price_jpy;
        const lineWeight = (i.weight_grams || 0) * i.quantity;
        const shippingShare = useWeight
            ? (totalWeight > 0 ? (lineWeight / totalWeight) * shippingJpy : 0)
            : (totalQty > 0 ? (i.quantity / totalQty) * shippingJpy : 0);
        const lineTotalJpy = lineJpy + shippingShare;
        const lineNok = grandTotalJpy > 0 ? (lineTotalJpy / grandTotalJpy) * totalNok : 0;
        const unitNok = i.quantity > 0 ? lineNok / i.quantity : 0;
        return { ...i, lineJpy, lineWeight, shippingShare, lineTotalJpy, lineNok, unitNok };
    });

    return { rows, totalItemJpy, totalWeight, totalQty, useWeight, grandTotalJpy };
}

function _poValidate() {
    // Clear previous error highlights
    document.querySelectorAll('.input-error').forEach(el => el.classList.remove('input-error'));
    if (!poLineItems.length) { toast('Add at least one line item', 'warning'); return false; }
    const nokEl = document.getElementById('po-total-nok');
    const totalNok = parseFloat(nokEl?.value);
    if (!totalNok || totalNok <= 0) {
        toast('Enter the total NOK paid', 'warning');
        nokEl?.classList.add('input-error');
        nokEl?.focus();
        return false;
    }
    for (const item of poLineItems) {
        if (item.quantity <= 0) {
            toast(`Set quantity for ${item.product_title}`, 'warning');
            const inp = document.querySelector(`tr[data-po-vid="${item.variant_id}"] input[type="number"]`);
            inp?.classList.add('input-error');
            inp?.focus();
            return false;
        }
        if (item.price_jpy <= 0) {
            toast(`Set JPY price for ${item.product_title}`, 'warning');
            const row = document.querySelector(`tr[data-po-vid="${item.variant_id}"]`);
            const inp = row?.querySelectorAll('input[type="number"]')[1];
            inp?.classList.add('input-error');
            inp?.focus();
            return false;
        }
    }
    return true;
}

function _showPoDetail(html) {
    const section = document.getElementById('po-detail-section');
    const body = document.getElementById('po-detail-body');
    if (!section || !body) return;
    body.innerHTML = html;
    section.style.display = 'block';
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function _hidePoDetail() {
    const section = document.getElementById('po-detail-section');
    if (section) section.style.display = 'none';
}

function _poDetailTableHtml(rows, totalItemJpy, totalWeight, totalQty, shippingJpy, grandTotalJpy, totalNok, storeName) {
    const shopifyUrl = sid => {
        if (!storeName || !sid) return null;
        const numericId = sid.replace('gid://shopify/Product/', '');
        return `https://admin.shopify.com/store/${storeName}/products/${numericId}`;
    };
    return `
        <table class="data-table po-detail-table">
            <thead><tr>
                <th>Product / Variant</th><th class="r">Qty</th><th class="r">Weight</th>
                <th class="r">Unit JPY</th><th class="r">Line JPY</th><th class="r">+ Ship</th>
                <th class="r">Total JPY</th><th class="r">Unit NOK</th><th class="r">Line NOK</th>
                ${storeName ? '<th>Shopify</th>' : ''}
            </tr></thead>
            <tbody>
                ${rows.map(r => {
                    const url = r.product_shopify_id ? shopifyUrl(r.product_shopify_id) : null;
                    return `
                    <tr>
                        <td><strong>${r.product_title || '—'}</strong><br><span class="muted" style="font-size:.75rem">${r.variant_title || '—'}${r.sku ? ' &middot; ' + r.sku : ''}</span></td>
                        <td class="mono r">${r.quantity}</td>
                        <td class="mono r muted">${r.lineWeight ? fmt(r.lineWeight, 0) + 'g' : '—'}</td>
                        <td class="mono r">&yen;${fmt(r.price_jpy, 0)}</td>
                        <td class="mono r">&yen;${fmt(r.lineJpy, 0)}</td>
                        <td class="mono r muted">&yen;${fmt(r.shippingShare, 0)}</td>
                        <td class="mono r">&yen;${fmt(r.lineTotalJpy, 0)}</td>
                        <td class="mono r">${fmtNok(r.unitNok)}</td>
                        <td class="mono r"><strong>${fmtNok(r.lineNok)}</strong></td>
                        ${storeName ? `<td>${url ? `<a href="${url}" target="_blank" class="btn btn-xs" title="Open in Shopify admin">Edit</a>` : '—'}</td>` : ''}
                    </tr>`;
                }).join('')}
            </tbody>
            <tfoot><tr class="po-totals-row">
                <td><strong>Totals</strong></td>
                <td class="mono r"><strong>${totalQty}</strong></td>
                <td class="mono r muted">${totalWeight ? fmt(totalWeight, 0) + 'g' : ''}</td>
                <td class="r"></td>
                <td class="mono r"><strong>&yen;${fmt(totalItemJpy, 0)}</strong></td>
                <td class="mono r muted">&yen;${fmt(shippingJpy, 0)}</td>
                <td class="mono r"><strong>&yen;${fmt(grandTotalJpy, 0)}</strong></td>
                <td class="r"></td>
                <td class="mono r"><strong>${fmtNok(totalNok)}</strong></td>
                ${storeName ? '<td></td>' : ''}
            </tr></tfoot>
        </table>`;
}

function previewPurchaseOrder() {
    if (!_poValidate()) return;

    const totalNok = parseFloat(document.getElementById('po-total-nok').value);
    const shippingJpy = parseFloat(document.getElementById('po-shipping-jpy')?.value) || 0;
    const { rows, totalItemJpy, totalWeight, totalQty, useWeight, grandTotalJpy } =
        _poCalcRows(poLineItems, shippingJpy, totalNok);

    const orderDate = document.getElementById('po-order-date')?.value || new Date().toISOString().slice(0, 10);
    const notes = document.getElementById('po-notes')?.value?.trim() || '';
    const effectiveRate = grandTotalJpy > 0 ? (totalNok / grandTotalJpy).toFixed(4) : '—';

    // Hide the form, show inline preview
    document.getElementById('po-form-card').style.display = 'none';

    _showPoDetail(`
        <h3 style="margin:0 0 .75rem">Preview Purchase Order</h3>
        <div class="po-meta-grid">
            <div class="po-meta-item"><span class="po-meta-label">Date</span><span>${orderDate}</span></div>
            <div class="po-meta-item"><span class="po-meta-label">Shipping</span><span>&yen;${fmt(shippingJpy, 0)}</span></div>
            <div class="po-meta-item"><span class="po-meta-label">Split by</span><span>${useWeight ? 'weight' : 'quantity'}</span></div>
            <div class="po-meta-item"><span class="po-meta-label">Rate</span><span>${effectiveRate} NOK/JPY</span></div>
            ${notes ? `<div class="po-meta-item" style="grid-column:1/-1"><span class="po-meta-label">Notes</span><span>${notes}</span></div>` : ''}
        </div>

        ${_poDetailTableHtml(rows, totalItemJpy, totalWeight, totalQty, shippingJpy, grandTotalJpy, totalNok, null)}

        <div class="po-footer">
            <div class="po-summary-bar">
                <span>Total paid: <strong>${fmtNok(totalNok)}</strong></span>
                <span>Effective rate: <strong>${effectiveRate}</strong> NOK/JPY</span>
            </div>
            <div class="po-actions">
                <button class="btn" onclick="closePoPreview()">Back to edit</button>
                <button class="btn btn-primary" id="btn-confirm-po" onclick="confirmSavePurchaseOrder()">
                    Confirm &amp; Save
                </button>
            </div>
        </div>`);
}

function closePoPreview() {
    _hidePoDetail();
    document.getElementById('po-form-card').style.display = '';
}

// ── Save ─────────────────────────────────────────────────────────────────────

async function confirmSavePurchaseOrder() {
    const btn = document.getElementById('btn-confirm-po');
    if (btn) btn.disabled = true;

    const orderDate = document.getElementById('po-order-date')?.value || null;
    const shippingJpy = parseFloat(document.getElementById('po-shipping-jpy')?.value) || 0;
    const totalNok = parseFloat(document.getElementById('po-total-nok')?.value);
    const notes = document.getElementById('po-notes')?.value?.trim() || null;

    try {
        const result = await api('/purchase-orders', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                order_date: orderDate ? new Date(orderDate).toISOString() : null,
                shipping_cost_jpy: shippingJpy,
                total_nok: totalNok,
                notes: notes,
                items: poLineItems.map(i => ({
                    variant_id: i.variant_id,
                    quantity: i.quantity,
                    price_jpy: i.price_jpy,
                    weight_grams: i.weight_grams || null,
                })),
            }),
        });
        if (result.auto_update_shopify) {
            toast(`PO #${result.id} saved — Shopify inventory updated`, 'success');
        } else {
            toast(`PO #${result.id} saved — update Shopify inventory manually`, 'success');
        }
        clearPoForm();
        loadPurchaseOrders();
        // Show the saved PO detail inline (includes Shopify links)
        viewPurchaseOrder(result.id);
    } catch (e) {
        toast(`Failed to save PO: ${e.message}`, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

// ── View / Cancel ────────────────────────────────────────────────────────────

async function viewPurchaseOrder(poId) {
    try {
        const po = await api(`/purchase-orders/${poId}`);

        const { rows, totalItemJpy, totalWeight, totalQty, grandTotalJpy } =
            _poCalcRows(po.items || [], po.shipping_cost_jpy, po.total_nok);

        const effectiveRate = grandTotalJpy > 0 ? (po.total_nok / grandTotalJpy).toFixed(4) : '—';
        const storeName = po.store_name;

        // Hide the form card, show detail inline
        document.getElementById('po-form-card').style.display = 'none';

        _showPoDetail(`
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:.75rem">
                <h3 style="margin:0">Purchase Order #${po.id}
                    <span class="badge ${po.status === 'completed' ? 'badge-success' : 'badge-neutral'}">${po.status}</span>
                </h3>
                <button class="btn btn-sm" onclick="closePoPreview()">Back to list</button>
            </div>
            <div class="po-meta-grid">
                <div class="po-meta-item"><span class="po-meta-label">Date</span><span>${fmtDate(po.order_date)}</span></div>
                <div class="po-meta-item"><span class="po-meta-label">FX Rate</span><span>${po.fx_rate_snapshot ? po.fx_rate_snapshot.toFixed(4) : '—'}</span></div>
                <div class="po-meta-item"><span class="po-meta-label">Shipping</span><span>&yen;${fmt(po.shipping_cost_jpy, 0)}</span></div>
                <div class="po-meta-item"><span class="po-meta-label">Total paid</span><span><strong>${fmtNok(po.total_nok)}</strong></span></div>
                ${po.notes ? `<div class="po-meta-item" style="grid-column:1/-1"><span class="po-meta-label">Notes</span><span>${po.notes}</span></div>` : ''}
            </div>

            ${_poDetailTableHtml(rows, totalItemJpy, totalWeight, totalQty, po.shipping_cost_jpy, grandTotalJpy, po.total_nok, storeName)}

            <div class="po-footer">
                <div class="po-summary-bar">
                    <span>Total paid: <strong>${fmtNok(po.total_nok)}</strong></span>
                    <span>Effective rate: <strong>${effectiveRate}</strong> NOK/JPY</span>
                </div>
                <div class="po-actions">
                    <button class="btn btn-primary" onclick="startNewPurchaseOrder()">+ New Purchase Order</button>
                </div>
            </div>`);
    } catch (e) {
        toast(`Failed to load PO: ${e.message}`, 'error');
    }
}

function startNewPurchaseOrder() {
    clearPoForm();
    _hidePoDetail();
    document.getElementById('po-form-card').style.display = '';
    document.getElementById('po-product-search')?.focus();
}

async function cancelPurchaseOrder(poId) {
    if (!confirm(`Cancel PO #${poId} and revert inventory (subtract quantities back from Shopify)?`)) return;
    try {
        await api(`/purchase-orders/${poId}/cancel?revert_inventory=true`, { method: 'POST' });
        toast(`PO #${poId} cancelled and inventory reverted`, 'success');
        loadPurchaseOrders();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────────────────
// ── Theme ─────────────────────────────────────────────────────────────────────
function _applyTheme(dark) {
    document.documentElement.setAttribute('data-theme', dark ? 'dark' : 'light');
    const iconDark  = document.getElementById('theme-icon-dark');
    const iconLight = document.getElementById('theme-icon-light');
    const label     = document.getElementById('theme-label');
    if (iconDark)  iconDark.style.display  = dark ? 'none' : '';
    if (iconLight) iconLight.style.display = dark ? ''     : 'none';
    if (label)     label.textContent       = dark ? 'Light mode' : 'Dark mode';
}
function toggleTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    localStorage.setItem('theme', isDark ? 'light' : 'dark');
    _applyTheme(!isDark);
}

document.addEventListener('DOMContentLoaded', () => {
    // Apply saved theme immediately
    _applyTheme(localStorage.getItem('theme') === 'dark');

    // Nav clicks
    document.querySelectorAll('.nav-item[data-tab]').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Modal close on backdrop
    document.getElementById('plan-modal')?.addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });

    // Price monitor filter buttons
    document.querySelectorAll('.pm-filter-btn').forEach(b => {
        b.addEventListener('click', () => setPmFilter(b.dataset.filter));
    });

    // Stock filter (old stock tab — kept for compatibility)
    document.getElementById('stock-filter')?.addEventListener('change', renderStock);

    // Products tab — search
    document.getElementById('product-search')?.addEventListener('input', e => {
        productSearchQuery = e.target.value;
        renderProducts();
    });

    // Products tab — filter pills (toggle)
    document.querySelectorAll('.filter-pill[data-filter]').forEach(btn => {
        btn.addEventListener('click', () => {
            const key = btn.dataset.filter;
            if (key === 'hidden') {
                // Hidden is exclusive — clear others when activating
                const willActivate = !productActiveFilters.has('hidden');
                productActiveFilters.clear();
                if (willActivate) productActiveFilters.add('hidden');
            } else {
                productActiveFilters.delete('hidden');
                if (productActiveFilters.has(key)) productActiveFilters.delete(key);
                else productActiveFilters.add(key);
            }
            // Sync pill active states
            document.querySelectorAll('.filter-pill[data-filter]').forEach(b =>
                b.classList.toggle('filter-pill-active', productActiveFilters.has(b.dataset.filter))
            );
            renderProducts();
        });
    });

    // Products tab — sort
    document.getElementById('product-sort')?.addEventListener('change', e => {
        productSort = e.target.value;
        renderProducts();
    });

    // Link modal — close on backdrop click
    document.getElementById('link-modal')?.addEventListener('click', e => {
        if (e.target === e.currentTarget) closeLinkModal();
    });

    // PO search results — delegated click handler
    document.getElementById('po-search-results')?.addEventListener('click', _handlePoSearchClick);

    // Close PO search dropdown when clicking outside
    document.addEventListener('click', e => {
        const searchEl = document.getElementById('po-product-search');
        const resultsEl = document.getElementById('po-search-results');
        if (resultsEl && searchEl && !searchEl.contains(e.target) && !resultsEl.contains(e.target)) {
            resultsEl.style.display = 'none';
        }
        // Close any open dropdown menus when clicking outside
        if (!e.target.closest('.dropdown')) {
            document.querySelectorAll('.dropdown-menu.open').forEach(m => m.classList.remove('open'));
        }
    });

    // SNKRDUNK live recalculate
    ['snk-rate', 'snk-shipping', 'snk-margin'].forEach(id => {
        document.getElementById(id)?.addEventListener('input', renderSnkrdunkTable);
    });
    document.getElementById('snk-spikes-only')?.addEventListener('change', renderSnkrdunkTable);

    // Competitor Intel filters
    document.getElementById('ci-type-filter')?.addEventListener('change', renderCiAlerts);
    document.getElementById('ci-domain-filter')?.addEventListener('change', async e => {
        ciDomain = e.target.value;
        await loadCiProducts();
    });

    // Health check
    api('/health').then(() => {
        document.querySelector('.status-dot')?.classList.add('online');
        const lbl = document.getElementById('api-status');
        if (lbl) lbl.textContent = 'Online';
    }).catch(() => {
        const lbl = document.getElementById('api-status');
        if (lbl) lbl.textContent = 'Offline';
    });

    // Initial tab from hash
    // Default date fields to today
    const today = new Date().toISOString().split('T')[0];
    ['mvat-rec-date', 'mvat-purchase-date', 'mvat-new-date'].forEach(id => {
        const el = document.getElementById(id);
        if (el && !el.value) el.value = today;
    });

    const hash = window.location.hash.slice(1);
    switchTab(hash || 'dashboard');
});


// ─────────────────────────────────────────────────────────────────────────────
// MARGIN VAT (Bruktmoms) — Purchase Order Model
// ─────────────────────────────────────────────────────────────────────────────

function mvatSwitchTab(tab) {
    document.querySelectorAll('.mvat-tab').forEach((t, i) => {
        t.classList.toggle('active', ['record','link','create'][i] === tab);
    });
    document.querySelectorAll('.mvat-tab-panel').forEach(p => p.classList.remove('active'));
    const panel = document.getElementById(`mvat-panel-${tab}`);
    if (panel) panel.classList.add('active');
}

function mvatCalc(sellingPrice, purchasePrice) {
    const margin = sellingPrice - purchasePrice;
    if (margin <= 0) return { margin: 0, vat: 0, rate: 0, bucket: 0 };
    const vat = margin * 25 / 125;
    const denom = 5 * sellingPrice - margin;
    const rate = denom > 0 ? (100 * margin / denom) : 25;
    return { margin, vat, rate, bucket: Math.min(Math.ceil(rate), 25) };
}

function renderMvatCalcBox(sellingPrice, purchasePrice) {
    const c = mvatCalc(sellingPrice, purchasePrice);
    if (c.margin <= 0) return '<span class="muted">No margin</span> — <strong>0% MVA</strong>';
    return `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:.5rem;font-size:.8125rem">
        <div>Margin<br><strong>kr ${fmtNum(c.margin)}</strong></div>
        <div>VAT<br><strong>kr ${c.vat.toFixed(2)}</strong></div>
        <div>Rate<br><strong>${c.rate.toFixed(2)}%</strong></div>
        <div>Bucket<br><strong>${c.bucket}% MVA</strong></div>
    </div>`;
}

// ── Tab Load ────────────────────────────────────────────────────────────

async function loadMarginVat() {
    showTabLoading('mvat-product-list');
    try {
        const [purchasesRes, summaryRes] = await Promise.all([
            api('/margin-vat/purchases?status=active'),
            api('/margin-vat/summary'),
        ]);
        renderMvatBucketSummary(summaryRes);
        renderMvatPurchases(purchasesRes);
        const totalItems = purchasesRes.reduce((s, p) => s + (p.items?.length || 0), 0);
        document.getElementById('mvat-count').textContent = `${purchasesRes.length} purchase(s), ${totalItems} item(s)`;
    } catch (e) {
        document.getElementById('mvat-product-list').innerHTML = `<p class="error">${e.message}</p>`;
    }
}

function renderMvatBucketSummary(summary) {
    const el = document.getElementById('mvat-bucket-summary');
    if (!summary?.length) { el.innerHTML = ''; return; }
    el.innerHTML = summary.map(b => `
        <div class="mvat-bucket-card ${b.collection_configured ? '' : 'mvat-bucket-warn'}">
            <div class="mvat-bucket-rate">${b.bucket_rate_pct}%</div>
            <div class="mvat-bucket-count">${b.product_count}</div>
        </div>`).join('');
}

// ── Purchase List ───────────────────────────────────────────────────────

function renderMvatPurchases(purchases) {
    const el = document.getElementById('mvat-product-list');
    if (!purchases?.length) {
        el.innerHTML = '<p class="muted" style="padding:1rem 1.25rem">No purchases recorded yet.</p>';
        return;
    }
    el.innerHTML = purchases.map(p => {
        const date = p.purchase_date ? new Date(p.purchase_date).toLocaleDateString('nb-NO') : '—';
        const total = p.total_nok || p.items.reduce((s, i) => s + i.quantity * i.unit_price_nok, 0);
        const proofCount = p.proof_images?.length || 0;

        const itemRows = p.items.map(it => {
            const linked = !!it.variant_shopify_id;
            const img = it.image_url ? `<img src="${it.image_url}" style="width:28px;height:28px;object-fit:cover;border-radius:3px">` : '';
            const lineTotal = it.quantity * it.unit_price_nok;
            const linkBtn = linked
                ? `<span class="badge badge-success badge-sm">${it.product_title || 'Linked'}</span>`
                : `<button class="btn btn-xs btn-primary" onclick="event.stopPropagation();mvatOpenItemLink(${it.id})">Link</button>`;
            const sellingHtml = it.selling_price_nok
                ? `<span class="mono">kr ${fmtNum(it.selling_price_nok)}</span>`
                : (linked ? '<span class="muted">—</span>' : `<input type="number" class="input-sm" style="width:80px;font-size:.75rem" placeholder="Set price" onchange="mvatSetSellingPrice(${it.id}, this.value)">`);
            const vatHtml = it.effective_rate_pct != null && it.effective_rate_pct > 0
                ? `<span class="mono">${it.effective_rate_pct.toFixed(1)}%</span> <span class="badge badge-sm badge-info">${it.bucket_rate_pct}%</span>`
                : '<span class="muted">—</span>';
            const needsSync = it.needs_reassignment ? ' <span class="badge badge-warning badge-sm">!</span>' : '';

            return `<tr>
                <td>${img}</td>
                <td>${it.description}</td>
                <td class="mono" style="text-align:center">${it.quantity}</td>
                <td class="mono" style="text-align:right">kr ${fmtNum(it.unit_price_nok)}</td>
                <td class="mono" style="text-align:right">kr ${fmtNum(lineTotal)}</td>
                <td style="text-align:right">${sellingHtml}</td>
                <td style="text-align:center">${vatHtml}${needsSync}</td>
                <td>${linkBtn}</td>
            </tr>`;
        }).join('');

        return `
            <div class="mvat-purchase-card">
                <div class="mvat-purchase-header" onclick="this.parentElement.querySelector('.mvat-purchase-body').classList.toggle('open')">
                    <div style="display:flex;gap:1rem;align-items:center;flex:1">
                        <strong>Purchase #${p.id}</strong>
                        <span class="muted">${p.seller || '—'}</span>
                        <span class="muted">${date}</span>
                        <span class="mono" style="margin-left:auto">kr ${fmtNum(total)}</span>
                        <span class="muted">${p.items.length} item${p.items.length !== 1 ? 's' : ''}</span>
                        ${proofCount ? `<span class="badge badge-info badge-sm">${proofCount} proof</span>` : ''}
                    </div>
                    <button class="btn btn-xs btn-danger" onclick="event.stopPropagation();mvatDeletePurchase(${p.id})" style="margin-left:.5rem">x</button>
                </div>
                <div class="mvat-purchase-body open">
                    <table class="data-table compact-table">
                        <thead><tr>
                            <th style="width:36px"></th><th>Item</th><th style="text-align:center">Qty</th>
                            <th style="text-align:right">Unit Price</th><th style="text-align:right">Total</th>
                            <th style="text-align:right">Selling</th><th style="text-align:center">VAT</th><th>Shopify</th>
                        </tr></thead>
                        <tbody>${itemRows}</tbody>
                    </table>
                    <div style="padding:.5rem .75rem;display:flex;gap:.5rem;align-items:center;font-size:.8125rem">
                        <input type="file" id="mvat-proof-upload-${p.id}" accept="image/*,.pdf" class="input-sm" style="font-size:.75rem;max-width:180px" />
                        <button class="btn btn-xs" onclick="mvatUploadPurchaseProof(${p.id})">Upload Proof</button>
                        ${(p.proof_images || []).map(img =>
                            img.content_type === 'application/pdf'
                                ? `<a href="/uploads/${img.file_path}" target="_blank" class="badge badge-sm badge-neutral">PDF</a>`
                                : `<a href="/uploads/${img.file_path}" target="_blank"><img src="/uploads/${img.file_path}" style="width:32px;height:32px;object-fit:cover;border-radius:3px;border:1px solid var(--border)"></a>`
                        ).join(' ')}
                    </div>
                </div>
            </div>`;
    }).join('');
}

// ── Record Purchase (multi-item) ────────────────────────────────────────

function mvatRecAddLine() {
    const tbody = document.getElementById('mvat-rec-items');
    const tr = document.createElement('tr');
    tr.innerHTML = `
        <td><input type="text" class="input-sm mvat-rec-desc" style="width:100%" placeholder="Description" /></td>
        <td><input type="number" class="input-sm mvat-rec-qty" style="width:100%" value="1" min="1" step="1" oninput="mvatRecUpdateTotals()" /></td>
        <td><input type="number" class="input-sm mvat-rec-unit" style="width:100%" min="0" step="1" placeholder="0" oninput="mvatRecUpdateTotals()" /></td>
        <td class="mono mvat-rec-line-total" style="text-align:right;font-size:.8125rem">kr 0</td>
        <td><button class="btn btn-xs btn-danger" onclick="this.closest('tr').remove();mvatRecUpdateTotals()">x</button></td>`;
    tbody.appendChild(tr);
    tr.querySelector('.mvat-rec-desc').focus();
}

function mvatRecUpdateTotals() {
    let total = 0;
    document.querySelectorAll('#mvat-rec-items tr').forEach(row => {
        const qty = parseInt(row.querySelector('.mvat-rec-qty')?.value || '1') || 1;
        const unit = parseFloat(row.querySelector('.mvat-rec-unit')?.value || '0') || 0;
        const line = qty * unit;
        total += line;
        const cell = row.querySelector('.mvat-rec-line-total');
        if (cell) cell.textContent = `kr ${fmtNum(line)}`;
    });
    document.getElementById('mvat-rec-total').textContent = `Total: kr ${fmtNum(total)}`;
}

async function mvatRecordPurchase() {
    const rows = document.querySelectorAll('#mvat-rec-items tr');
    const items = [];
    for (const row of rows) {
        const desc = row.querySelector('.mvat-rec-desc')?.value.trim();
        const qty = parseInt(row.querySelector('.mvat-rec-qty')?.value || '1') || 1;
        const unit = parseFloat(row.querySelector('.mvat-rec-unit')?.value || '0') || 0;
        if (!desc || unit <= 0) continue;
        items.push({ description: desc, quantity: qty, unit_price_nok: unit });
    }
    if (!items.length) { toast('Add at least one item', 'warning'); return; }

    const btn = document.getElementById('mvat-rec-btn');
    btn.disabled = true; btn.textContent = 'Saving...';

    try {
        const dateVal = document.getElementById('mvat-rec-date')?.value;
        const result = await api('/margin-vat/purchases', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                seller: document.getElementById('mvat-rec-seller')?.value.trim() || null,
                purchase_date: dateVal ? new Date(dateVal).toISOString() : null,
                items,
            }),
        });

        // Upload proof if selected
        const fileInput = document.getElementById('mvat-rec-proof');
        if (fileInput?.files?.length) {
            const fd = new FormData(); fd.append('file', fileInput.files[0]);
            await fetch(`${API}/margin-vat/purchases/${result.id}/proof-images`, { method: 'POST', body: fd });
        }

        toast(`Purchase #${result.id} saved — ${items.length} item(s)`, 'success');
        // Reset form
        document.getElementById('mvat-rec-items').innerHTML = `<tr>
            <td><input type="text" class="input-sm mvat-rec-desc" style="width:100%" placeholder="e.g. Pokemon 151 Booster Box" /></td>
            <td><input type="number" class="input-sm mvat-rec-qty" style="width:100%" value="1" min="1" step="1" oninput="mvatRecUpdateTotals()" /></td>
            <td><input type="number" class="input-sm mvat-rec-unit" style="width:100%" min="0" step="1" placeholder="0" oninput="mvatRecUpdateTotals()" /></td>
            <td class="mono mvat-rec-line-total" style="text-align:right;font-size:.8125rem">kr 0</td>
            <td></td></tr>`;
        ['mvat-rec-seller'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        const f = document.getElementById('mvat-rec-proof'); if (f) f.value = '';
        document.getElementById('mvat-rec-total').textContent = 'Total: kr 0';
        loadMarginVat();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    } finally {
        btn.disabled = false; btn.textContent = 'Save All Records';
    }
}

// ── Item Actions ────────────────────────────────────────────────────────

async function mvatSetSellingPrice(itemId, value) {
    const price = parseFloat(value);
    if (!price || price <= 0) return;
    try {
        await api(`/margin-vat/items/${itemId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ selling_price_nok: price }),
        });
        toast('Selling price set', 'success');
        loadMarginVat();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

let mvatLinkTimeout = null;

function mvatOpenItemLink(itemId) {
    document.querySelectorAll('.mvat-link-row').forEach(el => el.remove());
    // Find the item row and insert link UI after it
    const card = document.querySelector(`.mvat-purchase-body.open`);
    if (!card) return;
    const div = document.createElement('div');
    div.className = 'mvat-link-row';
    div.style.cssText = 'padding:.5rem .75rem;border-top:1px solid var(--border);display:flex;gap:.5rem;align-items:center';
    div.innerHTML = `
        <strong style="font-size:.8125rem;white-space:nowrap">Link to Shopify:</strong>
        <div style="position:relative;flex:1">
            <input type="text" class="input-sm" id="mvat-link-search-${itemId}" style="width:100%" placeholder="Search product..." autocomplete="off"
                oninput="mvatItemLinkSearch(${itemId}, this.value)" />
            <div id="mvat-link-results-${itemId}" class="mvat-dropdown"></div>
        </div>
        <button class="btn btn-xs" onclick="this.parentElement.remove()">Cancel</button>`;
    card.appendChild(div);
    document.getElementById(`mvat-link-search-${itemId}`)?.focus();
}

function mvatItemLinkSearch(itemId, query) {
    clearTimeout(mvatLinkTimeout);
    const el = document.getElementById(`mvat-link-results-${itemId}`);
    if (!query || query.length < 2) { el.style.display = 'none'; return; }
    mvatLinkTimeout = setTimeout(async () => {
        try {
            const products = await api(`/shopify/products?limit=15&search=${encodeURIComponent(query)}`);
            if (!products?.length) { el.innerHTML = '<div class="mvat-search-item muted">No products found</div>'; el.style.display = 'block'; return; }
            el.innerHTML = products.flatMap(p => (p.variants || []).map(v => `
                <div class="mvat-search-item" onclick="mvatLinkItem(${itemId}, '${p.shopify_id}', '${v.shopify_id}', '${p.title.replace(/'/g,"\\'")}')">
                    ${p.image_url ? `<img src="${p.image_url}" style="width:24px;height:24px;object-fit:cover;border-radius:3px">` : ''}
                    <div style="flex:1"><strong style="font-size:.8125rem">${p.title}</strong>
                    ${v.title && v.title !== 'Default Title' ? `<span class="muted"> — ${v.title}</span>` : ''}</div>
                    <span class="mono" style="font-size:.75rem">kr ${fmtNum(v.price)}</span>
                </div>`)).join('');
            el.style.display = 'block';
        } catch (e) { console.error(e); }
    }, 200);
}

async function mvatLinkItem(itemId, productShopifyId, variantShopifyId, title) {
    try {
        await api(`/margin-vat/items/${itemId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ product_shopify_id: productShopifyId, variant_shopify_id: variantShopifyId }),
        });
        toast(`Linked to "${title}"`, 'success');
        document.querySelectorAll('.mvat-link-row').forEach(el => el.remove());
        loadMarginVat();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function mvatDeletePurchase(id) {
    if (!confirm('Delete this purchase and all its items?')) return;
    try {
        await api(`/margin-vat/purchases/${id}`, { method: 'DELETE' });
        toast('Deleted', 'success');
        loadMarginVat();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

async function mvatUploadPurchaseProof(purchaseId) {
    const input = document.getElementById(`mvat-proof-upload-${purchaseId}`);
    if (!input?.files?.length) { toast('Select a file', 'warning'); return; }
    const fd = new FormData(); fd.append('file', input.files[0]);
    try {
        const res = await fetch(`${API}/margin-vat/purchases/${purchaseId}/proof-images`, { method: 'POST', body: fd });
        if (!res.ok) throw new Error(await res.text());
        toast('Proof uploaded', 'success');
        input.value = '';
        loadMarginVat();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

// ── Sync & Recalculate ──────────────────────────────────────────────────

async function mvatSyncCollections() {
    if (!confirm('Sync all items to Shopify tax collections?')) return;
    try {
        const res = await api('/margin-vat/sync-collections', { method: 'POST' });
        toast(`Added: ${res.products_added}, Removed: ${res.products_removed}, OK: ${res.products_already_correct}`, res.errors?.length ? 'warning' : 'success');
        loadMarginVat();
    } catch (e) { toast(`Sync failed: ${e.message}`, 'error'); }
}

async function mvatRecalculateAll() {
    try {
        const res = await api('/margin-vat/recalculate', { method: 'POST' });
        toast(`Recalculated ${res.updated} items (${res.bucket_changed} bucket changes)`, 'success');
        loadMarginVat();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
}

// ── Link to Shopify tab (kept from before) ──────────────────────────────

let mvatSelectedVariant = null;
let mvatSearchTimeout = null;

function mvatSearchProducts(query) {
    clearTimeout(mvatSearchTimeout);
    const el = document.getElementById('mvat-search-results');
    if (!query || query.length < 2) { el.style.display = 'none'; return; }
    mvatSearchTimeout = setTimeout(async () => {
        try {
            const products = await api(`/shopify/products?limit=20&search=${encodeURIComponent(query)}`);
            if (!products?.length) { el.innerHTML = '<div class="mvat-search-item muted">No products found</div>'; el.style.display = 'block'; return; }
            el.innerHTML = products.flatMap(p => (p.variants || []).map(v => `
                <div class="mvat-search-item" onclick='mvatSelectVariant(${JSON.stringify({
                    product_shopify_id: p.shopify_id, variant_shopify_id: v.shopify_id,
                    product_title: p.title, variant_title: v.title, sku: v.sku, price: v.price, image_url: p.image_url,
                }).replace(/'/g, "&#39;")})'>
                    ${p.image_url ? `<img src="${p.image_url}" style="width:28px;height:28px;object-fit:cover;border-radius:3px">` : ''}
                    <div style="flex:1"><strong style="font-size:.8125rem">${p.title}</strong>
                    ${v.title && v.title !== 'Default Title' ? `<span class="muted"> — ${v.title}</span>` : ''}</div>
                    <span class="mono" style="white-space:nowrap">kr ${fmtNum(v.price)}</span>
                </div>`)).join('');
            el.style.display = 'block';
        } catch (e) { console.error(e); }
    }, 300);
}

function mvatSelectVariant(data) {
    mvatSelectedVariant = data;
    document.getElementById('mvat-search-results').style.display = 'none';
    document.getElementById('mvat-product-search').value = data.product_title;
    const el = document.getElementById('mvat-selected-product');
    el.style.display = 'block';
    el.innerHTML = `<div style="display:flex;align-items:center;gap:.5rem">
        ${data.image_url ? `<img src="${data.image_url}" style="width:36px;height:36px;object-fit:cover;border-radius:4px">` : ''}
        <div style="flex:1"><strong>${data.product_title}</strong>
        ${data.variant_title && data.variant_title !== 'Default Title' ? `<span class="muted"> — ${data.variant_title}</span>` : ''}
        <br><span class="mono">kr ${fmtNum(data.price)}</span></div>
        <button class="btn btn-xs" onclick="mvatClearSelection()">&times;</button>
    </div>`;
    document.getElementById('mvat-register-btn').disabled = false;
    mvatCalculatePreview();
}

function mvatClearSelection() {
    mvatSelectedVariant = null;
    document.getElementById('mvat-product-search').value = '';
    document.getElementById('mvat-selected-product').style.display = 'none';
    document.getElementById('mvat-calc-preview').style.display = 'none';
    document.getElementById('mvat-register-btn').disabled = true;
}

function mvatCalculatePreview() {
    const el = document.getElementById('mvat-calc-preview');
    const pp = parseFloat(document.getElementById('mvat-purchase-price')?.value || '0');
    if (!mvatSelectedVariant || !pp || pp <= 0) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    el.innerHTML = renderMvatCalcBox(mvatSelectedVariant.price, pp);
}

async function mvatRegisterProduct() {
    if (!mvatSelectedVariant) { toast('Select a product', 'warning'); return; }
    const pp = parseFloat(document.getElementById('mvat-purchase-price')?.value || '0');
    if (!pp || pp <= 0) { toast('Enter purchase price', 'warning'); return; }
    const btn = document.getElementById('mvat-register-btn');
    btn.disabled = true; btn.textContent = 'Saving...';
    try {
        const dateVal = document.getElementById('mvat-purchase-date')?.value;
        const result = await api('/margin-vat/purchases', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                seller: document.getElementById('mvat-seller-desc')?.value.trim() || null,
                purchase_date: dateVal ? new Date(dateVal).toISOString() : null,
                items: [{ description: mvatSelectedVariant.product_title, quantity: 1, unit_price_nok: pp }],
            }),
        });
        // Link the item to Shopify product
        if (result.items?.length) {
            await api(`/margin-vat/items/${result.items[0].id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_shopify_id: mvatSelectedVariant.product_shopify_id, variant_shopify_id: mvatSelectedVariant.variant_shopify_id }),
            });
        }
        // Upload proof
        const fileInput = document.getElementById('mvat-proof-file');
        if (fileInput?.files?.length) {
            const fd = new FormData(); fd.append('file', fileInput.files[0]);
            await fetch(`${API}/margin-vat/purchases/${result.id}/proof-images`, { method: 'POST', body: fd });
        }
        toast('Registered', 'success');
        mvatClearSelection();
        ['mvat-purchase-price','mvat-purchase-date','mvat-seller-desc'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        const f = document.getElementById('mvat-proof-file'); if (f) f.value = '';
        loadMarginVat();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
    finally { btn.disabled = false; btn.textContent = 'Register Purchase'; }
}

// ── Create New Product tab (kept) ───────────────────────────────────────

let mvatTemplateTimeout = null;
let mvatTemplateImages = [];

function mvatTemplateSearch(query) {
    clearTimeout(mvatTemplateTimeout);
    const el = document.getElementById('mvat-template-results');
    if (!query || query.length < 2) { el.style.display = 'none'; return; }
    mvatTemplateTimeout = setTimeout(async () => {
        try {
            const products = await api(`/shopify/products?limit=15&search=${encodeURIComponent(query)}`);
            if (!products?.length) { el.innerHTML = '<div class="mvat-search-item muted">No products found</div>'; el.style.display = 'block'; return; }
            el.innerHTML = products.map(p => `
                <div class="mvat-search-item" onclick="mvatLoadTemplate('${p.shopify_id}')">
                    ${p.image_url ? `<img src="${p.image_url}" style="width:28px;height:28px;object-fit:cover;border-radius:3px">` : ''}
                    <div style="flex:1"><strong style="font-size:.8125rem">${p.title}</strong></div>
                    <span class="mono" style="font-size:.75rem">kr ${fmtNum(p.variants?.[0]?.price || 0)}</span>
                </div>`).join('');
            el.style.display = 'block';
        } catch (e) { console.error(e); }
    }, 300);
}

async function mvatLoadTemplate(shopifyId) {
    document.getElementById('mvat-template-results').style.display = 'none';
    document.getElementById('mvat-template-loading').style.display = 'block';
    try {
        const p = await api(`/margin-vat/product-detail?shopify_id=${encodeURIComponent(shopifyId)}`);
        document.getElementById('mvat-new-title').value = p.title || '';
        document.getElementById('mvat-new-desc').value = p.description || '';
        document.getElementById('mvat-new-vendor').value = p.vendor || '';
        document.getElementById('mvat-new-type').value = p.product_type || '';
        document.getElementById('mvat-new-tags').value = (p.tags || []).join(', ');
        const v = p.variants?.[0];
        if (v) { document.getElementById('mvat-new-price').value = v.price || ''; document.getElementById('mvat-new-sku').value = v.sku || ''; }
        mvatTemplateImages = [...(p.images || [])];
        mvatRenderTemplateImages();
        document.getElementById('mvat-template-search').value = `Copied: ${p.title}`;
        mvatNewCalcPreview();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); document.getElementById('mvat-template-search').value = ''; }
    finally { document.getElementById('mvat-template-loading').style.display = 'none'; }
}

function mvatRenderTemplateImages() {
    const section = document.getElementById('mvat-new-images-section');
    const el = document.getElementById('mvat-new-images');
    if (!mvatTemplateImages.length) { section.style.display = 'none'; return; }
    section.style.display = 'block';
    el.innerHTML = mvatTemplateImages.map((url, i) => `
        <div class="mvat-proof-item" style="position:relative">
            <img src="${url}" class="mvat-proof-thumb" style="width:56px;height:56px">
            <button class="btn btn-xs btn-danger" style="position:absolute;top:2px;right:2px;padding:0 3px;font-size:.65rem" onclick="mvatTemplateImages.splice(${i},1);mvatRenderTemplateImages()">&times;</button>
        </div>`).join('');
}

function mvatNewCalcPreview() {
    const el = document.getElementById('mvat-new-calc-preview');
    const sp = parseFloat(document.getElementById('mvat-new-price')?.value || '0');
    const pp = parseFloat(document.getElementById('mvat-new-purchase')?.value || '0');
    if (!sp || !pp || sp <= 0 || pp <= 0) { el.style.display = 'none'; return; }
    el.style.display = 'block';
    el.innerHTML = renderMvatCalcBox(sp, pp);
}

async function mvatCreateNewProduct() {
    const title = document.getElementById('mvat-new-title')?.value.trim();
    const price = parseFloat(document.getElementById('mvat-new-price')?.value || '0');
    const pp = parseFloat(document.getElementById('mvat-new-purchase')?.value || '0');
    if (!title) { toast('Enter a title', 'warning'); return; }
    if (!price || price <= 0) { toast('Enter selling price', 'warning'); return; }
    if (!pp || pp <= 0) { toast('Enter purchase price', 'warning'); return; }
    const btn = document.getElementById('mvat-create-btn');
    btn.disabled = true; btn.textContent = 'Creating...';
    try {
        const productData = { title, price,
            sku: document.getElementById('mvat-new-sku')?.value.trim() || null,
            description: document.getElementById('mvat-new-desc')?.value.trim() || null,
            vendor: document.getElementById('mvat-new-vendor')?.value.trim() || null,
            product_type: document.getElementById('mvat-new-type')?.value.trim() || null,
            tags: document.getElementById('mvat-new-tags')?.value.trim() || null,
        };
        if (mvatTemplateImages.length) productData.images = mvatTemplateImages;
        const shopifyResult = await api('/margin-vat/create-product', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(productData) });
        const variantId = shopifyResult.variants?.[0]?.id;
        if (!variantId) throw new Error('No variant returned');
        const dateVal = document.getElementById('mvat-new-date')?.value;
        const purchaseResult = await api('/margin-vat/purchases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
            seller: document.getElementById('mvat-new-seller')?.value.trim() || null,
            purchase_date: dateVal ? new Date(dateVal).toISOString() : null,
            items: [{ description: title, quantity: 1, unit_price_nok: pp }],
        })});
        if (purchaseResult.items?.length) {
            await api(`/margin-vat/items/${purchaseResult.items[0].id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ product_shopify_id: shopifyResult.product_shopify_id, variant_shopify_id: variantId })});
        }
        const fileInput = document.getElementById('mvat-new-proof');
        if (fileInput?.files?.length) {
            const fd = new FormData(); fd.append('file', fileInput.files[0]);
            await fetch(`${API}/margin-vat/purchases/${purchaseResult.id}/proof-images`, { method: 'POST', body: fd });
        }
        const numericId = shopifyResult.product_shopify_id.replace('gid://shopify/Product/', '');
        const shop = await api('/settings/dict?mask_sensitive=false').then(d => d.shopify_shop).catch(() => null);
        const adminUrl = shop ? `https://${shop}/admin/products/${numericId}` : null;
        toast(`Draft created`, 'success');
        document.getElementById('mvat-new-calc-preview').style.display = 'block';
        document.getElementById('mvat-new-calc-preview').innerHTML = `<div style="font-size:.8125rem"><strong>Draft created!</strong> ${adminUrl ? `<a href="${adminUrl}" target="_blank">${adminUrl}</a>` : `ID: ${numericId}`}</div>`;
        ['mvat-new-title','mvat-new-price','mvat-new-purchase','mvat-new-sku','mvat-new-date','mvat-new-seller','mvat-new-desc','mvat-new-vendor','mvat-new-type','mvat-new-tags','mvat-template-search'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        const f = document.getElementById('mvat-new-proof'); if (f) f.value = '';
        mvatTemplateImages = []; document.getElementById('mvat-new-images-section').style.display = 'none';
        loadMarginVat();
    } catch (e) { toast(`Failed: ${e.message}`, 'error'); }
    finally { btn.disabled = false; btn.textContent = 'Create Draft & Register'; }
}

// ── MVA Collection Settings ─────────────────────────────────────────────

async function loadMvaCollectionSettings() {
    const grid = document.getElementById('mva-collection-grid');
    if (!grid) return;

    // Render inputs immediately so they're visible
    function renderGrid(dict) {
        let html = '';
        for (let i = 0; i <= 24; i++) {
            const key = `mva_collection_${i}`;
            const val = (dict && dict[key]) || '';
            html += `
                <div style="display:flex;align-items:center;gap:.25rem">
                    <span style="font-size:.8125rem;min-width:42px;font-weight:600">${i}%</span>
                    <input type="text" class="input-sm mva-coll-input" data-bucket="${i}"
                        value="${val}" placeholder="Collection ID" style="width:100%;font-family:monospace;font-size:.75rem" />
                </div>
            `;
        }
        grid.innerHTML = html;
    }

    // Show empty grid first
    renderGrid({});

    // Then fill in saved values
    try {
        const dict = await api('/settings/dict?mask_sensitive=false');
        renderGrid(dict);
    } catch (_) { /* keep empty grid */ }
}

async function saveMvaCollections() {
    const inputs = document.querySelectorAll('.mva-coll-input');
    let saved = 0;
    let errors = 0;

    for (const input of inputs) {
        const bucket = input.dataset.bucket;
        const value = input.value.trim();
        const key = `mva_collection_${bucket}`;

        try {
            await api('/settings/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    key,
                    value,
                    description: `Shopify collection ID for ${bucket}% MVA tax override`,
                    is_sensitive: false,
                }),
            });
            saved++;
        } catch (_) {
            // Try PUT if POST fails (key already exists)
            try {
                await api(`/settings/${key}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ value }),
                });
                saved++;
            } catch (e) {
                errors++;
                console.error(`Failed to save ${key}:`, e);
            }
        }
    }

    toast(`Saved ${saved} MVA collection IDs${errors ? ` (${errors} errors)` : ''}`, errors ? 'warning' : 'success');
}
