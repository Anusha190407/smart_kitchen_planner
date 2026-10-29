/**
 * Smart Kitchen Planner - Frontend SPA Application
 * Handles authentication, state management, routing, editable data grids,
 * custom SVG charts, interactive simulations, and reporting.
 */

// --- Global Application State ---
const state = {
  token: localStorage.getItem('skp_token') || null,
  user: JSON.parse(localStorage.getItem('skp_user') || 'null'),
  restaurant: JSON.parse(localStorage.getItem('skp_restaurant') || 'null'),
  currentPage: 'dashboard',
  loading: false,
  error: null,
  
  // Data caches
  dashboardData: null,
  mealForecastData: null,
  selectedMealHistory: null,
  selectedMealId: null,
  ingredientForecastData: null,
  selectedIngredientDrilldown: null,
  inventoryData: null,
  ordersData: null,
  modelData: null,
  savingsData: null,
  settingsData: null,
  
  // What-if state
  whatif: {
    mealId: 1109,
    date: '2026-10-29',
    checkoutPrice: 230,
    promoActive: 0,
    featuredOnMenu: 0,
    festivalOrEvent: 0,
    simulationResult: null,
    loading: false
  },
  
  // Data Upload & Grid state
  upload: {
    activeSheet: 'Daily_Orders',
    sheets: ['Meals', 'Daily_Orders', 'Next_7_Days_Inputs', 'Recipes', 'Ingredient_Master', 'Inventory_History', 'Current_Stock'],
    gridData: [],
    gridColumns: [],
    historyStack: [],
    selectedRowIndex: null,
    validationErrors: [],
    loading: false,
    addTodayForm: {
      date: '2026-10-29',
      orders: [],
      stocks: []
    }
  }
};

// --- API Client ---
async function apiCall(endpoint, options = {}) {
  const headers = options.headers || {};
  if (state.token) {
    headers['Authorization'] = `Bearer ${state.token}`;
  }
  if (!options.isFormData && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  
  try {
    const res = await fetch(endpoint, { ...options, headers });
    if (res.status === 401) {
      logout();
      showToast('Session expired. Please sign in again.');
      throw new Error('Unauthorized');
    }
    if (!res.ok) {
      const errData = await res.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(errData.detail || errData.message || 'Request failed');
    }
    return await res.json();
  } catch (err) {
    console.error('API Error:', err);
    throw err;
  }
}

// --- Helpers ---
function formatCurrency(num) {
  if (num === null || num === undefined || isNaN(num)) return '₹0.00';
  return '₹' + Number(num).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatDate(isoStr) {
  if (!isoStr) return '';
  const parts = String(isoStr).split('-');
  if (parts.length === 3) return `${parts[2]}-${parts[1]}-${parts[0]}`;
  return String(isoStr);
}

function showToast(message) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.innerText = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 200);
  }, 3500);
}

// --- Auth Actions ---
async function handleLogin(e) {
  e.preventDefault();
  const email = document.getElementById('login-email').value;
  const password = document.getElementById('login-password').value;
  const errorBox = document.getElementById('auth-error');
  
  try {
    errorBox.style.display = 'none';
    const data = await apiCall('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    });
    setSession(data);
    showToast('Signed in successfully');
    render();
  } catch (err) {
    errorBox.innerText = err.message;
    errorBox.style.display = 'block';
  }
}

async function handleRegister(e) {
  e.preventDefault();
  const name = document.getElementById('reg-name').value;
  const email = document.getElementById('reg-email').value;
  const password = document.getElementById('reg-password').value;
  const errorBox = document.getElementById('auth-error');
  
  try {
    errorBox.style.display = 'none';
    const data = await apiCall('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify({ restaurant_name: name, email, password })
    });
    setSession(data);
    showToast('Account created and sample dataset initialized');
    render();
  } catch (err) {
    errorBox.innerText = err.message;
    errorBox.style.display = 'block';
  }
}

function setSession(data) {
  state.token = data.token;
  state.user = data.user;
  state.restaurant = data.restaurant;
  localStorage.setItem('skp_token', data.token);
  localStorage.setItem('skp_user', JSON.stringify(data.user));
  localStorage.setItem('skp_restaurant', JSON.stringify(data.restaurant));
}

function logout() {
  state.token = null;
  state.user = null;
  state.restaurant = null;
  localStorage.removeItem('skp_token');
  localStorage.removeItem('skp_user');
  localStorage.removeItem('skp_restaurant');
  render();
}

async function loadSampleData() {
  if (!confirm('Load sample dataset and trigger recalculation?')) return;
  state.loading = true;
  render();
  try {
    const res = await apiCall('/api/data/load-sample', { method: 'POST' });
    showToast(res.message);
    if (res.last_updated && state.restaurant) {
      state.restaurant.last_updated = res.last_updated;
    }
    await refreshCurrentPageData();
  } catch (err) {
    showToast('Failed to load sample dataset: ' + err.message);
  } finally {
    state.loading = false;
    render();
  }
}

// --- Navigation ---
function navigateTo(page) {
  state.currentPage = page;
  state.error = null;
  render();
  refreshCurrentPageData();
}

async function refreshCurrentPageData() {
  if (!state.token) return;
  state.loading = true;
  render();
  
  try {
    if (state.currentPage === 'dashboard') {
      state.dashboardData = await apiCall('/api/dashboard');
    } else if (state.currentPage === 'meals') {
      const cat = document.getElementById('meal-filter-cat')?.value || '';
      const cui = document.getElementById('meal-filter-cui')?.value || '';
      const url = `/api/forecast/meals?category=${encodeURIComponent(cat)}&cuisine=${encodeURIComponent(cui)}`;
      state.mealForecastData = await apiCall(url);
    } else if (state.currentPage === 'ingredients') {
      state.ingredientForecastData = await apiCall('/api/forecast/ingredients');
    } else if (state.currentPage === 'orders') {
      state.ordersData = await apiCall('/api/orders/recommendations');
    } else if (state.currentPage === 'inventory') {
      state.inventoryData = await apiCall('/api/inventory/status');
    } else if (state.currentPage === 'whatif') {
      if (!state.mealForecastData) {
        state.mealForecastData = await apiCall('/api/forecast/meals');
      }
      runWhatIfSimulation();
    } else if (state.currentPage === 'reports') {
      state.savingsData = await apiCall('/api/reports/savings');
    } else if (state.currentPage === 'upload') {
      await loadSheetData(state.upload.activeSheet);
    } else if (state.currentPage === 'model') {
      state.modelData = await apiCall('/api/model/status');
    } else if (state.currentPage === 'settings') {
      state.settingsData = await apiCall('/api/settings');
    }
  } catch (err) {
    state.error = err.message;
  } finally {
    state.loading = false;
    render();
  }
}

// --- Data Upload & Grid Management ---
async function loadSheetData(sheetName) {
  state.upload.activeSheet = sheetName;
  state.upload.loading = true;
  render();
  try {
    const data = await apiCall(`/api/data/sheet/${sheetName}`);
    state.upload.gridColumns = data.columns;
    state.upload.gridData = data.rows;
    state.upload.historyStack = [JSON.stringify(data.rows)];
    state.upload.validationErrors = [];
    state.upload.selectedRowIndex = null;
  } catch (err) {
    showToast('Failed to load sheet: ' + err.message);
  } finally {
    state.upload.loading = false;
    render();
  }
}

function handleGridCellEdit(rowIndex, colName, newVal) {
  // Push undo state
  state.upload.historyStack.push(JSON.stringify(state.upload.gridData));
  state.upload.gridData[rowIndex][colName] = newVal;
  render();
}

function handleGridAddRow() {
  state.upload.historyStack.push(JSON.stringify(state.upload.gridData));
  const newRow = {};
  state.upload.gridColumns.forEach(c => newRow[c] = '');
  state.upload.gridData.unshift(newRow);
  state.upload.selectedRowIndex = 0;
  render();
}

function handleGridDeleteRow() {
  if (state.upload.selectedRowIndex === null) {
    showToast('Select a row to delete');
    return;
  }
  state.upload.historyStack.push(JSON.stringify(state.upload.gridData));
  state.upload.gridData.splice(state.upload.selectedRowIndex, 1);
  state.upload.selectedRowIndex = null;
  render();
}

function handleGridUndo() {
  if (state.upload.historyStack.length <= 1) {
    showToast('Nothing to undo');
    return;
  }
  state.upload.historyStack.pop(); // Remove current
  const prev = state.upload.historyStack[state.upload.historyStack.length - 1];
  state.upload.gridData = JSON.parse(prev);
  render();
}

async function handleValidateSheet() {
  try {
    const res = await apiCall(`/api/data/sheet/${state.upload.activeSheet}/validate`, {
      method: 'POST',
      body: JSON.stringify({ rows: state.upload.gridData })
    });
    state.upload.validationErrors = res.errors || [];
    if (res.valid) {
      showToast('Validation passed. No errors found.');
    } else {
      showToast(`Validation found ${res.errors.length} issue(s).`);
    }
    render();
  } catch (err) {
    showToast('Validation check failed: ' + err.message);
  }
}

async function handleSaveSheet() {
  state.loading = true;
  render();
  try {
    const res = await apiCall(`/api/data/sheet/${state.upload.activeSheet}/save`, {
      method: 'POST',
      body: JSON.stringify({ rows: state.upload.gridData })
    });
    if (res.status === 'error') {
      state.upload.validationErrors = res.errors || [];
      showToast('Validation failed. Please review errors.');
    } else {
      showToast(res.message);
      state.upload.validationErrors = [];
    }
  } catch (err) {
    showToast('Save failed: ' + err.message);
  } finally {
    state.loading = false;
    render();
  }
}

async function handleFileUpload(file) {
  const formData = new FormData();
  formData.append('file', file);
  state.loading = true;
  render();
  try {
    const res = await apiCall('/api/data/upload-file', {
      method: 'POST',
      body: formData,
      isFormData: true
    });
    showToast(`Uploaded ${res.filename}. Select a sheet to review.`);
    const firstSheet = Object.keys(res.sheets)[0];
    if (firstSheet) {
      state.upload.activeSheet = firstSheet;
      state.upload.gridData = res.sheets[firstSheet];
      state.upload.gridColumns = Object.keys(res.sheets[firstSheet][0] || {});
      state.upload.historyStack = [JSON.stringify(state.upload.gridData)];
    }
  } catch (err) {
    showToast('File upload failed: ' + err.message);
  } finally {
    state.loading = false;
    render();
  }
}

// --- What-if Simulation ---
async function runWhatIfSimulation() {
  state.whatif.loading = true;
  render();
  try {
    const res = await apiCall('/api/whatif/simulate', {
      method: 'POST',
      body: JSON.stringify({
        meal_id: Number(state.whatif.mealId),
        date: state.whatif.date,
        checkout_price: Number(state.whatif.checkoutPrice),
        promo_active: Number(state.whatif.promoActive),
        featured_on_menu: Number(state.whatif.featuredOnMenu),
        festival_or_event: Number(state.whatif.festivalOrEvent)
      })
    });
    state.whatif.simulationResult = res;
  } catch (err) {
    showToast('What-if calculation failed: ' + err.message);
  } finally {
    state.whatif.loading = false;
    render();
  }
}

async function applyWhatIfToPlan() {
  if (!state.whatif.simulationResult) return;
  try {
    const sim = state.whatif.simulationResult;
    await apiCall('/api/whatif/apply', {
      method: 'POST',
      body: JSON.stringify({
        meal_id: sim.meal_id,
        date: sim.date,
        checkout_price: sim.parameters.checkout_price,
        promo_active: sim.parameters.promo_active,
        featured_on_menu: sim.parameters.featured_on_menu,
        festival_or_event: sim.parameters.festival_or_event,
        simulated_orders: sim.forecast_comparison.simulated_orders
      })
    });
    showToast('Scenario applied to operational plan.');
  } catch (err) {
    showToast('Failed to apply scenario: ' + err.message);
  }
}

function resetWhatIf() {
  state.whatif.checkoutPrice = 230;
  state.whatif.promoActive = 0;
  state.whatif.featuredOnMenu = 0;
  state.whatif.festivalOrEvent = 0;
  runWhatIfSimulation();
}

// --- Generic Excel Export ---
async function exportCurrentGrid(tableName, columns, rows) {
  try {
    const res = await fetch('/api/reports/export-table', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${state.token}`
      },
      body: JSON.stringify({ table_name: tableName, columns, rows })
    });
    const blob = await res.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${tableName}.xlsx`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  } catch (err) {
    showToast('Export failed: ' + err.message);
  }
}

// --- SVG Chart Renderers ---
function renderBarChart(data, xKey, yKey, height = 220) {
  if (!data || data.length === 0) return '<div class="state-box"><p class="state-desc">No data available for chart</p></div>';
  const maxVal = Math.max(...data.map(d => d[yKey] || 0), 1);
  const width = 600;
  const padding = { top: 20, right: 20, bottom: 35, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  const barW = Math.max(12, Math.min(36, (chartW / data.length) - 8));
  
  let barsSvg = '';
  data.forEach((d, i) => {
    const x = padding.left + (i * (chartW / data.length)) + ((chartW / data.length - barW) / 2);
    const h = ((d[yKey] || 0) / maxVal) * chartH;
    const y = padding.top + (chartH - h);
    barsSvg += `
      <rect x="${x}" y="${y}" width="${barW}" height="${h}" fill="#0F766E" rx="2">
        <title>${d[xKey]}: ${d[yKey]}</title>
      </rect>
      <text x="${x + barW/2}" y="${height - 12}" font-size="10" fill="#64748B" text-anchor="middle">${formatDate(d[xKey]).slice(0, 5)}</text>
    `;
  });
  
  return `
    <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; max-height: ${height}px;">
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="#E3E8EF" stroke-width="1" />
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="#E3E8EF" stroke-width="1" />
      <text x="${padding.left - 8}" y="${padding.top + 10}" font-size="10" fill="#64748B" text-anchor="end">${Math.round(maxVal)}</text>
      <text x="${padding.left - 8}" y="${height - padding.bottom}" font-size="10" fill="#64748B" text-anchor="end">0</text>
      ${barsSvg}
    </svg>
  `;
}

function renderLineChart(data, xKey, yKeys, height = 240) {
  if (!data || data.length === 0) return '<div class="state-box"><p class="state-desc">No data for chart</p></div>';
  const width = 640;
  const padding = { top: 20, right: 30, bottom: 35, left: 50 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  
  let allVals = [];
  yKeys.forEach(k => data.forEach(d => { if (d[k] !== undefined) allVals.push(d[k]); }));
  const maxVal = Math.max(...allVals, 1);
  const minVal = 0;
  
  const colors = ['#1F3A5F', '#0F766E', '#B7791F', '#C62828'];
  
  let pathsSvg = '';
  yKeys.forEach((key, kIdx) => {
    const color = colors[kIdx % colors.length];
    let pathD = '';
    data.forEach((d, i) => {
      const val = d[key] !== undefined ? d[key] : 0;
      const x = padding.left + (i * (chartW / (data.length - 1 || 1)));
      const y = padding.top + (chartH - ((val - minVal) / (maxVal - minVal || 1)) * chartH);
      pathD += (i === 0 ? `M ${x} ${y}` : ` L ${x} ${y}`);
    });
    pathsSvg += `<path d="${pathD}" fill="none" stroke="${color}" stroke-width="2" />`;
  });
  
  return `
    <svg viewBox="0 0 ${width} ${height}" style="width: 100%; height: auto; max-height: ${height}px;">
      <line x1="${padding.left}" y1="${height - padding.bottom}" x2="${width - padding.right}" y2="${height - padding.bottom}" stroke="#E3E8EF" stroke-width="1" />
      <line x1="${padding.left}" y1="${padding.top}" x2="${padding.left}" y2="${height - padding.bottom}" stroke="#E3E8EF" stroke-width="1" />
      <text x="${padding.left - 8}" y="${padding.top + 10}" font-size="10" fill="#64748B" text-anchor="end">${Math.round(maxVal)}</text>
      <text x="${padding.left - 8}" y="${height - padding.bottom}" font-size="10" fill="#64748B" text-anchor="end">0</text>
      ${pathsSvg}
    </svg>
  `;
}

// --- View Renderers ---
function renderAuth() {
  const isRegister = window.location.hash === '#register';
  return `
    <div class="auth-wrapper">
      <div class="auth-panel-form">
        <div class="auth-card">
          <div class="auth-header">
            <h1 class="auth-title">Smart Kitchen Planner</h1>
            <p class="auth-subtitle">Ingredient planning for restaurants</p>
          </div>
          <div id="auth-error" class="badge badge-red" style="display: none; width: 100%; padding: 8px; margin-bottom: 16px;"></div>
          ${isRegister ? `
            <form onsubmit="handleRegister(event)">
              <div class="form-group">
                <label class="form-label">Restaurant Name</label>
                <input id="reg-name" class="form-input" placeholder="e.g. Spice Garden Bistro" required />
              </div>
              <div class="form-group">
                <label class="form-label">Email</label>
                <input id="reg-email" type="email" class="form-input" placeholder="chef@restaurant.com" required />
              </div>
              <div class="form-group">
                <label class="form-label">Password</label>
                <input id="reg-password" type="password" class="form-input" placeholder="••••••••" required />
              </div>
              <button type="submit" class="btn btn-primary" style="width: 100%; margin-top: 8px;">Create Account</button>
              <p style="margin-top: 16px; font-size: 12px; text-align: center; color: var(--text-secondary);">
                Already have an account? <a href="#" onclick="window.location.hash=''; render();" style="color: var(--teal); font-weight: 600;">Sign in</a>
              </p>
            </form>
          ` : `
            <form onsubmit="handleLogin(event)">
              <div class="form-group">
                <label class="form-label">Email</label>
                <input id="login-email" type="email" class="form-input" value="chef@spicegarden.com" required />
              </div>
              <div class="form-group">
                <label class="form-label">Password</label>
                <input id="login-password" type="password" class="form-input" value="admin123" required />
              </div>
              <button type="submit" class="btn btn-primary" style="width: 100%; margin-top: 8px;">Sign in</button>
              <p style="margin-top: 16px; font-size: 12px; text-align: center; color: var(--text-secondary);">
                Don't have an account? <a href="#register" onclick="window.location.hash='#register'; render();" style="color: var(--teal); font-weight: 600;">Create account</a>
              </p>
            </form>
          `}
        </div>
      </div>
      <div class="auth-panel-preview">
        <h2 style="font-size: 18px; font-weight: 700; margin-bottom: 12px;">Operational Overview Preview</h2>
        <p style="font-size: 12px; color: #94A3B8; margin-bottom: 24px;">Multi-horizon Poisson demand modeling linked with FIFO batch tracking.</p>
        <div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 6px; padding: 16px;">
          <table style="width: 100%; font-size: 11px; color: #E2E8F0; border-collapse: collapse;">
            <thead>
              <tr style="border-bottom: 1px solid rgba(255,255,255,0.1); text-align: left;">
                <th style="padding: 6px 8px;">Ingredient</th>
                <th style="padding: 6px 8px;">Stock on Hand</th>
                <th style="padding: 6px 8px;">Days of Cover</th>
                <th style="padding: 6px 8px;">Order Suggestion</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td style="padding: 6px 8px;">Chicken</td>
                <td style="padding: 6px 8px; color: #F87171;">0 kg</td>
                <td style="padding: 6px 8px; color: #F87171;">0.0 days</td>
                <td style="padding: 6px 8px;"><span style="background: #991B1B; padding: 2px 6px; border-radius: 4px; font-size: 10px;">ORDER NOW</span></td>
              </tr>
              <tr>
                <td style="padding: 6px 8px;">Fish fillet</td>
                <td style="padding: 6px 8px; color: #F87171;">0 kg</td>
                <td style="padding: 6px 8px; color: #F87171;">0.0 days</td>
                <td style="padding: 6px 8px;"><span style="background: #991B1B; padding: 2px 6px; border-radius: 4px; font-size: 10px;">ORDER NOW</span></td>
              </tr>
              <tr>
                <td style="padding: 6px 8px;">Basmati rice</td>
                <td style="padding: 6px 8px;">34 kg</td>
                <td style="padding: 6px 8px;">6.2 days</td>
                <td style="padding: 6px 8px;"><span style="background: #065F46; padding: 2px 6px; border-radius: 4px; font-size: 10px;">SAFE</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function renderAppShell(contentHtml) {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'meals', label: 'Meal Forecast' },
    { id: 'ingredients', label: 'Ingredient Forecast' },
    { id: 'orders', label: 'Orders' },
    { id: 'inventory', label: 'Inventory' },
    { id: 'whatif', label: 'What-if' },
    { id: 'reports', label: 'Reports' },
    { id: 'upload', label: 'Data Upload' },
    { id: 'model', label: 'Model' },
    { id: 'settings', label: 'Settings' }
  ];
  
  return `
    <div class="app-layout">
      <aside class="sidebar">
        <div class="sidebar-header">
          <div class="sidebar-brand">Smart Kitchen</div>
          <div class="sidebar-tagline">Ingredient Planning System</div>
        </div>
        <nav class="sidebar-nav">
          ${navItems.map(item => `
            <div class="nav-item ${state.currentPage === item.id ? 'active' : ''}" onclick="navigateTo('${item.id}')">
              ${item.label}
            </div>
          `).join('')}
        </nav>
        <div class="sidebar-footer">
          <div>User: ${state.user?.email || ''}</div>
          <button class="btn btn-secondary btn-sm" onclick="logout()" style="margin-top: 8px; width: 100%;">Sign out</button>
        </div>
      </aside>
      
      <div class="main-wrapper">
        <header class="top-bar">
          <div class="top-bar-left">
            <span class="restaurant-name">${state.restaurant?.name || 'Restaurant'}</span>
            <span class="last-updated">Last updated: ${state.restaurant?.last_updated || 'Just now'}</span>
          </div>
          <div class="top-bar-right">
            <button class="btn btn-secondary btn-sm" onclick="loadSampleData()">Load sample data</button>
          </div>
        </header>
        
        <main class="content-body">
          ${state.loading ? `
            <div class="state-box">
              <div class="spinner"></div>
              <p class="state-desc" style="margin-top: 12px;">Calculating data and forecasts...</p>
            </div>
          ` : (state.error ? `
            <div class="panel">
              <div class="badge badge-red" style="padding: 10px; width: 100%;">Error: ${state.error}</div>
              <button class="btn btn-secondary btn-sm" onclick="refreshCurrentPageData()" style="margin-top: 12px;">Retry</button>
            </div>
          ` : contentHtml)}
        </main>
      </div>
    </div>
  `;
}

// --- Specific Pages ---
function renderDashboard() {
  const d = state.dashboardData;
  if (!d) return '<div class="state-box"><div class="spinner"></div></div>';
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Operational Dashboard</h1>
        <p class="page-desc">Overview of ingredient demand, order deadlines, and risk factors.</p>
      </div>
    </div>
    
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Items at Risk</div>
        <div class="kpi-value" style="color: ${d.kpis.items_at_risk > 0 ? 'var(--status-red)' : 'var(--navy)'};">
          ${d.kpis.items_at_risk}
        </div>
        <div class="kpi-subtext">Immediate reorder or expiry warning</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Orders Due Today</div>
        <div class="kpi-value" style="color: ${d.kpis.orders_due_today > 0 ? 'var(--status-amber)' : 'var(--navy)'};">
          ${d.kpis.orders_due_today}
        </div>
        <div class="kpi-subtext">Required order placement today</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Expected Waste (7 Days)</div>
        <div class="kpi-value">${formatCurrency(d.kpis.expected_waste_inr)}</div>
        <div class="kpi-subtext">Unused expiring batches cost</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Forecast Accuracy</div>
        <div class="kpi-value" style="color: var(--teal);">${d.kpis.forecast_accuracy}</div>
        <div class="kpi-subtext">Model validation benchmark</div>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">7-Day Projected Total Orders</div>
      </div>
      ${renderBarChart(d.orders_chart, 'date', 'total_orders', 220)}
    </div>
    
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Order Now (Urgent Deadlines)</div>
          <button class="btn btn-secondary btn-sm" onclick="navigateTo('orders')">View all</button>
        </div>
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Ingredient</th>
                <th class="text-right">Qty</th>
                <th>Unit</th>
                <th class="text-right">Cost</th>
                <th>Reason</th>
              </tr>
            </thead>
            <tbody>
              ${d.orders_now.slice(0, 6).map(o => `
                <tr>
                  <td><b>${o.ingredient}</b></td>
                  <td class="text-right">${o.quantity}</td>
                  <td>${o.unit}</td>
                  <td class="text-right">${formatCurrency(o.cost_inr)}</td>
                  <td><span class="badge ${o.is_late ? 'badge-red' : 'badge-amber'}">${o.is_late ? 'LATE' : 'DUE TODAY'}</span></td>
                </tr>
              `).join('')}
              ${d.orders_now.length === 0 ? '<tr><td colspan="5" class="text-center">No orders due today</td></tr>' : ''}
            </tbody>
          </table>
        </div>
      </div>
      
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Use First (Expiring Batches)</div>
          <button class="btn btn-secondary btn-sm" onclick="navigateTo('inventory')">View stock</button>
        </div>
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Ingredient</th>
                <th class="text-right">Batch Qty</th>
                <th>Earliest Expiry</th>
                <th class="text-right">Est. Waste</th>
              </tr>
            </thead>
            <tbody>
              ${d.use_first.map(u => `
                <tr>
                  <td><b>${u.ingredient}</b></td>
                  <td class="text-right">${u.qty_in_earliest_batch || u.stock_on_hand} ${u.unit}</td>
                  <td>${formatDate(u.earliest_expiry_date)}</td>
                  <td class="text-right" style="color: ${u.waste_inr_7d > 0 ? 'var(--status-red)' : 'inherit'};">
                    ${formatCurrency(u.waste_inr_7d)}
                  </td>
                </tr>
              `).join('')}
              ${d.use_first.length === 0 ? '<tr><td colspan="4" class="text-center">No expiring stock</td></tr>' : ''}
            </tbody>
          </table>
        </div>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Active Operational Alerts</div>
      </div>
      <div>
        ${d.alerts.map(a => `
          <div class="alert-card ${a.severity}">
            <div>
              <div class="alert-title">${a.title}</div>
              <div class="alert-msg">${a.message}</div>
            </div>
          </div>
        `).join('')}
        ${d.alerts.length === 0 ? '<p class="state-desc">All inventory levels and orders are operating normally.</p>' : ''}
      </div>
    </div>
  `;
}

function renderMealForecast() {
  const d = state.mealForecastData;
  if (!d) return '<div class="state-box"><div class="spinner"></div></div>';
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Meal Demand Forecast</h1>
        <p class="page-desc">7-day expected meal order counts generated by LightGBM/Poisson models.</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-secondary btn-sm" onclick="exportCurrentGrid('Meal_Forecast', ['meal_name', 'category', 'cuisine', 'base_price', 'total_predicted_orders'], d.meals)">Export to Excel</button>
      </div>
    </div>
    
    <div class="panel" style="padding: 12px 16px; margin-bottom: 16px;">
      <div style="display: flex; gap: 16px; align-items: center; flex-wrap: wrap;">
        <div>
          <label class="form-label">Category</label>
          <select id="meal-filter-cat" class="form-select" onchange="refreshCurrentPageData()" style="height: 32px; font-size: 12px;">
            <option value="">All Categories</option>
            ${d.categories.map(c => `<option value="${c}">${c}</option>`).join('')}
          </select>
        </div>
        <div>
          <label class="form-label">Cuisine</label>
          <select id="meal-filter-cui" class="form-select" onchange="refreshCurrentPageData()" style="height: 32px; font-size: 12px;">
            <option value="">All Cuisines</option>
            ${d.cuisines.map(c => `<option value="${c}">${c}</option>`).join('')}
          </select>
        </div>
      </div>
    </div>
    
    ${state.selectedMealHistory ? `
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Demand Trend: ${state.selectedMealHistory.mealName} (Past 28 Days Actual vs 7-Day Forecast)</div>
          <button class="btn btn-secondary btn-sm" onclick="state.selectedMealHistory = null; render();">Close Chart</button>
        </div>
        ${renderLineChart(state.selectedMealHistory.chartData, 'date', ['orders'], 240)}
      </div>
    ` : ''}
    
    <div class="panel">
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Meal Name</th>
              <th>Category</th>
              <th>Cuisine</th>
              <th class="text-right">Base Price</th>
              ${d.dates.map(date => `<th class="text-right">${formatDate(date)}</th>`).join('')}
              <th class="text-right">Total 7D</th>
            </tr>
          </thead>
          <tbody>
            ${d.meals.map(m => `
              <tr onclick="loadMealChart(${m.meal_id}, '${m.meal_name}')" style="cursor: pointer;">
                <td><b>${m.meal_name}</b></td>
                <td>${m.category}</td>
                <td>${m.cuisine}</td>
                <td class="text-right">${formatCurrency(m.base_price)}</td>
                ${d.dates.map(date => {
                  const day = m.days[date] || { expected: 0, low: 0, high: 0 };
                  return `
                    <td class="text-right hover-tooltip" data-tooltip="Low: ${day.low} | Exp: ${day.expected} | High: ${day.high} (${day.confidence})">
                      ${day.expected}
                    </td>
                  `;
                }).join('')}
                <td class="text-right"><b>${m.total_predicted_orders}</b></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

async function loadMealChart(mealId, mealName) {
  try {
    const data = await apiCall(`/api/forecast/meal-history/${mealId}`);
    const chartData = [];
    data.history.forEach(h => chartData.push({ date: h.date, orders: h.num_orders, type: 'actual' }));
    data.forecast.forEach(f => chartData.push({ date: f.date, orders: f.predicted_orders, type: 'forecast' }));
    state.selectedMealHistory = { mealId, mealName, chartData };
    render();
  } catch (err) {
    showToast('Failed to load meal trend: ' + err.message);
  }
}

function renderIngredientForecast() {
  const d = state.ingredientForecastData;
  if (!d) return '<div class="state-box"><div class="spinner"></div></div>';
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Ingredient Forecast & Requirements</h1>
        <p class="page-desc">Aggregated ingredient demand calculated directly from recipe multiplication.</p>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="exportCurrentGrid('Ingredient_Forecast', ['ingredient', 'group', 'unit', 'unit_cost_inr', 'total_7d', 'total_cost_7d'], d.ingredients)">Export to Excel</button>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">7-Day Projected Expenditure by Category (INR)</div>
      </div>
      ${renderBarChart(d.stacked_chart, 'date', 'Proteins', 220)}
    </div>
    
    ${state.selectedIngredientDrilldown ? `
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Meal Breakdown for: ${state.selectedIngredientDrilldown.ingredient}</div>
          <button class="btn btn-secondary btn-sm" onclick="state.selectedIngredientDrilldown = null; render();">Close Breakdown</button>
        </div>
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Driving Meal</th>
                <th class="text-right">Qty / Serving</th>
                <th class="text-right">7D Projected Servings</th>
                <th class="text-right">Total Ingredient Demand</th>
              </tr>
            </thead>
            <tbody>
              ${state.selectedIngredientDrilldown.meals.map(m => `
                <tr>
                  <td><b>${m.meal_name}</b></td>
                  <td class="text-right">${m.qty_per_serving}</td>
                  <td class="text-right">${m.total_orders_7d}</td>
                  <td class="text-right"><b>${m.total_qty_7d}</b></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    ` : ''}
    
    <div class="panel">
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th>Group</th>
              <th>Unit</th>
              <th class="text-right">Unit Cost</th>
              ${d.dates.map(date => `<th class="text-right">${formatDate(date)}</th>`).join('')}
              <th class="text-right">Total 7D</th>
              <th class="text-right">Total Cost</th>
            </tr>
          </thead>
          <tbody>
            ${d.ingredients.map(ing => `
              <tr onclick="drilldownIngredient('${ing.ingredient}')" style="cursor: pointer;">
                <td><b>${ing.ingredient}</b></td>
                <td><span class="badge badge-neutral">${ing.group}</span></td>
                <td>${ing.unit}</td>
                <td class="text-right">${formatCurrency(ing.unit_cost_inr)}</td>
                ${d.dates.map(date => {
                  const day = ing.days[date] || { expected: 0 };
                  return `<td class="text-right">${day.expected}</td>`;
                }).join('')}
                <td class="text-right"><b>${ing.total_7d}</b></td>
                <td class="text-right">${formatCurrency(ing.total_cost_7d)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function drilldownIngredient(ingName) {
  const d = state.ingredientForecastData;
  if (!d || !d.drill_down[ingName]) return;
  state.selectedIngredientDrilldown = {
    ingredient: ingName,
    meals: d.drill_down[ingName]
  };
  render();
}

function renderOrders() {
  const d = state.ordersData;
  if (!d) return '<div class="state-box"><div class="spinner"></div></div>';
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Purchase Order Recommendations</h1>
        <p class="page-desc">Automated replenishment calibrated to supplier lead times and coverage windows.</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <a href="/api/reports/purchase-orders/excel" target="_blank" class="btn btn-secondary btn-sm">Download PO (Excel)</a>
        <a href="/api/reports/purchase-orders/pdf" target="_blank" class="btn btn-secondary btn-sm">Download PO (PDF)</a>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title" style="color: var(--status-red);">Order Now (Deadline Today or Imminent)</div>
      </div>
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th>Lead Time</th>
              <th class="text-right">Order Qty</th>
              <th>Unit</th>
              <th class="text-right">Unit Cost</th>
              <th class="text-right">Total Cost</th>
              <th>Order By</th>
              <th>Expected Arrival</th>
              <th>Status / Reason</th>
            </tr>
          </thead>
          <tbody>
            ${d.orders_now.map(o => `
              <tr>
                <td><b>${o.ingredient}</b></td>
                <td>${o.lead_time_days} days</td>
                <td class="text-right"><b>${o.quantity}</b></td>
                <td>${o.unit}</td>
                <td class="text-right">${formatCurrency(o.unit_cost_inr)}</td>
                <td class="text-right"><b>${formatCurrency(o.cost_inr)}</b></td>
                <td><b>${formatDate(o.order_by_date)}</b></td>
                <td>${formatDate(o.arrival_date)}</td>
                <td><span class="badge ${o.is_late ? 'badge-red' : 'badge-amber'}">${o.reason}</span></td>
              </tr>
            `).join('')}
            ${d.orders_now.length === 0 ? '<tr><td colspan="9" class="text-center">No immediate orders required</td></tr>' : ''}
          </tbody>
        </table>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Order Soon (Upcoming Schedule)</div>
      </div>
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th>Lead Time</th>
              <th class="text-right">Order Qty</th>
              <th>Unit</th>
              <th class="text-right">Unit Cost</th>
              <th class="text-right">Total Cost</th>
              <th>Order By</th>
              <th>Expected Arrival</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            ${d.orders_soon.map(o => `
              <tr>
                <td><b>${o.ingredient}</b></td>
                <td>${o.lead_time_days} days</td>
                <td class="text-right">${o.quantity}</td>
                <td>${o.unit}</td>
                <td class="text-right">${formatCurrency(o.unit_cost_inr)}</td>
                <td class="text-right">${formatCurrency(o.cost_inr)}</td>
                <td>${formatDate(o.order_by_date)}</td>
                <td>${formatDate(o.arrival_date)}</td>
                <td>${o.reason}</td>
              </tr>
            `).join('')}
            ${d.orders_soon.length === 0 ? '<tr><td colspan="9" class="text-center">No upcoming orders</td></tr>' : ''}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderInventory() {
  const d = state.inventoryData;
  if (!d) return '<div class="state-box"><div class="spinner"></div></div>';
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Current Inventory & Stock Simulation</h1>
        <p class="page-desc">FIFO stock tracking, batch shelf-life projection, and stock-out prevention.</p>
      </div>
      <button class="btn btn-secondary btn-sm" onclick="exportCurrentGrid('Current_Inventory', ['ingredient', 'group', 'unit', 'stock_on_hand', 'earliest_expiry_date', 'days_of_cover', 'status'], d.inventory)">Export to Excel</button>
    </div>
    
    <div class="panel" style="background: #F8FAFC; border-left: 4px solid var(--navy);">
      <p style="font-size: 13px; color: var(--navy); font-weight: 500;">
        <b>Operational FIFO Assumption:</b> Only earliest batch expiry is known. Remaining stock is assumed to expire on <code>as_of_date + shelf_life_days / 2</code> (never earlier than the earliest batch).
      </p>
    </div>
    
    <div class="panel">
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th>Group</th>
              <th>Unit</th>
              <th class="text-right">Stock on Hand</th>
              <th>Earliest Expiry</th>
              <th class="text-right">Batch Qty</th>
              <th class="text-right">In Transit</th>
              <th>Arrival Date</th>
              <th class="text-right">Days of Cover</th>
              <th>Status</th>
              <th>7-Day Projected Stock</th>
            </tr>
          </thead>
          <tbody>
            ${d.inventory.map(item => `
              <tr>
                <td><b>${item.ingredient}</b></td>
                <td><span class="badge badge-neutral">${item.group}</span></td>
                <td>${item.unit}</td>
                <td class="text-right" style="color: ${item.stock_on_hand <= 0 ? 'var(--status-red)' : 'inherit'}; font-weight: ${item.stock_on_hand <= 0 ? '700' : 'normal'};">
                  ${item.stock_on_hand}
                </td>
                <td>${formatDate(item.earliest_expiry_date) || '-'}</td>
                <td class="text-right">${item.qty_in_earliest_batch || '-'}</td>
                <td class="text-right">${item.order_in_transit_qty || 0}</td>
                <td>${formatDate(item.order_arrival_date) || '-'}</td>
                <td class="text-right"><b>${item.days_of_cover} d</b></td>
                <td><span class="badge badge-${item.status}">${item.risk_label}</span></td>
                <td style="font-size: 11px; color: var(--text-secondary);">
                  ${item.projected_stock_line.map(p => Math.round(p.stock)).join(' → ')}
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderWhatIf() {
  const w = state.whatif;
  const sim = w.simulationResult;
  const mealsList = state.mealForecastData?.meals || [];
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Interactive What-if Planning</h1>
        <p class="page-desc">Simulate demand sensitivity and ingredient order impact in real time without altering database records.</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <button class="btn btn-secondary btn-sm" onclick="resetWhatIf()">Reset</button>
        <button class="btn btn-primary btn-sm" onclick="applyWhatIfToPlan()" ${!sim ? 'disabled' : ''}>Apply to Plan</button>
      </div>
    </div>
    
    <div style="display: grid; grid-template-columns: 360px 1fr; gap: 20px;">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Scenario Parameters</div>
        </div>
        <div class="form-group">
          <label class="form-label">Meal</label>
          <select class="form-select" onchange="state.whatif.mealId = Number(this.value); runWhatIfSimulation();">
            ${mealsList.map(m => `
              <option value="${m.meal_id}" ${m.meal_id === w.mealId ? 'selected' : ''}>${m.meal_name} (${m.category})</option>
            `).join('')}
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">Date</label>
          <input type="date" class="form-input" value="${w.date}" onchange="state.whatif.date = this.value; runWhatIfSimulation();" />
        </div>
        <div class="form-group">
          <label class="form-label">Checkout Price (INR): <span id="price-val">${w.checkoutPrice}</span></label>
          <input type="range" min="50" max="600" step="10" value="${w.checkoutPrice}" 
            oninput="document.getElementById('price-val').innerText = this.value; state.whatif.checkoutPrice = this.value;"
            onchange="runWhatIfSimulation();" style="width: 100%;" />
        </div>
        <div class="form-group" style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="promo-toggle" ${w.promoActive ? 'checked' : ''} onchange="state.whatif.promoActive = this.checked ? 1 : 0; runWhatIfSimulation();" />
          <label for="promo-toggle" style="font-size: 13px; font-weight: 500;">Promotional Campaign Active</label>
        </div>
        <div class="form-group" style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="featured-toggle" ${w.featuredOnMenu ? 'checked' : ''} onchange="state.whatif.featuredOnMenu = this.checked ? 1 : 0; runWhatIfSimulation();" />
          <label for="featured-toggle" style="font-size: 13px; font-weight: 500;">Featured on Daily Menu</label>
        </div>
        <div class="form-group" style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="festival-toggle" ${w.festivalOrEvent ? 'checked' : ''} onchange="state.whatif.festivalOrEvent = this.checked ? 1 : 0; runWhatIfSimulation();" />
          <label for="festival-toggle" style="font-size: 13px; font-weight: 500;">Festival or Local Event</label>
        </div>
      </div>
      
      <div>
        ${sim ? `
          <div class="kpi-grid" style="grid-template-columns: repeat(3, 1fr);">
            <div class="kpi-card">
              <div class="kpi-label">Baseline Orders</div>
              <div class="kpi-value">${sim.forecast_comparison.original_orders}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Simulated Orders</div>
              <div class="kpi-value" style="color: var(--teal);">${sim.forecast_comparison.simulated_orders}</div>
            </div>
            <div class="kpi-card">
              <div class="kpi-label">Delta Demand</div>
              <div class="kpi-value" style="color: ${sim.forecast_comparison.delta_orders >= 0 ? 'var(--status-green)' : 'var(--status-red)'};">
                ${sim.forecast_comparison.delta_orders >= 0 ? '+' : ''}${sim.forecast_comparison.delta_orders} (${sim.forecast_comparison.pct_change}%)
              </div>
            </div>
          </div>
          
          <div class="panel">
            <div class="panel-header">
              <div class="panel-title">Ingredient Requirement Impacts</div>
            </div>
            <div class="table-responsive">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Ingredient</th>
                    <th>Unit</th>
                    <th class="text-right">Qty / Serving</th>
                    <th class="text-right">Baseline Need</th>
                    <th class="text-right">Simulated Need</th>
                    <th class="text-right">Delta Qty</th>
                    <th class="text-right">Delta Cost</th>
                  </tr>
                </thead>
                <tbody>
                  ${sim.ingredient_impacts.map(i => `
                    <tr>
                      <td><b>${i.ingredient}</b></td>
                      <td>${i.unit}</td>
                      <td class="text-right">${i.qty_per_serving}</td>
                      <td class="text-right">${i.original_need}</td>
                      <td class="text-right"><b>${i.simulated_need}</b></td>
                      <td class="text-right" style="color: ${i.delta_qty >= 0 ? 'var(--status-green)' : 'var(--status-red)'};">
                        ${i.delta_qty >= 0 ? '+' : ''}${i.delta_qty}
                      </td>
                      <td class="text-right" style="color: ${i.delta_cost_inr >= 0 ? 'var(--status-green)' : 'var(--status-red)'};">
                        ${i.delta_cost_inr >= 0 ? '+' : ''}${formatCurrency(i.delta_cost_inr)}
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        ` : '<div class="state-box"><p class="state-desc">Select parameters to calculate what-if simulation.</p></div>'}
      </div>
    </div>
  `;
}

function renderReports() {
  const d = state.savingsData;
  if (!d) return '<div class="state-box"><div class="spinner"></div></div>';
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Executive Savings & Performance Report</h1>
        <p class="page-desc">Comparative audit against historical fixed ordering records in Inventory_History.</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <a href="/api/reports/purchase-orders/excel" target="_blank" class="btn btn-secondary btn-sm">Export PO (Excel)</a>
        <a href="/api/reports/purchase-orders/pdf" target="_blank" class="btn btn-secondary btn-sm">Export PO (PDF)</a>
      </div>
    </div>
    
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Historical Scrap (150 Days)</div>
        <div class="kpi-value" style="color: var(--status-red);">${formatCurrency(d.historical_total_waste_inr)}</div>
        <div class="kpi-subtext">Avg: ${formatCurrency(d.historical_weekly_waste_inr)} / week</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Planned Waste (7 Days)</div>
        <div class="kpi-value" style="color: var(--teal);">${formatCurrency(d.planned_weekly_waste_inr)}</div>
        <div class="kpi-subtext">Controlled via dynamic safety buffers</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Estimated Weekly Savings</div>
        <div class="kpi-value" style="color: var(--status-green);">${formatCurrency(d.weekly_rupees_saved)}</div>
        <div class="kpi-subtext">Scrap reduction + margin protection</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Stock-out Incidents</div>
        <div class="kpi-value">${d.historical_stockout_days} historical days</div>
        <div class="kpi-subtext">Eliminated via lead-time order-by rules</div>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Audit Methodology</div>
      </div>
      <p style="font-size: 13px; line-height: 1.6; color: var(--text-secondary);">
        ${d.methodology}
      </p>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Top Historically Wasted Ingredients</div>
      </div>
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Ingredient</th>
              <th class="text-right">Historical Scrap Loss</th>
            </tr>
          </thead>
          <tbody>
            ${d.top_wasted_ingredients.map(w => `
              <tr>
                <td><b>${w.ingredient}</b></td>
                <td class="text-right" style="color: var(--status-red);"><b>${formatCurrency(w.waste_cost_inr)}</b></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderUpload() {
  const u = state.upload;
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Data Upload & Spreadsheet Management</h1>
        <p class="page-desc">Import, inspect, and edit kitchen operational records with immediate validation.</p>
      </div>
      <div style="display: flex; gap: 8px;">
        <a href="/api/data/template/${u.activeSheet}" class="btn btn-secondary btn-sm">Download ${u.activeSheet} Template</a>
        <button class="btn btn-secondary btn-sm" onclick="exportCurrentGrid(u.activeSheet, u.gridColumns, u.gridData)">Export to Excel</button>
      </div>
    </div>
    
    <div class="panel" style="padding: 16px; margin-bottom: 20px;">
      <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
        <div>
          <label class="form-label">Drop File (.xlsx or .csv)</label>
          <input type="file" accept=".xlsx, .csv" onchange="if(this.files[0]) handleFileUpload(this.files[0])" />
        </div>
        <button class="btn btn-secondary btn-sm" onclick="loadSampleData()">Reload Default Sample Data</button>
      </div>
    </div>
    
    <div class="panel" style="margin-bottom: 20px;">
      <div class="panel-header">
        <div class="panel-title">Add Today's Data (Fast Daily Entry)</div>
      </div>
      <p style="font-size: 12px; color: var(--text-secondary); margin-bottom: 12px;">
        Submitting daily orders and closing stock counts moves "today" forward and automatically retrains models in the background.
      </p>
      <div style="display: flex; gap: 12px; align-items: flex-end;">
        <div>
          <label class="form-label">Operational Date</label>
          <input id="add-today-date" type="date" class="form-input" value="2026-10-29" style="height: 32px;" />
        </div>
        <button class="btn btn-primary btn-sm" onclick="submitQuickToday()">Submit & Advance Day</button>
      </div>
    </div>
    
    <div class="panel">
      <div style="display: flex; gap: 8px; border-bottom: 1px solid var(--border-card); padding-bottom: 12px; margin-bottom: 16px; overflow-x: auto;">
        ${u.sheets.map(s => `
          <button class="btn ${s === u.activeSheet ? 'btn-primary' : 'btn-secondary'} btn-sm" onclick="loadSheetData('${s}')">
            ${s}
          </button>
        `).join('')}
      </div>
      
      <div style="display: flex; gap: 8px; margin-bottom: 12px; align-items: center;">
        <button class="btn btn-secondary btn-sm" onclick="handleGridAddRow()">+ Add Row</button>
        <button class="btn btn-danger btn-sm" onclick="handleGridDeleteRow()">Delete Row</button>
        <button class="btn btn-secondary btn-sm" onclick="handleGridUndo()">Undo</button>
        <button class="btn btn-secondary btn-sm" onclick="handleValidateSheet()">Validate</button>
        <button class="btn btn-primary btn-sm" onclick="handleSaveSheet()" style="margin-left: auto;">Save to Database</button>
      </div>
      
      ${u.validationErrors.length > 0 ? `
        <div class="panel" style="background: var(--status-red-bg); border-color: var(--status-red); padding: 12px; margin-bottom: 12px;">
          <div style="font-weight: 700; color: var(--status-red); margin-bottom: 6px;">Validation Errors Detected (${u.validationErrors.length}):</div>
          <ul style="font-size: 12px; color: var(--status-red); padding-left: 20px;">
            ${u.validationErrors.slice(0, 8).map(err => `<li>${err}</li>`).join('')}
            ${u.validationErrors.length > 8 ? `<li>...and ${u.validationErrors.length - 8} more errors</li>` : ''}
          </ul>
        </div>
      ` : ''}
      
      <div class="table-responsive" style="max-height: 480px;">
        <table class="data-table">
          <thead>
            <tr>
              <th style="width: 40px;">#</th>
              ${u.gridColumns.map(col => `<th>${col}</th>`).join('')}
            </tr>
          </thead>
          <tbody>
            ${u.gridData.map((row, rIdx) => `
              <tr class="${u.selectedRowIndex === rIdx ? 'selected' : ''}" onclick="state.upload.selectedRowIndex = ${rIdx}; render();" style="background: ${u.selectedRowIndex === rIdx ? '#E2E8F0' : 'transparent'};">
                <td style="color: var(--text-muted); font-size: 11px;">${rIdx + 1}</td>
                ${u.gridColumns.map(col => `
                  <td contenteditable="true" onblur="handleGridCellEdit(${rIdx}, '${col}', this.innerText)" style="outline: none;">
                    ${row[col] !== null && row[col] !== undefined ? row[col] : ''}
                  </td>
                `).join('')}
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

async function submitQuickToday() {
  const dVal = document.getElementById('add-today-date').value;
  try {
    state.loading = true;
    render();
    const res = await apiCall('/api/data/add-today', {
      method: 'POST',
      body: JSON.stringify({
        date: dVal,
        orders: [],
        stocks: []
      })
    });
    showToast(res.message);
    await refreshCurrentPageData();
  } catch (err) {
    showToast('Failed to record day: ' + err.message);
  } finally {
    state.loading = false;
    render();
  }
}

function renderModel() {
  const m = state.modelData;
  if (!m || m.status === 'no_model') {
    return `
      <div class="page-header">
        <h1 class="page-title">Machine Learning Model Architecture</h1>
      </div>
      <div class="panel">
        <p class="state-desc">No trained model available yet.</p>
        <button class="btn btn-primary btn-sm" onclick="retrainModelNow()" style="margin-top: 12px;">Train Model Now</button>
      </div>
    `;
  }
  
  return `
    <div class="page-header">
      <div>
        <h1 class="page-title">Machine Learning Model Architecture</h1>
        <p class="page-desc">Poisson Gradient Tree Boosting with time-based validation and prediction intervals.</p>
      </div>
      <button class="btn btn-primary btn-sm" onclick="retrainModelNow()">Retrain Now</button>
    </div>
    
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Active Model Version</div>
        <div class="kpi-value" style="font-size: 18px;">${m.version}</div>
        <div class="kpi-subtext">Trained: ${m.trained_at}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Validation WAPE</div>
        <div class="kpi-value" style="color: var(--teal);">${m.metrics?.overall?.wape}%</div>
        <div class="kpi-subtext">Weighted Absolute Percentage Error</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Validation MAE</div>
        <div class="kpi-value">${m.metrics?.overall?.mae}</div>
        <div class="kpi-subtext">Mean Absolute Error (Meals)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Validation MAPE</div>
        <div class="kpi-value">${m.metrics?.overall?.mape}%</div>
        <div class="kpi-subtext">Excludes zero-order days</div>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">Baseline Comparison (Validation Set)</div>
      </div>
      <div class="table-responsive">
        <table class="data-table">
          <thead>
            <tr>
              <th>Model / Benchmark Strategy</th>
              <th class="text-right">MAE</th>
              <th class="text-right">WAPE</th>
              <th class="text-right">MAPE</th>
              <th>Status vs Baseline</th>
            </tr>
          </thead>
          <tbody>
            <tr style="background: var(--teal-light); font-weight: 600;">
              <td><b>Poisson Gradient Boosting (Active Model)</b></td>
              <td class="text-right">${m.metrics?.overall?.mae}</td>
              <td class="text-right">${m.metrics?.overall?.wape}%</td>
              <td class="text-right">${m.metrics?.overall?.mape}%</td>
              <td><span class="badge badge-green">OPTIMAL</span></td>
            </tr>
            <tr>
              <td>Baseline 1: Same Weekday Last Week (Lag-7)</td>
              <td class="text-right">${m.baselines?.baseline_weekday_lag7?.mae}</td>
              <td class="text-right">${m.baselines?.baseline_weekday_lag7?.wape}%</td>
              <td class="text-right">${m.baselines?.baseline_weekday_lag7?.mape}%</td>
              <td><span class="badge badge-neutral">Beaten (+${m.baselines?.model_vs_b1_wape_gain}% WAPE)</span></td>
            </tr>
            <tr>
              <td>Baseline 2: 28-Day Rolling Average</td>
              <td class="text-right">${m.baselines?.baseline_rolling_28d?.mae}</td>
              <td class="text-right">${m.baselines?.baseline_rolling_28d?.wape}%</td>
              <td class="text-right">${m.baselines?.baseline_rolling_28d?.mape}%</td>
              <td><span class="badge badge-neutral">Beaten (+${m.baselines?.model_vs_b2_wape_gain}% WAPE)</span></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
    
    <div class="panel">
      <div class="panel-header">
        <div class="panel-title">14-Day Validation Period: Actual vs Predicted Aggregate Orders</div>
      </div>
      ${renderLineChart(m.validation_chart, 'date', ['actual', 'predicted', 'baseline_lag7'], 240)}
    </div>
    
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Normalized Feature Importance</div>
        </div>
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Feature Name</th>
                <th class="text-right">Relative Weight</th>
              </tr>
            </thead>
            <tbody>
              ${Object.entries(m.feature_importances || {}).sort((a,b) => b[1] - a[1]).slice(0, 10).map(([k, v]) => `
                <tr>
                  <td><b>${k}</b></td>
                  <td class="text-right">${(v * 100).toFixed(1)}%</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
      
      <div class="panel">
        <div class="panel-header">
          <div class="panel-title">Model Version History (Last 5)</div>
        </div>
        <div class="table-responsive">
          <table class="data-table">
            <thead>
              <tr>
                <th>Version</th>
                <th>Trained At</th>
                <th class="text-right">WAPE</th>
                <th class="text-right">MAE</th>
              </tr>
            </thead>
            <tbody>
              ${(m.history_versions || []).map(v => `
                <tr>
                  <td><b>${v.version}</b></td>
                  <td>${v.trained_at}</td>
                  <td class="text-right">${v.wape}%</td>
                  <td class="text-right">${v.mae}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

async function retrainModelNow() {
  state.loading = true;
  render();
  try {
    const res = await apiCall('/api/model/retrain', { method: 'POST' });
    showToast(`Retrained model ${res.version} successfully. WAPE: ${res.metrics.overall.wape}%`);
    await refreshCurrentPageData();
  } catch (err) {
    showToast('Retraining failed: ' + err.message);
  } finally {
    state.loading = false;
    render();
  }
}

function renderSettings() {
  const s = state.settingsData || {};
  return `
    <div class="page-header">
      <h1 class="page-title">Notification & Operational Settings</h1>
    </div>
    
    <div class="panel" style="max-width: 600px;">
      <form onsubmit="handleSaveSettings(event)">
        <div class="form-group" style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="set-alerts-enabled" ${s.email_alerts_enabled ? 'checked' : ''} />
          <label for="set-alerts-enabled" style="font-size: 13px; font-weight: 600;">Enable Email Alert Notifications</label>
        </div>
        <div class="form-group">
          <label class="form-label">Alert Email Address</label>
          <input id="set-email" class="form-input" value="${s.alert_email || state.user?.email || ''}" />
        </div>
        <div class="form-group" style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="set-notify-stockout" ${s.notify_stockout !== 0 ? 'checked' : ''} />
          <label for="set-notify-stockout" style="font-size: 13px;">Stock-out Risk Warnings</label>
        </div>
        <div class="form-group" style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="set-notify-expiry" ${s.notify_expiry !== 0 ? 'checked' : ''} />
          <label for="set-notify-expiry" style="font-size: 13px;">Batch Expiry Warnings</label>
        </div>
        <div class="form-group" style="display: flex; align-items: center; gap: 8px;">
          <input type="checkbox" id="set-notify-arrival" ${s.notify_arrival !== 0 ? 'checked' : ''} />
          <label for="set-notify-arrival" style="font-size: 13px;">Supplier Order Delivery Confirmations</label>
        </div>
        <button type="submit" class="btn btn-primary" style="margin-top: 12px;">Save Settings</button>
      </form>
    </div>
  `;
}

async function handleSaveSettings(e) {
  e.preventDefault();
  try {
    await apiCall('/api/settings', {
      method: 'POST',
      body: JSON.stringify({
        email_alerts_enabled: document.getElementById('set-alerts-enabled').checked,
        alert_email: document.getElementById('set-email').value,
        notify_stockout: document.getElementById('set-notify-stockout').checked,
        notify_expiry: document.getElementById('set-notify-expiry').checked,
        notify_arrival: document.getElementById('set-notify-arrival').checked
      })
    });
    showToast('Settings saved successfully.');
  } catch (err) {
    showToast('Failed to save settings: ' + err.message);
  }
}

// --- Main App Root Renderer ---
function render() {
  const root = document.getElementById('app-root');
  if (!root) return;
  
  if (!state.token) {
    root.innerHTML = renderAuth();
    return;
  }
  
  let pageHtml = '';
  switch (state.currentPage) {
    case 'dashboard':
      pageHtml = renderDashboard();
      break;
    case 'meals':
      pageHtml = renderMealForecast();
      break;
    case 'ingredients':
      pageHtml = renderIngredientForecast();
      break;
    case 'orders':
      pageHtml = renderOrders();
      break;
    case 'inventory':
      pageHtml = renderInventory();
      break;
    case 'whatif':
      pageHtml = renderWhatIf();
      break;
    case 'reports':
      pageHtml = renderReports();
      break;
    case 'upload':
      pageHtml = renderUpload();
      break;
    case 'model':
      pageHtml = renderModel();
      break;
    case 'settings':
      pageHtml = renderSettings();
      break;
    default:
      pageHtml = renderDashboard();
  }
  
  root.innerHTML = renderAppShell(pageHtml);
}

// --- Initialization ---
window.addEventListener('DOMContentLoaded', () => {
  render();
  if (state.token) {
    refreshCurrentPageData();
  }
});
