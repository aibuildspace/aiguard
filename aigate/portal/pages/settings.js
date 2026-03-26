// ── Settings ────────────────────────────────────────────────────────────────

async function renderSettings() {
    $content().innerHTML = '<div class="section-header"><h2>Settings</h2></div><p style="color:var(--text-muted)">Loading...</p>';

    // Load current settings + activation status in parallel
    var current = {
        grafana_enabled: false, grafana_otlp_endpoint: "", grafana_otlp_headers: "", grafana_service_name: "aigate",
    };
    var activations = { proxy_url: "http://127.0.0.1:8080", playground: { active: true }, claude_code: { installed: false, active: false, detail: "" }, openclaw: { installed: false, active: false, detail: "" } };
    try { current = { ...current, ...(await api.get("/settings")) }; } catch (_) {}
    try { activations = { ...activations, ...(await api.get("/activations")) }; } catch (_) {}

    // Decode stored Basic auth header
    var _instanceId = "", _apiToken = "";
    if (current.grafana_otlp_headers && current.grafana_otlp_headers.startsWith("Basic ")) {
        try {
            var decoded = atob(current.grafana_otlp_headers.slice(6));
            var sep = decoded.indexOf(":");
            if (sep > 0) { _instanceId = decoded.slice(0, sep); _apiToken = decoded.slice(sep + 1); }
        } catch (_) {}
    }
    var grafanaConfigured = !!(current.grafana_otlp_endpoint && _instanceId && _apiToken);

    // ── Tool row builder ─────────────────────────────────────────────────
    function _toolRow(img, name, desc, tool, idPrefix) {
        var st = activations[tool];
        if (!st) return "";
        var slug = (idPrefix ? idPrefix + "-" : "") + tool.replace("_", "-");
        var installed = st.installed !== false;
        var actionsHtml = "";
        var cliHint = "";

        if (!installed) {
            actionsHtml = '<span class="activation-badge not-installed">Not Installed</span>';
        } else if (st.active) {
            actionsHtml = '<span id="' + slug + '-badge"><span class="activation-badge active">Active</span></span>';
        } else {
            actionsHtml = '<span id="' + slug + '-badge"><span class="activation-badge inactive">Inactive</span></span>';
        }

        if (installed && !idPrefix) {
            var cmd = tool === "claude_code" ? "aigate setup claude" : "aigate setup openclaw";
            cliHint = '<p class="activation-cli-hint"><code>' + cmd + '</code></p>';
        }

        return '<div class="activation-row">'
            + '<img src="/portal/static/' + img + '" class="activation-logo" alt="' + name + '">'
            + '<div class="activation-info">'
            +   '<span class="activation-name">' + name + '</span>'
            +   '<span class="activation-desc">' + desc + '</span>'
            + '</div>'
            + '<div class="activation-actions">' + actionsHtml + '</div>'
            + '<div class="activation-detail-wrap">'
            +   cliHint
            +   '<p class="activation-detail" id="' + slug + '-detail">' + esc(st.detail) + '</p>'
            + '</div>'
            + '</div>';
    }

    // ── Grafana helpers ──────────────────────────────────────────────────
    function _grafanaTraceSection() {
        if (!grafanaConfigured) {
            return '<div class="grafana-not-configured">'
                + '<p class="grafana-setup-msg"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg> Grafana tracing is not configured yet. Enter your OTLP details below to activate.</p>'
                + '</div>'
                + _grafanaFields()
                + '<div class="settings-actions">'
                +   '<button class="btn btn-primary btn-sm" id="grafana-save">Activate</button>'
                +   '<button class="btn btn-secondary btn-sm" id="grafana-test">Test Connection</button>'
                +   '<span class="settings-status" id="grafana-status"></span>'
                + '</div>';
        }
        return _grafanaFields()
            + '<div class="settings-actions">'
            +   '<button class="btn btn-primary btn-sm" id="grafana-save">Save</button>'
            +   '<button class="btn btn-secondary btn-sm" id="grafana-test">Test Connection</button>'
            +   '<button class="btn btn-outline-danger btn-sm" id="grafana-deactivate">Deactivate</button>'
            +   '<span class="settings-status" id="grafana-status"></span>'
            + '</div>'
            + '<div class="activation-grid" style="margin-top:16px">'
            + '<p class="trace-toggles-label">Activate for Telemetry</p>'
            + '<div class="activation-row">'
            +   '<img src="/portal/static/shield256.png" class="activation-logo" alt="AIGate">'
            +   '<div class="activation-info"><span class="activation-name">Chat Playground</span><span class="activation-desc">Built-in test chat &mdash; always proxied</span></div>'
            +   '<div class="activation-actions"><span class="activation-badge active">Active</span><a href="#chat" class="btn btn-secondary btn-xs">Open</a></div>'
            + '</div>'
            + _toolRow("claude.webp", "Claude Code CLI", "Routes via <code>ANTHROPIC_BASE_URL</code>", "claude_code", "gf")
            + _toolRow("openclaw.png", "OpenClaw", "Routes providers via <code>auth-profiles.json</code>", "openclaw", "gf")
            + '</div>';
    }

    function _grafanaFields() {
        return '<div id="grafana-fields">'
            + '<div class="settings-form-group"><label for="grafana-endpoint">OTLP Endpoint</label><input type="url" id="grafana-endpoint" placeholder="https://otlp-gateway-prod-{region}.grafana.net/otlp" value="' + esc(current.grafana_otlp_endpoint) + '"><p class="hint">OTLP gateway URL</p></div>'
            + '<div class="settings-form-row">'
            +   '<div class="settings-form-group" style="flex:1"><label for="grafana-instance-id">Instance ID</label><input type="text" id="grafana-instance-id" placeholder="123456" value="' + esc(_instanceId) + '"><p class="hint">Stack Instance ID</p></div>'
            +   '<div class="settings-form-group" style="flex:2"><label for="grafana-api-token">API Token</label><input type="password" id="grafana-api-token" placeholder="glc_eyJv..." value="' + esc(_apiToken) + '"><p class="hint">Token with <code>traces:write</code> scope</p></div>'
            + '</div>'
            + '<div class="settings-form-group"><label for="grafana-service">Service Name</label><input type="text" id="grafana-service" placeholder="aigate" value="' + esc(current.grafana_service_name) + '"></div>'
            + '</div>';
    }

    // ── Build page HTML ──────────────────────────────────────────────────
    var html = ''
    + '<div class="section-header"><h2>Settings</h2></div>'
    + '<div class="settings-page">'

    // Proxy Activation card
    + '<div class="settings-card">'
    +   '<div class="settings-card-header">'
    +     '<div class="settings-card-icon" style="background:var(--primary-bg);color:var(--primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg></div>'
    +     '<div><h3 class="settings-card-title">Tool Integrations</h3><p class="settings-card-desc">Route LLM traffic through the shield &middot; <code class="proxy-url-code">' + esc(activations.proxy_url) + '</code></p></div>'
    +   '</div>'
    +   '<div class="activation-grid">'
    +     '<div class="activation-row">'
    +       '<img src="/portal/static/shield256.png" class="activation-logo" alt="AIGate">'
    +       '<div class="activation-info"><span class="activation-name">Chat Playground</span><span class="activation-desc">Built-in test chat &mdash; always proxied</span></div>'
    +       '<div class="activation-actions"><span class="activation-badge active">Active</span><a href="#chat" class="btn btn-secondary btn-xs">Open</a></div>'
    +     '</div>'
    +     _toolRow("claude.webp", "Claude Code CLI", "Routes via <code>ANTHROPIC_BASE_URL</code> in <code>~/.claude/settings.json</code>", "claude_code")
    +     _toolRow("openclaw.png", "OpenClaw", "Routes providers via <code>auth-profiles.json</code>", "openclaw")
    +   '</div>'
    + '</div>'

    // Grafana Integration card
    + '<div class="settings-card">'
    +   '<div class="settings-card-header">'
    +     '<div class="settings-card-icon grafana"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg></div>'
    +     '<div><h3 class="settings-card-title">Grafana Integration</h3><p class="settings-card-desc">Export traces via OTLP to Grafana Tempo / Grafana Cloud</p></div>'
    +   '</div>'
    +   '<details class="settings-guide"><summary class="settings-guide-toggle"><svg class="settings-guide-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 6 15 12 9 18"/></svg>Setup Guide</summary>'
    +     '<div class="settings-guide-body">'
    +       '<p class="settings-guide-intro">Export traces via OTLP/HTTP to visualize the full request lifecycle in Grafana Tempo.</p>'
    +       '<div class="settings-guide-section"><h4>Grafana Cloud</h4><table class="settings-guide-table"><tr><td><strong>OTLP Endpoint</strong></td><td><code>https://otlp-gateway-{region}.grafana.net/otlp</code></td></tr><tr><td><strong>Instance ID</strong></td><td>Your Stack Instance ID</td></tr><tr><td><strong>API Token</strong></td><td>Access Policy token with <code>traces:write</code></td></tr></table><ol class="settings-guide-steps"><li>Go to <a href="https://grafana.com" target="_blank">grafana.com</a> &rarr; your stack &rarr; <strong>Details</strong>.</li><li>Region + Instance ID are on the stack details page.</li><li>Left sidebar &rarr; <strong>Security</strong> &rarr; <strong>Access Policies</strong> &rarr; create policy with <strong>traces:write</strong> scope &rarr; <strong>Add token</strong>.</li></ol></div>'
    +       '<div class="settings-guide-section"><h4>Self-Hosted Tempo</h4><ol class="settings-guide-steps"><li>Set endpoint to your Tempo OTLP receiver, e.g. <code>http://tempo:4318</code></li><li>Leave Instance ID and API Token blank if no auth.</li></ol></div>'
    +       '<div class="settings-guide-section"><h4>Viewing Traces</h4><ol class="settings-guide-steps"><li>In Grafana &rarr; <strong>Explore</strong> &rarr; <strong>Tempo</strong> data source.</li><li>Search by <strong>Service Name</strong> or paste a <strong>Trace ID</strong> from Audit Log.</li></ol></div>'
    +       '<div class="settings-guide-note"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg><span>Every proxied response includes <code>traceparent</code> and <code>X-AIGate-Trace-ID</code> headers.</span></div>'
    +     '</div>'
    +   '</details>'
    +   _grafanaTraceSection()
    + '</div>'

    // General card
    + '<div class="settings-card">'
    +   '<div class="settings-card-header">'
    +     '<div class="settings-card-icon" style="background:rgba(168,85,247,0.12);color:#a855f7"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg></div>'
    +     '<div><h3 class="settings-card-title">Shield LLM Key</h3><p class="settings-card-desc">API key used by LLM shields to evaluate content &middot; separate from proxy keys</p></div>'
    +   '</div>'
    +   '<div id="shield-llm-fields">'
    +     '<div class="settings-form-row">'
    +       '<div class="settings-form-group" style="flex:1"><label for="shield-llm-provider">Provider</label><select id="shield-llm-provider"><option value="openai"' + (current.shield_llm_provider === "anthropic" ? "" : " selected") + '>OpenAI</option><option value="anthropic"' + (current.shield_llm_provider === "anthropic" ? " selected" : "") + '>Anthropic</option></select></div>'
    +       '<div class="settings-form-group" style="flex:2"><label for="shield-llm-key">API Key</label><input type="password" id="shield-llm-key" placeholder="sk-..." value="' + (current.shield_llm_key_set ? "••••••••" : "") + '"><p class="hint">Used only for shield evaluation, not proxied traffic</p></div>'
    +     '</div>'
    +     '<div class="settings-actions">'
    +       '<button class="btn btn-primary btn-sm" id="shield-llm-save">Save Key</button>'
    +       (current.shield_llm_key_set ? '<button class="btn btn-outline-danger btn-sm" id="shield-llm-remove">Remove Key</button>' : '')
    +       '<span class="settings-status" id="shield-llm-status">' + (current.shield_llm_key_set ? 'Configured' : '') + '</span>'
    +     '</div>'
    +   '</div>'
    + '</div>'

    // Auto-Blacklist card
    + '<div class="settings-card">'
    +   '<div class="settings-card-header">'
    +     '<div class="settings-card-icon" style="background:rgba(239,68,68,0.12);color:#ef4444"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="4.93" y1="4.93" x2="19.07" y2="19.07"/></svg></div>'
    +     '<div><h3 class="settings-card-title">Auto-Blacklist</h3><p class="settings-card-desc">Automatically disable API keys after repeated shield blocks</p></div>'
    +   '</div>'
    +   '<div id="auto-blacklist-fields">'
    +     '<div class="settings-form-group"><label for="blacklist-threshold">Block Threshold</label><input type="number" id="blacklist-threshold" min="0" step="1" placeholder="0" value="' + (current.auto_blacklist_threshold || 0) + '"><p class="hint">Number of shield blocks before auto-blacklisting an API key. Set to 0 to disable.</p></div>'
    +     '<div class="settings-actions">'
    +       '<button class="btn btn-primary btn-sm" id="blacklist-save">Save</button>'
    +       '<span class="settings-status" id="blacklist-status">' + (current.auto_blacklist_threshold > 0 ? 'Active \u2014 ' + current.auto_blacklist_threshold + ' blocks' : 'Disabled') + '</span>'
    +     '</div>'
    +   '</div>'
    + '</div>'

    // General card
    + '<div class="settings-card">'
    +   '<div class="settings-card-header">'
    +     '<div class="settings-card-icon" style="background:var(--primary-bg);color:var(--primary)"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg></div>'
    +     '<div><h3 class="settings-card-title">General</h3><p class="settings-card-desc">Server configuration (read-only, set via environment variables)</p></div>'
    +   '</div>'
    +   '<div class="trace-stats-grid" style="grid-template-columns:repeat(2,1fr)">'
    +     '<div class="trace-stat"><span class="trace-stat-value" style="font-size:0.8rem">Passthrough</span><span class="trace-stat-label">Key Mode</span></div>'
    +     '<div class="trace-stat"><span class="trace-stat-value" style="font-size:0.8rem">90 days</span><span class="trace-stat-label">Audit Retention</span></div>'
    +   '</div>'
    + '</div>'

    + '</div>'; // settings-page

    $content().innerHTML = html;

    // ══════════════════════════════════════════════════════════════════════
    // GRAFANA LOGIC
    // ══════════════════════════════════════════════════════════════════════

    if (grafanaConfigured) {
        if ($("#grafana-deactivate")) {
            $("#grafana-deactivate").onclick = async function() {
                try {
                    await api.post("/settings", {
                        grafana_enabled: false, grafana_otlp_endpoint: "", grafana_otlp_headers: "",
                        grafana_service_name: "aigate",
                        grafana_trace_playground: false, grafana_trace_claude_code: false, grafana_trace_openclaw: false,
                    });
                    showToast("Grafana deactivated");
                    _rerender(renderSettings);
                } catch (e) { showToast("Failed: " + e.message, "error"); }
            };
        }
    }

    function _buildBasicAuth() {
        var id = $("#grafana-instance-id").value.trim();
        var token = $("#grafana-api-token").value.trim();
        if (id && token) return "Basic " + btoa(id + ":" + token);
        return "";
    }

    $("#grafana-save").onclick = async function() {
        var statusEl = $("#grafana-status");
        var payload = {
            grafana_enabled: true,
            grafana_otlp_endpoint: $("#grafana-endpoint").value.trim(),
            grafana_otlp_headers: _buildBasicAuth(),
            grafana_service_name: $("#grafana-service").value.trim() || "aigate",
            grafana_trace_playground: true,
            grafana_trace_claude_code: true,
            grafana_trace_openclaw: true,
        };
        if (!payload.grafana_otlp_endpoint) { showToast("OTLP endpoint is required", "error"); return; }
        try {
            await api.post("/settings", payload);
            showToast("Settings saved");
            if (!grafanaConfigured) { _rerender(renderSettings); return; }
            statusEl.textContent = "Saved";
            statusEl.className = "settings-status connected";
            setTimeout(function() { statusEl.textContent = ""; }, 3000);
        } catch (e) {
            showToast("Failed to save: " + e.message, "error");
            statusEl.textContent = "Error";
            statusEl.className = "settings-status error";
        }
    };

    $("#grafana-test").onclick = async function() {
        var statusEl = $("#grafana-status");
        statusEl.textContent = "Testing...";
        statusEl.className = "settings-status";
        try {
            var res = await api.post("/settings/test-grafana", { grafana_otlp_endpoint: $("#grafana-endpoint").value.trim(), grafana_otlp_headers: _buildBasicAuth() });
            if (res.ok) {
                statusEl.textContent = "Connected";
                statusEl.className = "settings-status connected";
                showToast("Connection successful", "success");
            } else {
                statusEl.textContent = res.detail || "Failed";
                statusEl.className = "settings-status error";
                showToast("Connection failed: " + (res.detail || "Unknown error"), "error");
            }
        } catch (e) {
            statusEl.textContent = "Error";
            statusEl.className = "settings-status error";
            showToast("Test failed: " + e.message, "error");
        }
    };

    // ══════════════════════════════════════════════════════════════════════
    // SHIELD LLM KEY
    // ══════════════════════════════════════════════════════════════════════

    $("#shield-llm-save").onclick = async function() {
        var keyVal = $("#shield-llm-key").value.trim();
        var providerVal = $("#shield-llm-provider").value;
        var statusEl = $("#shield-llm-status");
        // Don't save the masked placeholder
        if (keyVal === "••••••••") {
            // Just save provider change
            keyVal = "";
        }
        if (!keyVal && !current.shield_llm_key_set) {
            showToast("Enter an API key", "error");
            return;
        }
        try {
            var payload = { shield_llm_provider: providerVal };
            if (keyVal && keyVal !== "••••••••") payload.shield_llm_key = keyVal;
            await api.post("/settings/shield-llm-key", payload);
            showToast("Shield LLM key saved", "success");
            statusEl.textContent = "Saved";
            statusEl.className = "settings-status connected";
            setTimeout(function() { _rerender(renderSettings); }, 1000);
        } catch (e) {
            showToast("Failed: " + e.message, "error");
            statusEl.textContent = "Error";
            statusEl.className = "settings-status error";
        }
    };

    if ($("#shield-llm-remove")) {
        $("#shield-llm-remove").onclick = async function() {
            try {
                await api.del("/settings/shield-llm-key");
                showToast("Shield LLM key removed", "success");
                _rerender(renderSettings);
            } catch (e) {
                showToast("Failed: " + e.message, "error");
            }
        };
    }

    // ══════════════════════════════════════════════════════════════════════
    // AUTO-BLACKLIST
    // ══════════════════════════════════════════════════════════════════════

    $("#blacklist-save").onclick = async function() {
        var statusEl = $("#blacklist-status");
        var val = parseInt($("#blacklist-threshold").value, 10);
        if (isNaN(val) || val < 0) val = 0;
        try {
            await api.post("/settings/auto-blacklist", { auto_blacklist_threshold: val });
            showToast("Auto-blacklist threshold saved", "success");
            statusEl.textContent = val > 0 ? ("Active \u2014 " + val + " blocks") : "Disabled";
            statusEl.className = "settings-status" + (val > 0 ? " connected" : "");
        } catch (e) {
            showToast("Failed: " + e.message, "error");
            statusEl.textContent = "Error";
            statusEl.className = "settings-status error";
        }
    };
}
