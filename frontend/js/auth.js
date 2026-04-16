// frontend/js/auth.js
// auth.js — shared across all pages
// Config handled by ApiClient.initConfig() lazily or via explicit call
if (window.ApiClient) window.ApiClient.initConfig();

// Global fallback for feature access roles
const FEATURE_ACCESS_FALLBACK = {
    issue_create_roles: ['ADMIN', 'SALES', 'TELESALES', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES'],
    issue_manage_roles: ['ADMIN', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES', 'SALES', 'TELESALES'],
    invoice_creator_roles: ['ADMIN', 'SALES', 'TELESALES', 'PROJECT_MANAGER_AND_SALES'],
    invoice_verifier_roles: ['ADMIN'],
    leave_apply_roles: ['SALES', 'TELESALES', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES'],
    leave_edit_own_roles: ['SALES', 'TELESALES', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES'],
    leave_cancel_own_roles: ['SALES', 'TELESALES', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES'],
    leave_manage_roles: ['ADMIN'],
    salary_manage_roles: ['ADMIN'],
    salary_view_all_roles: ['ADMIN'],
    incentive_manage_roles: ['ADMIN'],
    incentive_view_all_roles: ['ADMIN'],
    employee_manage_roles: ['ADMIN'],
    project_demo_roles: ['ADMIN', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES', 'SALES', 'TELESALES'],
};

window.hasFeatureAccess = function(featureKey, roleInput) {
    const roleName = String(roleInput || getUser()?.role || '').toUpperCase();
    if (!roleName) return false;
    const effective = window.__crmEffectiveAccessPolicy;
    const featureAccess = effective?.feature_access || effective?.policy?.feature_access || FEATURE_ACCESS_FALLBACK;
    const allowedRoles = featureAccess?.[featureKey] || FEATURE_ACCESS_FALLBACK[featureKey] || [];
    return Array.isArray(allowedRoles) && allowedRoles.map(v => String(v).toUpperCase()).includes(roleName);
};

// Inject global theme styles (but NOT on the login page to avoid style degradation)
const isLoginPage = window.location.pathname.endsWith('index.html') || window.location.pathname.endsWith('/') || window.location.pathname === '';
if (!isLoginPage) {
    document.head.insertAdjacentHTML('beforeend', '<link rel="stylesheet" href="/static/css/theme.css?v=20260403">');
    document.head.insertAdjacentHTML('beforeend', '<link rel="stylesheet" href="/static/css/components.css?v=20260403">');
    document.head.insertAdjacentHTML('beforeend', '<link rel="stylesheet" href="/static/css/global.css?v=20260403">');
}

window.getToken = function() {
    const t = localStorage.getItem('access_token');
    if (!t || t === 'null' || t === 'undefined' || t === '') return null;
    return t;
}
window.setTokens = function(a, r) {
    localStorage.setItem('access_token', a);
    if (r) localStorage.setItem('refresh_token', r);
}
window.clearTokens = function() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('srm_user');
    localStorage.removeItem('current_user');
}
window.getUser = function() {
    try { 
        return JSON.parse(localStorage.getItem('srm_user') || sessionStorage.getItem('srm_user')); 
    } catch { return null; }
}

window.showAccessDeniedState = function(role, path) {
    const target = document.getElementById('main-content') || document.querySelector('.page-content-standard');
    if (!target || document.getElementById('access-denied-state')) return;

    const roleLabel = (role || 'USER').replace(/_/g, ' ');
    const pageLabel = (path || 'this page').replace('.html', '').replace(/[-_]/g, ' ');
    const card = document.createElement('div');
    card.id = 'access-denied-state';
    // Use theme tokens for the card
    card.style.cssText = 'position:relative;z-index:100;margin:0 auto 32px auto;max-width:540px;background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:32px;box-shadow:var(--shadow-xl);overflow:visible;';
    card.innerHTML = `
        <div style="text-align:center;">
            <div style="width:64px;height:64px;border-radius:16px;background:var(--primary-soft);color:var(--primary);display:flex;align-items:center;justify-content:center;font-size:32px;margin:0 auto 24px auto;">
                <i class="bi bi-shield-lock"></i>
            </div>
            <h2 style="font-size:1.5rem;font-weight:700;color:var(--text-1);margin-bottom:12px;font-family:'Outfit',sans-serif;">Access Restricted</h2>
            <p style="color:var(--text-2);font-size:0.95rem;line-height:1.6;margin-bottom:32px;">Your current role, ${roleLabel}, cannot view ${pageLabel}. Please return to the dashboard or contact your administrator.</p>
            <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
                <a href="dashboard.html" style="text-decoration:none;background:var(--primary);color:#fff;padding:10px 24px;border-radius:8px;font-weight:600;font-size:14px;min-width:120px;display:inline-flex;align-items:center;justify-content:center;transition:all 0.2s;">Return to Dashboard</a>
                <a href="profile.html" style="text-decoration:none;background:var(--bg-page);color:var(--text-1);padding:10px 24px;border-radius:8px;border:1px solid var(--border);font-weight:600;font-size:14px;min-width:120px;display:inline-flex;align-items:center;justify-content:center;transition:all 0.2s;">Open Profile</a>
            </div>
        </div>`;

    target.style.position = target.style.position || 'relative';
    target.insertBefore(card, target.firstChild);
    Array.from(target.children).forEach(child => {
        if (child.id === 'access-denied-state') return;
        child.style.opacity = '0.18';
        child.style.pointerEvents = 'none';
        child.setAttribute('aria-hidden', 'true');
    });
    window.__accessDenied = true;
}

window.hideAccessDeniedState = function() {
    const card = document.getElementById('access-denied-state');
    if (card) card.remove();
    
    const target = document.getElementById('main-content') || document.querySelector('.page-content-standard');
    if (target) {
        Array.from(target.children).forEach(child => {
            child.style.opacity = '';
            child.style.pointerEvents = '';
            child.removeAttribute('aria-hidden');
        });
    }
    window.__accessDenied = false;
}

// Guard: call on every protected page
window.requireAuth = function() {
    console.log('requireAuth called, location:', window.location.href);
    window.__accessDenied = false;
    const params = new URLSearchParams(window.location.search);
    const isLocal = ['localhost', '127.0.0.1', ''].includes(window.location.hostname) || window.location.protocol === 'file:';
    const isLoginPage = window.location.pathname.endsWith('index.html') || window.location.pathname.endsWith('/');

    if (params.get('dev') === 'true' && isLocal) {
        console.log('requireAuth: Dev mode detected');
        // Support mocking any role via ?dev_role=SALES|TELESALES|PROJECT_MANAGER|PROJECT_MANAGER_AND_SALES|CLIENT|ADMIN
        const devRole = (params.get('dev_role') || 'ADMIN').toUpperCase();
        const VALID_DEV_ROLES = ['ADMIN', 'SALES', 'TELESALES', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES', 'CLIENT'];
        const effectiveDevRole = VALID_DEV_ROLES.includes(devRole) ? devRole : 'ADMIN';
        const roleNameMap = {
            ADMIN: 'System Administrator (Dev)',
            SALES: 'Sales Staff (Dev)',
            TELESALES: 'Telesales Staff (Dev)',
            PROJECT_MANAGER: 'Project Manager (Dev)',
            PROJECT_MANAGER_AND_SALES: 'PM + Sales (Dev)',
            CLIENT: 'Client User (Dev)'
        };
        // Always overwrite dev user to match the requested role (allows role-switching mid-session)
        sessionStorage.setItem('access_token', 'dev-token');
        const devUserJson = JSON.stringify({
            id: 1,
            name: roleNameMap[effectiveDevRole] || 'Dev User',
            email: effectiveDevRole.toLowerCase() + '@crm.dev',
            role: effectiveDevRole
        });
        sessionStorage.setItem('srm_user', devUserJson);
        // Also sync to localStorage so getUser() finds it
        localStorage.setItem('srm_user', devUserJson);
        // CRITICAL: Clear any stale access policy cache from a previous session
        // so the fallback role→page map is used for the current dev role
        localStorage.removeItem('crm_access_policy');
        window.__crmEffectiveAccessPolicy = null;

        document.body.style.visibility = 'visible';
        document.body.style.opacity = '1';
        let pageName = document.title.split('—')[0].trim();
        if (!pageName || pageName === 'SRM AI SETU') pageName = 'Dashboard';
        if (typeof window.injectTopHeader === 'function') window.injectTopHeader(pageName);
        if (typeof window.enforceRoleAccess === 'function') window.enforceRoleAccess(effectiveDevRole);
        console.log('requireAuth: Dev mode setup complete for role:', effectiveDevRole);
        return;
    }

    const token = getToken();
    let user = getUser();

    if (!token) {
        // Bypass redirect if this is a payment success return
        if (params.get('status') === 'success') {
            console.log('requireAuth: Payment success bypass detected');
            return;
        }
        if (!isLoginPage) {
            // Encode the current page so login can redirect back
            const currentPage = window.location.pathname.split('/').pop() + window.location.search;
            window.location.replace('index.html?returnTo=' + encodeURIComponent(currentPage));
        }
        return;
    }

    // --- ROLE BASED ROUTING GUARD ---
    // --- DYNAMIC PERMISSIONS (Sole Source of Truth) ---

    // Default page access by role — used as fallback when no server policy is loaded yet.
    // ADMIN has '*' (all). Other roles have explicit lists.
    const DEFAULT_PAGE_ACCESS = {
        ADMIN: ['*'],
        SALES: [
            'dashboard.html', 'profile.html', 'notifications.html', 'search.html',
            'clients.html', 'billing.html', 'leaves.html', 'incentives.html',
            'visits.html', 'areas.html', 'leads.html', 'todo.html', 'timetable.html',
            'feedback.html', 'issues.html', 'projects.html', 'salary.html', 'employees.html',
            'salary_slip_view.html', 'settings.html', 'meetings.html',
            'employee_report.html', 'client_report.html', 'projects_demo.html'
        ],
        TELESALES: [
            'dashboard.html', 'profile.html', 'notifications.html', 'search.html',
            'clients.html', 'billing.html', 'leaves.html', 'incentives.html',
            'visits.html', 'areas.html', 'leads.html', 'todo.html', 'timetable.html',
            'feedback.html', 'issues.html', 'salary.html', 'employees.html',
            'salary_slip_view.html', 'settings.html', 'meetings.html',
            'employee_report.html', 'client_report.html', 'projects_demo.html'
        ],
        PROJECT_MANAGER: [
            'dashboard.html', 'profile.html', 'notifications.html', 'search.html',
            'clients.html', 'billing.html', 'leaves.html', 'incentives.html',
            'projects.html', 'meetings.html', 'issues.html', 'todo.html', 'timetable.html',
            'feedback.html', 'salary.html', 'employees.html',
            'salary_slip_view.html', 'settings.html', 'areas.html', 'leads.html',
            'employee_report.html', 'client_report.html', 'projects_demo.html'
        ],
        PROJECT_MANAGER_AND_SALES: [
            'dashboard.html', 'profile.html', 'notifications.html', 'search.html',
            'clients.html', 'billing.html', 'leaves.html', 'incentives.html',
            'projects.html', 'meetings.html', 'issues.html', 'todo.html', 'timetable.html',
            'feedback.html', 'visits.html', 'areas.html', 'leads.html',
            'salary.html', 'employees.html', 'salary_slip_view.html', 'settings.html',
            'employee_report.html', 'client_report.html', 'projects_demo.html'
        ],
        CLIENT: [
            'dashboard.html', 'profile.html', 'notifications.html', 'search.html', 'todo.html'
        ]
    };

    function getAllowedPagesForRole(role) {
        const roleName = (role || '').toUpperCase();
        
        // 1. Try memory (server-fetched effective policy takes priority)
        if (window.__crmEffectiveAccessPolicy) return window.__crmEffectiveAccessPolicy.allowed_pages || [];

        // 2. Try localStorage (cached policy from previous session)
        const cached = JSON.parse(localStorage.getItem('crm_access_policy') || 'null');
        if (cached && (cached.allowed_pages || cached.page_access)) {
            window.__crmEffectiveAccessPolicy = cached;
            return cached.allowed_pages || (cached.page_access ? (cached.page_access[roleName] || []) : []);
        }
        // 3. Fallback to the built-in role→page map (covers dev mode and initial load)
        return DEFAULT_PAGE_ACCESS[roleName] || ['dashboard.html', 'profile.html', 'notifications.html', 'search.html'];
    }


    // Exported to window for use in syncAccessControl
    window.enforceRoleAccess = function(role) {
        if (!role || role === 'ADMIN') {
            hideAccessDeniedState();
            return true;
        }
        const path = window.location.pathname.split('/').pop() || 'index.html';
        if (path === 'index.html' || path === 'login.html') {
            hideAccessDeniedState();
            return true;
        }

        const allowed = getAllowedPagesForRole(role);
        if (!allowed.includes(path) && !allowed.includes('*')) {
            // Explicitly allow common utility pages and sub-pages
            if (['salary_slip_view.html'].includes(path)) {
                hideAccessDeniedState();
                return true;
            }
            showAccessDeniedState(role, path);
            return false;
        }
        
        hideAccessDeniedState();
        return true;
    };

    // --- OPTIMISTIC UI ---
    // If we have a user in session, show the page IMMEDIATELY.
    // Ensure background matches theme to avoid flash
    user = window.getUser();
    const storedTheme = localStorage.getItem('srm-theme') || 'light';
    if (storedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
    }
    const bgColor = storedTheme === 'dark' ? '#0f172a' : '#f0f5fb';
    document.body.style.backgroundColor = bgColor;

    if (user) {
        enforceRoleAccess(user.role);
        document.body.style.visibility = 'visible';
        document.body.style.opacity = '1';
        const el = document.getElementById('username-display');
        if (el) el.textContent = user.name || 'User';
    } else {
        // Fallback: hide until we get a profile (rare)
        document.body.style.visibility = 'hidden';
        document.body.style.opacity = '0';
        // Emergency unhide after 2 seconds to prevent permanent black screen
        setTimeout(() => { 
            document.body.style.visibility = 'visible';
            document.body.style.opacity = '1';
        }, 2000);
    }

    // Background Verification using ApiClient for robust token handling (auto-refresh)
    if (window.ApiClient && typeof window.ApiClient.request === 'function') {
        window.ApiClient.request('/auth/profile')
            .then(async profile => {
                if (!profile) return;
                const userData = { id: profile.id, name: profile.name || profile.email, email: profile.email, role: profile.role };
                localStorage.setItem('srm_user', JSON.stringify(userData));

                if (window.ApiClient.getEffectiveAccessPolicy) {
                    try {
                        const effective = await window.ApiClient.getEffectiveAccessPolicy();
                        window.__crmEffectiveAccessPolicy = effective;
                        localStorage.setItem('crm_access_policy', JSON.stringify(effective));
                    } catch (e) {
                        console.warn('Failed to load effective access policy, using fallback map', e);
                    }
                }

                enforceRoleAccess(userData.role);
                if (document.body) {
                    document.body.style.visibility = 'visible';
                    document.body.style.opacity = '1';
                }
                console.log('Background auth check successful (via ApiClient)');
                const el = document.getElementById('username-display');
                if (el) el.textContent = profile.name || 'User';

                // Initial sync to set version
                syncAccessControl(true);

                // Fetch and check for critical issues across the app
                if (typeof checkCriticalIssues === 'function') checkCriticalIssues();
            })
            .catch((err) => {
                console.warn('Background auth check failed (via ApiClient):', err);
                if (err.status === 401) {
                    clearTokens();
                    if (!isLoginPage) window.location.replace('index.html');
                } else if (document.body) {
                    document.body.style.visibility = 'visible';
                    document.body.style.opacity = '1';
                }
            });
    } else {
        // Fallback for when ApiClient is not available (raw fetch)
        fetch(`${API}/auth/profile`, {
            headers: { 'Authorization': `Bearer ${token}` }
        })
            .then(r => {
                if (!r.ok) {
                    if (r.status === 401) {
                        clearTokens();
                        if (!isLoginPage) window.location.replace('index.html');
                    }
                    return null;
                }
                return r.json();
            })
            .then(async profile => {
                if (!profile) return;
                const userData = { id: profile.id, name: profile.name || profile.email, email: profile.email, role: profile.role };
                localStorage.setItem('srm_user', JSON.stringify(userData));
                enforceRoleAccess(userData.role);
                console.log('Background auth check successful (via Fallback Fetch)');
            })
            .catch(err => console.warn('Fallback auth check failing:', err));
    }
}

// --- AUTOMATIC ACCESS SYNC ---
async function syncAccessControl(isInitial = false) {
    const params = new URLSearchParams(window.location.search);
    if (params.get('dev') === 'true') return; // Do not run background sync in dev mode

    const token = getToken();
    if (!token) return;

    try {
        const response = await fetch(`${window.API || '/api'}/users/access-policy/status`, {
            headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!response.ok) {
            if (response.status === 401) window.logout && window.logout();
            return;
        }
        const status = await response.json();
        
        const cachedUser = getUser();
        const cachedVersion = localStorage.getItem('policy_version');
        
        // Detect changes
        const roleChanged = cachedUser && cachedUser.role !== status.role;
        const policyChanged = cachedVersion && parseInt(cachedVersion) !== status.policy_version;
        const deactivation = cachedUser && !status.is_active;

        if (deactivation) {
            alert('Your account has been deactivated. Logging out.');
            window.logout && window.logout();
            return;
        }

        if (roleChanged || policyChanged || isInitial) {
            localStorage.setItem('policy_version', status.policy_version);
            
            if (roleChanged || policyChanged) {
                console.log('Access control update detected, refreshing permissions...');
                let userData = cachedUser;
                
                // Try to fetch profile to get roles and preferences
                const profile = window.ApiClient ? await window.ApiClient.getProfile().catch(() => null) : null;
                if (profile) {
                    userData = {
                        id: profile.id,
                        name: profile.name || profile.email,
                        email: profile.email,
                        role: profile.role
                    };
                    
                    // Store user data in both
                    localStorage.setItem('srm_user', JSON.stringify(userData));
                    sessionStorage.setItem('srm_user', JSON.stringify(userData));
                    
                    // If profile includes latest policy, sync it to localStorage cache
                    if (profile.access_policy) {
                        localStorage.setItem('crm_access_policy', JSON.stringify(profile.access_policy));
                        window.__crmEffectiveAccessPolicy = profile.access_policy;
                    }
                }
                
                if (window.ApiClient && window.ApiClient.getEffectiveAccessPolicy) {
                    const effective = await window.ApiClient.getEffectiveAccessPolicy().catch(() => null);
                    if (effective) {
                        window.__crmEffectiveAccessPolicy = effective;
                        localStorage.setItem('crm_access_policy', JSON.stringify(effective));
                    }
                }

                if (userData) {
                    // Update UI: Dispatch event for SPA components to re-render
                    window.dispatchEvent(new CustomEvent('permissions-changed', { 
                        detail: { role: userData.role, policy: window.__crmEffectiveAccessPolicy } 
                    }));
                    
                    // Re-enforce access for current page
                    if (window.enforceRoleAccess) {
                        window.enforceRoleAccess(userData.role);
                    }
                }
                
                if (typeof window.showToast === 'function') window.showToast('Permissions updated automatically', 'info');
            }
        }
    } catch (e) {
        console.warn('Access sync failed:', e);
    }
}

// Set up background polling (every 30 seconds)
if (!window.__accessSyncInterval) {
    window.__accessSyncInterval = setInterval(() => syncAccessControl(), 30000);
}


// Re-evaluate auth on back/forward navigation
window.addEventListener('pageshow', (event) => {
    const params = new URLSearchParams(window.location.search);
    const isLocal = ['localhost', '127.0.0.1', ''].includes(window.location.hostname) || window.location.protocol === 'file:';
    if (params.get('dev') === 'true' && isLocal) return;

    const isLoginPage = window.location.pathname.endsWith('index.html') || window.location.pathname.endsWith('/');

    // If the page was restored from the bfcache and we have no token, kick them
    if (event.persisted && !getToken() && !isLoginPage) {
        window.location.replace('index.html');
    }

    // If we land on the login page but already have a VALID token, go to dashboard.
    const isBypass = params.get('dev') === 'true' || params.get('msg') === 'logged_out';

    if (isLoginPage && getToken() && !isBypass) {
        console.log('requireAuth: User already logged in, verifying session...');
        // Debounce: wait a tiny bit to ensure API is set from config
        setTimeout(() => {
            if (window.ApiClient && typeof window.ApiClient.request === 'function') {
                window.ApiClient.request('/auth/profile')
                    .then(r => {
                        console.log('requireAuth: Session verified, redirecting to dashboard');
                        window.location.replace('dashboard.html');
                    })
                    .catch(() => {
                        console.log('requireAuth: Stale session on login page, clearing tokens');
                        clearTokens();
                    });
            } else {
                fetch(API + '/auth/profile', {
                    headers: { 'Authorization': `Bearer ${token}` }
                }).then(r => {
                    if (r.ok) window.location.replace('dashboard.html');
                    else clearTokens();
                }).catch(() => clearTokens());
            }
        }, 300);
    }
});

// Logout
window.logout = function() {
    if (window.ApiClient && typeof window.ApiClient.clearTokens === 'function') {
        window.ApiClient.clearTokens();
    } else {
        window.clearTokens();
    }
    window.location.href = 'index.html?msg=logged_out';
}

// Global Critical Issue Check
window.checkCriticalIssues = async function() {
    // Only check if we are on a valid inner page
    const isLoginPage = window.location.pathname.endsWith('index.html') || window.location.pathname.endsWith('/');
    if (isLoginPage) return;

    try {
        const issues = await apiGet('/issues/?limit=100');
        const criticalIssues = issues.filter(i => i.severity === 'HIGH' && i.status === 'PENDING');

        if (criticalIssues.length > 0) {
            // 1. Highlight the sidebar link
            // Wait for sidebar to render just in case
            setTimeout(() => {
                const issuesLink = document.querySelector('a.sb-link[href="issues.html"]');
                if (issuesLink) {
                    issuesLink.classList.add('has-critical-issue');
                    // Optional: auto-expand the PM section if it's hidden
                    const parentSection = issuesLink.closest('.sb-section');
                    if (parentSection) {
                        const hdr = parentSection.querySelector('.sb-section-header');
                        const lst = parentSection.querySelector('.sb-section-items');
                        if (hdr && !hdr.classList.contains('open')) {
                            hdr.classList.add('open');
                            if (lst) lst.classList.add('open');
                        }
                    }
                }
            }, 500);

            // 2. Inject into the notification dropdown
            setTimeout(() => {
                const bellIcon = document.querySelector('.bi-bell')?.parentElement;
                if (bellIcon) {
                    // Make sure the red dot is visible
                    let dot = bellIcon.querySelector('.bg-danger');
                    if (!dot) {
                        bellIcon.insertAdjacentHTML('beforeend', '<span class="position-absolute bg-danger border border-white rounded-circle" style="width:10px;height:10px;top:8px;right:8px;"></span>');
                    }

                    // Update the dropdown menu content
                    const dropdownMenu = bellIcon.nextElementSibling;
                    if (dropdownMenu && dropdownMenu.classList.contains('dropdown-menu')) {
                        const notifCountBadge = dropdownMenu.querySelector('.badge.bg-danger');
                        if (notifCountBadge) {
                            notifCountBadge.textContent = criticalIssues.length;
                        }

                        // Replace the "No new alerts" text with the critical issue alert
                        const contentBody = dropdownMenu.querySelector('.p-3.text-center');
                        if (contentBody) {
                            contentBody.className = 'p-0';
                            contentBody.innerHTML = `
                                <div class="px-3 py-3 border-bottom d-flex gap-3 align-items-start" style="background-color: #FEF2F2; cursor: pointer;" onclick="window.location.href='issues.html'">
                                    <i class="bi bi-exclamation-octagon-fill text-danger mt-1 fs-5"></i>
                                    <div>
                                        <div class="fw-bold text-dark mb-1">Critical Issue Alert</div>
                                        <p class="mb-0 text-muted small" style="line-height: 1.4;">There ${criticalIssues.length === 1 ? 'is' : 'are'} ${criticalIssues.length} unresolved high-severity issue(s) requiring immediate attention.</p>
                                    </div>
                                </div>
                            `;
                        }
                    }
                }
            }, 600);
        }
    } catch (e) {
        console.warn("Could not check critical issues", e);
    }
}

// Session Management (Inactivity Timeout)
const INACTIVITY_LIMIT_MS = 7 * 24 * 60 * 60 * 1000; // 7 days (more persistent)
let inactivityTimer;

function resetInactivityTimer() {
    clearTimeout(inactivityTimer);
    if (getToken()) {
        inactivityTimer = setTimeout(() => {
            alert('Your session has expired due to inactivity. Please log in again.');
            logout();
        }, INACTIVITY_LIMIT_MS);
    }
}

// Attach activity listeners once DOM is ready
if (typeof document !== 'undefined') {
    ['click', 'mousemove', 'keydown', 'scroll', 'touchstart'].forEach(evt =>
        document.addEventListener(evt, resetInactivityTimer, { passive: true })
    );
}

// Call initially
resetInactivityTimer();

// Generic authenticated fetch (moved to utils.js)
// GET shorthand (moved to utils.js)
// POST shorthand (moved to utils.js)
// PATCH shorthand (moved to utils.js)
// DELETE shorthand (moved to utils.js)



