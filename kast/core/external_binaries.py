"""Resolve paths to external CLI binaries that collide with Python packages.

The anthropic SDK (a required kast dep) pulls in the Python ``httpx`` HTTP
client as a transitive dependency. pip installs an entry point also named
``httpx`` into the virtualenv's ``bin/``, which shadows the ProjectDiscovery
``httpx`` CLI on PATH when the venv is active. Any code that wants the PD
binary must search well-known system paths first.
"""

from __future__ import annotations

import os

_PD_HTTPX_CANDIDATES = [
    "/usr/local/bin/httpx",
    "/usr/bin/httpx",
    os.path.expanduser("~/go/bin/httpx"),
    "/opt/homebrew/bin/httpx",  # macOS
]


def find_pd_httpx() -> str | None:
    """Return the path to the ProjectDiscovery httpx binary, or None."""
    for path in _PD_HTTPX_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    # Walk PATH manually, skipping any entry that looks like a venv bin
    # (a sibling ``activate`` script gives it away).
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory, "httpx")
        if not (os.path.isfile(candidate) and os.access(candidate, os.X_OK)):
            continue
        if os.path.exists(os.path.join(directory, "activate")):
            continue
        return candidate
    return None
