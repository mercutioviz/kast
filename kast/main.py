#!/usr/bin/env python3
"""kast — Kali Automated Scan Tool.

Module entrypoint for ``python -m kast.main`` and the ``kast`` console
script. The actual CLI dispatch (Click subcommands) lives in
``kast.cli``; this file is a thin shim so the historical module path keeps
working — both for the system-installed ``/usr/local/bin/kast`` launcher
and for any caller that imports ``kast.main:main``.
"""

from kast.cli import main

if __name__ == "__main__":
    main()
