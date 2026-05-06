"""
KAST - Kali Automated Scan Tool
"""

from . import utils
from . import orchestrator
from . import report_builder
from . import report_templates

try:
    from importlib.metadata import PackageNotFoundError, version as _pkg_version
    __version__ = _pkg_version("kast")
except (ImportError, Exception):
    from pathlib import Path as _Path
    try:
        __version__ = (_Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
    except Exception:
        __version__ = "unknown"