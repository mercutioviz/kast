"""Click-based CLI dispatcher for kast.

Subcommand structure (Phase B):

    kast scan -t TARGET ...           Run a scan
    kast scan list                    List past scans
    kast scan show DIR                Detail of one past scan
    kast scan rerun DIR               Re-render reports from existing data
    kast plugins list [--json]        List available plugins
    kast plugins show NAME [--json]   Detail of one plugin
    kast plugins deps                 Plugin dependency tree
    kast doctor [--json]              Environment health check
    kast config schema                Export plugin config JSON schema
    kast config init                  Create default config file
    kast config show                  Show merged config
    kast version                      Print version

Phase B4/B6 add ``kast registry`` and ``kast self-update``.

Each subcommand group lives in its own module under ``kast/cli/``:
- ``kast/cli/scan.py``    — ``scan`` group (default + list/show/rerun)
- ``kast/cli/plugins.py`` — ``plugins`` group (list/show/deps)
- ``kast/cli/doctor.py``  — ``doctor`` command
- ``kast/cli/_shared.py`` — helpers used by multiple subcommands

The legacy v2 argv shape (``kast --target X`` etc.) is translated to
the equivalent subcommand form by ``kast.cli._translate_v2_argv`` before
Click parses it; that wrapper is the B7 deliverable.
"""

from __future__ import annotations

import logging
from pathlib import Path

import click
from rich.console import Console

from kast.cli._shared import make_args_namespace as _make_args_namespace
from kast.cli.doctor import doctor
from kast.cli.plugins import plugins
from kast.cli.registry import registry as registry_cmd
from kast.cli.scan import scan
from kast.cli.self_update import self_update
from kast.config_manager import ConfigManager
from kast.registry import PluginRegistry

console = Console()


def _read_version() -> str:
    """Read VERSION from project root."""
    try:
        version_file = Path(__file__).resolve().parent.parent.parent / "VERSION"
        return version_file.read_text().strip()
    except Exception:
        return "unknown"


KAST_VERSION = _read_version()


# ---------------------------------------------------------------------------
# Click root group
# ---------------------------------------------------------------------------


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]},
)
def cli() -> None:
    """kast — Kali Automated Scan Tool"""
    pass


# ---------------------------------------------------------------------------
# version (small enough to live inline)
# ---------------------------------------------------------------------------


@cli.command()
def version() -> None:
    """Show kast version and exit."""
    console.print(f"[bold cyan]KAST version {KAST_VERSION}[/bold cyan]")


# ---------------------------------------------------------------------------
# Subcommand groups defined in their own modules
# ---------------------------------------------------------------------------

cli.add_command(plugins)
cli.add_command(doctor)
cli.add_command(scan)
cli.add_command(registry_cmd)
cli.add_command(self_update)


# ---------------------------------------------------------------------------
# config (small enough to live inline)
# ---------------------------------------------------------------------------


@cli.group(name="config")
def config_group() -> None:
    """Configuration management."""
    pass


@config_group.command(name="schema")
def config_schema() -> None:
    """Export JSON schema for all plugins (used by kast-web)."""
    log = logging.getLogger("kast")
    args = _make_args_namespace(set=[])
    config_manager = ConfigManager(cli_args=args, logger=log)
    registry = PluginRegistry(log)
    config_manager.collect_schemas_from_classes(registry.discover())
    click.echo(config_manager.export_schema(format="json"))


@config_group.command(name="init")
def config_init() -> None:
    """Create default configuration file with all plugin options."""
    log = logging.getLogger("kast")
    args = _make_args_namespace(set=[])
    config_manager = ConfigManager(cli_args=args, logger=log)
    registry = PluginRegistry(log)
    config_manager.collect_schemas_from_classes(registry.discover())
    config_path = config_manager.create_default_config()
    console.print(f"[green]Created default configuration at:[/green] {config_path}")
    console.print("[cyan]Edit this file to customize plugin settings.[/cyan]")


@config_group.command(name="show")
@click.option("--config", "config_path", type=click.Path(),
              help="Path to configuration file.")
def config_show(config_path: str | None) -> None:
    """Show the current merged configuration."""
    log = logging.getLogger("kast")
    args = _make_args_namespace(set=[], config=config_path)
    config_manager = ConfigManager(cli_args=args, logger=log)
    config_manager.load(config_path)
    registry = PluginRegistry(log)
    config_manager.collect_schemas_from_classes(registry.discover())
    console.print("[bold cyan]Current Configuration:[/bold cyan]")
    console.print(config_manager.show_current_config())
