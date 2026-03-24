import asyncio
import json
import sys
from pathlib import Path

import typer
from aigate.cli.theme import console, ACTION_COLORS, SEVERITY_COLORS, TUI_STYLE_DICT, HEX_ACCENT
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

app = typer.Typer(help="Manage and test shields", no_args_is_help=True)


@app.command("list")
def list_shields():
    """List all loaded shields with their status (YAML + LLM shields)."""
    from aigate.config import settings
    from aigate.shields.loader import load_shields

    shields = load_shields(settings.shields_dir_list)

    # ── YAML / file-based shields ─────────────────────────────────────────
    table = Table(
        "ID", "Name", "Version", "Enabled", "Type", "Phase", "Action", "Severity",
        "Patterns", "Logic", "Tags",
        title="[bold]File Shields[/bold]",
    )
    for shield in shields.values():
        enabled = "[success]✓ ON[/success]" if shield.enabled else "[error]✗ OFF[/error]"
        table.add_row(
            shield.id,
            shield.name,
            shield.version,
            enabled,
            shield.type,
            shield.phase,
            shield.default_action,
            shield.severity,
            str(len(shield.patterns)),
            "✓" if shield.logic_module else "—",
            ", ".join(shield.tags[:3]),
        )
    console.print(table)

    # ── LLM shields (stored in DB) ────────────────────────────────────────
    async def _load_llm():
        from aigate.db.engine import init_db, async_session_factory
        from aigate.db.models.llm_shield import LlmShield
        from sqlalchemy import select

        await init_db()
        async with async_session_factory() as session:
            result = await session.execute(select(LlmShield).order_by(LlmShield.name))
            return result.scalars().all()

    try:
        llm_shields = asyncio.run(_load_llm())
    except Exception:
        llm_shields = []

    if llm_shields:
        llm_table = Table(
            "ID", "Name", "Enabled", "Model", "Provider", "Action", "Severity", "Description",
            title="[bold]LLM Shields[/bold]",
        )
        for ls in llm_shields:
            enabled = "[success]✓ ON[/success]" if ls.enabled else "[error]✗ OFF[/error]"
            llm_table.add_row(
                ls.id,
                ls.name,
                enabled,
                ls.model,
                ls.provider,
                ls.default_action,
                ls.severity,
                (ls.description[:50] + "…") if len(ls.description) > 50 else ls.description,
            )
        console.print()
        console.print(llm_table)
    else:
        console.print("\n[muted]No LLM shields configured. Create one via the portal or API.[/muted]")

    console.print(f"\n[muted]Shield dirs: {', '.join(settings.shields_dir_list)}[/muted]")
    console.print("[muted]Use 'aigate shield configure' to toggle shields interactively[/muted]")


@app.command("show")
def show_shield(
    shield_id: str = typer.Argument(..., help="Shield ID to inspect"),
):
    """Show detailed info about a specific shield (file-based or LLM)."""
    from aigate.config import settings
    from aigate.shields.loader import load_shields, find_shield_file

    shields = load_shields(settings.shields_dir_list)
    shield = shields.get(shield_id)

    if shield:
        # File-based shield
        shield_dir = Path(shield.shield_dir)
        shield_file = find_shield_file(shield_dir)

        console.print(Panel(
            f"[bold]{shield.name}[/bold] (v{shield.version})\n"
            f"{shield.description}\n\n"
            f"  ID:          {shield.id}\n"
            f"  Type:        {shield.type}\n"
            f"  Phase:       {shield.phase}\n"
            f"  Action:      {shield.default_action}\n"
            f"  Severity:    {shield.severity}\n"
            f"  Enabled:     {'[success]Yes[/success]' if shield.enabled else '[error]No[/error]'}\n"
            f"  Patterns:    {len(shield.patterns)}\n"
            f"  Logic:       {shield.logic_module or '—'}\n"
            f"  Tags:        {', '.join(shield.tags)}\n"
            f"  Directory:   {shield.shield_dir}",
            title=f"[accent]Shield: {shield.id}[/accent]",
            border_style="accent",
        ))

        if shield.patterns:
            table = Table("Pattern ID", "Type", "Severity", "Action", "Description", title="Patterns")
            for p in shield.patterns:
                table.add_row(p.id, p.type, p.severity, p.action, p.description[:60])
            console.print(table)

        if shield.params:
            console.print("\n[bold]Params:[/bold]")
            console.print(Syntax(json.dumps(shield.params, indent=2), "json", theme="monokai", padding=1))

        console.print(f"\n[muted]YAML: {shield_dir / 'shield.yaml'}[/muted]")
        return

    # Try LLM shield from DB
    async def _load_llm():
        from aigate.db.engine import init_db, async_session_factory
        from aigate.db.models.llm_shield import LlmShield

        await init_db()
        async with async_session_factory() as session:
            return await session.get(LlmShield, shield_id)

    try:
        ls = asyncio.run(_load_llm())
    except Exception:
        ls = None

    if ls:
        console.print(Panel(
            f"[bold]{ls.name}[/bold]\n"
            f"{ls.description}\n\n"
            f"  ID:          {ls.id}\n"
            f"  Type:        [purple]llm[/purple]\n"
            f"  Model:       {ls.model}\n"
            f"  Provider:    {ls.provider}\n"
            f"  Action:      {ls.default_action}\n"
            f"  Severity:    {ls.severity}\n"
            f"  Enabled:     {'[success]Yes[/success]' if ls.enabled else '[error]No[/error]'}",
            title=f"[purple]LLM Shield: {ls.id}[/purple]",
            border_style="purple",
        ))
        console.print("\n[bold]System Prompt:[/bold]")
        console.print(Syntax(ls.system_prompt, "text", theme="monokai", padding=1, word_wrap=True))
        return

    console.print(f"[error]Shield '{shield_id}' not found[/error]")
    console.print(f"Available file shields: {', '.join(shields.keys())}")
    console.print("[muted]Use 'aigate shield list' to see all shields including LLM shields.[/muted]")
    raise typer.Exit(1)


@app.command("configure")
def configure_shields():
    """Interactive shield configurator.

    \b
    List view:
        ↑/↓      Navigate shields
        Space    Toggle enabled/disabled
        Enter/→  Open shield detail
        q        Save & quit

    Detail view:
        ↑/↓      Navigate fields
        ←/→      Change value
        Enter    Cycle value
        Esc/←    Back to list (from top)
    """
    _run_configurator()


@app.command("config", hidden=True)
def config_shields():
    """Interactive shield configurator (alias for 'configure')."""
    _run_configurator()


# ══════════════════════════════════════════════════════════════════════════════
# Full-screen TUI configurator — everything in one prompt_toolkit Application
# ══════════════════════════════════════════════════════════════════════════════

_ACTIONS_FILE = ["block", "warn", "sanitize", "log", "pass"]
_ACTIONS_LLM = ["block", "warn", "log", "pass"]
_SEVERITIES = ["critical", "high", "medium", "low", "info"]

# Colour maps imported from theme:
#   ACTION_COLORS, SEVERITY_COLORS (already imported at top)


def _load_all_shields():
    """Load file-based and LLM shields. Returns (file_shields_dict, llm_list)."""
    from aigate.config import settings
    from aigate.shields.loader import load_shields

    file_shields = load_shields(settings.shields_dir_list)

    llm_shields: list = []
    try:
        async def _load():
            from aigate.db.engine import init_db, async_session_factory
            from aigate.db.models.llm_shield import LlmShield
            from sqlalchemy import select as sa_select

            await init_db()
            async with async_session_factory() as session:
                r = await session.execute(sa_select(LlmShield).order_by(LlmShield.name))
                return list(r.scalars().all())
        llm_shields = asyncio.run(_load())
    except Exception:
        pass

    return file_shields, llm_shields


def _build_items(file_shields, llm_shields):
    """Build unified item list for the TUI."""
    items = []
    for s in file_shields.values():
        items.append({
            "kind": "file", "id": s.id, "name": s.name,
            "enabled": s.enabled, "action": s.default_action,
            "severity": s.severity, "obj": s,
            "pattern_changes": {}, "param_changes": {},
        })
    for ls in llm_shields:
        items.append({
            "kind": "llm", "id": ls.id, "name": ls.name,
            "enabled": ls.enabled, "action": ls.default_action,
            "severity": ls.severity, "model": ls.model, "provider": ls.provider,
        })
    return items


def _is_modified(item, originals):
    orig = originals.get(item["id"], {})
    return (
        item["enabled"] != orig.get("enabled")
        or item["action"] != orig.get("action")
        or item["severity"] != orig.get("severity")
        or bool(item.get("pattern_changes"))
        or bool(item.get("param_changes"))
    )


def _run_configurator():
    from prompt_toolkit import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout, HSplit
    from prompt_toolkit.layout.containers import Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    file_shields, llm_shields = _load_all_shields()
    items = _build_items(file_shields, llm_shields)

    if not items:
        console.print("[warn]No shields found.[/warn]")
        return

    originals = {
        it["id"]: {"enabled": it["enabled"], "action": it["action"], "severity": it["severity"]}
        for it in items
    }

    # ── State ─────────────────────────────────────────────────────────
    state = {
        "view": "list",       # "list" | "detail"
        "cursor": 0,          # index in items (list view)
        "detail_row": 0,      # index in detail fields
        "detail_fields": [],  # built dynamically
        "done": False,
    }

    # ── Detail field builders ─────────────────────────────────────────
    def _build_detail_fields(item):
        """Build editable fields for the detail view."""
        fields = []
        fields.append({
            "key": "enabled", "label": "Status",
            "values": [True, False],
            "display": lambda v: ("ON", "#44ee44") if v else ("OFF", "#ee4444"),
            "current": item["enabled"],
        })

        action_list = _ACTIONS_FILE if item["kind"] == "file" else _ACTIONS_LLM
        fields.append({
            "key": "action", "label": "Action",
            "values": action_list,
            "display": lambda v: (v, ACTION_COLORS.get(v, "#ffffff")),
            "current": item["action"],
        })

        fields.append({
            "key": "severity", "label": "Severity",
            "values": _SEVERITIES,
            "display": lambda v: (v, SEVERITY_COLORS.get(v, "#ffffff")),
            "current": item["severity"],
        })

        if item["kind"] == "file" and item["obj"].patterns:
            overrides = item.setdefault("pattern_changes", {})
            for p in item["obj"].patterns:
                cur = overrides.get(p.id, p.action)
                fields.append({
                    "key": f"pat:{p.id}", "label": f"  {p.id}",
                    "values": _ACTIONS_FILE,
                    "display": lambda v: (v, ACTION_COLORS.get(v, "#ffffff")),
                    "current": cur,
                    "is_pattern": True, "pattern_id": p.id,
                    "original": p.action,
                })

        if item["kind"] == "file" and item["obj"].params:
            overrides = item.setdefault("param_changes", {})
            for k, v in item["obj"].params.items():
                cur = overrides.get(k, v)
                fields.append({
                    "key": f"param:{k}", "label": f"  {k}",
                    "values": None,  # free-text — not cycleable
                    "display": lambda v: (json.dumps(v) if not isinstance(v, str) else v, HEX_ACCENT),
                    "current": cur,
                    "is_param": True, "param_key": k,
                    "original": v,
                })

        return fields

    def _apply_field(item, field):
        """Write a field's current value back into the item dict."""
        key = field["key"]
        val = field["current"]
        if key == "enabled":
            item["enabled"] = val
        elif key == "action":
            item["action"] = val
        elif key == "severity":
            item["severity"] = val
        elif field.get("is_pattern"):
            overrides = item.setdefault("pattern_changes", {})
            if val != field.get("original"):
                overrides[field["pattern_id"]] = val
            elif field["pattern_id"] in overrides:
                del overrides[field["pattern_id"]]
        elif field.get("is_param"):
            overrides = item.setdefault("param_changes", {})
            if val != field.get("original"):
                overrides[field["param_key"]] = val
            elif field["param_key"] in overrides:
                del overrides[field["param_key"]]

    def _cycle_field(field, direction=1):
        """Cycle a field's value. direction: +1 right, -1 left."""
        if field["values"] is None:
            return  # free-text, not cycleable
        vals = field["values"]
        try:
            idx = vals.index(field["current"])
        except ValueError:
            idx = 0
        field["current"] = vals[(idx + direction) % len(vals)]

    # ── Render: list view ─────────────────────────────────────────────
    def _render_list():
        P = []  # (style, text) tuples
        W = 76

        # Header
        P.append(("class:brand", "  ■ AIGate "))
        P.append(("class:title", " Shield Configuration\n"))
        P.append(("class:bar", "  " + "━" * W + "\n"))

        # Column headers
        P.append(("class:colhdr", f"     {'':3s}{'ID':<22s} {'Name':<24s} {'Action':<10s} {'Severity':<10s}\n"))
        P.append(("class:rule", "  " + "─" * W + "\n"))

        last_kind = None
        for i, item in enumerate(items):
            if item["kind"] == "llm" and last_kind == "file":
                P.append(("class:section", "  ── LLM Shields " + "─" * (W - 17) + "\n"))
            last_kind = item["kind"]

            sel = i == state["cursor"]
            pre = "class:sel " if sel else ""

            # Pointer
            ptr = " ▸ " if sel else "   "
            P.append((pre + "class:ptr" if sel else "", ptr))

            # On/off badge
            if item["enabled"]:
                P.append((pre + "class:on", " ON "))
            else:
                P.append((pre + "class:off", "OFF "))

            # ID
            P.append((pre, f"{item['id']:<22s} "))

            # Name (truncated)
            name = item["name"][:23]
            P.append((pre + "class:name", f"{name:<24s}"))

            # Action (colored)
            act = item["action"]
            act_c = ACTION_COLORS.get(act, "#ffffff")
            P.append((pre + f"fg:{act_c}", f"{act:<10s} "))

            # Severity (colored)
            sev = item["severity"]
            sev_c = SEVERITY_COLORS.get(sev, "#ffffff")
            P.append((pre + f"fg:{sev_c}", f"{sev:<10s}"))

            # Modified marker
            if _is_modified(item, originals):
                P.append((pre + "class:mod", " ●"))

            P.append(("", "\n"))

        P.append(("class:rule", "  " + "─" * W + "\n"))

        # Status bar
        mod_n = sum(1 for it in items if _is_modified(it, originals))
        if mod_n:
            P.append(("class:status", f"  {mod_n} unsaved change{'s' if mod_n != 1 else ''}  "))
        else:
            P.append(("class:status", "  "))

        P.append(("class:bar", "\n  "))
        P.append(("class:key", " ↑↓ "))
        P.append(("class:hint", " navigate  "))
        P.append(("class:key", " Space "))
        P.append(("class:hint", " toggle  "))
        P.append(("class:key", " Enter "))
        P.append(("class:hint", " configure  "))
        P.append(("class:key", " q "))
        P.append(("class:hint", " save & quit"))
        P.append(("", "\n"))

        return P

    # ── Render: detail view ───────────────────────────────────────────
    def _render_detail():
        P = []
        W = 76
        item = items[state["cursor"]]
        fields = state["detail_fields"]

        # Header
        P.append(("class:brand", "  ■ AIGate "))
        kind_label = "LLM" if item["kind"] == "llm" else "File"
        P.append(("class:title", f" {item['name']}  "))
        P.append(("class:dim", f"({item['id']})  [{kind_label}]\n"))
        P.append(("class:bar", "  " + "━" * W + "\n"))

        has_patterns = any(f.get("is_pattern") for f in fields)
        has_params = any(f.get("is_param") for f in fields)
        in_patterns = False
        in_params = False

        for i, f in enumerate(fields):
            # Section headers
            if f.get("is_pattern") and not in_patterns:
                in_patterns = True
                P.append(("class:section", f"\n  ── Patterns " + "─" * (W - 13) + "\n"))
            elif f.get("is_param") and not in_params:
                in_params = True
                P.append(("class:section", f"\n  ── Parameters " + "─" * (W - 15) + "\n"))

            sel = i == state["detail_row"]
            pre = "class:sel " if sel else ""

            ptr = " ▸ " if sel else "   "
            P.append((pre + ("class:ptr" if sel else ""), ptr))

            # Label
            label = f["label"]
            P.append((pre + "class:label", f"{label:<25s} "))

            # Value (colored)
            display_text, display_color = f["display"](f["current"])
            if sel:
                # Show arrows for cycleable fields
                if f["values"] is not None:
                    P.append((pre, "◂ "))
                    P.append((pre + f"fg:{display_color} bold", f"{display_text}"))
                    P.append((pre, " ▸"))
                else:
                    P.append((pre + f"fg:{display_color}", f"{display_text}"))
            else:
                P.append((pre + f"fg:{display_color}", f"{display_text}"))

            # Modified marker
            if f.get("is_pattern") or f.get("is_param"):
                if f["current"] != f.get("original"):
                    P.append((pre + "class:mod", " ●"))

            P.append(("", "\n"))

        P.append(("class:rule", "\n  " + "─" * W + "\n"))

        # Status bar
        P.append(("class:bar", "  "))
        P.append(("class:key", " ↑↓ "))
        P.append(("class:hint", " navigate  "))
        P.append(("class:key", " ←→ "))
        P.append(("class:hint", " change value  "))
        P.append(("class:key", " Esc "))
        P.append(("class:hint", " back to list"))
        P.append(("", "\n"))

        return P

    # ── Combined render ───────────────────────────────────────────────
    def _render():
        if state["view"] == "detail":
            return _render_detail()
        return _render_list()

    # ── Key bindings ──────────────────────────────────────────────────
    kb = KeyBindings()

    @kb.add("up")
    @kb.add("k")
    def _up(event):
        if state["view"] == "list":
            state["cursor"] = max(0, state["cursor"] - 1)
        else:
            state["detail_row"] = max(0, state["detail_row"] - 1)

    @kb.add("down")
    @kb.add("j")
    def _down(event):
        if state["view"] == "list":
            state["cursor"] = min(len(items) - 1, state["cursor"] + 1)
        else:
            state["detail_row"] = min(len(state["detail_fields"]) - 1, state["detail_row"] + 1)

    @kb.add("space")
    def _toggle(event):
        if state["view"] == "list":
            items[state["cursor"]]["enabled"] = not items[state["cursor"]]["enabled"]
        else:
            fields = state["detail_fields"]
            if fields:
                f = fields[state["detail_row"]]
                if f["key"] == "enabled":
                    f["current"] = not f["current"]
                    _apply_field(items[state["cursor"]], f)
                elif f["values"] is not None:
                    _cycle_field(f, 1)
                    _apply_field(items[state["cursor"]], f)

    @kb.add("enter")
    def _enter(event):
        if state["view"] == "list":
            item = items[state["cursor"]]
            state["detail_fields"] = _build_detail_fields(item)
            state["detail_row"] = 0
            state["view"] = "detail"
        else:
            fields = state["detail_fields"]
            if fields:
                f = fields[state["detail_row"]]
                if f["values"] is not None:
                    _cycle_field(f, 1)
                    _apply_field(items[state["cursor"]], f)

    @kb.add("right")
    def _right(event):
        if state["view"] == "list":
            item = items[state["cursor"]]
            state["detail_fields"] = _build_detail_fields(item)
            state["detail_row"] = 0
            state["view"] = "detail"
        else:
            fields = state["detail_fields"]
            if fields:
                f = fields[state["detail_row"]]
                if f["values"] is not None:
                    _cycle_field(f, 1)
                    _apply_field(items[state["cursor"]], f)

    @kb.add("left")
    def _left(event):
        if state["view"] == "detail":
            fields = state["detail_fields"]
            if fields:
                f = fields[state["detail_row"]]
                if f["values"] is not None:
                    _cycle_field(f, -1)
                    _apply_field(items[state["cursor"]], f)
                    return
            # If not cycleable or at top, go back
            state["view"] = "list"

    @kb.add("escape")
    def _escape(event):
        if state["view"] == "detail":
            state["view"] = "list"
        else:
            state["done"] = True
            event.app.exit()

    @kb.add("q")
    def _quit(event):
        if state["view"] == "detail":
            state["view"] = "list"
        else:
            state["done"] = True
            event.app.exit()

    # ── Style (from centralised theme) ─────────────────────────────
    style = Style.from_dict(TUI_STYLE_DICT)

    # ── Run ───────────────────────────────────────────────────────────
    control = FormattedTextControl(_render)
    layout = Layout(Window(content=control, always_hide_cursor=True))
    app = Application(layout=layout, key_bindings=kb, style=style, full_screen=True)
    app.run()

    # ── Save ──────────────────────────────────────────────────────────
    _save_all_changes(items, originals, file_shields)


def _save_all_changes(items, originals, file_shields):
    """Write all pending changes to YAML files and DB."""
    from aigate.shields.loader import find_shield_file, read_shield, write_shield

    changed = 0

    for item in items:
        if item["kind"] != "file":
            continue
        if not _is_modified(item, originals):
            continue

        s = item["obj"]
        shield_dir = Path(s.shield_dir)
        shield_file = find_shield_file(shield_dir)
        if not shield_file:
            continue

        data, desc = read_shield(shield_file)
        data["enabled"] = item["enabled"]
        data["default_action"] = item["action"]
        data["severity"] = item["severity"]

        for pat_data in data.get("patterns", []):
            pid = pat_data.get("id")
            if pid and pid in item.get("pattern_changes", {}):
                pat_data["action"] = item["pattern_changes"][pid]

        if item.get("param_changes"):
            params = data.get("params", {})
            params.update(item["param_changes"])
            data["params"] = params

        write_shield(shield_dir, data, desc)
        changed += 1
        status = "[success]enabled[/success]" if item["enabled"] else "[error]disabled[/error]"
        console.print(f"  {item['id']}: {status}, action={item['action']}, severity={item['severity']}")

    llm_dirty = [it for it in items if it["kind"] == "llm" and _is_modified(it, originals)]
    if llm_dirty:
        async def _update():
            from aigate.db.engine import init_db, async_session_factory
            from aigate.db.models.llm_shield import LlmShield

            await init_db()
            async with async_session_factory() as session:
                for item in llm_dirty:
                    ls = await session.get(LlmShield, item["id"])
                    if ls:
                        ls.enabled = item["enabled"]
                        ls.default_action = item["action"]
                        ls.severity = item["severity"]
                        if item.get("model"):
                            ls.model = item["model"]
                await session.commit()

        asyncio.run(_update())
        for item in llm_dirty:
            changed += 1
            status = "[success]enabled[/success]" if item["enabled"] else "[error]disabled[/error]"
            console.print(f"  {item['id']} (LLM): {status}, action={item['action']}, severity={item['severity']}")

    if changed:
        console.print(f"\n[success]✓ Saved {changed} shield(s)[/success]")
        console.print("[muted]Use 'aigate shield reload' to apply to running server.[/muted]")
    else:
        console.print("[muted]No changes.[/muted]")


@app.command("edit")
def edit_shield(
    shield_id: str = typer.Argument(..., help="Shield ID to edit"),
    action: str = typer.Option(None, "--action", "-a", help="Set default action: block | warn | sanitize | log | pass"),
    severity: str = typer.Option(None, "--severity", "-s", help="Set severity: critical | high | medium | low | info"),
    enable: bool = typer.Option(None, "--enable/--disable", help="Enable or disable the shield"),
    param: list[str] = typer.Option(None, "--param", help="Set param as key=value (repeatable)"),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Interactive editing mode"),
):
    """Edit a shield's configuration (file-based or LLM).

    \b
    Examples:
        aigate shield edit prompt_injection --disable
        aigate shield edit pii_detection --action sanitize --severity high
        aigate shield edit content_policy --param blocked_keywords='["hack","exploit"]'
        aigate shield edit prompt_injection -i
        aigate shield edit my_llm_shield --action block --severity high
    """
    import questionary

    from aigate.config import settings
    from aigate.shields.loader import load_shields, find_shield_file, read_shield, write_shield

    shields = load_shields(settings.shields_dir_list)
    shield = shields.get(shield_id)

    # ── Try LLM shield if not found as file shield ────────────────────────
    if not shield:
        _edit_llm_shield(shield_id, action, severity, enable, interactive)
        return

    # ── File-based shield editing ─────────────────────────────────────────
    shield_dir = Path(shield.shield_dir)
    shield_file = find_shield_file(shield_dir)
    if not shield_file:
        console.print(f"[error]No shield.yaml found for {shield_id}[/error]")
        raise typer.Exit(1)

    data, desc = read_shield(shield_file)

    if interactive:
        console.print(Panel(
            f"[bold]Editing: {shield.name}[/bold] ({shield.id})\n"
            f"Current: action={shield.default_action}, severity={shield.severity}, "
            f"enabled={'yes' if shield.enabled else 'no'}",
            border_style="accent",
        ))

        # Toggle enable/disable
        new_enabled = questionary.confirm(
            "Enable this shield?",
            default=shield.enabled,
        ).ask()
        if new_enabled is None:
            raise typer.Abort()
        data["enabled"] = new_enabled

        # Select action
        actions = ["block", "warn", "sanitize", "log", "pass"]
        new_action = questionary.select(
            "Default action when triggered:",
            choices=actions,
            default=shield.default_action,
        ).ask()
        if new_action is None:
            raise typer.Abort()
        data["default_action"] = new_action

        # Select severity
        severities = ["critical", "high", "medium", "low", "info"]
        new_severity = questionary.select(
            "Shield severity level:",
            choices=severities,
            default=shield.severity,
        ).ask()
        if new_severity is None:
            raise typer.Abort()
        data["severity"] = new_severity

        # Edit patterns
        if shield.patterns:
            edit_patterns = questionary.confirm(
                f"Edit individual pattern actions? ({len(shield.patterns)} patterns)",
                default=False,
            ).ask()
            if edit_patterns:
                for i, p_data in enumerate(data.get("patterns", [])):
                    p_id = p_data.get("id", f"pattern_{i}")
                    current_action = p_data.get("action", shield.default_action)
                    new_p_action = questionary.select(
                        f"  Pattern '{p_id}' action (current: {current_action}):",
                        choices=actions,
                        default=current_action,
                    ).ask()
                    if new_p_action is not None:
                        p_data["action"] = new_p_action

        # Edit params
        if shield.params:
            edit_params = questionary.confirm(
                f"Edit shield parameters? ({len(shield.params)} params)",
                default=False,
            ).ask()
            if edit_params:
                params = data.get("params", {})
                for key, value in list(params.items()):
                    new_val = questionary.text(
                        f"  {key}:",
                        default=json.dumps(value) if not isinstance(value, str) else value,
                    ).ask()
                    if new_val is not None:
                        try:
                            params[key] = json.loads(new_val)
                        except json.JSONDecodeError:
                            params[key] = new_val
                data["params"] = params

    else:
        # Non-interactive: apply flags directly
        if enable is not None:
            data["enabled"] = enable
        if action:
            valid_actions = {"block", "warn", "sanitize", "log", "pass"}
            if action not in valid_actions:
                console.print(f"[error]Invalid action '{action}'. Choose from: {', '.join(valid_actions)}[/error]")
                raise typer.Exit(1)
            data["default_action"] = action
        if severity:
            valid_severities = {"critical", "high", "medium", "low", "info"}
            if severity not in valid_severities:
                console.print(f"[error]Invalid severity '{severity}'. Choose from: {', '.join(valid_severities)}[/error]")
                raise typer.Exit(1)
            data["severity"] = severity
        if param:
            params = data.get("params", {})
            for p in param:
                if "=" not in p:
                    console.print(f"[error]Invalid param format '{p}'. Use key=value[/error]")
                    raise typer.Exit(1)
                key, val = p.split("=", 1)
                try:
                    params[key] = json.loads(val)
                except json.JSONDecodeError:
                    params[key] = val
            data["params"] = params

        if enable is None and not action and not severity and not param:
            console.print("[warn]No changes specified. Use --action, --severity, --enable/--disable, --param, or -i[/warn]")
            raise typer.Exit(0)

    # Write back
    write_shield(shield_dir, data, desc)

    console.print(f"\n[success]✓ Updated shield '{shield_id}'[/success]")

    # Show summary of current state
    console.print(f"  Enabled:  {'[success]Yes[/success]' if data.get('enabled', True) else '[error]No[/error]'}")
    console.print(f"  Action:   {data.get('default_action', 'warn')}")
    console.print(f"  Severity: {data.get('severity', 'medium')}")
    if data.get("params"):
        console.print(f"  Params:   {json.dumps(data['params'])}")
    console.print(f"\n[muted]Changes are live on next request. Use 'aigate shield reload' to apply immediately.[/muted]")


def _edit_llm_shield(
    shield_id: str,
    action: str | None,
    severity: str | None,
    enable: bool | None,
    interactive: bool,
):
    """Edit an LLM shield stored in the database."""
    import questionary

    async def _run():
        from aigate.db.engine import init_db, async_session_factory
        from aigate.db.models.llm_shield import LlmShield

        await init_db()
        async with async_session_factory() as session:
            ls = await session.get(LlmShield, shield_id)
            if not ls:
                console.print(f"[error]Shield '{shield_id}' not found (checked file shields and LLM shields)[/error]")
                raise typer.Exit(1)

            if interactive:
                console.print(Panel(
                    f"[bold]Editing LLM Shield: {ls.name}[/bold] ({ls.id})\n"
                    f"Current: action={ls.default_action}, severity={ls.severity}, "
                    f"model={ls.model}, enabled={'yes' if ls.enabled else 'no'}",
                    border_style="purple",
                ))

                new_enabled = questionary.confirm("Enable this shield?", default=ls.enabled).ask()
                if new_enabled is not None:
                    ls.enabled = new_enabled

                actions = ["block", "warn", "log", "pass"]
                new_action = questionary.select(
                    "Default action:", choices=actions, default=ls.default_action,
                ).ask()
                if new_action is not None:
                    ls.default_action = new_action

                severities = ["critical", "high", "medium", "low", "info"]
                new_severity = questionary.select(
                    "Severity:", choices=severities, default=ls.severity,
                ).ask()
                if new_severity is not None:
                    ls.severity = new_severity

                new_model = questionary.text("Model:", default=ls.model).ask()
                if new_model:
                    ls.model = new_model

                edit_prompt = questionary.confirm("Edit system prompt?", default=False).ask()
                if edit_prompt:
                    console.print(f"\n[muted]Current system prompt:[/muted]\n{ls.system_prompt}\n")
                    new_prompt = questionary.text(
                        "New system prompt (leave empty to keep current):",
                    ).ask()
                    if new_prompt:
                        ls.system_prompt = new_prompt

            else:
                if enable is not None:
                    ls.enabled = enable
                if action:
                    valid = {"block", "warn", "log", "pass"}
                    if action not in valid:
                        console.print(f"[error]Invalid action '{action}'. Choose from: {', '.join(valid)}[/error]")
                        raise typer.Exit(1)
                    ls.default_action = action
                if severity:
                    valid = {"critical", "high", "medium", "low", "info"}
                    if severity not in valid:
                        console.print(f"[error]Invalid severity '{severity}'. Choose from: {', '.join(valid)}[/error]")
                        raise typer.Exit(1)
                    ls.severity = severity

                if enable is None and not action and not severity:
                    console.print("[warn]No changes specified. Use --action, --severity, --enable/--disable, or -i[/warn]")
                    raise typer.Exit(0)

            await session.commit()
            await session.refresh(ls)

            console.print(f"\n[success]✓ Updated LLM shield '{ls.id}'[/success]")
            console.print(f"  Enabled:  {'[success]Yes[/success]' if ls.enabled else '[error]No[/error]'}")
            console.print(f"  Action:   {ls.default_action}")
            console.print(f"  Severity: {ls.severity}")
            console.print(f"  Model:    {ls.model}")
            console.print(f"  Provider: {ls.provider}")

    asyncio.run(_run())


@app.command("validate")
def validate_shield(
    path: str = typer.Argument(..., help="Path to shield directory or shield.yaml"),
):
    """Validate a shield.yaml file."""
    from aigate.shields.loader import _load_shield, find_shield_file

    shield_path = Path(path)
    if shield_path.name in ("shield.yaml", "shield.yml"):
        shield_path = shield_path.parent

    shield_file = find_shield_file(shield_path)
    if not shield_file:
        console.print(f"[error]✗ No shield.yaml found in {shield_path}[/error]")
        raise typer.Exit(1)

    try:
        shield = _load_shield(shield_path, shield_file)
        console.print(f"[success]✓ Valid[/success] — {shield.id} v{shield.version} ({len(shield.patterns)} patterns)")
    except Exception as e:
        console.print(f"[error]✗ Invalid:[/error] {e}")
        raise typer.Exit(1)


@app.command("test")
def test_shield(
    shield_id: str = typer.Argument(..., help="Shield ID to test"),
    input_file: str = typer.Option(None, "--input", "-i", help="JSON payload file (or - for stdin)"),
    message: str = typer.Option(None, "--message", "-m", help="Quick test: user message text"),
):
    """Test a shield against a payload."""
    async def _run():
        from aigate.config import settings
        from aigate.shields.runner import ShieldRunner
        from aigate.shields.models import ScanContext
        from aigate.proxy.providers.anthropic import AnthropicProvider
        import uuid

        runner = ShieldRunner(settings.shields_dir_list)
        shield = runner.shields.get(shield_id)
        if not shield:
            console.print(f"[error]Shield '{shield_id}' not found[/error]")
            console.print(f"Available: {', '.join(runner.shields.keys())}")
            raise typer.Exit(1)

        # Build payload
        if message:
            payload = {"messages": [{"role": "user", "content": message}], "model": "test"}
        elif input_file:
            source = sys.stdin if input_file == "-" else open(input_file)
            payload = json.load(source)
        else:
            console.print("[error]Provide --message or --input[/error]")
            raise typer.Exit(1)

        provider = AnthropicProvider()
        content = provider.extract_content(payload)
        context = ScanContext(
            request_id=str(uuid.uuid4()),
            org_id="test",
            user_id=None,
            provider="test",
            model=content.get("model", "test"),
            phase="pre_request",
            messages=content.get("messages", []),
            system_prompt=content.get("system_prompt"),
            tool_results=content.get("tool_results", []),
            raw_body=payload,
        )

        result = await runner._run_shield(shield, context)

        if result.triggered:
            console.print(f"\n[bold error]TRIGGERED[/bold error] — effective action: [warn]{result.effective_action}[/warn]\n")
            table = Table("Pattern", "Msg #", "Severity", "Action", "Matched")
            for f in result.findings:
                table.add_row(
                    f.pattern_id,
                    str(f.message_index) if f.message_index is not None else "—",
                    f.severity,
                    f.action,
                    f.matched_text[:60],
                )
            console.print(table)
        else:
            console.print(f"\n[success]CLEAN[/success] — no findings\n")

    asyncio.run(_run())


@app.command("reload")
def reload_shields():
    """Reload shields on the running server."""
    import httpx
    from aigate.config import settings

    url = f"http://{settings.host}:{settings.port}/api/v1/shields/reload"
    try:
        resp = httpx.post(url, headers={"X-Admin-Key": settings.admin_api_key}, timeout=5.0)
        data = resp.json()
        console.print(f"[success]✓ Reloaded {data.get('reloaded', 0)} shields[/success]")
    except Exception as e:
        console.print(f"[error]Failed to reload: {e}[/error]")
        raise typer.Exit(1)
