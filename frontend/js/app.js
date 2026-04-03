// frontend/js/app.js

// Pull-to-refresh for mobile
(function initPullToRefresh() {
    if (!('ontouchstart' in window)) return;
    let startY = 0;
    const threshold = 150;
    document.addEventListener('touchstart', e => {
        if (window.scrollY === 0) startY = e.touches[0].pageY;
        else startY = 0;
    }, { passive: true });
    document.addEventListener('touchmove', e => {
        if (startY > 0) {
            const pullDistance = e.touches[0].pageY - startY;
            if (pullDistance > 10) {
                // Potential indicator logic
            }
        }
    }, { passive: true });
    document.addEventListener('touchend', e => {
        if (startY > 0) {
            const pullDistance = e.changedTouches[0].pageY - startY;
            if (pullDistance > threshold) {
                showToast('Refreshing...');
                setTimeout(() => location.reload(), 500);
            }
        }
        startY = 0;
    });
})();


// Global DOM references (initialized in DOMContentLoaded)
let mainContent;

// View Routing
async function loadView(viewName) {
    if (!mainContent) mainContent = document.getElementById('main-content') || document.body;
    mainContent.innerHTML = '<div style="display:flex; justify-content:center; padding: 40px; color: var(--primary); font-size: 24px;"><i class="fa-solid fa-circle-notch fa-spin"></i></div>';

    try {
        if (viewName === 'dashboard') {
            await renderDashboard();
        } else if (viewName === 'clients') {
            await renderClients();
        } else if (viewName === 'leads') {
            await renderLeads();
        } else if (viewName === 'areas') {
            await renderAreas();
        } else if (viewName === 'visits') {
            await renderVisits();
        } else if (viewName === 'feedback') {
            await renderFeedback();
        } else if (viewName === 'projects') {
            await renderProjects();
        } else if (viewName === 'meetings') {
            await renderMeetings();
        } else if (viewName === 'issues') {
            await renderIssues();
        } else if (viewName === 'employees') {
            await renderEmployees();
        } else if (viewName === 'salary') {
            await renderSalary();
        } else if (viewName === 'incentives') {
            await renderIncentives();
        } else if (viewName === 'admin') {
            await renderAdmin();
        } else if (viewName === 'profile') {
            await renderProfile();
        } else {
            mainContent.innerHTML = `
                <div class="card" style="text-align:center; padding: 60px;">
                    <i class="fa-solid fa-person-digging" style="font-size: 48px; color: var(--text-muted); margin-bottom: 16px;"></i>
                    <h2>${viewName.charAt(0).toUpperCase() + viewName.slice(1)} View is Under Construction</h2>
                    <p class="text-muted">Will be built out shortly.</p>
                </div>
            `;
        }
    } catch (e) {
        console.error('View load failed:', e);
        mainContent.innerHTML = `<div class="card text-danger"><i class="fa-solid fa-triangle-exclamation"></i> Error loading view. Please verify backend connection.</div>`;
    }
}
window.loadView = loadView; // Expose globally

document.addEventListener('DOMContentLoaded', () => {
    // Only activate SPA routing on index/login page (not on standalone template pages)
    const loginForm = document.getElementById('login-form');
    if (!loginForm) return;

    // DOM Elements
    const loginView = document.getElementById('login-view');
    const appShell = document.getElementById('app-shell');
    const loginError = document.getElementById('login-error');
    const logoutBtn = document.getElementById('logout-btn');
    mainContent = document.getElementById('main-content') || document.body;
    const navItems = document.querySelectorAll('.sidebar-nav .nav-item');
    const topbarTitle = document.getElementById('topbar-title') || { innerText: '' };

    // Auth Guard
    function checkAuth() {
        const token = window.ApiClient.getAccessToken();
        if (token) {
            showApp();
            let view = 'dashboard';
            const file = window.location.pathname.split('/').pop().replace('.html', '');
            if (file && file !== 'index' && file !== '') {
                view = file;
            }
            loadView(view);
        } else {
            showLogin();
        }
    }

    function showLogin() {
        if (loginView) loginView.classList.remove('hidden');
        if (appShell) appShell.classList.add('hidden');
    }

    function showApp() {
        if (loginView) loginView.classList.add('hidden');
        if (appShell) appShell.classList.remove('hidden');
    }

    // Login Form
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const submitBtn = loginForm.querySelector('button');

            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Authenticating...';
            loginError.classList.add('hidden');

            try {
                await window.ApiClient.login(email, password);
                showApp();
                loadView('dashboard');
            } catch (error) {
                loginError.classList.remove('hidden');
            } finally {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<span>Sign In</span><i class="fa-solid fa-arrow-right"></i>';
            }
        });
    }

    // Logout
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            window.ApiClient.clearTokens();
            showLogin();
        });
    }

    window.addEventListener('auth-failed', () => {
        window.ApiClient.clearTokens();
        showLogin();
    });

    // Sidebar Navigation - Accordion Logic
    const toggleSections = document.querySelectorAll('.toggle-section');
    toggleSections.forEach(section => {
        section.addEventListener('click', () => {
            const subItems = section.nextElementSibling;
            const arrow = section.querySelector('.section-arrow');

            if (subItems && subItems.classList.contains('nav-sub-items')) {
                const isHidden = subItems.classList.contains('hidden');

                // Close all other accordions
                document.querySelectorAll('.nav-sub-items').forEach(el => el.classList.add('hidden'));
                document.querySelectorAll('.section-arrow').forEach(arr => {
                    arr.classList.remove('fa-chevron-down');
                    arr.classList.add('fa-chevron-right');
                });

                // Open clicked accordion if it was closed
                if (isHidden) {
                    subItems.classList.remove('hidden');
                    if (arrow) {
                        arrow.classList.remove('fa-chevron-right');
                        arrow.classList.add('fa-chevron-down');
                    }
                }
            }
        });
    });

    // Sidebar Navigation - View Routing
    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            const viewName = e.currentTarget.getAttribute('data-view');
            if (viewName) {
                navItems.forEach(nav => nav.classList.remove('active'));
                e.currentTarget.classList.add('active');

                const sectionOuter = e.currentTarget.closest('.sidebar-section');
                const emojiSpan = sectionOuter ? sectionOuter.querySelector('.nav-icon') : null;
                const emojiHTML = emojiSpan ? emojiSpan.outerHTML : '';
                const text = e.currentTarget.innerText.trim();

                const topbarBreadcrumb = document.getElementById('topbar-breadcrumb');
                if (topbarBreadcrumb) {
                    topbarBreadcrumb.innerHTML = `${emojiHTML} <span style="margin-left:8px;">${text}</span>`;
                }

                loadView(viewName);
            }
        });
    });

    // Kickoff
    checkAuth();
});

async function renderDashboard() {
        const user = window.ApiClient.getCurrentUser();
        let stats = { total_clients: 0, open_issues: 0, total_visits: 0, total_shops: 0 };
        let shops = [], visits = [], clients = [], todos = [];
        try {
            const res = await window.ApiClient.getDashboardStats();
            stats.total_clients = res.total_clients || 0;
            stats.open_issues = res.open_issues_count || res.open_issues || 0;
            stats.total_visits = res.total_visits || 0;
            stats.total_shops = res.total_shops || 0;
        } catch (e) { console.warn('Dashboard stats failed', e); }
        try { shops = await window.ApiClient.getShops(); stats.total_shops = stats.total_shops || shops.length; } catch (e) { }
        try { clients = await window.ApiClient.getClients(); stats.total_clients = stats.total_clients || clients.length; } catch (e) { }
        try { visits = await window.ApiClient.getVisits(); stats.total_visits = stats.total_visits || visits.length; } catch (e) { }
        try { todos = await window.ApiClient.getTodos(); } catch (e) { } // Fetch actual personal to-dos

        const dateStr = new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

        const todoRows = todos.length ? todos.slice(0, 5).map(t => {
            const isDone = t.status === 'RESOLVED';
            const dotColor = isDone ? 'dot-green' : 'dot-yellow';
            const badgeColor = isDone ? 'badge-green-light' : 'badge-purple-light';
            return `
                <div class="task-item" style="${isDone ? 'opacity:0.6;' : ''}">
                    <div class="task-dot ${dotColor}"></div>
                    <div class="task-text" style="${isDone ? 'text-decoration:line-through;' : ''}">${t.title}</div>
                    <div class="task-badge ${badgeColor}">${isDone ? 'Done' : 'Pending'}</div>
                </div>`;
        }).join('') : `<div class="text-muted" style="padding:10px;">No pending tasks!</div>`;

        // Dynamic KPI data based on role
        const role = (user?.role || '').toUpperCase();
        const isAdmin = role === 'ADMIN';
        
        const kpi3 = isAdmin ? {
            title: 'Open Issues',
            value: stats.open_issues || 0,
            trend: '<i class="fa-solid fa-triangle-exclamation"></i> High Priority',
            trendClass: 'trend-down', // using red for alert
            icon: 'fa-solid fa-circle-exclamation',
            iconClass: 'icon-yellow',
            view: 'issues'
        } : {
            title: 'Ongoing Projects',
            value: '28', // Placeholder or from stats if available
            trend: '<i class="fa-solid fa-arrow-trend-down"></i> -2.1% <span>vs last month</span>',
            trendClass: 'trend-down',
            icon: 'fa-solid fa-briefcase',
            iconClass: 'icon-yellow',
            view: 'projects'
        };

        mainContent.innerHTML = `
        <!-- Row 1: Greeting -->
        <div class="d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2 class="page-section-title">Dashboard</h2>
                <p class="text-muted small mb-0">Welcome back! Here's what's happening today.</p>
            </div>
        </div>
        
        <!-- Row 2: KPI Grid of 4 (Lovable Style) -->
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 24px; margin-bottom: 24px;">
            <div class="stat-card" onclick="loadView('leads')" style="cursor:pointer;">
                <div class="stat-content-left">
                    <div class="stat-title">Total Leads</div>
                    <div class="stat-value">1,284</div>
                    <div class="stat-trend trend-up"><i class="fa-solid fa-arrow-trend-up"></i> +12.5% <span>vs last month</span></div>
                </div>
                <div class="stat-icon-wrapper icon-purple">
                    <i class="fa-solid fa-bullseye"></i>
                </div>
            </div>
            
            <div class="stat-card" onclick="loadView('clients')" style="cursor:pointer;">
                <div class="stat-content-left">
                    <div class="stat-title">Active Clients</div>
                    <div class="stat-value">342</div>
                    <div class="stat-trend trend-up"><i class="fa-solid fa-arrow-trend-up"></i> +4.2% <span>vs last month</span></div>
                </div>
                <div class="stat-icon-wrapper icon-teal">
                    <i class="fa-solid fa-users"></i>
                </div>
            </div>
            
            <div class="stat-card" onclick="loadView('${kpi3.view}')" style="cursor:pointer;">
                <div class="stat-content-left">
                    <div class="stat-title">${kpi3.title}</div>
                    <div class="stat-value">${kpi3.value}</div>
                    <div class="stat-trend ${kpi3.trendClass}">${kpi3.trend}</div>
                </div>
                <div class="stat-icon-wrapper ${kpi3.iconClass}">
                    <i class="${kpi3.icon}"></i>
                </div>
            </div>
            
            <div class="stat-card" onclick="loadView('billing')" style="cursor:pointer;">
                <div class="stat-content-left">
                    <div class="stat-title">Revenue (MTD)</div>
                    <div class="stat-value">₹24.5L</div>
                    <div class="stat-trend trend-up"><i class="fa-solid fa-arrow-trend-up"></i> +18.7% <span>vs last month</span></div>
                </div>
                <div class="stat-icon-wrapper icon-green">
                    <i class="fa-solid fa-indian-rupee-sign"></i>
                </div>
            </div>
        </div>
        
        <!-- Row 3: Charts (3 columns) -->
        <div style="display: grid; grid-template-columns: repeat(3, minmax(300px, 1fr)); gap: 24px; margin-bottom: 24px;">
            <div class="card">
                <h2 style="margin-bottom: 24px; font-size: 16px;">Leads by Month</h2>
                <div style="position: relative; height: 250px; width: 100%;">
                    <canvas id="leadsMonthChart"></canvas>
                </div>
            </div>
            
            <div class="card">
                <h2 style="margin-bottom: 24px; font-size: 16px;">Revenue Trend</h2>
                <div style="position: relative; height: 250px; width: 100%;">
                    <canvas id="revenueTrendChart"></canvas>
                </div>
            </div>
            
            <div class="card">
                <h2 style="margin-bottom: 24px; font-size: 16px;">Lead Sources</h2>
                <div style="position: relative; height: 250px; width: 100%; display: flex; justify-content: center;">
                    <canvas id="leadSourcesChart"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Row 4: Action Lists -->
        <div class="dashboard-lists-grid">
            <!-- Recent Activity -->
            <div class="card">
                <div class="panel-title" style="display:flex;justify-content:space-between;align-items:center;">Recent Activity <span class="badge badge-purple-light" style="font-size: 10px; font-weight: 700;">Last 10 Actions</span></div>
                <div class="activity-list">
                    <div class="activity-item">
                        <div class="activity-icon-circle icon-circle-purple">
                            <i class="fa-solid fa-bullseye"></i>
                        </div>
                        <div class="activity-text-wrapper">
                            <div class="activity-primary-text">New lead added</div>
                            <div class="activity-secondary-text">Rajesh Kumar — Website Inquiry</div>
                        </div>
                        <div class="activity-time">
                            <i class="fa-regular fa-clock"></i> 2 min ago
                        </div>
                    </div>
                    <div class="activity-item">
                        <div class="activity-icon-circle icon-circle-purple">
                            <i class="fa-regular fa-calendar-check"></i>
                        </div>
                        <div class="activity-text-wrapper">
                            <div class="activity-primary-text">Meeting scheduled</div>
                            <div class="activity-secondary-text">Infosys — Project Review</div>
                        </div>
                        <div class="activity-time">
                            <i class="fa-regular fa-clock"></i> 15 min ago
                        </div>
                    </div>
                    <div class="activity-item">
                        <div class="activity-icon-circle icon-circle-purple">
                            <i class="fa-solid fa-triangle-exclamation"></i>
                        </div>
                        <div class="activity-text-wrapper">
                            <div class="activity-primary-text">Issue escalated</div>
                            <div class="activity-secondary-text">TCS Portal — High Severity</div>
                        </div>
                        <div class="activity-time">
                            <i class="fa-regular fa-clock"></i> 1 hr ago
                        </div>
                    </div>
                    <div class="activity-item">
                        <div class="activity-icon-circle icon-circle-purple">
                            <i class="fa-solid fa-user-check"></i>
                        </div>
                        <div class="activity-text-wrapper">
                            <div class="activity-primary-text">Client converted</div>
                            <div class="activity-secondary-text">Wipro Technologies</div>
                        </div>
                        <div class="activity-time">
                            <i class="fa-regular fa-clock"></i> 3 hrs ago
                        </div>
                    </div>
                    <div class="activity-item">
                        <div class="activity-icon-circle icon-circle-purple">
                            <i class="fa-solid fa-indian-rupee-sign"></i>
                        </div>
                        <div class="activity-text-wrapper">
                            <div class="activity-primary-text">Payment received</div>
                            <div class="activity-secondary-text">₹2.5L — HCL Project</div>
                        </div>
                        <div class="activity-time">
                            <i class="fa-regular fa-clock"></i> 5 hrs ago
                        </div>
                    </div>
                </div>
            </div>

            <!-- Pending Tasks -->
            <div class="card">
                <div class="panel-title" style="display:flex;justify-content:space-between;align-items:center;">My Pending Tasks <button onclick="window.alert('Todo modal coming soon')" class="btn btn-ghost" style="font-size:12px;padding:4px 8px;"><i class="fa-solid fa-plus"></i></button></div>
                <div class="task-list">
                    ${todoRows}
                </div>
            </div>
        </div>
    `;

        // Initialize Charts (Delaying 100ms to allow DOM injection to finish)
        setTimeout(() => {
            initCharts();
        }, 100);
    }

    function initCharts() {
        if (!window.Chart) return;

        // Common Grid Options for the light dashed lines in the screenshot
        const gridOptions = {
            color: '#E5E7EB',
            borderDash: [5, 5],
            drawBorder: false
        };

        // 1. Leads by Month (Bar Chart, Purple)
        const ctxLeadsMonth = document.getElementById('leadsMonthChart');
        if (ctxLeadsMonth) {
            new Chart(ctxLeadsMonth, {
                type: 'bar',
                data: {
                    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                    datasets: [{
                        label: 'Leads',
                        data: [65, 70, 95, 100, 135, 125],
                        backgroundColor: '#6366f1',
                        borderRadius: 4,
                        barPercentage: 0.7
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 140,
                            ticks: { stepSize: 35, color: '#9CA3AF' },
                            grid: gridOptions,
                            border: { display: false }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#9CA3AF' },
                            border: { display: false }
                        }
                    }
                }
            });
        }

        // 2. Revenue Trend (Line Chart, Teal)
        const ctxRev = document.getElementById('revenueTrendChart');
        if (ctxRev) {
            new Chart(ctxRev, {
                type: 'line',
                data: {
                    labels: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun'],
                    datasets: [{
                        label: 'Revenue',
                        data: [180, 220, 190, 310, 280, 360],
                        borderColor: '#14b8a6',
                        backgroundColor: '#14b8a6',
                        pointBackgroundColor: '#14b8a6',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        pointRadius: 5,
                        tension: 0.4, // Smooth curvy line
                        borderWidth: 3
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: {
                            beginAtZero: true,
                            max: 360,
                            ticks: {
                                stepSize: 90,
                                callback: function (value) { return '₹' + value + 'K'; },
                                color: '#9CA3AF'
                            },
                            grid: gridOptions,
                            border: { display: false }
                        },
                        x: {
                            grid: { display: false },
                            ticks: { color: '#9CA3AF' },
                            border: { display: false }
                        }
                    }
                }
            });
        }

        // 3. Lead Sources (Doughnut Chart)
        const ctxSources = document.getElementById('leadSourcesChart');
        if (ctxSources) {
            new Chart(ctxSources, {
                type: 'doughnut',
                data: {
                    labels: ['Website', 'Referral', 'Cold Call', 'Social', 'Other'],
                    datasets: [{
                        data: [40, 25, 20, 10, 5],
                        backgroundColor: ['#6366f1', '#14b8a6', '#f59e0b', '#10B981', '#9CA3AF'],
                        borderWidth: 2,
                        borderColor: '#fff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '75%', // Make it thin like the screenshot
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                usePointStyle: true,
                                boxWidth: 8,
                                padding: 20,
                                color: '#6B7280'
                            }
                        }
                    }
                }
            });
        }
    }

    async function renderClients() {
        try {
            const user = window.ApiClient.getCurrentUser();
            const isPM = user && (user.role === 'PROJECT_MANAGER' || user.role === 'PROJECT_MANAGER_AND_SALES');
            const clients = isPM ? await window.ApiClient.getMyClients() : await window.ApiClient.getClients();
            const rows = clients.length === 0
                ? `<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--text-muted);">No clients found. Add your first client!</td></tr>`
                : clients.map(c => `
                    <tr>
                        <td><div style="font-weight:500;">${c.name}</div><div style="font-size:12px;color:var(--text-muted);">${c.email}</div></td>
                        <td>${c.phone || '—'}</td>
                        <td>${c.organization || '—'}</td>
                        <td>${c.pm_id ? `<span class="badge badge-primary">PM #${c.pm_id}</span>` : `<span class="badge badge-warning">Unassigned</span>`}</td>
                        <td style="display:flex;gap:6px;">
                            <button class="btn btn-ghost" title="Add Issue" style="padding:4px 8px;" onclick="openNewIssueModal('${c.id}')"><i class="fa-solid fa-triangle-exclamation" style="color:var(--warning);"></i></button>
                            <button class="btn btn-ghost" title="Add Meeting" style="padding:4px 8px;" onclick="openNewMeetingModal('${c.id}')"><i class="fa-regular fa-calendar-plus" style="color:var(--primary);"></i></button>
                        </td>
                    </tr>`).join('');
            mainContent.innerHTML = `
            <div class="page-header">
                <div><h1 style="margin-bottom:4px;">Clients</h1><p class="text-muted">${clients.length} onboarded accounts</p></div>
                <button class="btn btn-primary" onclick="openNewClientModal()"><i class="fa-solid fa-plus"></i> New Client</button>
            </div>
            <div class="card" style="padding:0;">
                <div class="table-container">
                    <table class="table">
                        <thead><tr><th>Client Name</th><th>Phone</th><th>Organization</th><th>Assigned PM</th><th>Actions</th></tr></thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>`;
        } catch (e) { throw e; }
    }

    async function renderLeads() {
        let shops = [];
        try {
            // Fetch kanban structure from backend if supported, or group manually
            shops = await window.ApiClient.getShops();
        } catch (e) { console.warn('Shops/Leads fetch failed', e); }

        const columns = [
            { key: 'LEAD', label: 'Lead', color: 'badge-purple-light', border: '' },
            { key: 'PITCHING', label: 'Pitching', color: 'badge-purple-light', border: '' },
            { key: 'NEGOTIATION', label: 'Negotiation', color: 'badge-purple-light', border: '3px solid var(--warning)' },
            { key: 'DELIVERY', label: 'Delivery', color: 'badge-green-light', border: '3px solid var(--success)' },
        ];

        const grouped = {};
        columns.forEach(c => { grouped[c.key] = []; });
        shops.forEach(s => {
            const st = (s.pipeline_stage || 'LEAD').toUpperCase();
            if (grouped[st]) grouped[st].push(s);
            else grouped['LEAD'].push(s); // Fallback for unrecognised stages
        });

        const makeCard = (s, border) => {
            const initials = (s.contact_person || s.name || '?').split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
            const isConverted = s.pipeline_stage === 'DELIVERY' || s.pipeline_stage === 'MAINTENANCE';

            return `
            <div class="card kanban-card" style="margin-bottom:12px;padding:16px;${border ? 'border-left:' + border + ';' : ''}">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
                    <div style="font-weight:600;font-size:15px;color:var(--text-dark);">${s.name || 'Unnamed'}</div>
                    <div class="dropdown">
                        <button class="btn btn-ghost p-1" data-bs-toggle="dropdown"><i class="fa-solid fa-ellipsis-vertical"></i></button>
                        <ul class="dropdown-menu shadow border-0">
                            <li><a class="dropdown-item" href="javascript:void(0)" onclick="openEditShopModal('${s.id}')"><i class="fa-solid fa-pen me-2"></i> Edit</a></li>
                            ${!isConverted ? `<li><a class="dropdown-item" href="javascript:void(0)" onclick="openNewBillModal('${s.id}')"><i class="fa-solid fa-file-invoice-dollar me-2 text-success"></i> Convert & Bill</a></li>` : ''}
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item text-danger" href="javascript:void(0)" onclick="confirmDeleteShop('${s.id}')"><i class="fa-solid fa-trash me-2"></i> Delete</a></li>
                        </ul>
                    </div>
                </div>
                <div class="text-muted" style="font-size:13px;margin-bottom:4px;"><i class="fa-solid fa-user me-2"></i> ${s.contact_person || '—'}</div>
                <div class="text-muted" style="font-size:13px;margin-bottom:12px;"><i class="fa-solid fa-phone me-2"></i> ${s.phone || '—'}</div>
                
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <select class="form-control" style="height:28px;font-size:11px;width:110px;padding:2px 5px;" onchange="updateShopStatus('${s.id}', this.value)">
                        ${columns.map(c => `<option value="${c.key}" ${s.pipeline_stage === c.key ? 'selected' : ''}>${c.label}</option>`).join('')}
                    </select>
                    <div style="width:28px;height:28px;border-radius:50%;background:var(--primary-light);color:var(--primary);display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;" title="Assigned Agent">
                        ${initials}
                    </div>
                </div>
            </div>`;
        };

        const kbCols = columns.map(col => `
            <div class="kanban-column" style="flex:1;min-width:300px;background:var(--surface);border-radius:12px;padding:16px;border:1px solid var(--border);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
                    <h3 style="margin:0;font-size:16px;font-weight:700;color:var(--text-1);">${col.label}</h3>
                    <span class="badge ${col.color}" style="background:var(--primary-soft);color:var(--primary);">${grouped[col.key].length}</span>
                </div>
                <div class="kanban-cards-container" style="min-height:100px;">
                    ${grouped[col.key].length
                ? grouped[col.key].map(s => makeCard(s, col.border)).join('')
                : `<div style="text-align:center;padding:32px;border:2px dashed var(--border);border-radius:12px;color:var(--text-3);font-size:13px;">Drop leads here</div>`
            }
                </div>
            </div>`).join('');

        mainContent.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div>
                <h1 style="margin-bottom:4px;">Project Overview</h1>
                <p class="text-muted">Manage your sales pipeline and convert shops to projects.</p>
            </div>
            <button class="btn btn-primary shadow-sm" onclick="openNewShopModal()"><i class="fa-solid fa-plus me-2"></i> Add Lead</button>
        </div>
        <div class="kanban-board" style="display:flex;gap:20px;overflow-x:auto;padding-bottom:16px;align-items:flex-start;">
            ${kbCols}
        </div>`;
    }

    // Shop Status Update
    window.updateShopStatus = async (shopId, newStatus) => {
        try {
            await window.ApiClient.updateShop(shopId, { pipeline_stage: newStatus });
            showToast(`Status updated to ${newStatus}`);
            renderLeads();
        } catch (e) {
            showToast('Failed to update status', 'error');
        }
    };

    // Confirm Delete Shop
    window.confirmDeleteShop = async (shopId) => {
        if (confirm("Are you sure you want to delete this lead? This action cannot be undone.")) {
            try {
                await window.ApiClient.deleteShop(shopId);
                showToast('Lead deleted successfully');
                renderLeads();
            } catch (e) {
                showToast('Could not delete lead. Admin privileges may be required.', 'error');
            }
        }
    };

    // Modal: Edit Shop
    window.openEditShopModal = async (shopId) => {
        try {
            const shop = await window.ApiClient.request(`/shops/${shopId}`);
            let areas = [];
            try { areas = await window.ApiClient.getAreas(); } catch (e) { }

            const areaOptions = areas.map(a => `<option value="${a.id}" ${a.id == shop.area_id ? 'selected' : ''}>${a.name}</option>`).join('');

            const html = `
                <div class="form-group"><label>Shop Name *</label><input type="text" id="es-name" class="form-control" value="${shop.name}" required></div>
                <div class="form-group"><label>Contact Person</label><input type="text" id="es-contact" class="form-control" value="${shop.contact_person || ''}"></div>
                <div class="form-group"><label>Phone</label><input type="text" id="es-phone" class="form-control" value="${shop.phone || ''}"></div>
                <div class="form-group"><label>Email</label><input type="email" id="es-email" class="form-control" value="${shop.email || ''}"></div>
                <div class="form-group">
                    <label>Area *</label>
                    <select id="es-area" class="form-control" required>
                        <option value="">-- Select Area --</option>
                        ${areaOptions}
                    </select>
                </div>
                <div class="form-group"><label>Address</label><textarea id="es-addr" class="form-textarea">${shop.address || ''}</textarea></div>
            `;

            createModal('modal-edit-shop', 'Edit Lead Details', html, async () => {
                const data = {
                    name: document.getElementById('es-name').value,
                    contact_person: document.getElementById('es-contact').value,
                    phone: document.getElementById('es-phone').value,
                    email: document.getElementById('es-email').value,
                    area_id: parseInt(document.getElementById('es-area').value),
                    address: document.getElementById('es-addr').value
                };
                if (!data.name || !data.area_id) throw new Error("Shop Name and Area are required");

                await window.ApiClient.updateShop(shopId, data);
                showToast('Lead updated successfully');
                renderLeads();
            });
        } catch (e) {
            showToast('Failed to load lead details', 'error');
        }
    };

    async function renderAreas() {
        let areas = [], shops = [], selectedAreaId = null;
        try { areas = await window.ApiClient.getAreas(); } catch (e) { console.warn('Areas fetch failed', e); }
        try { shops = await window.ApiClient.getShops(); } catch (e) { console.warn('Shops fetch failed', e); }

        if (areas.length) selectedAreaId = areas[0].id;
        const filteredShops = selectedAreaId ? shops.filter(s => s.area_id === selectedAreaId) : shops;
        const activeArea = areas.find(a => a.id === selectedAreaId);

        const areaItems = areas.length
            ? areas.map(a => {
                const count = shops.filter(s => s.area_id === a.id).length;
                const isActive = a.id === selectedAreaId;
                return `<div class="area-item" data-area-id="${a.id}" style="padding:12px 16px;border-left:3px solid ${isActive ? 'var(--primary)' : 'transparent'};background:${isActive ? 'var(--primary-light)' : 'transparent'};cursor:pointer;transition:background 0.2s;">
                    <div style="font-weight:${isActive ? '600' : '500'};color:${isActive ? 'var(--primary)' : 'inherit'}">${a.name}</div>
                    <div style="font-size:13px;color:var(--text-muted);margin-top:4px;"><i class="fa-solid fa-store"></i> ${count} shops</div>
                </div>`;
            }).join('')
            : `<div class="text-muted" style="padding:24px;text-align:center;">No areas found.</div>`;

        const shopRows = filteredShops.length
            ? filteredShops.map(s => `
                <tr>
                    <td><div style="font-weight:500;">${s.name}</div><div style="font-size:12px;color:var(--text-muted);">${s.address || '\u2014'}</div></td>
                    <td>${s.owner_name || '\u2014'}</td>
                    <td>${s.phone || '\u2014'}</td>
                    <td><span class="badge badge-purple-light">${s.pipeline_stage || 'LEAD'}</span></td>
                    <td><button class="btn btn-ghost" style="padding:4px;"><i class="fa-solid fa-ellipsis-vertical"></i></button></td>
                </tr>`).join('')
            : `<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--text-muted);">No shops in this area.</td></tr>`;

        mainContent.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div><h1 style="margin-bottom:4px;">Areas &amp; Shops</h1><p class="text-muted">Geographical tracking for field sales.</p></div>
            <div style="display:flex;gap:12px;">
                <button class="btn btn-secondary"><i class="fa-solid fa-location-dot"></i> New Area</button>
                <button class="btn btn-primary"><i class="fa-solid fa-store"></i> New Shop</button>
            </div>
        </div>
        <div style="display:flex;gap:24px;align-items:flex-start;">
            <div class="card" style="width:280px;flex-shrink:0;padding:0;">
                <div style="padding:16px;border-bottom:1px solid var(--border);"><input type="text" class="form-control" placeholder="Search areas..." id="area-search"></div>
                <div id="area-list" style="padding:8px 0;">${areaItems}</div>
            </div>
            <div class="card" style="flex:1;padding:0;">
                <div style="padding:20px;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center;">
                    <h3 style="margin:0;">Shops in ${activeArea ? activeArea.name : 'All Areas'}</h3>
                    <span class="badge badge-purple-light">${filteredShops.length} Total</span>
                </div>
                <div class="table-container"><table class="table">
                    <thead><tr><th>SHOP NAME</th><th>OWNER</th><th>PHONE</th><th>STATUS</th><th></th></tr></thead>
                    <tbody>${shopRows}</tbody>
                </table></div>
            </div>
        </div>`;

        document.querySelectorAll('.area-item').forEach(el => {
            el.addEventListener('click', () => {
                selectedAreaId = parseInt(el.dataset.areaId);
                renderAreas();
            });
        });
    }

    async function renderVisits() {
        let visits = [];
        try { visits = await window.ApiClient.getVisits(); } catch (e) { console.warn('Visits fetch failed', e); }

        const today = new Date().toISOString().slice(0, 10);
        const weekAgo = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
        const todayCount = visits.filter(v => (v.visit_date || '').slice(0, 10) === today).length;
        const weekCount = visits.filter(v => v.status === 'SATISFIED' || v.status === 'ACCEPT' && (v.visit_date || '') >= weekAgo).length;
        const missedCount = visits.filter(v => v.status === 'DECLINE').length;

        const statusBadge = s => ({
            'SATISFIED': '<span class="badge badge-green-light">Satisfied</span>',
            'ACCEPT': '<span class="badge badge-purple-light">Accepted</span>',
            'DECLINE': '<span class="badge badge-red-light">Declined</span>',
            'TAKE_TIME_TO_THINK': '<span class="badge badge-warning">Thinking</span>'
        }[s] || `<span class="badge">${s || '—'}</span>`);

        const rows = visits.length ? visits.map(v => `
            <tr>
                <td style="font-weight:500;">${v.shop_name || v.shop_id || '—'}</td>
                <td>${v.area_name || '—'}</td>
                <td>${v.agent_name || v.agent_id || '—'}</td>
                <td>${v.visit_date ? new Date(v.visit_date).toLocaleDateString() : '—'}</td>
                <td>${v.visit_time || '—'}</td>
                <td>${statusBadge(v.status)}</td>
                <td class="text-muted" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${v.remarks || '—'}</td>
            </tr>`).join('') :
            `<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-muted);">No visits recorded yet.</td></tr>`;

        mainContent.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div><h1 style="margin-bottom:4px;">Visits</h1><p class="text-muted">${visits.length} total visits tracked</p></div>
            <button class="btn btn-primary" onclick="openLogVisitModal()"><i class="fa-solid fa-location-dot"></i> Log Visit</button>
        </div>

        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:24px;margin-bottom:24px;">
            <div class="card" style="padding:20px;"><div class="text-muted" style="font-size:12px;font-weight:600;margin-bottom:8px;">TODAY'S VISITS</div><div style="font-size:28px;font-weight:700;color:var(--primary);">${todayCount}</div></div>
            <div class="card" style="padding:20px;"><div class="text-muted" style="font-size:12px;font-weight:600;margin-bottom:8px;">COMPLETED THIS WEEK</div><div style="font-size:28px;font-weight:700;color:var(--success);">${weekCount}</div></div>
            <div class="card" style="padding:20px;"><div class="text-muted" style="font-size:12px;font-weight:600;margin-bottom:8px;">MISSED VISITS</div><div style="font-size:28px;font-weight:700;color:var(--danger);">${missedCount}</div></div>
        </div>
        <div class="card" style="padding:0;">
            <div class="table-container">
                <table class="table">
                    <thead><tr><th>SHOP</th><th>AREA</th><th>AGENT</th><th>DATE</th><th>TIME</th><th>STATUS</th><th>REMARKS</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
    }

    async function renderFeedback(activeTab = 'clients') {
        const user = window.ApiClient.getCurrentUser();
        const isAdmin = user && user.role === 'ADMIN';

        const tabBar = `
            <div class="tab-bar" style="margin-bottom:24px;">
                <button class="tab-btn ${activeTab === 'clients' ? 'active' : ''}" onclick="renderFeedback('clients')">Client Reviews</button>
                <button class="tab-btn ${activeTab === 'user' ? 'active' : ''}" onclick="renderFeedback('user')">System Feedback (Internal)</button>
            </div>`;

        if (activeTab === 'clients') {
            mainContent.innerHTML = `
            <div class="page-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <div>
                    <h1 style="margin-bottom: 4px;">Feedback & Satisfaction</h1>
                    <p class="text-muted">Monitor client experiences and internal system feedback.</p>
                </div>
            </div>
            ${tabBar}
            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-bottom: 24px;">
                <div class="card" style="padding: 24px; text-align: center;">
                    <div class="text-muted" style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">AVG RATING</div>
                    <div style="font-size: 36px; font-weight: 700; color: var(--primary); margin-bottom: 8px;">4.2<span style="font-size: 18px; color: var(--text-muted);">/5</span></div>
                    <div style="color: #F59E0B; font-size: 18px;"><i class="fa-solid fa-star"></i><i class="fa-solid fa-star"></i><i class="fa-solid fa-star"></i><i class="fa-solid fa-star"></i><i class="fa-regular fa-star-half-stroke"></i></div>
                </div>
                <div class="card" style="padding: 24px; text-align: center; display: flex; flex-direction: column; justify-content: center;">
                    <div class="text-muted" style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">POSITIVE</div>
                    <div style="font-size: 36px; font-weight: 700; color: var(--success);"><i class="fa-regular fa-face-smile"></i> 15</div>
                </div>
                <div class="card" style="padding: 24px; text-align: center; display: flex; flex-direction: column; justify-content: center;">
                    <div class="text-muted" style="font-size: 13px; font-weight: 600; margin-bottom: 8px;">NEEDS ATTENTION</div>
                    <div style="font-size: 36px; font-weight: 700; color: var(--danger);"><i class="fa-regular fa-face-frown"></i> 2</div>
                </div>
            </div>
            <h3 style="margin-bottom: 16px;">Recent Reviews</h3>
            <div style="display: flex; flex-direction: column; gap: 16px;">
                <!-- Static mock reviews for now -->
                <div class="card">
                    <div style="display: flex; gap: 16px;">
                        <div style="width: 48px; height: 48px; border-radius: 50%; background: var(--primary-light); color: var(--primary); font-weight: 700; font-size: 20px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">I</div>
                        <div style="flex: 1;">
                            <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                                <div style="font-weight: 600; font-size: 16px;">Infosys <span style="font-weight: 400; font-size: 14px; color: var(--text-muted);">— Project Review</span></div>
                                <div class="text-muted" style="font-size: 13px;">2 days ago</div>
                            </div>
                            <div style="color: #F59E0B; font-size: 14px; margin-bottom: 12px;"><i class="fa-solid fa-star"></i><i class="fa-solid fa-star"></i><i class="fa-solid fa-star"></i><i class="fa-solid fa-star"></i><i class="fa-solid fa-star"></i></div>
                            <p style="color: var(--text-body); margin: 0; line-height: 1.6;">Excellent service and quick turnaround.</p>
                        </div>
                    </div>
                </div>
            </div>`;
        } else {
            // User Feedback Tab
            let userFeedbacks = [];
            try { userFeedbacks = await window.ApiClient.getUserFeedbacks(); } catch (e) { }

            const rows = userFeedbacks.length === 0
                ? '<div class="text-muted py-4 text-center">No internal feedback records found.</div>'
                : userFeedbacks.map(f => `
                <div class="card" style="margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
                        <div>
                            <div style="font-weight:600; font-size:16px;">${f.subject}</div>
                            <div style="font-size:12px; color:var(--text-muted);">From: User #${f.user_id}</div>
                        </div>
                        <div class="text-muted" style="font-size:12px;">${new Date(f.created_at || Date.now()).toLocaleDateString()}</div>
                    </div>
                    <p style="margin:0; font-size:14px; line-height:1.5;">${f.message}</p>
                </div>`).join('');

            mainContent.innerHTML = `
            <div class="page-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px;">
                <div>
                   <h1 style="margin-bottom: 4px;">System Feedback</h1>
                   <p class="text-muted">Internal suggestions and issue reports from employees.</p>
                </div>
                <button class="btn btn-primary" onclick="openNewUserFeedbackModal()"><i class="fa-solid fa-pen-nib"></i> Submit Feedback</button>
            </div>
            ${tabBar}
            <div style="display: flex; flex-direction: column; gap: 4px;">
                ${rows}
            </div>`;
        }
        window.renderFeedback = renderFeedback;
    }

    window.openNewUserFeedbackModal = () => {
        const html = `
            <div class="form-group">
                <label>Subject *</label>
                <input type="text" id="muf-subject" class="form-control" placeholder="E.g. Suggestion for Dashboard UI" required>
            </div>
            <div class="form-group">
                <label>Your Message *</label>
                <textarea id="muf-message" class="form-textarea" style="height:120px;" placeholder="Describe your feedback, suggestion or concern..." required></textarea>
            </div>
        `;
        createModal('modal-user-feedback', 'Submit Internal Feedback', html, async () => {
            const subject = document.getElementById('muf-subject').value;
            const message = document.getElementById('muf-message').value;
            if (!subject || !message) throw new Error("Subject and Message are required");

            await window.ApiClient.createUserFeedback({ subject, message });
            showToast('Feedback submitted to Admin!');
            if (document.querySelector('h1')?.innerText.includes('System Feedback')) renderFeedback('user');
        }, "Submit Feedback");
    };

    // ─── Projects (Native Backend Module) ─────────────────────────────────────────────
    async function renderProjects() {
        let projects = [];
        try {
            projects = await window.ApiClient.getProjects();
        } catch (e) {
            console.error('Projects fetch failed', e);
        }

        // Cache projects and current state for filtering
        window._projectsCache = projects;
        window._projectFilter = window._projectFilter || 'ALL';
        window._projectSearch = window._projectSearch || '';

        const statusBadge = (s) => ({
            'OPEN':        '<span class="badge badge-warning">Open</span>',
            'IN_PROGRESS': '<span class="badge badge-primary">In Progress</span>',
            'RESOLVED':    '<span class="badge badge-success">Resolved</span>',
            'BLOCKED':     '<span class="badge badge-danger">Blocked</span>',
            'CANCELLED':   '<span class="badge badge-secondary">Cancelled</span>',
        }[s] || `<span class="badge badge-primary">${s}</span>`);

        const pmanagerIcon = (pm_name) => pm_name ? `
            <div style="display:flex; flex-direction:column; gap:2px;">
                <div style="display:flex; align-items:center; gap:8px; color:var(--text-main); font-weight:500;">
                    <i class="bi bi-person text-muted" style="font-size: 1rem;"></i> 
                    <span>${pm_name}</span>
                </div>
            </div>` : '<span class="text-muted">—</span>';

        const formatBudget = (btn) => btn ? `₹${(btn / 100000).toFixed(0)}L` : '—';

        const formatDateRange = (p) => {
            if (!p.start_date && !p.end_date) return '<span class="text-muted">TBD</span>';
            const start = p.start_date ? new Date(p.start_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'TBD';
            const end = p.end_date ? new Date(p.end_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'TBD';
            return `<div class="text-muted" style="font-size:0.85rem;"><i class="bi bi-calendar3 me-1"></i> ${start} — ${end}</div>`;
        };

        const renderTableRows = (filtered) => {
            return filtered.length ? filtered.map(p => {
                const prog = p.progress_percentage || 0;
                return `
                <tr style="vertical-align: middle;">
                    <td style="font-weight:600; color:var(--text-main); padding: 20px 24px;">${p.name}</td>
                    <td class="text-muted" style="padding: 20px 24px;">${p.client_name || 'Client #' + p.client_id}</td>
                    <td style="padding: 20px 24px;">${pmanagerIcon(p.pm_name)}</td>
                    <td style="padding: 20px 24px;">${formatDateRange(p)}</td>
                    <td style="padding: 20px 24px;">${statusBadge(p.status)}</td>
                    <td style="font-weight:600; color:var(--text-main); padding: 20px 24px;">${formatBudget(p.budget)}</td>
                    <td style="width: 180px; padding: 20px 24px;">
                        <div style="display:flex; align-items:center; gap:12px;">
                            <div style="flex-grow:1; height:6px; background:var(--bg-app); border-radius:10px; overflow:hidden;">
                                <div style="width:${prog}%; height:100%; background:var(--primary); border-radius:10px;"></div>
                            </div>
                            <span style="font-size:0.8rem; font-weight:600; color:var(--text-3); min-width:32px;">${prog.toFixed(0)}%</span>
                        </div>
                    </td>
                </tr>`;
            }).join('') : `<tr><td colspan="7" style="text-align:center;padding:60px;color:var(--text-muted); font-size: 0.9rem;">No projects matching the criteria.</td></tr>`;
        };

        const applyFilters = () => {
            let filtered = window._projectsCache;
            if (window._projectFilter !== 'ALL') {
                filtered = filtered.filter(p => p.status === window._projectFilter);
            }
            if (window._projectSearch) {
                const s = window._projectSearch.toLowerCase();
                filtered = filtered.filter(p =>
                    p.name.toLowerCase().includes(s) ||
                    (p.client_name && p.client_name.toLowerCase().includes(s)) ||
                    (p.pm_name && p.pm_name.toLowerCase().includes(s))
                );
            }
            const tbody = mainContent.querySelector('tbody');
            if (tbody) tbody.innerHTML = renderTableRows(filtered);
        };

        mainContent.innerHTML = `
        <div class="projects-container">
            <div class="d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h2 class="page-section-title">Projects</h2>
                    <p class="text-muted small mb-0">Overview of all delivery projects.</p>
                </div>
                <button class="btn btn-primary" onclick="window.alert('Create Project functionality coming soon')" style="padding: 12px 24px; font-weight: 600; border-radius: 10px; display:flex; align-items:center; gap:8px;">
                    <i class="bi bi-plus-lg" style="font-size:1.1rem;"></i> Create Project
                </button>
            </div>
            
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 24px; gap: 16px;">
                <div style="display:flex; gap:8px; flex-wrap: wrap;">
                    ${['ALL', 'OPEN', 'IN_PROGRESS', 'RESOLVED', 'BLOCKED'].map(f => {
            const labels = { ALL: 'All', OPEN: 'Open', IN_PROGRESS: 'In Progress', RESOLVED: 'Resolved', BLOCKED: 'Blocked' };
            const active = window._projectFilter === f;
            return `<button class="btn ${active ? 'btn-primary' : 'btn-light'}" 
                                   onclick="window._projectFilter='${f}'; renderProjects();"
                                   style="border-radius:24px; padding: 6px 20px; font-size:0.9rem; font-weight:${active ? '600' : '500'}; 
                                          ${!active ? 'background:var(--bg-app); border:none; color:var(--text-main);' : ''}">${labels[f]}</button>`;
        }).join('')}
                </div>
            </div>

            <div class="card" style="padding:0; border-radius:12px; overflow:hidden;">
                <div class="table-container">
                    <table class="table" style="margin-bottom:0;">
                        <thead>
                            <tr>
                                <th>PROJECT</th>
                                <th>CLIENT</th>
                                <th>PM</th>
                                <th>TIMELINE</th>
                                <th>STATUS</th>
                                <th>BUDGET</th>
                                <th>PROGRESS</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${renderTableRows(projects)}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>`;

        // Initial filter application in case filter was already set
        if (window._projectFilter !== 'ALL' || window._projectSearch) applyFilters();
    }

    // ─── HR & Payroll Modules ─────────────────────────────────────────────
    async function renderEmployees() {
        let employees = [];
        try { employees = await window.ApiClient.getEmployees(); } catch (e) { console.warn('Employees fetch failed', e); }

        const formatCurrency = (amount) => amount ? `₹${amount.toLocaleString()}` : '—';

        const rows = employees.length ? employees.map(e => `
            <tr style="vertical-align: middle;">
                <td style="font-weight:600; color:var(--text-muted); padding: 20px 24px;">EMP00${e.id}</td>
                <td style="font-weight:600; color:var(--text); padding: 20px 24px;">${e.name || e.email || '—'}</td>
                <td style="padding: 20px 24px;"><span class="badge badge-purple-light">${e.department || 'Staff'}</span></td>
                <td style="padding: 20px 24px;">${formatCurrency(e.base_salary)}</td>
                <td style="padding: 20px 24px;">${formatCurrency(e.target)}</td>
                <td class="text-muted" style="padding: 20px 24px;">${e.joining_date ? new Date(e.joining_date).toLocaleDateString() : '—'}</td>
                <td style="padding: 20px 24px; color:var(--text-muted);"><i class="bi bi-key" style="cursor:pointer;" title="Reset Password"></i></td>
            </tr>`).join('') :
            `<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-muted);">No employees found.</td></tr>`;

        mainContent.innerHTML = `
        <div class="d-flex justify-content-between align-items-center mb-4">
            <div>
                <h2 class="page-section-title">Employees</h2>
                <p class="text-muted small mb-0">Manage staff details, targets, and salaries.</p>
            </div>
        </div>
        
        <div class="card" style="padding:0; border:1px solid var(--border); border-radius:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.02);">
            <div class="table-container">
                <table class="table" style="margin-bottom:0;">
                    <thead style="background:var(--bg-surface);">
                        <tr>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">CODE</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">NAME</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">DEPARTMENT</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">BASE SALARY</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">TARGET</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">JOINED</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">ACTIONS</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
    }

    async function renderSalary() {
        let employees = [];
        try { employees = await window.ApiClient.getEmployees(); } catch (e) { console.warn('Employees fetch failed', e); }

        const formatCurrency = (amount) => amount ? `₹${amount.toLocaleString()}` : '0';

        window.openSalaryModal = (id, name, base) => {
            const m = document.getElementById('salaryModal');
            if (!m) {
                const html = `
                <div class="modal fade" id="salaryModal" tabindex="-1">
                    <div class="modal-dialog modal-dialog-centered">
                        <div class="modal-content" style="border-radius:16px; border:none; box-shadow:0 10px 40px rgba(0,0,0,0.1);">
                            <div class="modal-header" style="border-bottom:1px solid var(--border); padding:20px 24px;">
                                <h5 class="modal-title fw-bold">Generate Salary Slip</h5>
                                <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
                            </div>
                            <div class="modal-body" style="padding:24px;">
                                <form id="salaryForm">
                                    <input type="hidden" id="sal-emp-id">
                                    <div class="mb-3">
                                        <label class="form-label text-muted small fw-semibold">Employee</label>
                                        <input type="text" id="sal-emp-name" class="form-control bg-light" readonly>
                                    </div>
                                    <div class="row mb-3">
                                        <div class="col-6">
                                            <label class="form-label text-muted small fw-semibold">Month</label>
                                            <input type="month" id="sal-month" class="form-control" required>
                                        </div>
                                        <div class="col-6">
                                            <label class="form-label text-muted small fw-semibold">Base Salary</label>
                                            <input type="number" id="sal-base" class="form-control bg-light" readonly>
                                        </div>
                                    </div>
                                    <div class="row mb-3">
                                        <div class="col-6">
                                            <label class="form-label text-muted small fw-semibold">Paid Leaves</label>
                                            <input type="number" id="sal-paid" class="form-control" value="0" min="0">
                                        </div>
                                        <div class="col-6">
                                            <label class="form-label text-muted small fw-semibold">Unpaid Leaves</label>
                                            <input type="number" id="sal-unpaid" class="form-control" value="0" min="0">
                                        </div>
                                    </div>
                                    <div class="mb-4">
                                        <label class="form-label text-muted small fw-semibold">Deductions (₹)</label>
                                        <input type="number" id="sal-deduction" class="form-control" value="0" min="0">
                                    </div>
                                    <button type="submit" class="btn btn-primary w-100 py-2 fw-semibold" style="border-radius:10px;">Generate Slip</button>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>`;
                document.body.insertAdjacentHTML('beforeend', html);

                document.getElementById('salaryForm').addEventListener('submit', async (e) => {
                    e.preventDefault();
                    try {
                        await window.ApiClient.generateSalary({
                            employee_id: document.getElementById('sal-emp-id').value,
                            month: document.getElementById('sal-month').value,
                            paid_leaves: parseInt(document.getElementById('sal-paid').value),
                            unpaid_leaves: parseInt(document.getElementById('sal-unpaid').value),
                            deduction_amount: parseFloat(document.getElementById('sal-deduction').value)
                        });
                        showToast('Salary slip generated successfully!');
                        bootstrap.Modal.getInstance(document.getElementById('salaryModal')).hide();
                    } catch (err) {
                        showToast('Failed to generate slip', 'error');
                    }
                });
            }
            document.getElementById('sal-emp-id').value = id;
            document.getElementById('sal-emp-name').value = name;
            document.getElementById('sal-base').value = base;
            const today = new Date();
            document.getElementById('sal-month').value = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
            new bootstrap.Modal(document.getElementById('salaryModal')).show();
        };

        const rows = employees.length ? employees.map(e => {
            const name = e.name || e.email || '—';
            return `
            <tr style="vertical-align: middle;">
                <td style="font-weight:600; color:var(--text); padding: 20px 24px;">
                    <div class="d-flex align-items-center gap-3">
                        <div class="rounded-circle bg-primary-subtle text-primary d-flex align-items-center justify-content-center fw-bold text-uppercase" style="width:40px;height:40px;">
                            ${name.substring(0, 2)}
                        </div>
                        <div>
                            <div class="mb-1">${name}</div>
                            <div class="text-muted small fw-normal">EMP00${e.id} &middot; ${e.department || 'Staff'}</div>
                        </div>
                    </div>
                </td>
                <td style="padding: 20px 24px;">
                    <span class="badge" style="background:var(--primary-soft); color:var(--primary); border-radius:6px; padding:6px 10px;">${e.role.replace(/_/g, ' ')}</span>
                </td>
                <td style="padding: 20px 24px; font-weight:600;">${formatCurrency(e.base_salary)}</td>
                <td style="padding: 20px 24px;">
                    <div class="d-flex align-items-center gap-1">
                        <span class="badge bg-success" title="Paid Leaves Taken">0 P</span>
                        <span class="badge bg-danger" title="Unpaid Leaves Taken">0 U</span>
                    </div>
                </td>
                <td style="padding: 20px 24px; text-align:right;">
                    <button class="btn btn-sm btn-light border fw-semibold" onclick="openSalaryModal('${e.id}', '${name.replace(/'/g, "\\'")}', ${e.base_salary})" style="border-radius:8px;">
                        <i class="bi bi-file-earmark-text text-primary me-1"></i> Generate Slip
                    </button>
                </td>
            </tr>`;
        }).join('') : `<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--text-muted);">No employees found.</td></tr>`;

        mainContent.innerHTML = `
        <div class="page-header" style="margin-bottom:24px; display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
                <h1 style="margin-bottom:8px; font-weight:700; font-size:2rem; letter-spacing:-0.5px;">Salary & Leaves</h1>
                <p class="text-muted m-0">Track employee compensation and generate payroll slips.</p>
            </div>
            <button class="btn btn-primary" onclick="window.alert('Mass Run Payroll Pending')" style="padding: 10px 20px; font-weight: 600; border-radius: 8px;">
                <i class="bi bi-wallet2 me-2"></i> Run Payroll
            </button>
        </div>
        
        <div class="card" style="padding:0; border:1px solid var(--border); border-radius:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.02);">
            <div class="table-container">
                <table class="table" style="margin-bottom:0;">
                    <thead style="background:var(--bg-surface);">
                        <tr>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">EMPLOYEE</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">ROLE</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">BASE SALARY</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border);">LEAVES (THIS MONTH)</th>
                            <th style="color:var(--text-3); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid var(--border); text-align:right;">ACTIONS</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
    }

    async function renderIncentives() {
        let incentives = [];
        try { incentives = await window.ApiClient.getIncentives(); } catch (e) { console.warn('Incentives fetch failed', e); }

        const formatCurrency = (amount) => amount ? `₹${amount.toLocaleString()}` : '0';
        const getStatusBadge = (s) => ({
            'APPROVED': '<span class="badge badge-green-light">Approved</span>',
            'PENDING': '<span class="badge badge-yellow-light">Pending</span>'
        }[s] || '<span class="badge badge-purple-light">N/A</span>');

        const rows = incentives.length ? incentives.map(i => `
            <tr style="vertical-align: middle;">
                <td style="font-weight:600; color:var(--text); padding: 20px 24px;">Employee #${i.employee_id}</td>
                <td style="padding: 20px 24px;"><span class="badge badge-purple-light">Sales</span></td>
                <td style="padding: 20px 24px; color:var(--text-muted);">${i.leads_converted || 0}</td>
                <td style="padding: 20px 24px; color:var(--text-muted);">${i.rate || '—'}</td>
                <td style="font-weight:600; color:var(--green); padding: 20px 24px;">${formatCurrency(i.amount)}</td>
                <td style="padding: 20px 24px;">${getStatusBadge(i.status)}</td>
            </tr>`).join('') :
            `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-muted);">No incentives recorded yet.</td></tr>`;

        // Dummy stats based on screenshot
        const totalEarned = formatCurrency(Math.floor(Math.random() * 50000 + 10000));
        const avgConv = Math.floor(Math.random() * 30 + 15);

        mainContent.innerHTML = `
        <div class="page-header" style="margin-bottom:24px; display:flex; justify-content:space-between; align-items:flex-start;">
            <div>
                <h1 style="margin-bottom:8px; font-weight:700; font-size:2rem; letter-spacing:-0.5px;">Incentives</h1>
                <p class="text-muted m-0">Performance-based bonus tracking.</p>
            </div>
            <button class="btn btn-primary" onclick="window.alert('Add Incentive Modal Pending')" style="padding: 10px 20px; font-weight: 600; border-radius: 8px;">
                <i class="bi bi-plus-lg me-2"></i> Add New
            </button>
        </div>
        
        <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap:24px; margin-bottom: 24px;">
            <div class="card" style="display:flex; flex-direction:row; align-items:center; gap:16px; padding:24px; border-radius:12px; border:1px solid #f1f5f9; box-shadow:0 4px 6px -1px rgba(0,0,0,0.02);">
                <div style="width:48px; height:48px; border-radius:12px; background:rgba(34,197,94,0.1); color:#22c55e; display:flex; align-items:center; justify-content:center; font-size:1.5rem;">
                    <i class="bi bi-award"></i>
                </div>
                <div>
                    <div style="font-size:0.75rem; font-weight:600; color:var(--text-muted); letter-spacing:0.5px; margin-bottom:4px;">TOTAL EARNED (MONTH)</div>
                    <div style="font-size:1.5rem; font-weight:700; color:var(--text);">${totalEarned}</div>
                </div>
            </div>
            <div class="card" style="display:flex; flex-direction:row; align-items:center; gap:16px; padding:24px; border-radius:12px; border:1px solid #f1f5f9; box-shadow:0 4px 6px -1px rgba(0,0,0,0.02);">
                <div style="width:48px; height:48px; border-radius:12px; background:rgba(99,102,241,0.1); color:#6366f1; display:flex; align-items:center; justify-content:center; font-size:1.5rem;">
                    <i class="bi bi-graph-up-arrow"></i>
                </div>
                <div>
                    <div style="font-size:0.75rem; font-weight:600; color:var(--text-muted); letter-spacing:0.5px; margin-bottom:4px;">TOP PERFORMER</div>
                    <div style="font-size:1.2rem; font-weight:700; color:var(--text);">Staff Leader</div>
                </div>
            </div>
            <div class="card" style="display:flex; flex-direction:row; align-items:center; gap:16px; padding:24px; border-radius:12px; border:1px solid #f1f5f9; box-shadow:0 4px 6px -1px rgba(0,0,0,0.02);">
                <div style="width:48px; height:48px; border-radius:12px; background:rgba(234,179,8,0.1); color:#eab308; display:flex; align-items:center; justify-content:center; font-size:1.5rem;">
                    <i class="bi bi-bullseye"></i>
                </div>
                <div>
                    <div style="font-size:0.75rem; font-weight:600; color:var(--text-muted); letter-spacing:0.5px; margin-bottom:4px;">AVG CONVERSION RATE</div>
                    <div style="font-size:1.5rem; font-weight:700; color:var(--text);">${avgConv}%</div>
                </div>
            </div>
        </div>

        <div class="card" style="padding:0; border:1px solid var(--border); border-radius:12px; box-shadow:0 4px 6px -1px rgba(0,0,0,0.02);">
            <div class="table-container">
                <table class="table" style="margin-bottom:0;">
                    <thead style="background:var(--bg-surface);">
                        <tr>
                            <th style="color:var(--text-muted); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid #f1f5f9;">EMPLOYEE</th>
                            <th style="color:var(--text-muted); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid #f1f5f9;">ROLE</th>
                            <th style="color:var(--text-muted); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid #f1f5f9;">CONVERTED</th>
                            <th style="color:var(--text-muted); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid #f1f5f9;">RATE</th>
                            <th style="color:var(--text-muted); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid #f1f5f9;">EARNED</th>
                            <th style="color:var(--text-muted); font-size:0.75rem; padding:16px 24px; border-bottom:1px solid #f1f5f9;">STATUS</th>
                        </tr>
                    </thead>
                    <tbody>${rows}</tbody>
                </table>
            </div>
        </div>`;
    }

    // ─── Meetings ─────────────────────────────────────────────
    async function renderMeetings() {
        let clients = [], allMeetings = [];
        try { clients = await window.ApiClient.getClients(); } catch (e) { }
        for (const c of clients.slice(0, 20)) {
            try {
                const ms = await window.ApiClient.getClientMeetings(c.id);
                (ms || []).forEach(m => allMeetings.push({ ...m, client_name: c.name }));
            } catch (e) { }
        }
        allMeetings.sort((a, b) => new Date(b.date || 0) - new Date(a.date || 0));
        const statusBadgeMtg = s => ({
            scheduled: '<span class="badge badge-purple-light">Scheduled</span>',
            completed: '<span class="badge badge-green-light">Completed</span>',
            cancelled: '<span class="badge badge-red-light">Cancelled</span>'
        }[(s || '').toLowerCase()] || `<span class="badge">${s || '—'}</span>`);
        const rows = allMeetings.length ? allMeetings.map(m => `
            <tr>
                <td style="font-weight:500;">${m.client_name}</td>
                <td>${m.title || '—'}</td>
                <td>${m.date ? new Date(m.date).toLocaleDateString() : '—'}</td>
                <td>${m.date ? new Date(m.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</td>
                <td>${statusBadgeMtg(m.status)}</td>
                <td class="text-muted" style="max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${m.content || '—'}</td>
            </tr>`).join('') :
            `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-muted);">No meetings found.</td></tr>`;
        mainContent.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div><h1>Meetings</h1><p class="text-muted">All client meeting summaries.</p></div>
            <button class="btn btn-primary" onclick="openNewMeetingModal()"><i class="fa-solid fa-plus"></i> New Meeting</button>
        </div>
        <div class="card" style="padding:0;"><div class="table-container"><table class="table">
            <thead><tr><th>CLIENT</th><th>TITLE</th><th>DATE</th><th>TIME</th><th>STATUS</th><th>NOTES</th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div></div>`;
    }

    // ─── Issues ───────────────────────────────────────────────
    async function renderIssues() {
        let issues = [];
        try { issues = await window.ApiClient.getIssues(); } catch (e) { console.warn('Issues fetch failed', e); }
        const sevBadge = s => ({
            HIGH: '<span class="badge badge-red-light">High</span>',
            MEDIUM: '<span class="badge badge-yellow-light">Medium</span>',
            LOW: '<span class="badge badge-green-light">Low</span>'
        })[(s || '').toUpperCase()] || `<span class="badge">${s || '—'}</span>`;
        const statusBadge = s => ({
            PENDING: '<span class="badge badge-yellow-light">Pending</span>',
            RESOLVED: '<span class="badge badge-green-light">Resolved</span>',
            COMPLETED: '<span class="badge badge-primary">Completed</span>',
            CANCEL: '<span class="badge badge-red-light">Cancelled</span>'
        })[(s || '').toUpperCase()] || `<span class="badge">${s || '—'}</span>`;
        const openCount = issues.filter(i => (i.status || '').toUpperCase() === 'PENDING').length;
        const rows = issues.length ? issues.map(i => `
            <tr>
                <td style="font-weight:500;">${i.title || '—'}</td>
                <td>Client #${i.client_id || '—'}</td>
                <td>${sevBadge(i.severity)}</td>
                <td>${statusBadge(i.status)}</td>
                <td>${i.pm_id ? `PM #${i.pm_id}` : '—'}</td>
                <td>${i.created_at ? new Date(i.created_at).toLocaleDateString() : '—'}</td>
                <td>
                    <select class="form-control" style="height:28px;font-size:11px;width:120px;padding:2px 5px;" onchange="promptIssueStatusUpdate('${i.id}', this.value, '${i.status}')">
                        <option value="PENDING" ${i.status === 'PENDING' ? 'selected' : ''}>Pending</option>
                        <option value="RESOLVED" ${i.status === 'RESOLVED' ? 'selected' : ''}>Resolved</option>
                        <option value="CANCEL" ${i.status === 'CANCEL' ? 'selected' : ''}>Cancel</option>
                    </select>
                </td>
            </tr>`).join('') :
            `<tr><td colspan="7" style="text-align:center;padding:40px;color:var(--text-muted);">No issues found.</td></tr>`;
        mainContent.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div><h1>Issues</h1><p class="text-muted">${openCount} open · ${issues.length} total</p></div>
            <button class="btn btn-primary" onclick="openNewIssueModal()"><i class="fa-solid fa-plus"></i> New Issue</button>
        </div>
        <div class="card" style="padding:0;"><div class="table-container"><table class="table">
            <thead><tr><th>TITLE</th><th>CLIENT</th><th>SEVERITY</th><th>STATUS</th><th>ASSIGNED PM</th><th>REPORTED</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div></div>`;
        window.promptIssueStatusUpdate = async (id, newStatus, oldStatus) => {
            if (newStatus === oldStatus) return;

            const remarks = prompt(`Please enter mandatory remarks for changing status to ${newStatus}:`);
            if (remarks === null) { // Cancelled prompt
                renderIssues();
                return;
            }

            if (!remarks.trim()) {
                showToast('Remarks are mandatory for status updates', 'error');
                renderIssues();
                return;
            }

            try {
                await window.ApiClient.patchIssue(id, { status: newStatus, remarks: remarks });
                showToast(`Issue status updated to ${newStatus}`);
                renderIssues();
            } catch (e) {
                showToast(e.message || 'Could not update issue', 'error');
                renderIssues();
            }
        };
    }

    // ─── HRM (Tabbed: Employees / Salary / Incentives) ──────────
    async function renderHRM(activeTab = 'employees') {
        const tabBar = `
            <div class="tab-bar" style="margin-bottom:0;">
                <button class="tab-btn ${activeTab === 'employees' ? 'active' : ''}" onclick="renderHRM('employees')">Employees</button>
                <button class="tab-btn ${activeTab === 'salary' ? 'active' : ''}" onclick="renderHRM('salary')">Salary Records</button>
                <button class="tab-btn ${activeTab === 'incentives' ? 'active' : ''}" onclick="renderHRM('incentives')">Incentives</button>
            </div>`;

        if (activeTab === 'employees') {
            let employees = [];
            try { employees = await window.ApiClient.getEmployees(); } catch (e) { }
            const roleColors = { ADMIN: 'badge-red-light', SALES: 'badge-green-light', TELESALES: 'badge-purple-light', PROJECT_MANAGER: 'badge-yellow-light', PROJECT_MANAGER_AND_SALES: 'badge-purple-light' };
            const rows = employees.length ? employees.map(e => `
                <tr>
                    <td>
                        <div style="display:flex;align-items:center;gap:12px;">
                            <div style="width:36px;height:36px;border-radius:50%;background:var(--primary-light);color:var(--primary);font-weight:700;display:flex;align-items:center;justify-content:center;">${(e.name || e.email || '?')[0].toUpperCase()}</div>
                            <div><div style="font-weight:500;">${e.name || e.email || '—'}</div><div style="font-size:12px;color:var(--text-muted);">${e.email || '—'}</div></div>
                        </div>
                    </td>
                    <td>${e.phone || '—'}</td>
                    <td><span class="badge ${roleColors[e.role] || 'badge-purple-light'}">${(e.role || '').replace(/_/g, ' ')}</span></td>
                    <td>${e.department || '—'}</td>
                    <td>${e.base_salary ? `Rs. ${e.base_salary.toLocaleString()}` : '—'}</td>
                    <td>${e.active_clients_count ?? '—'}</td>
                </tr>`).join('') :
                `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-muted);">No employees found. Create Employee records in the backend.</td></tr>`;
            mainContent.innerHTML = `
            <div class="page-header"><div><h1>HR &amp; Payroll</h1><p class="text-muted">${employees.length} employees on record.</p></div></div>
            <div class="card" style="padding:0 0 0 0;">
                ${tabBar}
                <div class="table-container"><table class="table">
                    <thead><tr><th>EMPLOYEE</th><th>PHONE</th><th>ROLE</th><th>DEPARTMENT</th><th>BASE SALARY</th><th>ACTIVE CLIENTS</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table></div>
            </div>`;
            window.renderHRM = renderHRM;

        } else if (activeTab === 'salary') {
            let employees = [], allSlips = [];
            try { employees = await window.ApiClient.getEmployees(); } catch (e) { }
            for (const emp of employees.slice(0, 30)) {
                try {
                    const slips = await window.ApiClient.getSalaryRecords(emp.id);
                    (slips || []).forEach(s => allSlips.push({ ...s, emp_name: emp.name || emp.email }));
                } catch (e) { }
            }
            allSlips.sort((a, b) => (b.period || '').localeCompare(a.period || ''));
            const rows = allSlips.length ? allSlips.map(s => `
                <tr>
                    <td style="font-weight:500;">${s.emp_name || '—'}</td>
                    <td>${s.period || '—'}</td>
                    <td>Rs. ${(s.basic_salary || 0).toLocaleString()}</td>
                    <td>Rs. ${(s.total_deductions || 0).toLocaleString()}</td>
                    <td style="font-weight:600;color:var(--primary);">Rs. ${(s.net_salary || 0).toLocaleString()}</td>
                    <td><span class="badge ${s.status === 'PAID' ? 'badge-green-light' : 'badge-yellow-light'}">${s.status || 'GENERATED'}</span></td>
                </tr>`).join('') :
                `<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-muted);">No salary records yet. Generate salary slips for employees.</td></tr>`;
            mainContent.innerHTML = `
            <div class="page-header"><div><h1>Salary Records</h1><p class="text-muted">${allSlips.length} slips on record.</p></div></div>
            <div class="card" style="padding:0;">
                ${tabBar}
                <div class="table-container"><table class="table">
                    <thead><tr><th>EMPLOYEE</th><th>PERIOD</th><th>BASIC</th><th>DEDUCTIONS</th><th>NET SALARY</th><th>STATUS</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table></div>
            </div>`;
            window.renderHRM = renderHRM;

        } else if (activeTab === 'incentives') {
            let slabs = [];
            try { slabs = await window.ApiClient.getIncentiveSlabs(); } catch (e) { }
            const rows = slabs.length ? slabs.map(s => `
                <tr>
                    <td>${s.min_percentage}%</td>
                    <td>${s.max_percentage != null ? s.max_percentage + '%' : 'No limit'}</td>
                    <td>Rs. ${s.amount_per_unit} / unit</td>
                    <td>${s.description || '—'}</td>
                </tr>`).join('') :
                `<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-muted);">No incentive slabs defined. Admin can create slabs in Incentive Targets.</td></tr>`;
            mainContent.innerHTML = `
            <div class="page-header"><div><h1>Incentive Slabs</h1><p class="text-muted">Performance-based bonus tiers.</p></div></div>
            <div class="card" style="padding:0;">
                ${tabBar}
                <div class="table-container"><table class="table">
                    <thead><tr><th>MIN ACHIEVEMENT</th><th>MAX ACHIEVEMENT</th><th>PAYOUT RATE</th><th>DESCRIPTION</th></tr></thead>
                    <tbody>${rows}</tbody>
                </table></div>
            </div>`;
            window.renderHRM = renderHRM;
        }
    }

    // ─── Admin (Users & Roles) ────────────────────────────────
    async function renderAdmin() {
        let users = [];
        try { users = await window.ApiClient.getEmployees(); } catch (e) { console.warn('Admin fetch failed', e); }
        const roleOptions = ['ADMIN', 'SALES', 'TELESALES', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES'];
        const rows = users.length ? users.map(u => `
            <tr>
                <td>
                    <div style="display:flex;align-items:center;gap:10px;">
                        <div style="width:32px;height:32px;border-radius:50%;background:var(--primary-light);color:var(--primary);font-weight:700;display:flex;align-items:center;justify-content:center;">${(u.name || u.email || '?')[0].toUpperCase()}</div>
                        ${u.name || u.email || '—'}
                    </div>
                </td>
                <td>${u.email || '—'}</td>
                <td>
                    <select class="form-control" style="height:32px;font-size:13px;" onchange="changeUserRole('${u.user_id || u.id}', this.value)">
                        ${roleOptions.map(r => `<option value="${r}" ${r === u.role ? 'selected' : ''}>${r}</option>`).join('')}
                    </select>
                </td>
                <td><span class="badge ${u.is_active ? 'badge-green-light' : 'badge-red-light'}">${u.is_active ? 'Active' : 'Inactive'}</span></td>
            </tr>`).join('') :
            `<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-muted);">No users found.</td></tr>`;
        mainContent.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div><h1>Users & Roles</h1><p class="text-muted">Manage system access and role assignments.</p></div>
        </div>
        <div class="card" style="padding:0;"><div class="table-container"><table class="table">
            <thead><tr><th>USER</th><th>EMAIL</th><th>ROLE</th><th>STATUS</th></tr></thead>
            <tbody>${rows}</tbody>
        </table></div></div>`;
        window.changeUserRole = async (userId, role) => {
            try { await window.ApiClient.updateUserRole(userId, role); } catch (e) { alert('Could not update role.'); }
        };
    }

    // ─── Modals Implementation ──────────────────────────────────────
    function createModal(id, title, contentHtml, submitAction, submitLabel = "Save") {
        const existing = document.getElementById(id);
        if (existing) existing.remove();

        const overlay = document.createElement('div');
        overlay.id = id;
        overlay.className = 'modal-overlay';
        overlay.innerHTML = `
            <div class="modal-box">
                <div class="modal-header">
                    <h2>${title}</h2>
                    <button class="modal-close-btn" onclick="document.getElementById('${id}').remove()"><i class="fa-solid fa-xmark"></i></button>
                </div>
                <div class="modal-body">
                    ${contentHtml}
                </div>
                <div class="modal-footer">
                    <button class="btn btn-ghost" onclick="document.getElementById('${id}').remove()">Cancel</button>
                    <button class="btn btn-primary" id="${id}-submit">${submitLabel}</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);

        document.getElementById(`${id}-submit`).addEventListener('click', async (e) => {
            const btn = e.target;
            const originalText = btn.innerHTML;
            btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Saving...';
            btn.disabled = true;
            try {
                await submitAction();
                overlay.remove();
            } catch (err) {
                console.error(err);
                alert("Error: " + (err.message || 'Action failed'));
            } finally {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }
        });
    }

    // Modal: New Client
    window.openNewClientModal = () => {
        const html = `
            <div class="form-group"><label>Client Name *</label><input type="text" id="mc-name" class="form-control" required></div>
            <div class="form-group"><label>Email *</label><input type="email" id="mc-email" class="form-control" required></div>
            <div class="form-group"><label>Phone *</label><input type="text" id="mc-phone" class="form-control" minlength="10" required></div>
            <div class="form-group"><label>Organization</label><input type="text" id="mc-org" class="form-control"></div>
            <div class="form-group"><label>Address</label><textarea id="mc-addr" class="form-textarea"></textarea></div>
        `;
        createModal('modal-new-client', 'Add New Client', html, async () => {
            const data = {
                name: document.getElementById('mc-name').value,
                email: document.getElementById('mc-email').value,
                phone: document.getElementById('mc-phone').value,
                organization: document.getElementById('mc-org').value,
                address: document.getElementById('mc-addr').value
            };
            if (!data.name || !data.email || !data.phone) throw new Error("Name, Email, and Phone are required. Phone must be 10+ digits.");
            await window.ApiClient.createClient(data);
            showToast('Client created successfully');
            if (document.querySelector('h1').innerText.includes('Clients')) renderClients();
        });
    };

    // Modal: Log Visit
    window.openLogVisitModal = async () => {
        let shops = [];
        try { shops = await window.ApiClient.getShops(); } catch (e) { }

        const shopOptions = shops.map(s => `<option value="${s.id}">${s.name}</option>`).join('');
        const html = `
            <div class="form-group">
                <label>Select Shop *</label>
                <select id="mv-shop" class="form-control" required>
                    <option value="">-- Choose Shop --</option>
                    ${shopOptions}
                </select>
            </div>
            <div class="form-group">
                <label>Status</label>
                <select id="mv-status" class="form-control">
                    <option value="SATISFIED" selected>Satisfied</option>
                    <option value="ACCEPT">Accept</option>
                    <option value="DECLINE">Decline</option>
                    <option value="TAKE_TIME_TO_THINK">Take time to think</option>
                    <option value="OTHER">Other</option>
                </select>
            </div>
            <div class="form-group">
                <label>Visit Date</label>
                <input type="datetime-local" id="mv-date" class="form-control" value="${new Date().toISOString().slice(0, 16)}">
            </div>
            <div class="form-group">
                <label>Notes</label>
                <textarea id="mv-notes" class="form-textarea" placeholder="Outcome of the visit..."></textarea>
            </div>
            <div class="form-group" id="visit-photo-group">
                <label>Upload Photo (Optional)</label>
                <input type="file" id="mv-photo" class="form-control" accept="image/*">
            </div>
        `;
        createModal('modal-log-visit', 'Log Field Visit', html, async () => {
            const user = window.ApiClient.getCurrentUser();
            const isTelesales = user && user.role === 'TELESALES';

            const shopId = document.getElementById('mv-shop').value;
            if (!shopId) throw new Error("Please select a shop");

            const formData = new FormData();
            formData.append('shop_id', shopId);
            formData.append('status', document.getElementById('mv-status').value);
            formData.append('remarks', document.getElementById('mv-notes').value);

            const vDate = document.getElementById('mv-date').value;
            if (vDate) {
                formData.append('visit_date', new Date(vDate).toISOString());
            }

            const photoInput = document.getElementById('mv-photo');
            if (photoInput.files.length > 0) {
                formData.append('photo', photoInput.files[0]);
            }

            const token = window.ApiClient.getAccessToken();
            const res = await fetch(`${window.ApiClient.API_BASE_URL}/visits/`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail || 'Failed to log visit');
            }
            showToast('Visit logged successfully');
            if (document.querySelector('h1').innerText.includes('Visits')) renderVisits();
        }, "Log Visit");

        // Hide photo upload for telesales
        const user = window.ApiClient.getCurrentUser();
        if (user && user.role === 'TELESALES') {
            const photoGrp = document.getElementById('visit-photo-group');
            if (photoGrp) photoGrp.style.display = 'none';
        }
    };

    // Modal: New Meeting
    window.openNewMeetingModal = async (defaultClientId = '') => {
        let clients = [];
        try { clients = await window.ApiClient.getClients(); } catch (e) { }

        const clientOptions = clients.map(c => `<option value="${c.id}" ${c.id == defaultClientId ? 'selected' : ''}>${c.name}</option>`).join('');
        const html = `
            <div class="form-group">
                <label>Client *</label>
                <select id="mm-client" class="form-control" ${defaultClientId ? 'disabled' : ''} required>
                    <option value="">-- Select Client --</option>
                    ${clientOptions}
                </select>
            </div>
            <div class="form-group"><label>Title *</label><input type="text" id="mm-title" class="form-control" required></div>
            <div style="display:flex;gap:12px;">
                <div class="form-group" style="flex:1;"><label>Date *</label><input type="date" id="mm-date" class="form-control" required></div>
                <div class="form-group" style="flex:1;"><label>Time</label><input type="time" id="mm-time" class="form-control"></div>
            </div>
            <div class="form-group">
                <label>Summary Notes</label>
                <textarea id="mm-notes" class="form-textarea"></textarea>
            </div>
        `;
        createModal('modal-new-meeting', 'Schedule Meeting', html, async () => {
            const clientId = document.getElementById('mm-client').value;
            if (!clientId) throw new Error("Client is required");
            const d = document.getElementById('mm-date').value;
            const t = document.getElementById('mm-time').value;
            const datetimeStr = d ? (t ? `${d}T${t}:00Z` : `${d}T00:00:00Z`) : null;

            const data = {
                title: document.getElementById('mm-title').value,
                date: datetimeStr,
                status: "scheduled",
                content: document.getElementById('mm-notes').value
            };
            if (!data.title) throw new Error("Title is required");

            await window.ApiClient.createMeeting(clientId, data);
            showToast('Meeting scheduled successfully');
            if (document.querySelector('h1').innerText.includes('Meetings')) renderMeetings();
        });
    };

    // Modal: New Issue
    window.openNewIssueModal = async (defaultClientId = '') => {
        let clients = [];
        try { clients = await window.ApiClient.getClients(); } catch (e) { }

        const clientOptions = clients.map(c => `<option value="${c.id}" ${c.id == defaultClientId ? 'selected' : ''}>${c.name}</option>`).join('');
        const html = `
            <div class="form-group">
                <label>Client *</label>
                <select id="mi-client" class="form-control" ${defaultClientId ? 'disabled' : ''} required>
                    <option value="">-- Select Client --</option>
                    ${clientOptions}
                </select>
            </div>
            <div class="form-group"><label>Issue Title *</label><input type="text" id="mi-title" class="form-control" required></div>
            <div style="display:flex;gap:12px;">
                <div class="form-group" style="flex:1;">
                    <label>Severity</label>
                    <select id="mi-sev" class="form-control">
                        <option value="LOW">Low</option>
                        <option value="MEDIUM" selected>Medium</option>
                        <option value="HIGH">High</option>
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label>Description</label>
                <textarea id="mi-desc" class="form-textarea"></textarea>
            </div>
        `;
        createModal('modal-new-issue', 'Report Issue', html, async () => {
            const clientId = document.getElementById('mi-client').value;
            if (!clientId) throw new Error("Client is required");

            const data = {
                title: document.getElementById('mi-title').value,
                description: document.getElementById('mi-desc').value,
                severity: document.getElementById('mi-sev').value,
                status: "OPEN"
            };
            if (!data.title) throw new Error("Title is required");

            await window.ApiClient.createIssue(clientId, data);
            showToast('Issue created successfully');
            if (document.querySelector('h1').innerText.includes('Issues')) renderIssues();
        });
    };

    // Modal: New Shop
    window.openNewShopModal = async (defaultAreaId = '') => {
        let areas = [];
        try { areas = await window.ApiClient.getAreas(); } catch (e) { }

        const areaOptions = areas.map(a => `<option value="${a.id}" ${a.id == defaultAreaId ? 'selected' : ''}>${a.name}</option>`).join('');
        const html = `
            <div class="form-group"><label>Shop Name *</label><input type="text" id="ms-name" class="form-control" required></div>
            <div class="form-group"><label>Owner Name</label><input type="text" id="ms-owner" class="form-control"></div>
            <div class="form-group"><label>Phone</label><input type="text" id="ms-phone" class="form-control"></div>
            <div class="form-group">
                <label>Area *</label>
                <select id="ms-area" class="form-control" ${defaultAreaId ? 'disabled' : ''} required>
                    <option value="">-- Select Area --</option>
                    ${areaOptions}
                </select>
            </div>
            <div class="form-group"><label>Address</label><textarea id="ms-addr" class="form-textarea"></textarea></div>
        `;
        createModal('modal-new-shop', 'Add New Shop', html, async () => {
            const areaId = document.getElementById('ms-area').value || defaultAreaId;
            if (!areaId) throw new Error("Area is required");

            const data = {
                name: document.getElementById('ms-name').value,
                owner_name: document.getElementById('ms-owner').value,
                phone: document.getElementById('ms-phone').value,
                address: document.getElementById('ms-addr').value,
                status: "ACTIVE"
            };
            if (!data.name) throw new Error("Shop Name is required");

            await window.ApiClient.createShop(areaId, data);
            showToast('Shop created successfully');
            if (document.querySelector('.page-header h1')?.innerText.includes('Shops')) renderShops(); // hypothetical shop view if exists
        });
    };

    // Modal: New Area
    window.openNewAreaModal = async () => {
        const html = `
            <div class="form-group"><label>Area Name *</label><input type="text" id="ma-name" class="form-control" required></div>
            <div class="form-group"><label>City *</label><input type="text" id="ma-city" class="form-control" required></div>
            <div class="form-group"><label>State</label><input type="text" id="ma-state" class="form-control"></div>
            <div class="form-group"><label>Pincode</label><input type="text" id="ma-pin" class="form-control"></div>
        `;
        createModal('modal-new-area', 'Add New Area', html, async () => {
            const data = {
                name: document.getElementById('ma-name').value,
                city: document.getElementById('ma-city').value,
                state: document.getElementById('ma-state').value,
                pincode: document.getElementById('ma-pin').value
            };
            if (!data.name || !data.city) throw new Error("Area Name and City are required");

            await window.ApiClient.createArea(data);
            showToast('Area created successfully');
            if (document.querySelector('.page-header h1')?.innerText.includes('Areas')) renderAreas();
        });
    };

    // ─── Profile ──────────────────────────────────────────────────
    async function renderProfile() {
        const u = window.ApiClient.getCurrentUser();
        if (!u) {
            loadView('dashboard');
            return;
        }

        const roleName = u.role.replace(/_/g, ' ');
        const initials = u.name.slice(0, 2).toUpperCase();

        // Check if user has an associated employee record for ID card
        // For now, we'll assume admins and PMs can see their own if they have one
        const canViewIdCard = ['ADMIN', 'PROJECT_MANAGER', 'PROJECT_MANAGER_AND_SALES', 'SALES', 'TELESALES'].includes(u.role);

        // Referral code is for Sales/Telesales
        const hasReferralCode = ['SALES', 'TELESALES', 'PROJECT_MANAGER_AND_SALES'].includes(u.role);

        mainContent.innerHTML = `
            <div class="page-header">
                <div><h1>My Profile</h1><p class="text-muted">Manage your personal information and credentials.</p></div>
            </div>
            
            <div class="grid-2">
                <div class="card">
                    <div style="display:flex; flex-direction:column; align-items:center; padding: 20px 0;">
                        <div style="width:100px; height:100px; border-radius:50%; background:var(--primary-subtle); color:var(--primary); display:flex; align-items:center; justify-content:center; font-size:36px; font-weight:700; margin-bottom:16px;">
                            ${initials}
                        </div>
                        <h2 style="margin-bottom:4px;color:var(--heading-color);">${u.name}</h2>
                        <span class="badge badge-purple-light">${roleName}</span>
                    </div>
                    
                    <div style="margin-top:20px; border-top: 1px solid var(--border); padding-top:20px;">
                        <div class="form-group">
                            <label>Full Name</label>
                            <input type="text" class="form-control" value="${u.name}" readonly>
                        </div>
                        <div class="form-group">
                            <label>Email Address</label>
                            <input type="email" class="form-control" value="${u.email}" readonly>
                        </div>
                        
                        ${hasReferralCode && u.referral_code ? `
                            <div class="form-group">
                                <label>Your Referral Code</label>
                                <div style="display:flex; gap:8px;">
                                    <input type="text" class="form-control" value="${u.referral_code}" readonly style="font-family:monospace; font-weight:700; color:var(--primary);">
                                    <button class="btn btn-ghost" onclick="navigator.clipboard.writeText('${u.referral_code}'); showToast('Code copied!')">
                                        <i class="bi bi-copy"></i>
                                    </button>
                                </div>
                                <small class="text-muted">Share this code with clients to track your referrals.</small>
                            </div>
                        ` : ''}
                    </div>
                </div>
                
                <div class="card">
                    <h3>Employee Resources</h3>
                    <div style="margin-top:20px; display:flex; flex-direction:column; gap:12px;">
                        ${canViewIdCard ? `
                            <div class="d-flex align-items-center justify-content-between p-3 border rounded-3 bg-app" style="background:var(--bg-app); border-color:var(--border) !important;">
                                <div class="d-flex align-items-center gap-3">
                                    <div class="icon-box bg-primary-subtle text-primary" style="width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;">
                                        <i class="bi bi-person-badge"></i>
                                    </div>
                                    <div>
                                        <div class="fw-bold">Company ID Card</div>
                                        <div class="text-muted small">Digital identity & verification</div>
                                    </div>
                                </div>
                                <button class="btn btn-sm btn-primary" onclick="window.open('${window.ApiClient.API_BASE_URL}/idcards/view_own', '_blank')">
                                    View Digital ID
                                </button>
                            </div>
                        ` : ''}
                        
                        <div class="d-flex align-items-center justify-content-between p-3 border rounded-3">
                            <div class="d-flex align-items-center gap-3">
                                <div class="icon-box bg-success-subtle text-success" style="width:40px;height:40px;border-radius:10px;display:flex;align-items:center;justify-content:center;">
                                    <i class="bi bi-shield-lock"></i>
                                </div>
                                <div>
                                    <div class="fw-bold">Security Settings</div>
                                    <div class="text-muted small">Update your password</div>
                                </div>
                            </div>
                            <button class="btn btn-sm btn-outline-secondary">Configure</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    // ─── Reports & Analytics ──────────────────────────────────────
    async function renderReports() {
        let stats = null;
        try { stats = await window.ApiClient.getReportsDashboard(); } catch (e) { console.warn('Reports fetch failed', e); }

        const openIssues = stats?.open_issues_count ?? 0;
        const totalClients = stats?.total_clients ?? 0;
        const totalVisits = stats?.total_visits ?? 0;
        const totalShops = stats?.total_shops ?? 0;

        mainContent.innerHTML = `
        <div class="page-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:24px;">
            <div><h1>Reports & Analytics</h1><p class="text-muted">Comprehensive system overview and metrics.</p></div>
            <button class="btn btn-primary" onclick="window.print()"><i class="fa-solid fa-print"></i> Print Report</button>
        </div>
        
        <div class="grid-4" style="margin-bottom:24px;">
            <div class="stat-card card">
                <div class="stat-content-left">
                    <div class="stat-title">Total Clients</div>
                    <div class="stat-value">${totalClients}</div>
                    <div class="stat-trend trend-up"><i class="fa-solid fa-arrow-up"></i> Active Portfolio</div>
                </div>
                <div class="stat-icon-wrapper icon-purple"><i class="fa-solid fa-building"></i></div>
            </div>
            
            <div class="stat-card card">
                <div class="stat-content-left">
                    <div class="stat-title">Open Issues</div>
                    <div class="stat-value">${openIssues}</div>
                    <div class="stat-trend ${openIssues > 0 ? 'trend-down' : 'trend-up'}"><i class="fa-solid fa-triangle-exclamation"></i> Needs Attention</div>
                </div>
                <div class="stat-icon-wrapper icon-red"><i class="fa-solid fa-bug"></i></div>
            </div>
            
            <div class="stat-card card">
                <div class="stat-content-left">
                    <div class="stat-title">Field Visits</div>
                    <div class="stat-value">${totalVisits}</div>
                    <div class="stat-trend trend-up"><i class="fa-solid fa-arrow-up"></i> Total Tracked</div>
                </div>
                <div class="stat-icon-wrapper icon-teal"><i class="fa-solid fa-route"></i></div>
            </div>
            
            <div class="stat-card card">
                <div class="stat-content-left">
                    <div class="stat-title">Total Shops</div>
                    <div class="stat-value">${totalShops}</div>
                    <div class="stat-trend trend-up"><i class="fa-solid fa-arrow-up"></i> Market Coverage</div>
                </div>
                <div class="stat-icon-wrapper icon-yellow"><i class="fa-solid fa-store"></i></div>
            </div>
        </div>

        <div class="grid-2">
            <div class="card">
                <h3>System Health</h3>
                <div style="margin-top:20px;display:flex;flex-direction:column;gap:15px;">
                    <div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:14px;font-weight:500;">
                            <span>Client Onboarding</span><span>Good</span>
                        </div>
                        <div style="width:100%;height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
                            <div style="width:85%;height:100%;background:var(--primary);"></div>
                        </div>
                    </div>
                    <div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:14px;font-weight:500;">
                            <span>Issue Resolution</span><span>${openIssues > 0 ? 'Needs Improvement' : 'Excellent'}</span>
                        </div>
                        <div style="width:100%;height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
                            <div style="width:${openIssues > 0 ? '45%' : '100%'};height:100%;background:${openIssues > 0 ? 'var(--warning)' : 'var(--success)'};"></div>
                        </div>
                    </div>
                    <div>
                        <div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:14px;font-weight:500;">
                            <span>Field Activity</span><span>Active</span>
                        </div>
                        <div style="width:100%;height:8px;background:var(--border);border-radius:4px;overflow:hidden;">
                            <div style="width:70%;height:100%;background:var(--teal);"></div>
                        </div>
                    </div>
                </div>
            </div>
            
            <div class="card" style="display:flex;flex-direction:column;justify-content:center;align-items:center;min-height:300px;">
                <div style="text-align:center;color:var(--text-muted);">
                    <i class="fa-solid fa-chart-pie" style="font-size:48px;margin-bottom:16px;opacity:0.3;"></i>
                    <p>Detailed chart generation requires historical data.</p>
                </div>
            </div>
        </div>`;
        window.renderReports = renderReports;
    }



    async function renderBilling() {
        try {
            const bills = await window.ApiClient.getBills();
            const rows = bills.length === 0
                ? '<tr><td colspan="5" style="text-align:center;padding:40px;color:var(--text-muted);">No bills found.</td></tr>'
                : bills.map(b => `
                    <tr>
                        <td style="font-weight:600;">${b.invoice_number || 'PENDING'}</td>
                        <td>Shop #${b.shop_id}</td>
                        <td>Rs. ${b.amount.toLocaleString()}</td>
                        <td><span class="badge ${b.status === 'PAID' ? 'badge-green-light' : 'badge-yellow-light'}">${b.status}</span></td>
                        <td>${b.whatsapp_sent ? '<span class="badge badge-green-light"><i class="fa-brands fa-whatsapp"></i> Sent</span>' : '<span class="badge badge-red-light">Not Sent</span>'}</td>
                    </tr>`).join('');

            mainContent.innerHTML = `
                <div class="page-header">
                    <div><h1>Billing & Invoices</h1><p class="text-muted">Manage payments and shop auto-conversions.</p></div>
                    <button class="btn btn-primary" onclick="openNewBillModal()"><i class="fa-solid fa-file-invoice-dollar"></i> Generate New Bill</button>
                </div>
                <div class="card" style="padding:0;">
                    <div class="table-container">
                        <table class="table">
                            <thead><tr><th>INVOICE #</th><th>SHOP/CLIENT</th><th>AMOUNT</th><th>STATUS</th><th>WHATSAPP</th></tr></thead>
                            <tbody>${rows}</tbody>
                        </table>
                    </div>
                </div>
            `;
        } catch (e) {
            mainContent.innerHTML = '<div class="card text-danger">Failed to load billing records.</div>';
        }
    }

    window.openNewBillModal = async (shopId = null) => {
        let shops = [];
        try { shops = await window.ApiClient.getShops(); } catch (e) { }

        const shopOptions = shops.map(s => `<option value="${s.id}" ${s.id == shopId ? 'selected' : ''}>${s.name}</option>`).join('');
        const html = `
            <div class="form-group">
                <label>Select Shop *</label>
                <select id="mb-shop" class="form-control" ${shopId ? 'disabled' : ''} required>
                    <option value="">-- Choose Shop --</option>
                    ${shopOptions}
                </select>
                <small class="text-muted">Note: Shop will be automatically converted to Client after billing.</small>
            </div>
            <div class="form-group">
                <label>Amount (Rs.) *</label>
                <input type="number" id="mb-amount" class="form-control" placeholder="E.g. 5000" required>
            </div>
        `;
        createModal('modal-new-bill', 'Generate Bill & Convert Shop', html, async () => {
            const shopId = document.getElementById('mb-shop').value;
            const amount = document.getElementById('mb-amount').value;
            if (!shopId || !amount) throw new Error("All fields are required");

            await window.ApiClient.generateBill({ shop_id: parseInt(shopId), amount: parseFloat(amount) });
            showToast('Bill generated and WhatsApp invoice sent!');
            renderBilling();
        }, "Generate & Convert");
    };

    async function renderTimetable() {
        const today = new Date();
        const dateStr = today.toLocaleDateString('en-IN', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

        // Mock Data for Timetable (following Google Calendar inspiration)
        const mockEvents = [
            { id: 1, name: 'Morning Lead Follow-up', start: '09:00 AM', end: '10:30 AM', type: 'Call', loc: 'Office', recurrence: 'Daily', status: 'COMPLETED' },
            { id: 2, name: 'Client Meeting - HCL', start: '11:00 AM', end: '12:30 PM', type: 'Meeting', loc: 'Main Street Office', recurrence: 'None', status: 'UPCOMING' },
            { id: 3, name: 'Shop Visit - Metro Bazar', start: '02:00 PM', end: '04:00 PM', type: 'Field Visit', loc: 'Metro Area', recurrence: 'Weekly', status: 'UPCOMING' },
            { id: 4, name: 'Team Sync', start: '05:00 PM', end: '06:00 PM', type: 'Internal', loc: 'Conference Room', recurrence: 'Daily', status: 'UPCOMING' },
        ];

        const rows = mockEvents.map(e => `
            <tr>
                <td><div class="fw-bold">${e.name}</div><div class="text-muted small">${e.type}</div></td>
                <td><div class="text-dark">${e.start} - ${e.end}</div></td>
                <td>${e.loc}</td>
                <td><span class="badge badge-purple-light">${e.recurrence}</span></td>
                <td><span class="badge ${e.status === 'COMPLETED' ? 'badge-green-light' : 'badge-yellow-light'}">${e.status}</span></td>
                <td><button class="btn btn-ghost p-1" onclick="window.alert('Future function: View Details')"><i class="bi bi-eye"></i></button></td>
            </tr>
        `).join('');

        mainContent.innerHTML = `
            <div class="page-header d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h1 class="h3 fw-bold mb-1">Timetable & Schedule</h1>
                    <p class="text-muted mb-0">${dateStr}</p>
                </div>
                <div class="d-flex gap-2">
                    <button class="btn btn-secondary border-0" style="background:var(--bg-app); color:var(--text-2);" onclick="renderTimetable()">Today</button>
                    <button class="btn btn-primary" onclick="openNewTimetableModal()"><i class="bi bi-calendar-plus me-1"></i> Schedule Activity</button>
                </div>
            </div>

            <div class="card border-0 shadow-sm p-0 mb-4">
                <div class="p-4 border-bottom d-flex justify-content-between align-items-center">
                    <h5 class="fw-bold mb-0">Daily Agenda</h5>
                    <div class="btn-group btn-group-sm">
                        <button class="btn btn-outline-primary active">Day</button>
                        <button class="btn btn-outline-primary">Week</button>
                        <button class="btn btn-outline-primary">Month</button>
                    </div>
                </div>
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead style="background:var(--bg-surface);">
                            <tr>
                                <th class="px-4">Event Name & Type</th>
                                <th>Schedule</th>
                                <th>Location / Reference</th>
                                <th>Recurrence</th>
                                <th>Status</th>
                                <th class="text-end px-4">Actions</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>

            <div class="row g-4">
                <div class="col-md-4">
                    <div class="card border-0 shadow-sm p-4 h-100">
                        <h6 class="fw-bold mb-3"><i class="bi bi-bell-fill text-warning me-2"></i>Upcoming Reminders</h6>
                        <div class="d-flex flex-column gap-3">
                            <div class="p-3 rounded border-start border-4 border-primary" style="background:var(--bg-app);">
                                <div class="fw-semibold small">Call Mr. Sharma</div>
                                <div class="text-muted smaller">In 15 minutes</div>
                            </div>
                            <div class="p-3 rounded border-start border-4 border-warning" style="background:var(--bg-app);">
                                <div class="fw-semibold small">Submit Weekly Report</div>
                                <div class="text-muted smaller">By 06:00 PM today</div>
                            </div>
                        </div>
                    </div>
                </div>
                <div class="col-md-8">
                    <div class="card border-0 shadow-sm p-4 h-100">
                        <h6 class="fw-bold mb-3"><i class="bi bi-sticky-fill text-info me-2"></i>Quick Remarks</h6>
                        <textarea class="form-control border-dashed" rows="4" placeholder="Type a quick note for your day..."></textarea>
                    </div>
                </div>
            </div>
        `;
    }

    async function renderTodo() {
        const today = new Date().toISOString().split('T')[0];
        const tomorrow = new Date(Date.now() + 86400000).toISOString().split('T')[0];
        const yesterday = new Date(Date.now() - 86400000).toISOString().split('T')[0];

        const mockTodos = [
            { id: 1, title: 'Finalize Proposal - TechCorp', priority: 'HIGH', status: 'OPEN', assigned: 'Nency Savaliya', due: `${tomorrow}T14:30:00`, related: 'Project Alpha' },
            { id: 2, title: 'Follow-up with New Leads', priority: 'MEDIUM', status: 'IN_PROGRESS', assigned: 'Nency Savaliya', due: `${today}T10:00:00`, related: 'Tech Expo' },
            { id: 3, title: 'Internal Security Audit', priority: 'LOW', status: 'OPEN', assigned: 'Admin', due: `${yesterday}T16:00:00`, related: 'System Admin' },
            { id: 4, title: 'Client Feedback Analysis', priority: 'HIGH', status: 'RESOLVED', assigned: 'Nency Savaliya', due: '2026-02-26T12:00:00', related: 'SRM Feedback' },
        ];

        const formatRelativeDate = (dateStr) => {
            const date = new Date(dateStr);
            const now = new Date();
            const diffTime = date.getTime() - now.getTime();
            const diffDays = Math.round(diffTime / (1000 * 60 * 60 * 24));

            const timeStr = date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false });

            let dateLabel = '';
            if (diffDays === 0) dateLabel = 'Today';
            else if (diffDays === 1) dateLabel = 'Tomorrow';
            else if (diffDays === -1) dateLabel = 'Yesterday';
            else dateLabel = date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });

            return `${dateLabel}, ${timeStr}`;
        };

        const sevBadge = s => ({
            HIGH: '<span class="badge bg-danger">High</span>',
            MEDIUM: '<span class="badge bg-warning text-dark">Medium</span>',
            LOW: '<span class="badge bg-success">Low</span>'
        })[s] || `<span class="badge bg-secondary">${s}</span>`;

        const statBadge = s => ({
            OPEN:        '<span class="badge badge-purple-light">Open</span>',
            IN_PROGRESS: '<span class="badge bg-info-subtle text-info border border-info-subtle">In Progress</span>',
            RESOLVED:    '<span class="badge badge-green-light">Resolved</span>',
            BLOCKED:     '<span class="badge bg-danger-subtle text-danger border border-danger-subtle">Blocked</span>'
        })[s] || `<span class="badge">${s}</span>`;

        const rows = mockTodos.map(t => {
            const initials = t.assigned.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2);
            return `
            <tr>
                <td class="px-4"><div class="fw-bold">${t.title}</div><div class="text-muted smaller">Assigned: ${t.assigned}</div></td>
                <td>${sevBadge(t.priority)}</td>
                <td>${statBadge(t.status)}</td>
                <td><div class="d-flex align-items-center gap-2"><div class="rounded-circle bg-primary-light text-primary d-flex align-items-center justify-content-center fw-bold" style="width:28px;height:28px;font-size:10px;">${initials}</div><span class="small">${t.assigned}</span></div></td>
                <td><i class="bi bi-clock me-1"></i>${formatRelativeDate(t.due)}</td>
                <td><span class="text-muted small">${t.related}</span></td>
                <td class="text-end px-4">
                    <div class="dropdown">
                        <button class="btn btn-ghost btn-sm" data-bs-toggle="dropdown"><i class="bi bi-three-dots-vertical"></i></button>
                        <ul class="dropdown-menu dropdown-menu-end shadow border-0 p-2">
                            <li><a class="dropdown-item py-2 small" href="javascript:void(0)" onclick="window.alert('Evidence upload triggered')"><i class="bi bi-upload me-2 text-primary"></i> Upload Evidence</a></li>
                            <li><a class="dropdown-item py-2 small" href="#"><i class="bi bi-pencil me-2 text-info"></i> Edit Task</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item py-2 small text-danger" href="#"><i class="bi bi-trash me-2"></i> Delete</a></li>
                        </ul>
                    </div>
                </td>
            </tr>
        `;
        }).join('');

        mainContent.innerHTML = `
            <div class="page-header d-flex justify-content-between align-items-center mb-4">
                <div>
                    <h1 class="h3 fw-bold mb-1">To-Do List</h1>
                    <p class="text-muted mb-0">Manage and track your personal and team tasks.</p>
                </div>
                <button class="btn btn-primary" onclick="openNewTodoModal()"><i class="bi bi-plus-lg me-1"></i> Add New Task</button>
            </div>

            <div class="row g-3 mb-4">
                <div class="col-6 col-lg-3">
                    <div class="card border-0 shadow-sm p-3 text-center">
                        <div class="text-muted smaller mb-1">Total Tasks</div>
                        <div class="h4 fw-bold mb-0">${mockTodos.length}</div>
                    </div>
                </div>
                <div class="col-6 col-lg-3">
                    <div class="card border-0 shadow-sm p-3 text-center">
                        <div class="text-muted smaller mb-1">High Priority</div>
                        <div class="h4 fw-bold mb-0 text-danger">${mockTodos.filter(t => t.priority === 'HIGH').length}</div>
                    </div>
                </div>
                <div class="col-6 col-lg-3">
                    <div class="card border-0 shadow-sm p-3 text-center">
                        <div class="text-muted smaller mb-1">Ongoing</div>
                        <div class="h4 fw-bold mb-0 text-info">${mockTodos.filter(t => t.status === 'IN_PROGRESS').length}</div>
                    </div>
                </div>
                <div class="col-6 col-lg-3">
                    <div class="card border-0 shadow-sm p-3 text-center">
                        <div class="text-muted smaller mb-1">Resolved</div>
                        <div class="h4 fw-bold mb-0 text-success">${mockTodos.filter(t => t.status === 'RESOLVED').length}</div>
                    </div>
                </div>
            </div>

            <div class="card border-0 shadow-sm p-0 overflow-hidden">
                <div class="table-responsive">
                    <table class="table table-hover align-middle mb-0">
                        <thead style="background:var(--bg-surface);">
                            <tr>
                                <th class="px-4">Task Title</th>
                                <th>Priority</th>
                                <th>Status</th>
                                <th>Assigned To</th>
                                <th>Due Date</th>
                                <th>Related Entity</th>
                                <th class="text-end px-4">Actions</th>
                            </tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                </div>
            </div>
        `;
    }

    window.openNewTodoModal = () => {
        const html = `
            <div class="row g-3">
                <div class="col-12"><label class="form-label fw-semibold">Task Title *</label><input type="text" id="td-title" class="form-control" placeholder="What needs to be done?"></div>
                <div class="col-md-6"><label class="form-label fw-semibold">Priority Level</label><select id="td-priority" class="form-select"><option value="LOW">Low</option><option value="MEDIUM" selected>Medium</option><option value="HIGH">High</option></select></div>
                <div class="col-md-6"><label class="form-label fw-semibold">Status</label><select id="td-status" class="form-select"><option value="OPEN">Open</option><option value="IN_PROGRESS">In Progress</option><option value="RESOLVED">Resolved</option><option value="BLOCKED">Blocked</option></select></div>
                <div class="col-md-6"><label class="form-label fw-semibold">Assigned To</label><input type="text" id="td-assigned" class="form-control" placeholder="User Name"></div>
                <div class="col-md-6"><label class="form-label fw-semibold">Due Date</label><input type="date" id="td-due" class="form-control"></div>
                <div class="col-12"><label class="form-label fw-semibold">Related Entity</label><input type="text" id="td-related" class="form-control" placeholder="Project, Client or Lead name"></div>
                <div class="col-12"><label class="form-label fw-semibold">Description</label><textarea id="td-desc" class="form-control" rows="3" placeholder="Additional details..."></textarea></div>
                <div class="col-12"><label class="form-label fw-semibold">Evidence Upload</label><input type="file" id="td-evidence" class="form-control"></div>
            </div>
        `;
        createModal('modal-new-todo', 'Create New Task', html, async () => {
            const title = document.getElementById('td-title').value;
            if (!title) throw new Error("Task title is required");
            showToast('New task added successfully (Frontend Sync)');
            renderTodo();
        }, "Create Task");
    };

    window.openNewTimetableModal = () => {
        const html = `
            <div class="row g-3">
                <div class="col-12"><label class="form-label fw-semibold">Event Name *</label><input type="text" id="tt-name" class="form-control" placeholder="e.g., Client Follow-up"></div>
                <div class="col-md-6"><label class="form-label fw-semibold">Start Time *</label><input type="datetime-local" id="tt-start" class="form-control"></div>
                <div class="col-md-6"><label class="form-label fw-semibold">End Time *</label><input type="datetime-local" id="tt-end" class="form-control"></div>
                <div class="col-md-6"><label class="form-label fw-semibold">Activity Type</label><select id="tt-type" class="form-select"><option value="Meeting">Meeting</option><option value="Call">Call</option><option value="Field Visit">Field Visit</option><option value="Internal">Internal</option></select></div>
                <div class="col-md-6"><label class="form-label fw-semibold">Recurrence</label><select id="tt-rec" class="form-select"><option value="None">None</option><option value="Daily">Daily</option><option value="Weekly">Weekly</option><option value="Monthly">Monthly</option></select></div>
                <div class="col-12"><label class="form-label fw-semibold">Location / Shop Reference</label><input type="text" id="tt-loc" class="form-control" placeholder="Shop name or address"></div>
                <div class="col-12"><label class="form-label fw-semibold">Reminders</label><select id="tt-rem" class="form-select"><option value="5m">5 mins before</option><option value="15m" selected>15 mins before</option><option value="1h">1 hour before</option></select></div>
                <div class="col-12"><label class="form-label fw-semibold">Remarks</label><textarea id="tt-remarks" class="form-control" rows="2" placeholder="Any special notes..."></textarea></div>
            </div>
        `;
        createModal('modal-new-timetable', 'Schedule Activity', html, async () => {
            const name = document.getElementById('tt-name').value;
            if (!name) throw new Error("Event name is required");
            showToast('Activity scheduled successfully (Frontend Sync)');
            renderTimetable();
        }, "Schedule");
    };
