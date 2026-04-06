// frontend/js/notifications.js — v5.0
// SRM AI SETU – Master Notification Feed + High-Priority Issue Section

let _allNotifications = [];
let _currentFilter = 'all'; // 'all' | 'unread'

document.addEventListener('DOMContentLoaded', () => {
    loadNotifications();
    document.getElementById('filter-all')?.addEventListener('click', () => setFilter('all'));
    document.getElementById('filter-unread')?.addEventListener('click', () => setFilter('unread'));
});

function setFilter(type) {
    _currentFilter = type;
    document.getElementById('filter-all')?.classList.toggle('active', type === 'all');
    document.getElementById('filter-unread')?.classList.toggle('active', type === 'unread');
    applyFilter();
}

function applyFilter() {
    const list = _currentFilter === 'unread'
        ? _allNotifications.filter(n => !n.is_read)
        : _allNotifications;

    const listEl = document.getElementById('notif-list');
    if (!listEl) return;

    if (list.length === 0) {
        renderEmptyState(_currentFilter === 'unread' ? 'No unread notifications.' : 'No notifications yet.');
    } else {
        renderNotifications(list);
    }

    const unreadCount = _allNotifications.filter(n => !n.is_read).length;
    const badge = document.getElementById('notif-unread-count');
    if (badge) {
        badge.textContent = unreadCount > 0 ? `${unreadCount} unread` : 'All read';
        badge.className = unreadCount > 0 ? 'badge bg-danger rounded-pill ms-2' : 'badge bg-success rounded-pill ms-2';
    }
}

async function loadNotifications() {
    const listEl = document.getElementById('notif-list');
    if (!listEl) return;

    // Load high-priority issues + regular notifications in parallel
    try {
        const [notifications, issues] = await Promise.allSettled([
            apiGet('/notifications/?limit=500'),
            apiGet('/issues/?severity=HIGH&status=OPEN&limit=50')
        ]);

        // --- High Priority Issues Banner Section ---
        const highIssues = (issues.status === 'fulfilled' && Array.isArray(issues.value)) ? issues.value : [];
        renderHighPrioritySection(highIssues);

        // --- Notifications Section ---
        _allNotifications = (notifications.status === 'fulfilled' && Array.isArray(notifications.value))
            ? notifications.value : [];

        if (_allNotifications.length === 0 && highIssues.length === 0) {
            renderEmptyState();
            return;
        }
        applyFilter();

    } catch (error) {
        console.error('Failed to load notifications:', error);
        listEl.innerHTML = `<div class="text-center py-5">
            <i class="bi bi-exclamation-circle text-danger" style="font-size: 3rem;"></i>
            <p class="text-muted mt-3">Failed to load. Please try again.</p></div>`;
    }
}

// ── High Priority Issues Section (mirrors bell dropdown) ─────────────────
function renderHighPrioritySection(issues) {
    const listEl = document.getElementById('notif-list');
    if (!listEl || issues.length === 0) return;

    const section = `
    <div id="high-priority-notif-section" class="border-bottom">
        <div class="px-4 py-2 d-flex align-items-center gap-2" style="background:#7f1d1d; color:#fca5a5; font-size:0.78rem; font-weight:700; letter-spacing:0.05em;">
            <i class="bi bi-exclamation-triangle-fill"></i>
            HIGH PRIORITY ISSUES — ${issues.length} Unresolved
            <a href="issues.html" class="ms-auto btn btn-sm btn-light py-0 px-3 fw-bold" style="font-size:0.72rem; color:#b91c1c; border-radius:6px;">View All Issues</a>
        </div>
        ${issues.map(i => `
        <a href="issues.html" class="d-flex align-items-start gap-3 px-4 py-3 border-bottom text-decoration-none" style="background:#fff1f2;">
            <div class="d-flex align-items-center justify-content-center rounded-circle flex-shrink-0" style="width:38px;height:38px;background:rgba(239,68,68,0.12);">
                <i class="bi bi-exclamation-triangle-fill" style="color:#ef4444;font-size:14px;"></i>
            </div>
            <div class="flex-grow-1 overflow-hidden">
                <div class="d-flex justify-content-between align-items-center mb-1">
                    <span class="badge rounded-pill border fw-bold" style="font-size:9px;background:rgba(239,68,68,0.1);color:#b91c1c;border-color:rgba(239,68,68,0.2)!important;">HIGH SEVERITY</span>
                    <span class="text-muted" style="font-size:0.72rem;">${formatTimeAgo(i.created_at || i.date)}</span>
                </div>
                <div class="fw-bold" style="font-size:0.88rem; color:#b91c1c;">${i.title || 'Untitled Issue'}</div>
                <div class="text-secondary mt-1" style="font-size:0.8rem; line-height:1.4;">${(i.description || '').slice(0, 120)}${(i.description || '').length > 120 ? '...' : ''}</div>
            </div>
        </a>`).join('')}
    </div>`;

    listEl.insertAdjacentHTML('afterbegin', section);
}

// ── Parse [Module] prefix ────────────────────────────────────────────────
function parseNotifTitle(rawTitle) {
    // Strip old emoji patterns
    const cleaned = (rawTitle || '').replace(/^[⏰🔔📢⚡🚨]+\s*/, '');
    const match = cleaned.match(/^\[([^\]]+)\]\s*(.*)$/);
    if (match) return { module: match[1], title: match[2] };
    return { module: null, title: cleaned || 'Notification' };
}

// ── Parse message payload (LINK:, MEETING_ID:, STATUS:COMPLETED) ────────
function parseMessagePayload(raw) {
    let msg = raw || '';
    let meetLink = null;
    let meetingId = null;
    let sessionClosed = false;

    if (msg.includes('STATUS:COMPLETED')) {
        sessionClosed = true;
        msg = msg.replace('STATUS:COMPLETED', '').trim();
    }
    if (msg.includes('MEETING_ID:')) {
        const parts = msg.split('MEETING_ID:');
        msg = parts[0].trim();
        const rest = parts[1] || '';
        const idPart = rest.split('\n')[0].trim();
        meetingId = idPart;
        // Check if there's also a LINK:
        if (rest.includes('LINK:')) {
            const linkParts = rest.split('LINK:');
            meetLink = linkParts[1].trim().split('\n')[0];
        }
    } else if (msg.includes('LINK:')) {
        const parts = msg.split('LINK:');
        msg = parts[0].trim();
        meetLink = parts[1].trim().split('\n')[0];
    }

    return { cleanMessage: msg.trim(), meetLink, meetingId, sessionClosed };
}

// ── Module → icon / color / redirect mapping ─────────────────────────────
function getModuleMeta(module, rawTitle) {
    const m = (module || '').toLowerCase();
    const t = (rawTitle || '').toLowerCase();

    if (m === 'critical' || t.includes('[critical]')) return { icon: 'bi-exclamation-triangle-fill', bg: 'bg-danger-subtle text-danger', href: 'issues.html' };
    if (m === 'issue') return { icon: 'bi-exclamation-triangle-fill', bg: 'bg-danger-subtle text-danger', href: 'issues.html' };
    if (m === 'alert') return { icon: 'bi-bell-fill', bg: 'bg-warning-subtle text-warning', href: null };
    if (m === 'reminder' || t.includes('meeting')) return { icon: 'bi-calendar-event-fill', bg: 'bg-warning-subtle text-warning', href: 'meetings.html' };
    if (m === 'leave') return { icon: 'bi-calendar-x-fill', bg: 'bg-info-subtle text-info', href: 'leaves.html' };
    if (m === 'salary') return { icon: 'bi-cash-stack', bg: 'bg-success-subtle text-success', href: 'salary.html' };
    if (m === 'incentive') return { icon: 'bi-award-fill', bg: 'bg-warning-subtle text-warning', href: 'incentives.html' };
    if (m === 'feedback') return { icon: 'bi-chat-square-text-fill', bg: 'bg-info-subtle text-info', href: 'feedback.html' };
    if (m === 'project') return { icon: 'bi-briefcase-fill', bg: 'bg-primary-subtle text-primary', href: 'projects.html' };
    if (m === 'task') return { icon: 'bi-check2-square', bg: 'bg-secondary-subtle text-secondary', href: 'todo.html' };
    if (m === 'demo') return { icon: 'bi-play-circle-fill', bg: 'bg-warning-subtle text-warning', href: 'projects_demo.html' };
    return { icon: 'bi-bell-fill', bg: 'bg-primary-subtle text-primary', href: null };
}

// ── Render full notification feed ────────────────────────────────────────
function renderNotifications(notifications) {
    // Preserve the high-priority issues section if already rendered
    const highSection = document.getElementById('high-priority-notif-section');
    const listEl = document.getElementById('notif-list');

    // ── Module → icon badge class mapping (Bootstrap Icons only) ──
    const getIconClass = (module) => {
        const m = (module || '').toLowerCase();
        if (m === 'critical' || m === 'issue')  return { icon: 'bi-exclamation-triangle-fill', cat: 'ni-alert' };
        if (m === 'alert')                       return { icon: 'bi-bell-fill',                 cat: 'ni-alert' };
        if (m === 'reminder' || m === 'meeting') return { icon: 'bi-calendar-event-fill',       cat: 'ni-meeting' };
        if (m === 'leave')                       return { icon: 'bi-calendar-x-fill',           cat: 'ni-leave' };
        if (m === 'salary')                      return { icon: 'bi-cash-stack',                cat: 'ni-salary' };
        if (m === 'incentive')                   return { icon: 'bi-award-fill',                cat: 'ni-meeting' };
        if (m === 'feedback')                    return { icon: 'bi-chat-square-text-fill',     cat: 'ni-feedback' };
        if (m === 'project')                     return { icon: 'bi-briefcase-fill',            cat: 'ni-project' };
        if (m === 'task')                        return { icon: 'bi-check2-square',             cat: 'ni-task' };
        if (m === 'demo')                        return { icon: 'bi-play-circle-fill',          cat: 'ni-meeting' };
        return { icon: 'bi-bell-fill', cat: 'ni-info' };
    };

    // Render cards after the high-priority section
    const cardsHtml = notifications.map(n => {
        const { module, title } = parseNotifTitle(n.title);
        const { cleanMessage, meetLink, meetingId, sessionClosed } = parseMessagePayload(n.message);
        const meta = getModuleMeta(module, n.title);
        const { icon, cat } = getIconClass(module);

        // Determine final redirect URL
        let redirectUrl = meta.href || 'notifications.html';
        if (meetingId) redirectUrl = `meetings.html?id=${meetingId}`;

        // Timestamp
        let timeStr = n.created_at;
        if (timeStr && typeof timeStr === 'string') {
            if (!timeStr.endsWith('Z') && !timeStr.includes('+')) timeStr += 'Z';
        } else timeStr = new Date().toISOString();
        const dateObj = new Date(timeStr);

        const isUnread = !n.is_read;
        const isCritical = module === 'Critical' || module === 'Issue';

        // Card state class
        const cardStateClass = isCritical ? 'nc-critical' : (isUnread ? 'nc-unread' : '');

        // Module badge colors
        const badgeColorMap = {
            'Issue': '#b91c1c', 'Critical': '#b91c1c', 'Reminder': '#92400e',
            'Alert': '#b45309', 'Leave': '#0369a1', 'Salary': '#166534',
            'Project': '#1d4ed8', 'Task': '#374151', 'Feedback': '#0e7490',
            'Incentive': '#92400e', 'Demo': '#92400e'
        };
        const badgeBgMap = {
            'Issue': 'rgba(239,68,68,0.10)', 'Critical': 'rgba(239,68,68,0.10)',
            'Reminder': 'rgba(245,158,11,0.10)', 'Alert': 'rgba(245,158,11,0.10)',
            'Leave': 'rgba(14,165,233,0.10)', 'Salary': 'rgba(34,197,94,0.10)',
            'Project': 'rgba(59,130,246,0.10)', 'Task': 'rgba(107,114,128,0.10)',
            'Feedback': 'rgba(6,182,212,0.10)', 'Incentive': 'rgba(245,158,11,0.10)',
            'Demo': 'rgba(245,158,11,0.10)'
        };
        const badgeColor = module ? (badgeColorMap[module] || '#475569') : null;
        const badgeBg    = module ? (badgeBgMap[module]    || 'rgba(100,116,139,0.08)') : null;
        const moduleBadge = module
            ? `<span class="notif-module-badge" style="background:${badgeBg};color:${badgeColor};">${module.toUpperCase()}</span>`
            : '';

        const newDot = isUnread ? `<span class="notif-unread-dot"></span>` : '';

        // Action button — meeting: "Join Meeting →", others: "View X →"
        let actionBtn = '';
        if (meta.href === 'meetings.html' || meetingId) {
            if (meetLink && !sessionClosed) {
                actionBtn = `<a href="${meetLink}" target="_blank" onclick="event.stopPropagation()" class="notif-action-link na-meeting">
                    <i class="bi bi-camera-video-fill"></i> Join Meeting
                </a>`;
            } else if (!sessionClosed) {
                const meetUrl = meetingId ? `meetings.html?id=${meetingId}` : 'meetings.html';
                actionBtn = `<a href="${meetUrl}" onclick="event.stopPropagation()" class="notif-action-link na-meeting">
                    <i class="bi bi-calendar-check"></i> Join Meeting
                </a>`;
            }
        } else if (meta.href && meta.href !== 'notifications.html') {
            const labels = {
                'issues.html': 'View Issue', 'leaves.html': 'View Leave',
                'salary.html': 'View Salary', 'incentives.html': 'View Incentive',
                'projects.html': 'View Project', 'todo.html': 'View Task',
                'feedback.html': 'View Feedback', 'projects_demo.html': 'View Demo'
            };
            const label = labels[meta.href] || 'View';
            actionBtn = `<a href="${meta.href}" onclick="event.stopPropagation()" class="notif-action-link">
                <i class="bi bi-arrow-right-short"></i> ${label}
            </a>`;
        }

        const sessionBadge = sessionClosed
            ? `<span class="badge bg-secondary ms-2" style="font-size:10px;">Session Ended</span>`
            : '';

        const markReadBtn = isUnread
            ? `<button class="btn p-0 border-0 ms-auto" style="color:var(--text-muted);font-size:0.9rem;" onclick="event.stopPropagation();markSingleAsRead('${n.id}')" title="Mark as read"><i class="bi bi-check2-circle"></i></button>`
            : '';

        return `
        <div class="notif-context-card ${cardStateClass}" onclick="window.location.href='${redirectUrl}'">
            <div class="notif-icon-badge ${cat}">
                <i class="bi ${icon}"></i>
                ${newDot}
            </div>
            <div class="notif-body">
                <div class="notif-meta-row">
                    <div class="d-flex align-items-center gap-2 flex-wrap">
                        ${moduleBadge}
                        <span class="notif-title-text">${title}</span>
                    </div>
                    <div class="d-flex align-items-center gap-2 flex-shrink-0">
                        <span class="notif-time-text">${formatTimeAgo(n.created_at)}</span>
                        ${markReadBtn}
                    </div>
                </div>
                <p class="notif-message-text mb-0">${cleanMessage}</p>
                ${(actionBtn || sessionBadge) ? `<div class="notif-action-row">${actionBtn}${sessionBadge}</div>` : ''}
                <div class="notif-date-full">${dateObj.toLocaleString('en-IN', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit', hour12:true })}</div>
            </div>
        </div>`;
    }).join('');

    // Rebuild: preserve high section, replace rest
    if (highSection) {
        // Remove everything except high section
        const children = Array.from(listEl.children);
        children.forEach(c => { if (c.id !== 'high-priority-notif-section') c.remove(); });
        highSection.insertAdjacentHTML('afterend', cardsHtml);
    } else {
        listEl.innerHTML = cardsHtml;
    }
}

function renderEmptyState(msg = 'All caught up.') {
    const highSection = document.getElementById('high-priority-notif-section');
    if (highSection) return; // Don't overwrite if issues are showing
    const listEl = document.getElementById('notif-list');
    if (listEl) listEl.innerHTML = `
        <div class="text-center py-5">
            <i class="bi bi-bell-slash text-muted" style="font-size:3rem;"></i>
            <p class="text-muted mt-3">${msg}</p>
        </div>`;
}

async function clearNotifications() {
    try {
        await apiPost('/notifications/mark-all-read');
        _allNotifications = _allNotifications.map(n => ({ ...n, is_read: true }));
        applyFilter();
        if (window.refreshBell) window.refreshBell();
        showToast('All notifications marked as read', 'success');
    } catch (error) {
        showToast('Failed to clear notifications', 'error');
    }
}

window.markSingleAsRead = async function (id) {
    // BUG 6 FIX: Only update local state AFTER the API call succeeds.
    // Previously the UI was updated optimistically before the request,
    // causing stale "read" state if the request failed.
    try {
        await apiPatch(`/notifications/${id}/read`);

        // Only mark as read in local state once the server confirmed it
        const notif = _allNotifications.find(n => n.id === id);
        if (notif) notif.is_read = true;
        applyFilter();
        if (window.refreshBell) window.refreshBell();
    } catch (error) {
        showToast('Failed to mark notification as read', 'error');
    }
};

function formatTimeAgo(dateString) {
    if (!dateString) return 'Just now';
    let t = dateString;
    if (typeof t === 'string' && !t.endsWith('Z') && !t.includes('+')) t += 'Z';
    const date = new Date(t);
    const diff = Math.floor((new Date() - date) / 1000);
    if (isNaN(diff) || diff < 0) return 'Just now';
    if (diff < 60) return 'Just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return date.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}