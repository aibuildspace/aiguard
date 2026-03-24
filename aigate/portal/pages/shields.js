// ── Shields ─────────────────────────────────────────────────────────────────

let _shieldsViewMode = localStorage.getItem("gk_shields_view") || "tiles";

const _shieldIcons = {
    pii_detection: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>`,
    prompt_injection: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
    jailbreak: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>`,
    content_policy: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/></svg>`,
    _default: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
    _llm: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>`,
};

function _getShieldIcon(id) {
    return _shieldIcons[id] || _shieldIcons._default;
}

function _severityColor(sev) {
    const m = { high: "danger", critical: "danger", medium: "warning", low: "success" };
    return m[sev] || "primary";
}

async function renderShields() {
    $content().innerHTML = `<div class="section-header"><h2>Shields</h2></div><p style="color:var(--text-muted)">Loading...</p>`;
    try {
        const [shields, llmShields] = await Promise.all([
            api.get("/shields"),
            api.get("/llm-shields"),
        ]);
        $content().innerHTML = `
            <div class="section-header">
                <h2>Shields</h2>
                <div class="shields-header-actions">
                    <div class="shields-view-toggle">
                        <button class="btn-icon btn-view ${_shieldsViewMode === 'tiles' ? 'active' : ''}" id="shields-view-tiles" title="Tile view">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                        </button>
                        <button class="btn-icon btn-view ${_shieldsViewMode === 'list' ? 'active' : ''}" id="shields-view-list" title="List view">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
                        </button>
                    </div>
                    <button class="btn btn-secondary btn-sm" id="reload-shields">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
                        Reload
                    </button>
                </div>
            </div>

            <!-- Tile View -->
            <div class="shields-tiles ${_shieldsViewMode === 'tiles' ? '' : 'hidden'}" id="shields-tiles">
                ${shields.map(s => `
                    <div class="shield-tile ${s.enabled ? '' : 'shield-tile-disabled'}" data-id="${esc(s.id)}" tabindex="0">
                        <div class="shield-tile-header">
                            <div class="shield-tile-icon severity-${_severityColor(s.severity)}">
                                ${_getShieldIcon(s.id)}
                            </div>
                            <label class="shield-toggle" title="${s.enabled ? 'Active' : 'Inactive'}">
                                <input type="checkbox" ${s.enabled ? 'checked' : ''} data-shield-toggle="${esc(s.id)}">
                                <span class="shield-toggle-track"></span>
                            </label>
                        </div>
                        <div class="shield-tile-body">
                            <div class="shield-tile-name">${esc(s.name)}</div>
                            <div class="shield-tile-desc">${esc(s.description || s.phase)}</div>
                        </div>
                        <div class="shield-tile-footer">
                            ${badge(s.severity, s.severity)}
                            ${badge(s.default_action, s.default_action === "block" ? "blocked" : s.default_action === "warn" ? "warned" : "clean")}
                            <span class="shield-tile-patterns">${s.pattern_count} pattern${s.pattern_count !== 1 ? 's' : ''}</span>
                        </div>
                    </div>
                `).join("")}
            </div>

            <!-- List View -->
            <div class="shields-list-wrap ${_shieldsViewMode === 'list' ? '' : 'hidden'}" id="shields-list">
                <div class="table-wrap">
                    <table>
                        <thead><tr><th></th><th>Name</th><th>Version</th><th>Severity</th><th>Action</th><th>Patterns</th><th>Logic</th><th>Active</th></tr></thead>
                        <tbody>
                            ${shields.map(s => `<tr class="shield-list-row ${s.enabled ? '' : 'shield-row-disabled'}" data-id="${esc(s.id)}">
                                <td><span class="shield-list-icon severity-${_severityColor(s.severity)}">${_getShieldIcon(s.id)}</span></td>
                                <td><strong>${esc(s.name)}</strong><br><span style="font-size:0.72rem;color:var(--text-muted)">${esc(s.id)}</span></td>
                                <td>${esc(s.version)}</td>
                                <td>${badge(s.severity, s.severity)}</td>
                                <td>${badge(s.default_action, s.default_action === "block" ? "blocked" : s.default_action === "warn" ? "warned" : "clean")}</td>
                                <td>${s.pattern_count || 0}</td>
                                <td>${s.has_logic_module ? badge("yes", "active") : "-"}</td>
                                <td><label class="shield-toggle"><input type="checkbox" ${s.enabled ? 'checked' : ''} data-shield-toggle="${esc(s.id)}"><span class="shield-toggle-track"></span></label></td>
                            </tr>`).join("")}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- LLM Shields Section -->
            <div class="llm-shields-section">
                <div class="section-header" style="margin-top:32px">
                    <h3 style="display:flex;align-items:center;gap:8px">
                        ${_shieldIcons._llm}
                        LLM Shields
                    </h3>
                    <div class="shields-header-actions">
                        <button class="btn btn-secondary btn-sm" id="seed-llm-defaults">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                            Seed Defaults
                        </button>
                        <button class="btn btn-primary btn-sm" id="create-llm-shield">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                            New LLM Shield
                        </button>
                    </div>
                </div>
                <p class="llm-shields-desc" style="color:var(--text-muted);font-size:0.85rem;margin:-8px 0 16px">
                    LLM shields use an AI model to evaluate content against custom rules. Requires a <a href="#settings">Shield LLM Key</a> in Settings.
                </p>
                ${llmShields.length === 0 ? `
                    <div class="llm-shields-empty">
                        <p style="color:var(--text-muted);text-align:center;padding:24px">No LLM shields yet. Click <strong>Seed Defaults</strong> for examples or <strong>New LLM Shield</strong> to create one.</p>
                    </div>
                ` : `
                    <div class="shields-tiles" id="llm-shields-tiles">
                        ${llmShields.map(s => `
                            <div class="shield-tile llm-shield-tile ${s.enabled ? '' : 'shield-tile-disabled'}" data-llm-id="${esc(s.id)}" tabindex="0">
                                <div class="shield-tile-header">
                                    <div class="shield-tile-icon severity-${_severityColor(s.severity)}">
                                        ${_shieldIcons._llm}
                                    </div>
                                    <label class="shield-toggle" title="${s.enabled ? 'Active' : 'Inactive'}">
                                        <input type="checkbox" ${s.enabled ? 'checked' : ''} data-llm-toggle="${esc(s.id)}">
                                        <span class="shield-toggle-track"></span>
                                    </label>
                                </div>
                                <div class="shield-tile-body">
                                    <div class="shield-tile-name">${esc(s.name)}</div>
                                    <div class="shield-tile-desc">${esc(s.description || 'LLM-based shield')}</div>
                                </div>
                                <div class="shield-tile-footer">
                                    ${badge(s.severity, s.severity)}
                                    ${badge(s.default_action, s.default_action === "block" ? "blocked" : s.default_action === "warn" ? "warned" : "clean")}
                                    <span class="shield-tile-patterns" style="font-size:0.72rem">${esc(s.model)}</span>
                                </div>
                            </div>
                        `).join("")}
                    </div>
                `}
            </div>

            <!-- Shield Detail Dialog (slide-out) -->
            <dialog id="shield-detail-dialog">
                <div class="shield-dialog-content">
                    <header class="shield-dialog-header">
                        <h3 id="shield-dialog-title">Shield Details</h3>
                        <button class="trace-close" id="shield-dialog-close" aria-label="Close">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </header>
                    <div class="shield-dialog-body" id="shield-dialog-body"></div>
                </div>
            </dialog>

            <!-- LLM Shield Create/Edit Dialog -->
            <dialog id="llm-shield-dialog">
                <div class="shield-dialog-content">
                    <header class="shield-dialog-header">
                        <h3 id="llm-shield-dialog-title">New LLM Shield</h3>
                        <button class="trace-close" id="llm-shield-dialog-close" aria-label="Close">
                            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                        </button>
                    </header>
                    <div class="shield-dialog-body" id="llm-shield-dialog-body"></div>
                </div>
            </dialog>
        `;

        // View toggle
        function setView(mode) {
            _shieldsViewMode = mode;
            localStorage.setItem("gk_shields_view", mode);
            $("#shields-tiles").classList.toggle("hidden", mode !== "tiles");
            $("#shields-list").classList.toggle("hidden", mode !== "list");
            $("#shields-view-tiles").classList.toggle("active", mode === "tiles");
            $("#shields-view-list").classList.toggle("active", mode === "list");
        }
        $("#shields-view-tiles").onclick = () => setView("tiles");
        $("#shields-view-list").onclick = () => setView("list");

        // Reload
        $("#reload-shields").onclick = async () => {
            await api.post("/shields/reload", {});
            showToast("Shields reloaded");
            _rerender(renderShields);
        };

        // Shield detail dialog
        const dialog = $("#shield-detail-dialog");
        function openShieldDetail(id) {
            const s = shields.find(sk => sk.id === id);
            if (!s) return;
            $("#shield-dialog-title").textContent = s.name;
            $("#shield-dialog-body").innerHTML = _renderShieldDetail(s);
            dialog.showModal();

            // Wire up save button
            const saveBtn = $("#shield-save-btn");
            if (saveBtn) {
                saveBtn.onclick = async () => {
                    const action = $("#shield-edit-action").value;
                    const severity = $("#shield-edit-severity").value;
                    const desc = $("#shield-edit-desc").value.trim();
                    const patch = {};
                    if (action !== s.default_action) patch.default_action = action;
                    if (severity !== s.severity) patch.severity = severity;
                    if (desc !== (s.description || "")) patch.description = desc;
                    if (!Object.keys(patch).length) { showToast("No changes to save", "info"); return; }
                    try {
                        saveBtn.disabled = true;
                        saveBtn.textContent = "Saving...";
                        await api.patch(`/shields/${s.id}`, patch);
                        showToast("Shield updated", "success");
                        dialog.close();
                        _rerender(renderShields);
                    } catch (e) {
                        showToast("Save failed: " + e.message, "error");
                        saveBtn.disabled = false;
                        saveBtn.textContent = "Save Changes";
                    }
                };
            }

            // Wire up test button inside dialog
            const testBtn = $("#shield-test-run");
            if (testBtn) {
                testBtn.onclick = async () => {
                    const msg = $("#shield-test-input").value.trim();
                    if (!msg) return;
                    try {
                        const result = await api.post(`/shields/test/${s.id}`, { messages: [{ role: "user", content: msg }], model: "test" });
                        const cls = result.triggered ? "blocked" : "clean";
                        $("#shield-test-result").innerHTML = `
                            <div class="shield-test-outcome ${cls}">
                                ${result.triggered ? "TRIGGERED" : "CLEAN"}
                            </div>
                            ${result.findings?.length ? `<div class="shield-test-findings">
                                ${result.findings.map(f => `<div class="shield-finding-row">
                                    <span class="shield-finding-pattern">${esc(f.pattern_id)}</span>
                                    <span>${badge(f.action, f.action === "block" ? "blocked" : "warned")}</span>
                                    <code>${esc(f.matched_text)}</code>
                                </div>`).join("")}
                            </div>` : ""}
                        `;
                    } catch (e) {
                        $("#shield-test-result").innerHTML = `<p style="color:var(--danger);font-size:0.85rem;">Error: ${esc(e.message)}</p>`;
                    }
                };
            }
        }

        $("#shield-dialog-close").onclick = () => dialog.close();
        dialog.addEventListener("click", (e) => { if (e.target === dialog) dialog.close(); });

        // Click handlers on tiles (file-based shields only) — ignore toggle clicks
        $$(".shield-tile:not(.llm-shield-tile)").forEach(tile => {
            tile.onclick = (e) => { if (e.target.closest(".shield-toggle")) return; openShieldDetail(tile.dataset.id); };
            tile.onkeydown = (e) => { if (e.key === "Enter" && !e.target.closest(".shield-toggle")) openShieldDetail(tile.dataset.id); };
        });

        // Click handlers on list rows — ignore toggle clicks
        $$(".shield-list-row").forEach(row => {
            row.style.cursor = "pointer";
            row.onclick = (e) => { if (e.target.closest(".shield-toggle")) return; openShieldDetail(row.dataset.id); };
        });

        // ── Toggle handlers for file-based shields ───────────────────────
        $$("[data-shield-toggle]").forEach(input => {
            input.onchange = async (e) => {
                e.stopPropagation();
                const sid = input.dataset.shieldToggle;
                const enabled = input.checked;
                const tile = input.closest('.shield-tile, .shield-list-row');
                try {
                    await api.patch(`/shields/${sid}`, { enabled });
                    if (tile) { tile.classList.toggle('shield-tile-disabled', !enabled); tile.classList.toggle('shield-row-disabled', !enabled); }
                    showToast(`${sid} ${enabled ? 'enabled' : 'disabled'}`, "success");
                } catch (err) {
                    showToast("Failed: " + err.message, "error");
                    input.checked = !enabled;
                }
            };
            input.onclick = (e) => e.stopPropagation();
        });

        // ── Toggle handlers for LLM shields ──────────────────────────────
        $$("[data-llm-toggle]").forEach(input => {
            input.onchange = async (e) => {
                e.stopPropagation();
                const sid = input.dataset.llmToggle;
                const enabled = input.checked;
                const tile = input.closest('.shield-tile');
                try {
                    await api.patch(`/llm-shields/${sid}`, { enabled });
                    if (tile) tile.classList.toggle('shield-tile-disabled', !enabled);
                    showToast(`${sid} ${enabled ? 'enabled' : 'disabled'}`, "success");
                } catch (err) {
                    showToast("Failed: " + err.message, "error");
                    input.checked = !enabled;
                }
            };
            input.onclick = (e) => e.stopPropagation();
        });

        // ── LLM Shield handlers ─────────────────────────────────────────
        const llmDialog = $("#llm-shield-dialog");
        $("#llm-shield-dialog-close").onclick = () => llmDialog.close();
        llmDialog.addEventListener("click", (e) => { if (e.target === llmDialog) llmDialog.close(); });

        // Seed defaults
        $("#seed-llm-defaults").onclick = async () => {
            try {
                const res = await api.post("/llm-shields/seed-defaults");
                if (res.created?.length) {
                    showToast(`Created ${res.created.length} default shield(s)`, "success");
                    _rerender(renderShields);
                } else {
                    showToast("Default shields already exist", "info");
                }
            } catch (e) { showToast("Error: " + e.message, "error"); }
        };

        // Create new LLM shield
        $("#create-llm-shield").onclick = () => _openLlmShieldForm(null, llmDialog);

        // Click on LLM shield tile → edit (ignore toggle clicks)
        $$(".llm-shield-tile").forEach(tile => {
            tile.onclick = (e) => {
                if (e.target.closest(".shield-toggle")) return;
                const s = llmShields.find(x => x.id === tile.dataset.llmId);
                if (s) _openLlmShieldForm(s, llmDialog);
            };
            tile.onkeydown = (e) => { if (e.key === "Enter" && !e.target.closest(".shield-toggle")) tile.click(); };
        });

    } catch (e) {
        $content().innerHTML = `<div class="section-header"><h2>Shields</h2></div><div class="card"><p style="color:var(--danger)">Error: ${esc(e.message)}</p></div>`;
    }
}

function _renderShieldDetail(s) {
    const actions = ["block", "warn", "sanitize", "log", "pass"];
    const severities = ["critical", "high", "medium", "low", "info"];

    return `
        <!-- Overview -->
        <div class="shield-detail-overview">
            <div class="shield-detail-icon severity-${_severityColor(s.severity)}">
                ${_getShieldIcon(s.id)}
            </div>
            <div class="shield-detail-info">
                <div class="shield-detail-name">${esc(s.name)}</div>
                <div class="shield-detail-id"><code>${esc(s.id)}</code> &middot; v${esc(s.version)}</div>
            </div>
        </div>

        <!-- Status badges -->
        <div class="shield-detail-badges">
            ${badge(s.severity, s.severity)}
            ${badge(s.default_action, s.default_action === "block" ? "blocked" : s.default_action === "warn" ? "warned" : "clean")}
            ${badge(s.phase, "info")}
            ${s.has_logic_module ? badge("logic", "active") : ""}
        </div>

        <!-- Edit Configuration -->
        <details class="trace-collapse" open>
            <summary class="trace-collapse-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
                Configuration
            </summary>
            <div class="trace-collapse-body">
                <div class="shield-edit-form">
                    <div class="shield-edit-row">
                        <div class="form-group">
                            <label>Default Action</label>
                            <select id="shield-edit-action">
                                ${actions.map(a => `<option value="${a}" ${a === s.default_action ? "selected" : ""}>${a}</option>`).join("")}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Severity</label>
                            <select id="shield-edit-severity">
                                ${severities.map(sv => `<option value="${sv}" ${sv === s.severity ? "selected" : ""}>${sv}</option>`).join("")}
                            </select>
                        </div>
                    </div>
                    <div class="form-group">
                        <label>Description</label>
                        <textarea id="shield-edit-desc" rows="2" style="font-size:0.85rem;">${esc(s.description || "")}</textarea>
                    </div>
                    <button class="btn btn-primary btn-sm" id="shield-save-btn" style="width:100%">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                        Save Changes
                    </button>
                </div>
            </div>
        </details>

        <!-- Info (read-only) -->
        <details class="trace-collapse">
            <summary class="trace-collapse-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                Details
            </summary>
            <div class="trace-collapse-body">
                <div class="shield-config-grid">
                    <div class="shield-config-item">
                        <label>Phase</label>
                        <span class="mono">${esc(s.phase)}</span>
                    </div>
                    <div class="shield-config-item">
                        <label>Patterns</label>
                        <span>${s.pattern_count}</span>
                    </div>
                    <div class="shield-config-item">
                        <label>Logic Module</label>
                        <span>${s.has_logic_module ? badge("yes", "active") : badge("no", "inactive")}</span>
                    </div>
                    <div class="shield-config-item">
                        <label>Tags</label>
                        <span>${s.tags?.length ? s.tags.map(t => `<span class="badge badge-info" style="margin-right:2px">${esc(t)}</span>`).join("") : "<span class='text-muted'>none</span>"}</span>
                    </div>
                </div>
            </div>
        </details>

        <!-- Quick Test -->
        <details class="trace-collapse">
            <summary class="trace-collapse-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Quick Test
            </summary>
            <div class="trace-collapse-body">
                <div class="form-group" style="margin-bottom:8px">
                    <textarea id="shield-test-input" rows="3" placeholder="Enter a test message..." style="font-size:0.85rem;"></textarea>
                </div>
                <button class="btn btn-primary btn-sm" id="shield-test-run" style="width:100%">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Run Test
                </button>
                <div id="shield-test-result" style="margin-top:10px;"></div>
            </div>
        </details>

        <!-- Source info -->
        <details class="trace-collapse">
            <summary class="trace-collapse-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
                Source
            </summary>
            <div class="trace-collapse-body">
                <div class="shield-config-item">
                    <label>Directory</label>
                    <code style="font-size:0.78rem;word-break:break-all">${esc(s.shield_dir)}</code>
                </div>
            </div>
        </details>
    `;
}


// ── LLM Shield Form (create / edit) ─────────────────────────────────────────

function _openLlmShieldForm(existing, dialog) {
    const isEdit = !!existing;
    const s = existing || { name: "", description: "", system_prompt: "", model: "gpt-4o-mini", provider: "openai", default_action: "warn", severity: "medium", enabled: true };
    const actions = ["block", "warn", "log", "pass"];
    const severities = ["critical", "high", "medium", "low", "info"];
    const models = ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "claude-haiku-4-20250414", "claude-sonnet-4-20250514"];

    $("#llm-shield-dialog-title").textContent = isEdit ? s.name : "New LLM Shield";
    $("#llm-shield-dialog-body").innerHTML = `
        ${isEdit ? `
        <!-- Overview -->
        <div class="shield-detail-overview">
            <div class="shield-detail-icon severity-${_severityColor(s.severity)}">
                ${_shieldIcons._llm}
            </div>
            <div class="shield-detail-info">
                <div class="shield-detail-name">${esc(s.name)}</div>
                <div class="shield-detail-id"><code>${esc(s.id)}</code> &middot; ${esc(s.model)}</div>
            </div>
        </div>
        <div class="shield-detail-badges">
            ${badge(s.severity, s.severity)}
            ${badge(s.default_action, s.default_action === "block" ? "blocked" : s.default_action === "warn" ? "warned" : "clean")}
            ${badge(s.provider, "info")}
            ${badge("llm", "active")}
        </div>
        ` : ""}

        <!-- Configuration -->
        <details class="trace-collapse" ${isEdit ? '' : 'open'}>
            <summary class="trace-collapse-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>
                Configuration
            </summary>
            <div class="trace-collapse-body">
                <div class="shield-edit-form">
                    <div class="form-group">
                        <label>Name</label>
                        <input type="text" id="llm-s-name" value="${esc(s.name)}" placeholder="e.g. Topic Guardrail" ${isEdit ? 'disabled style="opacity:0.6"' : ''}>
                    </div>
                    <div class="form-group">
                        <label>Description</label>
                        <input type="text" id="llm-s-desc" value="${esc(s.description)}" placeholder="Brief description of what this shield checks">
                    </div>
                    <div class="shield-edit-row">
                        <div class="form-group">
                            <label>Default Action</label>
                            <select id="llm-s-action">
                                ${actions.map(a => `<option value="${a}" ${a === s.default_action ? "selected" : ""}>${a}</option>`).join("")}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Severity</label>
                            <select id="llm-s-severity">
                                ${severities.map(sv => `<option value="${sv}" ${sv === s.severity ? "selected" : ""}>${sv}</option>`).join("")}
                            </select>
                        </div>
                    </div>
                    <div class="shield-edit-row">
                        <div class="form-group">
                            <label>Model</label>
                            <select id="llm-s-model">
                                ${models.map(m => `<option value="${m}" ${m === s.model ? "selected" : ""}>${m}</option>`).join("")}
                            </select>
                        </div>
                        <div class="form-group">
                            <label>Provider</label>
                            <select id="llm-s-provider">
                                <option value="openai" ${s.provider === "openai" ? "selected" : ""}>OpenAI</option>
                                <option value="anthropic" ${s.provider === "anthropic" ? "selected" : ""}>Anthropic</option>
                            </select>
                        </div>
                    </div>
                    <div class="form-group" style="display:flex;align-items:center;gap:8px">
                        <label style="margin:0">Enabled</label>
                        <input type="checkbox" id="llm-s-enabled" ${s.enabled ? "checked" : ""} style="width:auto">
                    </div>
                    <button class="btn btn-primary btn-sm" id="llm-s-save" style="width:100%;margin-top:4px">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                        ${isEdit ? "Save Changes" : "Create Shield"}
                    </button>
                </div>
            </div>
        </details>

        <!-- System Prompt -->
        <details class="trace-collapse" ${isEdit ? '' : 'open'}>
            <summary class="trace-collapse-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>
                System Prompt
            </summary>
            <div class="trace-collapse-body">
                <p class="hint" style="margin:0 0 8px;font-size:0.78rem;color:var(--text-muted)">The evaluation criteria sent to the LLM. It will respond with pass/fail JSON.</p>
                <textarea id="llm-s-prompt" rows="10" style="font-size:0.82rem;font-family:var(--font-mono,monospace)">${esc(s.system_prompt)}</textarea>
            </div>
        </details>

        <!-- Quick Test -->
        ${isEdit ? `
        <details class="trace-collapse">
            <summary class="trace-collapse-title">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                Quick Test
            </summary>
            <div class="trace-collapse-body">
                <div class="form-group" style="margin-bottom:8px">
                    <textarea id="llm-test-input" rows="3" placeholder="Enter a test message..." style="font-size:0.85rem;"></textarea>
                </div>
                <button class="btn btn-primary btn-sm" id="llm-test-run" style="width:100%">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    Run Test
                </button>
                <div id="llm-test-result" style="margin-top:10px;"></div>
            </div>
        </details>
        ` : ""}

        <!-- Delete -->
        ${isEdit ? `
        <details class="trace-collapse">
            <summary class="trace-collapse-title" style="color:var(--danger)">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14H7L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
                Danger Zone
            </summary>
            <div class="trace-collapse-body">
                <button class="btn btn-outline-danger btn-sm" id="llm-s-delete" style="width:100%">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14H7L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>
                    Delete Shield
                </button>
            </div>
        </details>
        ` : ""}
    `;

    dialog.showModal();

    // Save
    $("#llm-s-save").onclick = async () => {
        const payload = {
            name: $("#llm-s-name").value.trim(),
            description: $("#llm-s-desc").value.trim(),
            system_prompt: $("#llm-s-prompt").value.trim(),
            model: $("#llm-s-model").value,
            provider: $("#llm-s-provider").value,
            default_action: $("#llm-s-action").value,
            severity: $("#llm-s-severity").value,
            enabled: $("#llm-s-enabled").checked,
        };
        if (!payload.name) { showToast("Name is required", "error"); return; }
        if (!payload.system_prompt) { showToast("System prompt is required", "error"); return; }

        const btn = $("#llm-s-save");
        btn.disabled = true;
        btn.textContent = isEdit ? "Saving..." : "Creating...";
        try {
            if (isEdit) {
                await api.patch(`/llm-shields/${s.id}`, payload);
                showToast("LLM shield updated", "success");
            } else {
                await api.post("/llm-shields", payload);
                showToast("LLM shield created", "success");
            }
            dialog.close();
            _rerender(renderShields);
        } catch (e) {
            showToast("Error: " + e.message, "error");
            btn.disabled = false;
            btn.textContent = isEdit ? "Save Changes" : "Create Shield";
        }
    };

    // Delete
    if (isEdit) {
        const delBtn = $("#llm-s-delete");
        if (delBtn) {
            delBtn.onclick = async () => {
                if (!confirm(`Delete LLM shield "${s.name}"?`)) return;
                try {
                    await api.del(`/llm-shields/${s.id}`);
                    showToast("LLM shield deleted", "success");
                    dialog.close();
                    _rerender(renderShields);
                } catch (e) { showToast("Error: " + e.message, "error"); }
            };
        }

        // Test
        const testBtn = $("#llm-test-run");
        if (testBtn) {
            testBtn.onclick = async () => {
                const msg = $("#llm-test-input").value.trim();
                if (!msg) return;
                testBtn.disabled = true;
                testBtn.textContent = "Evaluating...";
                try {
                    const result = await api.post(`/llm-shields/test/${s.id}`, { messages: [{ role: "user", content: msg }] });
                    const cls = result.triggered ? "blocked" : "clean";
                    $("#llm-test-result").innerHTML = `
                        <div class="shield-test-outcome ${cls}">
                            ${result.triggered ? "TRIGGERED" : "CLEAN"}
                        </div>
                        ${result.findings?.length ? `<div class="shield-test-findings">
                            ${result.findings.map(f => `<div class="shield-finding-row">
                                <span class="shield-finding-pattern">${esc(f.pattern_id)}</span>
                                <span>${badge(f.action, f.action === "block" ? "blocked" : "warned")}</span>
                                <code>${esc(f.matched_text)}</code>
                            </div>`).join("")}
                        </div>` : ""}
                    `;
                } catch (e) {
                    $("#llm-test-result").innerHTML = `<p style="color:var(--danger);font-size:0.85rem;">Error: ${esc(e.message)}</p>`;
                } finally {
                    testBtn.disabled = false;
                    testBtn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg> Run Test`;
                }
            };
        }
    }
}
