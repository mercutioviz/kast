# Dry-Run Command Display Feature

## Overview

Enhanced the `--dry-run` feature to display the actual commands that would be executed by each plugin, along with operational details for internal logic plugins.

## Implementation Date
December 21, 2025

## What Was Changed

### 1. Base Plugin Class (`kast/plugins/base.py`)

Added a new method `get_dry_run_info()` to the `KastPlugin` base class:

```python
def get_dry_run_info(self, target, output_dir):
    """
    Return information about what this plugin would do in a real run.
    
    For external tool plugins:
    - Return the actual CLI commands that would be executed
    - Include all configuration-dependent flags and parameters
    
    For internal logic plugins:
    - Describe the operations that would be performed
    - List the steps in sequence
    
    :param target: The target that would be scanned
    :param output_dir: The output directory that would be used
    :return: Dict with keys:
        - 'commands': List of command strings (for external tools)
        - 'description': Plugin description
        - 'operations': String or list describing what would happen
    """
```

This method provides a default implementation that can be overridden by each plugin.

### 2. Orchestrator (`kast/orchestrator.py`)

Updated the dry-run mode section to:
- Call `get_dry_run_info()` for each plugin
- Display commands in a numbered list format (for plugins with multiple commands)
- Show operations for internal logic plugins
- Present information in a clear, formatted structure

### 3. Plugin Implementations

Implemented `get_dry_run_info()` in the following plugins:

#### External Tool Plugins

**TestSSL Plugin** (`kast/plugins/testssl_plugin.py`):
- Displays the full testssl command with all configuration flags
- Shows: vulnerability tests, cipher tests, connection timeout, warnings mode
- Example output:
  ```
  testssl -U -E --connect-timeout 10 --warnings=batch -oJ /path/to/output.json example.com
  ```

**WhatWeb Plugin** (`kast/plugins/whatweb_plugin.py`):
- Shows the whatweb command with aggression level and output format
- Example output:
  ```
  whatweb -a 3 example.com --log-json /path/to/output.json
  ```

**Related Sites Plugin** (`kast/plugins/related_sites_plugin.py`):
- Displays TWO commands (subfinder + httpx) in sequence
- Shows all httpx configuration: ports, rate limits, threads, timeout
- Example output:
  ```
  [1] subfinder -d example.com -o /path/to/output.json -json -silent
  [2] httpx -l /path/to/targets.txt -json -o /path/to/output.json -silent -timeout 10 -retries 2 -threads 50 -rate-limit 10 -ports 80,443,8080,8443,8000,8888 -follow-redirects -status-code -title -tech-detect -websocket -cdn
  ```

#### Internal Logic Plugins

**Script Detection Plugin** (`kast/plugins/script_detection_plugin.py`):
- Lists the sequential operations that would be performed
- No CLI commands, but shows internal workflow
- Example output:
  ```
  1. Fetch HTML from https://example.com
  2. Parse HTML with BeautifulSoup
  3. Extract all <script> tags with 'src' attributes
  4. Analyze script origins, SRI, and HTTPS usage
  5. Correlate findings with Mozilla Observatory results (if available)
  ```

## Usage

Run KAST with the `--dry-run` flag:

```bash
# Dry run for specific plugins
python -m kast.main --target example.com --dry-run --run-only testssl,whatweb

# Dry run for all plugins
python -m kast.main --target example.com --dry-run

# Dry run with mode filter
python -m kast.main --target example.com --dry-run --mode passive
```

## Output Format

The dry-run output now shows:

```
Plugin: Test SSL (testssl)
Type: passive
Priority: 50
Description: Tests SSL and TLS posture
Commands that would be executed:
  testssl -U -E --connect-timeout 10 --warnings=batch -oJ /path/to/output.json example.com
----------------------------------------------------------------------
```

For plugins with multiple commands:
```
Plugin: Related Sites Discovery (related_sites)
Type: passive
Priority: 45
Description: Discovers related subdomains and probes for live web services
Commands that would be executed:
  [1] subfinder -d example.com -o /path/to/output.json -json -silent
  [2] httpx -l /path/to/targets.txt -json -o /path/to/output.json -silent ...
----------------------------------------------------------------------
```

For internal logic plugins:
```
Plugin: External Script Detection (script_detection)
Type: passive
Priority: 10
Description: Detects and analyzes external JavaScript files loaded by the target.
Operations that would be performed:
  1. Fetch HTML from https://example.com
  2. Parse HTML with BeautifulSoup
  3. Extract all <script> tags with 'src' attributes
  4. Analyze script origins, SRI, and HTTPS usage
  5. Correlate findings with Mozilla Observatory results (if available)
----------------------------------------------------------------------
```

## Benefits

1. **Transparency**: Users can see exactly what commands will be executed before running
2. **Learning**: New users can learn the command syntax and options for each tool
3. **Debugging**: Helps developers verify configuration is being applied correctly
4. **Documentation**: Serves as living documentation of how each tool is invoked
5. **Security**: Allows security review of commands before execution

## Configuration Awareness

The displayed commands reflect the current configuration:
- Configuration file settings (`~/.config/kast/config.yaml`)
- CLI overrides (e.g., `--set plugin.option=value`)
- Default values from plugin schemas

This means the dry-run output shows the actual commands that would run given the current configuration state.

## Future Enhancements

To extend this feature to other plugins, implement `get_dry_run_info()` in each plugin:

1. For external tool plugins: Build the command string exactly as it would be executed
2. For internal logic plugins: List the operations in order
3. Return a dictionary with `commands`, `description`, and `operations` keys

Example template:
```python
def get_dry_run_info(self, target, output_dir):
    """Return dry-run information for this plugin."""
    # For external tools
    cmd = ["tool_name", "--option", "value", target]
    return {
        "commands": [' '.join(cmd)],
        "description": self.description,
        "operations": "Brief description of what happens"
    }
    
    # For internal logic
    return {
        "commands": [],  # No CLI commands
        "description": self.description,
        "operations": [
            "Step 1: Do something",
            "Step 2: Do something else",
            "Step 3: Generate results"
        ]
    }
```

## Notes

- Plugins that haven't implemented `get_dry_run_info()` will fall back to the default base class implementation
- The base implementation provides basic information but won't show actual commands
- All new plugins should implement this method for consistency
