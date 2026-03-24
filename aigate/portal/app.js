// ── API Client ──────────────────────────────────────────────────────────────

const api = {
    getKey() { return localStorage.getItem("guard_admin_key") || ""; },
    setKey(key) { localStorage.setItem("guard_admin_key", key); },
    async request(method, path, body) {
        const opts = { method, headers: { "Content-Type": "application/json" } };
        const key = this.getKey();
        if (key) opts.headers["X-Admin-Key"] = key;
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(`/api/v1${path}`, opts);
        if (!res.ok) {
            const text = await res.text();
            throw new Error(`${res.status}: ${text}`);
        }
        if (res.status === 204) return {};
        return res.json();
    },
    get(path) { return this.request("GET", path); },
    post(path, body) { return this.request("POST", path, body); },
    patch(path, body) { return this.request("PATCH", path, body); },
    del(path) { return this.request("DELETE", path); },
};

// ── Helpers ─────────────────────────────────────────────────────────────────

const $ = (sel, ctx) => (ctx || document).querySelector(sel);
const $$ = (sel, ctx) => [...(ctx || document).querySelectorAll(sel)];
const $content = () => $("#content");

// ── Model pricing (USD per 1K tokens) — input / output ──────────────────────
const MODEL_PRICING = {
    "gpt-4o-mini":    [0.00015, 0.0006],
    "gpt-4o":         [0.0025,  0.01],
    "gpt-4.1-mini":   [0.0004,  0.0016],
    "gpt-4.1":        [0.002,   0.008],
    "o3-mini":        [0.0011,  0.0044],
    "claude-sonnet-4-20250514": [0.003, 0.015],
    "claude-haiku-4-20250414":  [0.0008, 0.004],
    "claude-opus-4-20250514":   [0.015, 0.075],
};
const DEFAULT_PRICING = [0.002, 0.008];

function estimateCost(model, inputTokens, outputTokens) {
    const [inRate, outRate] = MODEL_PRICING[model] || DEFAULT_PRICING;
    return (inputTokens / 1000 * inRate) + (outputTokens / 1000 * outRate);
}

function formatCost(usd) {
    if (usd < 0.01) return '$' + usd.toFixed(6);
    if (usd < 1)    return '$' + usd.toFixed(4);
    return '$' + usd.toFixed(2);
}

function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    if (attrs) Object.entries(attrs).forEach(([k, v]) => {
        if (k.startsWith("on")) el.addEventListener(k.slice(2).toLowerCase(), v);
        else if (k === "className") el.className = v;
        else if (k === "htmlFor") el.htmlFor = v;
        else el.setAttribute(k, v);
    });
    children.flat().forEach(c => {
        if (c == null) return;
        el.append(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return el;
}

function badge(text, type) {
    return `<span class="badge badge-${type || text}">${text}</span>`;
}

function esc(s) {
    if (s == null) return "";
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function timeAgo(iso) {
    if (!iso) return "-";
    // Backend returns naive UTC timestamps (no Z suffix) — normalise
    if (!iso.endsWith("Z") && !iso.includes("+")) iso += "Z";
    const diff = Math.floor((Date.now() - new Date(iso)) / 1000);
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return new Date(iso).toLocaleDateString();
}

function _generateHex(len) {
    const arr = new Uint8Array(len / 2);
    crypto.getRandomValues(arr);
    return Array.from(arr, b => b.toString(16).padStart(2, "0")).join("");
}

/**
 * Re-render a page function while preserving scroll position.
 * Usage: await _rerender(renderShields);
 */
async function _rerender(fn) {
    const scrollY = window.scrollY;
    await fn();
    requestAnimationFrame(() => window.scrollTo(0, scrollY));
}

// ── Toasts ──────────────────────────────────────────────────────────────────

function showToast(msg, type = "success") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        document.body.appendChild(container);
    }

    const icons = {
        success: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`,
        error: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        info: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>`,
        warning: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    };

    const el = document.createElement("div");
    el.className = `toast toast-${type}`;
    el.innerHTML = `<span class="toast-icon">${icons[type] || icons.info}</span><span class="toast-msg">${esc(msg)}</span><button class="toast-close" aria-label="Close">&times;</button>`;
    el.querySelector(".toast-close").onclick = () => dismissToast(el);
    container.appendChild(el);
    requestAnimationFrame(() => el.classList.add("toast-visible"));
    setTimeout(() => dismissToast(el), 4000);
}

function dismissToast(el) {
    if (!el || el._dismissed) return;
    el._dismissed = true;
    el.classList.remove("toast-visible");
    el.classList.add("toast-exit");
    el.addEventListener("transitionend", () => el.remove(), { once: true });
    setTimeout(() => el.remove(), 400);
}

// ── Router ──────────────────────────────────────────────────────────────────

// Routes are resolved lazily (page modules load after this file)
function navigate() {
    const routes = { dashboard: renderDashboard, orgs: renderOrgs, users: renderUsers, keys: renderKeys, shields: renderShields, audit: renderAudit, chat: renderChat, costing: renderCosting, settings: renderSettings };
    const hash = location.hash.replace("#", "") || "dashboard";
    const fn = routes[hash] || routes.dashboard;
    $$(".nav-item").forEach(a => a.classList.toggle("active", a.dataset.page === hash));
    fn();
}

window.addEventListener("hashchange", navigate);

// ── Shared Trace Detail ─────────────────────────────────────────────────────
// Reused by both audit.js and dashboard.js

function _renderFlowDiagram(log) {
    const isBlocked = log.scan_outcome === "blocked";
    const isUpstreamError = !isBlocked && log.http_status >= 400;
    const hasScan = (log.skills_triggered || []).length > 0;
    const scanLabel = isBlocked ? "Blocked" : hasScan ? "Scanned" : "Passed";

    const clientState = "reached";
    const gkState = isBlocked ? "stopped" : "reached";
    const llmState = isBlocked ? "skipped" : isUpstreamError ? "errored" : "reached";
    const respState = isBlocked ? "skipped" : isUpstreamError ? "errored" : "reached";

    const c1State = "active";
    const c2State = isBlocked ? "blocked" : "active";
    const c3State = isBlocked ? "inactive" : isUpstreamError ? "error" : "active";

    let respLabel, respDetail;
    if (isBlocked) { respLabel = "403"; respDetail = "Blocked"; }
    else if (isUpstreamError) { respLabel = String(log.http_status); respDetail = "Error"; }
    else { respLabel = String(log.http_status); respDetail = "OK"; }

    return `<div class="flow-diagram">
        <div class="flow-node ${clientState}">
            <div class="flow-node-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>
            <span class="flow-node-label">Client</span>
        </div>
        <div class="flow-connector ${c1State}"><div class="flow-connector-line"></div></div>
        <div class="flow-node ${gkState}">
            <div class="flow-node-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
            <span class="flow-node-label">Shield</span>
            <span class="flow-node-detail">${esc(scanLabel)}</span>
        </div>
        <div class="flow-connector ${c2State}"><div class="flow-connector-line"></div></div>
        <div class="flow-node ${llmState}">
            <div class="flow-node-icon"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg></div>
            <span class="flow-node-label">${esc(log.provider)}</span>
            <span class="flow-node-detail">${isBlocked ? 'Not reached' : esc(log.model)}</span>
        </div>
        <div class="flow-connector ${c3State}"><div class="flow-connector-line"></div></div>
        <div class="flow-node ${respState}">
            <div class="flow-node-icon">${isBlocked || isUpstreamError
              ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>`
              : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`
            }</div>
            <span class="flow-node-label">${esc(respLabel)}</span>
            <span class="flow-node-detail">${esc(respDetail)}</span>
        </div>
    </div>`;
}

function _jsonSize(obj) {
    const s = JSON.stringify(obj).length;
    if (s < 1024) return s + ' B';
    if (s < 1048576) return (s / 1024).toFixed(1) + ' KB';
    return (s / 1048576).toFixed(1) + ' MB';
}

function _renderTraceBody(log) {
    const overhead = (log.proxy_latency_ms != null && log.upstream_latency_ms != null)
        ? (log.proxy_latency_ms - log.upstream_latency_ms) : null;
    // Normalise timestamp for display
    const ts = log.timestamp || '';
    const tsDisplay = ts ? new Date(ts + (ts.endsWith('Z') ? '' : 'Z')).toLocaleString() : '\u2014';

    return `
        <div class="trace-status-bar ${log.scan_outcome}">
            <div class="trace-status-left">
                ${badge(log.scan_outcome, log.scan_outcome)}
                <span class="trace-model">${esc(log.model)}</span>
                <span class="audit-provider-badge provider-${esc(log.provider)}">${esc(log.provider)}</span>
            </div>
            <span class="trace-time-abs">${tsDisplay}</span>
        </div>

        ${_renderFlowDiagram(log)}

        ${log.message_preview ? `
        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                Message
            </div>
            <div class="trace-message-preview">${esc(log.message_preview)}</div>
        </div>` : ''}

        ${(log.skills_triggered || []).length ? `
        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                Shields Triggered
            </div>
            <div class="trace-shields-simple">
                ${log.skills_triggered.map(s => `
                    <div class="trace-shield-row">
                        <span class="trace-shield-name">${esc(s.shield_id || s.skill_id || s)}</span>
                        ${s.pattern_id ? `<span class="trace-shield-pattern">${esc(s.pattern_id)}</span>` : ''}
                        ${s.action ? badge(s.action, s.action === 'block' ? 'blocked' : s.action === 'warn' ? 'warned' : 'clean') : ''}
                    </div>
                `).join("")}
            </div>
        </div>` : ''}

        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                Details
            </div>
            <div class="trace-stats-grid">
                <div class="trace-stat">
                    <span class="trace-stat-value status-${log.http_status < 400 ? 'ok' : log.http_status < 500 ? 'warn' : 'err'}">${log.http_status}</span>
                    <span class="trace-stat-label">Status</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value">${log.proxy_latency_ms != null ? log.proxy_latency_ms + 'ms' : '\u2014'}</span>
                    <span class="trace-stat-label">Total</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value">${log.upstream_latency_ms != null ? log.upstream_latency_ms + 'ms' : '\u2014'}</span>
                    <span class="trace-stat-label">Upstream</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value">${overhead != null ? overhead + 'ms' : '\u2014'}</span>
                    <span class="trace-stat-label">Scan</span>
                </div>
                ${log.input_tokens != null ? `<div class="trace-stat"><span class="trace-stat-value">${log.input_tokens}</span><span class="trace-stat-label">In Tokens</span></div>` : ''}
                ${log.output_tokens != null ? `<div class="trace-stat"><span class="trace-stat-value">${log.output_tokens}</span><span class="trace-stat-label">Out Tokens</span></div>` : ''}
                ${(log.input_tokens != null || log.output_tokens != null) ? `<div class="trace-stat"><span class="trace-stat-value">${formatCost(estimateCost(log.model, log.input_tokens || 0, log.output_tokens || 0))}</span><span class="trace-stat-label">Est. Cost</span></div>` : ''}
            </div>
            <div class="trace-endpoint-row">
                <span class="trace-stat-label">Endpoint</span>
                <code>${esc(log.endpoint)}</code>
            </div>
        </div>

        ${log.request_body ? `
        <div class="trace-flat-section trace-payload-section">
            <button class="trace-payload-toggle" data-target="trace-req-payload">
                <svg class="trace-payload-chevron" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 6 15 12 9 18"/></svg>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                Request Body
                <span class="trace-payload-size">${_jsonSize(log.request_body)}</span>
            </button>
            <div class="trace-payload-content" id="trace-req-payload" style="display:none">
                <pre class="trace-payload-pre"><code>${esc(JSON.stringify(log.request_body, null, 2))}</code></pre>
            </div>
        </div>` : ''}

        ${log.response_body ? `
        <div class="trace-flat-section trace-payload-section">
            <button class="trace-payload-toggle" data-target="trace-resp-payload">
                <svg class="trace-payload-chevron" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 6 15 12 9 18"/></svg>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                Response Body
                <span class="trace-payload-size">${_jsonSize(log.response_body)}</span>
            </button>
            <div class="trace-payload-content" id="trace-resp-payload" style="display:none">
                <pre class="trace-payload-pre"><code>${esc(JSON.stringify(log.response_body, null, 2))}</code></pre>
            </div>
        </div>` : ''}

        <div class="trace-flat-section trace-ids-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Trace
            </div>
            ${log.trace_id ? `<div class="trace-id-row">
                <span class="trace-id-label">Trace</span>
                <code class="trace-id-value">${esc(log.trace_id)}</code>
                <button class="btn-copy-sm" data-copy="${esc(log.trace_id)}" title="Copy">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                </button>
            </div>` : ''}
            ${log.span_id ? `<div class="trace-id-row">
                <span class="trace-id-label">Span</span>
                <code class="trace-id-value">${esc(log.span_id)}</code>
            </div>` : ''}
            <div class="trace-id-row">
                <span class="trace-id-label">Request</span>
                <code class="trace-id-value">${esc(log.request_id)}</code>
                <button class="btn-copy-sm" data-copy="${esc(log.request_id)}" title="Copy">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/></svg>
                </button>
            </div>
        </div>
    `;
}

/**
 * Open a trace detail dialog. Works with any page that has a #trace-dialog element.
 * If no dialog exists yet, creates one on-the-fly.
 * @param {object} log - The audit log entry to display
 * @param {object[]} [logList] - Optional array of all logs for prev/next navigation
 * @param {number} [logIndex] - Current index in logList
 */
function openTraceDialog(log, logList, logIndex) {
    let dialog = $("#trace-dialog");
    if (!dialog) {
        dialog = document.createElement("dialog");
        dialog.id = "trace-dialog";
        dialog.innerHTML = `
            <div class="trace-dialog-content">
                <header class="trace-dialog-header">
                    <h3>Request Trace</h3>
                    <div class="trace-header-actions">
                        <button class="trace-nav-btn" id="trace-prev" title="Previous request" style="display:none">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
                        </button>
                        <span class="trace-nav-counter" id="trace-counter" style="display:none"></span>
                        <button class="trace-nav-btn" id="trace-next" title="Next request" style="display:none">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 6 15 12 9 18"/></svg>
                        </button>
                        <button class="trace-close" id="trace-close" aria-label="Close">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </div>
                </header>
                <div id="trace-body" class="trace-body"></div>
            </div>
        `;
        document.body.appendChild(dialog);
    }

    function _showLog(entry, list, idx) {
        const body = $("#trace-body");
        body.innerHTML = _renderTraceBody(entry);

        // Copy buttons
        body.querySelectorAll(".btn-copy-sm").forEach(btn => {
            btn.onclick = (e) => {
                e.stopPropagation();
                navigator.clipboard.writeText(btn.dataset.copy).then(() => showToast("Copied", "info"));
            };
        });

        // Payload toggle buttons (request/response bodies)
        body.querySelectorAll(".trace-payload-toggle").forEach(btn => {
            btn.onclick = () => {
                const target = body.querySelector("#" + btn.dataset.target);
                if (target) {
                    const isOpen = target.style.display !== "none";
                    target.style.display = isOpen ? "none" : "block";
                    btn.classList.toggle("open", !isOpen);
                }
            };
        });

        // Nav buttons
        const prevBtn = $("#trace-prev");
        const nextBtn = $("#trace-next");
        const counter = $("#trace-counter");

        if (list && list.length > 1) {
            counter.textContent = `${idx + 1} / ${list.length}`;
            counter.style.display = "";
            prevBtn.style.display = idx > 0 ? "" : "none";
            nextBtn.style.display = idx < list.length - 1 ? "" : "none";
            prevBtn.onclick = () => _showLog(list[idx - 1], list, idx - 1);
            nextBtn.onclick = () => _showLog(list[idx + 1], list, idx + 1);
        } else {
            prevBtn.style.display = "none";
            nextBtn.style.display = "none";
            counter.style.display = "none";
        }
    }

    _showLog(log, logList, logIndex ?? 0);

    dialog.showModal();
    $("#trace-close").onclick = () => dialog.close();
    dialog.onclick = (e) => { if (e.target === dialog) dialog.close(); };

    // Keyboard navigation
    dialog.onkeydown = (e) => {
        if (logList && logList.length > 1) {
            const prevBtn = $("#trace-prev");
            const nextBtn = $("#trace-next");
            if (e.key === "ArrowLeft" && prevBtn.style.display !== "none") { e.preventDefault(); prevBtn.click(); }
            if (e.key === "ArrowRight" && nextBtn.style.display !== "none") { e.preventDefault(); nextBtn.click(); }
        }
    };
}

// ── Init ────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
    // Sidebar toggle via topbar hamburger
    $("#sidebar-toggle").addEventListener("click", () => {
        $("#sidebar").classList.toggle("collapsed");
    });

    // Admin key toggle
    const keyPanel = $("#admin-key-panel");
    const keyToggle = $("#admin-key-toggle");
    if (keyToggle && keyPanel) {
        keyToggle.addEventListener("click", () => {
            keyPanel.classList.toggle("visible");
        });
    }
    const keyInput = $("#admin-key-input");
    if (keyInput) {
        keyInput.value = api.getKey();
        $("#save-key-btn").addEventListener("click", () => {
            api.setKey(keyInput.value.trim());
            showToast("Admin key saved");
            if (keyPanel) keyPanel.classList.remove("visible");
            navigate();
        });
    }

    navigate();
});
