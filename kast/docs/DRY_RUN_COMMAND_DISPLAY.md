# Dry-Run Command Display Feature

## Overview

Enhanced the `--dry-run` flag to display the actual commands that KAST would execute for each plugin, providing valuable insight into what operations will be performed during a real scan.

## Implementation Date

December 21, 2025

## What Was Added

### 1. Base Plugin Method

Added `get_dry_run_info()` method to the base `KastPlugin` class in `kast/plugins/base.py`:

```python
def get_dry_run_info(self, target, output_dir):
    """
    Return information about what this plugin would do in a real run.
    Subclasses should override this to provide specific command information.
    
    Returns:
        dict: A dictionary containing:
            - 'commands': List of command strings that would be executed
            - 'description': Plugin description
            - 'operations': (optional) List of operations for internal plugins
    """
    return {
        "commands": [],
        "description": self.description
    }
```

### 2. Orchestrator Enhancement

Modified `kast/orchestrator.py` to call `get_dry_run_info()` and display the information:

- For plugins with commands: Displays numbered list of commands
- For plugins with operations: Displays numbered list of internal operations
- Provides clear visual separation between plugins

### 3. Plugin Implementations

Implemented `get_dry_run_info()` in all plugins:

#### External Tool Plugins (Show Commands)

1. **Observatory** (`observatory_plugin.py`)
   - Command: `mdn-http-observatory-scan <target>`

2. **Subfinder** (`subfinder_plugin.py`)
   - Command: `subfinder -d <target> -o <output_file> -json`

3. **Wafw00f** (`wafw00f_plugin.py`)
   - Command: `wafw00f <target> -a -vvv -f json -o <output_file>`

4. **WhatWeb** (`whatweb_plugin.py`)
   - Command: `whatweb -a 3 <target> --log-json <output_file>`

5. **Ftap** (`ftap_plugin.py`)
   - Command: `ftap --url <target> --detection-mode stealth -d <output_dir> -e json -f ftap.json`

6. **Testssl** (`testssl_plugin.py`)
   - Command: `testssl -U -E --connect-timeout 10 --warnings=batch -oJ <output_file> <target>`

7. **Katana** (`katana_plugin.py`)
   - Command: `katana -silent -u <target> -ob -rl 15 -fs fqdn -o <output_file>`

8. **ZAP** (`zap_plugin.py`)
   - Shows ZAP API configuration and scan commands (mode-dependent)

#### Internal Plugins (Show Operations)

1. **Script Detection** (`script_detection_plugin.py`)
   - Operations:
     1. Fetch HTML from target URL
     2. Parse HTML with BeautifulSoup
     3. Extract all `<script>` tags with 'src' attributes
     4. Analyze script origins, SRI, and HTTPS usage
     5. Correlate findings with Mozilla Observatory results (if available)

2. **Related Sites** (`related_sites_plugin.py`)
   - Commands:
     1. `subfinder -d <root_domain> -o <output_file> -json -silent`
     2. `httpx -l <targets_file> -json -o <output_file> -silent -timeout 10 -retries 2 -threads 50 -rate-limit 10 -ports 80,443,8080,8443,8000,8888 -follow-redirects -status-code -title -tech-detect -websocket -cdn`

## Example Output

```
$ kast -t www.example.com --dry-run

INFO     Dry run mode enabled. Showing what would be executed:
INFO     ================================================================

Plugin: Mozilla Observatory (mozilla_observatory)
Type: passive
Priority: 5
Description: Runs Mozilla Observatory to analyze web application security.
Commands that would be executed:
  mdn-http-observatory-scan www.example.com
----------------------------------------------------------------

Plugin: External Script Detection (script_detection)
Type: passive
Priority: 10
Description: Detects and analyzes external JavaScript files loaded by the target.
Operations that would be performed:
  1. Fetch HTML from https://www.example.com
  2. Parse HTML with BeautifulSoup
  3. Extract all <script> tags with 'src' attributes
  4. Analyze script origins, SRI, and HTTPS usage
  5. Correlate findings with Mozilla Observatory results (if available)
----------------------------------------------------------------

Plugin: Related Sites Discovery (related_sites)
Type: passive
Priority: 45
Description: Discovers related subdomains and probes for live web services
Commands that would be executed:
  [1] subfinder -d example.com -o /path/to/related_sites_subfinder.json -json -silent
  [2] httpx -l /path/to/related_sites_targets.txt -json -o /path/to/related_sites_httpx.json ...
----------------------------------------------------------------
```

## Benefits

1. **Transparency**: Users can see exactly what commands will be executed
2. **Education**: Helps users understand what each plugin does
3. **Debugging**: Makes it easier to troubleshoot issues or understand plugin behavior
4. **Security Review**: Allows security teams to audit commands before execution
5. **Documentation**: Commands serve as examples for manual tool usage

## Usage

Simply add the `--dry-run` flag to any KAST command:

```bash
# Basic dry-run
kast -t example.com --dry-run

# Dry-run with specific plugins
kast -t example.com --dry-run --run-only testssl,whatweb

# Dry-run with verbose output
kast -t example.com --dry-run --verbose
```

## Design Decisions

### For External Tool Plugins
- Display the actual command string that would be executed
- Include all flags, options, and file paths
- Show exact output file locations

### For Internal Python Plugins
- List high-level operations rather than implementation details
- Describe the logical flow of operations
- Focus on what the plugin accomplishes, not how it's coded

### Formatting
- Clear visual separation between plugins
- Consistent numbering for multi-command plugins
- Indentation for readability
- Plugin metadata (type, priority, description) always shown

## Future Enhancements

Potential improvements for future versions:

1. **Estimated Runtime**: Show approximate time each plugin would take
2. **Resource Usage**: Display expected CPU/memory/network usage
3. **Dependency Checks**: Show which tools are installed vs missing
4. **Output File Sizes**: Estimate disk space needed
5. **Network Calls**: List all external URLs that would be contacted
6. **JSON Export**: Option to export dry-run info as JSON

## Related Files

- `kast/plugins/base.py` - Base plugin class with `get_dry_run_info()` method
- `kast/orchestrator.py` - Orchestrator logic for displaying dry-run information
- `kast/plugins/*.py` - All plugin implementations

## Testing

Tested with all plugins using various targets to ensure:
- Commands are properly formatted
- File paths are correct
- Operations lists are accurate
- Output is clear and readable

## See Also

- `README.md` - Main KAST documentation
- `genai-instructions.md` - Plugin development guide
- `kast/docs/README_CREATE_PLUGIN.md` - Plugin creation guide
