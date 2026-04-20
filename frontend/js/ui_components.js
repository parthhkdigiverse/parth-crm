// frontend/js/ui_components.js
// Helper to get initials
window.getInitials = function (name) {
    if (!name) return '??';
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0].charAt(0) + parts[parts.length - 1].charAt(0)).toUpperCase();
    }
    return name.slice(0, 2).toUpperCase();
};

window.updateBulkActionBar = function (options) {
    const { count, onDelete, onCancel } = options || {};
    let bar = document.getElementById('bulk-action-bar');

    if (!bar) {
        const html = `
        <div id="bulk-action-bar" class="bulk-action-bar">
            <div class="d-flex align-items-center gap-3">
                <div class="bulk-select-badge"><span id="bulk-count-val">0</span> Selected</div>
                <button class="btn btn-link p-0" id="bulk-cancel-btn">Cancel</button>
            </div>
            <div class="bulk-action-btn-group">
                <button class="bulk-delete-confirm-btn" id="bulk-delete-confirm-btn">
                    <i class="bi bi-trash me-2"></i> Delete
                </button>
            </div>
        </div>`;
        document.body.insertAdjacentHTML('beforeend', html);
        bar = document.getElementById('bulk-action-bar');
    }

    const countVal = document.getElementById('bulk-count-val');
    const deleteBtn = document.getElementById('bulk-delete-confirm-btn');
    const cancelBtn = document.getElementById('bulk-cancel-btn');

    if (count > 0) {
        if (countVal) countVal.textContent = count;
        bar.classList.add('show');

        if (deleteBtn) deleteBtn.onclick = (e) => {
            e.preventDefault();
            if (onDelete) onDelete();
        };
        if (cancelBtn) cancelBtn.onclick = (e) => {
            e.preventDefault();
            if (onCancel) onCancel();
        };
    } else {
        bar.classList.remove('show');
    }
};
console.log('UI Components: updateBulkActionBar ready');

window.getRoleFlags = function (roleValue) {
    const role = (roleValue || '').toUpperCase();
    return {
        role,
        isAdmin: role === 'ADMIN',
        isSales: role === 'SALES' || role === 'PROJECT_MANAGER_AND_SALES',
        isTelesales: role === 'TELESALES',
        isPM: role === 'PROJECT_MANAGER' || role === 'PROJECT_MANAGER_AND_SALES',
        isClient: role === 'CLIENT'
    };
}

window.getQuickAddItems = function (roleValue) {
    const flags = getRoleFlags(roleValue);
    const items = [];

    if (flags.isAdmin || flags.isSales || flags.isTelesales || flags.isPM) {
        items.push({ href: 'clients.html?add=true', icon: 'bi-people', iconClass: 'text-info', label: 'New Client' });
    }
    if (flags.isAdmin || flags.isPM) {
        items.push({ href: 'projects.html?add=true', icon: 'bi-briefcase', iconClass: 'text-primary', label: 'New Project' });
    }
    if (flags.isAdmin || flags.isSales) {
        items.push({ href: 'areas.html?add=true', icon: 'bi-building', iconClass: '', iconStyle: 'color:#6366f1;', label: 'New Area / Shop' });
    }
    if (flags.isAdmin || flags.isSales || flags.isTelesales) {
        items.push({ href: 'visits.html?add=true', icon: flags.isTelesales ? 'bi-telephone' : 'bi-geo-alt', iconClass: 'text-success', label: flags.isTelesales ? 'New Call Log' : 'New Visit' });
    }
    if (flags.isAdmin || flags.isPM) {
        items.push({ href: 'meetings.html?add=true', icon: 'bi-calendar-event', iconClass: 'text-success', label: 'New Meeting' });
    }
    if (!flags.isClient) {
        items.push({ href: 'todo.html', icon: 'bi-check2-square', iconClass: 'text-primary', label: 'New Task' });
    }
    if (flags.isAdmin || flags.isSales || flags.isTelesales || flags.isPM) {
        items.push({ href: 'javascript:void(0)', onclick: 'if(window.openNewBillModal) window.openNewBillModal();', icon: 'bi-receipt', iconClass: 'text-danger', label: 'New Payment' });
    }
    if (flags.isAdmin || flags.isPM) {
        items.push({ href: 'issues.html?add=true', icon: 'bi-exclamation-triangle', iconClass: 'text-warning', label: 'New Issue' });
        items.push({ href: 'feedback.html?add=true', icon: 'bi-chat-square-text', iconClass: 'text-info', label: 'New Feedback' });
    }
    if (!flags.isClient && !flags.isAdmin) {
        items.push({ href: 'leaves.html?add=true', icon: 'bi-calendar3', iconClass: 'text-warning', label: 'New Leave Request' });
    }
    if (flags.isAdmin) {
        items.push({ divider: true });
        items.push({ href: 'admin.html?add=true', icon: 'bi-person-plus', iconClass: 'text-secondary', label: 'New User' });
    }

    return items;
}

window.renderQuickAddItems = function (roleValue) {
    return getQuickAddItems(roleValue).map(item => {
        if (item.divider) {
            return '<li><hr class="dropdown-divider my-1"></li>';
        }
        const action = item.onclick
            ? `href="${item.href}" onclick="${item.onclick}"`
            : `href="${item.href}"`;
        return `<li><a class="dropdown-item" ${action}><i class="bi ${item.icon} ${item.iconClass || ''}"></i> ${item.label}</a></li>`;
    }).join('');
}

// ─── SIDEBAR ──────────────────────────────────────────────────────────
window.renderSidebar = function (active) {
    const u = getUser();
    const role = u?.role || 'TELESALES';
    const { isAdmin, isSales, isTelesales, isPM, isClient } = getRoleFlags(role);

    const isCollapsed = localStorage.getItem('sidebar-collapsed') === 'true';
    if (isCollapsed) {
        document.body.classList.add('sidebar-collapsed');
        setTimeout(() => {
            document.getElementById('sidebar-container')?.classList.add('collapsed');
        }, 0);
    } else {
        document.body.classList.remove('sidebar-collapsed');
    }

    window.__lastSidebarActive = active;
    const roleName = String(role || '').toUpperCase();
    const effectivePolicy = window.__crmEffectiveAccessPolicy || JSON.parse(localStorage.getItem('crm_access_policy') || 'null');

    const allowedPages = Array.isArray(effectivePolicy?.allowed_pages)
        ? effectivePolicy.allowed_pages
        : (effectivePolicy?.policy?.page_access?.[roleName] || []);

    const allowAllPages = roleName === 'ADMIN' || allowedPages.includes('*');

    // The "Settings" link is compulsory for all Staff (non-ADMIN, non-CLIENT).
    // ADMIN has full access anyway.
    const isStaff = (roleName !== 'CLIENT' && roleName !== 'ADMIN');
    const showSettings = isStaff || (roleName === 'ADMIN');

    const canShowPage = (href) => {
        const page = String(href || '').split('?')[0];
        if (!page) return false;
        // Dashboard pages are always allowed for staff
        //if (['dashboard.html', 'timetable.html', 'todo.html'].includes(page)) return true;
        if (allowAllPages) return true;
        return allowedPages.includes(page);
    };

    const sbSection = (id, title, icon, items) => {
        const filteredItems = items.filter(item => canShowPage(item.href));
        // Always return the section header per user request for sidebar consistency
        // Only the items inside will be conditionally shown
        const isAnyActive = filteredItems.some(item => item.id === active);
        const isOpen = isAnyActive; // Auto-open if active item is inside

        const highCount = sessionStorage.getItem('crm_high_issue_count');
        const hasHighIssues = highCount && highCount !== '0';

        const resetCount = sessionStorage.getItem('crm_reset_req_count');
        const hasResets = resetCount && resetCount !== '0';

        const sectionHasAlert = (hasHighIssues && filteredItems.some(item => item.id === 'issues')) ||
            (hasResets && id === 'admin');

        return `
        <div class="sb-section" id="sb-sec-${id}">
            <div class="sb-section-header ${isOpen ? 'open' : ''} ${sectionHasAlert ? 'has-alert' : ''}" onclick="toggleSbSection('${id}')">
                <i class="bi ${icon} sb-sec-icon"></i>
                <div class="d-flex align-items-center gap-2">
                    <span>${title}</span>
                    ${sectionHasAlert ? '<span class="sb-sec-dot" style="background:#ef4444;"></span>' : ''}
                </div>
                <i class="bi bi-chevron-right sb-arrow"></i>
            </div>
            <div class="sb-section-items ${isOpen ? 'open' : ''}">
                ${filteredItems.map(item => {
            const showIssueBadge = item.id === 'issues' && hasHighIssues;
            const showResetBadge = item.id === 'admin' && hasResets;
            return `
                    <a href="${item.href}" class="sb-link ${item.id === active ? 'active' : ''} ${showIssueBadge || showResetBadge ? 'alert-highlight' : ''}">
                        <i class="bi ${item.icon}"></i>
                        <span>${item.label}</span>
                        ${showIssueBadge ? `<span class="sb-issue-badge">${highCount}</span>` : ''}
                        ${showResetBadge ? `<span class="sb-issue-badge" style="background:#f59e0b;">${resetCount}</span>` : ''}
                    </a>
                `;
        }).join('')}
            </div>
        </div>`;
    };

    return `
    <div id="sidebar-container" onclick="if(!event.target.closest('.sb-link') && !event.target.closest('.sb-section-header') && !event.target.closest('.sb-bottom-link')) toggleSidebarState()">
        <div class="sidebar-brand d-flex align-items-center" style="gap: 20px; padding: 0 24px; height: 60px; position: relative;">
            <div class="sidebar-logo-ai" style="width: 38px; height: 38px; flex-shrink: 0;"></div>
            <span class="brand-text" style="font-size: 18px;">SRM AI SETU</span>
        </div>

        <div class="sb-scroll-area">
            ${sbSection('db', 'Dashboard', 'bi-grid-1x2', [
        { id: 'dashboard', href: 'dashboard.html', icon: 'bi-bar-chart-line-fill', label: 'Overview' },
        { id: 'timetable', href: 'timetable.html', icon: 'bi-calendar3', label: 'Timetable' },
        { id: 'todo', href: 'todo.html', icon: 'bi-check2-square', label: 'To-Do List' }
    ])}

            ${sbSection('admin', 'Administration', 'bi-shield-check', [
        { id: 'admin', href: 'admin.html', icon: 'bi-people', label: 'Users & Roles' }
    ])}
            ${sbSection('fo', 'Field Operations', 'bi-geo-alt', [
        { id: 'leads', href: 'leads.html', icon: 'bi-kanban', label: 'Projects Overview' },
        { id: 'areas', href: 'areas.html', icon: 'bi-shop', label: 'Areas & Shops' },
        { id: 'visits', href: 'visits.html', icon: 'bi-geo-alt-fill', label: 'Visits' }
    ])}
            ${sbSection('pm', 'Project Management', 'bi-briefcase', [
        { id: 'demo', href: 'projects_demo.html', icon: 'bi-play-circle', label: 'Demo' },
        { id: 'projects', href: 'projects.html', icon: 'bi-briefcase', label: 'Projects' },
        { id: 'meetings', href: 'meetings.html', icon: 'bi-calendar-event', label: 'Meetings' },
        { id: 'issues', href: 'issues.html', icon: 'bi-exclamation-triangle', label: 'Issues' }
    ])}
            ${sbSection('client', 'Client Relations', 'bi-person-badge', [
        { id: 'clients', href: 'clients.html', icon: 'bi-people', label: 'Clients' },
        { id: 'payment', href: 'billing.html', icon: 'bi-receipt', label: 'Billing & Invoices' },
        { id: 'feedback', href: 'feedback.html', icon: 'bi-chat-square-text', label: 'Feedback' }
    ])}
            ${sbSection('hr', 'HR & Payroll', 'bi-people-fill', [
        { id: 'employees', href: 'employees.html', icon: 'bi-people', label: 'Employees' },
        { id: 'salary', href: 'salary.html', icon: 'bi-cash-stack', label: 'Salary & Payroll' },
        { id: 'leaves', href: 'leaves.html', icon: 'bi-calendar-x', label: 'Leaves' },
        { id: 'incentives', href: 'incentives.html', icon: 'bi-award', label: 'Incentives' }
    ])}
            ${sbSection('rpt', 'Reports & Analytics', 'bi-graph-up', [
        { id: 'employee_report', href: 'employee_report.html', icon: 'bi-person', label: 'Employee Report' },
        { id: 'client_report', href: 'client_report.html', icon: 'bi-people', label: 'Client Report' }
    ])}
        </div>
        
        <div class="sb-bottom">
            <a href="#" class="sb-bottom-link logout" onclick="logout();return false;" title="Logout">
                <i class="bi bi-box-arrow-right"></i> <span>Logout</span>
            </a>
            ${showSettings ? `
            <a href="settings.html" class="sb-bottom-link ${active === 'settings' ? 'active' : ''}" title="Settings">
                <i class="bi bi-gear"></i> <span>Settings</span>
            </a>` : ''}
        </div>
    </div>
    <div id="sb-overlay" class="sidebar-overlay" onclick="toggleMobileSidebar()"></div>
    `;
}

window.toggleMobileSidebar = function () {
    const sb = document.getElementById('sidebar-container');
    const overlay = document.getElementById('sb-overlay');
    if (!sb) return;

    const isOpen = sb.classList.toggle('mobile-open');
    if (overlay) {
        overlay.style.opacity = isOpen ? '1' : '0';
        overlay.style.visibility = isOpen ? 'visible' : 'hidden';
    }

    // Lock body scroll when mobile sidebar is open
    document.body.style.overflow = isOpen ? 'hidden' : '';
};

window.toggleMobileSearch = function () {
    let mobileSearch = document.getElementById('mobile-search-overlay');

    if (!mobileSearch) {
        const html = `
            <div id="mobile-search-overlay" class="position-fixed top-0 start-0 w-100 bg-white shadow-sm d-flex align-items-center px-3" style="height: 60px; z-index: 2000; transform: translateY(-100%); transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);">
                <i class="bi bi-search text-muted me-2"></i>
                <input type="text" id="mobile-search-input" class="form-control border-0 bg-transparent p-0 shadow-none" placeholder="Search..." onkeyup="if(event.key === 'Enter') { const val = this.value.trim(); if(val) window.location.href = 'search.html?q=' + encodeURIComponent(val); }">
                <button class="btn btn-link text-muted p-2" onclick="toggleMobileSearch()">
                    <i class="bi bi-x-lg"></i>
                </button>
            </div>
        `;
        document.body.insertAdjacentHTML('beforeend', html);
        mobileSearch = document.getElementById('mobile-search-overlay');
    }

    const isShowing = mobileSearch.style.transform === 'translateY(0%)';
    mobileSearch.style.transform = isShowing ? 'translateY(-100%)' : 'translateY(0%)';

    if (!isShowing) {
        setTimeout(() => document.getElementById('mobile-search-input').focus(), 300);
    }
};

window.toggleSidebarState = function () {
    const sb = document.getElementById('sidebar-container');
    if (!sb) return;
    const isCollapsed = sb.classList.toggle('collapsed');
    document.body.classList.toggle('sidebar-collapsed', isCollapsed);
    localStorage.setItem('sidebar-collapsed', isCollapsed);

    // Close all sections when collapsing
    if (isCollapsed) {
        document.querySelectorAll('.sb-section-items').forEach(el => el.classList.remove('open'));
        document.querySelectorAll('.sb-section-header').forEach(el => el.classList.remove('open'));
    }
};

window.toggleSbSection = function (id) {
    const sb = document.getElementById('sidebar-container');
    if (sb && sb.classList.contains('collapsed')) {
        sb.classList.remove('collapsed');
        localStorage.setItem('sidebar-collapsed', 'false');
    }

    const sec = document.getElementById(`sb-sec-${id}`);
    if (!sec) return;

    const hdr = sec.querySelector('.sb-section-header');
    const lst = sec.querySelector('.sb-section-items');

    const isOpen = lst.classList.toggle('open');
    hdr.classList.toggle('open', isOpen);
};

// ─── TOP HEADER ───────────────────────────────────────────────────────
window.injectTopHeader = function (pageTitle) {
    if (document.querySelector('.top-header')) return;
    window.__lastPageTitle = pageTitle;
    const u = getUser();
    const role = (u?.role || '').replace(/_/g, ' ');
    const initials = window.getInitials(u?.name || u?.email || 'AD');

    const pageToParent = {
        'Users & Roles': 'Administration',
        'Project Overview': 'Field Operations',
        'Projects Overview': 'Field Operations',
        'Visits': 'Field Operations',
        'Areas & Shops': 'Field Operations',
        'Projects': 'Project Management',
        'Project Management Demo': 'Project Management',
        'Meeting Strategy': 'Project Management',
        'Meetings': 'Project Management',
        'Issues': 'Project Management',
        'Clients': 'Client Relations',
        'Billing & Invoices': 'Client Relations',
        'Feedback': 'Client Relations',
        'Employees': 'HR & Payroll',
        'Salary': 'HR & Payroll',
        'Salary & Payroll': 'HR & Payroll',
        'Salary Slip': 'HR & Payroll',
        'Leaves': 'HR & Payroll',
        'Incentives': 'HR & Payroll',
        'Demo': 'Project Management',
        'Demo Pipeline': 'Project Management',
        'Reports': 'Reports & Analytics',
        'Timetable': 'Dashboard',
        'Timetable & Schedule': 'Dashboard',
        'To-Do List': 'Dashboard',
        'TO-DO List': 'Dashboard',
        'To-do': 'Dashboard',
        'Overview': 'Dashboard',
        'Dashboard': 'Home',
        'Profile': 'Account',
        'My Profile': 'Account',
        'Settings': 'Account',
        'Notifications': 'System',
        'Search Results': 'Search'
    };

    // Standardize key matching: trim and case-insensitive
    const normalizedTitle = (pageTitle || '').trim();
    let parent = pageToParent[normalizedTitle];

    if (!parent) {
        const lowerTitle = normalizedTitle.toLowerCase();
        const foundKey = Object.keys(pageToParent).find(k => k.toLowerCase() === lowerTitle);
        if (foundKey) parent = pageToParent[foundKey];
    }
    const chevronSvg = `<svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" style="opacity: 0.5;"><path d="M4.5 9L7.5 6L4.5 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
    const breadcrumbHtml = parent ? `
        <div class="d-flex align-items-center gap-2" style="font-size: 15px;">
            <span style="color: var(--text-2); font-weight: 500;">${parent}</span>
            ${chevronSvg}
            <h1 class="page-section-title mt-0 mb-0" style="font-size: 1.15rem; display: inline-block;">${pageTitle}</h1>
        </div>
    ` : `<h1 class="page-section-title mb-0" style="font-size: 1.25rem;">${pageTitle}</h1>`;

    const alertsRedDot = '<span id="nav-notif-dot" class="position-absolute bg-danger border border-white rounded-circle d-none" style="width:8px;height:8px;top:8px;right:8px;"></span>';

    const quickAddItems = renderQuickAddItems(u?.role);

    const logoHtml = `
        <div class="nav-logo align-items-center d-none" style="cursor: pointer; gap: 20px;" onclick="window.location.href='dashboard.html'">
            <div class="sidebar-logo-ai" style="width: 32px; height: 32px; flex-shrink: 0;"></div>
            <span class="brand-text" style="font-size: 16px; letter-spacing: -0.02em;">SRM AI SETU</span>
        </div>`;

    const headerHtml = `
    <div class="top-header">
        <div class="top-header-left">
            <button class="btn btn-dark-soft d-lg-none me-1" onclick="toggleMobileSidebar()" style="width: 38px; height: 38px; padding: 0; display: flex; align-items: center; justify-content: center; background: rgba(37, 99, 235, 0.05); border: 1px solid rgba(37, 99, 235, 0.1); border-radius: 8px;">
                <i class="bi bi-list" style="font-size: 1.4rem; color: var(--primary);"></i>
            </button>
            ${logoHtml}
            <div class="nav-breadcrumb">
                <div class="d-none d-sm-block">${breadcrumbHtml}</div>
                <div class="d-block d-sm-none page-nav-title" style="color: var(--nav-text-active); font-weight: 600;">${pageTitle}</div>
            </div>
        </div>

        <div class="top-header-center">
            <div class="nav-search" style="max-width: 320px; width: 100%;">
                <div class="position-relative w-100">
                    <button class="btn p-0 position-absolute text-muted search-btn" style="left: 12px; top: 50%; transform: translateY(-50%); z-index: 10;" onclick="const val = document.getElementById('global-search-input').value.trim(); if(val) window.location.href = 'search.html?q=' + encodeURIComponent(val);">
                        <i class="bi bi-search" style="color: var(--nav-text-muted);"></i>
                    </button>
                    <input type="text" id="global-search-input" class="form-control" placeholder="Search..." autocomplete="new-password" readonly onfocus="this.removeAttribute('readonly')" style="padding-left: 38px; border-radius: 20px; height: 38px; background: var(--bg-app); border: 1px solid var(--border); color: var(--text-main); font-weight: 500;">
                    <div id="live-search-dropdown" class="search-results-dropdown"></div>
                </div>
            </div>
        </div>

        <div class="top-header-right d-flex align-items-center gap-2">
            <!-- Mobile Search Icon (only visible on tablet) -->
            <button class="btn d-md-none p-0 d-flex align-items-center justify-content-center hover-hit-target search-icon-btn" style="width:40px; height:40px; color: var(--nav-text);" onclick="toggleMobileSearch()">
                <i class="bi bi-search"></i>
            </button>

            <!-- Add New Gradient Button -->
            <div class="dropdown d-none d-sm-block nav-add">
                <button class="btn d-flex align-items-center gap-2 px-3 dropdown-toggle shadow-sm" type="button" id="addNewDropdown" data-bs-toggle="dropdown" aria-expanded="false" style="font-size:13px; font-weight:700; border-radius: 10px; height: 40px; background: var(--accent-gradient); color: #ffffff !important; border: 1px solid rgba(255,255,255,0.2); padding: 10px 18px;">
                    <i class="bi bi-plus-lg" style="color: #ffffff !important;"></i> <span style="color: #ffffff !important;">Add New</span>
                </button>
                <ul class="dropdown-menu dropdown-menu-end shadow border-0" aria-labelledby="addNewDropdown" style="font-size: 0.85rem; border-radius:12px; padding:8px; min-width:200px; background: var(--bg-surface); border: 1px solid var(--border) !important;">
                    ${quickAddItems}
                </ul>
            </div>


            <!-- Notifications Bell -->
            <div class="dropdown">
                <div class="position-relative d-flex align-items-center justify-content-center hover-hit-target" data-bs-toggle="dropdown" aria-expanded="false" style="cursor:pointer; width:40px; height:40px; border-radius: 50%; color: var(--primary); background: var(--primary-soft);">
                    <i class="bi bi-bell" style="font-size: 1.1rem;"></i>
                    ${alertsRedDot}
                </div>
                <div class="dropdown-menu dropdown-menu-end shadow-lg border-0 p-0" style="width: 320px; border-radius: 12px; overflow: hidden; z-index: 9999; background: var(--bg-surface); border: 1px solid var(--border) !important;">
                    <div class="px-3 py-2 border-bottom d-flex justify-content-between align-items-center" style="background: var(--bg-page); border-color: var(--border) !important;">
                        <span class="fw-bold small" style="color: var(--text-1);">Notifications</span>
                        <span id="bell-unread-badge" class="badge bg-danger rounded-pill d-none" style="font-size:10px;">0</span>
                    </div>
                    <div id="bell-notif-list" style="max-height: 320px; overflow-y: auto;">
                        <div class="p-3 text-center">
                            <i class="bi bi-bell-slash text-muted" style="font-size: 1.5rem;"></i>
                            <p class="text-muted extra-small mt-2 mb-0">No new alerts.</p>
                        </div>
                    </div>
                    <div class="border-top" style="border-color: var(--border) !important;">
                        <a href="notifications.html" class="d-flex align-items-center justify-content-center gap-2 py-2 text-decoration-none" style="font-size: 0.8rem; font-weight: 600; color: var(--primary); background: var(--bg-page); transition: background 0.2s;" onmouseover="this.style.background='var(--primary-soft)'" onmouseout="this.style.background='var(--bg-page)'">
                            <i class="bi bi-layout-text-window-reverse"></i> View Master Feed
                        </a>
                    </div>
                </div>
            </div>
            
            <!-- Profile -->
            <div class="d-flex align-items-center gap-2 ps-2 dropdown border-start ms-1" style="border-color: var(--border) !important;">
                <div class="rounded-circle d-flex align-items-center justify-content-center fw-bold shadow-sm initials-bubble" style="width:36px; height:36px; font-size:11px; border: 1px solid var(--border); background: var(--primary-soft); color: var(--primary);">${initials}</div>
                <div class="d-flex align-items-center dropdown-toggle" id="profileDropdown" data-bs-toggle="dropdown" aria-expanded="false" style="cursor:pointer;">
                    <div class="d-none d-xl-block ms-1">
                        <div class="fw-bold mb-0 nav-uname" style="font-size:13px; line-height:1.2; color: var(--text-1);">${u?.name || 'User'}</div>
                        <div class="nav-urole" style="font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:0.05em; color: var(--text-3); margin-top: 1px; line-height:1;">${role}</div>
                    </div>
                </div>
                <ul class="dropdown-menu dropdown-menu-end shadow border-0 p-2" aria-labelledby="profileDropdown" style="border-radius:12px; min-width:200px; font-size:0.85rem; background: var(--bg-surface); border: 1px solid var(--border) !important;">
                    <li class="px-3 pt-2 pb-2 border-bottom mb-2">
                        <div class="fw-bold text-dark" style="font-size: 14px;">${u?.name || 'User'}</div>
                        <div style="font-size: 0.75rem; color: var(--text-3);">${u?.email || 'user@crmsetu.com'}</div>
                        <div class="mt-1"><span class="badge" style="background: var(--primary-soft); color: var(--primary); font-size: 9px; padding: 2px 6px; text-transform: uppercase; letter-spacing: 0.03em;">${role}</span></div>
                    </li>
                    <li><hr class="dropdown-divider my-1" style="border-color: var(--border);"></li>
                    <li><a class="dropdown-item rounded-2 py-2" href="profile.html" style="color: var(--text-2);"><i class="bi bi-person me-2 text-primary"></i> Profile</a></li>
                    <li><a class="dropdown-item rounded-2 py-2" href="settings.html" style="color: var(--text-2);"><i class="bi bi-gear me-2 text-secondary"></i> Settings</a></li>
                    <li><hr class="dropdown-divider my-1" style="border-color: var(--border);"></li>
                    <li><a class="dropdown-item rounded-2 py-2 text-danger" href="#" onclick="logout();return false;"><i class="bi bi-box-arrow-right me-2"></i> Logout</a></li>
                </ul>
            </div>
        </div>
    </div>`;

    const rightSide = document.querySelector('.flex-grow-1');
    if (rightSide) {
        rightSide.insertAdjacentHTML('afterbegin', headerHtml);
    }

    startNotificationPolling();
    checkHighPriorityIssues();
    if (typeof window.initLiveSearch === 'function') {
        window.initLiveSearch();
    }

    setTimeout(() => {
        if (window.checkUrlForQuickAdd) window.checkUrlForQuickAdd();
        // Force-clear Chrome autofill on the global search bar
        const gsi = document.getElementById('global-search-input');
        if (gsi) { gsi.value = ''; }
    }, 200);

    // Inject overlay if not present
    if (!document.getElementById('sb-overlay')) {
        document.body.insertAdjacentHTML('beforeend', '<div id="sb-overlay" class="sidebar-overlay" onclick="toggleMobileSidebar()"></div>');
    }

    // Run access check
    if (typeof window.checkPageAccess === 'function') {
        window.checkPageAccess();
    }
}

// ─── AUTO-REFRESH UI ON PERMISSIONS CHANGE ──────────────────────────
document.addEventListener('permissions-changed', () => {
    console.log('UI Components: Permissions changed, refreshing sidebar and header...');

    // Re-render sidebar if container exists
    const sbContainer = document.getElementById('sidebar');
    if (sbContainer && window.renderSidebar && window.__lastSidebarActive) {
        sbContainer.innerHTML = window.renderSidebar(window.__lastSidebarActive);
    }

    // Re-render top header if breadcrumb exists
    const topHeader = document.querySelector('.top-header');
    if (topHeader) {
        topHeader.remove(); // Remove old one
        if (window.injectTopHeader && window.__lastPageTitle) {
            window.injectTopHeader(window.__lastPageTitle);
        }
    }

    // Also update any quick-add items if the dropdown is open or stored
    // (They are re-rendered as part of injectTopHeader)
});

window.getInitials = function (name) {
    if (!name) return '??';
    const parts = name.split(' ').filter(p => p.trim() !== '');
    if (parts.length === 1) return parts[0].substring(0, 2).toUpperCase();
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
};

window.updateTopHeaderProfile = function (name, role) {
    const initials = window.getInitials(name || 'User');
    const u = getUser() || {};
    const displayRole = (role || u.role || 'User').replace(/_/g, ' ');

    const profileToggle = document.getElementById('profileDropdown');
    if (profileToggle) {
        // Update initials bubble
        const initialsBubble = profileToggle.parentElement?.querySelector('.initials-bubble');
        if (initialsBubble) {
            initialsBubble.textContent = initials;
        }

        // Update name and role in the toggle
        const nameEl = profileToggle.querySelector('.nav-uname');
        if (nameEl) nameEl.textContent = name || 'User';
        const roleEl = profileToggle.querySelector('.nav-urole');
        if (roleEl) roleEl.textContent = displayRole;
    }

    // Update dropdown header
    const dropdownMenu = profileToggle?.parentElement?.querySelector('.dropdown-menu');
    if (dropdownMenu) {
        const dropName = dropdownMenu.querySelector('li .fw-bold');
        if (dropName) dropName.textContent = name || 'User';

        const emailEl = dropdownMenu.querySelector('li div[style*="font-size: 0.75rem"]');
        if (emailEl) emailEl.textContent = u.email || 'user@crmsetu.com';

        const badgeEl = dropdownMenu.querySelector('li .badge');
        if (badgeEl) badgeEl.textContent = displayRole;
    }
};



// ─── GLOBAL QUICK ADD HANDLER ──────────────────────────────────────────
window.checkUrlForQuickAdd = function () {
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get('add') !== 'true') return;

    const path = window.location.pathname.toLowerCase();

    try {
        if (path.includes('visits.html')) {
            const modal = document.getElementById('visitModal');
            if (modal) modal.classList.add('show');
            else if (window.bootstrap) {
                const m = document.getElementById('visitModal');
                if (m) bootstrap.Modal.getOrCreateInstance(m).show();
            }
        }
        else if (path.includes('meetings.html')) {
            const modalEl = document.getElementById('addMeetingModal');
            if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
        else if (path.includes('issues.html')) {
            const modalEl = document.getElementById('addIssueModal');
            if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
        else if (path.includes('projects.html')) {
            const addBtn = document.querySelector('button[onclick*="openProjectUpdateModal"]') ||
                document.querySelector('.page-content button.btn-primary');
            if (addBtn) addBtn.click();
            else if (window.openProjectUpdateModal) window.openProjectUpdateModal();
        }
        else if (path.includes('areas.html') || path.includes('leads.html')) {
            const addBtn = document.querySelector('button[onclick*="openAreaModal"]') ||
                document.querySelector('button[onclick*="openCreateModal"]') ||
                document.querySelector('.page-content button.btn-primary');
            if (addBtn) addBtn.click();
            else if (window.openAreaModal) window.openAreaModal();
            else if (window.openCreateModal) window.openCreateModal();
        }
        else if (path.includes('clients.html')) {
            const addBtn = document.querySelector('button[onclick*="showAddClientModal"]') ||
                document.querySelector('.page-header button.btn-primary');
            if (addBtn) addBtn.click();
            else if (window.showAddClientModal) window.showAddClientModal();
        }
        else if (path.includes('admin.html')) {
            const addBtn = document.querySelector('button[onclick*="addUser"]') ||
                document.querySelector('.page-header button.btn-primary');
            if (addBtn) addBtn.click();
            else if (window.addUser) window.addUser();
        }
        else if (path.includes('feedback.html')) {
            const modalEl = document.getElementById('addFeedbackModal');
            if (modalEl) bootstrap.Modal.getOrCreateInstance(modalEl).show();
        }
        else if (path.includes('leaves.html')) {
            if (window.openLeaveModal) window.openLeaveModal();
            else {
                const modal = document.getElementById('leaveModal');
                if (modal) modal.classList.add('show');
            }
        }
    } catch (e) {
        console.warn("Quick Add trigger failed:", e);
    }
};

// ─── NOTIFICATION BELL POLLING ────────────────────────────────────────
// State to track if polling is already active
window._notifPollStarted = window._notifPollStarted || false;

// Expose refreshBell globally so other pages (like notifications.html) can trigger an instant sync.
window.refreshBell = async function () {
    if (!sessionStorage.getItem('access_token')) return;
    try {
        // BUG 4 FIX: Derive unread count from the list itself — eliminates redundant API call.
        // BUG 2 FIX: Limit raised to 200 to match master notification feed.
        const allList = await apiGet('/notifications/?limit=200');
        const notifications = (Array.isArray(allList) ? allList : []);
        const unread = notifications.filter(n => !n.is_read).length;

        // Update red dot
        const dot = document.getElementById('nav-notif-dot');
        if (dot) unread > 0 ? dot.classList.remove('d-none') : dot.classList.add('d-none');

        const bellBody = document.getElementById('bell-notif-list');
        if (!bellBody) return;

        bellBody.innerHTML = '';

        const unreadList = notifications.filter(n => !n.is_read).slice(0, 6);
        const displayList = unreadList.length > 0 ? unreadList : notifications.slice(0, 6);

        // Update unread badge in header
        const unreadBadge = document.getElementById('bell-unread-badge');
        if (unreadBadge) {
            if (unread > 0) {
                unreadBadge.textContent = unread > 99 ? '99+' : unread;
                unreadBadge.classList.remove('d-none');
            } else {
                unreadBadge.classList.add('d-none');
            }
        }

        if (displayList.length === 0) {
            bellBody.innerHTML = `<div class="p-3 text-center"><i class="bi bi-bell-slash text-muted" style="font-size:1.5rem;"></i><p class="text-muted small mb-0 mt-2">No notifications yet.</p></div>`;
            return;
        }

        // Helper: parse [Module] prefix
        const _parseBellTitle = (rawTitle) => {
            const match = (rawTitle || '').match(/^\[([^\]]+)\]\s*(.*)$/);
            if (match) return { module: match[1], title: match[2] };
            return { module: null, title: rawTitle || 'Notification' };
        };

        // Helper: get redirect URL from module/title
        const _getBellRedirect = (module, rawTitle) => {
            const m = (module || '').toLowerCase();
            const t = (rawTitle || '').toLowerCase();
            if (m === 'issue' || m === 'critical' || t.includes('issue')) return 'issues.html';
            if (m === 'leave' || t.includes('leave')) return 'leaves.html';
            if (m === 'meeting' || m === 'reminder' || t.includes('meeting')) return 'meetings.html';
            if (m === 'salary' || t.includes('salary')) return 'salary.html';
            if (m === 'incentive' || t.includes('incentive')) return 'incentives.html';
            if (m === 'project' || t.includes('project')) return 'projects.html';
            if (m === 'task' || t.includes('task')) return 'todo.html';
            if (m === 'feedback' || t.includes('feedback')) return 'feedback.html';
            if (m === 'demo' || t.includes('demo')) return 'projects_demo.html';
            return 'notifications.html';
        };

        // Helper: icon and color per module
        const _getBellIcon = (module) => {
            const m = (module || '').toLowerCase();
            if (m === 'issue' || m === 'critical') return { icon: 'bi-exclamation-triangle-fill', color: '#ef4444' };
            if (m === 'leave') return { icon: 'bi-calendar-x-fill', color: '#0ea5e9' };
            if (m === 'meeting' || m === 'reminder') return { icon: 'bi-calendar-event-fill', color: '#f59e0b' };
            if (m === 'salary') return { icon: 'bi-cash-stack', color: '#22c55e' };
            if (m === 'incentive') return { icon: 'bi-award-fill', color: '#f59e0b' };
            if (m === 'project') return { icon: 'bi-briefcase-fill', color: '#3b82f6' };
            if (m === 'task') return { icon: 'bi-check2-square', color: '#6b7280' };
            if (m === 'feedback') return { icon: 'bi-chat-square-text-fill', color: '#06b6d4' };
            return { icon: 'bi-bell-fill', color: '#3b82f6' };
        };

        bellBody.innerHTML = displayList.map(n => {
            try {
                const { module, title } = _parseBellTitle(n.title);
                const redirectUrl = _getBellRedirect(module, n.title);
                const { icon, color } = _getBellIcon(module);

                let timeStr = n.created_at;
                if (timeStr && typeof timeStr === 'string') {
                    if (!timeStr.endsWith('Z') && !timeStr.includes('+')) timeStr += 'Z';
                } else timeStr = new Date().toISOString();
                const dateObj = new Date(timeStr);

                let cleanMessage = n.message || "";
                let meetLink = null;
                let meetingId = null;
                let sessionClosed = false;

                if (cleanMessage.includes('STATUS:COMPLETED')) {
                    sessionClosed = true;
                    cleanMessage = cleanMessage.replace('STATUS:COMPLETED', '').trim();
                }

                // [START] - Standardized Link/Meeting ID Parsing
                if (cleanMessage.includes('MEETING_ID:')) {
                    const parts = cleanMessage.split('MEETING_ID:');
                    cleanMessage = parts[0].trim();
                    const rest = (parts[1] || '').split('\n');
                    meetingId = rest[0].trim();
                    // Check for JOIN_MEET: or LINK: after MEETING_ID
                    const linkMatch = (parts[1] || '').match(/(?:JOIN_MEET:|LINK:)(\S+)/);
                    if (linkMatch) meetLink = linkMatch[1];
                } else if (cleanMessage.includes('JOIN_MEET:')) {
                    const parts = cleanMessage.split('JOIN_MEET:');
                    cleanMessage = parts[0].trim();
                    meetLink = parts[1].trim().split('\n')[0];
                } else if (cleanMessage.includes('LINK:')) {
                    const parts = cleanMessage.split('LINK:');
                    cleanMessage = parts[0].trim();
                    meetLink = parts[1].trim().split('\n')[0];
                }
                // [END]

                // Override redirect for meeting with ID
                let finalRedirect = meetingId ? `meetings.html?id=${meetingId}` : redirectUrl;
                showBrowserNotification(n.id, title, cleanMessage, meetLink || finalRedirect);


                // Module badge
                const modBadge = module ? `<span style="font-size:9px; font-weight:700; letter-spacing:0.03em; color:${color}; background: ${color}18; padding: 1px 6px; border-radius: 4px;">${module.toUpperCase()}</span>` : '';

                // Action button
                let actionBtn = '';
                if (meetLink && !sessionClosed)
                    actionBtn = `<a href="${meetLink}" target="_blank" onclick="event.stopPropagation()" class="btn btn-primary d-inline-flex align-items-center gap-1 mt-1" style="font-size:10px; padding: 2px 8px; border-radius:6px; font-weight:700;"><i class="bi bi-camera-video-fill"></i> Join</a>`;
                else if (meetingId && !sessionClosed)
                    actionBtn = `<a href="meetings.html?id=${meetingId}" onclick="event.stopPropagation()" class="btn btn-primary d-inline-flex align-items-center gap-1 mt-1" style="font-size:10px; padding: 2px 8px; border-radius:6px; font-weight:700;"><i class="bi bi-calendar-check"></i> Join</a>`;
                else if (finalRedirect !== 'notifications.html')
                    actionBtn = `<a href="${finalRedirect}" onclick="event.stopPropagation()" class="text-decoration-none mt-1 d-inline-block" style="font-size:10px; font-weight:600; color: var(--primary);">View &rarr;</a>`;

                // BUG 3 FIX: Only apply blue highlight to truly unread items
                const rowBg = n.is_read ? '' : 'bg-primary-subtle';

                return `
                <div class="d-flex gap-2 px-3 py-2 border-bottom ${!n.is_read ? 'bg-primary-subtle' : ''}" style="cursor:pointer;" onclick="window.location.href='${finalRedirect}'">
                    <div class="d-flex align-items-center justify-content-center flex-shrink-0 rounded-circle" style="width:30px; height:30px; min-width:30px; background:${color}18;">
                        <i class="bi ${icon}" style="font-size:13px; color:${color};"></i>
                    </div>
                    <div class="w-100 overflow-hidden">
                        <div class="d-flex align-items-center gap-1 flex-wrap mb-1">${modBadge}<span class="fw-bold text-truncate" style="font-size:.82rem; color: var(--text-1);">${title}</span></div>
                        <div class="text-secondary" style="font-size:.78rem; line-height:1.35; word-break:break-word;">${cleanMessage.length > 80 ? cleanMessage.slice(0, 80) + '…' : cleanMessage}${sessionClosed ? '<br><span class="badge text-bg-secondary mt-1" style="font-size:9px;">Session Ended</span>' : ''}</div>
                        <div class="d-flex align-items-center gap-2">
                            ${actionBtn}
                            <span class="text-muted ms-auto" style="font-size:.65rem; white-space:nowrap;">${dateObj.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true })}</span>
                        </div>
                    </div>
                </div>`;
            } catch (err) { return ""; }
        }).join('');
    } catch (e) { console.error(e); }
};

window._shownPushes = window._shownPushes || new Set();

window.showBrowserNotification = function (notifId, title, bodyStr, link) {
    if (window._shownPushes.has(notifId) || !('Notification' in window)) return;
    window._shownPushes.add(notifId);
    if (Notification.permission === 'granted') {
        const popup = new Notification(title, { body: bodyStr });
        popup.onclick = () => { link ? window.open(link, '_blank') : window.location.href = 'notifications.html'; popup.close(); };
    }
}

window.startNotificationPolling = function () {
    if (window._notifPollStarted) return;
    window._notifPollStarted = true;
    if ('Notification' in window && Notification.permission === 'default') Notification.requestPermission();
    window.refreshBell();
    setInterval(window.refreshBell, 30000);
}

// ─── Global Live Search Logic ───
window.initLiveSearch = function () {
    const input = document.getElementById('global-search-input');
    const dropdown = document.getElementById('live-search-dropdown');
    if (!input || !dropdown) return;

    let debounceTimer;

    // Icons for different models
    const typeIcons = {
        client: '<i class="bi bi-person text-info"></i>',
        issue: '<i class="bi bi-exclamation-triangle text-warning"></i>',
        project: '<i class="bi bi-kanban text-primary"></i>',
        employee: '<i class="bi bi-person-badge text-secondary"></i>',
        lead: '<i class="bi bi-kanban text-danger"></i>',
        payment: '<i class="bi bi-receipt text-success"></i>',
        area: '<i class="bi bi-geo-alt" style="color:#6366f1;"></i>',
        meeting: '<i class="bi bi-calendar-event text-success"></i>'
    };

    // Base paths for redirection
    const typeLinks = {
        client: 'clients.html?id=',
        issue: 'issues.html?id=',
        project: 'projects.html?id=',
        employee: 'admin.html', // simplified for now
        lead: 'leads.html?id=',
        payment: 'clients.html', // payments don't have dedicated view page yet
        area: 'areas.html?id=',
        meeting: 'meetings.html?id='
    };

    input.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const query = e.target.value.trim();

        if (query.length < 2) {
            dropdown.classList.remove('show');
            return; // Too short to search
        }

        debounceTimer = setTimeout(async () => {
            try {
                // Ensure apiGet is globally available (from api.js)
                const res = await apiGet(`/search/?q=${encodeURIComponent(query)}`);

                let html = '';
                let hasResults = false;

                // Simple helper to highlight matched text (case-insensitive)
                const highlight = (text) => {
                    if (!text) return '';
                    const strText = String(text);
                    const regex = new RegExp(`(${query})`, 'gi');
                    return strText.replace(regex, '<span class="search-highlight">$1</span>');
                };

                for (const [category, items] of Object.entries(res)) {
                    if (items && items.length > 0) {
                        hasResults = true;
                        const catLabel = category.charAt(0).toUpperCase() + category.slice(1);
                        html += `<div class="search-section-header">${catLabel}</div>`;

                        items.forEach(item => {
                            const icon = typeIcons[item.type] || '<i class="bi bi-search py-1"></i>';
                            const link = typeLinks[item.type] ? typeLinks[item.type] + item.id : 'search.html?q=' + encodeURIComponent(query);

                            html += `
                                <a href="${link}" class="search-result-item">
                                    <div class="search-result-icon">${icon}</div>
                                    <div class="search-result-info">
                                        <div class="search-result-name">${highlight(item.name || 'Unknown')}</div>
                                        <div class="search-result-sub">${highlight(item.subtext || '')}</div>
                                    </div>
                                </a>
                            `;
                        });
                    }
                }

                if (!hasResults) {
                    html = `<div class="p-3 text-center text-muted small">No results found for "${query}"</div>`;
                }

                dropdown.innerHTML = html;
                dropdown.classList.add('show');
            } catch (err) {
                console.error("Live search failed", err);
            }
        }, 300); // 300ms debounce
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.classList.remove('show');
        }
    });

    // Re-open if clicking back on input with value
    input.addEventListener('focus', () => {
        if (input.value.trim().length >= 2 && dropdown.innerHTML.trim() !== '') {
            dropdown.classList.add('show');
        }
    });
};



window.checkHighPriorityIssues = async function () {
    // Tokens are always stored in localStorage (not sessionStorage)
    if (!localStorage.getItem('access_token')) return;
    try {
        const issues = await apiGet('/issues/');
        // Only count issues that are NOT resolved/cancelled — red only when unsolved
        const unreadHigh = (Array.isArray(issues) ? issues : []).filter(i => i.severity === 'HIGH' && !['RESOLVED', 'CANCELLED'].includes(i.status));

        // Store for sidebar badge
        const oldCount = sessionStorage.getItem('crm_high_issue_count');
        sessionStorage.setItem('crm_high_issue_count', unreadHigh.length);

        // If count changed, re-render sidebar to update badges & dot
        if (oldCount !== String(unreadHigh.length) && window.renderSidebar && window.__lastSidebarActive) {
            // #sidebar is the wrapper div; renderSidebar() produces #sidebar-container inside it
            const sb = document.getElementById('sidebar');
            if (sb) {
                sb.innerHTML = window.renderSidebar(window.__lastSidebarActive);
            }
        }

        const alertContainerId = 'high-priority-global-alert';
        let alertEl = document.getElementById(alertContainerId);

        if (unreadHigh.length > 0) {
            // ── Top banner: show only once per session (until user dismisses or logs out) ──
            if (!alertEl && sessionStorage.getItem('high_issue_alert_dismissed') !== '1') {
                const html = `
                <div id="${alertContainerId}" class="d-flex align-items-center justify-content-between py-2 px-4 mb-0" style="background-color: #B91C1C; color: white; z-index: 1050; font-size: 0.85rem; font-weight: 600; flex-shrink: 0; flex-grow: 0; height: auto; min-height: unset; max-height: 44px; overflow: hidden; width: 100%;">
                    <div class="d-flex align-items-center gap-2">
                        <i class="bi bi-exclamation-triangle-fill"></i>
                        <span>System Alert: ${unreadHigh.length} Unresolved High Priority Issue(s) detected.</span>
                    </div>
                    <div class="d-flex align-items-center gap-2">
                        <a href="issues.html" class="btn btn-sm btn-light py-0 px-2 fw-bold" style="font-size: 0.75rem; color: #B91C1C;">View Issues</a>
                        <button type="button" onclick="(function(){ var el=document.getElementById('${alertContainerId}'); if(el) el.remove(); sessionStorage.setItem('high_issue_alert_dismissed','1'); })()" style="background:none;border:none;color:white;font-size:1.1rem;line-height:1;padding:0 2px;cursor:pointer;opacity:0.85;" title="Dismiss">&times;</button>
                    </div>
                </div>`;

                // Insert inside .main-wrapper, before page content (not at body root)
                const mainWrapper = document.querySelector('.main-wrapper');
                if (mainWrapper) {
                    mainWrapper.insertAdjacentHTML('afterbegin', html);
                } else {
                    document.body.insertAdjacentHTML('afterbegin', html);
                }
                alertEl = document.getElementById(alertContainerId);
            } else if (alertEl) {
                alertEl.querySelector('span').textContent = `System Alert: ${unreadHigh.length} Unresolved High Priority Issue(s) detected.`;
            }

            // ── Notification bell: inject high-priority section (always, regardless of banner) ──
            const bellBody = document.getElementById('bell-notif-list');
            if (bellBody && !document.getElementById('bell-high-issues-section')) {
                const highHtml = `
                <div id="bell-high-issues-section">
                    <div class="px-3 py-1" style="background:#7f1d1d; color:#fca5a5; font-size:0.72rem; font-weight:700; letter-spacing:0.04em; text-transform:uppercase;">
                        <i class="bi bi-exclamation-triangle-fill me-1"></i> High Priority Issues
                    </div>
                    ${unreadHigh.slice(0, 3).map(i => `
                    <a href="issues.html" class="d-flex gap-2 px-3 py-2 border-bottom text-decoration-none" style="background:#fff1f2;">
                        <div class="w-100 overflow-hidden">
                            <div class="fw-bold text-truncate" style="font-size:.82rem; color:#b91c1c;">${i.title || 'Untitled Issue'}</div>
                            <div class="text-muted small mt-1" style="font-size:.72rem; line-height:1.3;">${i.description ? i.description.slice(0, 60) + (i.description.length > 60 ? '…' : '') : ''}</div>
                        </div>
                    </a>`).join('')}
                    ${unreadHigh.length > 3 ? `<div class="px-3 py-1 text-center" style="font-size:.75rem;"><a href="issues.html" style="color:#b91c1c; font-weight:600;">+${unreadHigh.length - 3} more high-priority issue(s)</a></div>` : ''}
                </div>`;
                bellBody.insertAdjacentHTML('afterbegin', highHtml);

                // Always show red dot on bell when high issues exist
                const dot = document.getElementById('nav-notif-dot');
                if (dot) dot.classList.remove('d-none');
            }
        } else {
            if (alertEl) {
                alertEl.remove();
                const topHeader = document.querySelector('.top-header');
                if (topHeader) topHeader.style.top = '0';
                const sidebar = document.getElementById('sidebar-container');
                if (sidebar) {
                    sidebar.style.height = '100vh';
                    sidebar.style.top = '0';
                }
            }
            // Remove bell section if it exists
            const bellHigh = document.getElementById('bell-high-issues-section');
            if (bellHigh) bellHigh.remove();

            sessionStorage.removeItem('crm_high_issue_count');
        }
    } catch (e) {
        console.error("High Priority check failed", e);
    }
};

/**
 * Renders a unified filter panel based on a configuration object.
 * @param {Object} config - The configuration for the filter panel.
 * @param {string} config.containerId - The ID of the element where the panel will be rendered.
 * @param {Array} config.filters - Array of filter definitions.
 * @param {string} config.title - Optional title (default: 'Filters').
 * @param {Function} config.onApply - Callback function called with filter data.
 * @param {Function} config.onReset - Callback function called when filters are cleared.
 */
window.renderFilterPanel = function (config) {
    const { containerId, filters, title = 'Filters', onApply, onReset, headerContent = '' } = config;
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`Filter container #${containerId} not found.`);
        return;
    }

    // Generate Filter Fields HTML
    const fieldsHtml = filters.map(f => {
        let inputHtml = '';
        if (f.type === 'select') {
            inputHtml = `
                <select id="${f.id}" class="form-select">
                    ${(f.options || []).map(opt => `<option value="${opt.value}" ${opt.selected ? 'selected' : ''}>${opt.label}</option>`).join('')}
                </select>`;
        } else if (f.type === 'date' || f.type === 'month') {
            inputHtml = `<input type="${f.type}" id="${f.id}" class="form-control" value="${f.value || ''}">`;
        } else { // Default to text input for 'text' and any other unspecified types
            inputHtml = `<input type="text" id="${f.id}" class="form-control" placeholder="${f.placeholder || ''}" value="${f.value || ''}">`;
        }

        return `
            <div class="filter-field">
                <label for="${f.id}" class="filter-label">${f.label}</label>
                <div class="filter-input-wrapper">
                    ${inputHtml}
                </div>
            </div>`;
    }).join('');

    const html = `
        <div class="filter-panel">
            <div class="filter-panel-head" onclick="this.nextElementSibling.classList.toggle('open'); this.querySelector('.filter-toggle-btn').classList.toggle('open')">
                <div class="filter-panel-head-left">
                    <i class="bi bi-filter"></i>
                    <span>${title}</span>
                </div>
                <div class="filter-active-pills" id="${containerId}-pills"></div>
                ${headerContent}
                <div class="filter-panel-head-right">
                    <span class="filter-summary-text" id="${containerId}-summary">No filters active</span>
                    <button class="filter-toggle-btn" type="button" onclick="event.stopPropagation(); this.closest('.filter-panel-head').nextElementSibling.classList.toggle('open'); this.classList.toggle('open')">
                        <i class="bi bi-chevron-down"></i>
                    </button>
                </div>
            </div>
            <div class="filter-panel-body">
                <div class="filter-grid">
                    ${fieldsHtml}
                </div>
                <div class="filter-actions">
                    <button class="btn-filter-reset" id="${containerId}-reset">
                        <i class="bi bi-x-circle"></i> Clear
                    </button>
                </div>
            </div>
        </div>`;

    container.innerHTML = html;

    const body = container.querySelector('.filter-panel-body');
    const pillsContainer = container.querySelector(`#${containerId}-pills`);
    const summaryText = container.querySelector(`#${containerId}-summary`);
    const resetBtn = container.querySelector(`#${containerId}-reset`);

    const updateUI = () => {
        const activeFilters = [];
        filters.forEach(f => {
            const el = document.getElementById(f.id);
            if (!el) return;
            const val = el.value;
            // Only consider as active if it's not empty or "ALL"
            if (val && val.toUpperCase() !== 'ALL' && val !== '') {
                let displayVal = val;
                if (f.type === 'select') {
                    const opt = f.options.find(o => o.value === val);
                    if (opt) displayVal = opt.label;
                }
                activeFilters.push({ id: f.id, label: f.label, value: displayVal });
            }
        });

        pillsContainer.innerHTML = activeFilters.map(af => `
            <div class="filter-pill">
                ${af.label}: ${af.value}
                <button class="filter-pill-remove" onclick="event.stopPropagation(); window.removeFilter('${containerId}', '${af.id}')">
                    <i class="bi bi-x"></i>
                </button>
            </div>`).join('');

        summaryText.textContent = activeFilters.length > 0
            ? `${activeFilters.length} filter${activeFilters.length > 1 ? 's' : ''} active`
            : 'No filters active';
    };

    const triggerApply = () => {
        const data = {};
        filters.forEach(f => {
            const el = document.getElementById(f.id);
            if (el) data[f.id.replace('filter-', '').replace('f-', '')] = el.value;
        });
        updateUI();
        if (onApply) onApply(data);
    };

    // Auto-apply on change
    filters.forEach(f => {
        const el = document.getElementById(f.id);
        if (el) {
            el.addEventListener('change', triggerApply);
            // also listen to input for text fields if user types (we could debounce, but change is fine for enter/blur)
            if (f.type !== 'select' && f.type !== 'date' && f.type !== 'month') {
                el.addEventListener('change', triggerApply);
            }
        }
    });

    // Global helper for pill removal
    window.removeFilter = (cid, fid) => {
        const el = document.getElementById(fid);
        if (el) {
            const filterDef = filters.find(f => f.id === fid);
            if (filterDef && filterDef.type === 'select') {
                el.value = filterDef.options[0]?.value || 'ALL';
            } else {
                el.value = '';
            }
            triggerApply();
        }
    };

    resetBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        filters.forEach(f => {
            const el = document.getElementById(f.id);
            if (el) {
                if (f.type === 'select') {
                    // Try to find 'ALL' or '' or use first option
                    const hasAll = f.options.some(o => o.value === 'ALL');
                    const hasEmpty = f.options.some(o => o.value === '');
                    if (hasAll) el.value = 'ALL';
                    else if (hasEmpty) el.value = '';
                    else el.value = f.options[0]?.value;
                } else {
                    el.value = '';
                }
            }
        });
        updateUI();
        body.classList.remove('open');
        container.querySelector('.filter-toggle-btn').classList.remove('open');
        if (onReset) onReset();
        triggerApply();
    });

    // Initial UI update - ensure closed by default
    updateUI();
    body.classList.remove('open');
    container.querySelector('.filter-toggle-btn').classList.remove('open');
};

// Start both polls
window.startAllPolling = function () {
    startNotificationPolling();
    // Run immediately on page load, then every 30s
    window.checkHighPriorityIssues();
    setInterval(window.checkHighPriorityIssues, 30000);
};

// ─── Dark Mode ────────────────────────────────────────────────
; (function applyInitialTheme() {
    let saved = localStorage.getItem('srm-theme');
    // Default to dark theme for consistency with redesign if no preference is set
    if (!saved) {
        saved = 'dark';
        localStorage.setItem('srm-theme', 'dark');
    }

    if (saved === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
    }
})();

// ─── Header & Context ────────────────────────────────────────────────
window.updateHeaderContext = function () {
    const u = typeof getUser === 'function' ? getUser() : (window.ApiClient ? window.ApiClient.getCurrentUser() : null);
    if (!u) return;

    // 1. Update Top Navigation (initially set by injectTopHeader, but here for sync)
    const nameEls = document.querySelectorAll('.nav-uname');
    nameEls.forEach(el => el.textContent = u.name || u.username || 'User');

    const firstName = (u.name || u.username || 'User').split(' ')[0];
    const now = new Date();
    const hours = now.getHours();

    // Determine period
    let period = 'night';
    if (hours < 12) period = 'morning';
    else if (hours < 17) period = 'afternoon';
    else if (hours < 21) period = 'evening';

    // 16 Warm & Professional Motivational Greetings - Strictly Professional
    const GREETINGS_DB = {
        morning: [
            { main: "Good Morning", sub: "A fresh day, a clean slate. Let's make progress that matters." },
            { main: "Good Morning", sub: "Your focus today shapes your results tomorrow. Start strong." },
            { main: "Good Morning", sub: "The team is counting on a great day. Let's get to work." },
            { main: "Good Morning", sub: "Set your priorities, stay the course. Today is yours to direct." }
        ],
        afternoon: [
            { main: "Good Afternoon", sub: "The morning was just the warmup. The real work happens now." },
            { main: "Good Afternoon", sub: "Halfway through. Everything you do from here compounds." },
            { main: "Good Afternoon", sub: "Stay focused — the most productive hours are still ahead." },
            { main: "Good Afternoon", sub: "You've built momentum. Keep it going." }
        ],
        evening: [
            { main: "Good Evening", sub: "A strong finish defines the day. You're almost there." },
            { main: "Good Evening", sub: "Wrap up with intention. What you complete today won't wait tomorrow." },
            { main: "Good Evening", sub: "The day's final stretch. Finish what you started." },
            { main: "Good Evening", sub: "Consistency in the final hours is what separates good from great." }
        ],
        night: [
            { main: "Working Late", sub: "Your commitment doesn't go unnoticed. Finish strong and rest well." },
            { main: "Still at It", sub: "Dedication like yours moves the whole team forward." },
            { main: "Late Night Session", sub: "The extra effort you put in tonight will show tomorrow's results." },
            { main: "Good Night", sub: "You've given today everything. Log off knowing it was worth it." }
        ]
    };

    const options = GREETINGS_DB[period];
    const pick = options[Math.floor(Math.random() * options.length)];

    const dateStr = now.toLocaleDateString('en-IN', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

    // Update Premium Header (Commonly used IDs)
    const premiumDateEl = document.getElementById('att-v2-date');
    if (premiumDateEl) premiumDateEl.textContent = dateStr.toUpperCase();

    // Also populate Admin-specific date if it exists
    const adminDateEl = document.getElementById('att-v2-date-admin');
    if (adminDateEl) adminDateEl.textContent = dateStr.toUpperCase();

    const premiumGreetLineEl = document.getElementById('att-v2-greeting-line');
    if (premiumGreetLineEl) {
        // Use innerHTML safely if we want to preserve sub-elements, or just rebuild it
        premiumGreetLineEl.innerHTML = `${pick.main}, <span class="header-name" id="att-v2-left-name">${firstName}</span>`;
    }

    const motivationalEl = document.getElementById('att-v2-motivational-msg');
    if (motivationalEl) {
        motivationalEl.textContent = pick.sub;
    }

    // Fallback for non-premium/Admin greeting IDs
    const greetingIds = ['dash-greeting', 'dash-greeting-v2', 'greetingUser', 'dash-greeting-admin'];
    greetingIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            // Apply the sameHeading + Name logic to fallbacks too if they are meant to be dynamic
            if (el.tagName === 'DIV' || el.tagName === 'H2') {
                el.innerHTML = `${pick.main}, <span class="header-name">${firstName}</span>`;
            } else {
                el.textContent = `${pick.main}, ${firstName}`;
            }
        }
    });

    const subGreetingIds = ['dash-sub-greeting', 'dash-sub-greeting-admin'];
    subGreetingIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = pick.sub;
    });

    const dateIds = ['dash-date', 'dash-date-v2', 'dash-date-header'];
    dateIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = dateStr;
    });

    // 3. Role-based Header Visibility
    // The user specifically requested that the "greeting header" (gradient) stays only on Overview.
    const isOverview = window.location.pathname.includes('dashboard.html');
    const dashHeaders = document.querySelectorAll('.dash-header');

    dashHeaders.forEach(header => {
        if (!isOverview) {
            // In other pages, we can hide it OR keep it but only for staff if it contains the widget
            // Here we just ensure the text is updated if it exists
        }
    });

    // Sync initials if found
    const avatarEls = document.querySelectorAll('.rounded-circle.fw-bold');
    avatarEls.forEach(el => {
        if (el.textContent.length <= 2 && typeof window.getInitials === 'function') {
            el.textContent = window.getInitials(u.name || u.email || 'AD');
        }
    });
};

// ─── Attendance Widget ───────────────────────────────────────────────
window.initAttendance = async function () {
    const widget = document.getElementById('employee-header-widget');
    if (!widget) return Promise.resolve();

    widget.classList.remove('d-none');

    // Hide basic greeting to avoid duplicates
    const basicHeader = document.querySelector('.dash-header-left');
    if (basicHeader) basicHeader.classList.add('d-none');

    const u = window.ApiClient ? window.ApiClient.getCurrentUser() : null;
    if (!u) return Promise.resolve();

    // 1. Greeting & Name are now handled globally by updateHeaderContext()
    // to ensure unique motivational messages are preserved.

    // 2. Populate Right Zone: Avatar + Name
    const nameEl = document.getElementById('att-v2-name');
    const avatarEl = document.getElementById('att-v2-avatar');
    if (nameEl) nameEl.textContent = u.name || 'User';
    if (avatarEl && typeof window.getInitials === 'function') {
        const initials = window.getInitials(u.name || u.email || 'U');
        if (u.photo_url) {
            avatarEl.innerHTML = `<img src="${u.photo_url}" alt="${initials}" onerror="this.parentElement.innerHTML='${initials}'">`;
        } else {
            avatarEl.textContent = initials;
        }
    }

    let status = null;
    try {
        status = await window.ApiClient.getPunchStatus();
    } catch (e) {
        console.error('Failed to get punch status', e);
        return Promise.resolve();
    }

    const updateUI = (s) => {
        const badge = document.getElementById('att-v2-badge');
        const btn = document.getElementById('header-punch-btn-new');
        const hh = document.getElementById('att-v2-hh');
        const mm = document.getElementById('att-v2-mm');
        const ss = document.getElementById('att-v2-ss');
        const firstIn = document.getElementById('att-v2-first-in');
        const liveBadge = document.getElementById('att-v2-live-badge');
        const livePulse = document.getElementById('att-v2-pulse');
        const liveText = document.getElementById('att-v2-live-text');
        const statusDot = document.getElementById('att-v2-status-dot');
        const lNameEl = document.getElementById('att-v2-left-name');

        if (s.is_punched_in) {
            if (badge) { badge.textContent = 'Punched In'; badge.className = 'pro-att-punch-badge in'; }
            if (btn) { btn.innerHTML = 'Punch<br>Out'; btn.className = 'pro-att-btn punch-out'; }
            if (liveBadge) liveBadge.className = 'pro-att-live-badge live';
            if (livePulse) livePulse.style.display = '';
            if (liveText) liveText.textContent = 'Live';
            if (statusDot) statusDot.className = 'pro-att-status-dot online';
            if (lNameEl) lNameEl.className = 'pro-att-name punched-in';
        } else {
            if (badge) { badge.textContent = 'Not Punched'; badge.className = 'pro-att-punch-badge out'; }
            if (btn) { btn.innerHTML = 'Punch<br>In'; btn.className = 'pro-att-btn punch-in'; }
            if (liveBadge) liveBadge.className = 'pro-att-live-badge offline';
            if (livePulse) livePulse.style.display = 'none';
            if (liveText) liveText.textContent = 'Offline';
            if (statusDot) statusDot.className = 'pro-att-status-dot offline';
            if (lNameEl) lNameEl.className = 'pro-att-name punched-out';
        }

        // Punch-in time
        if (firstIn) {
            if (s.first_punch_in) {
                const d = new Date(s.first_punch_in);
                firstIn.textContent = d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: true });
            } else {
                firstIn.textContent = '--:--';
            }
        }

        // Timer Logic: Fixed
        if (window._attTimer) clearInterval(window._attTimer);

        const tick = () => {
            let totalSec = s.completed_hours_secs || 0;
            if (s.is_punched_in && s.last_punch_ts) {
                const elapsed = Math.max(0, (Date.now() - s.last_punch_ts) / 1000);
                totalSec += elapsed;
            }

            const h = Math.floor(totalSec / 3600);
            const m = Math.floor((totalSec % 3600) / 60);
            const sec = Math.floor(totalSec % 60);

            if (hh) hh.textContent = h.toString().padStart(2, '0');
            if (mm) mm.textContent = m.toString().padStart(2, '0');
            if (ss) ss.textContent = sec.toString().padStart(2, '0');
        };

        if (s.is_punched_in || (s.completed_hours_secs > 0)) {
            tick();
            if (s.is_punched_in) {
                window._attTimer = setInterval(tick, 1000);
            }
        } else {
            if (hh) hh.textContent = '--';
            if (mm) mm.textContent = '--';
            if (ss) ss.textContent = '--';
        }

        // FIX 4: Midnight reset — check every 30s if the calendar date has rolled over
        if (window._midnightCheck) clearInterval(window._midnightCheck);
        const _midnightStartDate = new Date().toDateString();
        window._midnightCheck = setInterval(async () => {
            if (new Date().toDateString() !== _midnightStartDate) {
                clearInterval(window._midnightCheck);
                window._midnightCheck = null;
                if (window._attTimer) {
                    clearInterval(window._attTimer);
                    window._attTimer = null;
                }
                try {
                    const freshStatus = await window.ApiClient.getPunchStatus();
                    updateUI(freshStatus);
                } catch (e) {
                    console.warn('[Attendance] Midnight refresh failed', e);
                }
            }
        }, 30000);
    };

    updateUI(status);

    // 3. Punch Button Action
    const punchBtn = document.getElementById('header-punch-btn-new');
    if (punchBtn) {
        punchBtn.onclick = async () => {
            if (punchBtn.classList.contains('loading')) return;
            punchBtn.classList.add('loading');
            const origHTML = punchBtn.innerHTML;
            punchBtn.textContent = '...';
            try {
                const res = await window.ApiClient.punch();
                if (res && res.requires_manual_punchout) {
                    punchBtn.innerHTML = origHTML;
                    punchBtn.classList.remove('loading');
                    if (typeof window.showManualPunchOutModal === 'function') {
                        window.showManualPunchOutModal(res.open_sessions);
                    }
                    return;
                }
                const newStatus = await window.ApiClient.getPunchStatus();
                updateUI(newStatus);
                if (typeof window.showToast === 'function') {
                    window.showToast(res.message || 'Action successful');
                }
                if (typeof window.refreshDashboardKPIs === 'function') {
                    window.refreshDashboardKPIs();
                }
            } catch (e) {
                console.error('Punch failed', e);
                if (typeof window.showToast === 'function') {
                    window.showToast(e.data?.detail || 'Punch failed', 'error');
                }
                punchBtn.innerHTML = origHTML;
            } finally {
                punchBtn.classList.remove('loading');
            }
        };
    }

    return Promise.resolve();
};



window.showManualPunchOutModal = function (sessions) {
    let modalEl = document.getElementById('manualPunchOutModal');
    if (!modalEl) {
        document.body.insertAdjacentHTML('beforeend', `
            <div class="modal fade" id="manualPunchOutModal" tabindex="-1" aria-labelledby="manualPunchOutModalLabel" aria-hidden="true" data-bs-backdrop="static">
                <div class="modal-dialog modal-dialog-centered">
                    <div class="modal-content border-0 shadow">
                        <div class="modal-header border-bottom-0 pb-0">
                            <h5 class="modal-title fw-bold" id="manualPunchOutModalLabel"><i class="bi bi-exclamation-triangle text-warning me-2"></i> Unclosed Sessions Detected</h5>
                        </div>
                        <div class="modal-body pb-0">
                            <p class="text-muted small">You have open attendance sessions from previous days. You must manually close them before punching in today.</p>
                            <div id="manualPunchOutContainer" class="d-flex flex-column gap-3 mt-3"></div>
                        </div>
                        <div class="modal-footer border-top-0 pt-3">
                            <button type="button" class="btn btn-secondary" data-bs-dismiss="modal">Cancel</button>
                        </div>
                    </div>
                </div>
            </div>
        `);
        modalEl = document.getElementById('manualPunchOutModal');
    }

    const container = document.getElementById('manualPunchOutContainer');
    container.innerHTML = sessions.map(s => {
        const dateStr = window.formatDateToApp ? window.formatDateToApp(s.date) : s.date;
        const timeIn = s.punch_in ? new Date(s.punch_in).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'Unknown';
        return `
            <div class="card p-3 bg-light border-0 shadow-sm">
                <h6 class="fw-bold mb-1">${dateStr}</h6>
                <p class="mb-2 small text-muted">Started: ${timeIn}</p>
                <div class="input-group input-group-sm">
                    <span class="input-group-text bg-white">Out Time</span>
                    <input type="time" class="form-control" id="punch_out_${s.id}" value="23:59" required>
                    <button class="btn btn-primary fw-bold" onclick="window.submitManualPunchOut('${s.id}')">Close Session</button>
                </div>
                <p class="mt-2 mb-0 xsmall text-info-emphasis"><i class="bi bi-info-circle me-1"></i> Sessions are capped at 11:59 PM. Time after midnight counts for the next day.</p>
            </div>
        `;
    }).join('');

    const modal = new bootstrap.Modal(modalEl);
    modal.show();

    window.submitManualPunchOut = async (recordId) => {
        const timeInput = document.getElementById(`punch_out_${recordId}`).value;
        if (!timeInput) {
            window.showToast('Please select a punch-out time', 'warning');
            return;
        }
        try {
            await window.ApiClient.manualPunchOut(recordId, timeInput);
            window.showToast('Session closed manually', 'success');
            modal.hide();
            // Automatically attempt to punch in again if that was the only session
            setTimeout(() => {
                const btn = document.getElementById('header-punch-btn-new');
                if (btn) btn.click();
            }, 500);
        } catch (e) {
            console.error('Manual punch out failed', e);
            window.showToast(e.data?.detail || 'Failed to close session', 'error');
        }
    };
};

// Fetch reset requests count for sidebar badge
window.refreshResetBadge = async function () {
    const u = getUser();
    if (u?.role !== 'ADMIN') return;
    try {
        const requests = await apiGet('/auth/reset-requests');
        const pendingCount = requests.filter(r => r.status === 'PENDING').length;
        const old = sessionStorage.getItem('crm_reset_req_count');
        sessionStorage.setItem('crm_reset_req_count', pendingCount);

        if (String(old) !== String(pendingCount)) {
            // Re-render sidebar if count changed to update dot/badge
            const sbInput = document.getElementById('sidebar');
            if (sbInput && window.__lastSidebarActive) {
                sbInput.innerHTML = renderSidebar(window.__lastSidebarActive);
            }
        }
    } catch (e) {
        console.warn("Failed to refresh reset badge", e);
    }
};

// Start polling for resets
setInterval(refreshResetBadge, 300000); // 5 mins
setTimeout(refreshResetBadge, 2000);   // Initial delay

window.setTheme = function (mode) {
    let applyDark = false;
    if (mode === 'dark') {
        applyDark = true;
    } else if (mode === 'system') {
        applyDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    }

    if (applyDark) {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('srm-theme', 'dark');
        localStorage.setItem('srm_setting_theme', 'dark');
    } else {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('srm-theme', 'light');
        localStorage.setItem('srm_setting_theme', 'light');
    }

    const icon = document.getElementById('dark-mode-icon');
    if (icon) {
        icon.className = applyDark ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
};

window.toggleDarkMode = function () {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const newMode = isDark ? 'light' : 'dark';
    window.setTheme(newMode);

    const themeSelect = document.getElementById('theme-select');
    if (themeSelect) {
        themeSelect.value = newMode;
        if (typeof saveSetting === 'function') {
            saveSetting('theme', newMode);
        }
    } else {
        localStorage.setItem('srm-theme', newMode);
        localStorage.setItem('srm_setting_theme', newMode);
    }
};

// Sync icon with current mode on load (after header injection)
document.addEventListener('DOMContentLoaded', function () {
    const icon = document.getElementById('dark-mode-icon');
    if (icon) {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        icon.className = isDark ? 'bi bi-sun-fill' : 'bi bi-moon-fill';
    }
});

// ─── ACCESS CONTROL OVERLAY ──────────────────────────────────────────
window.checkPageAccess = function () {
    return; // DEPRECATED: Defer to auth.js window.enforceRoleAccess()
    const u = getUser();
    if (!u) return; // Not logged in yet

    // Skip check for basic pages
    const path = window.location.pathname.split('/').pop() || 'index.html';
    if (['index.html', 'login.html', 'dashboard.html', 'profile.html', 'notifications.html', 'search.html', 'employees.html'].includes(path)) {
        return;
    }
    const roleName = String(u.role || '').toUpperCase();
    if (roleName === 'ADMIN') return; // Admins see everything

    const effectivePolicy = window.__crmEffectiveAccessPolicy || JSON.parse(sessionStorage.getItem('crm_access_policy') || 'null');
    const allowedPages = Array.isArray(effectivePolicy?.allowed_pages)
        ? effectivePolicy.allowed_pages
        : (effectivePolicy?.policy?.page_access?.[roleName] || []);

    if (!allowedPages.includes(path) && !allowedPages.includes('*')) {
        if (path === 'salary_slip_view.html') {
            return;
        }
        showAccessDenied(path);
    }
};

window.showAccessDenied = function (pageName) {
    // Remove existing content to prevent interaction
    const mainWrapper = document.querySelector('.main-wrapper');
    if (!mainWrapper) return;

    const nicePageName = pageName.replace('.html', '').replace(/_/g, ' ').toUpperCase();

    mainWrapper.innerHTML = `
        <div class="d-flex flex-column align-items-center justify-content-center text-center p-5" style="min-height: 80vh;">
            <div class="mb-4" style="width: 120px; height: 120px; background: rgba(239, 68, 68, 0.1); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: #ef4444; font-size: 50px;">
                <i class="bi bi-shield-lock"></i>
            </div>
            <h1 class="fw-bold mb-2" style="font-family: 'Outfit', sans-serif; color: var(--text-1);">Access Restricted</h1>
            <p class="text-muted mb-4" style="max-width: 450px;">
                You don't have enough permission to access the <strong>${nicePageName}</strong> module. 
                Please contact your supervisor or administrator if you believe this is an error.
            </p>
            <div class="d-flex gap-3">
                <a href="dashboard.html" class="btn btn-primary px-4 py-2" style="border-radius: 10px; font-weight: 600;">
                    <i class="bi bi-house me-2"></i> Back to Dashboard
                </a>
                <button onclick="window.location.reload()" class="btn btn-outline-secondary px-4 py-2" style="border-radius: 10px; font-weight: 600;">
                    <i class="bi bi-arrow-clockwise me-2"></i> Retry
                </button>
            </div>
            <div class="mt-5 pt-4 border-top w-100" style="max-width: 400px; opacity: 0.6; font-size: 0.8rem;">
                <p class="mb-1">Access Policy: <strong>${getUser()?.role || 'Guest'}</strong></p>
                <p>Module ID: <code>${pageName}</code></p>
            </div>
        </div>
    `;

    // Also remove the "Add New" button if present
    const addBtn = document.querySelector('.nav-add');
    if (addBtn) addBtn.style.display = 'none';
};

// ── TOAST FAILSAFE ────────────────────────────────────────────────────
if (typeof window.showToast !== 'function') {
    window.showToast = function (msg, type) {
        if (typeof toast === 'function') {
            toast(msg, type);
        } else {
            console.warn("showToast fallback triggered for: " + msg);
            alert(msg);
        }
    };
}

// ── UNIVERSAL PAGINATION ───────────────────────────────────────────────
/**
 * Renders paginated data into a tbody and injects a pagination bar.
 *
 * @param {Object} options
 * @param {Array}    options.data          - Full data array to paginate
 * @param {number}   options.pageSize      - Rows per page (default: 15)
 * @param {string}   options.tbodyId       - ID of the <tbody> to render rows into
 * @param {string}   options.paginationId  - ID of the container for pagination controls
 * @param {Function} options.renderRow     - Function(item) => HTML string for a <tr>
 * @param {Array}    [options.targets]     - Optional: array of { id, renderRow, emptyMsg }
 * @param {string}   [options.emptyMsg]    - HTML for the "no data" state
 * @param {number}   [options.colSpan]     - colspan for empty/loading rows (default: 10)
 * @param {number}   [options.currentPage] - Page to jump to (1-indexed, default: 1)
 * @returns {Object} { goToPage, getCurrentPage } — controller object
 */
window.renderPagination = function (options) {
    const {
        data = [],
        pageSize: explicitPageSize,
        tbodyId,
        paginationId,
        renderRow,
        targets,
        emptyMsg = '<tr><td colspan="10" class="text-center py-5 text-muted">No data found.</td></tr>',
        colSpan = 10,
        currentPage: startPage = 1,
    } = options;

    // Prioritize explicit pageSize, then user setting, then default (10)
    const userPageSize = parseInt(localStorage.getItem('srm_setting_pagination_limit'));
    const pageSize = explicitPageSize || userPageSize || 10;

    const paginationContainer = document.getElementById(paginationId);

    let currentPage = Math.max(1, startPage);
    const totalPages = Math.max(1, Math.ceil(data.length / pageSize));

    function renderPage(page) {
        currentPage = Math.min(Math.max(1, page), totalPages);
        const start = (currentPage - 1) * pageSize;
        const slice = data.slice(start, start + pageSize);

        const renderToTarget = (tid, rRow, eMsg) => {
            const el = document.getElementById(tid);
            if (!el) return;
            if (data.length === 0) {
                el.innerHTML = eMsg || emptyMsg;
            } else {
                try {
                    el.innerHTML = slice.map((item, index) => {
                        try {
                            return rRow(item);
                        } catch (err) {
                            console.error(`[Pagination] Row render failed for index ${index}:`, err);
                            return `<tr class="table-danger text-center"><td colspan="20">Error rendering record: ${err.message}</td></tr>`;
                        }
                    }).join('');
                } catch (containerErr) {
                    console.error("[Pagination] Target container update failed:", containerErr);
                    el.innerHTML = `<tr class="table-warning text-center"><td colspan="20">Could not render table contents. Check console for details.</td></tr>`;
                }
            }
        };

        if (targets && targets.length > 0) {
            targets.forEach(t => renderToTarget(t.id, t.renderRow, t.emptyMsg));
        } else if (tbodyId && renderRow) {
            renderToTarget(tbodyId, renderRow, emptyMsg);
        }

        if (paginationContainer) {
            renderControls();
        }
    }

    function renderControls() {
        if (totalPages <= 1) {
            paginationContainer.innerHTML = '';
            return;
        }

        const showing = data.length === 0 ? 0 : Math.min(currentPage * pageSize, data.length);
        const from = data.length === 0 ? 0 : (currentPage - 1) * pageSize + 1;

        // Build page number buttons (show at most 5 around current)
        let pages = [];
        const delta = 2;
        const left = Math.max(1, currentPage - delta);
        const right = Math.min(totalPages, currentPage + delta);

        for (let i = left; i <= right; i++) pages.push(i);
        if (left > 2) pages = ['...left', ...pages];
        if (left > 1) pages = [1, ...pages];
        if (right < totalPages - 1) pages = [...pages, '...right'];
        if (right < totalPages) pages = [...pages, totalPages];

        const pageButtons = pages.map(p => {
            if (typeof p === 'string') {
                return `<li class="page-item disabled"><span class="page-link srm-page-ellipsis">…</span></li>`;
            }
            const active = p === currentPage ? 'active' : '';
            return `<li class="page-item ${active}"><button class="page-link srm-page-btn" data-page="${p}">${p}</button></li>`;
        }).join('');

        paginationContainer.innerHTML = `
            <div class="srm-pagination-bar">
                <span class="srm-pagination-info">
                    Showing <strong>${from}–${showing}</strong> of <strong>${data.length}</strong>
                </span>
                <nav aria-label="Table pagination">
                    <ul class="pagination pagination-sm srm-pagination mb-0">
                        <li class="page-item ${currentPage === 1 ? 'disabled' : ''}">
                            <button class="page-link srm-page-btn" data-page="${currentPage - 1}" aria-label="Previous">
                                <i class="bi bi-chevron-left"></i>
                            </button>
                        </li>
                        ${pageButtons}
                        <li class="page-item ${currentPage === totalPages ? 'disabled' : ''}">
                            <button class="page-link srm-page-btn" data-page="${currentPage + 1}" aria-label="Next">
                                <i class="bi bi-chevron-right"></i>
                            </button>
                        </li>
                    </ul>
                </nav>
            </div>`;

        // Wire up click events
        paginationContainer.querySelectorAll('.srm-page-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const p = parseInt(btn.dataset.page, 10);
                if (!isNaN(p) && p >= 1 && p <= totalPages) {
                    renderPage(p);
                    /* 
                    // Scroll to top of containing card — disabled per user request
                    const scrollTargetId = tbodyId || (targets && targets[0] ? targets[0].id : null);
                    if (scrollTargetId) {
                        const targetEl = document.getElementById(scrollTargetId);
                        if (targetEl) {
                            const el = targetEl.closest('.card, .table-responsive, [class*="card"]');
                            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                        }
                    }
                    */
                }
            });
        });
    }

    // First render
    renderPage(currentPage);

    // Return a controller so caller can refresh without re-init
    return {
        goToPage: (p) => renderPage(p),
        getCurrentPage: () => currentPage,
        getTotalPages: () => totalPages,
    };
};

/**
 * SRM Modern Multi-Select Initialization
 * @param {string} elementId - ID of the original <select multiple>
 * @param {object} options - Configuration options
 */
window.initSrmMultiSelect = function (elementId, options = {}) {
    const originalSelect = document.getElementById(elementId);
    if (!originalSelect) return;

    // Remove existing wrapper if already initialized
    const existingWrapper = originalSelect.parentElement.querySelector('.srm-multi-select-container');
    if (existingWrapper) existingWrapper.remove();

    originalSelect.style.display = 'none';

    const container = document.createElement('div');
    container.className = 'srm-multi-select-container';
    container.innerHTML = `
        <div class="srm-multi-select-tags"></div>
        <input type="text" class="srm-multi-select-input" placeholder="${options.placeholder || 'Search employees...'}">
        <div class="srm-multi-select-dropdown"></div>
    `;

    originalSelect.parentElement.appendChild(container);

    const tagsArea = container.querySelector('.srm-multi-select-tags');
    const input = container.querySelector('.srm-multi-select-input');
    const dropdown = container.querySelector('.srm-multi-select-dropdown');

    const updateTags = () => {
        tagsArea.innerHTML = '';
        Array.from(originalSelect.selectedOptions).forEach(opt => {
            if (opt.value === '' || opt.value === 'All Employees') return;
            const tag = document.createElement('span');
            tag.className = 'srm-tag';
            tag.innerHTML = `
                ${opt.text.split('(')[0].trim()}
                <span class="srm-tag-remove" data-value="${opt.value}">&times;</span>
            `;
            tag.querySelector('.srm-tag-remove').onclick = (e) => {
                e.stopPropagation();
                opt.selected = false;
                originalSelect.dispatchEvent(new Event('change'));
                updateTags();
                renderDropdown();
            };
            tagsArea.appendChild(tag);
        });

        // Special tag for All Employees
        const bulkOpt = Array.from(originalSelect.options).find(o => o.value === 'All Employees');
        if (bulkOpt && bulkOpt.selected) {
            const tag = document.createElement('span');
            tag.className = 'srm-tag';
            tag.style.background = 'var(--primary)';
            tag.style.color = 'white';
            tag.innerHTML = `
                 👤 All Employees
                 <span class="srm-tag-remove" data-value="All Employees">&times;</span>
             `;
            tag.querySelector('.srm-tag-remove').onclick = (e) => {
                e.stopPropagation();
                bulkOpt.selected = false;
                // Deselect everyone if All Employees was unchecked? 
                // Actually, let's keep it simple: just uncheck the bulk option.
                originalSelect.dispatchEvent(new Event('change'));
                updateTags();
                renderDropdown();
            };
            tagsArea.prepend(tag);
        }
    };

    const renderDropdown = (filter = '') => {
        const query = filter.toLowerCase();
        dropdown.innerHTML = '';

        Array.from(originalSelect.options).forEach(opt => {
            if (opt.value === '') return;
            if (query && !opt.text.toLowerCase().includes(query)) return;

            const isBulk = opt.value === 'All Employees';
            const isSelected = opt.selected;
            const item = document.createElement('div');
            item.className = `srm-multi-select-item ${isSelected ? 'selected' : ''} ${isBulk ? 'srm-multi-select-bulk' : ''}`;

            const [name, role] = opt.text.split('(');
            item.innerHTML = `
                ${isBulk ? '' : '<div class="srm-checkbox"></div>'}
                <div class="srm-multi-select-item-info">
                    <span class="srm-multi-select-item-name">${name.trim()}</span>
                    ${role ? `<span class="srm-multi-select-item-role">${role.replace(')', '').trim()}</span>` : ''}
                </div>
            `;

            item.onclick = (e) => {
                e.stopPropagation();
                if (isBulk) {
                    const shouldSelect = !opt.selected;
                    Array.from(originalSelect.options).forEach(o => {
                        if (o.value !== '') o.selected = shouldSelect;
                    });
                } else {
                    opt.selected = !opt.selected;
                }
                originalSelect.dispatchEvent(new Event('change'));
                updateTags();
                renderDropdown(input.value);
            };

            dropdown.appendChild(item);
        });
    };

    input.onfocus = () => dropdown.classList.add('show');
    container.onclick = () => {
        input.focus();
        dropdown.classList.add('show');
    };

    input.oninput = (e) => {
        renderDropdown(e.target.value);
    };

    document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) {
            dropdown.classList.remove('show');
            input.value = '';
        }
    });

    // Initial render
    updateTags();
    renderDropdown();

    // Expose a way to refresh if the original select options change dynamically
    container.refresh = () => {
        updateTags();
        renderDropdown();
    };

    return container;
};

