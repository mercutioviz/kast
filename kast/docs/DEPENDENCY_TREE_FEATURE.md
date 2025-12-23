# Plugin Dependency Tree Feature

## Overview

The `--show-deps` flag displays a visual tree representation of all KAST plugins, showing their execution order based on priority and any dependencies between plugins. This helps users understand which plugins will run and in what order.

## Usage

```bash
# Show dependency tree with default scan mode (passive)
kast --show-deps

# Show dependency tree for active scan mode
kast --show-deps -m active

# Show dependency tree for both active and passive plugins
kast --show-deps -m both
```

## Output Format

The dependency tree displays:

1. **Header**: Shows the current scan mode filter
2. **Execution Order**: Lists all plugins sorted by priority (lower number = higher priority)
3. **Plugin Details**: For each plugin shows:
   - Availability status (✓ = available, ✗ = not available)
   - Priority number
   - Plugin name and scan type
   - Display name
   - Description
   - Availability status
   - Dependencies (if any)
4. **Summary**: Statistics about total plugins, dependencies, and filtered plugins

## Example Output

```
======================================================================
KAST Plugin Dependency Tree
======================================================================
Scan Mode: passive

Execution Order (by priority):

  [✓] Priority   5 | mozilla_observatory (passive)
      Display Name: Mozilla Observatory
      Description:  Runs Mozilla Observatory to analyze web application security.
      Status:       Available
      Dependencies: None

  [✓] Priority  10 | script_detection (passive)
      Display Name: External Script Detection
      Description:  Detects and analyzes external JavaScript files loaded by the target.
      Status:       Available
      Dependencies:
        └─ mozilla_observatory (<lambda>)

----------------------------------------------------------------------
Dependency Summary:
  - Total plugins (in mode):  8
  - With dependencies:        1
  - Independent:              7
  - Filtered out (mode):      2
    (ftap (active), zap (active))
======================================================================
```

## Understanding Dependencies

Plugins can depend on other plugins to run first. In the example above:
- `script_detection` depends on `mozilla_observatory`
- The dependency has a condition (shown as `<lambda>`) that must be satisfied

The orchestrator ensures dependencies are satisfied before running dependent plugins, especially important in parallel execution mode.

## Scan Mode Filtering

The `--show-deps` flag respects the `-m/--mode` argument:

- `passive` (default): Shows only passive reconnaissance plugins
- `active`: Shows only active scanning plugins  
- `both`: Shows all plugins regardless of type

Filtered plugins are listed in the summary section.

## Use Cases

1. **Pre-scan Planning**: Review which plugins will run before starting a scan
2. **Dependency Understanding**: See which plugins depend on others
3. **Tool Availability Check**: Quickly see which tools are available/missing
4. **Execution Order**: Understand the order plugins will execute based on priority
5. **Documentation**: Generate documentation of your plugin ecosystem

## Implementation Details

- Function: `show_dependency_tree()` in `kast/utils.py`
- CLI integration: `main.py` with `--show-deps` argument
- Filters plugins based on `scan_type` attribute matching the mode
- Sorts plugins by `priority` attribute (ascending)
- Extracts dependency information from plugin `dependencies` list
- Checks tool availability via `is_available()` method

## Related Commands

- `--list-plugins` or `-ls`: Lists all plugins without dependency information
- `--dry-run`: Shows what commands would be executed without running them
- `--run-only`: Filter to specific plugins

## Notes

- The dependency tree is displayed and the program exits immediately
- No target is required for `--show-deps` (unlike normal scans)
- Configuration files are loaded to properly initialize plugins
- All plugins are instantiated to extract metadata, but no scans are performed
