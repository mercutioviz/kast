# kast/main.py
# Main CLI entry point for KAST. Handles argument parsing, logging, and plugin execution.

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
    level = logging.DEBUG if verbosity else logging.INFO
    logging.basicConfig(
        filename=log_file,
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

def main():
    parser = argparse.ArgumentParser(
        description="KAST: Kali Automated Scanning Tool"
    )
    parser.add_argument("target", help="Target domain or IP address")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose logging")
    parser.add_argument("-o", "--output", help="Output directory for results")
    parser.add_argument("--logdir", default=DEFAULT_LOG_DIR, help="Log directory (default: /var/log/kast/)")
    parser.add_argument("--plugins", nargs="*", help="List of plugins to run (default: all)")
    parser.add_argument("--help-plugins", action="store_true", help="List available plugins and exit")
    args = parser.parse_args()

    setup_logging(args.verbose, args.logdir)
    logging.info("KAST started")

    plugins = load_plugins()
    if args.help_plugins:
        print("Available plugins:")
        for name, cls in plugins.items():
            print(f"  {name}: {cls().description}")
        sys.exit(0)

    selected_plugins = args.plugins or list(plugins.keys())
    for pname in selected_plugins:
        if pname not in plugins:
            logging.error(f"Plugin '{pname}' not found.")
            print(f"Plugin '{pname}' not found.")
            sys.exit(1)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    results_dir = args.output or os.path.join(
        DEFAULT_RESULTS_BASE, f"{args.target}-{timestamp}"
    )
    os.makedirs(results_dir, exist_ok=True)

    for pname in selected_plugins:
        plugin_cls = plugins[pname]
        plugin = plugin_cls()
        try:
            result = plugin.run(args.target, {})
            result_file = os.path.join(results_dir, f"{pname}.json")
            with open(result_file, "w") as f:
                import json
                json.dump(result, f, indent=2)
            logging.info(f"Plugin {pname} completed successfully.")
        except Exception as e:
            logging.exception(f"Plugin {pname} failed: {e}")

if __name__ == "__main__":
    main()
