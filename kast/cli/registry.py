"""``kast registry`` group (Phase B4) — issue registry management.

Replaces the ad-hoc v2 ``fix_registry.py`` workflow that the audit
flagged as the workflow gating registry currency (audit § 5a.5).
Three subcommands:

- ``kast registry list``      — list entries with optional filters
- ``kast registry add ID ...`` — add one entry interactively or via flags
- ``kast registry promote DIR`` — promote IDs from missing_issue_ids.json

All writes go through ``write_json_atomic`` so a kast-web watcher (or
concurrent reader) never observes a partially-written registry.
"""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from kast.core.atomic import write_json_atomic
from kast.core.severity import Severity

console = Console()


REGISTRY_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "issue_registry.json"
)

VALID_SEVERITIES = [s.value for s in Severity if s != Severity.UNKNOWN]
VALID_REMEDIATION_APPROACHES = ["waf", "code", "combined"]


def _load_registry(path: Path) -> dict:
    """Read the registry; return ``{}`` if not present."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise click.UsageError(
            f"Registry at {path} is not valid JSON: {e}. "
            f"Run `kast doctor` to diagnose."
        )


def _save_registry(path: Path, data: dict) -> None:
    """Atomic write of the full registry."""
    write_json_atomic(path, data)


def _derive_display_name(issue_id: str) -> str:
    """Default display_name when the user doesn't supply one."""
    return issue_id.replace("_", " ").replace("-", " ").title()


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group()
def registry() -> None:
    """Issue-registry management."""
    pass


# ---------------------------------------------------------------------------
# registry list
# ---------------------------------------------------------------------------


@registry.command(name="list")
@click.option("--category", help="Filter: category contains this substring (case-insensitive).")
@click.option("--severity", type=click.Choice(VALID_SEVERITIES),
              help="Filter: exact severity match.")
@click.option("--waf-addressable/--no-waf-addressable", default=None,
              help="Filter: only WAF-addressable (or only NOT WAF-addressable) entries.")
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of formatted table.")
def registry_list(
    category: str | None,
    severity: str | None,
    waf_addressable: bool | None,
    json_output: bool,
) -> None:
    """List registry entries."""
    registry_data = _load_registry(REGISTRY_PATH)

    rows = []
    for issue_id, entry in registry_data.items():
        if category and category.lower() not in (entry.get("category") or "").lower():
            continue
        if severity and entry.get("severity") != severity:
            continue
        if waf_addressable is not None and bool(entry.get("waf_addressable")) != waf_addressable:
            continue
        rows.append({"id": issue_id, **entry})

    rows.sort(key=lambda r: (r.get("category") or "", r["id"]))

    if json_output:
        click.echo(json.dumps({"registry": rows, "count": len(rows)}, indent=2))
        return

    if not rows:
        console.print("[yellow]No matching registry entries.[/yellow]")
        return

    table = Table(title=f"Issue Registry ({len(rows)} entries)",
                  title_style="bold cyan", show_lines=False)
    table.add_column("ID", style="bold")
    table.add_column("Severity")
    table.add_column("Category")
    table.add_column("WAF-addressable", justify="center")
    table.add_column("Display Name", style="dim")

    severity_color = {
        "High": "red",
        "Medium": "yellow",
        "Low": "blue",
        "Informational": "cyan",
    }
    for r in rows:
        sev = r.get("severity", "?")
        color = severity_color.get(sev, "white")
        waf = "✓" if r.get("waf_addressable") else "—"
        table.add_row(
            r["id"],
            f"[{color}]{sev}[/{color}]",
            r.get("category", ""),
            waf,
            r.get("display_name", ""),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# registry add
# ---------------------------------------------------------------------------


@registry.command(name="add")
@click.argument("issue_id")
@click.option("--severity", type=click.Choice(VALID_SEVERITIES),
              required=True, help="Issue severity.")
@click.option("--category", required=True, help="Issue category (e.g., 'Encryption', 'HTTP Headers').")
@click.option("--display-name", help="Human-readable name (default: title-case of the issue_id).")
@click.option("--description", default="", help="What the issue is.")
@click.option("--remediation", default="",
              help="How to fix it. If empty, a generic placeholder is used.")
@click.option("--waf-addressable/--no-waf-addressable", default=False,
              help="Whether a WAF can mitigate this issue.")
@click.option("--remediation-approach",
              type=click.Choice(VALID_REMEDIATION_APPROACHES),
              default="combined", show_default=True)
@click.option("--code-fix-timeframe", default="1-2 weeks", show_default=True,
              help="Estimated time to fix in code (used by F1 TCO appendix in Phase C).")
@click.option("--waf-deployment-timeframe", default="1-2 days", show_default=True,
              help="Estimated time to deploy WAF protection (used by F1 TCO appendix in Phase C).")
@click.option("--force", is_flag=True,
              help="Overwrite an existing entry with the same ID.")
def registry_add(
    issue_id: str,
    severity: str,
    category: str,
    display_name: str | None,
    description: str,
    remediation: str,
    waf_addressable: bool,
    remediation_approach: str,
    code_fix_timeframe: str,
    waf_deployment_timeframe: str,
    force: bool,
) -> None:
    """Add a single entry to the issue registry."""
    registry_data = _load_registry(REGISTRY_PATH)

    if issue_id in registry_data and not force:
        raise click.UsageError(
            f"Issue {issue_id!r} already exists in the registry. "
            f"Use --force to overwrite."
        )

    entry = {
        "display_name": display_name or _derive_display_name(issue_id),
        "category": category,
        "severity": severity,
        "waf_addressable": waf_addressable,
        "description": description,
        "remediation": remediation or f"Review and address the {issue_id} issue.",
        "remediation_approach": remediation_approach,
        "code_fix_timeframe": code_fix_timeframe,
        "waf_deployment_timeframe": waf_deployment_timeframe,
    }

    action = "Updated" if issue_id in registry_data else "Added"
    registry_data[issue_id] = entry
    _save_registry(REGISTRY_PATH, registry_data)

    console.print(
        f"[green]{action}[/green] [bold]{issue_id}[/bold] "
        f"({severity}, {category}, waf_addressable={waf_addressable})"
    )
    console.print(f"[dim]Registry now has {len(registry_data)} entries.[/dim]")


# ---------------------------------------------------------------------------
# registry promote
# ---------------------------------------------------------------------------


@registry.command(name="promote")
@click.argument("scan_dir", type=click.Path(exists=True))
@click.option("--accept-all", is_flag=True,
              help="Promote every entry without prompting (CI-friendly).")
@click.option("--dry-run", is_flag=True,
              help="Show what would be promoted without writing the registry.")
def registry_promote(scan_dir: str, accept_all: bool, dry_run: bool) -> None:
    """Promote IDs from a scan's missing_issue_ids.json into the registry.

    The report renderer writes ``missing_issue_ids.json`` whenever a plugin
    emits an issue ID not in the registry. Each entry has the ID, the
    plugin that emitted it, and *inferred* metadata (severity, category,
    etc.) from heuristic analysis of the ID string. ``promote`` reads
    that file, lets you accept/skip each candidate, and writes accepted
    entries to the registry.
    """
    scan_path = Path(scan_dir)
    missing_path = scan_path / "missing_issue_ids.json"
    if not missing_path.exists():
        console.print(
            f"[yellow]No missing_issue_ids.json in {scan_path}.[/yellow] "
            f"Either the scan has no unregistered issues, or the report "
            f"hasn't been rendered yet."
        )
        return

    try:
        missing_payload = json.loads(missing_path.read_text())
    except json.JSONDecodeError as e:
        raise click.UsageError(f"Failed to parse {missing_path}: {e}")

    candidates = missing_payload.get("missing_issues", [])
    if not candidates:
        console.print("[green]Nothing to promote — registry is already in sync.[/green]")
        return

    registry_data = _load_registry(REGISTRY_PATH)
    accepted = {}
    skipped = []

    for cand in candidates:
        issue_id = cand["issue_id"]
        suggested = cand.get("suggested_metadata", {}) or {}

        if issue_id in registry_data:
            console.print(
                f"[dim]Already in registry, skipping:[/dim] {issue_id}"
            )
            skipped.append(issue_id)
            continue

        console.print(f"\n[bold cyan]Candidate:[/bold cyan] {issue_id}")
        console.print(f"  Reported by: {cand.get('plugin_display_name')} "
                      f"(plugin: {cand.get('plugin_name')})")
        console.print(f"  Occurrences: {cand.get('occurrence_count', 1)}")
        console.print("  Suggested:")
        console.print(f"    severity:        {suggested.get('severity')}")
        console.print(f"    category:        {suggested.get('category')}")
        console.print(f"    waf_addressable: {suggested.get('waf_addressable')}")
        console.print(f"    display_name:    {suggested.get('display_name')}")
        if suggested.get("remediation"):
            console.print(f"    remediation:     {suggested.get('remediation')[:100]}")

        if accept_all:
            decision = "y"
        else:
            decision = click.prompt("  Accept? [y/N/q to quit]",
                                    default="N", show_default=False).lower()

        if decision == "q":
            console.print("[yellow]Quitting; nothing written.[/yellow]")
            return
        if decision != "y":
            skipped.append(issue_id)
            console.print(f"  [dim]skipped {issue_id}[/dim]")
            continue

        accepted[issue_id] = {
            "display_name": suggested.get("display_name") or _derive_display_name(issue_id),
            "category": suggested.get("category", "Uncategorized"),
            "severity": suggested.get("severity", "Medium"),
            "waf_addressable": bool(suggested.get("waf_addressable", False)),
            "description": "",  # promotion doesn't infer descriptions
            "remediation": suggested.get("remediation", f"Review and address {issue_id}."),
            "remediation_approach": "combined",
            "code_fix_timeframe": "1-2 weeks",
            "waf_deployment_timeframe": "1-2 days",
        }

    if not accepted:
        console.print(
            f"\n[yellow]Nothing accepted.[/yellow] "
            f"({len(skipped)} skipped, registry unchanged.)"
        )
        return

    if dry_run:
        console.print(f"\n[bold cyan]Dry run — would promote {len(accepted)} entries:[/bold cyan]")
        for issue_id in accepted:
            console.print(f"  • {issue_id}")
        console.print("[yellow]No changes written. Re-run without --dry-run to apply.[/yellow]")
        return

    registry_data.update(accepted)
    _save_registry(REGISTRY_PATH, registry_data)

    console.print(
        f"\n[green]Promoted {len(accepted)} entries[/green] "
        f"to {REGISTRY_PATH.name}; registry now has {len(registry_data)} entries."
    )
    if skipped:
        console.print(f"[dim]Skipped: {', '.join(skipped)}[/dim]")
