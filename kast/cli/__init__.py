"""kast CLI entry point.

Defines ``main()`` which:

1. Translates v2-style argv (``kast --target X``, ``kast --list-plugins``,
   etc.) to the v3 subcommand form, preserving the kast↔kast-web argv
   contract.
2. Invokes the Click dispatcher in ``kast.cli.main``.

The translation is intentionally narrow — only the v2 invocations
actually used by kast-web and by the v2 user surface. Anything already
in v3 form (subcommand first) passes through unchanged.
"""

from __future__ import annotations

import sys

# v3 subcommands recognized as already-translated argv.
V3_SUBCOMMANDS = frozenset({
    "scan",
    "plugins",
    "config",
    "registry",     # Phase B4
    "doctor",       # Phase B5
    "self-update",  # Phase B6
    "version",
})


def _translate_v2_argv(argv: list[str]) -> list[str]:
    """Translate v2-style argv into v3 subcommand form.

    Returns a new argv list (without ``sys.argv[0]``). Caller assigns to
    ``sys.argv[1:]`` before invoking the Click app.
    """
    # Empty argv or top-level help — let Click handle it.
    if not argv:
        return argv
    if argv[0] in ("-h", "--help"):
        return argv

    # Already in v3 form.
    if argv[0] in V3_SUBCOMMANDS:
        return argv

    # Special v2 flags that exit early (don't carry other args).
    if "--version" in argv or "-V" in argv:
        return ["version"]
    if "--list-plugins" in argv or "-ls" in argv:
        return ["plugins", "list"]

    # Special v2 flags that DO carry related flags forward.
    for flag, subcommand in [
        ("--show-deps", ["plugins", "deps"]),
        ("--config-init", ["config", "init"]),
        ("--config-show", ["config", "show"]),
        ("--config-schema", ["config", "schema"]),
    ]:
        if flag in argv:
            remaining = [a for a in argv if a != flag]
            return subcommand + remaining

    # Default: any other v2 invocation (--target, --report-only, etc.) is a scan.
    return ["scan"] + argv


def main() -> None:
    """Entry point with v2-argv compatibility translation."""
    # Local import: the Click app pulls in the heavy report/registry/orchestrator
    # imports, so deferring keeps ``import kast.cli`` cheap for callers that
    # only want _translate_v2_argv (e.g., tests).
    from kast.cli.main import cli

    argv = sys.argv[1:]
    translated = _translate_v2_argv(argv)
    if translated != argv:
        sys.argv = [sys.argv[0]] + translated
    cli(prog_name="kast")
