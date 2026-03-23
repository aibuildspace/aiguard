// ── Users ───────────────────────────────────────────────────────────────────

async function renderUsers() {
    $content().innerHTML = `<div class="section-header"><h2>Users</h2></div><p style="color:var(--text-muted)">Loading...</p>`;
    try {
        const [users, orgs, budgets] = await Promise.all([
            api.get("/users"),
            api.get("/orgs"),
            api.get("/budgets").catch(() => []),
        ]);
        const orgMap = Object.fromEntries(orgs.map(o => [o.id, o]));
        const budgetByUser = Object.fromEntries(budgets.map(b => [b.user_id, b]));

        $content().innerHTML = `
            <div class="section-header">
                <h2>Users</h2>
                <button class="btn btn-primary" id="toggle-create-user">+ New User</button>
            </div>
            <div class="create-form" id="create-user-form" style="display:none">
                <h3>Create User</h3>
                <div class="form-row">
                    <div class="form-group"><label>Email</label><input type="email" id="user-email" placeholder="user@example.com"></div>
                    <div class="form-group"><label>Name</label><input type="text" id="user-name" placeholder="Jane Doe"></div>
                    <div class="form-group"><label>Organization</label><select id="user-org">${orgs.map(o => `<option value="${o.id}">${esc(o.name)}</option>`).join("")}</select></div>
                    <div class="form-group"><label>Role</label><select id="user-role"><option value="member">Member</option><option value="admin">Admin</option><option value="readonly">Read Only</option></select></div>
                </div>
                <button class="btn btn-primary" id="submit-create-user">Create</button>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Email</th><th>Name</th><th>Org</th><th>Role</th><th>Status</th><th>Budget</th></tr></thead>
                    <tbody>
                        ${users.map(u => {
                            const b = budgetByUser[u.id];
                            const budgetLabel = b ? _formatCost(b.monthly_limit_usd) + (b.enforce ? " (block)" : " (warn)") : '<span class="text-muted">None</span>';
                            return `<tr class="user-row clickable-row" data-id="${u.id}">
                                <td>${esc(u.email)}</td>
                                <td>${esc(u.name)}</td>
                                <td>${esc(orgMap[u.org_id]?.name || u.org_id)}</td>
                                <td>${esc(u.role)}</td>
                                <td>${u.is_active ? badge("active", "active") : badge("disabled", "inactive")}</td>
                                <td>${budgetLabel}</td>
                            </tr>`;
                        }).join("") || `<tr><td colspan="6" class="empty-state">No users yet</td></tr>`}
                    </tbody>
                </table>
            </div>
        `;

        // Toggle create form
        $("#toggle-create-user").onclick = () => {
            const f = $("#create-user-form");
            f.style.display = f.style.display === "none" ? "block" : "none";
        };

        // Submit create user
        $("#submit-create-user").onclick = async () => {
            const email = $("#user-email").value.trim();
            if (!email) return;
            await api.post("/users", {
                email,
                name: $("#user-name").value.trim() || email,
                org_id: $("#user-org").value,
                role: $("#user-role").value,
            });
            showToast("User created");
            _rerender(renderUsers);
        };

        // Clickable rows open detail panel
        $$(".user-row").forEach(row => {
            row.onclick = () => {
                const userId = row.dataset.id;
                const user = users.find(u => u.id === userId);
                if (user) _openUserPanel(user, orgMap, budgetByUser[userId] || null);
            };
        });

    } catch (e) {
        $content().innerHTML = `<div class="section-header"><h2>Users</h2></div><div class="card"><p style="color:var(--danger)">Error: ${esc(e.message)}</p></div>`;
    }
}

function _openUserPanel(user, orgMap, budget) {
    let dialog = $("#user-detail-dialog");
    if (!dialog) {
        dialog = document.createElement("dialog");
        dialog.id = "user-detail-dialog";
        dialog.innerHTML = `
            <div class="trace-dialog-content">
                <header class="trace-dialog-header">
                    <h3>User Details</h3>
                    <button class="trace-close" id="user-panel-close" aria-label="Close">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </header>
                <div id="user-panel-body" class="trace-body"></div>
            </div>
        `;
        document.body.appendChild(dialog);
    }

    const body = $("#user-panel-body");
    const orgName = orgMap[user.org_id]?.name || user.org_id;

    body.innerHTML = `
        <!-- User identity -->
        <div class="user-panel-identity">
            <div class="user-panel-avatar">${esc(user.name.charAt(0).toUpperCase())}</div>
            <div>
                <div class="user-panel-name">${esc(user.name)}</div>
                <div class="user-panel-email">${esc(user.email)}</div>
            </div>
        </div>

        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>
                Profile
            </div>
            <div class="user-panel-form">
                <div class="form-group">
                    <label>Name</label>
                    <input type="text" id="up-name" value="${esc(user.name)}">
                </div>
                <div class="form-group">
                    <label>Role</label>
                    <select id="up-role">
                        <option value="member" ${user.role === "member" ? "selected" : ""}>Member</option>
                        <option value="admin" ${user.role === "admin" ? "selected" : ""}>Admin</option>
                        <option value="readonly" ${user.role === "readonly" ? "selected" : ""}>Read Only</option>
                    </select>
                </div>
                <button class="btn btn-primary btn-sm" id="up-save-profile">Save Changes</button>
            </div>
        </div>

        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>
                Budget
            </div>
            <div class="user-panel-form" id="up-budget-section">
                ${_renderUserBudgetSection(budget, user)}
            </div>
        </div>

        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                Info
            </div>
            <div class="trace-stats-grid">
                <div class="trace-stat">
                    <span class="trace-stat-value">${esc(orgName)}</span>
                    <span class="trace-stat-label">Organization</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value status-${user.is_active ? 'ok' : 'err'}">${user.is_active ? "Active" : "Disabled"}</span>
                    <span class="trace-stat-label">Status</span>
                </div>
            </div>
        </div>

        <div class="trace-flat-section user-panel-actions">
            ${user.is_active
                ? `<button class="btn btn-danger btn-sm" id="up-disable">Disable User</button>`
                : `<button class="btn btn-primary btn-sm" id="up-enable">Enable User</button>`
            }
        </div>
    `;

    // Wire up actions
    _wireUserPanelActions(user, budget, orgMap);

    dialog.showModal();
    $("#user-panel-close").onclick = () => dialog.close();
    dialog.onclick = (e) => { if (e.target === dialog) dialog.close(); };
}

function _renderUserBudgetSection(budget, user) {
    if (budget) {
        const pctClass = budget.pct_used >= 100 ? "danger" : budget.pct_used >= 80 ? "warning" : "success";
        const mode = budget.enforce ? "block" : "warn";
        return `
            <div class="user-budget-summary">
                <div class="user-budget-row">
                    <span class="trace-stat-label">Monthly Limit</span>
                    <strong>${_formatCost(budget.monthly_limit_usd)}</strong>
                </div>
                <div class="user-budget-row">
                    <span class="trace-stat-label">Current Usage</span>
                    <strong>${_formatCost(budget.current_month_usage_usd)}</strong>
                </div>
                <div class="user-budget-row">
                    <span class="trace-stat-label">Used</span>
                    <span>
                        <div class="budget-bar" style="width:100px">
                            <div class="budget-bar-fill budget-bar-${pctClass}" style="width:${Math.min(budget.pct_used, 100)}%"></div>
                        </div>
                        <span class="budget-pct ${pctClass}">${budget.pct_used.toFixed(1)}%</span>
                    </span>
                </div>
                <div class="user-budget-row">
                    <span class="trace-stat-label">Tokens</span>
                    <span>${(budget.current_month_tokens_in || 0).toLocaleString()} in / ${(budget.current_month_tokens_out || 0).toLocaleString()} out</span>
                </div>
                <div class="user-budget-row">
                    <span class="trace-stat-label">Requests</span>
                    <span>${(budget.current_month_requests || 0).toLocaleString()}</span>
                </div>
            </div>
            <div class="form-group">
                <label>Monthly Limit (USD)</label>
                <input type="number" id="up-budget-limit" value="${budget.monthly_limit_usd}" step="0.01" min="0">
            </div>
            <div class="form-group">
                <label>Action</label>
                <div class="budget-mode-toggle" id="up-budget-mode">
                    <button type="button" class="budget-mode-btn ${mode === 'warn' ? 'active' : ''}" data-mode="warn">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                        Warn
                    </button>
                    <button type="button" class="budget-mode-btn ${mode === 'block' ? 'active' : ''}" data-mode="block">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                        Block
                    </button>
                </div>
            </div>
            <div class="user-panel-btn-row">
                <button class="btn btn-primary btn-sm" id="up-save-budget">Update Budget</button>
                <button class="btn btn-secondary btn-sm" id="up-reset-budget">Reset Usage</button>
                <button class="btn btn-danger btn-sm" id="up-delete-budget">Remove Budget</button>
            </div>
        `;
    }

    return `
        <p class="text-muted" style="margin:0 0 12px">No budget assigned.</p>
        <div class="form-group">
            <label>Monthly Limit (USD)</label>
            <input type="number" id="up-budget-limit" value="10.00" step="0.01" min="0">
        </div>
        <div class="form-group">
            <label>Action</label>
            <div class="budget-mode-toggle" id="up-budget-mode">
                <button type="button" class="budget-mode-btn active" data-mode="warn">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    Warn
                </button>
                <button type="button" class="budget-mode-btn" data-mode="block">
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                    Block
                </button>
            </div>
        </div>
        <button class="btn btn-primary btn-sm" id="up-assign-budget">Assign Budget</button>
    `;
}

function _wireUserPanelActions(user, budget, orgMap) {
    // Budget mode toggle buttons
    const modeToggle = $("#up-budget-mode");
    if (modeToggle) {
        modeToggle.querySelectorAll(".budget-mode-btn").forEach(btn => {
            btn.onclick = () => {
                modeToggle.querySelectorAll(".budget-mode-btn").forEach(b => b.classList.remove("active"));
                btn.classList.add("active");
            };
        });
    }
    function _getEnforce() {
        const active = modeToggle?.querySelector(".budget-mode-btn.active");
        return active?.dataset.mode === "block";
    }

    // Save profile
    $("#up-save-profile").onclick = async () => {
        try {
            const updated = await api.patch(`/users/${user.id}`, {
                name: $("#up-name").value.trim(),
                role: $("#up-role").value,
            });
            showToast("User updated");
            Object.assign(user, updated);
            _rerender(renderUsers);
        } catch (e) { showToast("Error: " + e.message, "error"); }
    };

    // Disable / Enable
    const disableBtn = $("#up-disable");
    const enableBtn = $("#up-enable");
    if (disableBtn) {
        disableBtn.onclick = async () => {
            try {
                await api.patch(`/users/${user.id}`, { is_active: false });
                showToast("User disabled");
                $("#user-detail-dialog").close();
                _rerender(renderUsers);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    }
    if (enableBtn) {
        enableBtn.onclick = async () => {
            try {
                await api.patch(`/users/${user.id}`, { is_active: true });
                showToast("User enabled");
                $("#user-detail-dialog").close();
                _rerender(renderUsers);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    }

    // Budget actions
    if (budget) {
        $("#up-save-budget").onclick = async () => {
            try {
                await api.patch(`/budgets/${budget.id}`, {
                    monthly_limit_usd: $("#up-budget-limit").value !== '' ? parseFloat($("#up-budget-limit").value) : 10.0,
                    enforce: _getEnforce(),
                });
                showToast("Budget updated");
                $("#user-detail-dialog").close();
                _rerender(renderUsers);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
        $("#up-reset-budget").onclick = async () => {
            try {
                await api.post(`/budgets/${budget.id}/reset`);
                showToast("Budget reset");
                $("#user-detail-dialog").close();
                _rerender(renderUsers);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
        $("#up-delete-budget").onclick = async () => {
            if (!confirm("Remove budget for this user?")) return;
            try {
                await api.del(`/budgets/${budget.id}`);
                showToast("Budget removed");
                $("#user-detail-dialog").close();
                _rerender(renderUsers);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    } else {
        const assignBtn = $("#up-assign-budget");
        if (assignBtn) {
            assignBtn.onclick = async () => {
                try {
                    await api.post("/budgets", {
                        user_id: user.id,
                        monthly_limit_usd: $("#up-budget-limit").value !== '' ? parseFloat($("#up-budget-limit").value) : 10.0,
                        enforce: _getEnforce(),
                    });
                    showToast("Budget assigned");
                    $("#user-detail-dialog").close();
                    _rerender(renderUsers);
                } catch (e) { showToast("Error: " + e.message, "error"); }
            };
        }
    }
}
