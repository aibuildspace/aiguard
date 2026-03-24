// ── Dashboard ───────────────────────────────────────────────────────────────

async function renderDashboard() {
    $content().innerHTML = `<div class="section-header"><h2>Dashboard</h2></div><p style="color:var(--text-muted)">Loading...</p>`;
    try {
        const data = await api.get("/dashboard");
        const recentLogs = data.recent_logs || [];

        $content().innerHTML = `
            <div class="section-header"><h2>Dashboard</h2></div>

            <!-- Hero stat cards — top KPIs -->
            <div class="stat-grid stat-grid-hero">
                <div class="stat-card stat-accent-blue">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></div>
                    <div class="stat-body"><div class="value">${data.requests_today}</div><div class="label">Requests Today</div></div>
                </div>
                <div class="stat-card stat-accent-red">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg></div>
                    <div class="stat-body"><div class="value danger">${data.blocked_today}</div><div class="label">Blocked</div></div>
                </div>
                <div class="stat-card stat-accent-amber">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg></div>
                    <div class="stat-body"><div class="value warning">${data.warned_today}</div><div class="label">Warned</div></div>
                </div>
                <div class="stat-card stat-accent-indigo">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>
                    <div class="stat-body"><div class="value primary">${data.shields_loaded || 0}</div><div class="label">Shields</div></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg></div>
                    <div class="stat-body"><div class="value">${data.active_orgs}</div><div class="label">Organizations</div></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div>
                    <div class="stat-body"><div class="value">${data.active_users}</div><div class="label">Users</div></div>
                </div>
                <div class="stat-card">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg></div>
                    <div class="stat-body"><div class="value">${data.active_keys}</div><div class="label">API Keys</div></div>
                </div>
                <div class="stat-card stat-accent-teal">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg></div>
                    <div class="stat-body"><div class="value">${_formatTokens(data.input_tokens_today || 0)}</div><div class="label">Input Tokens</div></div>
                </div>
                <div class="stat-card stat-accent-teal">
                    <div class="stat-icon"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg></div>
                    <div class="stat-body"><div class="value">${_formatTokens(data.output_tokens_today || 0)}</div><div class="label">Output Tokens</div></div>
                </div>
            </div>

            <!-- Recent Activity Section -->
            <div class="dash-section">
                <div class="dash-section-header">
                    <h3>Recent Activity</h3>
                    <div class="dash-section-actions">
                        <select id="dash-filter-outcome" class="input-sm">
                            <option value="">All outcomes</option>
                            <option value="clean">Clean</option>
                            <option value="warned">Warned</option>
                            <option value="blocked">Blocked</option>
                            <option value="sanitized">Sanitized</option>
                        </select>
                        <a href="#audit" class="btn btn-secondary btn-sm">View All Logs &rarr;</a>
                    </div>
                </div>

                <div class="dash-tile-grid" id="dash-tiles"></div>
            </div>

            <!-- Cost Overview Section -->
            <div class="dash-section">
                <div class="dash-section-header">
                    <h3>Cost Overview</h3>
                    <div class="dash-section-actions">
                        <select id="dash-cost-period" class="input-sm">
                            <option value="today">Today</option>
                            <option value="7d" selected>Last 7 Days</option>
                            <option value="30d">Last 30 Days</option>
                            <option value="all">All Time</option>
                        </select>
                        <a href="#costing" class="btn btn-secondary btn-sm">Full Cost Report &rarr;</a>
                    </div>
                </div>
                <div id="dash-cost-content" class="dash-cost-content">
                    <div class="dash-loading"><div class="spinner"></div> Loading costs...</div>
                </div>
            </div>
        `;

        // Render tiles
        _renderDashTiles(recentLogs);

        // Filter handler
        $("#dash-filter-outcome").onchange = () => {
            const filter = $("#dash-filter-outcome").value;
            const filtered = filter ? recentLogs.filter(l => l.scan_outcome === filter) : recentLogs;
            _renderDashTiles(filtered);
        };

        // Load cost overview
        _loadDashCosts();
        $("#dash-cost-period").onchange = () => _loadDashCosts();

    } catch (e) {
        $content().innerHTML = `<div class="section-header"><h2>Dashboard</h2></div>
            <div class="card"><p style="color:var(--danger)">Error: ${esc(e.message)}</p>
            <p style="color:var(--text-secondary)">Make sure the admin API key is set in the sidebar.</p></div>`;
    }
}

function _formatTokens(n) {
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "K";
    return String(n);
}

function _formatCost(usd) {
    if (usd < 0.01) return "$" + usd.toFixed(4);
    if (usd < 1) return "$" + usd.toFixed(3);
    return "$" + usd.toFixed(2);
}

function _outcomeClass(outcome) {
    switch (outcome) {
        case "blocked": return "hm-blocked";
        case "warned": return "hm-warned";
        default: return "hm-clean"; // clean, sanitized, etc. -> grey
    }
}

// Intensity based on latency — darker = slower / more notable
function _intensityClass(log) {
    const ms = log.proxy_latency_ms || 0;
    if (ms > 2000) return "hm-i4";
    if (ms > 1000) return "hm-i3";
    if (ms > 400)  return "hm-i2";
    return "hm-i1";
}

function _renderDashTiles(logs) {
    const grid = $("#dash-tiles");
    if (!logs.length) {
        grid.innerHTML = `<div class="hm-empty">No recent traces</div>`;
        return;
    }

    // Build legend — 3 colors: grey (clean), red (blocked), yellow (warned)
    const legend = `<div class="hm-legend">
        <span class="hm-legend-label">Less</span>
        <span class="hm-swatch hm-clean hm-i1"></span>
        <span class="hm-swatch hm-clean hm-i2"></span>
        <span class="hm-swatch hm-clean hm-i3"></span>
        <span class="hm-swatch hm-clean hm-i4"></span>
        <span class="hm-legend-label">More</span>
        <span class="hm-legend-sep"></span>
        <span class="hm-swatch hm-blocked hm-i2"></span><span class="hm-legend-label">Blocked</span>
        <span class="hm-swatch hm-warned hm-i2"></span><span class="hm-legend-label">Warned</span>
        <span class="hm-swatch hm-clean hm-i2"></span><span class="hm-legend-label">Clean / Sanitized</span>
    </div>`;

    // Group logs by day, then render rows
    const dayMap = new Map();
    for (const l of logs) {
        const ts = l.timestamp || "";
        const day = ts.slice(0, 10); // YYYY-MM-DD
        if (!dayMap.has(day)) dayMap.set(day, []);
        dayMap.get(day).push(l);
    }

    let rows = "";
    for (const [day, dayLogs] of dayMap) {
        const dayLabel = _formatDayLabel(day);
        rows += `<div class="hm-row">
            <span class="hm-row-label" title="${esc(day)}">${dayLabel}</span>
            <div class="hm-row-cells">
                ${dayLogs.map((l, i) => `<div class="hm-cell ${_outcomeClass(l.scan_outcome)} ${_intensityClass(l)}" data-day="${esc(day)}" data-idx="${i}" role="button" tabindex="0" title="${esc(l.model)} · ${l.scan_outcome} · ${timeAgo(l.timestamp)}"></div>`).join("")}
            </div>
        </div>`;
    }

    grid.innerHTML = `<div class="hm-grid">${rows}</div>${legend}`;

    // Click handlers — open detail panel
    $$(".hm-cell", grid).forEach(cell => {
        const day = cell.dataset.day;
        const idx = parseInt(cell.dataset.idx);
        const log = dayMap.get(day)?.[idx];
        if (!log) return;
        const handler = () => {
            $$(".hm-cell").forEach(c => c.classList.remove("active"));
            cell.classList.add("active");
            openTraceDialog(log);
        };
        cell.onclick = handler;
        cell.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); handler(); } };
    });
}

function _formatDayLabel(iso) {
    if (!iso) return "";
    const d = new Date(iso + "T00:00:00");
    const now = new Date();
    const today = now.toISOString().slice(0, 10);
    const yesterday = new Date(now - 86400000).toISOString().slice(0, 10);
    if (iso === today) return "Today";
    if (iso === yesterday) return "Yesterday";
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

async function _loadDashCosts() {
    const el = $("#dash-cost-content");
    if (!el) return;
    const period = $("#dash-cost-period")?.value || "7d";
    el.innerHTML = `<div class="dash-loading"><div class="spinner"></div> Loading costs...</div>`;
    try {
        const cost = await api.get(`/costing/summary?period=${period}`);
        el.innerHTML = `
            <div class="dash-cost-cards">
                <div class="dash-cost-card">
                    <div class="dash-cost-card-value">${_formatCost(cost.estimated_cost_usd)}</div>
                    <div class="dash-cost-card-label">Estimated Cost</div>
                </div>
                <div class="dash-cost-card">
                    <div class="dash-cost-card-value">${cost.total_requests.toLocaleString()}</div>
                    <div class="dash-cost-card-label">Total Requests</div>
                </div>
                <div class="dash-cost-card">
                    <div class="dash-cost-card-value">${_formatTokens(cost.total_input_tokens)}</div>
                    <div class="dash-cost-card-label">Input Tokens</div>
                </div>
                <div class="dash-cost-card">
                    <div class="dash-cost-card-value">${_formatTokens(cost.total_output_tokens)}</div>
                    <div class="dash-cost-card-label">Output Tokens</div>
                </div>
            </div>

            ${cost.by_model.length ? `
            <div class="dash-cost-breakdown">
                <h4>Cost by Model</h4>
                <div class="dash-cost-bars">
                    ${cost.by_model.slice(0, 5).map(m => {
                        const pct = cost.estimated_cost_usd > 0 ? (m.estimated_cost_usd / cost.estimated_cost_usd * 100) : 0;
                        return `<div class="dash-cost-bar-row">
                            <div class="dash-cost-bar-label">
                                <span class="audit-provider-badge provider-${esc(m.provider)}">${esc(m.provider)}</span>
                                <span>${esc(m.model)}</span>
                            </div>
                            <div class="dash-cost-bar-track">
                                <div class="dash-cost-bar-fill" style="width:${Math.max(pct, 2)}%"></div>
                            </div>
                            <span class="dash-cost-bar-value">${_formatCost(m.estimated_cost_usd)}</span>
                        </div>`;
                    }).join("")}
                </div>
            </div>` : ''}
        `;
    } catch (e) {
        el.innerHTML = `<div class="card" style="padding:16px"><p style="color:var(--text-muted)">Cost data unavailable</p></div>`;
    }
}
