// Shared vanilla-JS utilities between frontend/ipd.html and frontend/headnurse.html.
// Plain <script src="/js/ipd-shared.js"> include (no build step, no ES modules) -- this file
// must load BEFORE either page's own inline <script> block, since both rely on the globals
// (accessToken/refreshToken) and functions (apiRequest/closeModal/taskTypeBadge) defined here.
const API_BASE = '/api';
let accessToken = localStorage.getItem('access_token');
let refreshToken = localStorage.getItem('refresh_token') || null;

async function apiRequest(endpoint, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;
    const res = await fetch(`${API_BASE}${endpoint}`, { ...options, headers });
    if (res.status === 401) {
        const refresh = refreshToken || localStorage.getItem('refresh_token');
        if (refresh) {
            const r = await fetch(`${API_BASE}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refresh })
            });
            if (r.ok) {
                const data = await r.json();
                localStorage.setItem('access_token', data.access_token);
                localStorage.setItem('refresh_token', data.refresh_token);
                accessToken = data.access_token;
                refreshToken = data.refresh_token;
                headers['Authorization'] = `Bearer ${data.access_token}`;
                return fetch(`${API_BASE}${endpoint}`, { ...options, headers });
            }
        }
        localStorage.clear();
        window.location.href = '/index.html';
    }
    return res;
}

function closeModal(id) { document.getElementById(id).style.display = 'none'; }

function taskTypeBadge(t) {
    const icon = { Medication: '💊', Lab: '🧪', Observation: '👁️', General: '📋' }[t.task_type] || '📋';
    const sourceColor = t.source === 'Auto' ? '#2F6F52' : '#667169';
    return `<span title="${t.task_type || 'General'}">${icon}</span> <span style="font-size:10px;color:${sourceColor};border:1px solid ${sourceColor};border-radius:8px;padding:0 6px;">${t.source || 'Manual'}</span>`;
}
