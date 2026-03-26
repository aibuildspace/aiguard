// ── API Keys ────────────────────────────────────────────────────────────────

async function renderKeys() {
    $content().innerHTML = `<div class="section-header"><h2>API Keys</h2></div><p style="color:var(--text-muted)">Loading...</p>`;
    try {
        const [keys, orgs, users, budgets] = await Promise.all([
            api.get("/keys"),
            api.get("/orgs"),
            api.get("/users"),
            api.get("/budgets").catch(() => []),
        ]);
        const orgMap = Object.fromEntries(orgs.map(o => [o.id, o]));
        const userMap = Object.fromEntries(users.map(u => [u.id, u]));
        const budgetByKey = Object.fromEntries(budgets.filter(b => b.api_key_id).map(b => [b.api_key_id, b]));

        $content().innerHTML = `
            <div class="section-header">
                <h2>API Keys</h2>
                <div style="display:flex;gap:8px">
                    <button class="btn btn-outline-danger" id="delete-all-keys">Delete All</button>
                    <button class="btn btn-primary" id="toggle-create-key">+ New Key</button>
                </div>
            </div>
            <div class="create-form" id="create-key-form" style="display:none">
                <h3>Create API Key</h3>
                <div class="form-row">
                    <div class="form-group"><label>Organization</label><select id="key-org">${orgs.map(o => `<option value="${o.id}">${esc(o.name)}</option>`).join("")}</select></div>
                    <div class="form-group"><label>User (optional)</label><select id="key-user"><option value="">-- None --</option>${users.map(u => `<option value="${u.id}">${esc(u.email)}</option>`).join("")}</select></div>
                    <div class="form-group"><label>Label</label><input type="text" id="key-label" placeholder="my-key"></div>
                    <div class="form-group"><label>Provider</label><select id="key-provider"><option value="any">Any</option><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option></select></div>
                </div>
                <div class="form-group"><label>Upstream API Key (optional)</label><input type="password" id="key-upstream" placeholder="sk-..."></div>
                <button class="btn btn-primary" id="submit-create-key">Create</button>
                <div id="new-key-display"></div>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Prefix</th><th>Label</th><th>Org</th><th>User</th><th>Provider</th><th>Status</th><th>Budget</th><th>Last Used</th></tr></thead>
                    <tbody>
                        ${keys.map(k => {
                            const b = budgetByKey[k.id];
                            const budgetLabel = b ? _formatCost(b.monthly_limit_usd) + (b.enforce ? " (block)" : " (warn)") : '<span class="text-muted">None</span>';
                            const statusHtml = k.blacklist_reason
                                ? badge("blacklisted", "inactive")
                                : k.is_active ? badge("active", "active") : badge("revoked", "inactive");
                            return `<tr class="key-row clickable-row" data-id="${k.id}">
                                <td><code>${esc(k.key_prefix)}</code></td>
                                <td>${esc(k.label)}</td>
                                <td>${esc(orgMap[k.org_id]?.name || "")}</td>
                                <td>${esc(userMap[k.user_id]?.email || "-")}</td>
                                <td><span class="audit-provider-badge provider-${esc(k.provider)}">${esc(k.provider)}</span></td>
                                <td>${statusHtml}</td>
                                <td>${budgetLabel}</td>
                                <td>${timeAgo(k.last_used_at)}</td>
                            </tr>`;
                        }).join("") || `<tr><td colspan="8" class="empty-state">No API keys yet</td></tr>`}
                    </tbody>
                </table>
            </div>
        `;

        // Delete all keys
        $("#delete-all-keys").onclick = async () => {
            if (!confirm("Delete ALL API keys? This cannot be undone.")) return;
            try {
                await api.del("/keys");
                showToast("All keys deleted");
                _rerender(renderKeys);
            } catch (e) {
                showToast("Failed: " + e.message, "error");
            }
        };

        // Toggle create form
        $("#toggle-create-key").onclick = () => {
            const f = $("#create-key-form");
            f.style.display = f.style.display === "none" ? "block" : "none";
        };

        // Submit create key
        $("#submit-create-key").onclick = async () => {
            const result = await api.post("/keys", {
                org_id: $("#key-org").value,
                user_id: $("#key-user").value || undefined,
                label: $("#key-label").value.trim(),
                provider: $("#key-provider").value,
                upstream_key: $("#key-upstream").value.trim() || undefined,
            });
            if (result.key) {
                $("#new-key-display").innerHTML = `<div class="key-display"><strong>Save this key — it won't be shown again:</strong><br><br>${esc(result.key)}</div>`;
                showToast("API key created");
            }
        };

        // Clickable rows open detail panel
        $$(".key-row").forEach(row => {
            row.onclick = () => {
                const keyId = row.dataset.id;
                const key = keys.find(k => k.id === keyId);
                if (key) _openKeyPanel(key, orgMap, userMap, budgetByKey[keyId] || null);
            };
        });

    } catch (e) {
        $content().innerHTML = `<div class="section-header"><h2>API Keys</h2></div><div class="card"><p style="color:var(--danger)">Error: ${esc(e.message)}</p></div>`;
    }
}

function _openKeyPanel(key, orgMap, userMap, budget) {
    let dialog = $("#key-detail-dialog");
    if (!dialog) {
        dialog = document.createElement("dialog");
        dialog.id = "key-detail-dialog";
        dialog.innerHTML = `
            <div class="trace-dialog-content">
                <header class="trace-dialog-header">
                    <h3>API Key Details</h3>
                    <button class="trace-close" id="key-panel-close" aria-label="Close">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </header>
                <div id="key-panel-body" class="trace-body"></div>
            </div>
        `;
        document.body.appendChild(dialog);
    }

    const body = $("#key-panel-body");
    const orgName = orgMap[key.org_id]?.name || key.org_id;
    const userName = userMap[key.user_id]?.email || "None";

    body.innerHTML = `
        <!-- Key identity -->
        <div class="user-panel-identity">
            <div class="user-panel-avatar" style="background:var(--text-secondary)">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 11-7.778 7.778 5.5 5.5 0 017.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/></svg>
            </div>
            <div>
                <div class="user-panel-name">${esc(key.label || key.key_prefix)}</div>
                <div class="user-panel-email"><code>${esc(key.key_prefix)}...</code></div>
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
                    <span class="trace-stat-value">${esc(userName)}</span>
                    <span class="trace-stat-label">User</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value"><span class="audit-provider-badge provider-${esc(key.provider)}">${esc(key.provider)}</span></span>
                    <span class="trace-stat-label">Provider</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value status-${key.is_active ? 'ok' : 'err'}">${key.blacklist_reason ? "Blacklisted" : key.is_active ? "Active" : "Revoked"}</span>
                    <span class="trace-stat-label">Status</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value">${key.block_count || 0}</span>
                    <span class="trace-stat-label">Shield Blocks</span>
                </div>
                <div class="trace-stat">
                    <span class="trace-stat-value">${timeAgo(key.last_used_at) || "Never"}</span>
                    <span class="trace-stat-label">Last Used</span>
                </div>
            </div>
        </div>

        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                Upstream API Key
            </div>
            <div class="user-panel-form" id="kp-upstream-section">
                <p class="text-muted" style="margin:0 0 8px;font-size:0.78rem">
                    ${key.has_upstream_key
                        ? 'An upstream key is configured. Enter a new value to replace it.'
                        : 'No upstream key — proxy will fall back to <code>OPENAI_API_KEY</code> env var or passthrough.'}
                </p>
                <div class="form-group">
                    <label>Upstream Key</label>
                    <input type="password" id="kp-upstream-key" placeholder="${key.has_upstream_key ? '••••••••  (replace)' : 'sk-...'}" value="">
                </div>
                <div class="user-panel-btn-row">
                    <button class="btn btn-primary btn-sm" id="kp-save-upstream">Save Upstream Key</button>
                    ${key.has_upstream_key ? '<button class="btn btn-outline-danger btn-sm" id="kp-remove-upstream">Remove</button>' : ''}
                </div>
            </div>
        </div>

        <div class="trace-flat-section">
            <div class="trace-flat-label">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/></svg>
                Budget
            </div>
            <div class="user-panel-form" id="kp-budget-section">
                ${_renderKeyBudgetSection(budget, key)}
            </div>
        </div>

        <div class="trace-flat-section user-panel-actions">
            ${key.blacklist_reason
                ? `<div class="blacklist-reason" style="background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);border-radius:8px;padding:12px;margin-bottom:12px">
                    <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;color:#ef4444;font-weight:600;font-size:0.82rem">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg>
                        Auto-Blacklisted
                    </div>
                    <p style="margin:0;font-size:0.78rem;color:var(--text-secondary)">${esc(key.blacklist_reason)}</p>
                  </div>
                  <button class="btn btn-primary btn-sm" id="kp-reactivate">Reactivate Key</button>`
                : key.is_active
                    ? `<button class="btn btn-danger btn-sm" id="kp-revoke">Revoke Key</button>`
                    : `<button class="btn btn-primary btn-sm" id="kp-reactivate">Reactivate Key</button>`
            }
        </div>
    `;

    // Wire up actions
    _wireKeyPanelActions(key, budget);

    dialog.showModal();
    $("#key-panel-close").onclick = () => dialog.close();
    dialog.onclick = (e) => { if (e.target === dialog) dialog.close(); };
}

function _renderKeyBudgetSection(budget, key) {
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
                <input type="number" id="kp-budget-limit" value="${budget.monthly_limit_usd}" step="0.01" min="0">
            </div>
            <div class="form-group">
                <label>Action</label>
                <div class="budget-mode-toggle" id="kp-budget-mode">
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
                <button class="btn btn-primary btn-sm" id="kp-save-budget">Update Budget</button>
                <button class="btn btn-secondary btn-sm" id="kp-reset-budget">Reset Usage</button>
                <button class="btn btn-danger btn-sm" id="kp-delete-budget">Remove Budget</button>
            </div>
        `;
    }

    return `
        <p class="text-muted" style="margin:0 0 12px">No budget assigned to this key.</p>
        <div class="form-group">
            <label>Monthly Limit (USD)</label>
            <input type="number" id="kp-budget-limit" value="10.00" step="0.01" min="0">
        </div>
        <div class="form-group">
            <label>Action</label>
            <div class="budget-mode-toggle" id="kp-budget-mode">
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
        <button class="btn btn-primary btn-sm" id="kp-assign-budget">Assign Budget</button>
    `;
}

function _wireKeyPanelActions(key, budget) {
    // Budget mode toggle buttons
    const modeToggle = $("#kp-budget-mode");
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

    // Revoke
    const revokeBtn = $("#kp-revoke");
    if (revokeBtn) {
        revokeBtn.onclick = async () => {
            if (!confirm("Revoke this API key? This cannot be undone.")) return;
            try {
                await api.del(`/keys/${key.id}`);
                showToast("Key revoked");
                $("#key-detail-dialog").close();
                _rerender(renderKeys);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    }

    // Reactivate (blacklisted or revoked keys)
    const reactivateBtn = $("#kp-reactivate");
    if (reactivateBtn) {
        reactivateBtn.onclick = async () => {
            try {
                await api.post(`/keys/${key.id}/reactivate`);
                showToast("Key reactivated", "success");
                $("#key-detail-dialog").close();
                _rerender(renderKeys);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    }

    // Upstream key
    const saveUpstreamBtn = $("#kp-save-upstream");
    if (saveUpstreamBtn) {
        saveUpstreamBtn.onclick = async () => {
            const val = $("#kp-upstream-key").value.trim();
            if (!val) { showToast("Enter an upstream API key", "error"); return; }
            try {
                await api.patch(`/keys/${key.id}`, { upstream_key: val });
                showToast("Upstream key updated", "success");
                $("#key-detail-dialog").close();
                _rerender(renderKeys);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    }
    const removeUpstreamBtn = $("#kp-remove-upstream");
    if (removeUpstreamBtn) {
        removeUpstreamBtn.onclick = async () => {
            try {
                await api.patch(`/keys/${key.id}`, { upstream_key: "" });
                showToast("Upstream key removed");
                $("#key-detail-dialog").close();
                _rerender(renderKeys);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    }

    // Budget actions
    if (budget) {
        $("#kp-save-budget").onclick = async () => {
            try {
                await api.patch(`/budgets/${budget.id}`, {
                    monthly_limit_usd: $("#kp-budget-limit").value !== '' ? parseFloat($("#kp-budget-limit").value) : 10.0,
                    enforce: _getEnforce(),
                });
                showToast("Budget updated");
                $("#key-detail-dialog").close();
                _rerender(renderKeys);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
        $("#kp-reset-budget").onclick = async () => {
            try {
                await api.post(`/budgets/${budget.id}/reset`);
                showToast("Budget reset");
                $("#key-detail-dialog").close();
                _rerender(renderKeys);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
        $("#kp-delete-budget").onclick = async () => {
            if (!confirm("Remove budget for this key?")) return;
            try {
                await api.del(`/budgets/${budget.id}`);
                showToast("Budget removed");
                $("#key-detail-dialog").close();
                _rerender(renderKeys);
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };
    } else {
        const assignBtn = $("#kp-assign-budget");
        if (assignBtn) {
            assignBtn.onclick = async () => {
                try {
                    await api.post("/budgets", {
                        api_key_id: key.id,
                        monthly_limit_usd: $("#kp-budget-limit").value !== '' ? parseFloat($("#kp-budget-limit").value) : 10.0,
                        enforce: _getEnforce(),
                    });
                    showToast("Budget assigned");
                    $("#key-detail-dialog").close();
                    _rerender(renderKeys);
                } catch (e) { showToast("Error: " + e.message, "error"); }
            };
        }
    }
}
