// ── Organizations ───────────────────────────────────────────────────────────

async function renderOrgs() {
    $content().innerHTML = `<div class="section-header"><h2>Organizations</h2></div><p style="color:var(--text-muted)">Loading...</p>`;
    try {
        const orgs = await api.get("/orgs");
        $content().innerHTML = `
            <div class="section-header">
                <h2>Organizations</h2>
                <button class="btn btn-primary" id="toggle-create-org">+ New Org</button>
            </div>
            <div class="create-form" id="create-org-form" style="display:none">
                <h3>Create Organization</h3>
                <div class="form-row">
                    <div class="form-group"><label>Name</label><input type="text" id="org-name" placeholder="Acme Corp"></div>
                    <div class="form-group"><label>Slug (optional)</label><input type="text" id="org-slug" placeholder="auto-generated"></div>
                </div>
                <button class="btn btn-primary" id="submit-create-org">Create</button>
            </div>
            <div class="table-wrap">
                <table>
                    <thead><tr><th>Name</th><th>Slug</th><th>Policy</th><th></th></tr></thead>
                    <tbody>
                        ${orgs.map(o => `<tr>
                            <td>${esc(o.name)}</td>
                            <td><code>${esc(o.slug)}</code></td>
                            <td><button class="btn btn-sm btn-secondary btn-edit-policy" data-id="${o.id}" data-policy='${esc(JSON.stringify(o.policy || {}))}'>Edit Policy</button></td>
                            <td><button class="btn btn-sm btn-danger btn-delete-org" data-id="${o.id}">Delete</button></td>
                        </tr>`).join("") || `<tr><td colspan="4" class="empty-state">No organizations yet</td></tr>`}
                    </tbody>
                </table>
            </div>
            <dialog id="policy-dialog">
                <header>Edit Organization Policy</header>
                <div class="dialog-body">
                    <textarea id="policy-editor" rows="14" style="font-family:var(--mono);font-size:0.8rem"></textarea>
                </div>
                <footer>
                    <button class="btn btn-secondary" id="policy-cancel">Cancel</button>
                    <button class="btn btn-primary" id="policy-save">Save Policy</button>
                </footer>
            </dialog>
        `;
        $("#toggle-create-org").onclick = () => { const f = $("#create-org-form"); f.style.display = f.style.display === "none" ? "block" : "none"; };
        $("#submit-create-org").onclick = async () => {
            const name = $("#org-name").value.trim();
            if (!name) return;
            await api.post("/orgs", { name, slug: $("#org-slug").value.trim() || undefined });
            showToast("Organization created");
            _rerender(renderOrgs);
        };
        $$(".btn-delete-org").forEach(btn => { btn.onclick = async () => { if (confirm("Delete this organization?")) { await api.del(`/orgs/${btn.dataset.id}`); showToast("Organization deleted"); _rerender(renderOrgs); } }; });
        let editingOrgId = null;
        const dialog = $("#policy-dialog");
        $$(".btn-edit-policy").forEach(btn => { btn.onclick = () => { editingOrgId = btn.dataset.id; $("#policy-editor").value = JSON.stringify(JSON.parse(btn.dataset.policy), null, 2); dialog.showModal(); }; });
        $("#policy-cancel").onclick = () => dialog.close();
        $("#policy-save").onclick = async () => {
            try { const policy = JSON.parse($("#policy-editor").value); await api.patch(`/orgs/${editingOrgId}/policy`, { policy }); dialog.close(); showToast("Policy updated"); _rerender(renderOrgs); }
            catch (e) { alert("Invalid JSON: " + e.message); }
        };
    } catch (e) { $content().innerHTML = `<div class="section-header"><h2>Organizations</h2></div><div class="card"><p style="color:var(--danger)">Error: ${esc(e.message)}</p></div>`; }
}
