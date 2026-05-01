"""Atomic file writes for state-bearing kast outputs.

The kast↔kast-web contract (``docs/web-integration.md``) requires that
state-bearing files appear atomically — readers must never observe a
partially-written file. Specifically:

- ``<plugin>_processed.json`` (completion marker for each plugin)
- ``zap_scan_progress.json`` (live progress channel for ZAP scans)

In v2 these were written via ``with open(p, "w") as f: json.dump(...)``,
which leaves a window where a watcher can read a half-written file
(audit's "Surface 4 — Known implementation gaps"). v3 routes all such
writes through ``write_json_atomic``, which writes to a temp file and
then ``os.replace``\\s it into place — a POSIX rename(2) is atomic.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Union

PathLike = Union[str, "os.PathLike[str]"]


def write_json_atomic(path: PathLike, data: Any, **dump_kwargs: Any) -> None:
    """Write ``data`` as JSON to ``path`` atomically.

    Writes to ``<path>.tmp`` first, then ``os.replace``\\s the temp file
    over the target. Readers either see the previous file or the new
    file — never a partial.

    :param path: Destination path.
    :param data: JSON-serializable object.
    :param dump_kwargs: Additional kwargs for :func:`json.dump`. ``indent=2``
        is the default; pass ``indent=None`` for compact output.
        ``default`` is honored for non-standard types (e.g., ``default=str``).

    :raises TypeError, ValueError: If ``data`` is not JSON-serializable.
    :raises OSError: If the file cannot be written or replaced.

    On any failure, the temporary file is removed (best-effort) so a
    half-written ``<path>.tmp`` does not litter the output directory.
    """
    dump_kwargs.setdefault("indent", 2)

    path = Path(path)
    tmp = Path(f"{path}.tmp")

    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, **dump_kwargs)
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except (FileNotFoundError, OSError):
            pass
        raise
