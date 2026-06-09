"""Resolution of kast filesystem locations with CLI/env/config overrides.

The "results dir" is the parent directory where every scan creates a
``{target}-{timestamp}/`` subdirectory. kast-web installs frequently
relocate this (e.g. ``/opt/kast-web/scan_results/``), so the location
must be overridable without per-call ``--output-dir`` plumbing.

Precedence (highest first):
1. Explicit CLI argument
2. ``KAST_RESULTS_DIR`` environment variable
3. ``global.results_dir`` in the first kast config file found
4. ``~/kast_results`` (default)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import yaml


_DEFAULT_RESULTS_DIR = "~/kast_results"

_CONFIG_SEARCH_PATHS = [
    Path("./kast_config.yaml"),
    Path.home() / ".config" / "kast" / "config.yaml",
    Path("/etc/kast/config.yaml"),
]


def _from_config_files() -> Optional[str]:
    for path in _CONFIG_SEARCH_PATHS:
        path = path.expanduser()
        if not path.exists():
            continue
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except (OSError, yaml.YAMLError):
            continue
        if not isinstance(data, dict):
            continue
        global_section = data.get("global") or {}
        if not isinstance(global_section, dict):
            continue
        value = global_section.get("results_dir")
        if value:
            return str(value)
    return None


def resolve_results_dir(cli_arg: Optional[str] = None) -> Path:
    """Return the base results directory, honoring CLI / env / config / default.

    The path is expanded (``~`` and ``$VAR``) but not created.
    """
    if cli_arg:
        raw = cli_arg
    elif os.environ.get("KAST_RESULTS_DIR"):
        raw = os.environ["KAST_RESULTS_DIR"]
    else:
        raw = _from_config_files() or _DEFAULT_RESULTS_DIR
    return Path(os.path.expandvars(raw)).expanduser()
