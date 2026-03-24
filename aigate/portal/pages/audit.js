// ── Audit Log ───────────────────────────────────────────────────────────────

async function renderAudit() {
    $content().innerHTML = `<div class="section-header"><h2>Audit Log</h2></div><p style="color:var(--text-muted)">Loading...</p>`;
    try {
        const orgs = await api.get("/orgs");
        $content().innerHTML = `
            <div class="section-header">
                <h2>Audit Log</h2>
                <div class="audit-header-actions">
                    <button class="btn btn-danger btn-sm" id="audit-clear" title="Clear all logs">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2"/></svg>
                        Clear
                    </button>
                    <button class="btn btn-secondary btn-sm" id="audit-refresh" title="Refresh">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
                        Refresh
                    </button>
                </div>
            </div>
            <div class="audit-filters card">
                <div class="audit-filters-row">
                    <div class="form-group compact">
                        <label>Organization</label>
                        <select id="audit-org"><option value="">All orgs</option>${orgs.map(o => `<option value="${o.id}">${esc(o.name)}</option>`).join("")}</select>
                    </div>
                    <div class="form-group compact">
                        <label>Outcome</label>
                        <select id="audit-outcome">
                            <option value="">All outcomes</option>
                            <option value="clean">Clean</option>
                            <option value="warned">Warned</option>
                            <option value="blocked">Blocked</option>
                            <option value="sanitized">Sanitized</option>
                        </select>
                    </div>
                    <div class="form-group compact">
                        <label>Provider</label>
                        <select id="audit-provider">
                            <option value="">All providers</option>
                            <option value="openai">OpenAI</option>
                            <option value="anthropic">Anthropic</option>
                        </select>
                    </div>
                    <button class="btn btn-primary" id="audit-search">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                        Search
                    </button>
                </div>
            </div>
            <div id="audit-results"></div>
            <div id="audit-pagination" class="audit-pagination"></div>
            <dialog id="trace-dialog">
                <div class="trace-dialog-content">
                    <header class="trace-dialog-header">
                        <h3>Request Trace</h3>
                        <div class="trace-header-actions">
                            <button class="trace-nav-btn" id="trace-prev" title="Previous request (←)" style="display:none">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
                            </button>
                            <span class="trace-nav-counter" id="trace-counter" style="display:none"></span>
                            <button class="trace-nav-btn" id="trace-next" title="Next request (→)" style="display:none">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 6 15 12 9 18"/></svg>
                            </button>
                            <button class="trace-close" id="trace-close" aria-label="Close">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                            </button>
                        </div>
                    </header>
                    <div id="trace-body" class="trace-body"></div>
                </div>
            </dialog>
            <dialog id="clear-confirm-dialog" class="confirm-dialog">
                <div class="confirm-dialog-content">
                    <div class="confirm-icon">
                        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    </div>
                    <h3>Clear Audit Logs</h3>
                    <p>This will permanently delete all audit log entries. This action cannot be undone.</p>
                </div>
                <div class="confirm-actions">
                    <button class="btn btn-secondary" id="clear-cancel">Cancel</button>
                    <button class="btn btn-danger" id="clear-confirm">Delete All Logs</button>
                </div>
            </dialog>
        `;
        let offset = 0;
        const limit = 50;

        async function loadAudit() {
            const p = new URLSearchParams({ limit, offset });
            const org = $("#audit-org").value, outcome = $("#audit-outcome").value, provider = $("#audit-provider").value;
            if (org) p.set("org_id", org);
            if (outcome) p.set("outcome", outcome);
            if (provider) p.set("provider", provider);

            const resultsEl = $("#audit-results");
            resultsEl.innerHTML = `<div class="audit-loading"><div class="spinner"></div> Loading...</div>`;

            const logs = await api.get(`/audit?${p}`);

            if (!logs.length) {
                resultsEl.innerHTML = `<div class="card"><div class="empty-state">No audit records match your filters</div></div>`;
                $("#audit-pagination").innerHTML = "";
                return;
            }

            // Detect trace groups (conversations with multiple requests)
            const traceCount = {};
            logs.forEach(l => { if (l.trace_id) traceCount[l.trace_id] = (traceCount[l.trace_id] || 0) + 1; });

            resultsEl.innerHTML = `<div class="audit-list">${logs.map((l, i) => {
                const isGrouped = l.trace_id && traceCount[l.trace_id] > 1;
                return `
                <div class="audit-row${isGrouped ? ' audit-row-grouped' : ''}" data-idx="${i}" ${isGrouped ? `data-trace-group="${esc(l.trace_id)}"` : ''} role="button" tabindex="0">
                    <div class="audit-row-main">
                        <div class="audit-col audit-col-outcome">
                            ${badge(l.scan_outcome, l.scan_outcome)}
                        </div>
                        <div class="audit-col audit-col-info">
                            <span class="audit-model">${esc(l.model || 'unknown')}</span>
                            <span class="audit-endpoint">${esc(l.endpoint)}</span>
                        </div>
                        <div class="audit-col audit-col-provider">
                            <span class="audit-provider-badge provider-${esc(l.provider)}">${esc(l.provider)}</span>
                        </div>
                        <div class="audit-col audit-col-shields">
                            ${(l.skills_triggered || []).map(s => `<span class="audit-shield-tag">${esc(s.shield_id || s.skill_id || s)}</span>`).join("") || '<span class="text-muted">—</span>'}
                            ${isGrouped ? `<span class="audit-trace-badge" title="Part of ${traceCount[l.trace_id]}-message conversation"><svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>${traceCount[l.trace_id]}</span>` : ''}
                        </div>
                        <div class="audit-col audit-col-meta">
                            <span class="audit-latency">${l.upstream_latency_ms != null ? l.upstream_latency_ms + 'ms' : '—'}</span>
                            <span class="audit-status status-${l.http_status < 400 ? 'ok' : l.http_status < 500 ? 'warn' : 'err'}">${l.http_status}</span>
                        </div>
                        <div class="audit-col audit-col-time">
                            <span class="audit-time">${timeAgo(l.timestamp)}</span>
                        </div>
                        <div class="audit-col audit-col-chevron">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                        </div>
                    </div>
                </div>
            `;
            }).join("")}</div>`;

            // Pagination
            $("#audit-pagination").innerHTML = `
                <span class="audit-pagination-info">Showing ${offset + 1}–${offset + logs.length}</span>
                <div class="audit-pagination-btns">
                    ${offset > 0 ? `<button class="btn btn-sm btn-secondary" id="audit-prev">← Previous</button>` : ""}
                    ${logs.length === limit ? `<button class="btn btn-sm btn-secondary" id="audit-next">Next →</button>` : ""}
                </div>
            `;
            if ($("#audit-prev")) $("#audit-prev").onclick = () => { offset = Math.max(0, offset - limit); loadAudit(); };
            if ($("#audit-next")) $("#audit-next").onclick = () => { offset += limit; loadAudit(); };

            // Click rows to open trace detail (uses shared openTraceDialog from app.js)
            $$(".audit-row").forEach((row, idx) => {
                const openTrace = () => openTraceDialog(logs[idx], logs, idx);
                row.onclick = openTrace;
                row.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openTrace(); } };
            });
        }

        // Clear audit logs
        const clearDialog = $("#clear-confirm-dialog");
        $("#audit-clear").onclick = () => clearDialog.showModal();
        $("#clear-cancel").onclick = () => clearDialog.close();
        clearDialog.onclick = (e) => { if (e.target === clearDialog) clearDialog.close(); };
        $("#clear-confirm").onclick = async () => {
            try {
                await api.del("/audit");
                clearDialog.close();
                showToast("Audit logs cleared");
                loadAudit();
            } catch (e) {
                clearDialog.close();
                showToast("Failed to clear logs: " + e.message, "error");
            }
        };

        $("#audit-search").onclick = () => { offset = 0; loadAudit(); };
        $("#audit-refresh").onclick = () => loadAudit();
        // Auto-search on filter change
        ["audit-org", "audit-outcome", "audit-provider"].forEach(id => {
            $(`#${id}`).onchange = () => { offset = 0; loadAudit(); };
        });
        loadAudit();
    } catch (e) { $content().innerHTML = `<div class="section-header"><h2>Audit Log</h2></div><div class="card"><p style="color:var(--danger)">Error: ${esc(e.message)}</p></div>`; }
}
