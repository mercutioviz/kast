# utils.py
import importlib.util
import inspect
import os
import sys
from pathlib import Path

# Ensure parent directory of 'kast' is in sys.path
kast_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(kast_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def discover_plugins(log):
    plugins = []
    plugins_dir = Path(kast_dir) / "plugins"
    for file in plugins_dir.glob("*_plugin.py"):
        log.debug(f"Found plugin file: {file}")
        # Skip template_plugin.py so TemplatePlugin is never loaded
        if file.name == "template_plugin.py":
            log.debug("Skipping template_plugin.py (not a real plugin)")
            continue
        module_name = f"kast.plugins.{file.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr in dir(module):
            obj = getattr(module, attr)
            if not (
                isinstance(obj, type)
                and hasattr(obj, "run")
                and hasattr(obj, "is_available")
                and not inspect.isabstract(obj)
            ):
                continue
            # Phase B9: only include classes DEFINED in this file. Without
            # this check, classes imported by the plugin (e.g.
            # ExternalToolPlugin imported by whatweb_plugin and wafw00f_plugin)
            # get discovered as duplicate "plugins."
            if getattr(obj, "__module__", None) != module_name:
                continue
            # Also skip TemplatePlugin by class name (defensive)
            if obj.__name__ == "TemplatePlugin":
                log.debug("Skipping TemplatePlugin class (not a real plugin)")
                continue
            plugins.append(obj)

    # Sort plugins by priority
    plugins.sort(key=lambda x: x.priority)
    return plugins

def show_dependency_tree(registry, scan_mode, log):
    """
    Display a tree-like view of plugin dependencies, filtered by scan mode.

    :param registry: PluginRegistry instance providing plugin instances
    :param scan_mode: Scan mode filter ('active', 'passive', or 'both')
    :param log: Logger instance (kept for parity; instances are already loaded)
    :return: Formatted string containing dependency tree
    """
    output_lines = []
    output_lines.append("\n" + "="*70)
    output_lines.append("KAST Plugin Dependency Tree")
    output_lines.append("="*70)
    output_lines.append(f"Scan Mode: {scan_mode}\n")

    # Collect plugin metadata directly from registry instances. The registry
    # already handled discovery and instantiation (including the legacy
    # __init__(cli_args) fallback), so this loop has no try/except dance.
    plugin_metadata = []
    filtered_out = []

    for plugin_instance in registry.all_instances():
        plugin_scan_type = getattr(plugin_instance, "scan_type", "passive")

        # Filter by scan mode
        should_include = (
            scan_mode == "both" or
            plugin_scan_type == scan_mode
        )

        if not should_include:
            filtered_out.append({
                'name': plugin_instance.name,
                'scan_type': plugin_scan_type
            })
            continue

        # Collect metadata
        metadata = {
            'name': plugin_instance.name,
            'display_name': getattr(plugin_instance, 'display_name', plugin_instance.name),
            'description': plugin_instance.description,
            'priority': plugin_instance.priority,
            'scan_type': plugin_scan_type,
            'available': plugin_instance.is_available(),
            'dependencies': getattr(plugin_instance, 'dependencies', []),
            'instance': plugin_instance
        }
        plugin_metadata.append(metadata)

    # Sort by priority (already sorted, but ensure consistency)
    plugin_metadata.sort(key=lambda x: x['priority'])

    # Display execution order
    output_lines.append("Execution Order (by priority):\n")

    dep_count = 0
    independent_count = 0

    for meta in plugin_metadata:
        # Status indicator
        status = "✓" if meta['available'] else "✗"
        availability = "Available" if meta['available'] else "Not Available"

        # Format plugin header
        output_lines.append(f"  [{status}] Priority {meta['priority']:3d} | {meta['name']} ({meta['scan_type']})")
        output_lines.append(f"      Display Name: {meta['display_name']}")
        output_lines.append(f"      Description:  {meta['description']}")
        output_lines.append(f"      Status:       {availability}")

        # Format dependencies
        if meta['dependencies']:
            dep_count += 1
            output_lines.append("      Dependencies:")
            for dep in meta['dependencies']:
                dep_plugin = dep.get('plugin', 'unknown')
                condition = dep.get('condition')

                # Try to describe the condition
                condition_desc = "custom condition"
                if condition and hasattr(condition, '__name__'):
                    condition_desc = condition.__name__
                elif condition:
                    # Try to get a reasonable description
                    condition_str = str(condition)
                    if 'success' in condition_str.lower():
                        condition_desc = "requires success"
                    elif 'fail' in condition_str.lower():
                        condition_desc = "requires failure"
                    else:
                        condition_desc = "custom condition"

                output_lines.append(f"        └─ {dep_plugin} ({condition_desc})")
        else:
            independent_count += 1
            output_lines.append("      Dependencies: None")

        output_lines.append("")  # Blank line between plugins

    # Summary section
    output_lines.append("-"*70)
    output_lines.append("Dependency Summary:")
    output_lines.append(f"  - Total plugins (in mode):  {len(plugin_metadata)}")
    output_lines.append(f"  - With dependencies:        {dep_count}")
    output_lines.append(f"  - Independent:              {independent_count}")

    if filtered_out:
        output_lines.append(f"  - Filtered out (mode):      {len(filtered_out)}")
        plugins_str = ', '.join(f"{p['name']} ({p['scan_type']})" for p in filtered_out)
        output_lines.append(f"    ({plugins_str})")

    output_lines.append("="*70)
    output_lines.append("")

    return "\n".join(output_lines)
