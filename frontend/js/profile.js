/* frontend/js/profile.js */

// Ensure auth is present
if (typeof requireAuth === 'function') requireAuth();

// Initialize sidebar and header
const sidebarElement = document.getElementById('sidebar');
if (sidebarElement && typeof renderSidebar === 'function') {
    sidebarElement.innerHTML = renderSidebar('profile');
}
if (typeof injectTopHeader === 'function') injectTopHeader('Profile');

// Initial load
window.addEventListener('DOMContentLoaded', () => {
    loadProfile();
    initAvatarUpload();
});

/**
 * ── Avatar Upload Logic ─────────────────────────────────────────────────────
 */
function initAvatarUpload() {
    const uploadInput = document.getElementById('avatar-upload');
    const preview = document.getElementById('avatar-preview');
    const avatarImg = document.getElementById('profile-img');
    const avatarInitials = document.getElementById('profile-initials');

    if (!uploadInput) return;

    uploadInput.addEventListener('change', async function(e) {
        const file = e.target.files[0];
        if (!file) return;

        if (!file.type.startsWith('image/')) {
            showToast('Only image files are allowed.', 'error');
            return;
        }

        if (file.size > 2 * 1024 * 1024) { // 2MB limit
            showToast('Image size should be less than 2MB.', 'error');
            return;
        }

        // Preview locally
        const reader = new FileReader();
        reader.onload = function(ev) {
            if (preview) {
                preview.src = ev.target.result;
                preview.style.display = 'block';
            }
        };
        reader.readAsDataURL(file);

        // Upload to backend
        const formData = new FormData();
        formData.append('avatar', file);
        try {
            if (!window.ApiClient) throw new Error('ApiClient not initialized');
            const data = await window.ApiClient.request('/auth/upload-avatar', { 
                method: 'POST', 
                body: formData
            });
            if (data && data.url) {
                if (avatarImg) {
                    avatarImg.src = data.url;
                    avatarImg.style.display = 'block';
                }
                if (avatarInitials) avatarInitials.style.display = 'none';
                if (preview) preview.style.display = 'none';
                
                // Update session
                const stored = JSON.parse(sessionStorage.getItem('srm_user') || '{}');
                stored.profile_img = data.url;
                sessionStorage.setItem('srm_user', JSON.stringify(stored));
                showToast('Avatar updated!');
            }
        } catch (err) {
            showToast('Failed to upload avatar.', 'error');
        }
    });
}

/**
 * ── Load profile data ───────────────────────────────────────────────────────
 */
async function loadProfile() {
    console.log('Profile: Loading started');
    const u = JSON.parse(sessionStorage.getItem('srm_user') || '{}');
    
    try {
        let name = u?.name || u?.email || 'User';
        const rawRole = u?.role || 'USER';
        const roleLabel = rawRole.replace(/_/g, ' ');
        
        // Fetch fresh data
        try {
            const profile = await apiGet('/auth/profile');
            if (profile) {
                Object.assign(u, profile);
                sessionStorage.setItem('srm_user', JSON.stringify(u));
            }
        } catch (e) { 
            console.warn('Profile: Fresh fetch failed, using local data', e); 
        }

        // Update Hero UI
        const initials = window.getInitials(u.name || name);
        const avatarImg = document.getElementById('profile-img');
        const avatarInitials = document.getElementById('profile-initials');
        
        if (u.profile_img) {
            if (avatarImg) {
                avatarImg.src = u.profile_img;
                avatarImg.style.display = 'block';
            }
            if (avatarInitials) avatarInitials.style.display = 'none';
        } else {
            if (avatarImg) avatarImg.style.display = 'none';
            if (avatarInitials) {
                avatarInitials.textContent = initials;
                avatarInitials.style.display = 'block';
            }
        }

        if (document.getElementById('hero-name')) document.getElementById('hero-name').textContent = u.name || name;
        if (document.getElementById('hero-role')) document.getElementById('hero-role').innerHTML = `<i class="bi bi-shield-check"></i> ${roleLabel}`;
        if (document.getElementById('hero-email')) document.getElementById('hero-email').innerHTML = `<i class="bi bi-envelope me-1"></i>${u.email || '—'}`;

        // Pre-fill Form (with existence checks)
        const fields = {
            'edit-name': u.name || '',
            'edit-email': u.email || '',
            'edit-phone': u.phone || '',
            'edit-dept': u.department || roleLabel,
            'edit-summary': u.summary || ''
        };
        for (const [id, val] of Object.entries(fields)) {
            const el = document.getElementById(id);
            if (el) el.value = val;
        }
        
        // Social Links
        if (u.social_links) {
            if (u.social_links.linkedin && document.getElementById('edit-linkedin')) document.getElementById('edit-linkedin').value = u.social_links.linkedin;
            if (u.social_links.twitter && document.getElementById('edit-twitter')) document.getElementById('edit-twitter').value = u.social_links.twitter;
            if (u.social_links.github && document.getElementById('edit-github')) document.getElementById('edit-github').value = u.social_links.github;
        }

        // Account Info Rows
        console.log('Profile: Rendering info and links');
        renderAccountInfo(u, roleLabel);
        renderQuickLinks(u);

    } catch (err) {
        console.error('Profile: Critical error during load', err);
    } finally {
        // Show content regardless of any non-fatal UI errors
        console.log('Profile: Showing content container');
        const content = document.getElementById('profile-content');
        if (content) content.style.display = 'block';
    }
}

/**
 * ── Render Account Info ─────────────────────────────────────────────────────
 */
function renderAccountInfo(u, roleLabel) {
    const container = document.getElementById('account-info-rows');
    if (!container) return;

    const joinedDate = u.joining_date
        ? new Date(u.joining_date).toLocaleDateString('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })
        : '—';
    
    const salaryText = u.base_salary && u.role !== 'ADMIN'
        ? '₹' + Number(u.base_salary).toLocaleString('en-IN')
        : '—';

    const rows = [
        { label: 'Full Name', value: u.name, icon: 'bi-person' },
        { label: 'Email', value: u.email, icon: 'bi-envelope' },
        { label: 'Role', value: `<span class="role-badge" style="font-size:0.7rem;">${roleLabel}</span>`, icon: 'bi-briefcase' },
        { label: 'Department', value: u.department, icon: 'bi-building' },
        { label: 'Employee Code', value: u.employee_code, icon: 'bi-upc-scan' },
        { label: 'Joined', value: joinedDate, icon: 'bi-calendar3' },
        { label: 'Base Salary', value: salaryText, icon: 'bi-cash-stack' },
        { label: 'Phone', value: u.phone, icon: 'bi-telephone' },
        { label: 'User ID', value: `<span class="text-muted">#${u.id || '—'}</span>`, icon: 'bi-hash' }
    ];

    container.innerHTML = rows
        .filter(row => row.value && String(row.value).trim() !== '—' && String(row.value).trim() !== '')
        .map(row => `
            <div class="info-row">
                <span class="info-label"><i class="bi ${row.icon} me-2 text-muted"></i>${row.label}</span>
                <span class="info-value">${row.value}</span>
            </div>
        `).join('');
}

/**
 * ── Render Stats with Links ─────────────────────────────────────────────────
 */
async function renderStats(u) {
    const container = document.getElementById('stats-row');
    if (!container) return;

    try {
        const role = (u.role || '').toUpperCase();
        const isAdmin = role === 'ADMIN';

        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const [tasksRes, visitsRes, projectsRes] = await Promise.allSettled([
            window.ApiClient.getTodos(),
            window.ApiClient.getVisits('?limit=200'),
            window.ApiClient.getProjects('?limit=200')
        ]);

        const tasks = tasksRes.status === 'fulfilled' ? (tasksRes.value || []) : [];
        const openTasks = tasks.filter(t => t.status !== 'COMPLETED').length;
        const visits = visitsRes.status === 'fulfilled' ? (visitsRes.value || []) : [];
        const projects = projectsRes.status === 'fulfilled' ? (projectsRes.value || []) : [];

        let statCards = [];
        if (isAdmin) {
            const stats = await apiGet('/reports/dashboard');
            statCards = [
                { value: stats.total_leads || 0, label: 'Leads', link: 'leads.html' },
                { value: stats.active_clients || 0, label: 'Clients', link: 'clients.html' },
                { value: stats.open_issues || 0, label: 'Open Issues', link: 'issues.html' }
            ];
        } else {
            statCards = [
                { value: openTasks, label: 'Open Tasks', link: 'todo.html' },
                { value: visits.length, label: 'Activity', link: 'visits.html' },
                { value: projects.length, label: 'Projects', link: 'projects.html' }
            ];
        }

        container.innerHTML = statCards.map(card => `
            <a href="${card.link}" class="stat-pill">
                <div class="sp-val">${card.value}</div>
                <div class="sp-lbl">${card.label}</div>
            </a>`).join('');
    } catch (e) {
        console.error('Stats load failed', e);
    }
}

/**
 * ── Render Quick Links ──────────────────────────────────────────────────────
 */
function renderQuickLinks(u) {
    const container = document.getElementById('quick-actions-container');
    const list = document.getElementById('quick-links-list');
    if (!container || !list) return;

    const role = (u.role || '').toUpperCase();
    const isAdmin = role === 'ADMIN';
    const isSales = role === 'SALES' || role === 'PROJECT_MANAGER_AND_SALES' || role === 'TELESALES';
    const isPM = role === 'PROJECT_MANAGER' || role === 'PROJECT_MANAGER_AND_SALES';

    let links = [];

    if (isAdmin) {
        links = [
            { label: 'Manage Employees', desc: 'Add or update team members', icon: 'bi-people', link: 'admin.html', color: '#6366f1' },
            { label: 'Employee Reports', desc: 'View employee analytics', icon: 'bi-graph-up-arrow', link: 'employee_report.html', color: '#10b981' },
            { label: 'Client Reports', desc: 'View client analytics', icon: 'bi-graph-up-arrow', link: 'client_report.html', color: '#10b981' },
            { label: 'System Settings', desc: 'Configure platform preferences', icon: 'bi-sliders', link: 'settings.html', color: '#64748b' }
        ];
    } else {
        if (isSales) {
            links.push({ label: 'Add New Lead', desc: 'Create a new business opportunity', icon: 'bi-person-plus', link: 'leads.html?add=true', color: '#2563eb' });
            links.push({ label: 'Log New Visit', desc: 'Record a field activity', icon: 'bi-geo-alt', link: 'visits.html?add=true', color: '#10b981' });
        }
        if (isPM) {
            links.push({ label: 'New Project', desc: 'Setup a new client project', icon: 'bi-briefcase', link: 'projects.html?add=true', color: '#6366f1' });
        }
        links.push({ label: 'My Attendance', desc: 'View punch logs and leave status', icon: 'bi-calendar-check', link: 'leaves.html', color: '#f59e0b' });
        links.push({ label: 'My ID Card', desc: 'Download printable identification', icon: 'bi-person-badge', onclick: 'downloadMyIDCard()', color: '#6366f1' });
    }

    if (links.length > 0) {
        container.style.display = 'block';
        list.innerHTML = links.map(l => `
            <a ${l.link ? `href="${l.link}"` : `onclick="${l.onclick}" style="cursor:pointer;"`} class="quick-action-item">
                <div class="qai-icon" style="background: ${l.color}15; color: ${l.color};">
                    <i class="bi ${l.icon}"></i>
                </div>
                <div class="qai-content">
                    <div class="qai-label">${l.label}</div>
                    <div class="qai-desc">${l.desc}</div>
                </div>
                <i class="bi bi-chevron-right qai-arrow"></i>
            </a>
        `).join('');
    }
}

/**
 * ── Download ID Card ────────────────────────────────────────────────────────
 */
window.downloadMyIDCard = async function() {
    try {
        if (!window.ApiClient) throw new Error('ApiClient not initialized');
        const html = await window.ApiClient.getMyIDCardHtml();
        const blob = new Blob([html], { type: 'text/html' });
        const url = URL.createObjectURL(blob);
        const win = window.open(url, '_blank');
        if (!win) showToast('Please allow popups to view ID Card', 'warning');
    } catch (err) {
        showToast('Failed to load ID card', 'error');
    }
}

/**
 * ── Edit Profile Form ───────────────────────────────────────────────────────
 */
const profileForm = document.getElementById('edit-profile-form');
if (profileForm) {
    profileForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('btn-save-profile');
        const spn = document.getElementById('spinner-save-profile');
        const icon = document.getElementById('icon-save-profile');

        const payload = {
            name: document.getElementById('edit-name').value.trim(),
            phone: document.getElementById('edit-phone').value.trim(),
            summary: document.getElementById('edit-summary').value.trim(),
            social_links: {
                linkedin: document.getElementById('edit-linkedin').value.trim(),
                twitter: document.getElementById('edit-twitter').value.trim(),
                github: document.getElementById('edit-github').value.trim()
            }
        };

        const rules = {
            'edit-name': 'Full Name is required'
        };

        if (!validateForm(profileForm, rules)) {
            return;
        }

        try {
            if (btn) btn.disabled = true;
            if (spn) spn.classList.remove('d-none');
            if (icon) icon.classList.add('d-none');

            await apiPatch('/auth/profile', payload);
            showToast('Profile updated successfully!');
            loadProfile();
        } catch (err) {
            showToast(err?.message || 'Failed to update profile.', 'error');
        } finally {
            if (btn) btn.disabled = false;
            if (spn) spn.classList.add('d-none');
            if (icon) icon.classList.remove('d-none');
        }
    });
}

/**
 * ── Change Password Form ────────────────────────────────────────────────────
 */
const passwordForm = document.getElementById('change-password-form');
if (passwordForm) {
    passwordForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const old = document.getElementById('old-password').value;
        const nw = document.getElementById('new-password').value;
        const conf = document.getElementById('confirm-password').value;
        
        const btn = document.getElementById('btn-update-pwd');
        const spn = document.getElementById('spinner-update-pwd');
        const icon = document.getElementById('icon-update-pwd');

        const rules = {
            'old-password': 'Current password is required',
            'new-password': (val) => {
                if (!val) return 'New password is required';
                if (val.length < 8) return 'Password must be at least 8 characters';
                return true;
            },
            'confirm-password': (val) => {
                if (val !== document.getElementById('new-password').value) return 'Passwords do not match';
                return true;
            }
        };

        if (!validateForm(passwordForm, rules)) {
            return;
        }

        try {
            if (btn) btn.disabled = true;
            if (spn) spn.classList.remove('d-none');
            if (icon) icon.classList.add('d-none');

            await apiPost('/auth/change-password', { old_password: old, new_password: nw });
            passwordForm.reset();
            if (typeof checkStrength === 'function') checkStrength('');
            showToast('Password changed successfully!');
        } catch (err) {
            showToast(err?.message || 'Failed to change password.', 'error');
        } finally {
            if (btn) btn.disabled = false;
            if (spn) spn.classList.add('d-none');
            if (icon) icon.classList.remove('d-none');
        }
    });
}

/**
 * ── Password Strength & Visibility ──────────────────────────────────────────
 */
window.checkStrength = function(val) {
    const bar = document.getElementById('pwd-strength-bar');
    const txt = document.getElementById('pwd-strength-text');
    if (!bar || !txt) return;
    
    if (!val) { bar.style.width = '0%'; txt.textContent = ''; return; }
    let score = 0;
    if (val.length >= 8) score++;
    if (/[A-Z]/.test(val)) score++;
    if (/[0-9]/.test(val)) score++;
    if (/[^A-Za-z0-9]/.test(val)) score++;
    
    const levels = [
        { w: '25%', bg: '#ef4444', label: 'Weak' },
        { w: '50%', bg: '#f59e0b', label: 'Fair' },
        { w: '75%', bg: '#3b82f6', label: 'Good' },
        { w: '100%', bg: '#10b981', label: 'Strong' }
    ];
    const l = levels[score - 1] || levels[0];
    bar.style.width = l.w;
    bar.style.background = l.bg;
    txt.textContent = l.label;
    txt.style.color = l.bg;
}

window.togglePasswordVisibility = function(inputId, iconId) {
    const input = document.getElementById(inputId);
    const icon = document.getElementById(iconId);
    if (!input || !icon) return;
    
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.replace('bi-eye', 'bi-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.replace('bi-eye-slash', 'bi-eye');
    }
}
