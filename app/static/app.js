// API Base URL
const API_BASE = '/api/v1';

// Global state
let currentTab = 'dashboard';
let refreshInterval = null;

// Sorting state for competitor table
let competitorSortColumn = null;
let competitorSortDirection = 'asc'; // 'asc' or 'desc'
let competitorSortedData = [];

// Helper function to ensure table body exists with proper headers
function ensureTableBody(tableId, headers, className = 'data-table') {
    let table = document.getElementById(tableId);
    if (!table) {
        // Create table if it doesn't exist
        const container = document.querySelector(`#${tableId}`);
        if (!container) return null;
        
        table = document.createElement('table');
        table.id = tableId;
        table.className = className;
        
        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);
        
        const tbody = document.createElement('tbody');
        table.appendChild(tbody);
        
        container.innerHTML = '';
        container.appendChild(table);
    }
    
    return table.querySelector('tbody');
}

function setTableBodyMessage(tbody, colSpan, message, isError = false) {
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="${colSpan}" class="text-center" style="color: ${isError ? 'red' : '#666'};">${message}</td></tr>`;
}

// Helper function to show loading state
function showLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el) {
        // For table containers, find tbody and show loading there
        const tbody = el.querySelector('tbody');
        if (tbody) {
            tbody.innerHTML = '<tr><td colspan="10" class="text-center">Loading...</td></tr>';
        } else {
            // For other containers, show in the container itself
            el.innerHTML = '<div class="text-center" style="padding: 20px;">Loading...</div>';
        }
    }
}

function hideLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el) {
        // For table containers, find tbody and clear it
        const tbody = el.querySelector('tbody');
        if (tbody) {
            tbody.innerHTML = '';
        } else {
            el.innerHTML = '';
        }
    }
}

function showError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) {
        el.innerHTML = `<tr><td colspan="10" class="text-center" style="color: red;">${message}</td></tr>`;
    }
}

// Helper function to wait for element
function waitForElement(selector, timeout = 5000) {
    return new Promise((resolve, reject) => {
        const startTime = Date.now();
        
        const checkElement = () => {
            const element = document.querySelector(selector);
            if (element) {
                resolve(element);
            } else if (Date.now() - startTime > timeout) {
                reject(new Error(`Timeout waiting for ${selector}`));
            } else {
                requestAnimationFrame(checkElement);
            }
        };
        
        checkElement();
    });
}

// Toggle variant-specific fields based on selection
function toggleVariantFields() {
    const variantType = document.getElementById('plan-variant-type')?.value;
    const boxFields = document.getElementById('box-fields');
    const packFields = document.getElementById('pack-fields');
    
    if (boxFields && packFields) {
        if (variantType === 'pack') {
            boxFields.style.display = 'none';
            packFields.style.display = 'grid';
        } else {
            boxFields.style.display = 'grid';
            packFields.style.display = 'none';
        }
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    try {
        console.log('DOMContentLoaded fired');
        
        initializeTabs();
        console.log('Tabs initialized');
        
        // Check if there's a tab in the URL hash
        const hash = window.location.hash.substring(1); // Remove the '#'
        if (hash && hash !== '') {
            switchTab(hash);
            // Clear the hash after switching
            window.history.replaceState(null, null, '');
        } else {
            loadDashboard();
        }
        console.log('Dashboard loaded');
        
        checkHealth();
        console.log('Health checked');
        
        // Refresh health status every 30 seconds
        setInterval(checkHealth, 30000);
        console.log('Health check interval set');
    } catch (error) {
        console.error('FATAL ERROR during page initialization:', error);
        console.error('Stack:', error.stack);
    }
});

// Tab Management
const DYNAMIC_TABS = new Set([
    'booster-variants',
    'booster-inventory',
    'mappings',
    'reports',
    'competitors',
    'competitor-mappings',
    'settings'
]);

function getTabContentId(tabName) {
    return DYNAMIC_TABS.has(tabName) ? 'dynamic-tab' : `${tabName}-tab`;
}

function initializeTabs() {
    const tabs = document.querySelectorAll('.nav-item');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => switchTab(tab.dataset.tab));
    });
}

function switchTab(tabName) {
    currentTab = tabName;
    
    // Update tab buttons
    document.querySelectorAll('.nav-item').forEach(tab => {
        const shouldBeActive = tab.dataset.tab === tabName;
        tab.classList.toggle('active', shouldBeActive);
        // no-op
    });
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        const expectedId = getTabContentId(tabName);
        const shouldBeActive = content.id === expectedId;
        content.classList.toggle('active', shouldBeActive);
        content.classList.toggle('is-hidden', !shouldBeActive);
    });
    
    // Wait for DOM to update before loading data
    requestAnimationFrame(() => {
        setTimeout(() => {
            loadTabData(tabName);
        }, 50);
    });
}

function loadTabData(tabName) {
    switch(tabName) {
        case 'dashboard': 
            loadDashboard(); 
            break;
        case 'products':
            setTimeout(() => {
                fetch('/api/v1/shopify/products?collection_id=444175384827&template_suffix=pokemon-jp-bb&skip=0&limit=100').then(r => r.json()).then(products => {
                    const tbody = document.querySelector('#products-table tbody');
                    if (tbody) {
                        // Filter out Deluxe products
                        const filteredProducts = products.filter(p => !p.title || !p.title.toLowerCase().includes('deluxe'));
                        
                        tbody.innerHTML = '';
                        if (!filteredProducts || filteredProducts.length === 0) {
                            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No products found. Sync a collection first.</td></tr>';
                        } else {
                            filteredProducts.forEach(product => {
                                const row = document.createElement('tr');
                                const status = (product.status || 'unknown').toLowerCase();
                                row.innerHTML = `
                                    <td>${product.title || '-'}</td>
                                    <td>${product.handle || '-'}</td>
                                    <td><span class="badge badge-${status === 'active' ? 'success' : 'gray'}">${product.status || 'unknown'}</span></td>
                                    <td>${product.variants?.length || 0}</td>
                                    <td>${product.collection_id || '-'}</td>
                                    <td>
                                        <button class="btn btn-sm btn-secondary" onclick="viewProduct(${product.id})">View</button>
                                    </td>
                                `;
                                tbody.appendChild(row);
                            });
                        }
                    }
                }).catch(error => {
                    console.error('Error loading products:', error);
                    const tbody = document.querySelector('#products-table tbody');
                    if (tbody) {
                        tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="color: var(--danger);">Failed to load products</td></tr>';
                    }
                });
            }, 100);
            break;
        case 'price-plans': 
            setTimeout(() => {
                loadPricePlans();
            }, 100);
            break;
        case 'booster-variants': 
            setTimeout(() => {
                renderDynamicTab('booster-variants');
                loadBoosterVariantPlans();
            }, 100); 
            break;
        case 'booster-inventory': 
            setTimeout(() => {
                renderDynamicTab('booster-inventory');
                loadBoosterInventoryPlans();
            }, 100); 
            break;
        case 'mappings': 
            setTimeout(async () => {
                try {
                    renderDynamicTab('mappings');
                    // Load SNKRDUNK products, Shopify products, and existing mappings
                    let snkrdunkData = await fetch('/api/v1/snkrdunk/products').then(r => r.json());
                    
                    // If cache is empty, automatically fetch from SNKRDUNK
                    if (!snkrdunkData.items || snkrdunkData.items.length === 0) {
                        console.log('SNKRDUNK cache empty, fetching from API...');
                        showAlert('No cached SNKRDUNK products. Fetching from API...', 'info');
                        
                        try {
                            const fetchResult = await fetch('/api/v1/snkrdunk/fetch', {
                                method: 'POST',
                                headers: {'Content-Type': 'application/json'},
                                body: JSON.stringify({pages: 10, force_refresh: true})
                            }).then(r => r.json());
                            
                            console.log('Fetch result:', fetchResult);
                            
                            // Reload products after fetching
                            snkrdunkData = await fetch('/api/v1/snkrdunk/products').then(r => r.json());
                            showAlert(`Fetched and cached ${fetchResult.total_cached || fetchResult.total_items} SNKRDUNK products`, 'success');
                        } catch (fetchError) {
                            console.error('Error auto-fetching SNKRDUNK data:', fetchError);
                            showAlert('Could not auto-fetch SNKRDUNK data. Click "Fetch from SNKRDUNK" button manually.', 'warning');
                        }
                    }
                    
                    const [shopifyProducts, existingMappings] = await Promise.all([
                        fetch('/api/v1/shopify/products?collection_id=444175384827&template_suffix=pokemon-jp-bb&limit=100').then(r => r.json()),
                        fetch('/api/v1/mappings/snkrdunk').then(r => r.json())
                    ]);
                    
                    // Filter out Deluxe products from Shopify
                    const filteredShopify = shopifyProducts.filter(p => !p.title || !p.title.toLowerCase().includes('deluxe'));
                    
                    // Store globally for mapping functions
                    window.snkrdunkProducts = snkrdunkData.items || [];
                    window.shopifyProducts = filteredShopify;
                    
                    console.log('Loaded SNKRDUNK products:', window.snkrdunkProducts.length);
                    console.log('Loaded Shopify products:', window.shopifyProducts.length);
                    
                    // Initialize mappings object and populate with existing mappings
                    window.productMappings = {};
                    if (existingMappings && existingMappings.length > 0) {
                        existingMappings.forEach(mapping => {
                            // Find the Shopify product by shopify_id
                            const shopifyProduct = window.shopifyProducts.find(
                                p => p.shopify_id === mapping.product_shopify_id
                            );
                            if (shopifyProduct) {
                                // Map snkrdunk_key to our internal product ID
                                window.productMappings[mapping.snkrdunk_key] = shopifyProduct.id;
                            }
                        });
                    }
                    
                    // Render SNKRDUNK products table using the standard function
                    renderSnkrdunkProductsTable();
                    
                    // Load available history dates for date picker
                    loadAvailableHistoryDates();
                } catch (error) {
                    console.error('Error loading mappings data:', error);
                    showAlert('Error loading mappings: ' + error.message, 'error');
                }
            }, 100);
            break;
        case 'reports': 
            setTimeout(() => {
                renderDynamicTab('reports');
                loadReports();
            }, 100); 
            break;
        case 'settings': 
            setTimeout(() => {
                renderDynamicTab('settings');
                loadSettings();
            }, 100); 
            break;
        case 'competitors': 
            setTimeout(() => {
                renderDynamicTab('competitors');
                loadCompetitors();
            }, 100); 
            break;
        case 'competitor-mappings':
            setTimeout(() => {
                renderDynamicTab('competitor-mappings');
                loadCompetitorMappings();
            }, 100);
            break;
        case 'price-monitoring':
            setTimeout(() => {
                loadPriceMonitoring();
            }, 100);
            break;
    }
}

// Health Check
async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE}/health`);
        const data = await response.json();
        
        const statusEl = document.getElementById('api-status');
        const dotEl = document.querySelector('.status-dot');
        
        if (data.status === 'healthy') {
            statusEl.textContent = 'Healthy';
            dotEl.style.background = 'var(--success)';
        } else {
            statusEl.textContent = 'Degraded';
            dotEl.style.background = 'var(--warning)';
        }
    } catch (error) {
        document.getElementById('api-status').textContent = 'Offline';
        document.querySelector('.status-dot').style.background = 'var(--danger)';
    }
}

// Utility: Format time ago
function timeAgo(date) {
    if (!date) return 'Never';
    const now = new Date();
    const then = new Date(date);
    const seconds = Math.floor((now - then) / 1000);
    
    if (seconds < 60) return 'Just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`;
    return then.toLocaleDateString('no-NO');
}

// Dashboard
async function loadDashboard() {
    try {
        const [stats, config, syncStatus, priceHistory] = await Promise.all([
            fetch(`${API_BASE}/reports/statistics`).then(r => {
                if (!r.ok) throw new Error(`Statistics endpoint returned ${r.status}`);
                return r.json();
            }),
            fetch(`${API_BASE}/config`).then(r => {
                if (!r.ok) throw new Error(`Config endpoint returned ${r.status}`);
                return r.json();
            }),
            fetch(`${API_BASE}/competitors/sync-status`).then(r => {
                if (!r.ok) throw new Error(`Sync status endpoint returned ${r.status}`);
                return r.json();
            }),
            fetch(`${API_BASE}/shopify/price-change-history?limit=10`).then(r => {
                if (!r.ok) return { logs: [] };
                return r.json();
            }).catch(() => ({ logs: [] }))
        ]);
        
        console.log('Dashboard data loaded:', {stats, config, syncStatus, priceHistory});
        
        // Safely set stat values
        const setStat = (id, value) => {
            const el = document.getElementById(id);
            if (el) el.textContent = value || 0;
        };
        
        setStat('stat-products', stats.total_products);
        setStat('stat-active-products', stats.active_products || stats.total_products);
        setStat('stat-variants', stats.total_variants);
        setStat('stat-snkrdunk-mappings', stats.total_snkrdunk_mappings);
        setStat('stat-competitor-products', syncStatus.total_competitor_products);
        setStat('stat-mapped-competitors', stats.mapped_competitors);
        setStat('stat-pending-plans', stats.pending_price_plans);
        setStat('stat-applied-plans', stats.applied_price_plans || 0);
        
        // Set config
        const configShopEl = document.getElementById('config-shop');
        if (configShopEl) configShopEl.textContent = config.shopify_shop || 'Not configured';
        
        const configCollEl = document.getElementById('config-collection');
        if (configCollEl) configCollEl.textContent = config.default_collection_id || '—';
        
        // Update sync status cards
        const updateSyncCard = (id, timestamp, status = null) => {
            const el = document.getElementById(id);
            if (el) {
                if (timestamp) {
                    const date = new Date(timestamp);
                    const ago = timeAgo(timestamp);
                    el.innerHTML = `
                        <div style="font-size: 1.1rem; font-weight: 600; color: #22c55e;">${ago}</div>
                        <div style="font-size: 0.75rem; color: #666; margin-top: 0.25rem;">${date.toLocaleString('no-NO')}</div>
                        ${status ? `<div style="font-size: 0.75rem; color: #666; margin-top: 0.25rem;">${status}</div>` : ''}
                    `;
                } else {
                    el.innerHTML = '<div style="font-size: 1.1rem; font-weight: 600; color: #999;">Never</div>';
                }
            }
        };
        
        updateSyncCard('last-scrape-card', syncStatus.last_competitor_scrape, syncStatus.last_scrape_status);
        updateSyncCard('last-snkrdunk-card', stats.last_snkrdunk_fetch);
        updateSyncCard('last-plan-card', stats.last_price_plan_applied);
        
        // Load recent price changes
        const recentChangesEl = document.getElementById('recent-price-changes');
        if (recentChangesEl && priceHistory && priceHistory.logs && priceHistory.logs.length > 0) {
            recentChangesEl.innerHTML = priceHistory.logs.slice(0, 5).map(change => {
                const changeTypeLabels = {
                    'manual_competitor_match': 'Match Competitor',
                    'manual_in_stock_match': 'Match In Stock',
                    'price_plan': 'Price Plan',
                    'manual_update': 'Manual Update'
                };
                const changeType = changeTypeLabels[change.change_type] || change.change_type;
                const priceChange = change.new_price - change.old_price;
                const priceColor = priceChange > 0 ? '#ef4444' : priceChange < 0 ? '#22c55e' : '#666';
                const priceSymbol = priceChange > 0 ? '+' : '';
                
                return `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; border-bottom: 1px solid #e5e7eb;">
                        <div style="flex: 1;">
                            <div style="font-weight: 500; font-size: 0.9rem; color: #111; margin-bottom: 0.25rem;">${change.product_title || 'Unknown Product'}</div>
                            <div style="font-size: 0.75rem; color: #666;">${changeType}${change.competitor_name ? ` • ${change.competitor_name}` : ''}</div>
                            <div style="font-size: 0.7rem; color: #999; margin-top: 0.15rem;">${timeAgo(change.changed_at)}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size: 0.75rem; color: #999; text-decoration: line-through;">${change.old_price.toFixed(2)} kr</div>
                            <div style="font-size: 0.95rem; font-weight: 600; color: #22c55e; margin-top: 0.15rem;">${change.new_price.toFixed(2)} kr</div>
                            <div style="font-size: 0.75rem; color: ${priceColor}; margin-top: 0.15rem;">${priceSymbol}${priceChange.toFixed(2)} kr</div>
                        </div>
                    </div>
                `;
            }).join('');
        } else if (recentChangesEl) {
            recentChangesEl.innerHTML = '<div style="padding: 2rem; text-align: center; color: #999;">No recent price changes</div>';
        }
        
    } catch (error) {
        console.error('Dashboard error:', error);
        showAlert('Failed to load dashboard data: ' + error.message, 'error');
    }
}

async function triggerCompetitorScrape() {
    const btn = document.getElementById('scrape-btn');
    const originalText = btn.textContent;
    
    btn.disabled = true;
    btn.textContent = '⏳ Scraping...';
    
    try {
        const response = await fetch(`${API_BASE}/scrape/competitors`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.message || 'Scraping failed');
        }
        
        const result = await response.json();
        showAlert('✓ Competitor scraping started!', 'success');
        
        // Reload dashboard to show updated data
        await loadDashboard();
        
    } catch (error) {
        console.error('Scrape error:', error);
        showAlert(`❌ Scraping failed: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

// Price Monitoring
async function loadPriceMonitoring() {
    // Setup tab switching
    document.querySelectorAll('.price-monitor-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.monitorTab;
            
            // Update button styles
            document.querySelectorAll('.price-monitor-tab-btn').forEach(b => {
                b.style.borderBottom = '3px solid transparent';
                b.style.color = '#666';
            });
            btn.style.borderBottom = '3px solid #2563eb';
            btn.style.color = '#2563eb';
            
            // Show/hide views
            document.getElementById('my-changes-view').style.display = targetTab === 'my-changes' ? 'block' : 'none';
            document.getElementById('competitor-changes-view').style.display = targetTab === 'competitor-changes' ? 'block' : 'none';
            
            // Load appropriate data
            if (targetTab === 'my-changes') {
                loadMyPriceChanges();
            }
        });
    });
    
    // Setup filter for my changes
    document.getElementById('my-changes-filter').addEventListener('change', loadMyPriceChanges);
    
    // Load initial data
    await loadMyPriceChanges();
}

async function loadMyPriceChanges() {
    const changeTypeFilter = document.getElementById('my-changes-filter').value;
    const tbody = document.getElementById('my-changes-tbody');
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 2rem; color: #999;">Loading...</td></tr>';
    
    try {
        let url = `${API_BASE}/shopify/price-change-history?limit=500`;
        if (changeTypeFilter) {
            url += `&change_type=${changeTypeFilter}`;
        }
        
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch price changes');
        
        const data = await response.json();
        const logs = data.logs || [];
        
        // Calculate statistics
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        let totalChanges = logs.length;
        let priceDecreases = 0;
        let priceIncreases = 0;
        let todayChanges = 0;
        
        logs.forEach(log => {
            const changeDate = new Date(log.created_at);
            changeDate.setHours(0, 0, 0, 0);
            
            if (changeDate.getTime() === today.getTime()) {
                todayChanges++;
            }
            
            const priceDelta = log.new_price - log.old_price;
            if (priceDelta < 0) priceDecreases++;
            if (priceDelta > 0) priceIncreases++;
        });
        
        // Update statistics
        document.getElementById('total-my-changes').textContent = totalChanges;
        document.getElementById('total-price-decreases').textContent = priceDecreases;
        document.getElementById('total-price-increases').textContent = priceIncreases;
        document.getElementById('today-changes').textContent = todayChanges;
        
        // Render table
        if (logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 2rem; color: #999;">No price changes found</td></tr>';
            return;
        }
        
        tbody.innerHTML = logs.map(log => {
            const changeTypeLabels = {
                'manual_competitor_match': 'Competitor Match',
                'manual_in_stock_match': 'In Stock Match',
                'price_plan': 'Price Plan',
                'manual_update': 'Manual Update'
            };
            const changeType = changeTypeLabels[log.change_type] || log.change_type;
            
            const priceDelta = log.new_price - log.old_price;
            const priceColor = priceDelta > 0 ? '#ef4444' : priceDelta < 0 ? '#22c55e' : '#666';
            const priceSymbol = priceDelta > 0 ? '+' : '';
            
            return `
                <tr>
                    <td style="font-weight: 500;">${log.product_title || '-'}</td>
                    <td>${log.variant_title || 'Default'}</td>
                    <td style="color: #999; text-decoration: line-through;">${log.old_price.toFixed(2)} kr</td>
                    <td style="font-weight: 600; color: #22c55e;">${log.new_price.toFixed(2)} kr</td>
                    <td style="color: ${priceColor}; font-weight: 600;">${priceSymbol}${priceDelta.toFixed(2)} kr (${priceSymbol}${((priceDelta / log.old_price) * 100).toFixed(1)}%)</td>
                    <td><span class="badge" style="background: #dbeafe; color: #1e40af; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">${changeType}</span></td>
                    <td>${log.competitor_name || '-'}</td>
                    <td style="font-size: 0.85rem; color: #666;">${timeAgo(log.created_at)}</td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Error loading price changes:', error);
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: #ef4444;">Error: ${error.message}</td></tr>`;
    }
}

async function loadCompetitorPriceChanges() {
    const competitorFilter = document.getElementById('competitor-filter').value;
    const changeTypeFilter = document.getElementById('change-type-filter').value;
    const daysBack = parseInt(document.getElementById('days-back-filter').value);
    const tbody = document.getElementById('competitor-changes-tbody');
    
    tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 2rem; color: #999;">Loading competitor changes...</td></tr>';
    
    try {
        // Fetch competitor daily snapshots
        let url = `${API_BASE}/competitors/price-changes?days_back=${daysBack}`;
        if (competitorFilter) url += `&competitor=${competitorFilter}`;
        if (changeTypeFilter) url += `&change_type=${changeTypeFilter}`;
        
        const response = await fetch(url);
        
        if (!response.ok) {
            throw new Error('Failed to fetch competitor changes');
        }
        
        const changes = await response.json();
        
        if (!changes || changes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; padding: 2rem; color: #999;">No competitor changes detected in the selected period</td></tr>';
            return;
        }
        
        tbody.innerHTML = changes.map(change => {
            // Determine what changed
            const changeTypes = [];
            if (change.price_changed) changeTypes.push('💰 Price');
            if (change.stock_changed) changeTypes.push('📦 Stock');
            const changeTypeLabel = changeTypes.join(' + ');
            
            // Price change info
            let priceInfo = '';
            let deltaInfo = '';
            if (change.price_changed) {
                const priceDelta = change.current_price - change.previous_price;
                const priceColor = priceDelta > 0 ? '#ef4444' : priceDelta < 0 ? '#22c55e' : '#666';
                const priceSymbol = priceDelta > 0 ? '+' : '';
                const percentChange = change.previous_price > 0 ? ((priceDelta / change.previous_price) * 100).toFixed(1) : 0;
                
                priceInfo = `
                    <div><span style="color: #999; text-decoration: line-through;">${change.previous_price.toFixed(2)} kr</span></div>
                    <div style="font-weight: 600;">${change.current_price.toFixed(2)} kr</div>
                `;
                
                deltaInfo += `<div style="color: ${priceColor}; font-weight: 600;">${priceSymbol}${priceDelta.toFixed(2)} kr (${priceSymbol}${percentChange}%)</div>`;
            } else {
                priceInfo = `<div>${change.current_price.toFixed(2)} kr</div>`;
            }
            
            // Stock change info
            let stockInfo = '';
            if (change.stock_changed) {
                const stockDelta = change.current_stock_amount - change.previous_stock_amount;
                const stockColor = stockDelta > 0 ? '#22c55e' : stockDelta < 0 ? '#ef4444' : '#666';
                const stockSymbol = stockDelta > 0 ? '+' : '';
                
                stockInfo = `
                    <div><span style="color: #999; text-decoration: line-through;">${change.previous_stock_status} [${change.previous_stock_amount}]</span></div>
                    <div style="font-weight: 600;">${change.current_stock_status} [${change.current_stock_amount}]</div>
                `;
                
                if (stockDelta !== 0) {
                    deltaInfo += `<div style="color: ${stockColor}; font-weight: 600; margin-top: 0.25rem;">${stockSymbol}${stockDelta} units</div>`;
                }
                
                // Status change indicator
                if (change.previous_stock_status !== change.current_stock_status) {
                    const statusColor = change.in_stock ? '#22c55e' : '#ef4444';
                    deltaInfo += `<div style="color: ${statusColor}; font-size: 0.75rem; margin-top: 0.25rem;">${change.in_stock ? '✓ Back in stock' : '✗ Out of stock'}</div>`;
                }
            } else {
                stockInfo = `<div>${change.current_stock_status} [${change.current_stock_amount}]</div>`;
            }
            
            // Highlight significant changes
            const isSignificant = (change.price_changed && Math.abs((change.current_price - change.previous_price) / change.previous_price) > 0.1) ||
                                 (change.stock_changed && !change.in_stock && change.previous_stock_amount > 0);
            const rowStyle = isSignificant ? 'background: #fef3c7;' : '';
            
            return `
                <tr style="${rowStyle}">
                    <td style="font-weight: 500;">${change.product_name || '-'}</td>
                    <td><span class="badge" style="background: #f3f4f6; color: #374151; padding: 0.25rem 0.5rem; border-radius: 4px; font-size: 0.75rem;">${change.competitor_name}</span></td>
                    <td style="font-size: 0.85rem;">${changeTypeLabel}</td>
                    <td style="font-size: 0.9rem;">${priceInfo}</td>
                    <td style="font-size: 0.9rem;">${stockInfo}</td>
                    <td style="font-size: 0.85rem;">${deltaInfo || '-'}</td>
                    <td><span class="badge badge-${change.in_stock ? 'success' : 'gray'}">${change.in_stock ? 'In Stock' : 'Out of Stock'}</span></td>
                    <td style="font-size: 0.85rem; color: #666;">${timeAgo(change.changed_at)}</td>
                </tr>
            `;
        }).join('');
        
    } catch (error) {
        console.error('Error loading competitor changes:', error);
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; padding: 2rem; color: #ef4444;">Error: ${error.message}</td></tr>`;
    }
}

// Products
async function loadProducts(page = 0, limit = 50) {
    showLoading('products-table');
    
    try {
        const response = await fetch(`${API_BASE}/shopify/products?skip=${page * limit}&limit=${limit}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const products = await response.json();
        
        renderProductsTable(products);
        hideLoading('products-table');
    } catch (error) {
        console.error('Error loading products:', error);
        showError('products-table', 'Failed to load products: ' + error.message);
    }
}

function renderProductsTable(products) {
    const tbody = document.querySelector('#products-table tbody');
    
    if (!tbody) {
        console.error('Could not find products table tbody');
        return;
    }
    
    tbody.innerHTML = '';
    
    if (!products || products.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center">No products found. Sync a collection first.</td></tr>';
        return;
    }
    
    products.forEach(product => {
        const row = document.createElement('tr');
        const status = (product.status || 'unknown').toLowerCase();
        row.innerHTML = `
            <td>${product.title || '-'}</td>
            <td>${product.handle || '-'}</td>
            <td><span class="badge badge-${status === 'active' ? 'success' : 'gray'}">${product.status || 'unknown'}</span></td>
            <td>${product.variants?.length || 0}</td>
            <td>${product.collection_id || '-'}</td>
            <td>
                <button class="btn btn-sm btn-secondary" onclick="viewProduct(${product.id})">View</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function syncCollection() {
    const collectionId = document.getElementById('sync-collection-id').value;
    const excludeTitle = document.getElementById('sync-exclude-title').value;
    
    if (!collectionId) {
        showAlert('error', 'Please enter a collection ID');
        return;
    }
    
    showLoading('products-table');
    
    try {
        const response = await fetch(`${API_BASE}/shopify/fetch-collection`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                collection_id: collectionId,
                exclude_title_contains: excludeTitle || null
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', `Synced ${result.total_products} products with ${result.total_variants} variants`);
            loadProducts();
        } else {
            throw new Error(result.detail || 'Sync failed');
        }
    } catch (error) {
        showAlert('error', `Sync failed: ${error.message}`);
        hideLoading('products-table');
    }
}

// Price Plans
async function loadPricePlans() {
    // Small delay to ensure DOM is ready
    await new Promise(resolve => setTimeout(resolve, 100));
    
    showLoading('pending-plans-container');
    
    try {
        const response = await fetch(`${API_BASE}/price-plans?limit=50`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const plans = await response.json();
        renderPricePlansTabs(plans);
    } catch (error) {
        console.error('Error loading price plans:', error);
        const tbody = document.getElementById('pending-plans-tbody');
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color: red;">Failed to load: ${error.message}</td></tr>`;
        }
    } finally {
        hideLoading('pending-plans-container');
    }
}

function switchPricePlanTab(tab) {
    // Update tab buttons
    document.getElementById('tab-pending-plans').style.borderBottomColor = tab === 'pending' ? '#2563eb' : 'transparent';
    document.getElementById('tab-pending-plans').style.color = tab === 'pending' ? '#2563eb' : '#666';
    
    document.getElementById('tab-applied-plans').style.borderBottomColor = tab === 'applied' ? '#2563eb' : 'transparent';
    document.getElementById('tab-applied-plans').style.color = tab === 'applied' ? '#2563eb' : '#666';
    
    document.getElementById('tab-failed-plans').style.borderBottomColor = tab === 'failed' ? '#2563eb' : 'transparent';
    document.getElementById('tab-failed-plans').style.color = tab === 'failed' ? '#2563eb' : '#666';
    
    document.getElementById('tab-price-history').style.borderBottomColor = tab === 'history' ? '#2563eb' : 'transparent';
    document.getElementById('tab-price-history').style.color = tab === 'history' ? '#2563eb' : '#666';
    
    // Update containers
    document.getElementById('pending-plans-container').style.display = tab === 'pending' ? 'block' : 'none';
    document.getElementById('applied-plans-container').style.display = tab === 'applied' ? 'block' : 'none';
    document.getElementById('failed-plans-container').style.display = tab === 'failed' ? 'block' : 'none';
    document.getElementById('price-history-container').style.display = tab === 'history' ? 'block' : 'none';
    
    // Load price history when switching to that tab
    if (tab === 'history') {
        loadPriceChangeHistory();
    }
}

function renderPricePlansTabs(plans) {
    // Separate plans by status
    const pendingPlans = plans.filter(p => p.status === 'pending');
    const appliedPlans = plans.filter(p => p.status === 'applied');
    const failedPlans = plans.filter(p => p.status === 'failed');
    
    // Render pending plans
    renderPricePlansTable(pendingPlans, 'pending-plans-tbody', 'pending');
    
    // Render applied plans
    renderPricePlansTable(appliedPlans, 'applied-plans-tbody', 'applied');
    
    // Render failed plans (and show tab only if there are failed plans)
    renderPricePlansTable(failedPlans, 'failed-plans-tbody', 'failed');
    const failedTab = document.getElementById('tab-failed-plans');
    failedTab.style.display = failedPlans.length > 0 ? 'block' : 'none';
}

function renderPricePlansTable(plans, tbodyId, planType) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) {
        console.error(`${tbodyId} element not found`);
        return;
    }
    
    tbody.innerHTML = '';
    
    if (plans.length === 0) {
        let emptyMessage = 'No price plans found';
        if (planType === 'pending') {
            emptyMessage = 'No pending price plans. Generate one to get started.';
        } else if (planType === 'applied') {
            emptyMessage = 'No applied price plans yet.';
        } else if (planType === 'failed') {
            emptyMessage = 'No failed price plans.';
        }
        tbody.innerHTML = `<tr><td colspan="6" class="text-center">${emptyMessage}</td></tr>`;
        return;
    }
    
    plans.forEach(plan => {
        const row = document.createElement('tr');
        const statusBadge = plan.status === 'pending' ? 'warning' : plan.status === 'applied' ? 'success' : 'danger';
        
        let dateColumn = '';
        if (planType === 'applied') {
            dateColumn = `<td>${plan.applied_at ? new Date(plan.applied_at).toLocaleString() : '—'}</td>`;
        } else {
            dateColumn = `<td>${new Date(plan.generated_at).toLocaleString()}</td>`;
        }
        
        let failedColumn = '';
        if (planType === 'failed') {
            const failedCount = plan.total_items - plan.applied_items;
            failedColumn = `<td>${failedCount}</td>`;
        }
        
        row.innerHTML = `
            <td>#${plan.id}</td>
            ${dateColumn}
            ${planType === 'failed' ? '' : `<td><span class="badge badge-${statusBadge}">${plan.status}</span></td>`}
            <td>${plan.total_items}</td>
            ${planType === 'failed' ? failedColumn : `<td>${plan.applied_items}/${plan.total_items}</td>`}
            <td>
                <button class="btn btn-sm btn-secondary" onclick="viewPricePlan(${plan.id})">View</button>
                ${planType === 'pending' ? `<button class="btn btn-sm btn-success" onclick="applyPricePlan(${plan.id})">Apply</button>` : ''}
                ${planType === 'applied' ? `<button class="btn btn-sm btn-primary" onclick="verifyPricePlan(${plan.id})">Verify</button>` : ''}
                <button class="btn btn-sm btn-danger" onclick="deletePricePlan(${plan.id})">Delete</button>
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function generatePricePlan() {
    const variantType = document.getElementById('plan-variant-type').value;
    
    showLoading('pending-plans-container');
    
    let requestBody = {
        variant_type: variantType,
        plan_type: 'price_update'
    };
    
    if (variantType === 'box') {
        // Box-specific fields
        const exchangeRate = parseFloat(document.getElementById('plan-exchange-rate').value) || null;
        const shippingCost = parseInt(document.getElementById('plan-shipping-cost').value) || 500;
        const margin = parseFloat(document.getElementById('plan-margin').value) || 20.0;
        const vat = parseFloat(document.getElementById('plan-vat').value) || 25.0;
        
        requestBody.exchange_rate = exchangeRate;
        requestBody.shipping_cost_jpy = shippingCost;
        requestBody.min_margin_pct = margin;
        requestBody.vat_pct = vat;
    } else {
        // Pack-specific fields
        const packMarkup = parseFloat(document.getElementById('plan-pack-markup').value) || 20.0;
        const minThreshold = parseFloat(document.getElementById('plan-min-threshold').value) || 5.0;
        
        requestBody.pack_markup_pct = packMarkup;
        requestBody.min_change_threshold = minThreshold;
    }
    
    try {
        const response = await fetch(`${API_BASE}/price-plans/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert(`Price plan #${result.id} generated with ${result.total_items} items. Refreshing...`, 'success');
            
            // Wait a moment then reload the plans list
            await new Promise(resolve => setTimeout(resolve, 500));
            await loadPricePlans();
            
            // Switch to pending tab to show the new plan
            switchPricePlanTab('pending');
        } else {
            throw new Error(result.detail || 'Generation failed');
        }
    } catch (error) {
        showAlert(`Failed to generate plan: ${error.message}`, 'error');
        hideLoading('pending-plans-container');
    }
}

// Removed: Use individual "Match Price" buttons on Competitor Maps tab instead

async function matchPriceForProduct(button) {
    try {
        showLoading('competitor-mappings-table');
        
        // Get the productGroup from the row's data attribute
        const productGroup = JSON.parse(button.closest('tr').dataset.productGroup);
        
        // Get current Shopify variant price
        const shopifyVariant = productGroup.shopify_variants && productGroup.shopify_variants.length > 0 
            ? productGroup.shopify_variants[0]
            : null;
        
        if (!shopifyVariant) {
            showAlert('No variant found for this product', 'error');
            hideLoading('competitor-mappings-table');
            return;
        }
        
        const currentPrice = parseFloat(shopifyVariant.price) || 0;
        const variantId = shopifyVariant.id;
        const productId = productGroup.shopify_product_id;
        const productTitle = productGroup.shopify_product_title;
        
        // Find lowest competitor price (only from in-stock competitors)
        let lowestCompetitorPrice = null;
        if (productGroup.competitors && productGroup.competitors.length > 0) {
            const prices = productGroup.competitors
                .filter(c => {
                    // Check if competitor is in stock (handle both Norwegian and English)
                    const inStock = c.competitor_stock === 'in_stock' 
                        || c.competitor_stock === 'På lager'
                        || (c.competitor_stock_amount && c.competitor_stock_amount > 0);
                    return inStock && c.competitor_price_ore;
                })
                .map(c => c.competitor_price_ore ? (c.competitor_price_ore / 100) : null)
                .filter(p => p !== null);
            
            console.log(`Found ${prices.length} in-stock competitor prices:`, prices);
            if (prices.length > 0) {
                lowestCompetitorPrice = Math.min(...prices);
                console.log(`Lowest competitor price: ${lowestCompetitorPrice}`);
            }
        }
        
        if (!lowestCompetitorPrice) {
            showAlert('No in-stock competitor prices found for this product', 'warning');
            hideLoading('competitor-mappings-table');
            return;
        }
        
        // Create price plan for this single product (regardless of price difference)
        const items = [{
            product_id: productId,
            product_title: productTitle,
            variant_id: variantId,
            variant_title: shopifyVariant.title,
            current_price: currentPrice,
            new_price: lowestCompetitorPrice
        }];
        
        const requestBody = {
            variant_type: 'box',
            plan_type: 'price_update',
            items: items,
            strategy: 'match_competition'
        };
        
        const response = await fetch(`${API_BASE}/price-plans/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            const planId = result.id;
            console.log(`Price plan #${planId} created, now applying...`);
            
            // Automatically apply the plan
            const applyResponse = await fetch(`${API_BASE}/price-plans/${planId}/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const applyResult = await applyResponse.json();
            
            if (applyResponse.ok) {
                console.log(`Plan #${planId} applied successfully! ${productTitle} updated to ${lowestCompetitorPrice.toFixed(2)} kr.`);
                showAlert(`Price plan #${planId} created and applied! ${productTitle} updated to ${lowestCompetitorPrice.toFixed(2)} kr. Refreshing...`, 'success');
                
                // Refresh the page to show the updated prices from database
                setTimeout(() => {
                    location.reload();
                }, 1500);
            } else {
                throw new Error(applyResult.detail || 'Plan apply failed');
            }
        } else {
            throw new Error(result.detail || 'Plan creation failed');
        }
    } catch (error) {
        showAlert(`Failed to create price plan: ${error.message}`, 'error');
        hideLoading('competitor-mappings-table');
    }
}

async function matchPriceForProductInStock(button) {
    try {
        // Get the productGroup from the row's data attribute
        const productGroup = JSON.parse(button.closest('tr').dataset.productGroup);
        
        // Get current Shopify variant price
        const shopifyVariant = productGroup.shopify_variants && productGroup.shopify_variants.length > 0 
            ? productGroup.shopify_variants[0]
            : null;
        
        if (!shopifyVariant) {
            showAlert('No variant found for this product', 'error');
            return;
        }
        
        const currentPrice = parseFloat(shopifyVariant.price) || 0;
        const variantId = shopifyVariant.id;
        const productTitle = productGroup.shopify_product_title;
        
        // Find lowest IN-STOCK competitor price only
        let lowestInStockPrice = null;
        let lowestInStockCompetitor = null;
        
        if (productGroup.competitors && productGroup.competitors.length > 0) {
            const inStockCompetitors = productGroup.competitors
                .filter(c => {
                    // Check if competitor is in stock (handle both Norwegian and English)
                    const inStock = c.competitor_stock === 'in_stock' 
                        || c.competitor_stock === 'På lager'
                        || (c.competitor_stock_amount && c.competitor_stock_amount > 0);
                    return inStock && c.competitor_price_ore;
                })
                .map(c => ({
                    name: c.competitor_name,
                    price: c.competitor_price_ore / 100
                }));
            
            console.log(`Found ${inStockCompetitors.length} in-stock competitors:`, inStockCompetitors);
            
            if (inStockCompetitors.length > 0) {
                // Find the competitor with the lowest price
                const lowest = inStockCompetitors.reduce((min, c) => 
                    c.price < min.price ? c : min
                );
                lowestInStockPrice = lowest.price;
                lowestInStockCompetitor = lowest.name;
                console.log(`Lowest in-stock: ${lowestInStockCompetitor} at ${lowestInStockPrice} kr`);
            }
        }
        
        if (!lowestInStockPrice || !lowestInStockCompetitor) {
            showAlert('No in-stock competitor prices found for this product', 'warning');
            return;
        }
        
        // Confirm the price change
        const confirmed = confirm(
            `Match price for "${productTitle}" to ${lowestInStockPrice.toFixed(2)} kr from ${lowestInStockCompetitor} (in stock)?`
        );
        
        if (!confirmed) return;
        
        showLoading('competitor-mappings-table');
        
        // Use direct variant update with logging - same approach as matchMappedCompetitorPrice
        const updateUrl = `${API_BASE}/shopify/variants/${variantId}` +
            `?price=${lowestInStockPrice}` +
            `&change_type=manual_in_stock_match` +
            `&competitor_name=${encodeURIComponent(lowestInStockCompetitor)}` +
            `&competitor_price=${lowestInStockPrice}`;
        
        const response = await fetch(updateUrl, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update variant price');
        }
        
        const result = await response.json();
        console.log(`Price updated. Log ID: ${result.log_id}, Old: ${result.old_price}, New: ${result.price}`);
        
        showAlert(`✓ Price updated to ${lowestInStockPrice.toFixed(2)} kr from ${lowestInStockCompetitor} (in stock)`, 'success');
        
        // Refresh the page to show updated prices
        setTimeout(() => {
            location.reload();
        }, 1500);
        
    } catch (error) {
        console.error('Error matching in-stock price:', error);
        showAlert(`❌ Failed to match in-stock price: ${error.message}`, 'error');
        hideLoading('competitor-mappings-table');
    }
}

async function viewPricePlan(planId) {
    try {
        const response = await fetch(`${API_BASE}/price-plans/${planId}`);
        const plan = await response.json();
        
        showModal('price-plan-detail-modal');
        document.getElementById('plan-detail-content').innerHTML = `
            <div class="mb-2"><strong>Plan ID:</strong> #${plan.id}</div>
            <div class="mb-2"><strong>Status:</strong> <span class="badge badge-${plan.status === 'pending' ? 'warning' : 'success'}">${plan.status}</span></div>
            <div class="mb-2"><strong>Generated:</strong> ${new Date(plan.generated_at).toLocaleString()}</div>
            <div class="mb-2"><strong>Total Items:</strong> ${plan.total_items}</div>
            <div class="mb-2"><strong>FX Rate:</strong> ${plan.fx_rate || 'N/A'}</div>
            
            <h4 class="mt-2 mb-1">Items (${plan.items?.length || 0})</h4>
            <div class="table-container">
                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Current Price</th>
                            <th>New Price</th>
                            <th>Change</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${(plan.items || []).map(item => `
                            <tr>
                                <td>${item.current_title}</td>
                                <td>${item.current_price} NOK</td>
                                <td>${item.new_price} NOK</td>
                                <td>${(item.new_price - item.current_price).toFixed(2)} NOK</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    } catch (error) {
        showAlert('error', `Failed to load plan: ${error.message}`);
    }
}

async function applyPricePlan(planId) {
    console.log('[JS] applyPricePlan called with planId:', planId);
    if (!confirm('Are you sure you want to apply this price plan? This will update prices on Shopify.')) {
        console.log('[JS] User cancelled');
        return;
    }
    
    console.log('[JS] User confirmed, showing loading...');
    showLoading('pending-plans-container');
    
    try {
        console.log('[JS] Making fetch request to:', `${API_BASE}/price-plans/${planId}/apply`);
        const response = await fetch(`${API_BASE}/price-plans/${planId}/apply`, {
            method: 'POST'
        });
        console.log('[JS] Got response:', response.status, response.statusText);
        
        const result = await response.json();
        console.log('[JS] Parsed result:', result);
        
        if (response.ok) {
            // Check if there are errors
            if (result.failed_items > 0 && result.error_s && result.error_s.length > 0) {
                console.error('[JS] Errors during apply:', result.error_s);
                const errorSummary = result.error_s.slice(0, 3).join('\n');
                const moreErrors = result.error_s.length > 3 ? `\n...and ${result.error_s.length - 3} more errors` : '';
                showAlert(`Applied ${result.applied_items} items, but ${result.failed_items} failed:\n${errorSummary}${moreErrors}`, 'danger');
                hideLoading('pending-plans-container');
            } else {
                showAlert(`Applied ${result.applied_items} price changes. Refreshing...`, 'success');
                
                // Reload page to show updated plan status
                setTimeout(() => {
                    window.location.hash = 'price-plans';
                    location.reload();
                }, 1000);
            }
        } else {
            throw new Error(result.detail || 'Apply failed');
        }
    } catch (error) {
        showAlert('error', `Failed to apply plan: ${error.message}`);
        hideLoading('pending-plans-container');
    }
}

async function deletePricePlan(planId) {
    if (!confirm(`Are you sure you want to delete price plan #${planId}?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/price-plans/${planId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showAlert(`Price plan #${planId} deleted successfully. Refreshing...`, 'success');
            
            // Reload page to show updated list
            setTimeout(() => {
                window.location.hash = 'price-plans';
                location.reload();
            }, 1000);
        } else {
            const result = await response.json();
            throw new Error(result.detail || 'Delete failed');
        }
    } catch (error) {
        showAlert(`Failed to delete plan: ${error.message}`, 'error');
    }
}

async function loadPriceChangeHistory() {
    showLoading('price-history-container');
    
    try {
        const response = await fetch(`${API_BASE}/shopify/price-change-history?limit=100`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        const tbody = document.getElementById('price-history-tbody');
        tbody.innerHTML = '';
        
        if (data.logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" class="text-center">No price changes yet</td></tr>';
            return;
        }
        
        data.logs.forEach(log => {
            const row = document.createElement('tr');
            const changeAmount = log.price_delta || 0;
            const changeColor = changeAmount < 0 ? 'green' : (changeAmount > 0 ? 'red' : 'gray');
            const changeSymbol = changeAmount < 0 ? '↓' : (changeAmount > 0 ? '↑' : '=');
            
            row.innerHTML = `
                <td>${new Date(log.created_at).toLocaleString()}</td>
                <td>
                    <div style="font-weight: 500;">${log.product_title}</div>
                    ${log.variant_title ? `<div style="font-size: 0.85em; color: #666;">${log.variant_title}</div>` : ''}
                </td>
                <td>${log.old_price.toFixed(2)} kr</td>
                <td>${log.new_price.toFixed(2)} kr</td>
                <td style="color: ${changeColor}; font-weight: 500;">${changeSymbol} ${Math.abs(changeAmount).toFixed(2)} kr</td>
                <td>${formatChangeType(log.change_type)}</td>
                <td>${log.competitor_name || '—'}</td>
            `;
            tbody.appendChild(row);
        });
    } catch (error) {
        console.error('Error loading price history:', error);
        const tbody = document.getElementById('price-history-tbody');
        tbody.innerHTML = `<tr><td colspan="7" class="text-center" style="color: red;">Failed to load: ${error.message}</td></tr>`;
    } finally {
        hideLoading('price-history-container');
    }
}

function formatChangeType(type) {
    const types = {
        'manual_competitor_match': 'Manual Match',
        'manual_in_stock_match': 'In-Stock Match',
        'auto_update': 'Auto Update',
        'manual_update': 'Manual Update',
        'bulk_update': 'Bulk Update'
    };
    return types[type] || type;
}

async function verifyPricePlan(planId) {
    if (!confirm(`Verify that price changes were actually applied in Shopify for plan #${planId}?`)) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/price-plans/${planId}/verify`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            if (result.status === 'verified') {
                showAlert(`Verification successful! ${result.verified_items} items confirmed.`, 'success');
            } else if (result.status === 'reverted') {
                showAlert(`Verification failed! ${result.mismatched_items} mismatches found. Plan reverted to pending. Refreshing...`, 'error');
                setTimeout(() => {
                    window.location.hash = 'price-plans';
                    location.reload();
                }, 2000);
            }
        } else {
            throw new Error(result.detail || 'Verification failed');
        }
    } catch (error) {
        showAlert(`Failed to verify plan: ${error.message}`, 'error');
    }
}

// Booster Variants
async function loadBoosterVariantPlans() {
    const tbody = ensureTableBody('booster-variants-table', [
        'Plan ID', 'Generated', 'Status', 'Items', 'Actions'
    ]);
    if (!tbody) return;
    setTableBodyMessage(tbody, 5, 'Loading...');

    try {
        const response = await fetch(`${API_BASE}/booster-variants/plans?limit=50`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const plans = await response.json();
        renderBoosterVariantPlansTable(plans, tbody);
    } catch (error) {
        console.error('Error loading booster variant plans:', error);
        setTableBodyMessage(tbody, 5, `Failed to load: ${error.message}`, true);
    }
}

function renderBoosterVariantPlansTable(plans, tbody) {
    const targetBody = tbody || document.querySelector('#booster-variants-table tbody');
    if (!targetBody) {
        console.error('Cannot find tbody for booster-variants-table');
        return;
    }
    targetBody.innerHTML = '';
    
    if (plans.length === 0) {
        setTableBodyMessage(targetBody, 5, 'No booster variant plans found.');
        return;
    }
    
    plans.forEach(plan => {
        const row = document.createElement('tr');
        const statusBadge = plan.status === 'pending' ? 'warning' : plan.status === 'applied' ? 'success' : 'gray';
        
        row.innerHTML = `
            <td>#${plan.id}</td>
            <td>${new Date(plan.generated_at).toLocaleString()}</td>
            <td><span class="badge badge-${statusBadge}">${plan.status}</span></td>
            <td>${plan.total_items}</td>
            <td>
                ${plan.status === 'pending' ? `<button class="btn btn-sm btn-success" onclick="applyBoosterVariantPlan(${plan.id})">Apply</button>` : ''}
            </td>
        `;
        targetBody.appendChild(row);
    });
}

async function generateBoosterVariantPlan() {
    const collectionId = document.getElementById('booster-variant-collection-id').value;
    
    if (!collectionId) {
        showAlert('error', 'Please enter a collection ID');
        return;
    }
    
    const tbody = ensureTableBody('booster-variants-table', [
        'Plan ID', 'Generated', 'Status', 'Items', 'Actions'
    ]);
    setTableBodyMessage(tbody, 5, 'Generating plan...');
    
    try {
        const response = await fetch(`${API_BASE}/booster-variants/generate-plan?collection_id=${collectionId}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', `Booster variant plan #${result.id} generated with ${result.total_items} items`);
            loadBoosterVariantPlans();
        } else {
            throw new Error(result.detail || 'Generation failed');
        }
    } catch (error) {
        showAlert('error', `Failed to generate plan: ${error.message}`);
        if (tbody) {
            setTableBodyMessage(tbody, 5, `Failed to generate: ${error.message}`, true);
        }
    }
}

async function applyBoosterVariantPlan(planId) {
    if (!confirm('Are you sure? This will split products into Booster Box + Pack variants on Shopify.')) {
        return;
    }
    
    const tbody = ensureTableBody('booster-variants-table', [
        'Plan ID', 'Generated', 'Status', 'Items', 'Actions'
    ]);
    setTableBodyMessage(tbody, 5, 'Applying plan...');
    
    try {
        const response = await fetch(`${API_BASE}/booster-variants/plans/${planId}/apply`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', `Applied ${result.applied_items} variant splits`);
            loadBoosterVariantPlans();
        } else {
            throw new Error(result.detail || 'Apply failed');
        }
    } catch (error) {
        showAlert('error', `Failed to apply plan: ${error.message}`);
        if (tbody) {
            setTableBodyMessage(tbody, 5, `Failed to apply: ${error.message}`, true);
        }
    }
}

// Booster Inventory
async function loadBoosterInventoryPlans() {
    const tbody = ensureTableBody('booster-inventory-table', [
        'Plan ID', 'Generated', 'Status', 'Items', 'Actions'
    ]);
    if (!tbody) return;
    setTableBodyMessage(tbody, 5, 'Loading...');

    try {
        const response = await fetch(`${API_BASE}/booster-inventory/plans?limit=50`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        const plans = await response.json();
        renderBoosterInventoryPlansTable(plans, tbody);
    } catch (error) {
        console.error('Error loading booster inventory plans:', error);
        setTableBodyMessage(tbody, 5, `Failed to load: ${error.message}`, true);
    }
}

function renderBoosterInventoryPlansTable(plans, tbody) {
    const targetBody = tbody || document.querySelector('#booster-inventory-table tbody');
    if (!targetBody) {
        console.error('Cannot find tbody for booster-inventory-table');
        return;
    }
    targetBody.innerHTML = '';
    
    if (plans.length === 0) {
        setTableBodyMessage(targetBody, 5, 'No booster inventory plans found.');
        return;
    }
    
    plans.forEach(plan => {
        const row = document.createElement('tr');
        const statusBadge = plan.status === 'pending' ? 'warning' : plan.status === 'applied' ? 'success' : 'gray';
        
        row.innerHTML = `
            <td>#${plan.id}</td>
            <td>${new Date(plan.generated_at).toLocaleString()}</td>
            <td><span class="badge badge-${statusBadge}">${plan.status}</span></td>
            <td>${plan.total_items}</td>
            <td>
                ${plan.status === 'pending' ? `<button class="btn btn-sm btn-success" onclick="applyBoosterInventoryPlan(${plan.id})">Apply</button>` : ''}
            </td>
        `;
        targetBody.appendChild(row);
    });
}

async function generateBoosterInventoryPlan() {
    const collectionId = document.getElementById('booster-inventory-collection-id').value;
    
    if (!collectionId) {
        showAlert('error', 'Please enter a collection ID');
        return;
    }
    
    const tbody = ensureTableBody('booster-inventory-table', [
        'Plan ID', 'Generated', 'Status', 'Items', 'Actions'
    ]);
    setTableBodyMessage(tbody, 5, 'Generating plan...');
    
    try {
        const response = await fetch(`${API_BASE}/booster-inventory/generate-plan?collection_id=${collectionId}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', `Booster inventory plan #${result.id} generated with ${result.total_items} items`);
            loadBoosterInventoryPlans();
        } else {
            throw new Error(result.detail || 'Generation failed');
        }
    } catch (error) {
        showAlert('error', `Failed to generate plan: ${error.message}`);
        if (tbody) {
            setTableBodyMessage(tbody, 5, `Failed to generate: ${error.message}`, true);
        }
    }
}

async function applyBoosterInventoryPlan(planId) {
    if (!confirm('Are you sure? This will adjust inventory levels on Shopify.')) {
        return;
    }
    
    const tbody = ensureTableBody('booster-inventory-table', [
        'Plan ID', 'Generated', 'Status', 'Items', 'Actions'
    ]);
    setTableBodyMessage(tbody, 5, 'Applying plan...');
    
    try {
        const response = await fetch(`${API_BASE}/booster-inventory/plans/${planId}/apply`, {
            method: 'POST'
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', `Applied ${result.applied_items} inventory adjustments`);
            loadBoosterInventoryPlans();
        } else {
            throw new Error(result.detail || 'Apply failed');
        }
    } catch (error) {
        showAlert('error', `Failed to apply plan: ${error.message}`);
        if (tbody) {
            setTableBodyMessage(tbody, 5, `Failed to apply: ${error.message}`, true);
        }
    }
}

// Mappings
async function loadMappings() {
    const tableContainer = document.getElementById('mappings-table');
    if (!tableContainer) {
        console.error('mappings-table element not found');
        return;
    }

    const tbody = document.getElementById('mappings-tbody');
    if (tbody) {
        setTableBodyMessage(tbody, 4, 'Loading...');
    }

    try {
        const response = await fetch(`${API_BASE}/mappings/snkrdunk?limit=100`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const mappings = await response.json();
        window.productMappings = {};
        if (mappings && mappings.length > 0 && window.shopifyProducts) {
            mappings.forEach(mapping => {
                const shopifyProduct = window.shopifyProducts.find(
                    p => p.shopify_id === mapping.product_shopify_id
                );
                if (shopifyProduct) {
                    window.productMappings[mapping.snkrdunk_key] = shopifyProduct.id;
                }
            });
        }

        // Rendering is now handled by the combined table in Mappings tab
        // renderMappingsTable();
    } catch (error) {
        console.error('Error loading mappings:', error);
        showAlert('Failed to load mappings: ' + error.message, 'error');
        
        // Show error in table
        if (tbody) {
            setTableBodyMessage(tbody, 4, `Failed to load mappings: ${error.message}`, true);
        }
    }
}

// ============================================================================
// SNKRDUNK Products Functions
// ============================================================================

async function loadSnkrdunkProducts() {
    const tableContainer = document.getElementById('snkrdunk-products-table');
    if (!tableContainer) {
        console.error('snkrdunk-products-table element not found');
        return;
    }

    const tbody = document.getElementById('snkrdunk-products-tbody');
    if (tbody) {
        setTableBodyMessage(tbody, 5, 'Loading...');
    }

    try {
        const response = await fetch(`${API_BASE}/snkrdunk/products`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        window.snkrdunkProducts = data.items || [];
        renderSnkrdunkProductsTable(data.items);
        
        if (data.total_items > 0) {
            showAlert(`Loaded ${data.total_items} SNKRDUNK products`, 'success');
        }
    } catch (error) {
        console.error('Error loading SNKRDUNK products:', error);
        showAlert('Failed to load SNKRDUNK products: ' + error.message, 'error');
        
        // Show error in table
        if (tbody) {
            setTableBodyMessage(tbody, 5, `Failed to load products: ${error.message}`, true);
        }
    }
}

function renderSnkrdunkProductsTable(products) {
    // Try multiple times to find the element
    let attempts = 0;
    const maxAttempts = 10;
    
    const tryRender = () => {
        const tbody = document.querySelector('#snkrdunk-products-table tbody');
        
        if (!tbody) {
            attempts++;
            if (attempts < maxAttempts) {
                setTimeout(tryRender, 50);
                return;
            }
            console.error('Cannot find tbody in #snkrdunk-products-table after', attempts, 'attempts');
            console.log('Tab content:', document.getElementById('mappings-tab'));
            console.log('Table container:', document.getElementById('snkrdunk-products-table'));
            return;
        }
        
        tbody.innerHTML = '';
        
        if (!products || products.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="text-center" style="padding: 2rem;">
                        <p style="color: var(--text-secondary); margin-bottom: 1rem;">No SNKRDUNK products cached.</p>
                        <p style="color: var(--text-secondary); font-size: 0.875rem;">
                            Click "Fetch from SNKRDUNK" to load products.
                        </p>
                    </td>
                </tr>
            `;
            return;
        }
        
        products.forEach(product => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${product.id || '-'}</td>
                <td style="max-width: 300px;">${product.name || '-'}</td>
                <td>¥${product.minPriceJpy ? product.minPriceJpy.toLocaleString() : '-'}</td>
                <td>¥${product.maxPriceJpy ? product.maxPriceJpy.toLocaleString() : '-'}</td>
                <td>${product.brand?.name || '-'}</td>
                <td><span class="badge badge-info">Page ${product._page || '?'}</span></td>
            `;
            tbody.appendChild(row);
        });
    };
    
    tryRender();
}

async function clearSnkrdunkCache() {
    if (!confirm('Are you sure you want to clear the SNKRDUNK cache? This will remove all cached products.')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/snkrdunk/cache`, {
            method: 'DELETE'
        });
        
        if (!response.ok) throw new Error('Failed to clear cache');
        
        showAlert('Cache cleared successfully', 'success');
        await loadSnkrdunkProducts();
    } catch (error) {
        showAlert('Failed to clear cache: ' + error.message, 'error');
    }
}

// Reports
async function loadReports() {
    loadAuditLogs();
}

async function loadAuditLogs() {
    const tbody = ensureTableBody('audit-logs-table', [
        'Timestamp', 'Operation', 'Entity Type', 'Status', 'Error'
    ]);
    if (!tbody) return;
    setTableBodyMessage(tbody, 5, 'Loading...');

    try {
        const response = await fetch(`${API_BASE}/reports/audit-logs?limit=50`);
        const logs = await response.json();
        renderAuditLogsTable(logs, tbody);
    } catch (error) {
        console.error('Failed to load audit logs:', error);
        setTableBodyMessage(tbody, 5, 'Failed to load audit logs', true);
    }
}

function renderAuditLogsTable(logs, tbody) {
    const targetBody = tbody || document.querySelector('#audit-logs-table tbody');
    if (!targetBody) {
        console.error('Cannot find tbody for audit-logs-table');
        return;
    }
    targetBody.innerHTML = '';
    
    if (logs.length === 0) {
        setTableBodyMessage(targetBody, 5, 'No audit logs found.');
        return;
    }
    
    logs.forEach(log => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td>${new Date(log.created_at).toLocaleString()}</td>
            <td>${log.operation}</td>
            <td>${log.entity_type || '-'}</td>
            <td><span class="badge badge-${log.success ? 'success' : 'danger'}">${log.success ? 'Success' : 'Failed'}</span></td>
            <td>${log.error_message || '-'}</td>
        `;
        targetBody.appendChild(row);
    });
}

async function generateStockReport() {
    const collectionId = document.getElementById('stock-report-collection-id').value;
    
    if (!collectionId) {
        showAlert('error', 'Please enter a collection ID');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/reports/stock`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ collection_id: collectionId })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            showAlert('success', `Stock report generated: ${result.total_products} products, ${result.total_variants} variants`);
        } else {
            throw new Error(result.detail || 'Generation failed');
        }
    } catch (error) {
        showAlert('error', `Failed to generate report: ${error.message}`);
    }
}

// SNKRDUNK Operations
async function fetchSnkrdunk() {
    showLoading('snkrdunk-status');
    
    try {
        const response = await fetch(`${API_BASE}/snkrdunk/fetch`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                pages: [1, 2, 3, 4, 5, 6],
                force_refresh: true
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            const logId = result.log_id;
            const itemCount = result.total_items || 0;
            const message = logId 
                ? `✓ Scan #${logId}: Fetched ${itemCount} items from SNKRDUNK`
                : `✓ Fetched ${itemCount} items from SNKRDUNK`;
            showAlert('success', message);
            return result;
        } else {
            throw new Error(result.detail || 'Fetch failed');
        }
    } catch (error) {
        showAlert('error', `Failed to fetch SNKRDUNK: ${error.message}`);
        throw error;
    } finally {
        hideLoading('snkrdunk-status');
    }
}

// Alias for button onclick
function fetchSnkrdunkData() {
    fetchSnkrdunk().then(result => {
        // Reload the mappings tab after successful fetch
        setTimeout(() => {
            loadTabData('mappings');
            // Explicitly reload the dropdown after a short delay to show new scan
            setTimeout(() => loadSnkrdunkScanHistory(), 500);
        }, 500);
    }).catch(error => {
        console.error('Fetch failed:', error);
    });
}

// Utility Functions
function hideLoading(elementId) {
    // Content will be replaced by render functions
}

function showError(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `<div class="alert alert-error">${message}</div>`;
    }
}

function setTableBodyMessage(tbody, colSpan, message, isError = false) {
    if (!tbody) return;
    const color = isError ? 'color: var(--danger);' : '';
    tbody.innerHTML = `
        <tr>
            <td colspan="${colSpan}" class="text-center" style="${color}">${message}</td>
        </tr>
    `;
}

function ensureTableBody(containerId, headers, tableClass = '') {
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Container not found: ${containerId}`);
        return null;
    }

    let table = container.querySelector('table');
    if (!table) {
        table = document.createElement('table');
        if (tableClass) table.className = tableClass;

        const thead = document.createElement('thead');
        const headerRow = document.createElement('tr');
        headers.forEach(header => {
            const th = document.createElement('th');
            th.textContent = header;
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        container.innerHTML = '';
        container.appendChild(table);
    }

    let tbody = table.querySelector('tbody');
    if (!tbody) {
        tbody = document.createElement('tbody');
        table.appendChild(tbody);
    }

    return tbody;
}

function showAlert(typeOrMessage, messageOrType) {
    // Handle both parameter orders for backward compatibility
    let type, message;
    
    const validTypes = ['success', 'error', 'warning', 'info', 'danger'];
    
    if (validTypes.includes(typeOrMessage)) {
        // Called as (type, message)
        type = typeOrMessage;
        message = messageOrType;
    } else if (validTypes.includes(messageOrType)) {
        // Called as (message, type)
        type = messageOrType;
        message = typeOrMessage;
    } else {
        // Default to info if type not recognized
        type = 'info';
        message = typeOrMessage;
    }
    
    const alertsContainer = document.getElementById('alerts-container');
    if (!alertsContainer) return;
    
    const alertClass = type === 'success' ? 'alert-success' : type === 'error' ? 'alert-error' : type === 'warning' ? 'alert-warning' : type === 'danger' ? 'alert-danger' : 'alert-info';
    
    const alert = document.createElement('div');
    alert.className = `alert ${alertClass}`;
    alert.textContent = message;
    
    alertsContainer.appendChild(alert);
    
    setTimeout(() => alert.remove(), 5000);
}

function showModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

// Close modal on background click
document.addEventListener('click', (e) => {
    if (e.target && e.target.classList && e.target.classList.contains('modal')) {
        e.target.classList.remove('active');
    }
});

// ============================================================================
// Settings Functions
// ============================================================================

function renderSettingsTab(containerId = 'dynamic-tab') {
    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = `
        <div class="card">
            <div class="card-header">
                <h3 class="card-title">⚙️ Settings</h3>
            </div>
            <div id="settings-status" class="form-hint">Loading settings...</div>
        </div>

        <div class="card">
            <div class="card-header">
                <h3 class="card-title">🔐 API Keys</h3>
            </div>
            <form id="api-keys-form">
                <div class="grid-2">
                    <div class="form-group">
                        <label class="form-label">Shopify Shop Domain</label>
                        <input type="text" class="form-input" id="shopify-shop" placeholder="myshop.myshopify.com" required>
                        <small style="color: var(--text-secondary);">Your Shopify store URL</small>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Shopify Admin API Token</label>
                        <input type="password" class="form-input" id="shopify-token" placeholder="shpat_..." required>
                        <small style="color: var(--text-secondary);">Admin API access token from Shopify</small>
                    </div>
                </div>
                <div class="form-group">
                    <label class="form-label">Google Translate API Key (optional)</label>
                    <input type="password" class="form-input" id="google-api-key" placeholder="AIza...">
                </div>
                <div class="flex gap-2">
                    <button type="submit" class="btn btn-primary">💾 Save</button>
                    <button type="button" class="btn btn-secondary" onclick="loadSettings()">🔄 Reload</button>
                </div>
            </form>
        </div>

        <div class="card">
            <div class="card-header">
                <h3 class="card-title">📋 All Settings</h3>
            </div>
            <div id="settings-table" class="table-container"></div>
        </div>
    `;

    const form = document.getElementById('api-keys-form');
    if (form) {
        form.addEventListener('submit', saveApiKeys);
    }
}

function renderDynamicTab(tabName) {
    const container = document.getElementById('dynamic-tab');
    if (!container) return;

    if (tabName === 'booster-variants') {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Generate Booster Variant Plan</h3>
                </div>
                <div class="form-group">
                    <label class="form-label">Collection ID</label>
                    <input type="text" id="booster-variant-collection-id" class="form-input" placeholder="444116140283" value="444116140283">
                    <div class="form-hint">Booster collection ID (typically 444116140283)</div>
                </div>
                <button class="btn btn-primary" onclick="generateBoosterVariantPlan()">Generate Plan</button>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Booster Variant Plans</h3>
                    <button class="btn btn-sm btn-secondary" onclick="loadBoosterVariantPlans()">Refresh</button>
                </div>
                <div id="booster-variants-table" class="table-container"></div>
            </div>
        `;
        return;
    }

    if (tabName === 'booster-inventory') {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Generate Booster Inventory Plan</h3>
                </div>
                <div class="form-group">
                    <label class="form-label">Collection ID</label>
                    <input type="text" id="booster-inventory-collection-id" class="form-input" placeholder="444116140283" value="444116140283">
                    <div class="form-hint">Booster collection ID</div>
                </div>
                <button class="btn btn-primary" onclick="generateBoosterInventoryPlan()">Generate Plan</button>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Booster Inventory Plans</h3>
                    <button class="btn btn-sm btn-secondary" onclick="loadBoosterInventoryPlans()">Refresh</button>
                </div>
                <div id="booster-inventory-table" class="table-container"></div>
            </div>
        `;
        return;
    }

    if (tabName === 'mappings') {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">� SNKRDUNK Products & Mappings</h3>
                    <button class="btn btn-sm btn-secondary" onclick="loadTabData('mappings')">Refresh</button>
                </div>
                <div class="flex gap-2" style="margin-bottom: 1rem;">
                    <button class="btn btn-primary" onclick="fetchSnkrdunkData()">🔄 Fetch from SNKRDUNK</button>
                    <button class="btn btn-secondary" onclick="clearSnkrdunkCache()">🗑️ Clear Cache</button>
                    <button class="btn btn-primary" onclick="autoMapProducts()">🤖 Auto-Map All</button>
                </div>
                <div style="margin-bottom: 1rem; padding: 0.75rem; background: #f9fafb; border-radius: 4px;">
                    <label class="form-label" style="margin-bottom: 0.5rem; font-weight: 600;">Previous SNKRDUNK Price Updates</label>
                    <select id="snkrdunk-scan-select" class="form-input" onchange="loadSnkrdunkScan()" style="max-width: 400px;">
                        <option value="">-- Loading previous updates --</option>
                    </select>
                </div>
                <table class="data-table" id="snkrdunk-products-table" style="width: 100%; overflow-x: auto;">
                    <thead>
                        <tr>
                            <th style="min-width: 60px;">ID</th>
                            <th style="min-width: 150px;">SNKRDUNK Product</th>
                            <th style="min-width: 100px;">Price (¥)</th>
                            <th style="min-width: 100px;">Price Change</th>
                            <th style="min-width: 100px;">Brand</th>
                            <th style="min-width: 120px;">Last Updated</th>
                            <th style="min-width: 30px; text-align: center;">→</th>
                            <th style="min-width: 200px;">Mapped Shopify Product</th>
                            <th style="min-width: 80px;">Actions</th>
                        </tr>
                    </thead>
                    <tbody id="snkrdunk-products-tbody"></tbody>
                </table>
            </div>
        `;
        return;
    }

    if (tabName === 'reports') {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Generate Stock Report</h3>
                </div>
                <div class="form-group">
                    <label class="form-label">Collection ID</label>
                    <input type="text" id="stock-report-collection-id" class="form-input" placeholder="444175384827" value="444175384827">
                </div>
                <button class="btn btn-primary" onclick="generateStockReport()">Generate Report</button>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">Audit Logs</h3>
                    <button class="btn btn-sm btn-secondary" onclick="loadAuditLogs()">Refresh</button>
                </div>
                <div id="audit-logs-table" class="table-container"></div>
            </div>
        `;
        return;
    }

    if (tabName === 'competitors') {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">🔍 Competitor Scanner</h3>
                    <button class="btn btn-sm btn-secondary" onclick="loadCompetitors()">Refresh Data</button>
                </div>
                <div class="grid-2" style="margin-bottom: 1rem;">
                    <div>
                        <label class="form-label">Quick Scan</label>
                        <div class="flex gap-1" style="flex-wrap: wrap;">
                            <button class="btn btn-sm btn-primary" onclick="runCompetitorScraper('boosterpakker')">🇳🇴 Booster Pakker</button>
                            <button class="btn btn-sm btn-primary" onclick="runCompetitorScraper('hatamontcg')">🎴 HataMonTCG</button>
                            <button class="btn btn-sm btn-primary" onclick="runCompetitorScraper('laboge')">📦 Laboge</button>
                            <button class="btn btn-sm btn-primary" onclick="runCompetitorScraper('lcg_cards')">🃏 LCG Cards</button>
                            <button class="btn btn-sm btn-primary" onclick="runCompetitorScraper('pokemadness')">🎁 Pokemadness</button>
                        </div>
                    </div>
                    <div>
                        <label class="form-label">Bulk Operations</label>
                        <div class="flex gap-1">
                            <button class="btn btn-sm btn-primary" onclick="runAllCompetitorScrapers()">Scan All Sites</button>
                            <button class="btn btn-sm btn-secondary" onclick="reprocessCompetitorProducts()">Normalize & Filter Pokémon</button>
                            <button class="btn btn-sm btn-secondary" onclick="loadUnmappedCompetitors()">Show Unmapped</button>
                        </div>
                    </div>
                </div>
                <div id="competitor-scan-status" style="display: none; margin: 1rem 0; padding: 1rem; background: var(--bg-secondary); border-radius: var(--border-radius); font-size: 0.875rem;">
                    <div><strong id="scan-status-text">Scanning...</strong></div>
                    <div id="scan-status-detail" style="margin-top: 0.5rem; color: var(--text-secondary);"></div>
                </div>

            </div>

            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">📊 Competitor Products</h3>
                    <button class="btn btn-primary" id="auto-map-btn" onclick="autoMapCompetitors()" style="margin-left: auto;">🤖 Auto-Map</button>
                </div>
                <div class="grid-3" style="margin-bottom: 1rem;">
                    <div class="form-group">
                        <label class="form-label">Category Filter</label>
                        <select id="competitor-category-filter" class="form-input" onchange="filterCompetitorProducts()">
                            <option value="">All Categories</option>
                            <option value="booster_box">Booster Box</option>
                            <option value="booster_pack">Booster Pack</option>
                            <option value="elite_trainer_box">Elite Trainer Box</option>
                            <option value="theme_deck">Theme Deck</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Website Filter</label>
                        <select id="competitor-website-filter" class="form-input" onchange="filterCompetitorProducts()">
                            <option value="">All Websites</option>
                            <option value="boosterpakker">Booster Pakker</option>
                            <option value="hatamontcg">HataMonTCG</option>
                            <option value="laboge">Laboge</option>
                            <option value="lcg_cards">LCG Cards</option>
                            <option value="pokemadness">Pokemadness</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label class="form-label">Brand Filter</label>
                        <input type="text" id="competitor-brand-filter" class="form-input" placeholder="e.g., Pokémon" onchange="filterCompetitorProducts()">
                    </div>
                </div>
                <div id="competitors-table" class="table-container"></div>
            </div>

            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">🔗 Product Mapping</h3>
                </div>
                <div id="competitors-mapping-section">
                    <div id="competitor-mapping-empty" style="color: var(--text-secondary); text-align: center; padding: 2rem;">
                        Select a competitor product to map it to your Shopify product
                    </div>
                    <div id="competitor-mapping-panel" style="display: none;">
                        <div class="grid-2" style="margin-bottom: 1rem;">
                            <div>
                                <div class="form-label">Selected Competitor</div>
                                <div id="competitor-selected-summary">—</div>
                            </div>
                            <div>
                                <div class="form-label">Price (NOK)</div>
                                <div id="competitor-selected-price">—</div>
                            </div>
                        </div>
                        <div class="grid-2" style="margin-bottom: 1rem;">
                            <div class="form-group">
                                <label class="form-label">Map to Shopify Product</label>
                                <select id="competitor-shopify-select" class="form-input"></select>
                                <div class="form-hint">Select the matching Shopify product</div>
                                <div class="flex gap-2" style="margin-top: 0.5rem;">
                                    <button class="btn btn-sm btn-primary" onclick="mapSelectedCompetitorToShopify()">Map to Shopify</button>
                                    <button class="btn btn-sm btn-secondary" onclick="loadCompetitorPriceComparison()">Compare Prices</button>
                                </div>
                            </div>
                            <div class="form-group">
                                <label class="form-label">Map to SNKRDUNK Product</label>
                                <select id="competitor-snkrdunk-select" class="form-input"></select>
                                <div class="form-hint">Select the matching SNKRDUNK product</div>
                                <div class="flex gap-2" style="margin-top: 0.5rem;">
                                    <button class="btn btn-sm btn-primary" onclick="mapSelectedCompetitorToSnkrdunk()">Map to SNKRDUNK</button>
                                </div>
                            </div>
                        </div>
                        <div class="card" style="margin-top: 1rem;">
                            <div class="card-header">
                                <h4 class="card-title">📈 Price Comparison</h4>
                            </div>
                            <div id="competitor-price-compare">Select a Shopify product to compare prices.</div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        return;
    }

    if (tabName === 'settings') {
        renderSettingsTab('dynamic-tab');
        return;
    }

    if (tabName === 'competitor-mappings') {
        container.innerHTML = `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">🗺️ Competitor Product Mappings</h3>
                    <div style="display: flex; gap: 0.5rem;">
                        <button class="btn btn-sm btn-secondary" onclick="refreshShopifyPrices()">Refresh Shopify Prices</button>
                        <button class="btn btn-sm btn-secondary" onclick="loadCompetitorMappings()">Refresh</button>
                    </div>
                </div>
                <div id="competitor-mappings-table" class="table-container"></div>
            </div>
        `;
        return;
    }
}

async function loadSettings() {
    await loadCurrentSettings();
    await loadAllSettings();
}

async function loadCurrentSettings() {
    try {
        const response = await fetch(`${API_BASE}/settings/`);
        const settings = await response.json();
        const statusEl = document.getElementById('settings-status');
        if (statusEl) {
            statusEl.textContent = 'Settings loaded.';
        }
        
        // Populate form fields with masked values
        settings.forEach(setting => {
            if (setting.key === 'shopify_shop') {
                document.getElementById('shopify-shop').value = setting.value || '';
            } else if (setting.key === 'shopify_token') {
                document.getElementById('shopify-token').placeholder = setting.value ? `Saved: ${setting.value}` : 'shpat_...';
                document.getElementById('shopify-token').value = '';
            } else if (setting.key === 'google_translate_api_key') {
                document.getElementById('google-api-key').placeholder = setting.value ? `Saved: ${setting.value}` : 'AIza...';
                document.getElementById('google-api-key').value = '';
            }
        });
        
    } catch (error) {
        console.error('Failed to load settings:', error);
        const statusEl = document.getElementById('settings-status');
        if (statusEl) {
            statusEl.textContent = 'Failed to load settings.';
        }
    }
}

async function loadAllSettings() {
    try {
        const response = await fetch(`${API_BASE}/settings/`);
        const settings = await response.json();
        const tbody = ensureTableBody('settings-table', [
            'Key', 'Value', 'Description', 'Type'
        ], 'data-table');
        if (!tbody) return;
        tbody.innerHTML = '';

        if (settings.length === 0) {
            setTableBodyMessage(tbody, 4, 'No settings configured yet.');
            return;
        }

        settings.forEach(s => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><code>${s.key}</code></td>
                <td><code>${s.value || '-'}</code></td>
                <td>${s.description || '-'}</td>
                <td>
                    <span class="badge ${s.is_sensitive ? 'badge-warning' : 'badge-info'}">
                        ${s.is_sensitive ? '🔒 Sensitive' : '📄 Public'}
                    </span>
                </td>
            `;
            tbody.appendChild(row);
        });
        
    } catch (error) {
        showAlert('Failed to load all settings', 'error');
        const tbody = ensureTableBody('settings-table', [
            'Key', 'Value', 'Description', 'Type'
        ], 'data-table');
        if (tbody) {
            setTableBodyMessage(tbody, 4, 'Failed to load settings.', true);
        }
    }
}

// ============================================================================
// Product Mapping Functions
// ============================================================================

// Store current mappings
window.productMappings = {};

function renderMappingsTable() {
    const tbody = document.getElementById('mappings-tbody');
    if (!tbody) {
        console.error('mappings-tbody element not found');
        return;
    }
    
    if (!window.snkrdunkProducts || !window.shopifyProducts) {
        console.warn('Missing snkrdunkProducts or shopifyProducts data');
        tbody.innerHTML = '<tr><td colspan="5" class="text-center">No data loaded. Please fetch SNKRDUNK data first.</td></tr>';
        return;
    }
    
    tbody.innerHTML = '';
    
    if (window.snkrdunkProducts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center">No SNKRDUNK products to map</td></tr>';
        return;
    }
    
    window.snkrdunkProducts.forEach((snkrProduct) => {
        try {
            const row = document.createElement('tr');
            row.dataset.snkrdunkId = snkrProduct.id;
            
            const mappedShopifyId = window.productMappings[snkrProduct.id];
            const selectOptions = '<option value="">-- Select Shopify Product --</option>' +
                window.shopifyProducts.map(sp => 
                    `<option value="${sp.id}" ${mappedShopifyId == sp.id ? 'selected' : ''}>${sp.title}</option>`
                ).join('');
            
            // Get last updated timestamp for this SNKRDUNK product
            const lastUpdated = snkrProduct.last_price_updated 
                ? new Date(snkrProduct.last_price_updated).toLocaleString()
                : '—';
            
            row.innerHTML = `
                <td style="max-width: 300px;">
                    <strong>${snkrProduct.nameEn || snkrProduct.name}</strong>
                </td>
                <td>¥${snkrProduct.minPriceJpy ? snkrProduct.minPriceJpy.toLocaleString() : '-'}</td>
                <td style="font-size: 0.85rem; color: #666;">
                    ${lastUpdated}
                </td>
                <td style="text-align: center; font-size: 1.5rem;">→</td>
                <td>
                    <select class="form-input" style="min-width: 300px;" 
                            onchange="updateAndSaveMapping(${snkrProduct.id}, this.value)">
                        ${selectOptions}
                    </select>
                </td>
            `;
            tbody.appendChild(row);
        } catch (error) {
            console.error('Error rendering mapping row:', error, snkrProduct);
        }
    });
}

async function updateAndSaveMapping(snkrdunkId, shopifyId) {
    if (!shopifyId) {
        window.productMappings[snkrdunkId] = null;
        return;
    }
    
    window.productMappings[snkrdunkId] = shopifyId;
    
    // Auto-save immediately
    const snkrProduct = window.snkrdunkProducts.find(p => p.id == snkrdunkId);
    const shopifyProduct = window.shopifyProducts.find(p => p.id == shopifyId);
    
    if (!snkrProduct || !shopifyProduct) return;
    
    try {
        await fetch('/api/v1/mappings/snkrdunk', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                snkrdunk_key: snkrProduct.id.toString(),
                handle: shopifyProduct.handle,
                product_shopify_id: shopifyProduct.shopify_id,
                notes: `Manually mapped: ${snkrProduct.nameEn} → ${shopifyProduct.title}`
            })
        });
        // Silent save - no alert to avoid spam
    } catch (error) {
        console.error('Failed to save mapping:', error);
    }
}

function calculateSimilarity(str1, str2) {
    // Simple similarity check - normalize and compare
    const normalize = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '');
    const s1 = normalize(str1);
    const s2 = normalize(str2);
    
    // Check if one contains the other
    if (s1.includes(s2) || s2.includes(s1)) return 0.8;
    
    // Check word overlap
    const words1 = str1.toLowerCase().split(/\s+/);
    const words2 = str2.toLowerCase().split(/\s+/);
    const commonWords = words1.filter(w => words2.includes(w)).length;
    
    return commonWords / Math.max(words1.length, words2.length);
}

async function autoMapProducts() {
    if (!window.snkrdunkProducts || !window.shopifyProducts) {
        showAlert('Please load products first', 'error');
        return;
    }
    
    let mappedCount = 0;
    const mappingsToSave = [];
    
    window.snkrdunkProducts.forEach(snkrProduct => {
        const snkrName = (snkrProduct.nameEn || snkrProduct.name || '').trim();
        if (!snkrName) return;
        
        let bestMatch = null;
        let bestScore = 0;
        
        window.shopifyProducts.forEach(shopifyProduct => {
            const shopifyName = (shopifyProduct.title || '').trim();
            const score = calculateSimilarity(snkrName, shopifyName);
            
            if (score > bestScore && score > 0.5) {
                bestScore = score;
                bestMatch = shopifyProduct;
            }
        });
        
        if (bestMatch) {
            window.productMappings[snkrProduct.id] = bestMatch.id;
            mappingsToSave.push({
                snkrdunk: snkrProduct,
                shopify: bestMatch,
                score: bestScore
            });
            mappedCount++;
        }
    });
    
    // Re-render table with new mappings
    renderSnkrdunkProductsTable();
    
    // Auto-save all mappings
    if (mappingsToSave.length > 0) {
        try {
            for (const mapping of mappingsToSave) {
                await fetch('/api/v1/mappings/snkrdunk', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        snkrdunk_key: mapping.snkrdunk.id.toString(),
                        handle: mapping.shopify.handle,
                        product_shopify_id: mapping.shopify.shopify_id,
                        notes: `Auto-mapped (${Math.round(mapping.score * 100)}% match): ${mapping.snkrdunk.nameEn} → ${mapping.shopify.title}`
                    })
                });
            }
            showAlert(`Auto-mapped and saved ${mappedCount} products`, 'success');
        } catch (error) {
            showAlert(`Mapped ${mappedCount} products but some saves failed`, 'warning');
        }
    } else {
        showAlert('No matches found', 'warning');
    }
}

// ============================================================================
// Column Visibility Toggle
// ============================================================================

function toggleColumn(columnName) {
    const checkbox = document.getElementById(`col-${columnName}`);
    const isVisible = checkbox.checked;
    const cells = document.querySelectorAll(`.col-${columnName}`);
    
    cells.forEach(cell => {
        cell.style.display = isVisible ? '' : 'none';
    });
}

// ============================================================================
// Translation Editing
// ============================================================================

function editTranslation(productId) {
    const row = document.querySelector(`#snkrdunk-products-tbody tr[data-product-id="${productId}"]`);
    if (!row) return;
    
    const nameJa = row.dataset.nameJa;
    const translationCell = row.querySelector('.col-name-en');
    const currentTranslation = translationCell.querySelector('.translation-text').textContent.trim();
    
    // Create inline editor
    const input = document.createElement('input');
    input.type = 'text';
    input.value = currentTranslation === 'Double-click to edit' ? '' : currentTranslation;
    input.className = 'form-input';
    input.style.width = '100%';
    input.style.minWidth = '300px';
    
    // Save on blur or Enter
    const saveTranslation = async () => {
        const newTranslation = input.value.trim();
        if (newTranslation === currentTranslation) {
            translationCell.innerHTML = `<span class="translation-text">${currentTranslation}</span>`;
            return;
        }
        
        try {
            const response = await fetch('/api/v1/translations/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    japanese_text: nameJa,
                    english_text: newTranslation
                })
            });
            
            if (!response.ok) throw new Error('Failed to save translation');
            
            translationCell.innerHTML = `<span class="translation-text">${newTranslation || '<em style="color:var(--text-secondary)">Double-click to edit</em>'}</span>`;
            showAlert('Translation saved', 'success');
        } catch (error) {
            showAlert('Failed to save translation: ' + error.message, 'error');
            translationCell.innerHTML = `<span class="translation-text">${currentTranslation}</span>`;
        }
    };
    
    input.addEventListener('blur', saveTranslation);
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            input.blur();
        } else if (e.key === 'Escape') {
            translationCell.innerHTML = `<span class="translation-text">${currentTranslation}</span>`;
        }
    });
    
    translationCell.innerHTML = '';
    translationCell.appendChild(input);
    input.focus();
    input.select();
}

async function saveApiKeys(event) {
    event.preventDefault();
    
    const shopifyShop = document.getElementById('shopify-shop').value.trim();
    const shopifyToken = document.getElementById('shopify-token').value.trim();
    const googleApiKey = document.getElementById('google-api-key').value.trim();
    
    if (!shopifyShop || !shopifyToken) {
        showAlert('Shopify shop and token are required', 'error');
        return;
    }
    
    const data = {
        shopify_shop: shopifyShop,
        shopify_token: shopifyToken
    };
    
    if (googleApiKey) {
        data.google_translate_api_key = googleApiKey;
    }
    
    try {
        const response = await fetch(`${API_BASE}/settings/api-keys/update`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) throw new Error('Failed to save API keys');
        
        const result = await response.json();
        showAlert('API keys saved successfully! ✓', 'success');
        
        // Clear password fields
        document.getElementById('shopify-token').value = '';
        document.getElementById('google-api-key').value = '';
        
        // Reload settings
        await loadSettings();
        
    } catch (error) {
        showAlert('Failed to save API keys: ' + error.message, 'error');
    }
}


// ============================================================================
// COMPETITOR FUNCTIONS
// ============================================================================

async function loadCompetitors() {
    try {
        await new Promise(resolve => setTimeout(resolve, 100));
        
        const category = document.getElementById('competitor-category-filter')?.value || '';
        const website = document.getElementById('competitor-website-filter')?.value || '';
        const brand = document.getElementById('competitor-brand-filter')?.value || '';
        
        const params = new URLSearchParams();
        if (category) params.append('category', category);
        if (website) params.append('website', website);
        if (brand) params.append('brand', brand);
        params.append('limit', '200');
        
        const response = await fetch(`${API_BASE}/competitors/?${params.toString()}`);
        if (!response.ok) throw new Error('Failed to load competitors');
        
        const products = await response.json();
        window.competitorProducts = products;
        competitorSortedData = [...products];

        // Load SNKRDUNK options once for the dropdowns
        let snkrdunkOptions = [];
        try {
            const snkRes = await fetch(`${API_BASE}/mappings/snkrdunk?limit=1000`);
            if (snkRes.ok) {
                snkrdunkOptions = await snkRes.json();
            }
        } catch (e) {
            console.error('Failed to load SNKRDUNK options:', e);
        }

        // Load existing mappings
        let mappedCompetitors = {};
        try {
            const mapRes = await fetch(`${API_BASE}/competitors/mapped`);
            if (mapRes.ok) {
                const mappedList = await mapRes.json();
                // Flatten the grouped structure to map competitor IDs
                mappedList.forEach(group => {
                    group.competitors.forEach(comp => {
                        mappedCompetitors[comp.competitor_product_id] = comp;
                    });
                });
            }
        } catch (e) {
            console.error('Failed to load mappings:', e);
        }

        // Store mapping data globally for sorting
        window.mappedCompetitorsData = mappedCompetitors;

        const table = document.getElementById('competitors-table');
        const headers = ['Website', 'Product Name', 'Category', 'Price (NOK)', 'Stock', 'Last Updated', 'Price Last Changed', 'Mapping', 'Actions'];
        const thead = table?.querySelector('thead');
        
        if (!table || !thead) {
            // Create table if it doesn't exist
            let newTable = document.createElement('table');
            newTable.id = 'competitors-table';
            newTable.className = 'data-table';
            
            const newThead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            headers.forEach((header, idx) => {
                const th = document.createElement('th');
                th.textContent = header;
                // Make sortable columns have cursor pointer
                if (['Price (NOK)', 'Mapping'].includes(header)) {
                    th.style.cursor = 'pointer';
                    th.style.userSelect = 'none';
                    th.onclick = () => sortCompetitorTable(header);
                    th.title = 'Click to sort';
                }
                headerRow.appendChild(th);
            });
            newThead.appendChild(headerRow);
            newTable.appendChild(newThead);
            
            const tbody = document.createElement('tbody');
            newTable.appendChild(tbody);
            
            const container = document.querySelector('#competitors-table')?.parentElement;
            if (container) {
                container.querySelector('#competitors-table')?.remove();
                container.appendChild(newTable);
            }
        } else {
            // Update header click handlers
            const headerCells = thead.querySelectorAll('th');
            headerCells.forEach((th, idx) => {
                const header = th.textContent;
                if (['Price (NOK)', 'Mapping'].includes(header)) {
                    th.style.cursor = 'pointer';
                    th.style.userSelect = 'none';
                    th.onclick = () => sortCompetitorTable(header);
                    th.title = 'Click to sort';
                } else {
                    th.style.cursor = 'auto';
                    th.onclick = null;
                }
            });
        }

        renderCompetitorTable(competitorSortedData, snkrdunkOptions, mappedCompetitors);
        
        // Restore sort state from localStorage if available
        const savedSortState = localStorage.getItem('competitorSortState');
        if (savedSortState) {
            try {
                const { column, direction } = JSON.parse(savedSortState);
                competitorSortColumn = column;
                competitorSortDirection = direction;
                // Re-sort with saved state (without toggling)
                competitorSortedData = [...products].sort((a, b) => {
                    let aVal, bVal;
                    
                    if (column === 'Price (NOK)') {
                        aVal = a.price_ore ? a.price_ore / 100 : Infinity;
                        bVal = b.price_ore ? b.price_ore / 100 : Infinity;
                        const result = aVal - bVal;
                        return direction === 'asc' ? result : -result;
                    } else if (column === 'Mapping') {
                        const aIsMapped = mappedCompetitors && mappedCompetitors[a.id] ? 1 : 0;
                        const bIsMapped = mappedCompetitors && mappedCompetitors[b.id] ? 1 : 0;
                        const result = aIsMapped - bIsMapped;
                        if (result === 0) return 0;
                        return direction === 'asc' ? -result : result;
                    }
                    return 0;
                });
                renderCompetitorTable(competitorSortedData, snkrdunkOptions, mappedCompetitors);
                updateCompetitorSortIndicators();
            } catch (e) {
                console.error('Failed to restore sort state:', e);
            }
        }
        
    } catch (error) {
        console.error('Error loading competitors:', error);
        const tbody = ensureTableBody('competitors-table', [
            'Website', 'Product Name', 'Category', 'Price (NOK)', 'Stock', 'Last Updated', 'Price Last Changed', 'Mapping', 'Actions'
        ], 'data-table');
        if (tbody) {
            setTableBodyMessage(tbody, 9, `Error: ${error.message}`, true);
        }
    }
}

function sortCompetitorTable(columnName) {
    // Toggle sort direction if same column clicked, otherwise start with ascending
    if (competitorSortColumn === columnName) {
        competitorSortDirection = competitorSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        competitorSortColumn = columnName;
        competitorSortDirection = 'asc';
    }
    
    // Save sort state to localStorage
    localStorage.setItem('competitorSortState', JSON.stringify({
        column: competitorSortColumn,
        direction: competitorSortDirection
    }));
    
    // Sort the data
    competitorSortedData = [...competitorSortedData].sort((a, b) => {
        let aVal, bVal;
        
        if (columnName === 'Price (NOK)') {
            aVal = a.price_ore ? a.price_ore / 100 : Infinity;
            bVal = b.price_ore ? b.price_ore / 100 : Infinity;
            const result = aVal - bVal;
            return competitorSortDirection === 'asc' ? result : -result;
        } else if (columnName === 'Mapping') {
            // Sort by mapped vs unmapped (mapped first if ascending)
            const aIsMapped = window.mappedCompetitorsData && window.mappedCompetitorsData[a.id] ? 1 : 0;
            const bIsMapped = window.mappedCompetitorsData && window.mappedCompetitorsData[b.id] ? 1 : 0;
            const result = aIsMapped - bIsMapped;
            if (result === 0) return 0; // If same mapping status, maintain order
            return competitorSortDirection === 'asc' ? -result : result; // Mapped products first in ascending
        }
        
        return 0;
    });
    
    // Re-render table
    renderCompetitorTable(competitorSortedData, [], window.mappedCompetitorsData || {});
    
    // Update header visual indicators
    updateCompetitorSortIndicators();
}

function updateCompetitorSortIndicators() {
    const thead = document.querySelector('#competitors-table thead');
    if (thead) {
        const headers = thead.querySelectorAll('th');
        headers.forEach(th => {
            th.textContent = th.textContent.replace(' ↑', '').replace(' ↓', '');
        });
        
        headers.forEach((th, idx) => {
            if (th.textContent === competitorSortColumn) {
                th.textContent += competitorSortDirection === 'asc' ? ' ↑' : ' ↓';
            }
        });
    }
}

function renderCompetitorTable(products, snkrdunkOptions, mappedCompetitors) {
    const tbody = document.querySelector('#competitors-table tbody');
    if (!tbody) return;
    
    if (products.length === 0) {
        setTableBodyMessage(tbody, 9, 'No competitor data yet. Run a scan to populate data.');
        return;
    }
    
    tbody.innerHTML = '';
    products.forEach(product => {
        const row = document.createElement('tr');
        const linkHtml = product.product_link
            ? `<a href="${product.product_link}" target="_blank" rel="noopener noreferrer">View</a>`
            : '';
        const displayName = formatCompetitorName(product.raw_name);
        
        let mappingHtml = '';
        const existingMapping = mappedCompetitors[product.id];
        
        if (existingMapping) {
            // Show existing mapping with unmap option
            mappingHtml = `
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span style="font-weight: 600; color: green;">✓ Mapped</span>
                </div>
            `;
        } else {
            // Show unmapped indicator
            mappingHtml = `
                <div style="display: flex; gap: 0.5rem; align-items: center;">
                    <span style="font-weight: 600; color: #999;">— Unmapped</span>
                </div>
            `;
        }
        
        const lastUpdated = product.last_updated 
            ? new Date(product.last_updated).toLocaleDateString('no-NO', {year: '2-digit', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'})
            : '—';
        const priceLastChanged = product.price_last_changed 
            ? new Date(product.price_last_changed).toLocaleDateString('no-NO', {year: '2-digit', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'})
            : '—';
        
        row.innerHTML = `
            <td><strong>${product.website}</strong></td>
            <td>
                <div>${displayName} ${linkHtml}</div>
                <div style="font-size: 0.75rem; color: var(--text-secondary);">${product.normalized_name || '—'}</div>
            </td>
            <td>${product.category || '—'}</td>
            <td>${product.price_ore ? (product.price_ore / 100).toFixed(2) + ' kr' : '—'}</td>
            <td>${product.stock_status || 'Unknown'}</td>
            <td style="font-size: 0.85rem; color: #666;">${lastUpdated}</td>
            <td style="font-size: 0.85rem; color: #666;">${priceLastChanged}</td>
            <td>${mappingHtml}</td>
            <td>
                ${existingMapping ? `<button class="btn btn-sm btn-secondary" onclick="unmapCompetitor(${existingMapping.mapping_id})">Unmap</button>` : `<button class="btn btn-sm btn-primary" onclick="showMapDialog(${product.id})">Map</button>`}
            </td>
        `;
        tbody.appendChild(row);
    });
}

async function unmapCompetitor(competitorId) {
    if (!confirm('Remove this mapping?')) return;
    
    try {
        // Save current state
        const scrollTop = window.scrollY;
        
        const response = await fetch(`${API_BASE}/competitors/mappings/${competitorId}`, {
            method: 'DELETE'
        });
        
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }
        
        showAlert('Mapping removed successfully ✓', 'success');
        
        // Reload data (which will restore sort from localStorage automatically)
        await loadCompetitors();
        
        // Restore scroll position
        window.scrollTo(0, scrollTop);
    } catch (error) {
        console.error('Unmap error:', error);
        showAlert('Error: ' + error.message, 'error');
    }
}

async function linkCompetitorToSnkrdunk(competitorId, selectElementId) {
    const select = document.getElementById(selectElementId);
    if (!select || !select.value) {
        showAlert('Please select a product first', 'error');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/competitors/map-to-snkrdunk?competitor_id=${competitorId}&snkrdunk_mapping_id=${select.value}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.detail || `HTTP ${response.status}`);
        }
        showAlert('Mapping created! ✓', 'success');
        loadCompetitors();
    } catch (error) {
        console.error('Mapping error details:', error);
        showAlert('Error: ' + error.message, 'error');
    }
}

async function showMapDialog(competitorProductId) {
    try {
        // Get all Shopify products to choose from
        const response = await fetch(`${API_BASE}/shopify/products?limit=500`);
        if (!response.ok) throw new Error('Failed to load Shopify products');
        
        const shopifyProducts = await response.json();
        
        if (shopifyProducts.length === 0) {
            showAlert('No Shopify products available to map to', 'error');
            return;
        }
        
        // Create a modal dialog
        const modalId = 'map-dialog-' + Date.now();
        const modalHtml = `
            <div id="${modalId}" style="
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 1000;
            ">
                <div style="
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    max-width: 500px;
                    width: 90%;
                    max-height: 70vh;
                    overflow-y: auto;
                ">
                    <h2 style="margin-top: 0;">Map to Shopify Product</h2>
                    <p style="color: #666; font-size: 0.9rem;">Select a Shopify product to map this competitor product to:</p>
                    
                    <input type="text" id="shopify-search-${modalId}" placeholder="Search Shopify products..." style="
                        width: 100%;
                        padding: 0.5rem;
                        margin-bottom: 1rem;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        font-size: 0.9rem;
                    ">
                    
                    <div id="shopify-products-list-${modalId}" style="
                        max-height: 400px;
                        overflow-y: auto;
                        border: 1px solid #eee;
                        border-radius: 4px;
                    "></div>
                    
                    <div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
                        <button class="btn btn-primary" id="confirm-map-${modalId}" style="flex: 1;">Map Selected</button>
                        <button class="btn btn-secondary" onclick="document.getElementById('${modalId}').remove();" style="flex: 1;">Cancel</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        let selectedProductId = null;
        const searchInput = document.getElementById('shopify-search-' + modalId);
        const productsList = document.getElementById('shopify-products-list-' + modalId);
        const confirmBtn = document.getElementById('confirm-map-' + modalId);
        
        // Render product list with search
        function renderProducts(searchTerm = '') {
            const filtered = shopifyProducts.filter(p => 
                p.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
                p.handle.toLowerCase().includes(searchTerm.toLowerCase())
            );
            
            productsList.innerHTML = filtered.map(product => `
                <div style="
                    padding: 0.75rem;
                    border-bottom: 1px solid #eee;
                    cursor: pointer;
                    background: ${selectedProductId === product.id ? '#e3f2fd' : 'white'};
                    transition: background 0.2s;
                " onclick="selectShopifyProduct(${product.id}, '${modalId}')" class="shopify-product-item">
                    <div style="font-weight: 500;">${product.title}</div>
                    <div style="font-size: 0.75rem; color: #999;">${product.handle}</div>
                </div>
            `).join('');
        }
        
        window.selectShopifyProduct = (productId, mId) => {
            selectedProductId = productId;
            renderProducts(searchInput.value);
        };
        
        searchInput.addEventListener('input', (e) => {
            renderProducts(e.target.value);
        });
        
        confirmBtn.addEventListener('click', async () => {
            if (!selectedProductId) {
                showAlert('Please select a Shopify product', 'error');
                return;
            }
            
            try {
                const mapResponse = await fetch(`${API_BASE}/competitors/map-to-shopify?competitor_id=${competitorProductId}&shopify_product_id=${selectedProductId}`, {
                    method: 'POST'
                });
                
                if (!mapResponse.ok) {
                    const errorData = await mapResponse.json();
                    throw new Error(errorData.detail || 'Mapping failed');
                }
                
                showAlert('Product mapped successfully! ✓', 'success');
                document.getElementById(modalId).remove();
                await loadCompetitors();
                
            } catch (error) {
                console.error('Manual map error:', error);
                showAlert('Error: ' + error.message, 'error');
            }
        });
        
        // Initial render
        renderProducts();
        
    } catch (error) {
        console.error('Map dialog error:', error);
        showAlert('Error: ' + error.message, 'error');
    }
}

function filterCompetitorProducts() {
    loadCompetitors();
}

async function autoMapCompetitors() {
    const btn = document.getElementById('auto-map-btn');
    const originalText = btn.textContent;
    
    btn.disabled = true;
    btn.textContent = '🔄 Mapping...';
    
    try {
        const response = await fetch(`${API_BASE}/competitors/auto-map`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Auto-map failed');
        }
        
        const result = await response.json();
        
        showAlert(
            `✅ Auto-Mapping Complete!\n\n` +
            `Total unmapped: ${result.total_unmapped}\n` +
            `Mapped: ${result.mapped}\n` +
            `Failed/No match: ${result.failed}`,
            'success'
        );
        
        // Reload competitors table to reflect new mappings
        await loadCompetitors();
        
    } catch (error) {
        console.error('Auto-map error:', error);
        showAlert(`❌ Auto-Mapping Failed: ${error.message}`, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

function formatCompetitorName(name) {
    if (!name) return '—';
    let s = String(name).trim();

    // Remove language markers (e.g. Kinesisk, Japansk)
    s = s.replace(/\b(kinesisk|japansk|engelsk|norsk|tysk|fransk|italiensk|spansk|koreansk|chinese|japanese|english|norwegian|german|french|italian|spanish|korean)\b/gi, '');

    // Remove parenthetical tags like (Sealed)
    s = s.replace(/\([^)]*\)/g, '');

    // Remove redundant Pokemon tokens
    s = s.replace(/\bpok[eé]mon\b/gi, '');

    // Normalize BOKS -> Box and common Norwegian variants
    s = s.replace(/\bbooster\s*boks\b/gi, 'Booster Box');
    s = s.replace(/\bbokser\b/gi, 'Boxes');
    s = s.replace(/\bboks\b/gi, 'Box');

    // Collapse spaces
    s = s.replace(/\s+/g, ' ').trim();

    // Title case
    s = s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

    // Preserve common acronyms
    const acronyms = ['EX', 'GX', 'V', 'VMAX', 'VSTAR', 'V-UNION', 'SR', 'SSR', 'HR', 'UR', 'AR', 'SAR', 'JP', 'EN'];
    acronyms.forEach(token => {
        const re = new RegExp(`\\b${token.replace('-', '\\-')}\\b`, 'gi');
        s = s.replace(re, token);
    });

    return s;
}

async function runCompetitorScraper(website) {
    showAlert(`Starting scan of ${website}...`, 'info');
    showCompetitorScanStatus(true, `Scanning ${website}...`);
    
    try {
        const response = await fetch(`${API_BASE}/competitors/scrape/${website}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Scraper failed');
        }
        
        const result = await response.json();
        showCompetitorScanStatus(false);
        showAlert(`✓ ${website} scan completed! Scan Log ID: ${result.log_id}`, 'success');
        
        // Reload competitor data
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Show scan logs panel
        showScanLogs();
        loadCompetitors();
        
    } catch (error) {
        showCompetitorScanStatus(false);
        showAlert(`Error scanning ${website}: ${error.message}`, 'error');
    }
}

async function runAllCompetitorScrapers() {
    showAlert('Starting full competitor scan (all sites)...', 'info');
    showCompetitorScanStatus(true, 'Scanning all sites...');
    
    try {
        const response = await fetch(`${API_BASE}/competitors/scrape-all`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Scan failed');
        }
        
        const result = await response.json();
        
        // Show summary
        const details = Object.entries(result.results)
            .map(([site, res]) => `${site}: ${res.status}`)
            .join(', ');
        
        showCompetitorScanStatus(false);
        showAlert(`✓ Full scan completed! ${details}. View Scan Logs for details.`, 'success');
        
        // Reload competitor data after a delay to let database settle
        await new Promise(resolve => setTimeout(resolve, 2000));
        
        // Show scan logs panel
        setTimeout(() => {
            showScanLogs();
        }, 500);
        
        try {
            await loadCompetitors();
        } catch (e) {
            console.warn('Failed to reload competitors table (data is still saved):', e);
            // Don't show error - the scan was successful, just the table reload failed
        }
        
    } catch (error) {
        showCompetitorScanStatus(false);
        showAlert(`Error during scan: ${error.message}`, 'error');
    }
}

async function reprocessCompetitorProducts() {
    showAlert('Normalizing competitor products...', 'info');
    showCompetitorScanStatus(true, 'Normalizing & filtering non-Pokémon products...');

    try {
        const response = await fetch(`${API_BASE}/competitors/reprocess?remove_non_pokemon=true`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Reprocess failed');
        }

        const result = await response.json();
        showCompetitorScanStatus(false);
        const removedText = result.removed ? `, removed ${result.removed}` : '';
        showAlert(`✓ Normalized ${result.updated} of ${result.total} products${removedText}`, 'success');

        await new Promise(resolve => setTimeout(resolve, 500));
        loadCompetitors();
    } catch (error) {
        showCompetitorScanStatus(false);
        showAlert(`Error normalizing products: ${error.message}`, 'error');
    }
}

function showCompetitorScanStatus(show, text = '') {
    const statusDiv = document.getElementById('competitor-scan-status');
    if (!statusDiv) return;
    
    if (show) {
        statusDiv.style.display = 'block';
        document.getElementById('scan-status-text').textContent = text;
        document.getElementById('scan-status-detail').textContent = 'This may take several minutes...';
    } else {
        statusDiv.style.display = 'none';
    }
}

async function loadUnmappedCompetitors() {
    try {
        const response = await fetch(`${API_BASE}/competitors/unmapped?limit=50`);
        if (!response.ok) throw new Error('Failed to load unmapped competitors');
        
        const unmapped = await response.json();
        
        if (!unmapped || unmapped.length === 0) {
            showAlert('All competitors are mapped! ✓', 'success');
            return;
        }
        
        const mappingSection = document.getElementById('competitors-mapping-section');
        if (!mappingSection) return;
        
        mappingSection.innerHTML = `
            <div style="overflow-x: auto;">
                <table style="width: 100%; font-size: 0.875rem;">
                    <thead>
                        <tr style="border-bottom: 2px solid var(--border-color);">
                            <th style="padding: 0.5rem; text-align: left;">Competitor Product</th>
                            <th style="padding: 0.5rem; text-align: left;">Suggested Shopify</th>
                            <th style="padding: 0.5rem; text-align: left;">Suggested SNKRDUNK</th>
                            <th style="padding: 0.5rem; text-align: center;">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${unmapped.map(item => `
                            <tr style="border-bottom: 1px solid var(--border-color);">
                                <td style="padding: 0.5rem;">
                                    <div><strong>${item.competitor_name}</strong></div>
                                    <div style="font-size: 0.75rem; color: var(--text-secondary);">${item.website || '—'}</div>
                                </td>
                                <td style="padding: 0.5rem;">
                                    ${item.suggested_shopify_match ? `
                                        <div><strong>${item.suggested_shopify_match.title}</strong></div>
                                        <div style="font-size: 0.75rem; color: var(--text-secondary);">ID: ${item.suggested_shopify_match.id}</div>
                                    ` : '<span style="color: var(--text-secondary);">No match</span>'}
                                </td>
                                <td style="padding: 0.5rem;">
                                    ${item.suggested_snkrdunk_match ? `
                                        <div><strong>${item.suggested_snkrdunk_match.name}</strong></div>
                                        <div style="font-size: 0.75rem; color: var(--text-secondary);">ID: ${item.suggested_snkrdunk_match.id}</div>
                                    ` : '<span style="color: var(--text-secondary);">No match</span>'}
                                </td>
                                <td style="padding: 0.5rem; text-align: center;">
                                    <div class="flex gap-1" style="justify-content: center;">
                                        ${item.suggested_shopify_match ? `<button class="btn btn-sm btn-primary" onclick="quickMapCompetitorToShopify(${item.competitor_id}, ${item.suggested_shopify_match.id})">Map Shopify</button>` : ''}
                                        ${item.suggested_snkrdunk_match ? `<button class="btn btn-sm btn-secondary" onclick="quickMapCompetitorToSnkrdunk(${item.competitor_id}, ${item.suggested_snkrdunk_match.id})">Map SNKRDUNK</button>` : ''}
                                    </div>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
        
    } catch (error) {
        showAlert('Error loading unmapped competitors: ' + error.message, 'error');
    }
}

async function selectCompetitorForMapping(competitorId) {
    console.log('=== selectCompetitorForMapping START ===');
    console.log('competitorId:', competitorId);
    
    const competitor = (window.competitorProducts || []).find(p => p.id === competitorId);
    if (!competitor) {
        console.error('Competitor not found!');
        showAlert('Competitor product not found. Please refresh the page.', 'error');
        return;
    }

    console.log('Found competitor:', competitor);
    window.selectedCompetitor = competitor;

    // Show modal overlay and container
    const overlay = document.getElementById('competitor-mapping-overlay');
    const container = document.getElementById('competitor-mapping-container');
    const emptyState = document.getElementById('competitor-mapping-empty');
    const panel = document.getElementById('competitor-mapping-panel');
    
    console.log('Elements found:', { overlay: !!overlay, container: !!container, emptyState: !!emptyState, panel: !!panel });
    
    if (overlay) {
        overlay.style.display = 'block';
        console.log('Overlay shown');
    }
    if (container) {
        container.style.display = 'block';
        console.log('Container shown');
    }
    if (emptyState) {
        emptyState.style.display = 'none';
        console.log('Empty state hidden');
    }
    if (panel) {
        panel.style.display = 'block';
        console.log('Panel shown, display:', panel.style.display);
    } else {
        console.error('Panel element not found!');
    }

    const summary = document.getElementById('competitor-selected-summary');
    const priceEl = document.getElementById('competitor-selected-price');
    console.log('Summary and price elements:', { summary: !!summary, priceEl: !!priceEl });
    if (summary) {
        summary.textContent = `${competitor.raw_name || '—'} (${competitor.website})`;
        console.log('Set summary text:', summary.textContent);
    }
    if (priceEl) {
        priceEl.textContent = competitor.price_ore ? `${(competitor.price_ore / 100).toFixed(2)} kr` : '—';
        console.log('Set price text:', priceEl.textContent);
    }

    const comparePanel = document.getElementById('competitor-price-compare');
    if (comparePanel) {
        comparePanel.textContent = 'Select a Shopify product to compare prices.';
    }

    try {
        await Promise.all([
            loadShopifyOptions(),
            loadSnkrdunkOptions()
        ]);
    } catch (error) {
        showAlert('Error loading product options: ' + error.message, 'error');
    }

    const shopifySelect = document.getElementById('competitor-shopify-select');
    if (shopifySelect) {
        shopifySelect.onchange = () => loadCompetitorPriceComparison();
    }
}

function closeMappingPanel() {
    const overlay = document.getElementById('competitor-mapping-overlay');
    const container = document.getElementById('competitor-mapping-container');
    const emptyState = document.getElementById('competitor-mapping-empty');
    const panel = document.getElementById('competitor-mapping-panel');
    
    if (overlay) overlay.style.display = 'none';
    if (container) container.style.display = 'none';
    if (panel) panel.style.display = 'none';
    if (emptyState) emptyState.style.display = 'block';
    
    window.selectedCompetitor = null;
}

async function loadShopifyOptions() {
    const select = document.getElementById('competitor-shopify-select');
    if (!select) return;

    if (!window.shopifyProductOptions) {
        const response = await fetch(`${API_BASE}/shopify/products?limit=500`);
        if (!response.ok) throw new Error('Failed to load Shopify products');
        const products = await response.json();
        window.shopifyProductOptions = products || [];
    }

    select.innerHTML = '<option value="">-- Select Shopify Product --</option>' +
        window.shopifyProductOptions.map(p => `<option value="${p.id}">${p.title}</option>`).join('');
}

async function loadSnkrdunkOptions() {
    const select = document.getElementById('competitor-snkrdunk-select');
    if (!select) return;

    if (!window.snkrdunkMappingOptions) {
        const response = await fetch(`${API_BASE}/mappings/snkrdunk?limit=1000`);
        if (!response.ok) throw new Error('Failed to load SNKRDUNK mappings');
        const mappings = await response.json();
        window.snkrdunkMappingOptions = mappings || [];
    }

    select.innerHTML = '<option value="">-- Select SNKRDUNK Product --</option>' +
        window.snkrdunkMappingOptions.map(m => `<option value="${m.id}">${m.snkrdunk_product_name}</option>`).join('');
}

async function mapSelectedCompetitorToShopify() {
    const competitor = window.selectedCompetitor;
    const select = document.getElementById('competitor-shopify-select');
    if (!competitor || !select || !select.value) {
        showAlert('Select a competitor and Shopify product first', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/competitors/map-to-shopify?competitor_id=${competitor.id}&shopify_product_id=${select.value}`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to map competitor to Shopify');
        showAlert('Mapped competitor to Shopify ✓', 'success');
        closeMappingPanel();
        loadCompetitors();
    } catch (error) {
        showAlert(`Mapping failed: ${error.message}`, 'error');
    }
}

async function mapSelectedCompetitorToSnkrdunk() {
    const competitor = window.selectedCompetitor;
    const select = document.getElementById('competitor-snkrdunk-select');
    if (!competitor || !select || !select.value) {
        showAlert('Select a competitor and SNKRDUNK product first', 'error');
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/competitors/map-to-snkrdunk?competitor_id=${competitor.id}&snkrdunk_mapping_id=${select.value}`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to map competitor to SNKRDUNK');
        showAlert('Mapped competitor to SNKRDUNK ✓', 'success');
        closeMappingPanel();
        loadCompetitors();
    } catch (error) {
        showAlert(`Mapping failed: ${error.message}`, 'error');
    }
}

function closeMappingPanel() {
    const overlay = document.getElementById('competitor-mapping-overlay');
    const container = document.getElementById('competitor-mapping-container');
    const emptyState = document.getElementById('competitor-mapping-empty');
    const panel = document.getElementById('competitor-mapping-panel');
    
    if (overlay) overlay.style.display = 'none';
    if (container) container.style.display = 'none';
    if (panel) panel.style.display = 'none';
    if (emptyState) emptyState.style.display = 'block';
    
    window.selectedCompetitor = null;
}

async function loadCompetitorPriceComparison() {
    const select = document.getElementById('competitor-shopify-select');
    const panel = document.getElementById('competitor-price-compare');
    if (!select || !panel || !select.value) {
        if (panel) panel.textContent = 'Select a Shopify product to compare prices.';
        return;
    }

    try {
        const response = await fetch(`${API_BASE}/competitors/price-comparison/${select.value}`);
        if (!response.ok) throw new Error('Failed to load price comparison');
        const data = await response.json();
        const stats = data.competitor_prices || {};
        panel.innerHTML = `
            <div class="grid-2" style="gap: 1rem;">
                <div><strong>Our Price:</strong> ${data.our_price_nok ?? '—'} NOK</div>
                <div><strong>Position:</strong> ${data.price_position || 'unknown'}</div>
                <div><strong>Avg Competitor:</strong> ${stats.avg_price_nok ?? '—'} NOK</div>
                <div><strong>Range:</strong> ${stats.min_price_nok ?? '—'} - ${stats.max_price_nok ?? '—'} NOK</div>
            </div>
            <div style="margin-top: 0.75rem;">
                <strong>By Website:</strong>
                <div style="margin-top: 0.5rem;">
                    ${(stats.prices_by_website ? Object.entries(stats.prices_by_website) : [])
                        .map(([site, price]) => `<div>${site}: ${price} NOK</div>`)
                        .join('') || 'No competitor prices found.'}
                </div>
            </div>
        `;
    } catch (error) {
        panel.textContent = `Failed to load comparison: ${error.message}`;
    }
}

async function quickMapCompetitorToShopify(competitorId, shopifyProductId) {
    try {
        const response = await fetch(`${API_BASE}/competitors/map-to-shopify?competitor_id=${competitorId}&shopify_product_id=${shopifyProductId}`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to map competitor to Shopify');
        showAlert('Mapped competitor to Shopify ✓', 'success');
    } catch (error) {
        showAlert(`Mapping failed: ${error.message}`, 'error');
    }
}

async function quickMapCompetitorToSnkrdunk(competitorId, snkrdunkMappingId) {
    try {
        const response = await fetch(`${API_BASE}/competitors/map-to-snkrdunk?competitor_id=${competitorId}&snkrdunk_mapping_id=${snkrdunkMappingId}`, {
            method: 'POST'
        });
        if (!response.ok) throw new Error('Failed to map competitor to SNKRDUNK');
        showAlert('Mapped competitor to SNKRDUNK ✓', 'success');
    } catch (error) {
        showAlert(`Mapping failed: ${error.message}`, 'error');
    }
}

async function refreshShopifyPrices() {
    try {
        showLoading('competitor-mappings-table');
        
        // Call backend to fetch latest prices from Shopify and update database
        const response = await fetch(`${API_BASE}/shopify/refresh-all-prices`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) throw new Error('Failed to refresh prices from Shopify');
        
        const result = await response.json();
        
        if (result.updated_count > 0) {
            showAlert(`✓ Shopify prices refreshed! Updated ${result.updated_count} variant prices${result.error_count > 0 ? `, ${result.error_count} errors` : ''}.`, 'success');
            
            // Reload competitor mappings to show updated prices
            setTimeout(() => {
                loadCompetitorMappings();
            }, 500);
        } else {
            showAlert('No variant prices were updated', 'warning');
            hideLoading('competitor-mappings-table');
        }
    } catch (error) {
        console.error('Error refreshing Shopify prices:', error);
        showAlert(`Failed to refresh Shopify prices: ${error.message}`, 'error');
        hideLoading('competitor-mappings-table');
    }
}

async function loadCompetitorMappings() {
    try {
        await new Promise(resolve => setTimeout(resolve, 100));
        
        const response = await fetch(`${API_BASE}/competitors/mapped?limit=500`);
        if (!response.ok) throw new Error('Failed to load competitor mappings');
        
        const mappings = await response.json();
        
        const tbody = ensureTableBody('competitor-mappings-table', [
            'My Shopify Product', 'My Price', 'Competitors (Expandable)', 'Lowest In-Stock', 'Stock Filter', 'Margin vs Lowest', 'Actions'
        ], 'data-table');
        if (!tbody) return;
        
        if (!mappings || mappings.length === 0) {
            setTableBodyMessage(tbody, 5, 'No competitor mappings yet. Map products from the Competitors tab.');
            return;
        }
        
        tbody.innerHTML = '';
        mappings.forEach((productGroup, idx) => {
            const myPrice = productGroup.shopify_variants && productGroup.shopify_variants.length > 0 
                ? parseFloat(productGroup.shopify_variants[0].price) 
                : null;
            
            // Calculate lowest IN-STOCK competitor price only
            const inStockPrices = productGroup.competitors
                .filter(c => {
                    const inStock = c.competitor_stock === 'in_stock' 
                        || c.competitor_stock === 'På lager'
                        || (c.competitor_stock_amount && c.competitor_stock_amount > 0);
                    return inStock && c.competitor_price_ore;
                })
                .map(c => c.competitor_price_ore ? (c.competitor_price_ore / 100) : null)
                .filter(p => p !== null);
            
            const lowestInStockPrice = inStockPrices.length > 0 
                ? Math.min(...inStockPrices)
                : null;
            
            // Check if my price is the cheapest or equal to lowest in-stock
            const isCheapest = myPrice && lowestInStockPrice && myPrice <= lowestInStockPrice;
            
            let marginVsLowest = '—';
            if (myPrice && lowestInStockPrice) {
                const diff = ((myPrice - lowestInStockPrice) / lowestInStockPrice * 100).toFixed(1);
                marginVsLowest = `${diff > 0 ? '+' : ''}${diff}%`;
            }
            
            // Main product row
            const row = document.createElement('tr');
            const expandId = `comp-expand-${idx}`;
            const matchInStockBtnId = `match-instock-btn-${idx}`;
            row.innerHTML = `
                <td style="font-weight: 600;">${productGroup.shopify_product_title || '—'}</td>
                <td style="font-weight: 600; color: ${isCheapest ? 'green' : '#2563eb'}; background: ${isCheapest ? '#e8f5e9' : 'transparent'}; padding: 0.5rem; border-radius: 4px;">${myPrice ? myPrice.toFixed(2) + ' kr' : '—'}</td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="toggleCompetitorExpand('${expandId}')">
                        Show ${productGroup.competitors.length} competitors ▼
                    </button>
                </td>
                <td style="font-weight: 600; color: #2563eb;">${lowestInStockPrice ? lowestInStockPrice.toFixed(2) + ' kr' : '—'}</td>
                <td style="font-size: 0.8rem; color: #666;">In-stock only</td>
                <td style="font-weight: 600; color: ${parseFloat(marginVsLowest) > 20 ? 'green' : parseFloat(marginVsLowest) > 0 ? 'orange' : 'red'}">${marginVsLowest}</td>
                <td>
                    <button class="btn btn-sm btn-primary" id="${matchInStockBtnId}" onclick="matchPriceForProductInStock(this)">
                        Match In-Stock Price
                    </button>
                </td>
            `;
            row.dataset.productGroup = JSON.stringify(productGroup);
            tbody.appendChild(row);
            
            // Hidden expandable row with competitors
            const expandRow = document.createElement('tr');
            expandRow.id = expandId;
            expandRow.style.display = 'none';
            expandRow.innerHTML = `
                <td colspan="6" style="background: #f9f9f9; padding: 1rem;">
                    <div style="margin: 0.5rem 0; font-weight: 600; font-size: 0.9rem;">Competing Products:</div>
                    ${productGroup.competitors.map(c => {
                        const compPrice = c.competitor_price_ore ? (c.competitor_price_ore / 100) : null;
                        let margin = '—';
                        if (myPrice && compPrice) {
                            margin = ((myPrice - compPrice) / compPrice * 100).toFixed(1);
                        }
                        const inStock = c.competitor_stock === 'in_stock' || c.competitor_stock === 'På lager' || (c.competitor_stock_amount && c.competitor_stock_amount > 0);
                        const stockBg = inStock ? '#e8f5e9' : '#ffebee';
                        const stockColor = inStock ? 'green' : 'red';
                        
                        return `
                            <div style="margin: 0.75rem 0; padding: 0.75rem; background: white; border-left: 3px solid ${stockColor}; border-radius: 4px;">
                                <div style="display: flex; justify-content: space-between; align-items: start;">
                                    <div style="flex: 1;">
                                        <div style="font-weight: 600;">${c.competitor_name}</div>
                                        <div style="font-size: 0.85rem; color: #666;">${c.competitor_normalized || '—'}</div>
                                        <div style="font-size: 0.8rem; color: #999; margin-top: 0.25rem;">
                                            <strong>${c.competitor_website}</strong>
                                            ${c.competitor_link ? ` | <a href="${c.competitor_link}" target="_blank" style="color: #2563eb;">View</a>` : ''}
                                        </div>
                                    </div>
                                    <div style="text-align: right; margin-left: 1rem;">
                                        <div style="font-weight: 600; color: #2563eb; font-size: 1.1rem;">${compPrice ? compPrice.toFixed(2) + ' kr' : '—'}</div>
                                        <div style="font-size: 0.85rem; color: ${margin > 0 ? 'green' : 'red'}; margin: 0.25rem 0;">
                                            Margin: ${margin}%
                                        </div>
                                        <div style="background: ${stockBg}; color: ${stockColor}; padding: 0.25rem 0.5rem; border-radius: 3px; font-size: 0.8rem; font-weight: 600; margin-top: 0.25rem;">
                                            ${inStock ? '✓ In Stock' : '✗ Out of Stock'}
                                        </div>
                                        <div style="display: flex; gap: 0.5rem; margin-top: 0.5rem;">
                                            <button class="btn btn-sm btn-primary" onclick="matchMappedCompetitorPrice(${productGroup.shopify_product_id}, ${c.competitor_price_ore}, '${productGroup.shopify_product_title.replace(/'/g, "\\'")}', '${c.competitor_name.replace(/'/g, "\\'")}')" style="background: #2563eb; color: white; padding: 0.25rem 0.75rem; border: none; border-radius: 3px; cursor: pointer; font-size: 0.8rem;">
                                                Match Price
                                            </button>
                                            <button class="btn btn-sm btn-danger" onclick="unmapCompetitorProduct(${c.mapping_id})" style="background: #dc2626; color: white; padding: 0.25rem 0.75rem; border: none; border-radius: 3px; cursor: pointer; font-size: 0.8rem;">
                                                Unmap
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;
                    }).join('')}
                </td>
            `;
            tbody.appendChild(expandRow);
        });
    } catch (error) {
        console.error('Error loading competitor mappings:', error);
        const tbody = ensureTableBody('competitor-mappings-table', [
            'My Shopify Product', 'My Price', 'Competitors', 'Lowest In-Stock', 'Stock Filter', 'Margin vs Lowest', 'Actions'
        ], 'data-table');
        if (tbody) {
            setTableBodyMessage(tbody, 6, `Error: ${error.message}`, true);
        }
    }
}

function toggleCompetitorExpand(expandId) {
    const element = document.getElementById(expandId);
    if (element) {
        element.style.display = element.style.display === 'none' ? 'table-row' : 'none';
    }
}

async function matchMappedCompetitorPrice(shopifyProductId, competitorPriceOre, shopifyProductTitle, competitorName) {
    try {
        const priceKr = (competitorPriceOre / 100);
        const confirmed = confirm(`Match price for "${shopifyProductTitle}" to ${priceKr.toFixed(2)} kr from ${competitorName}?`);
        
        if (!confirmed) return;
        
        showLoading('competitor-mappings-table');
        
        // Get the product/variant info from the mappings
        const mappingsResponse = await fetch(`${API_BASE}/competitors/mapped?limit=500`);
        if (!mappingsResponse.ok) throw new Error('Failed to load mappings');
        
        const mappings = await mappingsResponse.json();
        const productGroup = mappings.find(m => m.shopify_product_id === shopifyProductId);
        
        if (!productGroup || !productGroup.shopify_variants || productGroup.shopify_variants.length === 0) {
            throw new Error('No variant found for this product');
        }
        
        const shopifyVariant = productGroup.shopify_variants[0];
        const variantId = shopifyVariant.id;
        
        // Use direct variant update with logging - simpler and more reliable
        const updateUrl = `${API_BASE}/shopify/variants/${variantId}` +
            `?price=${priceKr}` +
            `&change_type=manual_competitor_match` +
            `&competitor_name=${encodeURIComponent(competitorName)}` +
            `&competitor_price=${priceKr}`;
        
        const response = await fetch(updateUrl, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update variant price');
        }
        
        const result = await response.json();
        console.log(`Price updated. Log ID: ${result.log_id}, Old: ${result.old_price}, New: ${result.price}`);
        
        showAlert(`✓ Price updated to ${priceKr.toFixed(2)} kr from ${competitorName}`, 'success');
        
        // Refresh the page to show updated prices
        setTimeout(() => {
            location.reload();
        }, 1500);
        
    } catch (error) {
        console.error('Match price error:', error);
        showAlert(`❌ Failed to match price: ${error.message}`, 'error');
        hideLoading('competitor-mappings-table');
    }
}


async function showMatchSpecificPriceDialog(shopifyProductId, currentMappingId, shopifyProductTitle) {
    try {
        // Get all competitor products
        const response = await fetch(`${API_BASE}/competitors?limit=1000`);
        if (!response.ok) throw new Error('Failed to load competitor products');
        
        const competitorProducts = await response.json();
        
        if (competitorProducts.length === 0) {
            showAlert('No competitor products available', 'error');
            return;
        }
        
        // Create a modal dialog
        const modalId = 'match-price-dialog-' + Date.now();
        const modalHtml = `
            <div id="${modalId}" style="
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background: rgba(0,0,0,0.5);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 1000;
            ">
                <div style="
                    background: white;
                    padding: 2rem;
                    border-radius: 8px;
                    max-width: 600px;
                    width: 90%;
                    max-height: 80vh;
                    overflow-y: auto;
                ">
                    <h2 style="margin-top: 0;">Match Specific Competitor Price</h2>
                    <p style="color: #666; font-size: 0.9rem; margin-bottom: 1rem;">
                        Select a competitor product to match your price with:<br>
                        <strong>${shopifyProductTitle}</strong>
                    </p>
                    
                    <input type="text" id="competitor-search-${modalId}" placeholder="Search competitor products..." style="
                        width: 100%;
                        padding: 0.5rem;
                        margin-bottom: 1rem;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        font-size: 0.9rem;
                    ">
                    
                    <div id="competitor-products-list-${modalId}" style="
                        max-height: 400px;
                        overflow-y: auto;
                        border: 1px solid #eee;
                        border-radius: 4px;
                    "></div>
                    
                    <div style="display: flex; gap: 1rem; margin-top: 1.5rem;">
                        <button class="btn btn-primary" id="confirm-change-${modalId}" style="flex: 1;">Match This Price</button>
                        <button class="btn btn-secondary" onclick="document.getElementById('${modalId}').remove();" style="flex: 1;">Cancel</button>
                    </div>
                </div>
            </div>
        `;
        
        document.body.insertAdjacentHTML('beforeend', modalHtml);
        
        let selectedCompetitorId = null;
        const searchInput = document.getElementById('competitor-search-' + modalId);
        const productsList = document.getElementById('competitor-products-list-' + modalId);
        const confirmBtn = document.getElementById('confirm-change-' + modalId);
        
        // Render competitor product list with search
        function renderCompetitors(searchTerm = '') {
            const filtered = competitorProducts.filter(p => 
                (p.normalized_name || p.raw_name || '').toLowerCase().includes(searchTerm.toLowerCase()) ||
                (p.website || '').toLowerCase().includes(searchTerm.toLowerCase())
            );
            
            productsList.innerHTML = filtered.map(competitor => {
                const price = competitor.price_ore ? (competitor.price_ore / 100).toFixed(2) : 'N/A';
                const inStock = competitor.stock_status === 'in_stock' || competitor.stock_amount > 0;
                const stockBg = inStock ? '#10b981' : '#ef4444';
                const stockColor = 'white';
                const displayName = competitor.normalized_name || competitor.raw_name || 'Unknown Product';
                
                return `
                    <div style="
                        padding: 0.75rem;
                        border-bottom: 1px solid #eee;
                        cursor: pointer;
                        background: ${selectedCompetitorId === competitor.id ? '#e3f2fd' : 'white'};
                        transition: background 0.2s;
                    " onclick="selectCompetitor(${competitor.id}, '${modalId}')" class="competitor-product-item">
                        <div style="display: flex; justify-content: space-between; align-items: start;">
                            <div style="flex: 1;">
                                <div style="font-weight: 500; margin-bottom: 0.25rem;">${displayName}</div>
                                <div style="font-size: 0.75rem; color: #666; margin-bottom: 0.25rem;">${competitor.website || 'Unknown'}</div>
                                <div style="display: inline-block; background: ${stockBg}; color: ${stockColor}; padding: 0.15rem 0.4rem; border-radius: 3px; font-size: 0.75rem; font-weight: 600;">
                                    ${inStock ? '✓ In Stock' : '✗ Out of Stock'}
                                </div>
                            </div>
                            <div style="text-align: right;">
                                <div style="font-weight: 600; color: #2563eb; font-size: 1rem;">${price} kr</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
            
            if (filtered.length === 0) {
                productsList.innerHTML = '<div style="padding: 2rem; text-align: center; color: #999;">No matching competitor products found</div>';
            }
        }
        
        window.selectCompetitor = (competitorId, mId) => {
            selectedCompetitorId = competitorId;
            renderCompetitors(searchInput.value);
        };
        
        searchInput.addEventListener('input', (e) => {
            renderCompetitors(e.target.value);
        });
        
        confirmBtn.addEventListener('click', async () => {
            if (!selectedCompetitorId) {
                showAlert('Please select a competitor product', 'error');
                return;
            }
            
            try {
                // First unmap the current mapping
                await fetch(`${API_BASE}/competitors/mappings/${currentMappingId}`, {
                    method: 'DELETE',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                // Then create new mapping
                const mapResponse = await fetch(`${API_BASE}/competitors/map-to-shopify?competitor_id=${selectedCompetitorId}&shopify_product_id=${shopifyProductId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });
                
                if (!mapResponse.ok) {
                    const error = await mapResponse.json();
                    throw new Error(error.detail || 'Failed to change match');
                }
                
                document.getElementById(modalId).remove();
                showAlert('✓ Competitor price match updated successfully', 'success');
                await loadCompetitorMappings();
                
            } catch (error) {
                console.error('Change match error:', error);
                showAlert(`❌ Failed to change match: ${error.message}`, 'error');
            }
        });
        
        renderCompetitors();
        
    } catch (error) {
        console.error('Error showing change match dialog:', error);
        showAlert(`❌ Error: ${error.message}`, 'error');
    }
}

async function unmapCompetitorProduct(mappingId) {
    if (!confirm('Are you sure you want to unmap this competitor product?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE}/competitors/mappings/${mappingId}`, {
            method: 'DELETE',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to unmap');
        }
        
        showAlert('✓ Competitor product unmapped', 'success');
        await loadCompetitorMappings();
        
    } catch (error) {
        console.error('Unmap error:', error);
        showAlert(`❌ Unmap failed: ${error.message}`, 'error');
    }
}
// ============================================================================
// PRICE HISTORY FUNCTIONS
// ============================================================================

async function loadMappingsAtDate() {
    const dateInput = document.getElementById('mappings-history-date');
    if (!dateInput || !dateInput.value) {
        showAlert('Please select a date', 'error');
        return;
    }
    
    const selectedDate = dateInput.value;
    
    try {
        showAlert('Loading historical data...', 'info');
        
        // Get all SNKRDUNK prices at selected date
        const response = await fetch(`${API_BASE}/history/snkrdunk-prices/${selectedDate}`);
        if (!response.ok) {
            throw new Error('No data available for this date');
        }
        
        const data = await response.json();
        const snkrdunkHistoricalPrices = {};
        
        if (data.data && data.data.length > 0) {
            data.data.forEach(priceData => {
                snkrdunkHistoricalPrices[priceData.snkrdunk_key] = priceData;
            });
        }
        
        // Update window.snkrdunkProducts with historical prices
        if (window.snkrdunkProducts) {
            window.snkrdunkProducts.forEach(product => {
                if (snkrdunkHistoricalPrices[product.id]) {
                    const historical = snkrdunkHistoricalPrices[product.id];
                    product.minPriceJpy = historical.price_jpy;
                    product.last_price_updated = historical.recorded_at;
                }
            });
            
            renderSnkrdunkProductsTable();
            showAlert(`✓ Showing data from ${selectedDate}`, 'success');
        }
    } catch (error) {
        console.error('History load error:', error);
        showAlert(`❌ Failed to load historical data: ${error.message}`, 'error');
    }
}

function resetMappingsToToday() {
    const dateInput = document.getElementById('mappings-history-date');
    if (dateInput) {
        dateInput.value = '';
    }
    
    // Reload current mappings
    loadTabData('mappings');
}

async function loadSnkrdunkScanHistory() {
    try {
        const response = await fetch(`${API_BASE}/snkrdunk/scan-logs?limit=50`);
        if (!response.ok) {
            console.warn('Failed to load SNKRDUNK scan history');
            return;
        }
        
        const logs = await response.json();
        const select = document.getElementById('snkrdunk-scan-select');
        
        if (!select) {
            console.warn('Dropdown not found');
            return;
        }
        
        // Clear existing options
        select.innerHTML = '';
        
        // Add placeholder
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = '-- Select a previous SNKRDUNK price update --';
        select.appendChild(placeholder);
        
        if (logs.length === 0) {
            console.log('No SNKRDUNK price update scans found');
            const noscansOption = document.createElement('option');
            noscansOption.disabled = true;
            noscansOption.textContent = '(No SNKRDUNK updates yet)';
            select.appendChild(noscansOption);
            return;
        }
        
        // Add options (API returns newest first)
        logs.forEach((scan, index) => {
            const option = document.createElement('option');
            const created = new Date(scan.created_at);
            const dateStr = created.toLocaleDateString('en-US', {month: 'short', day: 'numeric', year: '2-digit'});
            const timeStr = created.toLocaleTimeString('en-US', {hour: '2-digit', minute: '2-digit'});
            
            option.value = scan.id;
            option.textContent = `${dateStr} ${timeStr} (${scan.total_items || 0} items)`;
            select.appendChild(option);
            
            // Auto-select the latest scan (first in list from API)
            if (index === 0) {
                option.style.fontWeight = 'bold';
                option.selected = true;
            }
        });
        
        console.log(`Loaded ${logs.length} SNKRDUNK price updates`);
        
        // Auto-load the most recent scan
        if (logs.length > 0) {
            await loadSnkrdunkScan();
        }
    } catch (error) {
        console.error('Failed to load SNKRDUNK scan history:', error);
    }
}

// Load selected scan from dropdown
async function loadSnkrdunkScan() {
    const select = document.getElementById('snkrdunk-scan-select');
    if (!select) return;
    
    // If no selection or empty, reload current data without scan_log_id
    if (!select.value) {
        try {
            showAlert('Loading current SNKRDUNK data...', 'info');
            const response = await fetch(`${API_BASE}/snkrdunk/products`);
            if (!response.ok) throw new Error('Failed to load products');
            
            const data = await response.json();
            window.snkrdunkProducts = data.items || [];
            renderSnkrdunkProductsTable();
            showAlert('✓ Showing current SNKRDUNK prices', 'success');
        } catch (error) {
            console.error('Error loading current data:', error);
            showAlert('Error loading current data: ' + error.message, 'error');
        }
        return;
    }
    
    try {
        showAlert('Loading historical prices...', 'info');
        
        const logId = select.value;
        
        // Fetch products with scan_log_id to get price changes
        const response = await fetch(`${API_BASE}/snkrdunk/products?scan_log_id=${logId}`);
        if (!response.ok) throw new Error('Failed to load products');
        
        const data = await response.json();
        window.snkrdunkProducts = data.items || [];
        
        // Fetch the scan log details for display
        const scanResponse = await fetch(`${API_BASE}/snkrdunk/scan-logs/${logId}`);
        if (!scanResponse.ok) {
            showAlert('Failed to load scan details', 'error');
            return;
        }
        
        const scan = await scanResponse.json();
        const scanDate = new Date(scan.created_at);
        
        // Fetch historical prices for this specific scan log to update prices
        const historyResponse = await fetch(`${API_BASE}/snkrdunk/price-history?log_id=${logId}&limit=200`);
        
        if (historyResponse.ok) {
            const historyData = await historyResponse.json();
            const historicalPrices = {};
            
            // Build a map of product id -> price data
            if (historyData.items && historyData.items.length > 0) {
                historyData.items.forEach(item => {
                    historicalPrices[item.id] = item;
                });
            }
            
            // Update window.snkrdunkProducts with historical data
            if (window.snkrdunkProducts && window.snkrdunkProducts.length > 0) {
                window.snkrdunkProducts.forEach(product => {
                    const key = product.id.toString();
                    // Always update the timestamp to the selected scan
                    product.last_price_updated = scan.created_at;
                    // Only update price if we have historical data for this product
                    if (historicalPrices[key]) {
                        const hist = historicalPrices[key];
                        product.minPriceJpy = hist.minPriceJpy;
                    }
                });
            }
        }
        
        renderSnkrdunkProductsTable();
        
        const dateStr = scanDate.toLocaleString();
        showAlert(`✓ Showing prices from ${dateStr}`, 'success');
    } catch (error) {
        console.error('Error loading scan:', error);
        showAlert('Error loading scan: ' + error.message, 'error');
    }
}

async function loadAvailableHistoryDates() {
    // Call the new function to populate dropdown
    loadSnkrdunkScanHistory();
}

// ============================================================================
// SNKRDUNK HISTORY NAVIGATION (DEPRECATED - Now using scan history dropdown)
// ============================================================================

// Old functions kept for backwards compatibility but no longer used
let currentSnkrdunkViewDate = null; // null = today

async function loadSnkrdunkAtDate() {
    // This function is deprecated. Use loadSnkrdunkScan() instead.
    console.warn('loadSnkrdunkAtDate is deprecated. Use the scan history dropdown instead.');
}

function resetSnkrdunkToToday() {
    // This function is deprecated
    console.warn('resetSnkrdunkToToday is deprecated. Use the scan history dropdown instead.');
    loadTabData('mappings');
}

function updateSnkrdunkDateDisplay() {
    // This function is deprecated
}

async function prevSnkrdunkDay() {
    // This function is deprecated
    console.warn('prevSnkrdunkDay is deprecated. Use the scan history dropdown instead.');
}

async function nextSnkrdunkDay() {
    // This function is deprecated
    console.warn('nextSnkrdunkDay is deprecated. Use the scan history dropdown instead.');
}

function renderSnkrdunkProductsTable() {
    const snkrdunkTbody = document.getElementById('snkrdunk-products-tbody');
    if (!snkrdunkTbody) return;
    
    snkrdunkTbody.innerHTML = '';
    if (!window.snkrdunkProducts || window.snkrdunkProducts.length === 0) {
        snkrdunkTbody.innerHTML = '<tr><td colspan="9" class="text-center">No products cached</td></tr>';
        return;
    }
    
    window.snkrdunkProducts.forEach(p => {
        const row = snkrdunkTbody.insertRow();
        row.dataset.productId = p.id;
        row.dataset.nameJa = p.name || '';
        
        const lastUpdated = p.last_price_updated 
            ? new Date(p.last_price_updated).toLocaleString()
            : '—';
        
        // Find mapped Shopify product
        const mappedShopifyId = window.productMappings ? window.productMappings[p.id.toString()] : null;
        const mappedShopifyProduct = mappedShopifyId && window.shopifyProducts 
            ? window.shopifyProducts.find(sp => sp.id === mappedShopifyId)
            : null;
        
        const shopifyName = mappedShopifyProduct ? mappedShopifyProduct.title : '(Not mapped)';
        const mappingStyle = mappedShopifyProduct ? 'color: var(--success);' : 'color: var(--warning);';
        
        // Calculate price change from previous scan
        let priceChangeHtml = '<span style="color: #999;">—</span>';
        if (p.price_change !== undefined && p.price_change !== null && p.price_change !== 0) {
            const changeAmount = Math.abs(p.price_change);
            const changeSign = p.price_change > 0 ? '+' : '-';
            const changeColor = p.price_change > 0 ? '#10b981' : '#ef4444'; // green for increase, red for decrease
            priceChangeHtml = `<span style="color: ${changeColor}; font-weight: 600;">${changeSign}¥${changeAmount.toLocaleString()}</span>`;
        }
        
        row.innerHTML = `
            <td style="font-size: 0.85rem; color: #666;">${p.id||'-'}</td>
            <td ondblclick="event.stopPropagation(); editTranslation(${p.id})" style="cursor: pointer;" title="Original: ${p.name||''}">
                <span class="translation-text">${p.nameEn||'<em style="color:var(--text-secondary)">Double-click to edit</em>'}</span>
            </td>
            <td>¥${p.minPriceJpy?p.minPriceJpy.toLocaleString():'-'}</td>
            <td>${priceChangeHtml}</td>
            <td>${p.brand?.name||'-'}</td>
            <td style="font-size: 0.85rem; color: #666;">${lastUpdated}</td>
            <td style="text-align: center; color: #999;">→</td>
            <td style="${mappingStyle} font-weight: 500; cursor: pointer;" onclick="event.stopPropagation(); showMapProductModal(${p.id}, ${JSON.stringify(p).replace(/"/g, '&quot;')})">${shopifyName}</td>
            <td>
                <button class="btn btn-sm btn-secondary" onclick="showSnkrdunkProductDetail(${JSON.stringify(p).replace(/"/g, '&quot;')})">View</button>
            </td>
        `;
    });
}

// ============================================================================
// PRODUCT DETAIL MODAL
// ============================================================================

let currentSnkrdunkCurrentProduct = null;
let currentSnkrdunkCurrentModal = null;
let currentSnkrdunkCurrentPrice = null;

async function matchSnkrdunkCompetitorPrice(competitorPriceOre, competitorName, competitorWebsite) {
    // Use EXACT same logic as matchMappedCompetitorPrice from competitor maps
    if (!currentSnkrdunkCurrentProduct) {
        showAlert('Product information not found', 'error');
        return;
    }
    
    try {
        const priceKr = (competitorPriceOre / 100);
        const displayName = competitorWebsite || competitorName || 'competitor';
        const confirmed = confirm(`Match price to ${priceKr.toFixed(2)} kr from ${displayName}?`);
        
        if (!confirmed) return;
        
        // Find the mapping for this SNKRDUNK product
        const mappingsResp = await fetch(`${API_BASE}/mappings/snkrdunk?limit=100`);
        if (!mappingsResp.ok) throw new Error('Failed to fetch mappings');
        const allMappings = await mappingsResp.json();
        const productMapping = allMappings.find(m => m.snkrdunk_key === currentSnkrdunkCurrentProduct.id.toString());
        
        if (!productMapping || !productMapping.handle) {
            showAlert('Product mapping not found', 'error');
            return;
        }
        
        // Get competitor grouping to find the database product ID and variant
        const competitorResp = await fetch(`${API_BASE}/competitors/mapped?limit=1000`);
        if (!competitorResp.ok) throw new Error('Failed to fetch competitors');
        const competitorGroupings = await competitorResp.json();
        
        const productGrouping = competitorGroupings.find(g => g.shopify_product_handle === productMapping.handle);
        
        if (!productGrouping || !productGrouping.shopify_variants || productGrouping.shopify_variants.length === 0) {
            showAlert('No variant found for this product', 'error');
            return;
        }
        
        const shopifyVariant = productGrouping.shopify_variants[0];
        const variantId = shopifyVariant.id;
        
        // Use direct variant update with logging - EXACT same as competitor maps
        const updateUrl = `${API_BASE}/shopify/variants/${variantId}` +
            `?price=${priceKr}` +
            `&change_type=manual_competitor_match` +
            `&competitor_name=${encodeURIComponent(displayName)}` +
            `&competitor_price=${priceKr}`;
        
        const response = await fetch(updateUrl, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to update variant price');
        }
        
        const result = await response.json();
        console.log(`Price updated. Log ID: ${result.log_id}, Old: ${result.old_price}, New: ${result.price}`);
        
        showAlert(`✓ Price updated to ${priceKr.toFixed(2)} kr from ${displayName}`, 'success');
        
        // Close modal and refresh
        setTimeout(() => {
            if (currentSnkrdunkCurrentModal) {
                currentSnkrdunkCurrentModal.remove();
            }
            location.reload();
        }, 1500);
        
    } catch (error) {
        console.error('Match price error:', error);
        showAlert(`❌ Failed to match price: ${error.message}`, 'error');
    }
}

async function matchCompetitorPrice(competitorPriceOre) {
    if (!currentSnkrdunkCurrentProduct) {
        showAlert('error', 'Product information not found');
        return;
    }
    
    // Convert competitor price from øre to NOK
    const competitorPriceNOK = competitorPriceOre ? (competitorPriceOre / 100) : 0;
    
    if (competitorPriceNOK <= 0) {
        showAlert('error', 'Invalid competitor price');
        return;
    }
    
    if (confirm(`Update your price from kr ${currentSnkrdunkCurrentPrice.toFixed(2)} to kr ${competitorPriceNOK.toFixed(2)}?`)) {
        try {
            showLoading('snkrdunk-products-table'); // Show loading for any visible table
            
            // Find the mapping for this product
            const mappingsResp = await fetch(`${API_BASE}/mappings/snkrdunk?limit=100`);
            if (!mappingsResp.ok) throw new Error('Failed to fetch mappings');
            const allMappings = await mappingsResp.json();
            const productMapping = allMappings.find(m => m.snkrdunk_key === currentSnkrdunkCurrentProduct.id.toString());
            
            if (!productMapping || !productMapping.handle) {
                showAlert('error', 'Product mapping not found');
                hideLoading('snkrdunk-products-table');
                return;
            }
            
            // Get competitor grouping to find the database product ID
            const competitorResp = await fetch(`${API_BASE}/competitors/mapped?limit=1000`);
            if (!competitorResp.ok) throw new Error('Failed to fetch competitors');
            const competitorGroupings = await competitorResp.json();
            
            const productGrouping = competitorGroupings.find(g => g.shopify_product_handle === productMapping.handle);
            
            if (!productGrouping) {
                showAlert('error', 'Product grouping not found');
                hideLoading('snkrdunk-products-table');
                return;
            }
            
            // Use the database product ID from the grouping
            const shopifyProductId = productGrouping.shopify_product_id;
            
            console.log('Searching for Shopify product ID:', shopifyProductId);
            
            // Get the Shopify product to find the variant
            const productsResp = await fetch(`${API_BASE}/shopify/products?limit=1000`);
            if (!productsResp.ok) throw new Error('Failed to fetch products');
            const productsData = await productsResp.json();
            
            console.log('All products from API:', productsData);
            console.log('Product IDs available:', productsData.map(p => ({ id: p.id, shopify_id: p.shopify_id, title: p.title })));
            
            const myProduct = productsData.find(p => p.id === shopifyProductId || p.shopify_id === shopifyProductId);
            
            console.log('Found product:', myProduct);
            console.log('Product variants:', myProduct?.variants);
            
            if (!myProduct) {
                showAlert('error', `Product not found (ID: ${shopifyProductId})`);
                hideLoading('snkrdunk-products-table');
                return;
            }
            
            if (!myProduct.variants || myProduct.variants.length === 0) {
                showAlert('error', 'No variants found for this product');
                hideLoading('snkrdunk-products-table');
                return;
            }
            
            // Find the booster box variant
            const boxVariant = myProduct.variants.find(v => v.title && v.title.toLowerCase().includes('booster box')) 
                || myProduct.variants[0];
            
            // Create price plan instead of updating directly (same logic as matchPriceForProduct)
            const items = [{
                product_id: shopifyProductId,
                product_title: myProduct.title,
                variant_id: boxVariant.id,
                variant_title: boxVariant.title,
                current_price: currentSnkrdunkCurrentPrice,
                new_price: competitorPriceNOK
            }];
            
            const requestBody = {
                variant_type: 'box',
                plan_type: 'price_update',
                items: items,
                strategy: 'manual_update'
            };
            
            const planResp = await fetch(`${API_BASE}/price-plans/generate`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody)
            });
            
            const planResult = await planResp.json();
            
            if (!planResp.ok) {
                throw new Error(planResult.detail || 'Failed to create price plan');
            }
            
            const planId = planResult.id;
            console.log(`Price plan #${planId} created, now applying...`);
            
            // Automatically apply the plan
            const applyResp = await fetch(`${API_BASE}/price-plans/${planId}/apply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const applyResult = await applyResp.json();
            
            if (applyResp.ok) {
                console.log(`Plan #${planId} applied successfully! ${myProduct.title} updated to ${competitorPriceNOK.toFixed(2)} kr.`);
                showAlert(`success`, `Price plan #${planId} created and applied! ${myProduct.title} updated to kr ${competitorPriceNOK.toFixed(2)}. Refreshing...`);
                
                // Close the modal and refresh after a short delay
                setTimeout(() => {
                    document.querySelectorAll('div[style*="position: fixed"]').forEach(m => {
                        if (m.style.zIndex === '1000') m.remove();
                    });
                    location.reload();
                }, 1500);
            } else {
                throw new Error(applyResult.detail || 'Plan apply failed');
            }
            
        } catch (error) {
            console.error('Error matching price:', error);
            showAlert('error', `Failed to update price: ${error.message}`);
            hideLoading('snkrdunk-products-table');
        }
    }
}

async function showMapProductModal(snkrdunkId, snkrdunkProduct) {
    const modal = document.createElement('div');
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 2000;
    `;
    
    modal.innerHTML = `
        <div style="background: white; border-radius: 8px; max-width: 600px; width: 95%; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.4);">
            <div style="padding: 2rem; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h2 style="margin: 0; color: #111; font-size: 1.3rem;">Map to Shopify Product</h2>
                    <div style="font-size: 0.85rem; color: #666; margin-top: 0.25rem;">SNKRDUNK: ${snkrdunkProduct.nameEn || snkrdunkProduct.name}</div>
                </div>
                <button onclick="this.closest('div').parentElement.parentElement.remove()" style="background: none; border: none; font-size: 2rem; cursor: pointer; color: #666;">&times;</button>
            </div>
            
            <div style="padding: 2rem;">
                <div style="margin-bottom: 1.5rem;">
                    <input type="text" id="shopify-search-input" placeholder="Search Shopify products..." style="width: 100%; padding: 0.75rem; border: 1px solid #d1d5db; border-radius: 4px; font-size: 1rem;">
                </div>
                
                <div id="shopify-products-list" style="max-height: 400px; overflow-y: auto; border: 1px solid #e5e7eb; border-radius: 4px; background: #f9fafb;">
                    <div style="padding: 2rem; text-align: center; color: #666;">Loading Shopify products...</div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
    };
    
    // Load and render Shopify products
    const searchInput = modal.querySelector('#shopify-search-input');
    const productsList = modal.querySelector('#shopify-products-list');
    
    try {
        const resp = await fetch(`${API_BASE}/shopify/products?limit=1000`);
        if (!resp.ok) throw new Error('Failed to load products');
        const products = await resp.json();
        
        function renderProducts(filtered) {
            if (filtered.length === 0) {
                productsList.innerHTML = '<div style="padding: 2rem; text-align: center; color: #666;">No products found</div>';
                return;
            }
            
            productsList.innerHTML = filtered.map(p => `
                <div style="padding: 1rem; border-bottom: 1px solid #e5e7eb; cursor: pointer; hover: background: #f3f4f6;" 
                     onclick="event.stopPropagation(); mapSnkrdunkToShopify(${snkrdunkId}, '${p.shopify_id}', '${p.title.replace(/'/g, "\\'")}', '${p.handle}', this.closest('div').parentElement.parentElement.parentElement)">
                    <div style="font-weight: 600; color: #111;">${p.title}</div>
                    <div style="font-size: 0.85rem; color: #666; margin-top: 0.25rem;">ID: ${p.shopify_id} | Handle: ${p.handle}</div>
                </div>
            `).join('');
        }
        
        renderProducts(products);
        
        // Search filter
        searchInput.addEventListener('input', (e) => {
            const query = e.target.value.toLowerCase();
            const filtered = products.filter(p => 
                p.title.toLowerCase().includes(query) || 
                p.handle.toLowerCase().includes(query)
            );
            renderProducts(filtered);
        });
        
    } catch (error) {
        console.error('Error loading products:', error);
        productsList.innerHTML = '<div style="padding: 2rem; text-align: center; color: #d32f2f;">Error loading products</div>';
    }
}

async function mapSnkrdunkToShopify(snkrdunkId, shopifyId, shopifyTitle, shopifyHandle, modalContainer) {
    try {
        // Create the mapping
        const resp = await fetch(`${API_BASE}/mappings/snkrdunk`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                snkrdunk_key: snkrdunkId.toString(),
                product_shopify_id: shopifyId,
                handle: shopifyHandle
            })
        });
        
        if (!resp.ok) {
            const error = await resp.json();
            throw new Error(error.detail || 'Failed to create mapping');
        }
        
        showAlert('success', `Mapped to "${shopifyTitle}"! Refreshing...`);
        
        // Close modal and refresh
        setTimeout(async () => {
            modalContainer.remove();
            
            // Reload the mappings
            try {
                const mappingsResp = await fetch(`${API_BASE}/mappings/snkrdunk`);
                if (mappingsResp.ok) {
                    const mappings = await mappingsResp.json();
                    window.productMappings = {};
                    if (mappings && mappings.length > 0) {
                        mappings.forEach(mapping => {
                            const shopifyProduct = window.shopifyProducts.find(
                                p => p.shopify_id === mapping.product_shopify_id
                            );
                            if (shopifyProduct) {
                                window.productMappings[mapping.snkrdunk_key] = shopifyProduct.id;
                            }
                        });
                    }
                }
            } catch (e) {
                console.error('Error reloading mappings:', e);
            }
            
            // Re-render the products table
            renderSnkrdunkProductsTable();
        }, 800);
        
    } catch (error) {
        console.error('Error mapping product:', error);
        showAlert('error', `Failed to map product: ${error.message}`);
    }
}

async function showSnkrdunkProductDetail(product) {
    currentSnkrdunkCurrentProduct = product;
    const modal = document.createElement('div');
    currentSnkrdunkCurrentModal = modal;
    modal.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0,0,0,0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    `;
    
    modal.innerHTML = `
        <div style="background: white; border-radius: 8px; max-width: 1000px; width: 95%; max-height: 90vh; overflow-y: auto; box-shadow: 0 8px 24px rgba(0,0,0,0.4);">
            <div style="padding: 2rem; border-bottom: 1px solid #e5e7eb; display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <h2 style="margin: 0; color: #111; font-size: 1.5rem;">${product.nameEn || product.name}</h2>
                    <div style="font-size: 0.9rem; color: #666; margin-top: 0.25rem;">ID: ${product.id}</div>
                </div>
                <button onclick="this.closest('div').parentElement.parentElement.remove()" style="background: none; border: none; font-size: 2rem; cursor: pointer; color: #666;">&times;</button>
            </div>
            
            <div style="padding: 2rem;">
                <!-- Product Info -->
                <div style="margin-bottom: 2rem;">
                    <h3 style="margin: 0 0 1rem 0; color: #111;">Product Information</h3>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem;">
                        <div>
                            <div style="color: #666; font-size: 0.9rem;">Min Price (JPY)</div>
                            <div style="font-size: 1.3rem; font-weight: 600; color: #2563eb;">¥${product.minPriceJpy ? product.minPriceJpy.toLocaleString() : '-'}</div>
                        </div>
                        <div>
                            <div style="color: #666; font-size: 0.9rem;">Brand</div>
                            <div style="font-size: 1.1rem;">${product.brand?.name || '-'}</div>
                        </div>
                        <div>
                            <div style="color: #666; font-size: 0.9rem;">Last Updated</div>
                            <div style="font-size: 1rem;">${product.last_price_updated ? new Date(product.last_price_updated).toLocaleString() : '—'}</div>
                        </div>
                        <div>
                            <div style="color: #666; font-size: 0.9rem;">Type</div>
                            <div style="font-size: 1.1rem;">${product.type_en || '-'}</div>
                        </div>
                    </div>
                </div>
                
                <!-- My Price Section -->
                <div id="my-price-section" style="margin-bottom: 2rem; padding: 1rem; background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); border-radius: 6px; border-left: 4px solid #22c55e;">
                    <h3 style="margin: 0 0 1rem 0; color: #166534; font-size: 1.1rem;">Your Price</h3>
                    <div id="my-price-content" style="color: #666;">Loading...</div>
                </div>
                
                <!-- Competitor Pricing -->
                <div id="competitor-pricing-section" style="margin-bottom: 2rem;">
                    <h3 style="margin: 0 0 1rem 0; color: #111;">Competitor Pricing</h3>
                    <div id="competitor-pricing-list" style="display: grid; gap: 0.75rem;">
                        <div style="padding: 1rem; background: #f9fafb; border-radius: 4px; text-align: center; color: #666;">
                            Loading competitor prices...
                        </div>
                    </div>
                </div>
                
                <!-- Mapped Products -->
                <div id="product-mappings-section" style="margin-bottom: 2rem;">
                    <h3 style="margin: 0 0 1rem 0; color: #111;">Shopify Mappings</h3>
                    <div id="product-mappings-list" style="padding: 1rem; background: #f9fafb; border-radius: 4px; min-height: 50px; display: flex; align-items: center; justify-content: center; color: #666;">
                        Loading mappings...
                    </div>
                </div>
                
                <!-- Price History Timeline -->
                <div id="price-history-section">
                    <h3 style="margin: 0 0 1rem 0; color: #111;">Price History (Last 30 Days)</h3>
                    <div id="price-history-list" style="padding: 1rem; background: #f9fafb; border-radius: 4px; min-height: 50px; display: flex; align-items: center; justify-content: center; color: #666;">
                        Loading price history...
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    modal.onclick = (e) => {
        if (e.target === modal) modal.remove();
    };
    
    // Load competitor pricing
    (async () => {
        try {
            // First get the SNKRDUNK to Shopify mapping for this product
            const mappingsResp = await fetch(`${API_BASE}/mappings/snkrdunk?limit=100`);
            if (!mappingsResp.ok) throw new Error(`API error: ${mappingsResp.status}`);
            const allMappings = await mappingsResp.json();
            
            // Debug: log all mappings to see the structure
            console.log('All SNKRDUNK mappings:', allMappings);
            console.log('Looking for product ID:', product.id, 'as string:', product.id.toString());
            
            const productMapping = allMappings.find(m => {
                console.log(`Comparing: ${m.snkrdunk_key} === ${product.id.toString()}?`);
                return m.snkrdunk_key === product.id.toString() || m.snkrdunk_key === product.id;
            });
            
            console.log('Found product mapping:', productMapping);
            
            if (!productMapping || !productMapping.handle) {
                modal.querySelector('#competitor-pricing-list').innerHTML = '<div style="padding: 1rem; color: #999;">Not mapped to any Shopify product</div>';
                return;
            }
            
            console.log('Using handle for matching:', productMapping.handle);
            
            // Now get mapped competitors which includes data for this Shopify product
            const competitorResp = await fetch(`${API_BASE}/competitors/mapped?limit=1000`);
            if (!competitorResp.ok) throw new Error(`API error: ${competitorResp.status}`);
            const competitorGroupings = await competitorResp.json();
            
            console.log('Competitor groupings:', competitorGroupings);
            console.log('Looking for product handle:', productMapping.handle);
            
            // Find the grouping for this Shopify product by matching the handle
            const productGrouping = competitorGroupings.find(g => {
                console.log(`Comparing handles: "${g.shopify_product_handle}" === "${productMapping.handle}"?`);
                return g.shopify_product_handle === productMapping.handle;
            });
            
            console.log('Found product grouping:', productGrouping);
            
            if (!productGrouping || !productGrouping.competitors || productGrouping.competitors.length === 0) {
                modal.querySelector('#competitor-pricing-list').innerHTML = '<div style="padding: 1rem; color: #999;">No competitors mapped to this product</div>';
                return;
            }
            
            const competitorPricingList = modal.querySelector('#competitor-pricing-list');
            competitorPricingList.innerHTML = '';
            
            // Sort competitors by price
            const competitors = [...productGrouping.competitors].sort((a, b) => (a.competitor_price_ore || 0) - (b.competitor_price_ore || 0));
            
            competitors.forEach((comp, idx) => {
                const priceNOK = comp.competitor_price_ore ? (comp.competitor_price_ore / 100).toFixed(2) : 'N/A';
                const website = comp.competitor_website ? comp.competitor_website.charAt(0).toUpperCase() + comp.competitor_website.slice(1) : 'Unknown';
                
                // Determine stock status
                let stockStatus = 'Unknown';
                let stockColor = '#999';
                if (comp.competitor_stock) {
                    if (comp.competitor_stock.toLowerCase() === 'in_stock' || comp.competitor_stock.toLowerCase() === 'in stock') {
                        stockStatus = '✓ In Stock';
                        stockColor = '#22c55e';
                    } else if (comp.competitor_stock.toLowerCase() === 'out_of_stock' || comp.competitor_stock.toLowerCase() === 'out of stock') {
                        stockStatus = '✗ Out of Stock';
                        stockColor = '#ef4444';
                    } else {
                        stockStatus = comp.competitor_stock;
                    }
                }
                
                competitorPricingList.innerHTML += `
                    <div style="padding: 1.2rem; background: white; border: 1px solid #e5e7eb; border-radius: 6px; display: grid; grid-template-columns: 1.2fr 1fr 1fr 0.9fr; gap: 1.2rem; align-items: center;">
                        <div>
                            <div style="color: #666; font-size: 0.85rem; font-weight: 600;">WEBSITE</div>
                            <a href="${comp.competitor_link || '#'}" target="_blank" style="font-size: 1rem; margin-top: 0.25rem; color: #2563eb; text-decoration: none; font-weight: 500; cursor: pointer;">${website}</a>
                            <div style="color: #999; font-size: 0.8rem; margin-top: 0.25rem;">${comp.competitor_normalized || comp.competitor_name || '-'}</div>
                        </div>
                        <div>
                            <div style="color: #666; font-size: 0.85rem; font-weight: 600;">PRICE (NOK)</div>
                            <div style="font-size: 1.3rem; font-weight: 600; color: #f59e0b; margin-top: 0.25rem;">kr ${priceNOK}</div>
                            <div style="color: ${stockColor}; font-size: 0.85rem; margin-top: 0.5rem; font-weight: 500;">${stockStatus}</div>
                        </div>
                        <div>
                            <div style="color: #666; font-size: 0.85rem; font-weight: 600;">vs YOUR PRICE</div>
                            <div id="diff-${idx}" style="font-size: 1.1rem; font-weight: 600; margin-top: 0.25rem;">—</div>
                        </div>
                        <div>
                            <button onclick="matchSnkrdunkCompetitorPrice('${comp.competitor_price_ore}', '${comp.competitor_name.replace(/'/g, "\\'")}'${website ? `, '${website}'` : ''})" style="padding: 0.6rem 0.8rem; background: #2563eb; color: white; border: none; border-radius: 4px; font-size: 0.85rem; font-weight: 600; cursor: pointer; white-space: nowrap;">Match Price</button>
                        </div>
                    </div>
                `;
            });
            
        } catch (error) {
            console.error('Error loading competitor prices:', error);
            if (modal.querySelector('#competitor-pricing-list')) {
                modal.querySelector('#competitor-pricing-list').innerHTML = '<div style="padding: 1rem; color: #999;">Error loading competitor data</div>';
            }
        }
    })();
    
    // Load my price
    (async () => {
        try {
            const mappingsResp = await fetch(`${API_BASE}/mappings/snkrdunk?limit=100`);
            if (!mappingsResp.ok) throw new Error(`API error: ${mappingsResp.status}`);
            const mappingsData = await mappingsResp.json();
            const productMapping = mappingsData.find(m => m.snkrdunk_key === product.id.toString());
            
            if (!productMapping || !productMapping.product_shopify_id) {
                const myPriceContent = modal.querySelector('#my-price-section');
                if (myPriceContent) {
                    myPriceContent.style.display = 'none';
                }
                return;
            }
            
            const productsResp = await fetch(`${API_BASE}/shopify/products?limit=1000`);
            if (!productsResp.ok) throw new Error(`API error: ${productsResp.status}`);
            const productsData = await productsResp.json();
            
            // Find my product
            const myProduct = productsData.find(p => p.shopify_id === productMapping.product_shopify_id);
            
            if (!myProduct || !myProduct.variants || myProduct.variants.length === 0) {
                const myPriceContent = modal.querySelector('#my-price-content');
                if (myPriceContent) {
                    myPriceContent.innerHTML = '<div style="color: #999;">No variant data available</div>';
                }
                return;
            }
            
            // Get booster box variant
            const boxVariant = myProduct.variants.find(v => v.title && v.title.toLowerCase().includes('booster box')) 
                || myProduct.variants[0];
            
            const myPrice = parseFloat(boxVariant.price) || 0;
            currentSnkrdunkCurrentPrice = myPrice;
            const myPriceContent = modal.querySelector('#my-price-content');
            
            if (myPriceContent) {
                myPriceContent.innerHTML = `
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 2rem;">
                        <div>
                            <div style="color: #666; font-size: 0.9rem;">Shopify Product</div>
                            <div style="font-size: 1.1rem; font-weight: 600; color: #166534; margin-top: 0.5rem;">${myProduct.title || 'Unknown'}</div>
                        </div>
                        <div>
                            <div style="color: #666; font-size: 0.9rem;">Price (NOK)</div>
                            <div style="font-size: 1.5rem; font-weight: 700; color: #22c55e; margin-top: 0.5rem;">kr ${myPrice.toFixed(2)}</div>
                        </div>
                    </div>
                `;
            }
            
            // Update competitor differences now that we have myPrice
            try {
                const mappingsResp2 = await fetch(`${API_BASE}/mappings/snkrdunk?limit=100`);
                if (!mappingsResp2.ok) throw new Error(`API error: ${mappingsResp2.status}`);
                const allMappings2 = await mappingsResp2.json();
                const productMapping2 = allMappings2.find(m => m.snkrdunk_key === product.id.toString());
                
                if (productMapping2 && productMapping2.handle) {
                    const competitorResp = await fetch(`${API_BASE}/competitors/mapped?limit=1000`);
                    if (!competitorResp.ok) throw new Error(`API error: ${competitorResp.status}`);
                    const competitorGroupings = await competitorResp.json();
                    
                    const productGrouping = competitorGroupings.find(g => g.shopify_product_handle === productMapping2.handle);
                    
                    if (productGrouping && productGrouping.competitors) {
                        const competitors = [...productGrouping.competitors].sort((a, b) => (a.competitor_price_ore || 0) - (b.competitor_price_ore || 0));
                        
                        competitors.forEach((comp, idx) => {
                            const diffElement = modal.querySelector(`#diff-${idx}`);
                            if (diffElement) {
                                const competitorPriceNOK = comp.competitor_price_ore ? (comp.competitor_price_ore / 100) : 0;
                                const difference = myPrice - competitorPriceNOK;
                                let diffColor = '#666';
                                let diffText = '';
                                
                                if (difference > 0) {
                                    diffColor = '#ef4444';
                                    diffText = `+kr ${Math.abs(difference).toFixed(2)} (higher)`;
                                } else if (difference < 0) {
                                    diffColor = '#22c55e';
                                    diffText = `kr ${Math.abs(difference).toFixed(2)} (cheaper)`;
                                } else {
                                    diffText = 'Same price';
                                }
                                
                                diffElement.style.color = diffColor;
                                diffElement.textContent = diffText;
                            }
                        });
                    }
                }
            } catch (err) {
                console.error('Error updating competitor differences:', err);
            }
        } catch (error) {
            console.error('Error loading my price:', error);
            const myPriceContent = modal.querySelector('#my-price-content');
            if (myPriceContent) {
                myPriceContent.innerHTML = '<div style="color: #999;">Error loading your product data</div>';
            }
        }
    })();
    
    // Load mappings
    (async () => {
        try {
            const mappingsResp = await fetch(`${API_BASE}/mappings/snkrdunk?limit=100`);
            if (!mappingsResp.ok) throw new Error(`API error: ${mappingsResp.status}`);
            const mappingsData = await mappingsResp.json();
            const productMappings = mappingsData.filter(m => m.snkrdunk_key === product.id.toString());
            
            const mappingsList = modal.querySelector('#product-mappings-list');
            if (mappingsList) {
                if (productMappings && productMappings.length > 0) {
                    mappingsList.innerHTML = productMappings.map(m => `
                        <div style="padding: 0.75rem; background: white; border: 1px solid #e5e7eb; border-radius: 4px; margin-bottom: 0.5rem; width: 100%;">
                            <div style="font-weight: 600; color: #111;">${m.handle || 'Shopify Product'}</div>
                            <div style="font-size: 0.85rem; color: #666; margin-top: 0.25rem;">
                                Mapped: ${m.updated_at ? new Date(m.updated_at).toLocaleString() : 'Unknown'}
                            </div>
                        </div>
                    `).join('');
                } else {
                    mappingsList.innerHTML = '<div style="color: #999;">No mappings found for this product</div>';
                }
            }
        } catch (error) {
            console.error('Error loading mappings:', error);
            const mappingsList = modal.querySelector('#product-mappings-list');
            if (mappingsList) {
                mappingsList.innerHTML = '<div style="color: #999;">Error loading mappings</div>';
            }
        }
    })();
    
    // Load price history
    (async () => {
        try {
            const response = await fetch(`${API_BASE}/history/snkrdunk/${product.id}/timeline?days_back=30`);
            
            if (!response.ok) {
                throw new Error(`API error: ${response.status}`);
            }
            
            const result = await response.json();
            const priceHistoryList = modal.querySelector('#price-history-list');
            
            if (!priceHistoryList) return;
            
            if (!result.data || result.data.length === 0) {
                priceHistoryList.innerHTML = `
                    <div style="padding: 2rem; text-align: center; color: #999;">
                        <div style="font-size: 1.2rem; margin-bottom: 0.5rem;">No historical data available</div>
                        <div style="font-size: 0.9rem;">Price history will be recorded as scans are performed</div>
                    </div>
                `;
                return;
            }
            
            // Prepare chart data
            const timeline = result.data;
            const dates = timeline.map(item => {
                const d = new Date(item.timestamp);
                // Show time for same-day data, date for multi-day
                const now = new Date();
                const isToday = d.toDateString() === now.toDateString();
                if (isToday) {
                    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
                } else {
                    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
                }
            });
            const prices = timeline.map(item => item.price_jpy);
            
            // Calculate price statistics
            const currentPrice = prices[prices.length - 1];
            const oldestPrice = prices[0];
            const minPrice = Math.min(...prices);
            const maxPrice = Math.max(...prices);
            const avgPrice = Math.round(prices.reduce((a, b) => a + b, 0) / prices.length);
            const priceChange = currentPrice - oldestPrice;
            const priceChangePercent = ((priceChange / oldestPrice) * 100).toFixed(1);
            
            // Create simple ASCII/SVG chart
            const chartWidth = 900;
            const chartHeight = 200;
            const padding = 40;
            const plotWidth = chartWidth - padding * 2;
            const plotHeight = chartHeight - padding * 2;
            
            // Scale prices to chart height
            const priceRange = maxPrice - minPrice;
            const priceScale = priceRange > 0 ? plotHeight / priceRange : 1;
            
            // Generate SVG path for line chart
            let pathData = '';
            const points = [];
            
            timeline.forEach((item, idx) => {
                const x = padding + (idx / (timeline.length - 1)) * plotWidth;
                const y = padding + plotHeight - ((item.price_jpy - minPrice) * priceScale);
                points.push({ x, y, price: item.price_jpy, date: dates[idx] });
                
                if (idx === 0) {
                    pathData += `M ${x} ${y}`;
                } else {
                    pathData += ` L ${x} ${y}`;
                }
            });
            
            // Create grid lines for y-axis
            const ySteps = 5;
            let gridLines = '';
            for (let i = 0; i <= ySteps; i++) {
                const y = padding + (plotHeight / ySteps) * i;
                const price = maxPrice - (priceRange / ySteps) * i;
                gridLines += `
                    <line x1="${padding}" y1="${y}" x2="${chartWidth - padding}" y2="${y}" 
                          stroke="#e5e7eb" stroke-width="1" stroke-dasharray="2,2"/>
                    <text x="${padding - 10}" y="${y + 4}" text-anchor="end" font-size="11" fill="#666">
                        ¥${Math.round(price).toLocaleString()}
                    </text>
                `;
            }
            
            // Create dots for each data point
            let dots = points.map((p, idx) => `
                <circle cx="${p.x}" cy="${p.y}" r="4" fill="#2563eb" stroke="white" stroke-width="2" 
                        onmouseover="this.setAttribute('r', '6')" onmouseout="this.setAttribute('r', '4')">
                    <title>${p.date}: ¥${p.price.toLocaleString()}</title>
                </circle>
            `).join('');
            
            priceHistoryList.innerHTML = `
                <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 1rem; margin-bottom: 1.5rem;">
                    <div style="text-align: center; padding: 1rem; background: white; border-radius: 6px; border: 1px solid #e5e7eb;">
                        <div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">Current</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #2563eb;">¥${currentPrice.toLocaleString()}</div>
                    </div>
                    <div style="text-align: center; padding: 1rem; background: white; border-radius: 6px; border: 1px solid #e5e7eb;">
                        <div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">Average (30d)</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: #666;">¥${avgPrice.toLocaleString()}</div>
                    </div>
                    <div style="text-align: center; padding: 1rem; background: white; border-radius: 6px; border: 1px solid #e5e7eb;">
                        <div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">Low / High</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: #22c55e;">¥${minPrice.toLocaleString()}</div>
                        <div style="font-size: 1.2rem; font-weight: 600; color: #ef4444; margin-top: 0.25rem;">¥${maxPrice.toLocaleString()}</div>
                    </div>
                    <div style="text-align: center; padding: 1rem; background: white; border-radius: 6px; border: 1px solid #e5e7eb;">
                        <div style="font-size: 0.85rem; color: #666; margin-bottom: 0.5rem;">Change (30d)</div>
                        <div style="font-size: 1.5rem; font-weight: 700; color: ${priceChange >= 0 ? '#ef4444' : '#22c55e'};">
                            ${priceChange >= 0 ? '+' : ''}¥${priceChange.toLocaleString()}
                        </div>
                        <div style="font-size: 0.9rem; color: ${priceChange >= 0 ? '#ef4444' : '#22c55e'}; margin-top: 0.25rem;">
                            ${priceChange >= 0 ? '+' : ''}${priceChangePercent}%
                        </div>
                    </div>
                </div>
                
                <div style="background: white; padding: 1.5rem; border-radius: 6px; border: 1px solid #e5e7eb;">
                    <svg width="${chartWidth}" height="${chartHeight}" style="width: 100%; height: auto;">
                        ${gridLines}
                        <path d="${pathData}" fill="none" stroke="#2563eb" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                        ${dots}
                    </svg>
                </div>
                
                <div style="margin-top: 1rem; text-align: center; color: #666; font-size: 0.9rem;">
                    Showing ${timeline.length} data point${timeline.length !== 1 ? 's' : ''} from the last 30 days
                </div>
            `;
            
        } catch (error) {
            console.error('Error loading price history:', error);
            const priceHistoryList = modal.querySelector('#price-history-list');
            if (priceHistoryList) {
                priceHistoryList.innerHTML = `
                    <div style="padding: 1rem; color: #ef4444; text-align: center;">
                        Error loading price history: ${error.message}
                    </div>
                `;
            }
        }
    })();
}


// ==================== SCAN LOGS ====================

async function showScanLogs() {
    const logsPanel = document.getElementById('scan-logs-panel');
    if (logsPanel) {
        logsPanel.style.display = 'block';
    }
    
    try {
        const response = await fetch(`${API_BASE}/competitors/scan-logs?limit=50`);
        if (!response.ok) throw new Error(`HTTP ${response.status}: Failed to load scan logs`);
        
        const logs = await response.json();
        console.log('Loaded scan logs:', logs);
        
        const tbody = document.getElementById('scan-logs-tbody');
        if (!tbody) {
            console.error('scan-logs-tbody element not found');
            return;
        }
        
        if (!logs || logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No scan logs yet. Run a scan to get started.</td></tr>';
            return;
        }
        
        tbody.innerHTML = '';
        logs.forEach(log => {
            const row = document.createElement('tr');
            const startDate = log.started_at ? new Date(log.started_at).toLocaleString('no-NO') : '-';
            const completeDate = log.completed_at ? new Date(log.completed_at).toLocaleString('no-NO') : '-';
            const duration = log.duration_seconds ? `${log.duration_seconds.toFixed(1)}s` : '-';
            const statusColor = log.status === 'success' ? '#28a745' : '#dc3545';
            const statusText = log.status === 'success' ? 'SUCCESS' : 'FAILED';
            
            // Add retry button for failed scans
            const retryButton = log.status === 'failed' 
                ? `<button class="btn btn-sm btn-warning" onclick="retryFailedScan('${log.scraper_name}')" style="margin-left: 0.5rem;">🔄 Retry</button>`
                : '';
            
            row.innerHTML = `
                <td><strong>${log.scraper_name}</strong></td>
                <td style="color: ${statusColor}; font-weight: 600;">${statusText}</td>
                <td style="font-size: 0.85rem;">${startDate}</td>
                <td style="font-size: 0.85rem;">${completeDate}</td>
                <td><strong>${duration}</strong></td>
                <td>
                    <button class="btn btn-sm btn-secondary" onclick="viewScanLogDetails(${log.id}, '${log.scraper_name}')">Details</button>
                    ${retryButton}
                </td>
            `;
            tbody.appendChild(row);
        });
        
    } catch (error) {
        console.error('Error loading scan logs:', error);
        showAlert(`Error loading scan logs: ${error.message}`, 'error');
    }
}

function hideScanLogs() {
    const logsPanel = document.getElementById('scan-logs-panel');
    if (logsPanel) {
        logsPanel.style.display = 'none';
    }
}

async function retryFailedScan(scraperName) {
    if (!confirm(`Retry scan for ${scraperName}?`)) {
        return;
    }
    
    showAlert(`🔄 Retrying ${scraperName} scan...`, 'info');
    
    try {
        await runCompetitorScraper(scraperName);
        // Refresh scan logs after a short delay to show the new scan
        setTimeout(() => {
            showScanLogs();
        }, 2000);
    } catch (error) {
        console.error('Error retrying scan:', error);
        showAlert(`❌ Failed to retry scan: ${error.message}`, 'error');
    }
}

async function viewScanLogDetails(logId, scraperName) {
    try {
        const response = await fetch(`${API_BASE}/competitors/scan-logs/${logId}`);
        if (!response.ok) throw new Error('Failed to load scan log details');
        
        const log = await response.json();
        console.log('Scan log details:', log);
        
        // Set modal title
        document.getElementById('scan-log-modal-title').textContent = `Scan Log: ${scraperName}`;
        
        const statusColor = log.status === 'success' ? '#28a745' : '#dc3545';
        const statusText = log.status === 'success' ? 'SUCCESS' : 'FAILED';
        const startDate = log.started_at ? new Date(log.started_at).toLocaleString('no-NO') : '-';
        const completeDate = log.completed_at ? new Date(log.completed_at).toLocaleString('no-NO') : '-';
        const duration = log.duration_seconds ? `${log.duration_seconds.toFixed(1)}s` : '-';
        
        let content = `
            <div style="margin-bottom: 1.5rem;">
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
                    <div>
                        <div style="font-size: 0.85rem; color: #666;">Status</div>
                        <div style="color: ${statusColor}; font-weight: 600; font-size: 1.1rem;">${statusText}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85rem; color: #666;">Duration</div>
                        <div style="font-weight: 600; font-size: 1.1rem;">${duration}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85rem; color: #666;">Started</div>
                        <div style="font-size: 0.9rem;">${startDate}</div>
                    </div>
                    <div>
                        <div style="font-size: 0.85rem; color: #666;">Completed</div>
                        <div style="font-size: 0.9rem;">${completeDate}</div>
                    </div>
                </div>
        `;
        
        // Always show output section with a header
        content += `<div style="margin-bottom: 1rem;">
                    <div style="font-weight: 600; margin-bottom: 0.5rem;">Scan Output:</div>`;
        
        if (log.output && log.output.trim()) {
            content += `<pre style="background: #f5f5f5; padding: 1rem; border-radius: 4px; overflow-x: auto; max-height: 400px; font-size: 0.85rem; line-height: 1.4; color: #333; border-left: 4px solid #2563eb;">` + escapeHtml(log.output) + `</pre>`;
        } else {
            content += `<div style="background: #f5f5f5; padding: 1rem; border-radius: 4px; color: #999; border-left: 4px solid #2563eb;">No output captured</div>`;
        }
        content += `</div>`;
        
        // Show error section if exists
        if (log.error_message && log.error_message.trim()) {
            content += `
                <div>
                    <div style="font-weight: 600; margin-bottom: 0.5rem; color: #dc3545;">Error:</div>
                    <pre style="background: #fee; padding: 1rem; border-radius: 4px; overflow-x: auto; max-height: 300px; font-size: 0.85rem; line-height: 1.4; color: #c00; border-left: 4px solid #dc3545;">` + escapeHtml(log.error_message) + `</pre>
                </div>
            `;
        }
        
        content += `</div>`;
        
        const contentDiv = document.getElementById('scan-log-detail-content');
        if (contentDiv) {
            contentDiv.innerHTML = content;
            showModal('scan-log-detail-modal');
        }
        
    } catch (error) {
        console.error('Error loading scan log details:', error);
        showAlert(`Error loading details: ${error.message}`, 'error');
    }
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}
