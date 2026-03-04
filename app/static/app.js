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
let productSearchQuery  = '';
let productStockFilter  = 'all';
let selectedProductId   = null;
let hiddenProductIds    = new Set(JSON.parse(localStorage.getItem('hiddenProducts') || '[]'));

// Link-modal state
let linkModalProductId  = null;
let _linkSearchTimer    = null;
let _linkStaged         = [];  // [{id, domain, title, price, inStock, url}, ...]
let _linkSearchResults  = [];  // cached last search results
let _linkSortPrice      = null; // null = default, 'asc' = low→high, 'desc' = high→low

// Purchase Orders state
let poLineItems = [];
let poSearchTimer = null;

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
    else if (tab === 'settings')        loadSettings();
}

// ─────────────────────────────────────────────────────────────────────────────
// DASHBOARD
// ─────────────────────────────────────────────────────────────────────────────
async function loadDashboard() {
    showTabLoading('dash-attention');
    showTabLoading('dash-alerts');

    const [prodRes, alertsRes, snkRes, matchRes] = await Promise.allSettled([
        api('/shopify/products?limit=500'),
        api('/marketintel/alerts?limit=50'),
        api('/snkrdunk/products'),
        api('/marketintel/matched-products?limit=200'),
    ]);

    shopifyProducts = prodRes.status === 'fulfilled'
        ? (prodRes.value.products || prodRes.value || []) : [];
    miAlerts = alertsRes.status === 'fulfilled' ? alertsRes.value : [];
    snkrdunkItems = snkRes.status === 'fulfilled' ? (snkRes.value.items || []) : [];
    matchedProducts = matchRes.status === 'fulfilled' ? matchRes.value : [];

    const variants     = flatVariants(shopifyProducts);
    const outOfStock   = variants.filter(v => v.inventory_quantity <= 0);
    const lowStock     = variants.filter(v => v.inventory_quantity > 0 && v.inventory_quantity <= 10);
    const unreadAlerts = miAlerts.filter(a => !a.read_at).length;
    const overpriced   = matchedProducts.filter(m => {
        const own  = m.own_product?.price;
        const comp = m.competitor_product?.price;
        return own && comp && ((own - comp) / comp) > 0.10;
    });

    // Stat cards
    document.getElementById('stat-products').textContent    = shopifyProducts.length || 0;
    document.getElementById('stat-out-of-stock').textContent = outOfStock.length;
    document.getElementById('stat-price-alerts').textContent = overpriced.length;
    document.getElementById('stat-mi-alerts').textContent    = unreadAlerts;

    // Needs attention list
    const attn = document.getElementById('dash-attention');
    const items = [
        ...outOfStock.slice(0, 10).map(v =>
            `<li class="attention-item attention-danger">
                <span class="attention-label">OUT OF STOCK</span>
                <span>${v.productTitle} — ${v.title}</span>
            </li>`
        ),
        ...lowStock.slice(0, 5).map(v =>
            `<li class="attention-item attention-warning">
                <span class="attention-label">LOW (${v.inventory_quantity})</span>
                <span>${v.productTitle} — ${v.title}</span>
            </li>`
        ),
        ...overpriced.slice(0, 5).map(m => {
            const pct = (((m.own_product.price - m.competitor_product.price) / m.competitor_product.price) * 100).toFixed(1);
            return `<li class="attention-item attention-warning">
                <span class="attention-label">OVERPRICED +${pct}%</span>
                <span>${m.own_product.title} vs ${m.competitor_product.competitor_domain}</span>
            </li>`;
        }),
    ];
    attn.innerHTML = items.length
        ? `<ul class="attention-list">${items.join('')}</ul>`
        : '<p class="muted">Nothing needs attention right now.</p>';

    // Recent competitor alerts
    const alertsEl = document.getElementById('dash-alerts');
    if (miAlerts.length === 0) {
        alertsEl.innerHTML = '<p class="muted">No recent competitor alerts.</p>';
    } else {
        alertsEl.innerHTML = miAlerts.slice(0, 15).map(a => `
            <div class="alert-row alert-row-${a.severity}">
                <div class="alert-row-meta">
                    ${severityBadge(a.severity)}
                    <span class="alert-type">${a.type.replace(/_/g, ' ')}</span>
                    <span class="muted">${fmtDate(a.created_at)}</span>
                </div>
                <div class="alert-row-body">
                    <strong>${a.payload?.product_title || '—'}</strong>
                    ${a.payload?.competitor_domain ? `<span class="muted"> · ${a.payload.competitor_domain}</span>` : ''}
                    ${a.type === 'price_change'
                        ? `<span class="muted"> · ${fmtNok(a.payload?.previous_price)} → ${fmtNok(a.payload?.current_price)} (${a.payload?.change_pct?.toFixed(1)}%)</span>`
                        : ''}
                    ${a.type === 'new_product'
                        ? `<span class="muted"> · ${fmtNok(a.payload?.current_price)}</span>`
                        : ''}
                </div>
            </div>
        `).join('');
    }
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
        const res  = await api('/snkrdunk/products');
        snkrdunkItems = res.items || [];
        const logs = await api('/snkrdunk/scan-logs?limit=10');
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
        if (btn) { btn.disabled = false; btn.textContent = 'Refresh SNKRDUNK Data'; }
    }
}

function renderSnkrdunkTable() {
    const rate     = parseFloat(document.getElementById('snk-rate')?.value     || '0.063');
    const shipping = parseFloat(document.getElementById('snk-shipping')?.value  || '500');
    const margin   = parseFloat(document.getElementById('snk-margin')?.value    || '20') / 100;
    const VAT      = 0.25;

    const prevMap = {};
    for (const p of snkrdunkPrevItems) prevMap[p.id] = p.minPrice || p.minPriceJpy;

    const SPIKE = 0.10;
    const rows = snkrdunkItems.map(item => {
        const jpy          = item.minPrice || item.minPriceJpy;
        const nokCost      = (jpy + shipping) * rate;
        const nokRec       = Math.ceil((nokCost / (1 - margin)) * (1 + VAT) / 25) * 25;
        const prev         = prevMap[item.id];
        const spike        = prev && Math.abs((jpy - prev) / prev) >= SPIKE;
        const spikePct     = prev ? (((jpy - prev) / prev) * 100).toFixed(1) : null;
        return { item, jpy, nokRec, spike, spikePct };
    });

    const spikeOnly = document.getElementById('snk-spikes-only')?.checked;
    const filtered  = spikeOnly ? rows.filter(r => r.spike) : rows;

    document.getElementById('snkrdunk-table-wrap').innerHTML = `
        <table class="data-table">
            <thead><tr>
                <th>Product</th>
                <th>Min JPY</th>
                <th>Rec. NOK</th>
                <th>Spike</th>
            </tr></thead>
            <tbody>
                ${filtered.length === 0
                    ? '<tr><td colspan="4" class="text-center muted">No items.</td></tr>'
                    : filtered.map(({ item, jpy, nokRec, spike, spikePct }) => `
                        <tr class="${spike ? 'row-spike' : ''}">
                            <td>${item.nameEn || item.name || item.id}</td>
                            <td class="mono">¥${fmt(jpy)}</td>
                            <td class="mono">${fmtNok(nokRec)}</td>
                            <td>${spike
                                ? `<span class="badge ${Number(spikePct) > 0 ? 'badge-danger' : 'badge-info'}">${Number(spikePct) > 0 ? '▲' : '▼'} ${Math.abs(spikePct)}%</span>`
                                : '<span class="muted">—</span>'}</td>
                        </tr>`
                    ).join('')}
            </tbody>
        </table>`;
}

function renderSnkrdunkLogs(logs) {
    const el = document.getElementById('snkrdunk-logs');
    if (!el) return;
    if (!logs?.length) { el.innerHTML = '<p class="muted">No scan logs yet.</p>'; return; }
    el.innerHTML = `
        <table class="data-table">
            <thead><tr><th>Date</th><th>Status</th><th>Items</th><th>Duration</th></tr></thead>
            <tbody>
                ${logs.map(l => `<tr>
                    <td>${fmtDate(l.created_at)}</td>
                    <td>${l.status === 'success'
                        ? '<span class="badge badge-success">OK</span>'
                        : '<span class="badge badge-danger">Failed</span>'}</td>
                    <td>${l.total_items ?? '—'}</td>
                    <td class="mono">${l.duration_seconds ? l.duration_seconds.toFixed(1) + 's' : '—'}</td>
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
    el.innerHTML = plans.map(p => `
        <div class="plan-card">
            <div class="plan-card-header">
                <span class="plan-id">#${p.id}</span>
                <span class="muted">${p.plan_type || 'standard'}</span>
                <span class="badge ${p.status === 'pending' ? 'badge-warning' : p.status === 'applied' ? 'badge-success' : 'badge-neutral'}">${p.status}</span>
                <span class="muted">${fmtDate(p.created_at)}</span>
                <span class="muted">${p.item_count || 0} items</span>
                <div style="margin-left:auto;display:flex;gap:.5rem">
                    ${p.status === 'pending'
                        ? `<button class="btn btn-primary btn-sm" onclick="applyPlan(${p.id})">Apply</button>`
                        : ''}
                    <button class="btn btn-sm" onclick="viewPlan(${p.id})">Details</button>
                </div>
            </div>
        </div>`).join('');
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
        toast(`Plan #${planId} applied — ${res.applied_count || 0} prices updated`, 'success');
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
        body.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1rem">
                <h3 style="margin:0">Price Plan #${plan.id}
                    <span class="badge ${plan.status === 'pending' ? 'badge-warning' : 'badge-success'}">${plan.status}</span>
                </h3>
                ${plan.status === 'pending'
                    ? `<button class="btn btn-primary" onclick="applyPlan(${plan.id}); closeModal()">Apply Plan</button>`
                    : ''}
            </div>
            <p class="muted">${fmtDate(plan.created_at)} · ${plan.item_count || plan.items?.length || 0} items · ${plan.plan_type || 'standard'}</p>
            <table class="data-table">
                <thead><tr><th>Product</th><th>Variant</th><th>Current</th><th>New Price</th><th>Change</th></tr></thead>
                <tbody>
                    ${(plan.items || []).map(i => {
                        const delta = (i.new_price - i.current_price);
                        const sign  = delta >= 0 ? '+' : '';
                        return `<tr>
                            <td>${i.product_title || '—'}</td>
                            <td class="muted">${i.variant_title || ''}</td>
                            <td class="mono">${fmtNok(i.current_price)}</td>
                            <td class="mono"><strong>${fmtNok(i.new_price)}</strong></td>
                            <td class="mono ${delta > 0 ? 'text-danger' : 'text-success'}">${sign}${fmtNok(delta)}</td>
                        </tr>`;
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
// SETTINGS
// ─────────────────────────────────────────────────────────────────────────────
async function loadSettings() {
    showTabLoading('settings-list');
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

async function syncShopify() {
    const btn = document.getElementById('btn-sync-shopify');
    if (btn) btn.disabled = true;
    try {
        await api('/shopify/fetch-collection', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: '{}',
        });
        toast('Shopify sync complete', 'success');
    } catch (e) {
        toast(`Sync failed: ${e.message}`, 'error');
    } finally {
        if (btn) btn.disabled = false;
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
            const candidates = await api(`/marketintel/competitor-products?search=${encodeURIComponent(p.title)}&limit=50`);
            const good = candidates.filter(c => {
                if (c.price == null) return false;
                // Exclude Korean editions
                const tl = (c.title || '').toLowerCase();
                if (tl.includes('koreansk') || tl.includes('korean')) return false;
                // Price: 40%–200% of ours (filters out single packs and wildly different items)
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

async function loadProducts() {
    showTabLoading('products-list');
    try {
        const [prodRes, linksRes, mappingsRes, snkRes] = await Promise.allSettled([
            api('/shopify/products?limit=500'),
            api('/competitor-links'),
            api('/mappings/snkrdunk?limit=500'),
            api('/snkrdunk/products'),
        ]);

        shopifyProducts  = prodRes.status      === 'fulfilled' ? (prodRes.value.products || prodRes.value || []) : [];
        const allLinks   = linksRes.status     === 'fulfilled' ? linksRes.value   : [];
        snkrdunkMappings = mappingsRes.status  === 'fulfilled' ? mappingsRes.value : [];
        snkrdunkItems    = snkRes.status       === 'fulfilled' ? (snkRes.value.items || []) : [];

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

function _filterProducts() {
    const q   = productSearchQuery.trim().toLowerCase();
    const stf = productStockFilter;
    let products = shopifyProducts;

    // Hidden filter
    if (stf === 'hidden') {
        products = products.filter(p => hiddenProductIds.has(p.shopify_id));
    } else {
        products = products.filter(p => !hiddenProductIds.has(p.shopify_id));
        if (stf === 'out') products = products.filter(p =>
            (p.variants || []).some(v => v.inventory_quantity <= 0));
        else if (stf === 'low') products = products.filter(p =>
            (p.variants || []).some(v => v.inventory_quantity > 0 && v.inventory_quantity <= 10));
    }

    if (q) products = products.filter(p =>
        p.title.toLowerCase().includes(q) ||
        (p.variants || []).some(v => (v.sku || '').toLowerCase().includes(q))
    );
    return products;
}

function hideProduct(shopifyId) {
    hiddenProductIds.add(shopifyId);
    localStorage.setItem('hiddenProducts', JSON.stringify([...hiddenProductIds]));
    if (selectedProductId === shopifyId) selectedProductId = null;
    renderProducts();
}

function unhideProduct(shopifyId) {
    hiddenProductIds.delete(shopifyId);
    localStorage.setItem('hiddenProducts', JSON.stringify([...hiddenProductIds]));
    renderProducts();
}

function renderProducts() {
    const products = _filterProducts();
    const el = document.getElementById('products-list');
    document.getElementById('products-count').textContent = `${products.length} products`;

    if (!products.length) {
        el.innerHTML = '<p class="muted" style="padding:2rem">No products match the filter.</p>';
        return;
    }

    // Build split panel on first render only
    if (!document.getElementById('prod-list-panel')) {
        el.innerHTML = `
        <div class="prod-layout">
            <div class="prod-list-panel" id="prod-list-panel"></div>
            <div class="prod-detail-panel" id="prod-detail-panel">
                <div class="prod-no-selection">← Select a product</div>
            </div>
        </div>`;
    }

    const listPanel = document.getElementById('prod-list-panel');
    listPanel.innerHTML = products.map(p => renderProductListItem(p)).join('');

    // Select first product if nothing selected, or restore selection
    const toSelect = (selectedProductId && shopifyProducts.find(p => p.shopify_id === selectedProductId))
        ? selectedProductId
        : products[0]?.shopify_id;
    if (toSelect) selectProduct(toSelect);
}

// ── Product list item (left panel) ───────────────────────────────────────────

function renderProductListItem(p) {
    const variants   = p.variants || [];
    const links      = productCompLinks[p.shopify_id] || [];
    const snkMapped  = !!snkrdunkMappings.find(m => m.product_shopify_id === p.shopify_id && !m.disabled);

    // Use box variants only (consistent with detail panel)
    const boxV = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const dispV = boxV.length ? boxV : variants;

    const totalStock = dispV.reduce((s, v) => s + (v.inventory_quantity ?? 0), 0);
    const minStock   = dispV.length ? Math.min(...dispV.map(v => v.inventory_quantity ?? 0)) : 0;
    const boxPrice   = dispV[0]?.price;
    const priceLabel = boxPrice ? fmtNok(boxPrice) : '';

    const stockStatus = minStock <= 0 ? 'out' : minStock <= 5 ? 'critical' : minStock <= 10 ? 'low' : 'ok';
    const stockLabel  = minStock <= 0 ? 'OOS'
        : minStock <= 5  ? `${totalStock} · Low!`
        : minStock <= 10 ? `${totalStock} · Low`
        : String(totalStock);

    // Are we cheapest among in-stock competitors?
    const inStockPrices = links.filter(l => l.mi_in_stock === true && l.mi_price != null).map(l => l.mi_price);
    const isCheapest = boxPrice && inStockPrices.length && boxPrice <= Math.min(...inStockPrices);

    const isSelected = p.shopify_id === selectedProductId;

    return `
    <div class="pli-row pli-${stockStatus}${isSelected ? ' selected' : ''}"
         data-id="${p.shopify_id}" onclick="selectProduct('${p.shopify_id}')">
        <div class="pli-body">
            <span class="pli-name">${p.title}</span>
            <span class="pli-price">${priceLabel}</span>
        </div>
        <div class="pli-meta">
            <span class="pli-stock pli-stock-${stockStatus}">${stockLabel}</span>
            ${isCheapest ? '<span class="pli-dot pli-dot-cheapest" title="Our price is the lowest in-stock">★</span>' : ''}
            ${snkMapped ? '<span class="pli-dot pli-dot-snk">S</span>' : ''}
            ${links.length ? `<span class="pli-dot pli-dot-comp">${links.length}</span>` : ''}
        </div>
    </div>`;
}

// ── Product detail panel (right panel) ───────────────────────────────────────

function renderProductDetail(p) {
    if (!p) return '<div class="prod-no-selection">← Select a product</div>';

    const variants   = p.variants || [];
    const links      = productCompLinks[p.shopify_id] || [];
    const mapping    = snkrdunkMappings.find(m => m.product_shopify_id === p.shopify_id && !m.disabled);
    const snkItem    = mapping ? snkrdunkItems.find(i => String(i.id) === String(mapping.snkrdunk_key)) : null;
    const snkJpy     = snkItem ? (snkItem.minPrice || snkItem.minPriceJpy) : null;
    const snkRec     = snkJpy  ? calcSnkrdunkRec(snkJpy) : null;
    const isHidden   = hiddenProductIds.has(p.shopify_id);

    // Only show box variants; fall back to all if none
    const boxVariants    = variants.filter(v => (v.option_value || v.title || '').toLowerCase().includes('box'));
    const displayVariants = boxVariants.length ? boxVariants : variants;
    const refVariant      = displayVariants[0];

    // Left panel — compact info rows per box variant
    const boxCards = displayVariants.map(v => {
        const qty = v.inventory_quantity ?? 0;
        const sc  = qty <= 0 ? 'pdd-qty-zero' : qty <= 10 ? 'pdd-qty-low' : 'pdd-qty-ok';
        return `
        <div class="pdd-box-card">
            <div class="pdd-info-row">
                <span class="pdd-info-label">Type</span>
                <span class="pdd-info-value">${v.title || 'Booster Box'}</span>
            </div>
            <div class="pdd-info-row">
                <span class="pdd-info-label">Our price</span>
                <span class="pdd-info-value mono">${fmtNok(v.price)}</span>
            </div>
            <div class="pdd-info-row">
                <span class="pdd-info-label">Stock</span>
                <input type="number" class="qty-input ${sc}" value="${qty}" min="0" step="1"
                       data-orig="${qty}" title="Click to edit stock"
                       onkeydown="if(event.key==='Enter'){this.blur()}"
                       onblur="setInventory(${v.id},this.value,this)">
            </div>
            ${snkJpy ? `
            <div class="pdd-info-row pdd-info-divider">
                <span class="pdd-info-label">SNKRDUNK</span>
                <span class="pdd-info-value mono">¥${fmt(snkJpy)}</span>
            </div>
            <div class="pdd-info-row">
                <span class="pdd-info-label">SNK RRP</span>
                <span class="pdd-info-value mono pdd-info-snk">${fmtNok(snkRec)}</span>
            </div>` : ''}
        </div>`;
    }).join('');

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
            return `
            <div class="pdd-comp-row${isCheapest ? ' pdd-comp-cheapest' : ''}">
                <span class="pdd-comp-domain">${lnk.mi_domain || '—'}</span>
                <span class="pdd-comp-title">${lnk.mi_title || '—'}</span>
                <span class="pdd-comp-price">${fmtNok(lnk.mi_price)}</span>
                ${isCheapest ? '<span class="pdd-best-badge">Best</span>' : ''}
                <span class="pdd-stock-dot ${inStock ? 'pdd-stock-in' : oos ? 'pdd-stock-oos' : 'pdd-stock-unknown'}"
                      title="${inStock ? 'In stock' : oos ? 'Out of stock' : 'Unknown'}"></span>
                ${delta}
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
            ${weCheapest ? '<span class="pdd-cheapest-pill" title="Our price is the lowest among in-stock competitors">★ Lowest price</span>' : ''}
        </div>
        <div class="pdd-header-actions">
            ${isHidden
                ? `<button class="btn btn-xs btn-warning" onclick="unhideProduct('${p.shopify_id}')">Unhide</button>`
                : `<button class="btn btn-xs" onclick="hideProduct('${p.shopify_id}')" title="Hide from list">Hide</button>`}
            <button class="btn btn-xs btn-refresh" onclick="refreshSingleProduct('${p.shopify_id}')">↻ Refresh</button>
        </div>
    </div>
    <div class="pdd-body">
        <div class="pdd-left">
            ${boxCards}
        </div>
        <div class="pdd-right">
            <div class="pdd-section-head">
                <span class="pdd-label">Competitors</span>
                <button class="btn btn-xs btn-primary" onclick="openLinkModal('${p.shopify_id}','${esc(p.title)}')">+ Link</button>
            </div>
            <div class="pdd-comp-list">${compRows}</div>
        </div>
    </div>`;
}

function selectProduct(shopifyId) {
    selectedProductId = shopifyId;
    document.querySelectorAll('.pli-row').forEach(el => {
        el.classList.toggle('selected', el.dataset.id === shopifyId);
    });
    const panel   = document.getElementById('prod-detail-panel');
    const product = shopifyProducts.find(p => p.shopify_id === shopifyId);
    if (panel) panel.innerHTML = renderProductDetail(product);
}

function _refreshSelectedProduct() {
    if (!selectedProductId) return;
    const product  = shopifyProducts.find(p => p.shopify_id === selectedProductId);
    const listItem = document.querySelector(`.pli-row[data-id="${selectedProductId}"]`);
    if (listItem && product) {
        const tmp = document.createElement('div');
        tmp.innerHTML = renderProductListItem(product);
        const newItem = tmp.firstElementChild;
        listItem.replaceWith(newItem);
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
    _linkSortPrice = null;
    const sortBtn = document.getElementById('link-sort-btn');
    if (sortBtn) { sortBtn.textContent = 'Price ↕'; sortBtn.classList.remove('btn-primary'); }
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
            _linkSearchResults = await api(`/marketintel/competitor-products?search=${encodeURIComponent(q)}&limit=50`);
            renderLinkResults();
        } catch (e) {
            el.innerHTML = `<p class="error" style="padding:1rem">Search failed: ${e.message}</p>`;
        }
    }, 300);
}

function renderLinkResults() {
    const el = document.getElementById('link-search-results');
    if (!el) return;
    if (!_linkSearchResults.length) {
        el.innerHTML = '<p class="muted" style="padding:1.25rem;text-align:center">No matches found.</p>';
        return;
    }
    let results = _linkSearchResults;
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
                strategy:   'match_competition',
                plan_type:  'price_update',
                items: [{
                    product_shopify_id: productShopifyId,
                    variant_shopify_id: variantShopifyId,
                    current_price:      currentPrice,
                    new_price:          newPrice,
                    current_title:      `${productTitle} — ${variantTitle}`,
                }],
            }),
        });
        toast(`Price plan #${plan.id} created — go to Price Plans to review & apply`, 'success');
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
    const shopifyUrl = sid => storeName ? `https://admin.shopify.com/store/${storeName}/products/${sid}` : null;
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
            </div>`);
    } catch (e) {
        toast(`Failed to load PO: ${e.message}`, 'error');
    }
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
document.addEventListener('DOMContentLoaded', () => {
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

    // Products tab — search + stock filter
    document.getElementById('product-search')?.addEventListener('input', e => {
        productSearchQuery = e.target.value;
        renderProducts();
    });
    document.getElementById('product-stock-filter')?.addEventListener('change', e => {
        productStockFilter = e.target.value;
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
    const hash = window.location.hash.slice(1);
    switchTab(hash || 'dashboard');
});
