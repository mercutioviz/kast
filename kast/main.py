#!/usr/bin/env python3
# main.py
# Entry point for KAST - Kali Automated Scan Tool. Handles CLI arguments, logging, and orchestrator setup.

import argparse
import os
import sys
import logging
from datetime import datetime
from pathlib import Path
import json
import time

from rich.console import Console
from rich.logging import RichHandler

from kast.orchestrator import ScannerOrchestrator
from kast.config_manager import ConfigManager
from kast.registry import PluginRegistry
from kast.core.atomic import write_json_atomic

# Set up rich console for CLI output
console = Console()

# Read version from VERSION file
def get_version():
    """Read version from VERSION file in project root."""
    try:
        version_file = Path(__file__).parent.parent / "VERSION"
        with open(version_file, 'r') as f:
            return f.read().strip()
    except Exception as e:
        # Fallback version if file can't be read
        return "2.8.2-dev"

KAST_VERSION = get_version()

def parse_args():
    parser = argparse.ArgumentParser(
        description="KAST - Kali Automated Scan Tool"
    )
    parser.add_argument(
        "-V", "--version",
        action="store_true",
        help="Display the version of KAST and exit"
    )
    parser.add_argument(
        "-ls", "--list-plugins",
        action="store_true",
        help="List all available plugins and exit"
    )
    parser.add_argument(
        "--show-deps",
        action="store_true",
        help="Display plugin dependency tree filtered by scan mode and exit"
    )
    parser.add_argument(
        "--run-only",
        type=str,
        help="Run only specified plugins (comma-separated list of plugin names)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose mode"
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        help="Target output directory (default: ~/kast_results/www.target.com-YYYYMMDD-hhmmss/)"
    )
    parser.add_argument(
        "--report-only",
        type=str,
        help="Report only mode (specify the output directory containing raw JSON files)"
    )
    parser.add_argument(
        "--format",
        choices=["html", "pdf", "both"],
        default="html",
        help="Output format for the report (default: html)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (show what would be done, but don't execute)"
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["active", "passive", "both"],
        default="passive",
        help="Scan mode: active, passive, or both (default: passive)"
    )
    parser.add_argument(
        "-t", "--target",
        type=str,
        required=False,
        help="Target domain name to scan"
    )
    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Parallel mode: run tools simultaneously"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        help="Maximum number of parallel workers (default: 5, only used with --parallel)"
    )
    parser.add_argument(
        "-l", "--log-dir",
        type=str,
        default="/var/log/kast/",
        help="Log directory (default: /var/log/kast/)"
    )
    parser.add_argument(
        "--logo",
        type=str,
        help="Custom logo file (PNG or JPG) to use in reports (optional)"
    )
    parser.add_argument(
        "--httpx-rate-limit",
        type=int,
        default=10,
        help="(DEPRECATED: use --set related_sites.httpx_rate_limit=N) Rate limit for httpx requests per second (default: 10, used by related_sites plugin)"
    )
    parser.add_argument(
        "--zap-profile",
        type=str,
        choices=["quick", "standard", "thorough", "api", "passive"],
        help="ZAP scan profile shortcut: quick (~20min), standard (~45min), thorough (~90min), api (~30min), passive (~15min, safe for production)"
    )
    
    # Configuration management arguments
    parser.add_argument(
        "--config",
        type=str,
        help="Path to configuration file. If not specified, searches in order: ./kast_config.yaml (project), ~/.config/kast/config.yaml (user), /etc/kast/config.yaml (system)"
    )
    parser.add_argument(
        "--config-init",
        action="store_true",
        help="Create default configuration file with all plugin options"
    )
    parser.add_argument(
        "--config-show",
        action="store_true",
        help="Display current configuration (merged from file + CLI overrides)"
    )
    parser.add_argument(
        "--config-schema",
        action="store_true",
        help="Export JSON schema for all plugins (for GUI tools like kast-web)"
    )
    parser.add_argument(
        "--set",
        action="append",
        help="Override config value: --set plugin.key=value (can be used multiple times)"
    )
    
    return parser.parse_args()

def setup_logging(log_dir, verbose):
    log_dir = Path(log_dir).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "kast.log"

    # Set up RichHandler for colorized logs
    handlers = [RichHandler(console=console, rich_tracebacks=True, show_time=True)]
    handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers
    )
    logging.debug(f"Logging initialized. Log file: {log_file}")

def list_plugins():
    """
    List all available plugins with their descriptions.
    """
    # Create a minimal logger for plugin discovery
    logging.basicConfig(level=logging.CRITICAL)
    log = logging.getLogger("kast")

    # Use a PluginRegistry without cli_args/config_manager — list-plugins
    # only needs metadata, and the registry's MinimalArgs stand-in is enough.
    registry = PluginRegistry(log)

    console.print("[bold cyan]Available KAST Plugins:[/bold cyan]\n")

    instances = registry.all_instances()
    if not instances:
        console.print("[yellow]No plugins found.[/yellow]")
        return

    for plugin in instances:
        available = plugin.is_available()
        status = "[green]✓[/green]" if available else "[red]✗[/red]"
        console.print(
            f"{status} [bold]{plugin.name}[/bold] "
            f"(priority: {plugin.priority}, type: {plugin.scan_type})"
        )
        console.print(f"  {plugin.description}")
        if not available:
            console.print(f"  [dim red]Tool not available in PATH[/dim red]")
        console.print()

def write_kast_info(output_dir, kast_info):
    """
    Write kast execution information to kast_info.json
    
    :param output_dir: Directory where the JSON file will be written
    :param kast_info: Dictionary containing kast execution information
    """
    try:
        info_file = output_dir / "kast_info.json"
        write_json_atomic(info_file, kast_info)
        logging.getLogger("kast").info(f"Kast info written to {info_file}")
    except Exception as e:
        logging.getLogger("kast").error(f"Failed to write kast_info.json: {e}")

def main():
    args = parse_args()

    if args.version:
        console.print(f"[bold cyan]KAST version {KAST_VERSION}[/bold cyan]")
        sys.exit(0)

    if args.list_plugins:
        list_plugins()
        sys.exit(0)

    # Set up logging early for config commands and show-deps
    setup_logging(args.log_dir, args.verbose)
    log = logging.getLogger("kast")
    
    # Handle --show-deps flag
    if args.show_deps:
        from kast.utils import show_dependency_tree

        # Initialize configuration manager
        config_manager = ConfigManager(cli_args=args, logger=log)
        config_manager.load(args.config)

        # Build the registry once (handles discovery + instantiation +
        # legacy __init__ shape fallback).
        registry = PluginRegistry(log, cli_args=args, config_manager=config_manager)

        # Generate and display dependency tree
        tree_output = show_dependency_tree(registry, args.mode, log)
        console.print(tree_output)
        sys.exit(0)
    
    # Initialize configuration manager
    config_manager = ConfigManager(cli_args=args, logger=log)
    
    # Handle --zap-profile shortcut
    if args.zap_profile:
        profile_path = f"kast/config/zap_automation_{args.zap_profile}.yaml"
        log.info(f"Using ZAP profile: {args.zap_profile} ({profile_path})")
        console.print(f"[cyan]Using ZAP profile:[/cyan] {args.zap_profile} ({profile_path})")
        
        # Add to CLI overrides (will be processed when config is loaded)
        if not args.set:
            args.set = []
        args.set.append(f"zap.zap_config.automation_plan={profile_path}")
    
    # Handle config-only commands. Schemas are read directly from plugin
    # CLASSES (no instantiation) — Phase A5 moved identity to class attributes
    # so config_manager.collect_schemas_from_classes() is the canonical path.
    if args.config_schema:
        registry = PluginRegistry(log)
        config_manager.collect_schemas_from_classes(registry.discover())
        schema = config_manager.export_schema(format="json")
        console.print(schema)
        sys.exit(0)

    if args.config_init:
        registry = PluginRegistry(log)
        config_manager.collect_schemas_from_classes(registry.discover())
        config_path = config_manager.create_default_config()
        console.print(f"[green]Created default configuration at:[/green] {config_path}")
        console.print("[cyan]Edit this file to customize plugin settings.[/cyan]")
        sys.exit(0)

    if args.config_show:
        config_manager.load(args.config)
        registry = PluginRegistry(log)
        config_manager.collect_schemas_from_classes(registry.discover())
        config_yaml = config_manager.show_current_config()
        console.print("[bold cyan]Current Configuration:[/bold cyan]")
        console.print(config_yaml)
        sys.exit(0)
    
    # Handle target requirement - can be extracted from kast_info.json in report-only mode
    if not args.target and not args.report_only:
        console.print("[bold red]Error:[/bold red] --target is required unless using --version, --list-plugins, or config commands.")
        sys.exit(1)

    # Capture start time
    start_time = time.time()
    start_timestamp = datetime.now().isoformat()

    # Print startup info
    console.print(f"[bold green]KAST - Kali Automated Scan Tool[/bold green]")

    log.info("KAST started with arguments: %s", args)
    
    # Load configuration for normal operation
    config_manager.load(args.config)
    
    # Validate custom logo if provided
    custom_logo_path = None
    if args.logo:
        logo_path = Path(args.logo).expanduser()
        if not logo_path.exists():
            log.warning(f"Custom logo file not found: {args.logo}. Using default logo.")
            console.print(f"[yellow]Warning:[/yellow] Logo file '{args.logo}' not found. Using default logo.")
        elif logo_path.suffix.lower() not in ['.png', '.jpg', '.jpeg']:
            log.warning(f"Custom logo file must be PNG or JPG: {args.logo}. Using default logo.")
            console.print(f"[yellow]Warning:[/yellow] Logo file must be PNG or JPG. Using default logo.")
        else:
            custom_logo_path = str(logo_path.resolve())
            log.info(f"Using custom logo: {custom_logo_path}")
            console.print(f"[cyan]Using custom logo:[/cyan] {custom_logo_path}")

    # Show dry run info if requested
    if args.dry_run:
        #console.print("[yellow]Dry run mode enabled. No actions will be performed.[/yellow]")
        log.info("Dry run mode enabled.")

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
    else:
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path.home() / "kast_results" / f"{args.target}-{now}"

    if args.dry_run:
        #console.print(f"[yellow]Output directory (dry run): {output_dir}[/yellow]")
        log.info(f"Dry run output directory: {output_dir}")
    else:
        if args.report_only:
            log.info(f"Report-only output directory: {output_dir}")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            log.info(f"Output directory: {output_dir}")

    # Handle report-only mode
    if args.report_only:
        #console.print("[yellow]Report-only mode enabled.[/yellow]")
        log.info("Report-only mode enabled.")
        report_only=True

        # Check output_dir exists
        report_dir = Path(args.report_only)
        if not report_dir.exists():
            console.print(f"[bold red]Error:[/bold red] Output directory {report_dir} does not exist.")
            sys.exit(1)
        output_dir = report_dir
        
        # If target not provided, try to extract it from kast_info.json
        if not args.target:
            kast_info_path = output_dir / "kast_info.json"
            if not kast_info_path.exists():
                console.print(f"[bold red]Error:[/bold red] kast_info.json not found in {output_dir}")
                console.print("[yellow]Either provide --target or ensure kast_info.json exists in the report directory.[/yellow]")
                sys.exit(1)
            
            try:
                with open(kast_info_path, 'r') as f:
                    kast_info = json.load(f)
                
                # Extract target from cli_arguments
                if 'cli_arguments' in kast_info and 'target' in kast_info['cli_arguments']:
                    args.target = kast_info['cli_arguments']['target']
                    log.info(f"Target extracted from kast_info.json: {args.target}")
                    console.print(f"[cyan]Target extracted from kast_info.json:[/cyan] {args.target}")
                else:
                    console.print(f"[bold red]Error:[/bold red] Target not found in kast_info.json")
                    console.print("[yellow]The kast_info.json file must contain cli_arguments.target[/yellow]")
                    sys.exit(1)
            except json.JSONDecodeError as e:
                console.print(f"[bold red]Error:[/bold red] Failed to parse kast_info.json: {e}")
                sys.exit(1)
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] Failed to read kast_info.json: {e}")
                sys.exit(1)
    else:
        report_only=False

    # Build the plugin registry once (discovery + instantiation + schema
    # registration happen inside). All downstream code consumes instances.
    registry = PluginRegistry(log, cli_args=args, config_manager=config_manager)
    all_instances = registry.all_instances()
    log.info(
        f"Discovered {len(all_instances)} plugins: "
        f"{[p.name for p in all_instances]}"
    )

    # Filter plugins if --run-only is specified
    if args.run_only:
        requested_names = [name.strip() for name in args.run_only.split(',')]
        log.info(f"--run-only specified: {requested_names}")

        available_names = {p.name for p in all_instances}
        invalid_names = [name for name in requested_names if name not in available_names]

        if invalid_names:
            console.print(
                f"[bold red]Error:[/bold red] Invalid plugin name(s): "
                f"{', '.join(invalid_names)}"
            )
            console.print()
            list_plugins()
            sys.exit(1)

        selected_plugins = [registry.get(name) for name in requested_names]
        log.info(
            f"Filtered to {len(selected_plugins)} plugin(s): "
            f"{[p.name for p in selected_plugins]}"
        )
    else:
        selected_plugins = all_instances

    # Launch orchestrator with the already-instantiated plugins.
    orchestrator = ScannerOrchestrator(
        selected_plugins, args, output_dir, log, report_only
    )
    results = orchestrator.run()
    
    # Capture end time
    end_time = time.time()
    end_timestamp = datetime.now().isoformat()
    
    # Write kast_info.json if not in dry-run or report-only mode
    if not args.dry_run and not report_only:
        kast_info = {
            "kast_version": KAST_VERSION,
            "start_timestamp": start_timestamp,
            "end_timestamp": end_timestamp,
            "duration_seconds": round(end_time - start_time, 2),
            "cli_arguments": {
                "target": args.target,
                "mode": args.mode,
                "parallel": args.parallel,
                "max_workers": args.max_workers,
                "verbose": args.verbose,
                "output_dir": str(output_dir),
                "run_only": args.run_only,
                "log_dir": args.log_dir,
                "format": args.format,
                "logo": args.logo,
                "dry_run": args.dry_run,
                "report_only": args.report_only
            },
            "plugins": orchestrator.get_plugin_timings()
        }
        write_kast_info(output_dir, kast_info)
    
    processed_files = list(output_dir.glob("*_processed.json"))
    if processed_files:
        console.print("[green]Post-processed JSON files created:[/green]")
        for pf in processed_files:
            console.print(f"  - {pf}")
        
        # Generate report(s) based on format option
        try:
            plugin_results = []
            for pf in processed_files:
                with open(pf) as f:
                    plugin_results.append(json.load(f))
            
            from kast.report_builder import generate_html_report, generate_pdf_report
            
            # Generate HTML report
            if args.format in ['html', 'both']:
                html_path = output_dir / 'kast_report.html'
                generate_html_report(plugin_results, str(html_path), args.target, custom_logo_path)
                console.print(f"[green]HTML report generated:[/green] {html_path}")
                log.info(f"HTML report generated at {html_path}")
            
            # Generate PDF report
            if args.format in ['pdf', 'both']:
                pdf_path = output_dir / 'kast_report.pdf'
                generate_pdf_report(plugin_results, str(pdf_path), args.target, custom_logo_path)
                console.print(f"[green]PDF report generated:[/green] {pdf_path}")
                log.info(f"PDF report generated at {pdf_path}")
                
        except Exception as e:
            console.print(f"[bold red]Error generating report:[/bold red] {str(e)}")
            log.exception("Failed to generate report")

if __name__ == "__main__":
    main()
