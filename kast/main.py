#!/usr/bin/env python3
# main.py
# Entry point for KAST - Kali Automated Scan Tool. Handles CLI arguments, logging, and orchestrator setup.

import argparse
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

from kast.utils import discover_plugins
from kast.orchestrator import ScannerOrchestrator

# Set up rich console for CLI output
console = Console()

def parse_args():
    parser = argparse.ArgumentParser(
        description="KAST - Kali Automated Scan Tool"
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
        action="store_true",
        help="Report only mode (no scanning, just reporting)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (show what would be done, but don't execute)"
    )
    parser.add_argument(
        "-m", "--mode",
        choices=["active", "passive"],
        default="passive",
        help="Scan mode: active or passive (default: passive)"
    )
    parser.add_argument(
        "-t", "--target",
        type=str,
        required=True,
        help="Target domain name to scan"
    )
    parser.add_argument(
        "-p", "--parallel",
        action="store_true",
        help="Parallel mode: run tools simultaneously"
    )
    parser.add_argument(
        "-l", "--log-dir",
        type=str,
        default="/var/log/kast/",
        help="Log directory (default: /var/log/kast/)"
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

def main():
    args = parse_args()

    # Set up logging
    setup_logging(args.log_dir, args.verbose)
    log = logging.getLogger("kast")

    # Print startup info
    console.print(f"[bold green]KAST - Kali Automated Scan Tool[/bold green]")
    log.info("KAST started with arguments: %s", args)

    # Show dry run info if requested
    if args.dry_run:
        console.print("[yellow]Dry run mode enabled. No actions will be performed.[/yellow]")
        log.info("Dry run mode enabled.")

    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir).expanduser()
    else:
        now = datetime.now().strftime("%Y%m%d-%H%M%S")
        output_dir = Path.home() / "kast_results" / f"{args.target}-{now}"
    if args.dry_run:
        console.print(f"[yellow]Output directory (dry run): {output_dir}[/yellow]")
        log.info(f"Dry run output directory: {output_dir}")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        log.info(f"Output directory: {output_dir}")

    # Show report-only info if requested
    if args.report_only:
        console.print("[yellow]Report-only mode enabled. (Not yet implemented.)[/yellow]")
        log.info("Report-only mode enabled.")

    # Discover plugins
    plugins = discover_plugins(log)
    log.info(f"Discovered {len(plugins)} plugins: {[p.__name__ for p in plugins]}")

    # Launch orchestrator
    orchestrator = ScannerOrchestrator(plugins, args, output_dir, log)
    results = orchestrator.run()
    processed_files = list(output_dir.glob("*_processed.json"))
    if processed_files:
        console.print("[green]Post-processed JSON files created:[/green]")
        for pf in processed_files:
            console.print(f"  - {pf}")

    # Example output
    console.print(f"[cyan]Target:[/cyan] {args.target}")
    console.print(f"[cyan]Mode:[/cyan] {args.mode}")
    if args.parallel:
        console.print("[cyan]Parallel mode enabled.[/cyan]")
    if args.verbose:
        console.print("[cyan]Verbose mode enabled.[/cyan]")

if __name__ == "__main__":
    main()