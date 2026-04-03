// frontend/js/utils.js
/**
 * Shared utilities for SRM AI SETU Frontend
 */

// ── Authentication ──
function requireAuth() {
    const token = sessionStorage.getItem('access_token');
    if (!token) {
        window.location.replace('index.html');
        if (window.ApiClient && typeof window.ApiClient.clearTokens === 'function') {
            window.ApiClient.clearTokens();
        } else {
            sessionStorage.removeItem('access_token');
            sessionStorage.removeItem('refresh_token');
            sessionStorage.removeItem('srm_user');
        }
        return false;
    }
    return true;
}

// ── UI Components ──

/**
 * Shows a toast notification
 * @param {string} msg 
 * @param {'success' | 'error' | 'warning' | 'info'} type 
 */
function showToast(msg, type = 'success') {
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);

        // Add styles if missing
        if (!document.getElementById('toast-styles')) {
            const style = document.createElement('style');
            style.id = 'toast-styles';
            style.textContent = `
                #toast-container {
                    position: fixed;
                    top: 24px;
                    right: 24px;
                    z-index: 10000;
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                    pointer-events: none;
                }
                .custom-toast {
                    background: rgba(255, 255, 255, 0.95);
                    backdrop-filter: blur(10px);
                    color: #0f172a;
                    padding: 14px 20px;
                    border-radius: 12px;
                    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
                    display: flex;
                    align-items: center;
                    gap: 12px;
                    animation: toastSlideIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
                    min-width: 280px;
                    max-width: 350px;
                    border: 1px solid rgba(226, 232, 240, 0.8);
                    pointer-events: auto;
                    transition: all 0.4s ease;
                }
                .custom-toast.hide {
                    opacity: 0;
                    transform: translateY(-20px) scale(0.95);
                }
                .toast-icon-wrapper {
                    flex-shrink: 0;
                    width: 28px;
                    height: 28px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    font-size: 0.9rem;
                }
                .toast-content {
                    font-size: 0.875rem;
                    font-weight: 500;
                    line-height: 1.4;
                    flex-grow: 1;
                }
                /* Success */
                .toast-success .toast-icon-wrapper { background: #dcfce7; color: #16a34a; }
                /* Error */
                .toast-error .toast-icon-wrapper { background: #fee2e2; color: #dc2626; }
                /* Warning */
                .toast-warning .toast-icon-wrapper { background: #fef9c3; color: #ca8a04; }
                /* Info */
                .toast-info .toast-icon-wrapper { background: #e0f2fe; color: #0284c7; }
                
                @keyframes toastSlideIn {
                    from { transform: translateX(110%); opacity: 0; }
                    to { transform: translateX(0); opacity: 1; }
                }
            `;
            document.head.appendChild(style);
        }
    }

    const t = document.createElement('div');
    t.className = `custom-toast toast-${type}`;

    let icon = 'bi-check-lg';
    if (type === 'error') icon = 'bi-x-lg';
    if (type === 'warning') icon = 'bi-exclamation-triangle-fill';
    if (type === 'info') icon = 'bi-info-lg';

    t.innerHTML = `
        <div class="toast-icon-wrapper"><i class="bi ${icon}"></i></div>
        <div class="toast-content">${msg}</div>
    `;
    container.appendChild(t);

    setTimeout(() => {
        t.classList.add('hide');
        setTimeout(() => t.remove(), 400); // Wait for transition
    }, 4000);
}

/**
 * Shows a global "Offline" banner if the server is unreachable
 */
function showOfflineBanner(show = true) {
    let banner = document.getElementById('offline-banner');
    if (show) {
        if (!banner) {
            banner = document.createElement('div');
            banner.id = 'offline-banner';
            banner.style.cssText = `
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                background: #ef4444;
                color: white;
                text-align: center;
                padding: 8px;
                font-weight: 600;
                z-index: 10001;
                font-size: 0.9rem;
            `;
            banner.innerHTML = '<i class="bi bi-wifi-off me-2"></i> Server Disconnected. Some features may be unavailable.';
            document.body.appendChild(banner);
        }
    } else {
        if (banner) banner.remove();
    }
}

/**
 * Toggles password visibility for a given input element
 * @param {string} inputId The ID of the password input
 * @param {string} iconId The ID of the icon to toggle
 */
function togglePasswordVisibility(inputId, iconId) {
    const inp = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    if (!inp || !icon) return;
    
    if (inp.type === 'password') {
        inp.type = 'text';
        icon.className = 'bi bi-eye-slash';
    } else {
        inp.type = 'password';
        icon.className = 'bi bi-eye';
    }
}

// Export to window
window.togglePasswordVisibility = togglePasswordVisibility;
window.requireAuth = requireAuth;
window.showOfflineBanner = showOfflineBanner;

// ── API Helper Functions ──

/**
 * Global convenience function for GET requests
 * Wraps ApiClient.request() for simpler usage
 */
async function apiGet(path) {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        return await window.ApiClient.request(path, { method: 'GET' });
    } catch (error) {
        console.error(`apiGet failed for ${path}:`, error);
        throw error;
    }
}

/**
 * Global convenience function for POST requests
 */
async function apiPost(path, body = {}, options = {}) {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        return await window.ApiClient.request(path, { method: 'POST', body, ...options });
    } catch (error) {
        console.error(`apiPost failed for ${path}:`, error);
        throw error;
    }
}

/**
 * Global convenience function for PATCH requests
 */
async function apiPatch(path, body = {}, options = {}) {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        return await window.ApiClient.request(path, { method: 'PATCH', body, ...options });
    } catch (error) {
        console.error(`apiPatch failed for ${path}:`, error);
        throw error;
    }
}

/**
 * Global convenience function for PUT requests
 */
async function apiPut(path, body = {}, options = {}) {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        return await window.ApiClient.request(path, { method: 'PUT', body, ...options });
    } catch (error) {
        console.error(`apiPut failed for ${path}:`, error);
        throw error;
    }
}

/**
 * Global convenience function for DELETE requests
 */
async function apiDelete(path, options = {}) {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        return await window.ApiClient.request(path, { method: 'DELETE', ...options });
    } catch (error) {
        console.error(`apiDelete failed for ${path}:`, error);
        throw error;
    }
}

/**
 * Global convenience function for POST/PATCH requests (fetch fallback)
 * Wraps fetch with proper auth headers
 */
async function apiFetch(path, options = {}) {
    if (!window.ApiClient) throw new Error('ApiClient not initialized');
    const url = `${window.ApiClient.API_BASE_URL}${path}`;
    const headers = {
        ...(options.headers || {})
    };

    if (!(options.body instanceof FormData) && !headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
    }

    const token = window.ApiClient.getAccessToken();
    if (token && !options.noAuth) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        return await fetch(url, {
            ...options,
            headers
        });
    } catch (error) {
        console.error(`apiFetch failed for ${path}:`, error);
        if (window.showOfflineBanner) window.showOfflineBanner(true);
        throw error;
    }
}

// Export to window
window.apiGet = apiGet;
window.apiPost = apiPost;
window.apiPatch = apiPatch;
window.apiPut = apiPut;
window.apiDelete = apiDelete;
window.apiFetch = apiFetch;

window.showToast = showToast;
/**
 * Centralized form validation helper for SRM AI SETU
 * @param {string|HTMLElement} form - The form ID or element
 * @param {Object} rules - Validation rules { fieldId: "Error Message" or function }
 * @returns {boolean} - True if valid, false otherwise
 */
function validateForm(form, rules = {}) {
    const formEl = typeof form === 'string' ? document.getElementById(form) : form;
    if (!formEl) return true;

    // Clear previous errors
    formEl.querySelectorAll('.is-invalid').forEach(el => el.classList.remove('is-invalid'));
    formEl.querySelectorAll('.invalid-feedback').forEach(el => el.remove());

    let isValid = true;
    let firstErrorEl = null;

    for (const [fieldId, rule] of Object.entries(rules)) {
        const field = formEl.querySelector(`#${fieldId}`) || formEl.querySelector(`[name="${fieldId}"]`);
        if (!field) continue;

        let errorMsg = '';
        if (typeof rule === 'string') {
            if (!field.value || field.value.trim() === '') {
                errorMsg = rule;
            }
        } else if (typeof rule === 'function') {
            const result = rule(field.value, field);
            if (result !== true) {
                errorMsg = typeof result === 'string' ? result : 'Invalid input';
            }
        }

        if (errorMsg) {
            isValid = false;
            field.classList.add('is-invalid');
            
            const feedback = document.createElement('div');
            feedback.className = 'invalid-feedback';
            feedback.textContent = errorMsg;
            
            // Handle input-group wrapping
            if (field.parentElement.classList.contains('input-group')) {
                field.parentElement.appendChild(feedback);
            } else {
                field.after(feedback);
            }

            if (!firstErrorEl) firstErrorEl = field;
        }
    }

    if (firstErrorEl) {
        firstErrorEl.focus();
        // Scroll into view if it's a long modal
        firstErrorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }

    return isValid;
}
window.validateForm = validateForm;

// ── Shared Archive UI Component ──
class ArchivedDataOffcanvas {
    constructor(options) {
        this.moduleName = options.moduleName;
        this.title = options.title || `Archived ${this.moduleName}`;
        this.columns = options.columns || [{ key: 'name', label: 'Name' }];
        this.onRestore = options.onRestore || null;
        this.offcanvasId = `archived-offcanvas-${this.moduleName}`;
        
        this._injectHtml();
        this.offcanvasEl = document.getElementById(this.offcanvasId);
        this.bsOffcanvas = new bootstrap.Offcanvas(this.offcanvasEl);
        window.ArchivedDataOffcanvas.instances[this.offcanvasId] = this;
    }

    _injectHtml() {
        if (!document.getElementById(this.offcanvasId)) {
            const html = `
            <div class="offcanvas offcanvas-end" tabindex="-1" id="${this.offcanvasId}" style="width: 500px; z-index: 1055;">
                <div class="offcanvas-header bg-light border-bottom">
                    <h5 class="offcanvas-title fw-bold">
                        <i class="bi bi-archive text-muted me-2"></i>${this.title}
                    </h5>
                    <button type="button" class="btn-close" data-bs-dismiss="offcanvas" aria-label="Close"></button>
                </div>
                <div class="offcanvas-body p-0">
                    <div class="p-3">
                        <p class="text-muted small mb-0">Restore items previously removed. They will reappear in your active lists.</p>
                    </div>
                    <div class="table-responsive">
                        <table class="table table-hover align-middle mb-0" id="${this.offcanvasId}-table">
                            <thead class="bg-light">
                                <tr class="x-small text-uppercase text-muted fw-bold">
                                    ${this.columns.map(c => `<th>${c.label}</th>`).join('')}
                                    <th class="text-end pe-4">Actions</th>
                                </tr>
                            </thead>
                            <tbody id="${this.offcanvasId}-body">
                                <tr>
                                    <td colspan="${this.columns.length + 1}" class="text-center py-4 text-muted">
                                        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
                                        <span class="ms-2">Loading...</span>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>`;
            document.body.insertAdjacentHTML('beforeend', html);
        }
    }

    async open() {
        this.bsOffcanvas.show();
        await this.loadData();
    }

    async loadData() {
        const tbody = document.getElementById(`${this.offcanvasId}-body`);
        tbody.innerHTML = `<tr><td colspan="${this.columns.length + 1}" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></td></tr>`;
        
        try {
            if (!window.ApiClient) throw new Error('ApiClient not initialized');
            const data = await window.ApiClient.fetchArchived(this.moduleName);
            this.renderTable(data || []);
        } catch (err) {
            console.error('Failed to fetch archived data', err);
            tbody.innerHTML = `<tr><td colspan="${this.columns.length + 1}" class="text-center py-4 text-danger">Error loading data</td></tr>`;
        }
    }

    renderTable(data) {
        const tbody = document.getElementById(`${this.offcanvasId}-body`);
        if (!data || data.length === 0) {
            tbody.innerHTML = `<tr><td colspan="${this.columns.length + 1}" class="text-center py-5">
                <i class="bi bi-inbox text-muted" style="font-size:2rem;"></i>
                <p class="text-muted mt-2 mb-0">No archived items found</p>
            </td></tr>`;
            return;
        }

        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const user = window.ApiClient.getCurrentUser();
        const isAdmin = user && user.role && user.role.toUpperCase() === 'ADMIN';

        tbody.innerHTML = data.map(item => {
            const colsHtml = this.columns.map(col => {
                const val = col.render ? col.render(item) : (item[col.key] || '—');
                return `<td>${val}</td>`;
            }).join('');
            
            return `
            <tr>
                ${colsHtml}
                <td class="text-end pe-4 text-nowrap">
                    <button class="btn btn-sm btn-outline-primary rounded-3 me-1" onclick="window.ArchivedDataOffcanvas.instances['${this.offcanvasId}'].restoreItem('${item.id}')">
                        <i class="bi bi-arrow-90deg-up"></i> Restore
                    </button>
                    ${isAdmin ? `
                    <button class="btn btn-sm btn-outline-danger rounded-3" onclick="window.ArchivedDataOffcanvas.instances['${this.offcanvasId}'].hardDeleteItem('${item.id}')">
                        <i class="bi bi-trash"></i>
                    </button>
                    ` : ''}
                </td>
            </tr>`;
        }).join('');
    }

    async restoreItem(id) {
        try {
            if (!window.ApiClient) throw new Error('ApiClient not initialized');
            await window.ApiClient.unarchiveItem(this.moduleName, id);
            showToast('Item restored successfully');
            await this.loadData();
            if (this.onRestore) this.onRestore();
        } catch (err) {
            console.error('Error restoring item', err);
            showToast(err?.data?.detail || 'Failed to restore item', 'error');
        }
    }

    async hardDeleteItem(id) {
        if (!confirm("Are you sure? This cannot be undone.")) return;
        try {
            if (!window.ApiClient) throw new Error('ApiClient not initialized');
            await window.ApiClient.hardDeleteItem(this.moduleName, id);
            showToast('Item permanently deleted');
            await this.loadData();
            if (this.onRestore) this.onRestore();
        } catch (err) {
            console.error('Error permanently deleting item', err);
            showToast(err?.data?.detail || 'Failed to permanently delete item', 'error');
        }
    }
}
window.ArchivedDataOffcanvas = ArchivedDataOffcanvas;
window.ArchivedDataOffcanvas.instances = {};
