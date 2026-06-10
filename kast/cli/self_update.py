"""``kast self-update`` — Python wrapper around ``update.sh``.

Provides a kast-native command surface for the existing v2 update
script. The Python side is intentionally thin: it locates the bash
script, translates Click options to script flags, and shells out
under sudo.

In addition to the pass-through flags, this module implements
``--check-only`` natively in Python by comparing the local ``VERSION``
file to the version on ``origin/main`` via git. This avoids needing
sudo for the common "is there an update available?" check.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import click
from rich.console import Console

console = Console()


# Search order for update.sh:
# 1. Relative to package (dev checkout: <repo>/update.sh)
# 2. /opt/kast/update.sh (typical install location)
_DEV_UPDATE_PATH = Path(__file__).resolve().parent.parent.parent / "update.sh"
_INSTALLED_UPDATE_PATH = Path("/opt/kast/update.sh")


def _find_update_script() -> Path | None:
    """Locate ``update.sh`` or return None if not present anywhere we look."""
    for candidate in (_DEV_UPDATE_PATH, _INSTALLED_UPDATE_PATH):
        if candidate.exists():
            return candidate
    return None


def _read_local_version() -> str | None:
    """Read the project's VERSION file relative to the package."""
    version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
    if version_file.exists():
        return version_file.read_text().strip()
    return None


def _read_remote_version() -> str | None:
    """Get the VERSION on ``origin/main`` via git, or None if unavailable.

    Doesn't fetch; the caller is responsible for ``git fetch`` if they
    want the truly latest version. The ``--check-only`` command tells
    the user when this looks stale.
    """
    repo_dir = Path(__file__).resolve().parent.parent.parent
    try:
        result = subprocess.run(
            ["git", "show", "origin/main:VERSION"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


@click.command(name="self-update")
@click.option("--check-only", is_flag=True,
              help="Compare local VERSION to origin/main and exit (no sudo, no update).")
@click.option("--auto", is_flag=True,
              help="Non-interactive update; passes --auto to update.sh.")
@click.option("--force", is_flag=True,
              help="Force update despite warnings; passes --force to update.sh.")
@click.option("--dry-run", is_flag=True,
              help="Preview changes without modifying anything; passes --dry-run.")
@click.option("--list-backups", is_flag=True,
              help="List available backups (read-only; useful before --rollback).")
@click.option("--rollback", "rollback_timestamp",
              help="Roll back to a backup timestamp (e.g., 20260501_120000).")
@click.option("--skip-tools", is_flag=True,
              help="Skip external-tool re-check; passes --skip-tools.")
@click.option("--install-dir", "install_dir", type=click.Path(),
              help="Target install directory (default in update.sh: /opt/kast).")
def self_update(
    check_only: bool,
    auto: bool,
    force: bool,
    dry_run: bool,
    list_backups: bool,
    rollback_timestamp: str | None,
    skip_tools: bool,
    install_dir: str | None,
) -> None:
    """Update the kast installation, or roll back to a previous backup."""
    if check_only:
        _do_check_only()
        return

    script = _find_update_script()
    if script is None:
        raise click.UsageError(
            f"Could not locate update.sh. Looked at:\n"
            f"  - {_DEV_UPDATE_PATH} (dev checkout)\n"
            f"  - {_INSTALLED_UPDATE_PATH} (typical install)\n"
            f"Re-install kast or run update.sh from the repo root manually."
        )

    cmd: list[str] = ["sudo", str(script)]
    if auto:
        cmd.append("--auto")
    if force:
        cmd.append("--force")
    if dry_run:
        cmd.append("--dry-run")
    if list_backups:
        cmd.append("--list-backups")
    if rollback_timestamp:
        cmd.extend(["--rollback", rollback_timestamp])
    if skip_tools:
        cmd.append("--skip-tools")
    if install_dir:
        cmd.extend(["--install-dir", install_dir])

    console.print(f"[cyan]Running:[/cyan] {' '.join(cmd)}")
    console.print(
        "[dim]update.sh requires root privileges; sudo will prompt if needed.[/dim]"
    )
    try:
        result = subprocess.run(cmd)
        sys.exit(result.returncode)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted.[/yellow]")
        sys.exit(130)


def _do_check_only() -> None:
    """Compare local VERSION to origin/main:VERSION; print and exit."""
    local = _read_local_version()
    remote = _read_remote_version()

    if local is None:
        console.print(
            "[red]VERSION file not found — kast install may be incomplete.[/red]"
        )
        sys.exit(1)

    if remote is None:
        console.print(f"[bold]Local version:[/bold] {local}")
        console.print(
            "[yellow]Could not fetch remote version "
            "(no git remote, no network, or not a git checkout).[/yellow]"
        )
        console.print(
            "[dim]Run `git fetch origin` and retry "
            "to refresh the comparison.[/dim]"
        )
        sys.exit(2)

    console.print(f"[bold]Local version:[/bold]  {local}")
    console.print(f"[bold]Remote version:[/bold] {remote}")

    if local == remote:
        console.print("[green]Up to date.[/green]")
        sys.exit(0)
    else:
        console.print(
            "[yellow]Update available.[/yellow] "
            "Run [bold]kast self-update[/bold] (or [bold]kast self-update --auto[/bold] "
            "for non-interactive) to apply."
        )
        # Convention: exit 0 since the check itself succeeded; the difference
        # is informational. (CI hooks should grep the output if they need to
        # decide whether to apply.)
        sys.exit(0)
