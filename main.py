# main.py
# Relative path: kast/main.py
# Description: Main entry point for the KAST CLI tool. Handles argument parsing, logging, plugin loading, and scan orchestration.

import argparse
import logging
import os
import sys
from datetime import datetime

from .plugin_loader import load_plugins

DEFAULT_LOG_DIR = "/var/log/kast/"
DEFAULT_RESULTS_BASE = os.path.expanduser("~/kast_results/")

def setup_logging(verbosity, log_dir):
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "kast.log")
    log_level = logging.WARNING
    if verbosity == 1:
        log_level = logging.INFO
    elif verbosity >= 2:
        log_level = logging.DEBUG
    logging.basicConfig(
        filename=log_file,
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

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
        help="Directory to store results (default: ~/kast_results/www.target.com-YYYYMMDD-hhmmss/)"
    )
    parser.add_argument(
        "--log-dir", default=DEFAULT_LOG_DIR,
        help=f"Directory for log files (default: {DEFAULT_LOG_DIR})"
    )
    return parser.parse_args()

def main():
    args = parse_args()
    setup_logging(args.verbose, args.log_dir)

    # Prepare results directory
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target_dir = args.target.replace("://", "_").replace("/", "_")
    results_dir = args.output_dir or os.path.join(
        DEFAULT_RESULTS_BASE, f"{target_dir}-{timestamp}"
    )
    os.makedirs(results_dir, exist_ok=True)
    logging.info(f"Results will be saved to: {results_dir}")

    # Load plugins
    plugins = load_plugins()
    logging.info(f"Loaded plugins: {[p.name for p in plugins]}")

    # Run plugins
    for plugin in plugins:
        try:
            logging.info(f"Running plugin: {plugin.name}")
            result = plugin.run(args.target, results_dir)
            # Save or process result as needed
        except Exception as e:
            logging.error(f"Plugin {plugin.name} failed: {e}")

if __name__ == "__main__":
    main()
