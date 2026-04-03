 /* frontend/js/settings.js */

// Ensure auth is present
if (typeof requireAuth === 'function') requireAuth();

// Initialize sidebar and header
const sidebarElement = document.getElementById('sidebar');
if (sidebarElement && typeof renderSidebar === 'function') {
    sidebarElement.innerHTML = renderSidebar('settings');
}
if (typeof injectTopHeader === 'function') injectTopHeader('Settings');

// Initial load
window.addEventListener('DOMContentLoaded', () => {
    console.trace('Settings page initialized');
    loadSettings();
    initSystem();
    initThemeCards();

    // Default view: Show the first section if none in hash
    const hash = window.location.hash.substring(1);
    const validSections = [
        'appearance', 'notifications', 'account', 'incentives-config', 
        'payslip-contact', 'invoice-settings', 'access-control', 
        'data-management-settings', 'attendance-settings', 
        'employee-code-settings', 'system'
    ];
    
    if (hash && validSections.includes(hash)) {
        const link = document.querySelector(`.settings-nav a[href="#${hash}"]`);
        // We use a tiny timeout to ensure initSystem() has finished DOM updates
        setTimeout(() => {
            const upToDateLink = document.querySelector(`.settings-nav a[href="#${hash}"]`);
            if (upToDateLink && upToDateLink.style.display !== 'none') {
                scrollTo(hash, upToDateLink);
            } else {
                scrollTo('appearance', document.querySelector('.settings-nav a[href="#appearance"]'));
            }
        }, 50);
    } else {
        scrollTo('appearance', document.querySelector('.settings-nav a[href="#appearance"]'));
    }
});

// Prevents scroll/tab jump on hash change
window.addEventListener('hashchange', () => {
    const id = window.location.hash.substring(1);
    if (id) {
        const link = document.querySelector(`.settings-nav a[href="#${id}"]`);
        scrollTo(id, link);
    }
});

/**
 * ── Theme Card Logic ────────────────────────────────────────────────────────
 */
function initThemeCards() {
    const cards = document.querySelectorAll('.theme-card');
    const currentTheme = localStorage.getItem('srm-theme') || 'light';
    
    cards.forEach(card => {
        const theme = card.dataset.theme;
        if (theme === currentTheme) {
            card.classList.add('active');
        }
        
        card.addEventListener('click', () => {
            cards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            saveSetting('theme', theme);
            if (window.setTheme) window.setTheme(theme);
        });
    });
}

/**
 * ── Load saved settings ─────────────────────────────────────────────────────
 */
async function loadSettings() {
    let backendPrefs = {};
    const u = JSON.parse(sessionStorage.getItem('srm_user') || '{}');

    // Try fetching from backend first
    if (u.id) {
        try {
            const profile = await apiGet('/auth/profile');
            backendPrefs = profile.preferences || {};
        } catch (err) {
            console.error('Failed to load backend preferences', err);
        }
    }

    // Checkboxes mapping
    const keys = [
        'compact_tables', 'animate_cards', 'compact_sidebar',
        'notif_inapp', 'notif_meetings', 'notif_issues', 'notif_leads'
    ];
    keys.forEach(k => {
        const el = document.getElementById(k.replace(/_/g, '-'));
        if (el && el.type === 'checkbox') {
            // Backend -> LocalStorage -> Default
            let val = backendPrefs[k];
            if (val === undefined) val = localStorage.getItem('srm_setting_' + k);

            if (val !== undefined && val !== null) {
                el.checked = String(val) === 'true';
            } else {
                el.checked = el.defaultChecked !== false;
            }
            
            // Trigger side effects for specific flags
            if (k === 'compact_sidebar') {
                document.body.classList.toggle('sidebar-compact', el.checked);
            }
        }
    });

    // Selects mapping: element-id => preference key
    const selectMap = {
        'poll-rate': 'poll_rate',
        'session-timeout': 'session_timeout',
        'default-view': 'default_view',
        'date-format': 'date_format',
        'timezone-select': 'timezone',
        'language-select': 'language'
    };
    Object.entries(selectMap).forEach(([elId, prefKey]) => {
        const el = document.getElementById(elId);
        if (el) {
            let val = backendPrefs[prefKey];
            if (val === undefined) val = localStorage.getItem('srm_setting_' + prefKey);
            if (val) el.value = val;
        }
    });
}

/**
 * ── Save a setting ──────────────────────────────────────────────────────────
 */
async function saveSetting(key, value) {
    // Save locally
    if (key === 'theme') {
        localStorage.setItem('srm-theme', value);
    }
    localStorage.setItem('srm_setting_' + key, value);

    // Save to backend
    try {
        const prefs = {};
        prefs[key] = value;
        await apiPatch('/auth/preferences', { preferences: prefs });
        showToast('Setting saved');
    } catch (err) {
        console.error('Pref save error', err);
        showToast('Saved locally (offline)', false);
    }
}

/**
 * ── Tab Navigation ──────────────────────────────────────────────────────────
 */
function scrollTo(id, el) {
    // Update nav active state
    document.querySelectorAll('.settings-nav a').forEach(a => a.classList.remove('active'));
    if (el) el.classList.add('active');

    // Toggle section visibility
    document.querySelectorAll('.settings-section, .danger-zone').forEach(sec => {
        sec.classList.remove('active-tab');
        sec.style.display = 'none';
    });

    const target = document.getElementById(id);
    if (target) {
        target.classList.add('active-tab');
        target.style.display = 'block';
        
        // Also show danger zone if it's the system tab and user is admin
        if (id === 'system') {
           const dz = document.getElementById('danger-zone');
           if (dz) { dz.style.display = 'block'; dz.classList.add('active-tab'); }
        }
    }

    // Update URL hash without jumping
    history.pushState(null, null, '#' + id);
    return false;
}

/**
 * ── Toast Notifications ─────────────────────────────────────────────────────
 */
function showToast(msg, isError = false) {
    const toast = document.getElementById('toast-msg');
    const txt = document.getElementById('toast-text');
    if (!toast || !txt) return;
    
    toast.querySelector('i').className = isError ? 'bi bi-x-circle-fill text-danger' : 'bi bi-check-circle-fill text-success';
    txt.textContent = msg;
    toast.style.display = 'flex';
    setTimeout(() => { toast.style.display = 'none'; }, 2200);
}

/**
 * ── Clear all settings ─────────────────────────────────────────────────────
 */
async function clearAllSettings() {
    if (!confirm('Are you sure you want to reset all site preferences to defaults?')) return;
    const keys = Object.keys(localStorage).filter(k => k.startsWith('srm_setting_'));
    keys.forEach(k => localStorage.removeItem(k));

    try {
        await apiPatch('/auth/preferences', { preferences: {} });
    } catch (err) { }

    loadSettings();
    showToast('All settings reset to defaults');
}

/**
 * ── System Initialization ───────────────────────────────────────────────────
 */
function initSystem() {
    const u = JSON.parse(sessionStorage.getItem('srm_user') || '{}');
    const isAdmin = u?.role === 'ADMIN';

    if (isAdmin) {
        document.getElementById('system-nav-link').style.display = 'flex';
        document.getElementById('incentives-nav-link').style.display = 'flex';
        document.getElementById('payslip-nav-link').style.display = 'flex';
        document.getElementById('invoice-nav-link').style.display = 'flex';
        document.getElementById('access-control-nav-link').style.display = 'flex';
        document.getElementById('data-management-nav-link').style.display = 'flex';
        document.getElementById('attendance-nav-link').style.display = 'flex';
        document.getElementById('emp-code-nav-link').style.display = 'flex';
        
        if (typeof loadSlabsSettings === 'function') loadSlabsSettings();
        if (typeof loadIncentiveEligibilityUsers === 'function') loadIncentiveEligibilityUsers();
        if (typeof loadPayslipContact === 'function') loadPayslipContact();
        if (typeof loadInvoiceSettings === 'function') loadInvoiceSettings();
        if (typeof loadAttendanceSettings === 'function') loadAttendanceSettings();
        if (typeof loadDeletePolicy === 'function') loadDeletePolicy();
        if (typeof loadEmployeeCodeSettings === 'function') loadEmployeeCodeSettings();
        if (typeof initAccessControl === 'function') initAccessControl();

        const apiUrl = window.API_BASE || (window.location.origin + '/api');
        const apiEl = document.getElementById('api-url-display');
        if (apiEl) apiEl.textContent = apiUrl;
        
        const userIdEl = document.getElementById('sys-user-id');
        if (userIdEl) userIdEl.textContent = `#${u?.id || '—'}`;

        // Ping API
        apiGet('/health', {}, { timeout: 3000 }).then(() => {
            const statusChip = document.getElementById('api-status-chip');
            if (statusChip) statusChip.innerHTML = '<i class="bi bi-check-circle-fill"></i> Online';
        }).catch(() => {
            const statusChip = document.getElementById('api-status-chip');
            if (statusChip) {
                statusChip.innerHTML = '<i class="bi bi-x-circle-fill"></i> Offline';
                statusChip.style.background = '#fef2f2';
                statusChip.style.color = '#b91c1c';
                statusChip.style.borderColor = '#fca5a5';
            }
        });
    } else {
        const sysLink = document.getElementById('system-nav-link');
        if (sysLink) sysLink.style.display = 'none';
    }
}

/**
 * ── Loading State Helper ────────────────────────────────────────────────────
 */
function toggleLoading(btnId, spnId, iconId, isLoading) {
    const btn = document.getElementById(btnId);
    const spn = document.getElementById(spnId);
    const icon = document.getElementById(iconId);
    if (!btn) return;
    btn.disabled = isLoading;
    if (spn) spn.classList.toggle('d-none', !isLoading);
    if (icon) icon.classList.toggle('d-none', isLoading);
}

/**
 * ── Attendance Settings (Admin) ─────────────────────────────────────────────
 */
async function loadAttendanceSettings() {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const settings = await window.ApiClient.getAttendanceSettings();
        document.getElementById('att-absent-threshold').value = settings.absent_hours_threshold ?? 0;
        document.getElementById('att-halfday-threshold').value = settings.half_day_hours_threshold ?? 4;
        document.getElementById('att-saturday').value = (settings.weekly_off_saturday || 'FULL').toUpperCase();
        document.getElementById('att-sunday').value = (settings.weekly_off_sunday || 'FULL').toUpperCase();

        const holidays = (settings.official_holidays || []).map(d => {
            if (typeof d === 'string') return d;
            try { return new Date(d).toISOString().slice(0, 10); } catch { return ''; }
        }).filter(Boolean);
        document.getElementById('att-holidays').value = holidays.join(', ');
    } catch (err) {
        console.error('Failed to load attendance settings', err);
    }
}

async function saveAttendanceSettings() {
    const btnMsg = document.getElementById('att-save-msg');
    const absent = parseFloat(document.getElementById('att-absent-threshold').value || '0');
    const half = parseFloat(document.getElementById('att-halfday-threshold').value || '4');
    const saturday = document.getElementById('att-saturday').value;
    const sunday = document.getElementById('att-sunday').value;
    const holidayRaw = document.getElementById('att-holidays').value || '';
    const holidays = holidayRaw.split(',').map(h => h.trim()).filter(Boolean);

    const rules = {
        'att-absent-threshold': (val) => isNaN(parseFloat(val)) ? 'Invalid value' : true,
        'att-halfday-threshold': (val) => isNaN(parseFloat(val)) ? 'Invalid value' : true
    };

    if (!validateForm(document.getElementById('attendance-settings'), rules)) {
        return;
    }

    try {
        toggleLoading('btn-save-att', 'spn-save-att', 'icon-save-att', true);
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        await window.ApiClient.updateAttendanceSettings({
            absent_hours_threshold: absent,
            half_day_hours_threshold: half,
            weekly_off_saturday: saturday,
            weekly_off_sunday: sunday,
            official_holidays: holidays
        });
        btnMsg.classList.remove('d-none');
        setTimeout(() => btnMsg.classList.add('d-none'), 2000);
    } catch (err) {
        console.error('Attendance settings save failed', err);
        showToast('Failed to save attendance settings', true);
    } finally {
        toggleLoading('btn-save-att', 'spn-save-att', 'icon-save-att', false);
    }
}

/**
 * ── Incentive Slabs (Admin) ──────────────────────────────────────────────────
 */
async function loadSlabsSettings() {
    const list = document.getElementById('slabs-settings-list');
    if (!list) return;
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const slabs = await window.ApiClient.getIncentiveSlabs();
        if (!slabs || !slabs.length) {
            list.innerHTML = '<p class="text-muted small mb-0">No slabs configured yet. Add one below.</p>';
            return;
        }
        list.innerHTML = `
        <div class="table-responsive">
            <table class="table table-sm align-middle mb-0" style="font-size:0.85rem;">
                <thead><tr class="text-uppercase text-muted" style="font-size:0.72rem; font-weight:700; letter-spacing:0.06em;">
                    <th>Range (Units)</th><th>Per Unit</th><th>Slab Bonus</th><th>Actions</th>
                </tr></thead>
                <tbody>${slabs.map(s => `
                <tr id="slab-row-${s.id}">
                    <td class="fw-semibold">${s.min_units} – ${s.max_units}</td>
                    <td class="text-primary fw-bold">₹${Number(s.incentive_per_unit).toLocaleString('en-IN')}</td>
                    <td class="text-success fw-bold">₹${Number(s.slab_bonus).toLocaleString('en-IN')}</td>
                    <td class="d-flex gap-1">
                        <button class="btn btn-sm" style="background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:7px;font-size:0.75rem;padding:2px 8px;" onclick="openEditSlabSettings('${s.id}','${s.min_units}','${s.max_units}','${s.incentive_per_unit}','${s.slab_bonus}')"><i class="bi bi-pencil"></i></button>
                        <button class="btn btn-sm" style="background:#fef2f2;color:#b91c1c;border:1px solid #fca5a5;border-radius:7px;font-size:0.75rem;padding:2px 8px;" onclick="deleteSlabSetting('${s.id}')"><i class="bi bi-trash"></i></button>
                    </td>
                </tr>`).join('')}
                </tbody>
            </table>
        </div>`;
    } catch (e) {
        list.innerHTML = `<p class="text-danger small mb-0">Failed to load slabs: ${e.message || 'Error'}</p>`;
    }
}

async function addSlabSetting() {
    const min = parseInt(document.getElementById('slab-min').value);
    const max = parseInt(document.getElementById('slab-max').value);
    const perUnit = parseFloat(document.getElementById('slab-per-unit').value);
    const bonus = parseFloat(document.getElementById('slab-bonus').value || '0');
    const msg = document.getElementById('slab-save-msg');

    const rules = {
        'slab-min': 'Minimum units required',
        'slab-max': (val) => {
            if (!val) return 'Maximum units required';
            if (parseInt(val) <= parseInt(document.getElementById('slab-min').value)) return 'Max must be > Min';
            return true;
        },
        'slab-per-unit': 'Incentive amount required'
    };

    if (!validateForm(document.getElementById('incentives-config'), rules)) {
        return;
    }

    try {
        toggleLoading('btn-add-slab', 'spn-add-slab', 'icon-add-slab', true);
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        await window.ApiClient.createIncentiveSlab({ min_units: min, max_units: max, incentive_per_unit: perUnit, slab_bonus: bonus });
        ['slab-min', 'slab-max', 'slab-per-unit', 'slab-bonus'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        msg.textContent = 'Slab added!';
        msg.className = 'ms-3 small text-success';
        msg.classList.remove('d-none');
        setTimeout(() => msg.classList.add('d-none'), 2500);
        loadSlabsSettings();
    } catch (e) {
        msg.textContent = e.message || 'Failed to add slab.';
        msg.className = 'ms-3 small text-danger';
        msg.classList.remove('d-none');
        setTimeout(() => msg.classList.add('d-none'), 3000);
    } finally {
        toggleLoading('btn-add-slab', 'spn-add-slab', 'icon-add-slab', false);
    }
}

async function deleteSlabSetting(id) {
    if (!confirm('Delete this incentive slab?')) return;
    try {
        await apiDelete('/incentives/slabs/' + id);
        loadSlabsSettings();
        showToast('Slab deleted');
    } catch (e) {
        showToast('Failed to delete slab', true);
    }
}

let _editingSlabId = null;
function openEditSlabSettings(id, min, max, perUnit, bonus) {
    _editingSlabId = id;
    document.getElementById('slab-min').value = min;
    document.getElementById('slab-max').value = max;
    document.getElementById('slab-per-unit').value = perUnit;
    document.getElementById('slab-bonus').value = bonus;
    const btn = document.querySelector('[onclick="addSlabSetting()"]');
    if (btn) { btn.innerHTML = '<i class="bi bi-check me-1"></i> Update Slab'; btn.setAttribute('onclick', 'saveEditSlabSettings()'); }
    document.getElementById('slab-save-msg').textContent = `Editing slab ${min}–${max}`;
    document.getElementById('slab-save-msg').className = 'ms-3 small text-info';
    document.getElementById('slab-save-msg').classList.remove('d-none');
    document.getElementById('slab-min').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function saveEditSlabSettings() {
    const min = parseInt(document.getElementById('slab-min').value);
    const max = parseInt(document.getElementById('slab-max').value);
    const perUnit = parseFloat(document.getElementById('slab-per-unit').value);
    const bonus = parseFloat(document.getElementById('slab-bonus').value || '0');
    const msg = document.getElementById('slab-save-msg');

    const rules = {
        'slab-min': 'Minimum units required',
        'slab-max': (val) => {
            if (!val) return 'Maximum units required';
            if (parseInt(val) <= parseInt(document.getElementById('slab-min').value)) return 'Max must be > Min';
            return true;
        },
        'slab-per-unit': 'Incentive amount required'
    };

    if (!validateForm(document.getElementById('incentives-config'), rules)) {
        return;
    }
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        await window.ApiClient.updateIncentiveSlab(_editingSlabId, { min_units: min, max_units: max, incentive_per_unit: perUnit, slab_bonus: bonus });
        ['slab-min', 'slab-max', 'slab-per-unit', 'slab-bonus'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
        _editingSlabId = null;
        const btn = document.querySelector('[onclick="saveEditSlabSettings()"]');
        if (btn) { btn.innerHTML = '<i class="bi bi-plus me-1"></i> Add Slab'; btn.setAttribute('onclick', 'addSlabSetting()'); }
        msg.textContent = 'Slab updated!';
        msg.className = 'ms-3 small text-success';
        msg.classList.remove('d-none');
        setTimeout(() => msg.classList.add('d-none'), 2500);
        loadSlabsSettings();
    } catch (e) {
        msg.textContent = e.message || 'Failed to update slab.';
        msg.className = 'ms-3 small text-danger';
        msg.classList.remove('d-none');
    }
}

/**
 * ── Incentive Eligibility (Admin) ──────────────────────────────────────────
 */
async function loadIncentiveEligibilityUsers() {
    const sel = document.getElementById('elig-user');
    const msg = document.getElementById('eligibility-msg');
    if (!sel) return;
    try {
        const users = await apiGet('/users/');
        const eligUsers = (users || []).filter(u => u.role !== 'CLIENT');
        sel.innerHTML = '<option value="">Select user</option>' + eligUsers.map(u => {
            const label = `${u.name || u.email} (${u.role})`;
            return `<option value="${u.id}" data-enabled="${u.incentive_enabled !== false}">${label}</option>`;
        }).join('');
        sel.addEventListener('change', function() {
            const opt = sel.options[sel.selectedIndex];
            if (!opt || !opt.value) return;
            const enabledEl = document.getElementById('elig-user-enabled');
            if (enabledEl) enabledEl.value = String(opt.dataset.enabled) === 'true' ? 'true' : 'false';
        });
        if (msg) msg.textContent = `${eligUsers.length} users loaded for incentive eligibility control.`;
    } catch (e) {
        if (msg) {
            msg.textContent = 'Failed to load users for eligibility setup.';
            msg.className = 'small text-danger mb-3';
        }
    }
}

async function applyRoleEligibility() {
    const role = document.getElementById('elig-role')?.value;
    const enabled = document.getElementById('elig-role-enabled')?.value === 'true';
    if (!role) {
        showToast('Select a role', true);
        return;
    }
    try {
        toggleLoading('btn-apply-role-elig', 'spn-apply-role-elig', 'icon-apply-role-elig', true);
        const res = await apiPatch('/users/incentive-eligibility/by-role', { role, enabled });
        const count = res?.updated ?? 0;
        const msg = document.getElementById('eligibility-msg');
        if (msg) {
            msg.textContent = `Updated ${count} users in role ${role}.`;
            msg.className = 'small text-success mb-3';
        }
        await loadIncentiveEligibilityUsers();
        showToast('Role eligibility updated');
    } catch (e) {
        showToast(e.data?.detail || e.message || 'Failed to update role eligibility', true);
    } finally {
        toggleLoading('btn-apply-role-elig', 'spn-apply-role-elig', 'icon-apply-role-elig', false);
    }
}

async function saveUserEligibility() {
    const userId = document.getElementById('elig-user')?.value;
    const enabled = document.getElementById('elig-user-enabled')?.value === 'true';
    if (!userId) {
        showToast('Select a user', true);
        return;
    }
    try {
        toggleLoading('btn-save-user-elig', 'spn-save-user-elig', 'icon-save-user-elig', true);
        await apiPatch(`/users/${userId}/incentive-eligibility`, { enabled });
        const msg = document.getElementById('eligibility-msg');
        if (msg) {
            msg.textContent = 'User incentive eligibility saved.';
            msg.className = 'small text-success mb-3';
        }
        await loadIncentiveEligibilityUsers();
        showToast('User eligibility updated');
    } catch (e) {
        showToast(e.data?.detail || e.message || 'Failed to update user eligibility', true);
    } finally {
        toggleLoading('btn-save-user-elig', 'spn-save-user-elig', 'icon-save-user-elig', false);
    }
}

/**
 * ── Employee Code Configuration (Admin) ─────────────────────────────────────
 */
async function loadEmployeeCodeSettings() {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const data = await window.ApiClient.getEmployeeCodeSettings();
        const enabledEl = document.getElementById('emp-code-enabled');
        if (enabledEl) enabledEl.checked = data.enabled !== false;
        
        const prefixEl = document.getElementById('emp-code-prefix');
        if (prefixEl) prefixEl.value = data.prefix || 'EMP';
        
        const seqEl = document.getElementById('emp-code-next-seq');
        if (seqEl) seqEl.value = data.next_seq || 1;
    } catch (e) {
        console.warn('Could not load employee code settings:', e);
    }
}

async function saveEmployeeCodeSettings() {
    const enabled = document.getElementById('emp-code-enabled').checked;
    const prefix = document.getElementById('emp-code-prefix').value.trim();
    const next_seq = parseInt(document.getElementById('emp-code-next-seq').value);
    const msg = document.getElementById('emp-code-save-msg');

    const rules = {
        'emp-code-prefix': 'Prefix is required',
        'emp-code-next-seq': 'Next sequence is required'
    };

    if (!validateForm(document.getElementById('employee-code-settings'), rules)) {
        return;
    }
    try {
        toggleLoading('btn-save-emp-code', 'spn-save-emp-code', 'icon-save-emp-code', true);
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        await window.ApiClient.updateEmployeeCodeSettings({ enabled, prefix, next_seq });
        if (msg) {
            msg.textContent = 'Saved!';
            msg.classList.remove('d-none');
            setTimeout(() => msg.classList.add('d-none'), 2500);
        }
        showToast('Employee code configuration saved');
    } catch (e) {
        showToast(e.data?.detail || e.message || 'Failed to save', true);
    } finally {
        toggleLoading('btn-save-emp-code', 'spn-save-emp-code', 'icon-save-emp-code', false);
    }
}

/**
 * ── Payslip & Contact Settings (Admin) ──────────────────────────────────────
 */
async function loadPayslipContact() {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const data = await window.ApiClient.getPayslipSettings();
        const emailEl = document.getElementById('payslip-email');
        if (emailEl) emailEl.value = data.email || '';
        const phoneEl = document.getElementById('payslip-phone');
        if (phoneEl) phoneEl.value = data.phone || '';
    } catch (e) {
        console.warn('Could not load payslip contact settings:', e);
    }
}

async function savePayslipContact() {
    const email = document.getElementById('payslip-email').value.trim();
    const phone = document.getElementById('payslip-phone').value.trim();
    const msg = document.getElementById('payslip-save-msg');
    const rules = {
        'payslip-email': (val) => {
            if (!val) return 'Email is required';
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) return 'Invalid email format';
            return true;
        },
        'payslip-phone': 'Phone is required'
    };

    if (!validateForm(document.getElementById('payslip-contact'), rules)) {
        return;
    }
    try {
        toggleLoading('btn-save-payslip', 'spn-save-payslip', 'icon-save-payslip', true);
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        await window.ApiClient.updatePayslipSettings({ email, phone });
        if (msg) {
            msg.textContent = 'Saved!';
            msg.classList.remove('d-none');
            setTimeout(() => msg.classList.add('d-none'), 2500);
        }
        showToast('Payslip contact info saved');
    } catch (e) {
        showToast(e.message || 'Failed to save', true);
    } finally {
        toggleLoading('btn-save-payslip', 'spn-save-payslip', 'icon-save-payslip', false);
    }
}

/**
 * ── Invoice & Payment Settings (Admin) ──────────────────────────────────────
 */
async function uploadPaymentQR(inputEle, urlInputId, previewImgId) {
    const file = inputEle.files[0];
    if (!file) return;
    const formData = new FormData();
    formData.append('file', file);
    try {
        const token = sessionStorage.getItem('access_token');
        if (!token) return;
        const apiBase = window.API_BASE || (window.location.origin + '/api');
        const res = await fetch(apiBase + '/billing/settings/upload-qr', {
            method: 'POST',
            headers: { 'Authorization': `Bearer ${token}` },
            body: formData
        });
        if (!res.ok) throw new Error('Upload failed');
        const data = await res.json();
        document.getElementById(urlInputId).value = data.url;
        const img = document.getElementById(previewImgId);
        if (img) {
            img.src = data.url;
            img.style.display = 'block';
        }
    } catch(e) {
        showToast('Failed to upload image', true);
    }
}

async function loadInvoiceSettings() {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const data = await window.ApiClient.getInvoiceSettings();
        const setVal = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
        setVal('inv-default-amount', data.invoice_default_amount || 12000);
        setVal('inv-personal-no-gst-amount', data.personal_without_gst_default_amount || 12000);
        setVal('inv-year', data.invoice_year || new Date().getFullYear());
        setVal('inv-seq-with-gst', data.invoice_seq_with_gst || 1);
        setVal('inv-seq-without-gst', data.invoice_seq_without_gst || 1);
        setVal('inv-company-name', data.company_name || '');
        setVal('inv-company-address', data.company_address || '');
        setVal('inv-header-image-details', data.company_header_image_details || '');
        setVal('inv-company-phone', data.company_phone || '');
        setVal('inv-company-email', data.company_email || '');
        setVal('inv-company-gstin', data.company_gstin || '');
        setVal('inv-company-pan', data.company_pan || '');
        setVal('inv-company-cin', data.company_cin || '');
        setVal('inv-company-cst-code', data.company_cst_code || '');
        setVal('inv-terms-conditions', data.invoice_terms_conditions || '');
        setVal('inv-business-upi-id', data.business_payment_upi_id || data.payment_upi_id || '');
        setVal('inv-business-upi-name', data.business_payment_account_name || data.payment_account_name || '');
        setVal('inv-business-bank-name', data.business_payment_bank_name || data.payment_bank_name || '');
        setVal('inv-business-bank-account-number', data.business_payment_account_number || data.payment_account_number || '');
        setVal('inv-business-bank-ifsc', data.business_payment_ifsc || data.payment_ifsc || '');
        setVal('inv-business-bank-branch', data.business_payment_branch || data.payment_branch || '');
        
        const bQrUrl = data.business_payment_qr_image_url || data.payment_qr_image_url || '';
        const bInput = document.getElementById('inv-business-qr-url');
        const bPreview = document.getElementById('inv-business-qr-preview');
        if (bInput) bInput.value = bQrUrl;
        if (bPreview) {
            if (bQrUrl) {
                bPreview.src = bQrUrl;
                bPreview.style.display = 'block';
            } else {
                bPreview.style.display = 'none';
            }
        }

        setVal('inv-personal-upi-id', data.personal_payment_upi_id || '');
        setVal('inv-personal-upi-name', data.personal_payment_account_name || '');
        setVal('inv-personal-bank-name', data.personal_payment_bank_name || '');
        setVal('inv-personal-bank-account-number', data.personal_payment_account_number || '');
        setVal('inv-personal-bank-ifsc', data.personal_payment_ifsc || '');
        setVal('inv-personal-bank-branch', data.personal_payment_branch || '');
        
        const pQrUrl = data.personal_payment_qr_image_url || '';
        const pInput = document.getElementById('inv-personal-qr-url');
        const pPreview = document.getElementById('inv-personal-qr-preview');
        if (pInput) pInput.value = pQrUrl;
        if (pPreview) {
            if (pQrUrl) {
                pPreview.src = pQrUrl;
                pPreview.style.display = 'block';
            } else {
                pPreview.style.display = 'none';
            }
        }

        const verifierRoles = String(data.invoice_verifier_roles || 'ADMIN').split(',').map(v => v.trim()).filter(Boolean);
        document.querySelectorAll('#inv-verifier-roles input[type="checkbox"]').forEach(cb => {
            cb.checked = verifierRoles.includes(cb.value);
        });
    } catch (e) {
        console.warn('Could not load invoice settings:', e);
    }
}

async function saveInvoiceSettings() {
    const msg = document.getElementById('inv-save-msg');
    const selectedRoles = Array.from(document.querySelectorAll('#inv-verifier-roles input[type="checkbox"]:checked')).map(cb => cb.value);
    if (!selectedRoles.includes('ADMIN')) {
        selectedRoles.unshift('ADMIN');
    }

    const rules = {
        'inv-company-name': 'Company name is required',
        'inv-company-address': 'Company address is required',
        'inv-company-email': (val) => {
            if (!val) return 'Email is required';
            if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(val)) return 'Invalid email format';
            return true;
        },
        'inv-company-phone': 'Phone is required'
    };

    if (!validateForm(document.getElementById('invoice-settings'), rules)) {
        return;
    }

    const getVal = (id, fb = '') => { const el = document.getElementById(id); return el ? el.value : fb; };

    const payload = {
        invoice_default_amount: parseFloat(getVal('inv-default-amount', '12000')) || 12000,
        personal_without_gst_default_amount: parseFloat(getVal('inv-personal-no-gst-amount', '12000')) || 12000,
        invoice_year: parseInt(getVal('inv-year'), 10) || new Date().getFullYear(),
        invoice_seq_with_gst: parseInt(getVal('inv-seq-with-gst'), 10) || 1,
        invoice_seq_without_gst: parseInt(getVal('inv-seq-without-gst'), 10) || 1,
        company_name: getVal('inv-company-name').trim(),
        company_address: getVal('inv-company-address').trim(),
        company_header_image_details: getVal('inv-header-image-details').trim(),
        company_phone: getVal('inv-company-phone').trim(),
        company_email: getVal('inv-company-email').trim(),
        company_gstin: getVal('inv-company-gstin').trim(),
        company_pan: getVal('inv-company-pan').trim(),
        company_cin: getVal('inv-company-cin').trim(),
        company_cst_code: getVal('inv-company-cst-code').trim(),
        invoice_terms_conditions: getVal('inv-terms-conditions').trim(),
        business_payment_upi_id: getVal('inv-business-upi-id').trim(),
        business_payment_account_name: getVal('inv-business-upi-name').trim(),
        business_payment_bank_name: getVal('inv-business-bank-name').trim(),
        business_payment_account_number: getVal('inv-business-bank-account-number').trim(),
        business_payment_ifsc: getVal('inv-business-bank-ifsc').trim(),
        business_payment_branch: getVal('inv-business-bank-branch').trim(),
        business_payment_qr_image_url: getVal('inv-business-qr-url').trim(),
        personal_payment_upi_id: getVal('inv-personal-upi-id').trim(),
        personal_payment_account_name: getVal('inv-personal-upi-name').trim(),
        personal_payment_bank_name: getVal('inv-personal-bank-name').trim(),
        personal_payment_account_number: getVal('inv-personal-bank-account-number').trim(),
        personal_payment_ifsc: getVal('inv-personal-bank-ifsc').trim(),
        personal_payment_branch: getVal('inv-personal-bank-branch').trim(),
        personal_payment_qr_image_url: getVal('inv-personal-qr-url').trim(),
        invoice_verifier_roles: selectedRoles.join(',')
    };
    try {
        toggleLoading('btn-save-inv', 'spn-save-inv', 'icon-save-inv', true);
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        await window.ApiClient.updateInvoiceSettings(payload);
        if (msg) {
            msg.textContent = 'Saved!';
            msg.classList.remove('d-none');
            setTimeout(() => msg.classList.add('d-none'), 2500);
        }
        showToast('Invoice settings saved');
    } catch (e) {
        showToast(e.data?.detail || e.message || 'Failed to save', true);
    } finally {
        toggleLoading('btn-save-inv', 'spn-save-inv', 'icon-save-inv', false);
    }
}

/**
 * ── Data Retention Policy (Admin) ───────────────────────────────────────────
 */
async function loadDeletePolicy() {
    try {
        const res = await apiGet('/hrm/delete-policy');
        const el = document.getElementById('global-delete-policy');
        if (el) el.value = res.policy || 'SOFT';
    } catch (e) {
        console.warn('Failed to load delete policy');
    }
}

async function saveDeletePolicy() {
    const policy = document.getElementById('global-delete-policy').value;
    const msg = document.getElementById('delete-policy-save-msg');
    if (!confirm(`Are you sure you want to switch to ${policy} delete? This affects all future deletions.`)) return;
    try {
        toggleLoading('btn-save-del-policy', 'spn-save-del-policy', 'icon-save-del-policy', true);
        await apiPut('/hrm/delete-policy', { policy });
        if (msg) {
            msg.classList.remove('d-none');
            setTimeout(() => msg.classList.add('d-none'), 2500);
        }
        showToast('Global delete policy updated');
    } catch (e) {
        showToast('Failed to update policy', true);
    } finally {
        toggleLoading('btn-save-del-policy', 'spn-save-del-policy', 'icon-save-del-policy', false);
    }
}

/**
 * ── Access Control (Admin) ───────────────────────────────────────────────────
 * 
 * Manages per-role Page Access and Feature Access permissions.
 * State is stored locally and synced to/from the backend via:
 *   GET  /auth/access-policy  → { page_access: {ROLE: [pages]}, feature_access: {key: [roles]} }
 *   PUT  /auth/access-policy  → save back
 * Falls back to a hardcoded defaults map if backend is unavailable.
 */

const AC_ROLES = [
    { key: 'ADMIN',                    label: 'Admin',          icon: 'bi-shield-fill' },
    { key: 'SALES',                    label: 'Sales',          icon: 'bi-graph-up-arrow' },
    { key: 'TELESALES',                label: 'Telesales',      icon: 'bi-telephone' },
    { key: 'PROJECT_MANAGER',          label: 'PM',              icon: 'bi-kanban' },
    { key: 'PROJECT_MANAGER_AND_SALES',label: 'PM & Sales',       icon: 'bi-people' },
];

const AC_ALL_PAGES = [
    { name: 'dashboard.html',       icon: 'bi-speedometer2', label: 'Dashboard',       required: false },
    { name: 'admin.html',           icon: 'bi-shield-lock',   label: 'Admin',           required: false },
    { name: 'leads.html',           icon: 'bi-funnel',        label: 'Leads',           required: false },
    { name: 'clients.html',         icon: 'bi-person-check',  label: 'Clients',         required: false },
    { name: 'visits.html',          icon: 'bi-map',           label: 'Visits',          required: false },
    { name: 'areas.html',           icon: 'bi-geo',           label: 'Areas',           required: false },
    { name: 'projects.html',        icon: 'bi-kanban',        label: 'Projects',        required: false },
    { name: 'projects_demo.html',   icon: 'bi-play-btn',      label: 'Projects Demo',   required: false },
    { name: 'meetings.html',        icon: 'bi-camera-video',  label: 'Meetings',        required: false },
    { name: 'todo.html',            icon: 'bi-check2-square', label: 'Tasks / To-Do',   required: false },
    { name: 'timetable.html',       icon: 'bi-calendar-week', label: 'Timetable',       required: false },
    { name: 'billing.html',         icon: 'bi-receipt',       label: 'Billing',         required: false },
    { name: 'issues.html',          icon: 'bi-bug',           label: 'Issues',          required: false },
    { name: 'feedback.html',        icon: 'bi-chat-square-text', label: 'Feedback',     required: false },
    { name: 'employee_report.html', icon: 'bi-bar-chart-line', label: 'Employee Report', required: false },
    { name: 'client_report.html',   icon: 'bi-bar-chart-line', label: 'Client Report',   required: false },
    { name: 'leaves.html',          icon: 'bi-calendar-x',   label: 'Leaves',          required: false },
    { name: 'salary.html',          icon: 'bi-cash-stack',    label: 'Salary',          required: false },
    { name: 'salary_slip_view.html',icon: 'bi-receipt',       label: 'Salary Slip',     required: false },
    { name: 'incentives.html',      icon: 'bi-trophy',        label: 'Incentives',      required: false },
    { name: 'employees.html',       icon: 'bi-people',        label: 'Employees',       required: false },
    { name: 'notifications.html',   icon: 'bi-bell',          label: 'Notifications',   required: false },
    { name: 'search.html',          icon: 'bi-search',        label: 'Search',          required: false },
    { name: 'profile.html',         icon: 'bi-person-circle', label: 'Profile',         required: true  },
    { name: 'settings.html',        icon: 'bi-gear',          label: 'Settings',        required: true  },
];

const AC_FEATURES = [
    { key: 'issue_create_roles',    label: 'Create Issues',        desc: 'Can report new issues' },
    { key: 'issue_manage_roles',    label: 'Manage Issues',        desc: 'Can resolve/assign issues' },
    { key: 'invoice_creator_roles', label: 'Create Invoices',      desc: 'Can create billing invoices' },
    { key: 'invoice_verifier_roles',label: 'Verify Invoices',      desc: 'Can approve & send invoices' },
    { key: 'leave_apply_roles',     label: 'Apply for Leave',      desc: 'Can submit leave requests' },
    { key: 'leave_manage_roles',    label: 'Manage Leaves',        desc: 'Can approve/reject leaves' },
    { key: 'salary_manage_roles',   label: 'Manage Salaries',      desc: 'Can generate payslips' },
    { key: 'salary_view_all_roles', label: 'View All Salaries',    desc: 'Can view all employee pay' },
    { key: 'incentive_manage_roles',label: 'Manage Incentives',    desc: 'Can configure incentive slabs' },
    { key: 'employee_manage_roles', label: 'Manage Employees',     desc: 'Can add/edit/remove users' },
];

const AC_DEFAULT_POLICY = {
    page_access: {
        ADMIN:                     ['*'],
        SALES:                     ['dashboard.html', 'timetable.html', 'todo.html', 'leads.html', 'visits.html', 'areas.html', 'clients.html', 'billing.html', 'leaves.html', 'salary.html', 'salary_slip_view.html', 'search.html', 'notifications.html', 'profile.html', 'settings.html', 'issues.html', 'incentives.html', 'employees.html', 'projects.html', 'projects_demo.html', 'employee_report.html', 'client_report.html'],
        TELESALES:                 ['dashboard.html','timetable.html','todo.html','leads.html','visits.html','clients.html','billing.html','leaves.html','salary.html','search.html','notifications.html','profile.html','settings.html','issues.html','incentives.html','employees.html'],
        PROJECT_MANAGER:           ['dashboard.html','timetable.html','todo.html','projects.html','meetings.html','issues.html','clients.html','billing.html','feedback.html','employee_report.html','client_report.html','leaves.html','salary.html','search.html','notifications.html','profile.html','settings.html','employees.html'],
        PROJECT_MANAGER_AND_SALES: ['dashboard.html','timetable.html','todo.html','leads.html','visits.html','areas.html','projects.html','meetings.html','issues.html','clients.html','billing.html','feedback.html','employee_report.html','client_report.html','leaves.html','salary.html','search.html','notifications.html','profile.html','settings.html','employees.html'],
    },
    feature_access: {
        issue_create_roles:     ['ADMIN','SALES','TELESALES','PROJECT_MANAGER','PROJECT_MANAGER_AND_SALES'],
        issue_manage_roles:     ['ADMIN','PROJECT_MANAGER','PROJECT_MANAGER_AND_SALES','SALES','TELESALES'],
        invoice_creator_roles:  ['ADMIN','SALES','TELESALES','PROJECT_MANAGER_AND_SALES'],
        invoice_verifier_roles: ['ADMIN'],
        leave_apply_roles:      ['SALES','TELESALES','PROJECT_MANAGER','PROJECT_MANAGER_AND_SALES'],
        leave_manage_roles:     ['ADMIN'],
        salary_manage_roles:    ['ADMIN'],
        salary_view_all_roles:  ['ADMIN'],
        incentive_manage_roles: ['ADMIN'],
        employee_manage_roles:  ['ADMIN'],
    }
};

let _acPolicy = null;        // working copy of the policy
let _acActiveRole = 'SALES'; // currently selected role tab

async function initAccessControl() {
    try {
        const fetched = await apiGet('/users/access-policy').catch(() => null);
        if (fetched && (fetched.page_access || fetched.feature_access)) {
            _acPolicy = {
                page_access: { ...AC_DEFAULT_POLICY.page_access, ...(fetched.page_access || {}) },
                feature_access: { ...AC_DEFAULT_POLICY.feature_access, ...(fetched.feature_access || {}) }
            };
        } else {
            _acPolicy = JSON.parse(JSON.stringify(AC_DEFAULT_POLICY));
        }
    } catch (e) {
        _acPolicy = JSON.parse(JSON.stringify(AC_DEFAULT_POLICY));
    }
    renderAcRoleBar();
    renderAcForRole(_acActiveRole);
}

function renderAcRoleBar() {
    const bar = document.getElementById('ac-role-bar');
    if (!bar) return;
    bar.innerHTML = AC_ROLES.map(r => {
        const isActive = r.key === _acActiveRole;
        const pageCount = _acPolicy.page_access[r.key]?.includes('*')
            ? AC_ALL_PAGES.length + '+'
            : (_acPolicy.page_access[r.key] || []).length;
        return `<button class="ac-role-pill ${isActive ? 'active' : ''}" onclick="acSwitchRole('${r.key}')">
            <i class="bi ${r.icon}"></i>
            ${r.label}
            <span class="ac-role-badge">${pageCount}</span>
        </button>`;
    }).join('');
}

function acSwitchRole(roleKey) {
    _acActiveRole = roleKey;
    renderAcRoleBar();
    renderAcForRole(roleKey);
}

function renderAcForRole(roleKey) {
    renderAcPages(roleKey);
    renderAcFeatures(roleKey);
}

function renderAcPages(roleKey) {
    const container = document.getElementById('ac-pages-list');
    const countEl = document.getElementById('ac-page-count');
    if (!container) return;

    const allowedPages = _acPolicy.page_access[roleKey] || [];
    const isFullAccess = allowedPages.includes('*');
    const isAdmin = roleKey === 'ADMIN';

    if (isAdmin) {
        container.innerHTML = `
        <div class="ac-item">
            <div class="ac-item-label">
                <i class="bi bi-infinity text-primary"></i>
                <span>Full access to all pages <span class="ac-item-tag" style="background:#eff6ff;color:#1d4ed8;border-color:#bfdbfe;">ADMIN</span></span>
            </div>
        </div>`;
        if (countEl) countEl.textContent = 'All pages';
        return;
    }

    const count = isFullAccess ? AC_ALL_PAGES.length : allowedPages.length;
    if (countEl) countEl.textContent = `${count} / ${AC_ALL_PAGES.length} pages`;

    // Merge all known pages + any custom ones
    const knownNames = AC_ALL_PAGES.map(p => p.name);
    const unknownAllowed = allowedPages.filter(p => p !== '*' && !knownNames.includes(p));
    const extraPages = unknownAllowed.map(p => ({ name: p, icon: 'bi-file-earmark', label: p, required: false }));
    const allPages = [...AC_ALL_PAGES, ...extraPages];

    container.innerHTML = allPages.map(page => {
        const isChecked = isFullAccess || allowedPages.includes(page.name);
        const isReq = page.required;
        return `<div class="ac-item">
            <div class="ac-item-label">
                <i class="bi ${page.icon}"></i>
                <div>
                    <span class="ac-page-name">${page.name}</span>
                    ${isReq ? '<span class="ac-item-tag required ms-1">Required</span>' : ''}
                </div>
            </div>
            <label class="ac-toggle">
                <input type="checkbox" data-role="${roleKey}" data-page="${page.name}"
                    ${isChecked ? 'checked' : ''} ${isReq ? 'disabled' : ''}
                    onchange="acTogglePage('${roleKey}', '${page.name}', this.checked)">
                <span class="slider"></span>
            </label>
        </div>`;
    }).join('');
}

function renderAcFeatures(roleKey) {
    const container = document.getElementById('ac-features-list');
    if (!container) return;

    container.innerHTML = AC_FEATURES.map(f => {
        const allowedRoles = _acPolicy.feature_access[f.key] || [];
        const isEnabled = allowedRoles.map(r => r.toUpperCase()).includes(roleKey);
        const isAdminOnly = f.key.includes('manage') || f.key.includes('verifier') || f.key.includes('view_all');
        const isForced = roleKey === 'ADMIN' && isAdminOnly;
        return `<div class="ac-item">
            <div class="ac-item-label" style="flex-direction:column;align-items:flex-start;gap:2px;">
                <span style="font-weight:600;">${f.label}</span>
                <span class="ac-feature-desc">${f.desc}</span>
            </div>
            <label class="ac-toggle">
                <input type="checkbox" data-role="${roleKey}" data-feature="${f.key}"
                    ${isEnabled ? 'checked' : ''} ${isForced ? 'disabled' : ''}
                    onchange="acToggleFeature('${roleKey}', '${f.key}', this.checked)">
                <span class="slider"></span>
            </label>
        </div>`;
    }).join('');
}

function acTogglePage(roleKey, pageName, enabled) {
    if (!_acPolicy.page_access[roleKey]) _acPolicy.page_access[roleKey] = [];
    const pages = _acPolicy.page_access[roleKey];

    if (pages.includes('*')) {
        // Expand the wildcard first
        _acPolicy.page_access[roleKey] = AC_ALL_PAGES.map(p => p.name);
    }

    if (enabled) {
        if (!_acPolicy.page_access[roleKey].includes(pageName)) {
            _acPolicy.page_access[roleKey].push(pageName);
        }
    } else {
        _acPolicy.page_access[roleKey] = _acPolicy.page_access[roleKey].filter(p => p !== pageName);
    }

    const countEl = document.getElementById('ac-page-count');
    if (countEl) countEl.textContent = `${_acPolicy.page_access[roleKey].length} / ${AC_ALL_PAGES.length} pages`;
    renderAcRoleBar(); // update badge counts
}

function acToggleFeature(roleKey, featureKey, enabled) {
    if (!_acPolicy.feature_access[featureKey]) _acPolicy.feature_access[featureKey] = [];
    const roles = _acPolicy.feature_access[featureKey];

    if (enabled) {
        if (!roles.map(r => r.toUpperCase()).includes(roleKey)) {
            _acPolicy.feature_access[featureKey].push(roleKey);
        }
    } else {
        _acPolicy.feature_access[featureKey] = roles.filter(r => r.toUpperCase() !== roleKey);
    }
}

function acAddPage() {
    const sel = document.getElementById('ac-add-page-select');
    const page = sel?.value?.trim();
    if (!page) { showToast('Select a page first', 'warning'); return; }
    if (!_acPolicy.page_access[_acActiveRole]) _acPolicy.page_access[_acActiveRole] = [];
    if (!_acPolicy.page_access[_acActiveRole].includes(page)) {
        _acPolicy.page_access[_acActiveRole].push(page);
        sel.value = '';
        renderAcPages(_acActiveRole);
        renderAcRoleBar();
        showToast(`Added ${page} to ${_acActiveRole}`);
    } else {
        showToast('Page already in the list', 'warning');
    }
}

function resetAccessPolicy() {
    if (!confirm('Reset all access rules to system defaults? Your custom changes will be lost.')) return;
    _acPolicy = JSON.parse(JSON.stringify(AC_DEFAULT_POLICY));
    renderAcRoleBar();
    renderAcForRole(_acActiveRole);
    showToast('Access policy reset to defaults');
}

async function saveAccessPolicy() {
    const saveMsg = document.getElementById('ac-save-msg');
    const errMsg = document.getElementById('ac-error-msg');
    if (saveMsg) saveMsg.classList.add('d-none');
    if (errMsg) errMsg.classList.add('d-none');

    toggleLoading('btn-save-access', 'spn-save-access', 'icon-save-access', true);

    // Always keep ADMIN as full access
    _acPolicy.page_access['ADMIN'] = ['*'];

    try {
        // Try to persist to backend
        await apiPut('/users/access-policy', _acPolicy);

        // Always save to localStorage as the fallback for local-only use cases
        localStorage.setItem('crm_access_policy', JSON.stringify(_acPolicy));

        // Refetch profile and effective policy to keep session in sync
        if (window.ApiClient && window.ApiClient.getProfile) {
            const profile = await window.ApiClient.getProfile().catch(() => null);
            if (profile) {
                const userData = { id: profile.id, name: profile.name || profile.email, email: profile.email, role: profile.role };
                sessionStorage.setItem('srm_user', JSON.stringify(userData));
            }
        }

        if (window.ApiClient && window.ApiClient.getEffectiveAccessPolicy) {
            const effective = await window.ApiClient.getEffectiveAccessPolicy().catch(() => null);
            if (effective) {
                window.__crmEffectiveAccessPolicy = effective;
                sessionStorage.setItem('crm_access_policy', JSON.stringify(effective));
            }
        }

        // Trigger UI refresh
        window.dispatchEvent(new CustomEvent('permissions-changed', { 
            detail: { policy: _acPolicy } 
        }));

        if (saveMsg) {
            saveMsg.classList.remove('d-none');
            setTimeout(() => saveMsg.classList.add('d-none'), 3000);
        }
        showToast('Access policy saved & synchronized!');
    } catch (e) {
        const msg = e?.message || 'Failed to save policy';
        if (errMsg) {
            errMsg.textContent = msg;
            errMsg.classList.remove('d-none');
        }
        showToast(msg, 'error');
    } finally {
        toggleLoading('btn-save-access', 'spn-save-access', 'icon-save-access', false);
    }
}

