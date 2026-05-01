"""Shared helpers for ``kast.cli.*`` subcommand modules.

Lives in its own module to avoid circular imports between
``kast.cli.main`` and the per-subcommand modules.
"""

from __future__ import annotations

import argparse


def make_args_namespace(**overrides) -> argparse.Namespace:
    """Build an argparse-style ``Namespace`` for code that still expects one.

    The orchestrator, plugins, and ConfigManager were written against the v2
    argparse layout. Click subcommand handlers translate Click params to a
    Namespace via this helper so those consumers don't have to change.
    """
    defaults = dict(
        verbose=False,
        target=None,
        mode="passive",
        output_dir=None,
        report_only=None,
        format="html",
        dry_run=False,
        parallel=False,
        max_workers=5,
        log_dir="/var/log/kast/",
        logo=None,
        run_only=None,
        httpx_rate_limit=10,
        zap_profile=None,
        config=None,
        set=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)
