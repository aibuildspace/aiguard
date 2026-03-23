// ── Costing ─────────────────────────────────────────────────────────────────

async function renderCosting() {
    $content().innerHTML = `<div class="section-header"><h2>Costing &amp; Budgets</h2></div><p style="color:var(--text-muted)">Loading...</p>`;
    try {
        const [users, budgets] = await Promise.all([
            api.get("/users").catch(() => []),
            api.get("/budgets").catch(() => []),
        ]);
        const budgetMap = Object.fromEntries(budgets.map(b => [b.user_id, b]));

        $content().innerHTML = `
            <div class="section-header"><h2>Costing &amp; Budgets</h2></div>

            <!-- Period selector & summary -->
            <div class="card costing-toolbar">
                <div class="costing-controls">
                    <div class="form-group compact">
                        <label>Period</label>
                        <select id="cost-period">
                            <option value="today">Today</option>
                            <option value="7d">Last 7 Days</option>
                            <option value="30d" selected>Last 30 Days</option>
                            <option value="all">All Time</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" id="cost-refresh">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
                        Refresh
                    </button>
                </div>
            </div>

            <div id="cost-summary"></div>

            <!-- Budgets Section -->
            <div class="dash-section" style="margin-top:8px">
                <div class="dash-section-header">
                    <h3>User Budgets</h3>
                    <button class="btn btn-primary btn-sm" id="toggle-add-budget">+ Assign Budget</button>
                </div>

                <div class="card create-form" id="add-budget-form" style="display:none;margin-bottom:16px">
                    <h4 style="margin-bottom:12px">Assign Budget to User</h4>
                    <div class="form-row">
                        <div class="form-group">
                            <label>User</label>
                            <select id="budget-user">
                                <option value="">-- Select user --</option>
                                ${users.filter(u => !budgetMap[u.id]).map(u => `<option value="${u.id}">${esc(u.name)} (${esc(u.email)})</option>`).join("")}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Monthly Limit (USD)</label>
                            <input type="number" id="budget-limit" value="10.00" step="0.01" min="0">
                        </div>
                        <div class="form-group">
                            <label>Enforce</label>
                            <select id="budget-enforce">
                                <option value="false">No (warn only)</option>
                                <option value="true">Yes (block over-budget)</option>
                            </select>
                        </div>
                    </div>
                    <button class="btn btn-primary" id="submit-add-budget">Assign Budget</button>
                </div>

                <div id="budget-list"></div>
            </div>
        `;

        // Load cost data
        async function loadCosts() {
            const period = $("#cost-period").value;
            const el = $("#cost-summary");
            el.innerHTML = `<div class="dash-loading"><div class="spinner"></div> Loading...</div>`;
            try {
                const cost = await api.get("/costing/summary?period=" + period);
                el.innerHTML = _renderCostSummary(cost);
            } catch (e) {
                el.innerHTML = `<div class="card"><p style="color:var(--danger)">Error loading costs: ${esc(e.message)}</p></div>`;
            }
        }

        loadCosts();
        $("#cost-period").onchange = loadCosts;
        $("#cost-refresh").onclick = loadCosts;

        // Budget form toggle
        $("#toggle-add-budget").onclick = () => {
            const f = $("#add-budget-form");
            f.style.display = f.style.display === "none" ? "block" : "none";
        };

        // Submit budget
        $("#submit-add-budget").onclick = async () => {
            const userId = $("#budget-user").value;
            if (!userId) { showToast("Select a user", "warning"); return; }
            try {
                await api.post("/budgets", {
                    user_id: userId,
                    monthly_limit_usd: $("#budget-limit").value !== '' ? parseFloat($("#budget-limit").value) : 10.0,
                    enforce: $("#budget-enforce").value === "true",
                });
                showToast("Budget assigned");
                _rerender(renderCosting);
            } catch (e) {
                showToast("Error: " + e.message, "error");
            }
        };

        // Render budget list
        _renderBudgetList(budgets);

    } catch (e) {
        $content().innerHTML = `<div class="section-header"><h2>Costing</h2></div><div class="card"><p style="color:var(--danger)">Error: ${esc(e.message)}</p></div>`;
    }
}

function _renderCostSummary(cost) {
    const hasTokens = cost.total_input_tokens > 0 || cost.total_output_tokens > 0;
    const noDataNotice = !hasTokens && cost.total_requests > 0
        ? `<div class="cost-notice"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> Token counts from streaming responses may take a moment to appear. Costs are estimated once tokens are captured.</div>`
        : '';
    return `
        ${noDataNotice}
        <!-- Summary cards -->
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

        <div class="costing-grid">
            <!-- By Model -->
            <div class="card costing-panel">
                <h4>Cost by Model</h4>
                ${cost.by_model.length ? `
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>Model</th><th>Provider</th><th>Requests</th><th>In Tokens</th><th>Out Tokens</th><th>Est. Cost</th></tr></thead>
                        <tbody>
                            ${cost.by_model.map(m => `<tr>
                                <td><strong>${esc(m.model || '(unknown)')}</strong></td>
                                <td><span class="audit-provider-badge provider-${esc(m.provider)}">${esc(m.provider)}</span></td>
                                <td>${m.requests.toLocaleString()}</td>
                                <td>${_formatTokens(m.input_tokens)}</td>
                                <td>${_formatTokens(m.output_tokens)}</td>
                                <td><strong>${_formatCost(m.estimated_cost_usd)}</strong></td>
                            </tr>`).join("")}
                        </tbody>
                    </table>
                </div>` : `<p class="text-muted" style="margin-top:8px">No model data for this period</p>`}
            </div>

            <!-- By User -->
            <div class="card costing-panel">
                <h4>Cost by User</h4>
                ${cost.by_user.length ? `
                <div class="table-wrap">
                    <table>
                        <thead><tr><th>User</th><th>Requests</th><th>In Tokens</th><th>Out Tokens</th><th>Est. Cost</th></tr></thead>
                        <tbody>
                            ${cost.by_user.map(u => `<tr>
                                <td>${u.user_name ? `<strong>${esc(u.user_name)}</strong><br><small style="color:var(--text-muted)">${esc(u.user_email || '')}</small>` : '<span class="text-muted">Anonymous / Passthrough</span>'}</td>
                                <td>${u.requests.toLocaleString()}</td>
                                <td>${_formatTokens(u.input_tokens)}</td>
                                <td>${_formatTokens(u.output_tokens)}</td>
                                <td><strong>${_formatCost(u.estimated_cost_usd)}</strong></td>
                            </tr>`).join("")}
                        </tbody>
                    </table>
                </div>` : `<p class="text-muted" style="margin-top:8px">No user data for this period</p>`}
            </div>
        </div>

        <!-- Daily Breakdown -->
        ${cost.by_day.length ? `
        <div class="card" style="margin-top:16px">
            <h4>Daily Breakdown</h4>
            <div class="costing-day-chart">
                ${_renderDayBars(cost.by_day)}
            </div>
        </div>` : ''}
    `;
}

function _renderDayBars(days) {
    if (!days.length) return '';
    const maxCost = Math.max(...days.map(d => d.estimated_cost_usd), 0.001);
    return `<div class="day-chart">
        ${days.map(d => {
            const pct = (d.estimated_cost_usd / maxCost) * 100;
            const label = d.date.slice(5); // MM-DD
            return `<div class="day-bar-col" title="${d.date}: ${_formatCost(d.estimated_cost_usd)} (${d.requests} reqs)">
                <div class="day-bar-fill" style="height:${Math.max(pct, 2)}%"></div>
                <span class="day-bar-label">${label}</span>
            </div>`;
        }).join("")}
    </div>`;
}

function _renderBudgetList(budgets) {
    const el = $("#budget-list");
    if (!budgets.length) {
        el.innerHTML = `<div class="card"><div class="empty-state">No budgets assigned yet. Assign budgets to users to track and optionally enforce spending limits.</div></div>`;
        return;
    }
    el.innerHTML = `
        <div class="table-wrap">
            <table>
                <thead><tr>
                    <th>User</th>
                    <th>Monthly Limit</th>
                    <th>Current Usage</th>
                    <th>% Used</th>
                    <th>Requests</th>
                    <th>Enforce</th>
                    <th></th>
                </tr></thead>
                <tbody>
                    ${budgets.map(b => {
                        const pctClass = b.pct_used >= 100 ? 'danger' : b.pct_used >= 80 ? 'warning' : 'success';
                        return `<tr>
                            <td>
                                <strong>${esc(b.user_name || 'Unknown')}</strong>
                                ${b.user_email ? `<br><small style="color:var(--text-muted)">${esc(b.user_email)}</small>` : ''}
                            </td>
                            <td>${_formatCost(b.monthly_limit_usd)}</td>
                            <td>${_formatCost(b.current_month_usage_usd)}</td>
                            <td>
                                <div class="budget-bar">
                                    <div class="budget-bar-fill budget-bar-${pctClass}" style="width:${Math.min(b.pct_used, 100)}%"></div>
                                </div>
                                <span class="budget-pct ${pctClass}">${b.pct_used.toFixed(1)}%</span>
                            </td>
                            <td>${b.current_month_requests}</td>
                            <td>${b.enforce ? badge("enforced", "blocked") : badge("warn only", "warned")}</td>
                            <td>
                                <div class="btn-group-sm">
                                    <button class="btn btn-sm btn-secondary btn-toggle-enforce" data-id="${b.id}" data-enforce="${!b.enforce}" title="${b.enforce ? 'Disable enforcement' : 'Enable enforcement'}">${b.enforce ? 'Disable' : 'Enable'}</button>
                                    <button class="btn btn-sm btn-secondary btn-reset-budget" data-id="${b.id}" title="Reset usage">Reset</button>
                                    <button class="btn btn-sm btn-danger btn-delete-budget" data-id="${b.id}" title="Delete budget">Delete</button>
                                </div>
                            </td>
                        </tr>`;
                    }).join("")}
                </tbody>
            </table>
        </div>
    `;

    // Action handlers
    $$(".btn-toggle-enforce").forEach(btn => {
        btn.onclick = async () => {
            try {
                await api.patch(`/budgets/${btn.dataset.id}`, { enforce: btn.dataset.enforce === "true" });
                showToast("Budget updated");
                _rerender(renderCosting);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    });
    $$(".btn-reset-budget").forEach(btn => {
        btn.onclick = async () => {
            try {
                await api.post(`/budgets/${btn.dataset.id}/reset`);
                showToast("Budget reset");
                _rerender(renderCosting);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    });
    $$(".btn-delete-budget").forEach(btn => {
        btn.onclick = async () => {
            if (!confirm("Delete this budget?")) return;
            try {
                await api.del(`/budgets/${btn.dataset.id}`);
                showToast("Budget deleted");
                _rerender(renderCosting);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    });
}
