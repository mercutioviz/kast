"""Click-based CLI dispatcher for kast (Phase B1).

Subcommand structure:

    kast scan -t TARGET ...           Run a scan
    kast plugins list [--json]        List available plugins
    kast plugins deps                 Plugin dependency tree
    kast config schema                Export plugin config JSON schema
    kast config init                  Create default config file
    kast config show                  Show merged config
    kast version                      Print version

Phase B4/B5/B6 add ``kast registry``, ``kast doctor``, ``kast self-update``.

The legacy v2 argv shape (``kast --target X`` etc.) is translated to
the equivalent subcommand form by ``kast.cli._translate_v2_argv`` before
Click parses it; that wrapper is the B7 deliverable.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler

from kast.config_manager import ConfigManager
from kast.core.atomic import write_json_atomic
from kast.orchestrator import ScannerOrchestrator
from kast.registry import PluginRegistry

console = Console()

# Suppress some noisy library loggers across all subcommands.
for _name in ("weasyprint", "PIL", "fontTools", "fontTools.subset",
              "fontTools.ttLib", "fontTools.ttLib.ttFont"):
    logging.getLogger(_name).setLevel(logging.WARNING)


def _read_version() -> str:
    """Read VERSION from project root."""
    try:
        version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_file.read_text().strip()
    except Exception:
        return "unknown"


KAST_VERSION = _read_version()


def _setup_logging(log_dir: str, verbose: bool) -> None:
    """Set up Rich-based logging plus a file handler. Mirrors v2 main.py."""
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
    logging.debug(f"Logging initialized. Log file: {log_file}")


def _make_args_namespace(**overrides) -> argparse.Namespace:
    """Build an argparse-style Namespace for code that still expects one
    (ConfigManager, plugins, orchestrator). Click params get translated to
    the namespace fields these consumers read.
    """
    defaults = dict(
        verbose=False,
        target=None,
        mode="passive",
        output_dir=None,
        report_only=None,
        format="html",
        dry_run=False,
        parallel=False,
        max_workers=5,
        log_dir="/var/log/kast/",
        logo=None,
        run_only=None,
        httpx_rate_limit=10,
        zap_profile=None,
        config=None,
        set=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
)
def cli() -> None:
    """kast — Kali Automated Scan Tool"""
    pass


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@cli.command()
def version() -> None:
    """Show kast version and exit."""
    console.print(f"[bold cyan]KAST version {KAST_VERSION}[/bold cyan]")


# ---------------------------------------------------------------------------
# plugins
# ---------------------------------------------------------------------------


@cli.group()
def plugins() -> None:
    """Plugin management commands."""
    pass


@plugins.command(name="list")
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of formatted text.")
def plugins_list(json_output: bool) -> None:
    """List all available plugins."""
    logging.basicConfig(level=logging.CRITICAL)
    log = logging.getLogger("kast")
    registry = PluginRegistry(log)

    instances = registry.all_instances()
    if json_output:
        manifest = [
            {
                "name": p.name,
                "display_name": p.display_name,
                "description": p.description,
                "scan_type": p.scan_type,
                "priority": p.priority,
                "available": p.is_available(),
                "website_url": getattr(p, "website_url", None),
            }
            for p in instances
        ]
        click.echo(json.dumps({"kast_version": KAST_VERSION, "plugins": manifest}, indent=2))
        return

    console.print("[bold cyan]Available KAST Plugins:[/bold cyan]\n")
    if not instances:
        console.print("[yellow]No plugins found.[/yellow]")
        return
    for p in instances:
        avail = p.is_available()
        status = "[green]✓[/green]" if avail else "[red]✗[/red]"
        console.print(
            f"{status} [bold]{p.name}[/bold] (priority: {p.priority}, type: {p.scan_type})"
        )
        console.print(f"  {p.description}")
        if not avail:
            console.print("  [dim red]Tool not available in PATH[/dim red]")
        console.print()


@plugins.command(name="deps")
@click.option("-m", "--mode", type=click.Choice(["active", "passive", "both"]),
              default="passive", help="Scan mode filter.")
@click.option("--config", "config_path", type=click.Path(),
              help="Path to configuration file.")
@click.option("--set", "set_overrides", multiple=True,
              help="Override config value: --set plugin.key=value")
def plugins_deps(mode: str, config_path: str | None,
                 set_overrides: tuple[str, ...]) -> None:
    """Show plugin dependency tree filtered by scan mode."""
    from kast.utils import show_dependency_tree

    log = logging.getLogger("kast")
    args = _make_args_namespace(mode=mode, config=config_path, set=list(set_overrides))

    config_manager = ConfigManager(cli_args=args, logger=log)
    config_manager.load(config_path)
    registry = PluginRegistry(log, cli_args=args, config_manager=config_manager)
    tree_output = show_dependency_tree(registry, mode, log)
    console.print(tree_output)


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


@cli.group(name="config")
def config_group() -> None:
    """Configuration management."""
    pass


@config_group.command(name="schema")
def config_schema() -> None:
    """Export JSON schema for all plugins (used by kast-web)."""
    log = logging.getLogger("kast")
    args = _make_args_namespace(set=[])
    config_manager = ConfigManager(cli_args=args, logger=log)
    registry = PluginRegistry(log)
    config_manager.collect_schemas_from_classes(registry.discover())
    click.echo(config_manager.export_schema(format="json"))


@config_group.command(name="init")
def config_init() -> None:
    """Create default configuration file with all plugin options."""
    log = logging.getLogger("kast")
    args = _make_args_namespace(set=[])
    config_manager = ConfigManager(cli_args=args, logger=log)
    registry = PluginRegistry(log)
    config_manager.collect_schemas_from_classes(registry.discover())
    config_path = config_manager.create_default_config()
    console.print(f"[green]Created default configuration at:[/green] {config_path}")
    console.print("[cyan]Edit this file to customize plugin settings.[/cyan]")


@config_group.command(name="show")
@click.option("--config", "config_path", type=click.Path(),
              help="Path to configuration file.")
def config_show(config_path: str | None) -> None:
    """Show the current merged configuration."""
    log = logging.getLogger("kast")
    args = _make_args_namespace(set=[], config=config_path)
    config_manager = ConfigManager(cli_args=args, logger=log)
    config_manager.load(config_path)
    registry = PluginRegistry(log)
    config_manager.collect_schemas_from_classes(registry.discover())
    console.print("[bold cyan]Current Configuration:[/bold cyan]")
    console.print(config_manager.show_current_config())


# ---------------------------------------------------------------------------
# scan
# ---------------------------------------------------------------------------


@cli.command()
@click.option("-t", "--target", help="Target domain name to scan.")
@click.option("-m", "--mode", type=click.Choice(["active", "passive", "both"]),
              default="passive", help="Scan mode (default: passive).")
@click.option("-o", "--output-dir", "output_dir", type=click.Path(),
              help="Custom output directory.")
@click.option("--report-only", "report_only_path", type=click.Path(exists=True),
              help="Re-render reports from existing scan directory.")
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
def scan(
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
) -> None:
    """Run a security scan against TARGET."""
    _setup_logging(log_dir, verbose)
    log = logging.getLogger("kast")

    if not target and not report_only_path:
        console.print(
            "[bold red]Error:[/bold red] --target is required unless using --report-only."
        )
        sys.exit(1)

    args = _make_args_namespace(
        target=target,
        mode=mode,
        output_dir=output_dir,
        report_only=report_only_path,
        format=format_,
        dry_run=dry_run,
        parallel=parallel,
        max_workers=max_workers,
        verbose=verbose,
        log_dir=log_dir,
        logo=logo,
        run_only=run_only,
        httpx_rate_limit=httpx_rate_limit,
        zap_profile=zap_profile,
        config=config_path,
        set=list(set_overrides),
    )

    config_manager = ConfigManager(cli_args=args, logger=log)

    if zap_profile:
        # Resolve relative to the package directory, not the cwd (pre-Phase A
        # this was a relative path bug; fixed here).
        package_dir = Path(__file__).resolve().parent.parent
        profile_file = package_dir / "config" / f"zap_automation_{zap_profile}.yaml"
        log.info(f"Using ZAP profile: {zap_profile} ({profile_file})")
        console.print(f"[cyan]Using ZAP profile:[/cyan] {zap_profile} ({profile_file})")
        args.set = list(args.set) + [f"zap.zap_config.automation_plan={profile_file}"]

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
            log.warning(f"Custom logo file must be PNG or JPG: {logo}. Using default.")
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
                console.print(f"[bold red]Error:[/bold red] Failed to parse kast_info.json: {e}")
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
        invalid_names = [n for n in requested_names if n not in available_names]
        if invalid_names:
            console.print(
                f"[bold red]Error:[/bold red] Invalid plugin name(s): "
                f"{', '.join(invalid_names)}"
            )
            console.print()
            ctx = click.get_current_context()
            ctx.invoke(plugins_list, json_output=False)
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

    if not dry_run and not is_report_only:
        kast_info = {
            "kast_version": KAST_VERSION,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "duration_seconds": round(end_time - start_time, 2),
            "cli_arguments": {
                "target": target,
                "mode": mode,
                "parallel": parallel,
                "max_workers": max_workers,
                "verbose": verbose,
                "output_dir": str(out_dir),
                "run_only": run_only,
                "log_dir": log_dir,
                "format": format_,
                "logo": logo,
                "dry_run": dry_run,
                "report_only": report_only_path,
            },
            "plugins": orchestrator.get_plugin_timings(),
        }
        info_file = out_dir / "kast_info.json"
        try:
            write_json_atomic(info_file, kast_info)
            log.info(f"Kast info written to {info_file}")
        except Exception as e:
            log.error(f"Failed to write kast_info.json: {e}")

    processed_files = list(Path(out_dir).glob("*_processed.json"))
    if processed_files:
        console.print("[green]Post-processed JSON files created:[/green]")
        for pf in processed_files:
            console.print(f"  - {pf}")
        try:
            plugin_results = []
            for pf in processed_files:
                plugin_results.append(json.loads(pf.read_text()))
            from kast.report_builder import generate_html_report, generate_pdf_report

            if format_ in ("html", "both"):
                html_path = out_dir / "kast_report.html"
                generate_html_report(
                    plugin_results, str(html_path), target, custom_logo_path
                )
                console.print(f"[green]HTML report generated:[/green] {html_path}")
                log.info(f"HTML report generated at {html_path}")

            if format_ in ("pdf", "both"):
                pdf_path = out_dir / "kast_report.pdf"
                generate_pdf_report(
                    plugin_results, str(pdf_path), target, custom_logo_path
                )
                console.print(f"[green]PDF report generated:[/green] {pdf_path}")
                log.info(f"PDF report generated at {pdf_path}")
        except Exception as e:
            console.print(f"[bold red]Error generating report:[/bold red] {e}")
            log.exception("Failed to generate report")
