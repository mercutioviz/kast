"""``kast plugins`` subcommands (Phase B3).

Lives in its own module so per-subcommand logic doesn't accumulate in
``kast.cli.main``. The main module imports the ``plugins`` group and
registers it on the root Click group.

Provides:

- ``kast plugins list [--json]``  — list every plugin with status
- ``kast plugins show NAME [--json]`` — full detail on one plugin
- ``kast plugins deps``           — dependency tree filtered by mode
"""

from __future__ import annotations

import json
import logging

import click
from rich.console import Console

from kast.config_manager import ConfigManager
from kast.registry import PluginRegistry

console = Console()


def _plugin_to_dict(plugin) -> dict:
    """Common metadata extraction used by both list --json and show --json."""
    return {
        "name": plugin.name,
        "display_name": plugin.display_name,
        "description": plugin.description,
        "scan_type": plugin.scan_type,
        "priority": plugin.priority,
        "available": plugin.is_available(),
        "website_url": getattr(plugin, "website_url", None),
        "output_type": getattr(plugin, "output_type", None),
    }


@click.group()
def plugins() -> None:
    """Plugin management commands."""
    pass


@plugins.command(name="list")
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of formatted text.")
def plugins_list(json_output: bool) -> None:
    """List all available plugins."""
    logging.basicConfig(level=logging.CRITICAL)
    log = logging.getLogger("kast")
    registry = PluginRegistry(log)

    instances = registry.all_instances()
    if json_output:
        from kast.cli.main import KAST_VERSION  # late to avoid import cycles
        click.echo(
            json.dumps(
                {
                    "kast_version": KAST_VERSION,
                    "plugins": [_plugin_to_dict(p) for p in instances],
                },
                indent=2,
            )
        )
        return

    console.print("[bold cyan]Available KAST Plugins:[/bold cyan]\n")
    if not instances:
        console.print("[yellow]No plugins found.[/yellow]")
        return
    for p in instances:
        avail = p.is_available()
        status = "[green]✓[/green]" if avail else "[red]✗[/red]"
        console.print(
            f"{status} [bold]{p.name}[/bold] (priority: {p.priority}, type: {p.scan_type})"
        )
        console.print(f"  {p.description}")
        if not avail:
            console.print("  [dim red]Tool not available in PATH[/dim red]")
        console.print()


@plugins.command(name="show")
@click.argument("name")
@click.option("--json", "json_output", is_flag=True,
              help="Emit machine-readable JSON instead of formatted text.")
def plugins_show(name: str, json_output: bool) -> None:
    """Show full detail on a single plugin (identity + config schema)."""
    logging.basicConfig(level=logging.CRITICAL)
    log = logging.getLogger("kast")
    registry = PluginRegistry(log)

    try:
        plugin = registry.get(name)
    except KeyError:
        # Use Click's UsageError for a clean exit code (2) and friendly message
        available_names = sorted(p.name for p in registry.all_instances())
        raise click.UsageError(
            f"No plugin named {name!r}. Available plugin names: "
            f"{', '.join(available_names)}"
        )

    info = _plugin_to_dict(plugin)
    info["dependencies"] = [
        {"plugin": dep.get("plugin")} for dep in getattr(plugin, "dependencies", [])
    ]
    info["config_schema"] = type(plugin).config_schema

    if json_output:
        click.echo(json.dumps(info, indent=2))
        return

    # Formatted output
    console.print(f"[bold cyan]Plugin:[/bold cyan] {info['name']} ({info['display_name']})")
    console.print(f"[bold]Description:[/bold] {info['description']}")
    console.print(f"[bold]Type:[/bold] {info['scan_type']}")
    console.print(f"[bold]Priority:[/bold] {info['priority']}")
    if info.get("website_url"):
        console.print(f"[bold]Website:[/bold] {info['website_url']}")
    console.print(
        f"[bold]Available:[/bold] {'[green]✓[/green]' if info['available'] else '[red]✗ (tool not in PATH)[/red]'}"
    )

    deps = info["dependencies"]
    if deps:
        console.print("[bold]Dependencies:[/bold]")
        for dep in deps:
            console.print(f"  • {dep['plugin']}")
    else:
        console.print("[bold]Dependencies:[/bold] (none)")

    schema = info["config_schema"]
    properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
    if properties:
        console.print("\n[bold cyan]Configuration options:[/bold cyan]")
        for key, prop in properties.items():
            type_str = prop.get("type", "any")
            if isinstance(type_str, list):
                type_str = "|".join(type_str)
            default = prop.get("default", "(none)")
            desc = prop.get("description", "")
            console.print(
                f"  [bold]{key}[/bold] ({type_str}, default: {default!r})"
            )
            if desc:
                console.print(f"    {desc}")
    else:
        console.print("\n[dim]No configurable options.[/dim]")


@plugins.command(name="deps")
@click.option("-m", "--mode", type=click.Choice(["active", "passive", "both"]),
              default="passive", help="Scan mode filter.")
@click.option("--config", "config_path", type=click.Path(),
              help="Path to configuration file.")
@click.option("--set", "set_overrides", multiple=True,
              help="Override config value: --set plugin.key=value")
def plugins_deps(mode: str, config_path: str | None,
                 set_overrides: tuple[str, ...]) -> None:
    """Show plugin dependency tree filtered by scan mode."""
    from kast.cli.main import _make_args_namespace
    from kast.utils import show_dependency_tree

    log = logging.getLogger("kast")
    args = _make_args_namespace(mode=mode, config=config_path, set=list(set_overrides))

    config_manager = ConfigManager(cli_args=args, logger=log)
    config_manager.load(config_path)
    registry = PluginRegistry(log, cli_args=args, config_manager=config_manager)
    tree_output = show_dependency_tree(registry, mode, log)
    console.print(tree_output)
