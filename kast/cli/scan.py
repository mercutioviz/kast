"""``kast scan`` group (Phase B2).

The default invocation ``kast scan -t TARGET ...`` runs a scan against
TARGET (the v2-compatible flow). Subcommands manage past scans:

- ``kast scan list``      — list past scans under ~/kast_results
- ``kast scan show DIR``  — print details of one scan
- ``kast scan rerun DIR`` — re-render reports from existing data

``kast scan rerun`` subsumes ``kast scan --report-only DIR``; the
v2-style ``kast --report-only DIR`` invocation translates to
``kast scan --report-only DIR`` (preserves the kast↔kast-web contract).
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from kast.cli._shared import make_args_namespace
from kast.config_manager import ConfigManager
from kast.core.atomic import write_json_atomic
from kast.orchestrator import ScannerOrchestrator
from kast.registry import PluginRegistry

console = Console()


# ---------------------------------------------------------------------------
# scan group (default action runs a scan)
# ---------------------------------------------------------------------------


@click.group(invoke_without_command=True,
             context_settings={"help_option_names": ["-h", "--help"]})
@click.option("-t", "--target", help="Target domain name to scan.")
@click.option("-m", "--mode", type=click.Choice(["active", "passive", "both"]),
              default="passive", help="Scan mode (default: passive).")
@click.option("-o", "--output-dir", "output_dir", type=click.Path(),
              help="Custom output directory.")
@click.option("--report-only", "report_only_path", type=click.Path(exists=True),
              help="Re-render reports from existing scan directory (deprecated; use `kast scan rerun`).")
@click.option("--format", "format_", type=click.Choice(["html", "pdf", "both"]),
              default="html", help="Report output format (default: html).")
@click.option("--dry-run", is_flag=True,
              help="Preview execution without running tools.")
@click.option("-p", "--parallel", is_flag=True,
              help="Run plugins simultaneously.")
@click.option("--max-workers", type=int, default=5,
              help="Max parallel workers (default: 5).")
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging.")
@click.option("-l", "--log-dir", default="/var/log/kast/",
              help="Log directory (default: /var/log/kast/).")
@click.option("--logo", type=click.Path(),
              help="Custom logo file (PNG/JPG) for reports.")
@click.option("--run-only", help="Comma-separated plugin names to run.")
@click.option("--httpx-rate-limit", type=int, default=10,
              help="(DEPRECATED: use --set related_sites.httpx_rate_limit=N)")
@click.option("--zap-profile",
              type=click.Choice(["quick", "standard", "thorough", "api", "passive"]),
              help="ZAP scan profile shortcut.")
@click.option("--config", "config_path", type=click.Path(),
              help="Path to configuration file.")
@click.option("--set", "set_overrides", multiple=True,
              help="Override config value: --set plugin.key=value")
@click.option("--ai-summary", "ai_summary_flag", is_flag=True,
              help="Generate an AI executive summary (requires KAST_AI_API_KEY).")
@click.option("--ai-model", "ai_model", default=None,
              help="Override AI model (default: claude-sonnet-4-6).")
@click.option("--ai-adapter", "ai_adapter", type=click.Choice(["anthropic"]),
              default="anthropic", help="AI provider adapter (default: anthropic).")
@click.option("--ai-endpoint", "ai_endpoint", default=None,
              help="Route AI requests through a kast-web AI service URL instead of calling the "
                   "provider API directly (Phase C8). Overrides --ai-adapter and KAST_AI_API_KEY.")
@click.pass_context
def scan(
    ctx: click.Context,
    target: str | None,
    mode: str,
    output_dir: str | None,
    report_only_path: str | None,
    format_: str,
    dry_run: bool,
    parallel: bool,
    max_workers: int,
    verbose: bool,
    log_dir: str,
    logo: str | None,
    run_only: str | None,
    httpx_rate_limit: int,
    zap_profile: str | None,
    config_path: str | None,
    set_overrides: tuple[str, ...],
    ai_summary_flag: bool,
    ai_model: str | None,
    ai_adapter: str,
    ai_endpoint: str | None,
) -> None:
    """Run a security scan against TARGET, or manage past scans via subcommand."""
    # If a subcommand was given (list / show / rerun), defer to it.
    if ctx.invoked_subcommand is not None:
        return

    # No subcommand: this is the v2-compatible "run a scan" invocation.
    _run_scan(
        target=target, mode=mode, output_dir=output_dir,
        report_only_path=report_only_path, format_=format_, dry_run=dry_run,
        parallel=parallel, max_workers=max_workers, verbose=verbose,
        log_dir=log_dir, logo=logo, run_only=run_only,
        httpx_rate_limit=httpx_rate_limit, zap_profile=zap_profile,
        config_path=config_path, set_overrides=set_overrides,
        ai_summary_flag=ai_summary_flag, ai_model=ai_model, ai_adapter=ai_adapter,
        ai_endpoint=ai_endpoint,
    )


# ---------------------------------------------------------------------------
# scan list
# ---------------------------------------------------------------------------


def _read_scan_metadata(scan_dir: Path) -> dict:
    """Extract a one-line summary of a single scan dir.

    Returns a dict with keys: target, scan_date, duration_seconds,
    plugin_count, issue_count, status (complete | incomplete).
    """
    info_path = scan_dir / "kast_info.json"
    if not info_path.exists():
        # Best-effort fallback when kast_info.json is missing.
        return {
            "target": scan_dir.name.rsplit("-", 2)[0] if "-" in scan_dir.name else scan_dir.name,
            "scan_date": None,
            "duration_seconds": None,
            "plugin_count": None,
            "issue_count": None,
            "status": "incomplete",
            "path": str(scan_dir),
        }

    try:
        info = json.loads(info_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {
            "target": scan_dir.name.rsplit("-", 2)[0] if "-" in scan_dir.name else scan_dir.name,
            "scan_date": None,
            "duration_seconds": None,
            "plugin_count": None,
            "issue_count": None,
            "status": "incomplete",
            "path": str(scan_dir),
        }

    cli_args = info.get("cli_arguments", {}) or {}
    plugins = info.get("plugins", []) or []
    # Issue count from the *_processed.json files
    issue_count = 0
    for pf in scan_dir.glob("*_processed.json"):
        try:
            data = json.loads(pf.read_text())
            issue_count += len(data.get("issues", []) or [])
        except (json.JSONDecodeError, OSError):
            pass

    return {
        "target": cli_args.get("target") or scan_dir.name,
        "scan_date": info.get("start_timestamp"),
        "duration_seconds": info.get("duration_seconds"),
        "plugin_count": len(plugins),
        "issue_count": issue_count,
        "status": "complete",
        "path": str(scan_dir),
    }


def _resolve_results_dir() -> Path:
    """Default scan-storage location (matches what `kast scan` uses)."""
    return Path.home() / "kast_results"


@scan.command(name="list")
@click.option("--limit", type=int, default=20, show_default=True,
              help="Maximum number of scans to list.")
@click.option("--target", "target_pattern",
              help="Filter by target substring (case-insensitive).")
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of formatted table.")
def scan_list(limit: int, target_pattern: str | None, json_output: bool) -> None:
    """List past scans under ~/kast_results."""
    results_dir = _resolve_results_dir()
    if not results_dir.exists():
        if json_output:
            click.echo(json.dumps({"scans": []}, indent=2))
        else:
            console.print(f"[yellow]No results directory at {results_dir}.[/yellow]")
        return

    scan_dirs = [p for p in results_dir.iterdir() if p.is_dir()]
    # Newest first, by directory mtime.
    scan_dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    rows = []
    for scan_dir in scan_dirs:
        meta = _read_scan_metadata(scan_dir)
        if target_pattern and target_pattern.lower() not in (meta["target"] or "").lower():
            continue
        rows.append(meta)
        if len(rows) >= limit:
            break

    if json_output:
        click.echo(json.dumps({"scans": rows}, indent=2))
        return

    if not rows:
        console.print("[yellow]No scans found.[/yellow]")
        return

    table = Table(title="Past scans (newest first)", title_style="bold cyan",
                  show_lines=False)
    table.add_column("Date", style="cyan")
    table.add_column("Target", style="bold")
    table.add_column("Duration", justify="right")
    table.add_column("Plugins", justify="right")
    table.add_column("Issues", justify="right")
    table.add_column("Status")
    table.add_column("Path", style="dim")
    for row in rows:
        date = (row["scan_date"] or "")[:19].replace("T", " ")
        duration = (
            f"{row['duration_seconds']:.0f}s"
            if row["duration_seconds"] is not None
            else "—"
        )
        plugin_count = str(row["plugin_count"]) if row["plugin_count"] is not None else "—"
        issue_count = str(row["issue_count"]) if row["issue_count"] is not None else "—"
        status_color = "green" if row["status"] == "complete" else "yellow"
        table.add_row(
            date,
            row["target"] or "",
            duration,
            plugin_count,
            issue_count,
            f"[{status_color}]{row['status']}[/{status_color}]",
            str(row["path"]),
        )
    console.print(table)


# ---------------------------------------------------------------------------
# scan show
# ---------------------------------------------------------------------------


@scan.command(name="show")
@click.argument("scan_dir", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of formatted text.")
def scan_show(scan_dir: str, json_output: bool) -> None:
    """Show details of one past scan."""
    path = Path(scan_dir)
    info_path = path / "kast_info.json"
    info = {}
    if info_path.exists():
        try:
            info = json.loads(info_path.read_text())
        except json.JSONDecodeError as e:
            console.print(f"[red]kast_info.json is malformed: {e}[/red]")
            sys.exit(1)

    # Per-plugin issue counts from the _processed.json files
    plugin_issues = {}
    for pf in path.glob("*_processed.json"):
        plugin_name = pf.stem.removesuffix("_processed")
        try:
            data = json.loads(pf.read_text())
            plugin_issues[plugin_name] = len(data.get("issues", []) or [])
        except (json.JSONDecodeError, OSError):
            plugin_issues[plugin_name] = None

    # Reports present
    reports = []
    for name in ("kast_report.html", "kast_report.pdf"):
        rpath = path / name
        if rpath.exists():
            reports.append({"name": name, "size_bytes": rpath.stat().st_size})

    payload = {
        "path": str(path),
        "kast_info": info,
        "plugin_issues": plugin_issues,
        "reports": reports,
    }

    if json_output:
        click.echo(json.dumps(payload, indent=2))
        return

    cli_args = info.get("cli_arguments", {}) or {}
    plugins = info.get("plugins", []) or []
    target = cli_args.get("target") or path.name

    console.print(f"[bold cyan]Scan:[/bold cyan] {target}")
    if info:
        start = (info.get("start_timestamp") or "")[:19].replace("T", " ")
        end = (info.get("end_timestamp") or "")[:19].replace("T", " ")
        duration = info.get("duration_seconds")
        console.print(f"[bold]Date:[/bold] {start} → {end} ({duration}s)")
        console.print(f"[bold]Mode:[/bold] {cli_args.get('mode')}")
    console.print(f"[bold]Output:[/bold] {path}")
    console.print()

    if plugins:
        console.print("[bold cyan]Plugins:[/bold cyan]")
        for p in plugins:
            name = p.get("plugin_name", "?")
            status = p.get("status", "?")
            duration = p.get("duration_seconds")
            duration_str = f"{duration}s" if duration is not None else "—"
            color = {
                "success": "green",
                "fail": "red",
                "failed": "red",
                "unavailable": "yellow",
                "skipped": "dim",
            }.get(status, "white")
            console.print(
                f"  [{color}]●[/{color}] {name:25s} ({status}, {duration_str})"
            )

    if reports:
        console.print()
        console.print("[bold cyan]Reports:[/bold cyan]")
        for r in reports:
            size_kb = r["size_bytes"] / 1024
            console.print(f"  {r['name']} ({size_kb:.1f} KB)")


# ---------------------------------------------------------------------------
# scan rerun (alias for --report-only)
# ---------------------------------------------------------------------------


@scan.command(name="rerun")
@click.argument("scan_dir", type=click.Path(exists=True))
@click.option("--format", "format_", type=click.Choice(["html", "pdf", "both"]),
              default="both", help="Report output format (default: both).")
@click.option("--logo", type=click.Path(),
              help="Custom logo file (PNG/JPG) for reports.")
@click.option("--ai-summary", "ai_summary_flag", is_flag=True,
              help="Generate an AI executive summary using the configured AI provider.")
@click.option("--ai-model", type=str, default=None,
              help="Override the AI model (e.g. claude-opus-4-7).")
@click.option("--ai-adapter", type=click.Choice(["anthropic"]), default="anthropic",
              help="AI provider adapter (default: anthropic).")
@click.option("--ai-endpoint", type=str, default=None, envvar="KAST_AI_ENDPOINT",
              help="Route AI requests through a kast-web AI service endpoint.")
def scan_rerun(scan_dir: str, format_: str, logo: str | None,
               ai_summary_flag: bool, ai_model: str | None,
               ai_adapter: str, ai_endpoint: str | None) -> None:
    """Re-render reports from an existing scan directory.

    Equivalent to ``kast scan --report-only DIR --format X`` — preserved
    for legacy compatibility; ``rerun`` is the canonical v3 form.

    Pass ``--ai-summary`` to add an AI executive summary to the re-rendered
    report without re-running any plugins.

    Defaults to ``--format both`` so HTML and PDF are always kept in sync.
    """
    _run_scan(
        target=None,
        mode="passive",  # ignored in report-only mode
        output_dir=None,
        report_only_path=scan_dir,
        format_=format_,
        dry_run=False,
        parallel=False,
        max_workers=5,
        verbose=False,
        log_dir="/var/log/kast/",
        logo=logo,
        run_only=None,
        httpx_rate_limit=10,
        zap_profile=None,
        config_path=None,
        set_overrides=(),
        ai_summary_flag=ai_summary_flag,
        ai_model=ai_model,
        ai_adapter=ai_adapter,
        ai_endpoint=ai_endpoint,
    )


# ---------------------------------------------------------------------------
# _run_scan — the actual scan logic (was inline in cli/main.py before B2)
# ---------------------------------------------------------------------------


def _build_ai_info(enabled: bool, adapter: str, ai_summary: dict | None,
                   ai_error: str | None, endpoint: str | None = None) -> dict:
    """Build the ``ai`` block for kast_info.json.

    Status is one of ``"success" | "error" | "disabled"``.
    When ``endpoint`` is set, the ``adapter`` field is ``"http"`` and
    ``endpoint`` records the kast-web URL used (Phase C8).
    """
    resolved_adapter = "http" if endpoint else adapter
    if not enabled:
        return {"enabled": False, "status": "disabled", "adapter": None,
                "endpoint": None, "model": None, "prompt_version": None,
                "tokens_in": None, "tokens_out": None,
                "latency_ms": None, "error": None}
    if ai_summary is None:
        return {"enabled": True, "status": "error", "adapter": resolved_adapter,
                "endpoint": endpoint, "model": None, "prompt_version": None,
                "tokens_in": None, "tokens_out": None,
                "latency_ms": None, "error": ai_error}
    meta = ai_summary.get("_meta") or {}
    return {
        "enabled": True,
        "status": "success",
        "adapter": resolved_adapter,
        "endpoint": endpoint,
        "model": meta.get("model"),
        "prompt_version": meta.get("prompt_version"),
        "tokens_in": meta.get("tokens_in"),
        "tokens_out": meta.get("tokens_out"),
        "latency_ms": meta.get("latency_ms"),
        "error": None,
    }


def _setup_logging(log_dir: str, verbose: bool) -> None:
    """Set up Rich-based logging plus a file handler."""
    from rich.logging import RichHandler

    log_dir_p = Path(log_dir).expanduser()
    log_dir_p.mkdir(parents=True, exist_ok=True)
    log_file = log_dir_p / "kast.log"

    handlers = [
        RichHandler(console=console, rich_tracebacks=True, show_time=True),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
    )


def _run_scan(
    *, target, mode, output_dir, report_only_path, format_, dry_run,
    parallel, max_workers, verbose, log_dir, logo, run_only,
    httpx_rate_limit, zap_profile, config_path, set_overrides,
    ai_summary_flag=False, ai_model=None, ai_adapter="anthropic", ai_endpoint=None,
) -> None:
    """Execute a scan (or re-render in report-only mode).

    Extracted from the previous in-line ``scan`` Click command in
    cli/main.py during the B2 refactor that introduced subcommands.
    """
    _setup_logging(log_dir, verbose)
    log = logging.getLogger("kast")

    # Late import to avoid a circular dependency through cli/main.py.
    from kast.cli.main import KAST_VERSION

    if not target and not report_only_path:
        console.print(
            "[bold red]Error:[/bold red] --target is required unless using --report-only "
            "or `kast scan rerun`."
        )
        sys.exit(1)

    args = make_args_namespace(
        target=target, mode=mode, output_dir=output_dir,
        report_only=report_only_path, format=format_, dry_run=dry_run,
        parallel=parallel, max_workers=max_workers, verbose=verbose,
        log_dir=log_dir, logo=logo, run_only=run_only,
        httpx_rate_limit=httpx_rate_limit, zap_profile=zap_profile,
        config=config_path, set=list(set_overrides),
    )

    config_manager = ConfigManager(cli_args=args, logger=log)

    if zap_profile:
        # Resolve relative to the package directory, not cwd (audit § 5.3 fix).
        package_dir = Path(__file__).resolve().parent.parent
        profile_file = package_dir / "config" / f"zap_automation_{zap_profile}.yaml"
        log.info(f"Using ZAP profile: {zap_profile} ({profile_file})")
        console.print(
            f"[cyan]Using ZAP profile:[/cyan] {zap_profile} ({profile_file})"
        )
        args.set = list(args.set) + [
            f"zap.zap_config.automation_plan={profile_file}"
        ]

    console.print("[bold green]KAST - Kali Automated Scan Tool[/bold green]")
    log.info("KAST started with arguments: %s", args)
    config_manager.load(config_path)

    custom_logo_path = None
    if logo:
        logo_path = Path(logo).expanduser()
        if not logo_path.exists():
            log.warning(f"Custom logo file not found: {logo}. Using default logo.")
            console.print(
                f"[yellow]Warning:[/yellow] Logo file '{logo}' not found. Using default logo."
            )
        elif logo_path.suffix.lower() not in [".png", ".jpg", ".jpeg"]:
            log.warning(f"Custom logo file must be PNG or JPG: {logo}.")
            console.print(
                "[yellow]Warning:[/yellow] Logo file must be PNG or JPG. Using default."
            )
        else:
            custom_logo_path = str(logo_path.resolve())
            log.info(f"Using custom logo: {custom_logo_path}")
            console.print(f"[cyan]Using custom logo:[/cyan] {custom_logo_path}")

    if dry_run:
        log.info("Dry run mode enabled.")

    if output_dir:
        out_dir = Path(output_dir).expanduser()
    else:
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        out_dir = Path.home() / "kast_results" / f"{target}-{now}"

    is_report_only = bool(report_only_path)
    if is_report_only:
        report_dir = Path(report_only_path)
        if not report_dir.exists():
            console.print(
                f"[bold red]Error:[/bold red] Output directory {report_dir} does not exist."
            )
            sys.exit(1)
        out_dir = report_dir
        if not target:
            kast_info_path = out_dir / "kast_info.json"
            if not kast_info_path.exists():
                console.print(
                    f"[bold red]Error:[/bold red] kast_info.json not found in {out_dir}"
                )
                console.print(
                    "[yellow]Either provide --target or ensure kast_info.json exists.[/yellow]"
                )
                sys.exit(1)
            try:
                kast_info = json.loads(kast_info_path.read_text())
                target = (kast_info.get("cli_arguments") or {}).get("target")
                args.target = target
                if not target:
                    console.print(
                        "[bold red]Error:[/bold red] Target not found in kast_info.json"
                    )
                    sys.exit(1)
                log.info(f"Target extracted from kast_info.json: {target}")
                console.print(
                    f"[cyan]Target extracted from kast_info.json:[/cyan] {target}"
                )
            except json.JSONDecodeError as e:
                console.print(
                    f"[bold red]Error:[/bold red] Failed to parse kast_info.json: {e}"
                )
                sys.exit(1)
    elif not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    log.info(f"Output directory: {out_dir}")

    start_time = time.time()
    start_timestamp = datetime.now().isoformat()

    registry = PluginRegistry(log, cli_args=args, config_manager=config_manager)
    all_instances = registry.all_instances()
    log.info(
        f"Discovered {len(all_instances)} plugins: {[p.name for p in all_instances]}"
    )

    if run_only:
        requested_names = [n.strip() for n in run_only.split(",")]
        log.info(f"--run-only specified: {requested_names}")
        available_names = {p.name for p in all_instances}
        invalid = [n for n in requested_names if n not in available_names]
        if invalid:
            console.print(
                f"[bold red]Error:[/bold red] Invalid plugin name(s): {', '.join(invalid)}"
            )
            sys.exit(1)
        selected_plugins = [registry.get(n) for n in requested_names]
        log.info(
            f"Filtered to {len(selected_plugins)} plugin(s): "
            f"{[p.name for p in selected_plugins]}"
        )
    else:
        selected_plugins = all_instances

    orchestrator = ScannerOrchestrator(
        selected_plugins, args, out_dir, log, is_report_only
    )
    results = orchestrator.run()

    end_time = time.time()
    end_timestamp = datetime.now().isoformat()

    processed_files = list(Path(out_dir).glob("*_processed.json"))
    plugin_results: list = []
    ai_summary = None
    ai_error: str | None = None
    if processed_files:
        for pf in processed_files:
            try:
                plugin_results.append(json.loads(pf.read_text()))
            except (json.JSONDecodeError, OSError) as e:
                log.warning(f"Failed to load {pf}: {e}")

    if ai_summary_flag and not dry_run and plugin_results:
        try:
            from kast.ai.config import get_ai_adapter
            from kast.ai.summary import generate_ai_summary
            from kast.report.data import collect_report_data
            adapter = get_ai_adapter(ai_adapter, ai_model, endpoint_url=ai_endpoint)
            tmp_data = collect_report_data(plugin_results, target)
            ai_summary = generate_ai_summary(adapter, tmp_data)
            log.info(
                f"AI summary generated: model={ai_summary['_meta']['model']}, "
                f"tokens={ai_summary['_meta']['tokens_in']}+{ai_summary['_meta']['tokens_out']}, "
                f"latency={ai_summary['_meta']['latency_ms']}ms"
            )
        except Exception as e:
            ai_error = str(e)
            log.exception("AI summary generation failed")
            console.print(f"[yellow]Warning:[/yellow] AI summary unavailable: {e}")

    if not dry_run and not is_report_only:
        kast_info = {
            "kast_version": KAST_VERSION,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "duration_seconds": round(end_time - start_time, 2),
            "cli_arguments": {
                "target": target, "mode": mode, "parallel": parallel,
                "max_workers": max_workers, "verbose": verbose,
                "output_dir": str(out_dir), "run_only": run_only,
                "log_dir": log_dir, "format": format_, "logo": logo,
                "dry_run": dry_run, "report_only": report_only_path,
                "ai_summary": ai_summary_flag,
            },
            "plugins": orchestrator.get_plugin_timings(),
            "ai": _build_ai_info(ai_summary_flag, ai_adapter, ai_summary, ai_error, endpoint=ai_endpoint),
        }
        info_file = out_dir / "kast_info.json"
        try:
            write_json_atomic(info_file, kast_info)
            log.info(f"Kast info written to {info_file}")
        except Exception as e:
            log.error(f"Failed to write kast_info.json: {e}")
    elif not dry_run and is_report_only and ai_summary_flag:
        # Update only the ai block in the existing kast_info.json so the
        # re-rendered report's metadata stays consistent.
        info_file = out_dir / "kast_info.json"
        try:
            existing = json.loads(info_file.read_text()) if info_file.exists() else {}
            existing["ai"] = _build_ai_info(
                ai_summary_flag, ai_adapter, ai_summary, ai_error, endpoint=ai_endpoint
            )
            write_json_atomic(info_file, existing)
            log.info("kast_info.json ai block updated after rerun")
        except Exception as e:
            log.error(f"Failed to update kast_info.json: {e}")

    if processed_files:
        console.print("[green]Post-processed JSON files created:[/green]")
        for pf in processed_files:
            console.print(f"  - {pf}")
        try:
            from kast.report_builder import generate_html_report, generate_pdf_report

            if format_ in ("html", "both"):
                html_path = out_dir / "kast_report.html"
                generate_html_report(
                    plugin_results, str(html_path), target, custom_logo_path,
                    ai_summary=ai_summary, ai_error=ai_error,
                )
                console.print(f"[green]HTML report generated:[/green] {html_path}")
                log.info(f"HTML report generated at {html_path}")

            if format_ in ("pdf", "both"):
                pdf_path = out_dir / "kast_report.pdf"
                generate_pdf_report(
                    plugin_results, str(pdf_path), target, custom_logo_path,
                    ai_summary=ai_summary, ai_error=ai_error,
                )
                console.print(f"[green]PDF report generated:[/green] {pdf_path}")
                log.info(f"PDF report generated at {pdf_path}")
        except Exception as e:
            console.print(f"[bold red]Error generating report:[/bold red] {e}")
            log.exception("Failed to generate report")
