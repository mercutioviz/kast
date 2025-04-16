#!/usr/bin/env python3

import argparse
import sys
import os
import time
from datetime import datetime

# Add the project root directory to sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)  # Go up one level from src/
sys.path.insert(0, project_root)

from rich.console import Console
from rich.panel import Panel

from src.modules.recon import coordinator as recon_coordinator
from src.modules.vuln_scan import vulnerability_scanner
from src.modules.reporting import report_generator
from src.modules.utils import banner, validators
from src.modules.utils.logger import setup_logger, get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)
console = Console()

def main():
    """Main function to run KAST"""
    parser = argparse.ArgumentParser(description="KAST - Kali Automated Scanning Tool")
    parser.add_argument("target", help="Target URL or IP address", nargs="?")
    parser.add_argument("-m", "--mode", choices=["recon", "vuln", "full"], default="full",
                        help="Scan mode: reconnaissance only, vulnerability scan only, or full scan (default)")
    parser.add_argument("-o", "--output", help="Output directory for reports")
    parser.add_argument("-q", "--quiet", action="store_true", help="Quiet mode, minimal output")
    parser.add_argument("--no-browser", action="store_true", help="Disable browser-based scanning")
    parser.add_argument("--no-online", action="store_true", help="Disable online services (SSL Labs, SecurityHeaders.io, Mozilla Observatory)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run mode - show what would be done without actually doing it")
    parser.add_argument("--no-banner", action="store_true", help="Skip banner and permission confirmation")
    
    args = parser.parse_args()
    
    # Display banner unless --no-banner is specified
    if not args.no_banner:
        banner.display_banner()
    
    # If no target is provided, show help and exit
    if args.target is None:
        parser.print_help()
        sys.exit(0)
    
    # Validate target
    if not validators.is_valid_target(args.target):
        console.print("[bold red]Invalid target. Please provide a valid URL or IP address.[/bold red]")
        sys.exit(1)
    
    # Legal disclaimer unless --no-banner is specified
    if not args.quiet and not args.no_banner:
        console.print(Panel.fit(
            "[yellow]LEGAL DISCLAIMER[/yellow]: This tool should only be used for authorized security testing. "
            "Unauthorized scanning of systems is illegal and unethical.",
            title="Warning",
            border_style="red"
        ))
        response = input("Do you confirm that you have permission to scan this target? (y/N): ")
        if response.lower() != 'y':
            console.print("[bold red]Scan aborted.[/bold red]")
            sys.exit(0)
    
    # Set up output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        output_dir = args.output
    else:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_dir = os.path.join(script_dir, "results")
        
        # Check if we have write permissions to the default directory
        if os.access(default_dir, os.W_OK):
            output_dir = os.path.join(default_dir, f"{args.target.replace('://', '_').replace('/', '_')}-{timestamp}")
        else:
            # Fall back to a directory in the user's home folder
            home_dir = os.path.expanduser("~")
            output_dir = os.path.join(home_dir, ".kast", "results", f"{args.target.replace('://', '_').replace('/', '_')}-{timestamp}")
            logger.warning(f"No write permission to {default_dir}, using {output_dir} instead")

    try:
        os.makedirs(output_dir, exist_ok=True)
    except PermissionError:
        # If we still can't create the directory, fall back to /tmp
        old_output_dir = output_dir
        output_dir = os.path.join("/tmp", f"kast-{args.target.replace('://', '_').replace('/', '_')}-{timestamp}")
        os.makedirs(output_dir, exist_ok=True)
        logger.warning(f"No write permission to {old_output_dir}, using {output_dir} instead")
    
    # Set up logger
    main_logger = setup_logger(args.target, output_dir)
    
    if args.dry_run:
        logger.info("[DRY RUN] This is a dry run. No actual scanning will be performed.")
    
    logger.info(f"Starting scan against {args.target}")
    logger.info(f"Reports will be saved to {output_dir}")
    
    results = {}
    
    # Run reconnaissance phase
    if args.mode in ["recon", "full"]:
        logger.info("Starting reconnaissance phase...")
        results["recon"], recon_dir = recon_coordinator.run_recon(
            args.target, 
            output_dir, 
            use_browser=(not args.no_browser),
            use_online_services=(not args.no_online),
            dry_run=args.dry_run
        )
    
    # Run vulnerability scanning phase
    if args.mode in ["vuln", "full"]:
        logger.info("Starting vulnerability scanning phase...")
        results["vuln"], vuln_dir = vulnerability_scanner.run_scan(
            args.target, 
            output_dir, 
            use_browser=(not args.no_browser),
            dry_run=args.dry_run
        )
    
    # Generate report
    logger.info("Generating report...")
    if args.dry_run:
        logger.info("[DRY RUN] Would generate report with collected data")
        report_path = os.path.join(output_dir, "report.html")
    else:
        report_path = report_generator.generate_report(args.target, results, output_dir)
    
    logger.info(f"Scan completed! Report available at: {report_path}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.error("Scan interrupted by user. Exiting...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        sys.exit(1)
