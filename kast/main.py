# File: kast/main.py
# Description: Main entry point for the KAST (Kali Automated Scanning Tool) CLI.
# Handles argument parsing, logging setup, plugin loading, and scan orchestration.

import argparse
import logging
import os
import sys
from datetime import datetime
from kast.plugin_loader import load_plugins
from kast.result_schema import ScanResult

DEFAULT_LOG_DIR = "/var/log/kast/"
DEFAULT_RESULTS_BASE = os.path.expanduser("~/kast_results/")

def setup_logging(verbosity, log_dir, target):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{target}.log")
    log_level = logging.WARNING  # Default
    if verbosity == 1:
        log_level = logging.INFO
    elif verbosity >= 2:
        log_level = logging.DEBUG
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

def parse_args():
    parser = argparse.ArgumentParser(
        description="KAST: Kali Automated Scanning Tool"
    )
    parser.add_argument("target", help="Target domain or IP to scan")
    parser.add_argument(
        "-v", "--verbose", action="count", default=0,
        help="Increase output verbosity (use -vv for debug)"
    )
    parser.add_argument(
        "-o", "--output-dir", default=None,
        help="Directory to store scan results (default: ~/kast_results/www.target.com-YYYYMMDD-hhmmss/)"
    )
    parser.add_argument(
        "--log-dir", default=DEFAULT_LOG_DIR,
        help=f"Directory for log files (default: {DEFAULT_LOG_DIR})"
    )
    parser.add_argument(
        "--plugins", nargs="*", default=None,
        help="List of plugins to run (default: all available)"
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Only generate report from previous scan results"
    )
    parser.add_argument(
        "--results-file", default=None,
        help="Path to previous scan results (for --report-only)"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_dir = args.output_dir or os.path.join(
        DEFAULT_RESULTS_BASE,
        f"{args.target}-{timestamp}"
    )
    os.makedirs(target_dir, exist_ok=True)
    setup_logging(args.verbose, args.log_dir, args.target)
    logging.info(f"Starting KAST scan for {args.target}")

    if args.report_only:
        if not args.results_file or not os.path.isfile(args.results_file):
            logging.error("Results file must be specified and exist in report-only mode.")
            sys.exit(1)
        # Reporting logic will go here later
        logging.info("Report-only mode not yet implemented.")
        sys.exit(0)

    plugins = load_plugins(args.plugins)
    scan_result = ScanResult(target=args.target, timestamp=timestamp, results=[])
    for plugin in plugins:
        try:
            result = plugin.run(args.target)
            scan_result.results.append(result)
        except Exception as e:
            logging.error(f"Plugin {plugin.name} failed: {e}")

    # Save results as JSON
    import json
    results_path = os.path.join(target_dir, "results.json")
    with open(results_path, "w") as f:
        json.dump(scan_result.to_dict(), f, indent=2)
    logging.info(f"Scan complete. Results saved to {results_path}")

if __name__ == "__main__":
    main()
