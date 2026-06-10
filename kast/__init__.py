"""
KAST - Kali Automated Scan Tool
"""

from . import orchestrator, report_templates, utils

__all__ = ["orchestrator", "report_templates", "utils", "__version__"]

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("kast")
except (ImportError, Exception):
    from pathlib import Path as _Path
    try:
        __version__ = (_Path(__file__).resolve().parent.parent / "VERSION").read_text().strip()
    except Exception:
        __version__ = "unknown"
