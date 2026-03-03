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

// Link-modal state
let linkModalProductId  = null;
let _linkSearchTimer    = null;
let _linkStaged         = [];  // [{id, domain, title, price, inStock, url}, ...]

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

function deltaBadge(ownPrice, compPrice) {
    if (!ownPrice || !compPrice) return '<span class="badge badge-neutral">—</span>';
    const pct = ((ownPrice - compPrice) / compPrice) * 100;
    const sign = pct > 0 ? '+' : '';
    if (pct > 10)  return `<span class="badge badge-danger">${sign}${pct.toFixed(1)}%</span>`;
    if (pct > 3)   return `<span class="badge badge-warning">${sign}${pct.toFixed(1)}%</span>`;
    if (pct < -5)  return `<span class="badge badge-info">${sign}${pct.toFixed(1)}%</span>`;
    return `<span class="badge badge-success">${sign}${pct.toFixed(1)}%</span>`;
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

function renderProducts() {
    const q   = productSearchQuery.trim().toLowerCase();
    const stf = productStockFilter;

    let products = shopifyProducts;

    if (q) {
        products = products.filter(p =>
            p.title.toLowerCase().includes(q) ||
            (p.variants || []).some(v => (v.sku || '').toLowerCase().includes(q))
        );
    }

    if (stf !== 'all') {
        products = products.filter(p => {
            const variants = p.variants || [];
            if (stf === 'out')  return variants.some(v => v.inventory_quantity <= 0);
            if (stf === 'low')  return variants.some(v => v.inventory_quantity > 0 && v.inventory_quantity <= 10);
            return true;
        });
    }

    const el = document.getElementById('products-list');
    document.getElementById('products-count').textContent = `${products.length} products`;

    if (!products.length) {
        el.innerHTML = '<p class="muted" style="padding:2rem">No products match the filter.</p>';
        return;
    }

    el.innerHTML = products.map(p => renderProductCard(p)).join('');
}

function renderProductCard(p) {
    const variants = p.variants || [];
    const links    = productCompLinks[p.shopify_id] || [];
    const idSafe   = p.shopify_id.replace(/\W/g, '_');

    // SNKRDUNK
    const mapping = snkrdunkMappings.find(m => m.product_shopify_id === p.shopify_id && !m.disabled);
    const snkItem = mapping ? snkrdunkItems.find(i => String(i.id) === String(mapping.snkrdunk_key)) : null;
    const snkJpy  = snkItem ? (snkItem.minPrice || snkItem.minPriceJpy) : null;
    const snkRec  = snkJpy  ? calcSnkrdunkRec(snkJpy) : null;

    // Stock badge
    const minStock = variants.length ? Math.min(...variants.map(v => v.inventory_quantity ?? 0)) : 0;
    const stockBadge = minStock <= 0
        ? '<span class="badge badge-danger">Out of stock</span>'
        : minStock <= 5
            ? '<span class="badge badge-danger">Critical</span>'
            : minStock <= 10
                ? '<span class="badge badge-warning">Low stock</span>'
                : '<span class="badge badge-success">In stock</span>';

    // Variant rows
    const variantRows = variants.map(v => `
        <tr class="${stockClass(v.inventory_quantity)}">
            <td>${v.title || 'Default'}</td>
            <td class="mono text-muted">${v.sku || '—'}</td>
            <td class="mono">${fmtNok(v.price)}</td>
            <td class="text-center mono pc-stock-qty ${v.inventory_quantity <= 0 ? 'pc-stock-zero' : v.inventory_quantity <= 10 ? 'pc-stock-low' : ''}">${v.inventory_quantity}</td>
        </tr>`).join('');

    // SNKRDUNK section
    const snkSection = snkItem
        ? `<div class="pc-snk-box">
            <div class="pc-snk-header">
                <span class="pc-snk-label">SNKRDUNK</span>
                <span class="pc-snk-name">${snkItem.nameEn || snkItem.name || ''}</span>
            </div>
            <div class="pc-snk-body">
                <div class="pc-snk-prices">
                    <span class="pc-snk-jpy mono">¥${fmt(snkJpy)}</span>
                    <span class="pc-snk-arrow">→</span>
                    <span class="pc-snk-nok mono">Rec. ${fmtNok(snkRec)}</span>
                </div>
                <div class="pc-snk-actions">
                    ${variants
                        .filter(v => (v.option_value || v.title || '').toLowerCase().includes('box') || variants.length === 1)
                        .map(v => `<button class="btn btn-sm btn-primary"
                            onclick="matchPriceSnkrdunk('${p.shopify_id}','${v.shopify_id}',${snkRec},'${esc(p.title)}','${esc(v.title || 'Default')}',${v.price})">
                            Set ${fmtNok(snkRec)}${variants.length > 1 ? ' · ' + (v.title || 'Default') : ''}
                        </button>`).join('')}
                </div>
            </div>
           </div>`
        : `<div class="pc-snk-box pc-snk-empty">
            <span class="pc-snk-label">SNKRDUNK</span>
            <span class="pc-snk-unmapped">Not mapped — <a href="#snkrdunk" onclick="switchTab('snkrdunk')">set up in SNKRDUNK tab</a></span>
           </div>`;

    // Competitor rows
    const refVariant = variants.find(v => (v.option_value || v.title || '').toLowerCase().includes('box')) || variants[0];
    const compRows = links.length
        ? links.map(lnk => `
            <div class="pc-comp-row">
                <div class="pc-comp-left">
                    <span class="pc-comp-domain">${lnk.mi_domain || '—'}</span>
                    <span class="pc-comp-title">${lnk.mi_title || '—'}</span>
                </div>
                <div class="pc-comp-right">
                    <span class="pc-comp-price mono">${fmtNok(lnk.mi_price)}</span>
                    ${lnk.mi_in_stock === true  ? '<span class="badge badge-success">In stock</span>'
                    : lnk.mi_in_stock === false ? '<span class="badge badge-danger">OOS</span>' : ''}
                    ${refVariant && lnk.mi_price != null ? deltaBadge(refVariant.price, lnk.mi_price) : ''}
                    ${lnk.mi_source_url ? `<a href="${lnk.mi_source_url}" target="_blank" class="btn btn-xs">↗</a>` : ''}
                    ${refVariant && lnk.mi_price != null
                        ? `<button class="btn btn-xs btn-primary"
                            onclick="matchPriceComp('${p.shopify_id}','${refVariant.shopify_id}',${lnk.mi_price},'${esc(p.title)}','${esc(refVariant.title || 'Default')}',${refVariant.price},'${esc(lnk.mi_domain)}')">
                            Match</button>`
                        : ''}
                    <button class="btn btn-xs btn-danger" onclick="unlinkCompetitor(${lnk.id})" title="Remove">×</button>
                </div>
            </div>`).join('')
        : '<div class="pc-comp-empty">No competitors linked yet. Click + Link to add one.</div>';

    // Header summary (visible when collapsed)
    const totalStock = variants.reduce((s, v) => s + (v.inventory_quantity ?? 0), 0);
    const prices = variants.map(v => v.price).filter(Boolean);
    const priceLabel = prices.length > 1
        ? `${fmtNok(Math.min(...prices))} – ${fmtNok(Math.max(...prices))}`
        : prices.length ? fmtNok(prices[0]) : '';
    const compSummary = links.length
        ? links.map(l => `${l.mi_domain}${l.mi_price != null ? ' ' + fmtNok(l.mi_price) : ''}`).join(' · ')
        : '';

    return `
    <div class="product-card" id="pcard-${idSafe}">
        <div class="product-card-header" onclick="toggleProductCard('${idSafe}')">
            <div class="product-card-title">
                <span class="pc-name">${p.title}</span>
                <span class="pc-meta">${priceLabel}${totalStock > 0 ? ' · ' + totalStock + ' pcs' : ''}</span>
            </div>
            <div class="pc-header-right">
                ${stockBadge}
                ${snkItem ? '<span class="pc-snk-dot" title="SNKRDUNK mapped">SNK</span>' : ''}
                ${links.length ? `<span class="pc-comp-dot" title="${compSummary}">${links.length} comp</span>` : ''}
                <svg class="pc-chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="transform:rotate(-90deg)"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
        </div>
        <div class="product-card-body" id="pbody-${idSafe}" style="display:none">

            <!-- Variants table -->
            <div class="pc-section">
                <table class="data-table compact-table">
                    <thead><tr><th>Variant</th><th>SKU</th><th>Price</th><th class="text-center">Stock</th></tr></thead>
                    <tbody>${variantRows}</tbody>
                </table>
            </div>

            <!-- SNKRDUNK -->
            ${snkSection}

            <!-- Competitors -->
            <div class="pc-section">
                <div class="pc-section-header">
                    <span class="pc-section-title">Competitors</span>
                    <div class="pc-section-actions">
                        <button class="btn btn-xs" onclick="event.stopPropagation();refreshSingleProduct('${p.shopify_id}')">↻ Refresh</button>
                        <button class="btn btn-xs btn-primary" onclick="event.stopPropagation();openLinkModal('${p.shopify_id}','${esc(p.title)}')">+ Link</button>
                    </div>
                </div>
                <div class="pc-comp-list" id="comp-links-${idSafe}">${compRows}</div>
            </div>

        </div>
    </div>`;
}

function esc(str) {
    return String(str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

function toggleProductCard(idSafe) {
    const body    = document.getElementById(`pbody-${idSafe}`);
    const chevron = document.querySelector(`#pcard-${idSafe} .pc-chevron`);
    if (!body) return;
    const open = body.style.display !== 'none';
    body.style.display = open ? 'none' : '';
    if (chevron) chevron.style.transform = open ? 'rotate(-90deg)' : '';
}

// ── Competitor linking ────────────────────────────────────────────────────────

function openLinkModal(shopifyProductId, productTitle) {
    linkModalProductId = shopifyProductId;
    _linkStaged = [];
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

    // Update card in-place — keep modal open
    const pid  = linkModalProductId;
    const safe = pid.replace(/\W/g, '_');
    const product = shopifyProducts.find(p => p.shopify_id === pid);
    if (product) {
        const card = document.getElementById(`pcard-${safe}`);
        if (card) {
            const wasOpen = document.getElementById(`pbody-${safe}`)?.style.display !== 'none';
            card.outerHTML = renderProductCard(product);
            if (wasOpen) {
                const body    = document.getElementById(`pbody-${safe}`);
                const chevron = document.querySelector(`#pcard-${safe} .pc-chevron`);
                if (body)    body.style.display = '';
                if (chevron) chevron.style.transform = '';
            }
        }
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
            const results = await api(`/marketintel/competitor-products?search=${encodeURIComponent(q)}&limit=50`);
            if (!results.length) {
                el.innerHTML = '<p class="muted" style="padding:1.25rem;text-align:center">No matches found.</p>';
                return;
            }
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
        } catch (e) {
            el.innerHTML = `<p class="error" style="padding:1rem">Search failed: ${e.message}</p>`;
        }
    }, 300);
}

async function unlinkCompetitor(linkId) {
    if (!confirm('Remove this competitor link?')) return;
    try {
        await api(`/competitor-links/${linkId}`, { method: 'DELETE' });
        // Remove from local cache
        for (const pid of Object.keys(productCompLinks)) {
            productCompLinks[pid] = productCompLinks[pid].filter(l => l.id !== linkId);
        }
        toast('Link removed', 'success');
        renderProducts();
    } catch (e) {
        toast(`Failed: ${e.message}`, 'error');
    }
}

async function refreshSingleProduct(shopifyProductId) {
    // Fetch all competitor products for domains linked to this product
    const links = productCompLinks[shopifyProductId] || [];
    if (!links.length) { toast('No competitors linked.', 'info'); return; }

    try {
        const res = await api('/competitor-links/refresh-prices', { method: 'POST' });
        toast(`Refreshed ${res.updated} competitor prices`, 'success');
        // Reload links
        const allLinks = await api('/competitor-links');
        productCompLinks = {};
        for (const lnk of allLinks) (productCompLinks[lnk.shopify_product_id] ||= []).push(lnk);
        renderProducts();
    } catch (e) {
        toast(`Refresh failed: ${e.message}`, 'error');
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
