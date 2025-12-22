# WhatWeb Plugin Configuration Migration

## Overview

This document describes the migration of the WhatWeb plugin to use the centralized ConfigManager system, enabling configuration via YAML files and CLI arguments.

**Date:** 2025-12-22  
**Plugin:** `whatweb_plugin.py`  
**Status:** ✅ Complete

## Changes Made

### 1. Configuration Schema Added

Added a `config_schema` class variable defining all configurable options:

```python
config_schema = {
    "type": "object",
    "title": "WhatWeb Configuration",
    "description": "Web technology detection configuration",
    "properties": {
        "aggression_level": {
            "type": "integer",
            "default": 3,
            "minimum": 1,
            "maximum": 4,
            "description": "Aggression level (1=stealthy, 3=aggressive, 4=heavy)"
        },
        "timeout": {
            "type": "integer",
            "default": 30,
            "minimum": 5,
            "maximum": 120,
            "description": "HTTP request timeout in seconds"
        },
        "user_agent": {
            "type": ["string", "null"],
            "default": None,
            "description": "Custom User-Agent string (null for default)"
        },
        "follow_redirects": {
            "type": "integer",
            "default": 2,
            "minimum": 0,
            "maximum": 10,
            "description": "Maximum redirect depth to follow"
        }
    }
}
```

### 2. Initialization Order Fixed

Updated `__init__` to set plugin attributes **before** calling `super().__init__()`:

```python
def __init__(self, cli_args, config_manager=None):
    # Set plugin name BEFORE super().__init__()
    self.name = "whatweb"
    self.display_name = "WhatWeb"
    self.description = "Identifies technologies used by a website."
    self.website_url = "https://github.com/urbanadventurer/whatweb"
    self.scan_type = "passive"
    self.output_type = "file"
    
    # Now call parent init (registers schema)
    super().__init__(cli_args, config_manager)
    
    self.command_executed = None
    
    # Load configuration values
    self._load_plugin_config()
```

### 3. Configuration Loading Method

Added `_load_plugin_config()` method to load config values:

```python
def _load_plugin_config(self):
    """Load configuration with defaults from schema."""
    self.aggression_level = self.get_config('aggression_level', 3)
    self.timeout = self.get_config('timeout', 30)
    self.user_agent = self.get_config('user_agent', None)
    self.follow_redirects = self.get_config('follow_redirects', 2)
    
    self.debug(f"WhatWeb config loaded: aggression={self.aggression_level}, "
              f"timeout={self.timeout}, "
              f"user_agent={'(custom)' if self.user_agent else '(default)'}, "
              f"follow_redirects={self.follow_redirects}")
```

### 4. Dynamic Command Building

Updated `run()` method to build commands based on config values:

**Before:**
```python
cmd = [
    "whatweb",
    "-a", "3",  # Hard-coded
    target,
    "--log-json", output_file
]
```

**After:**
```python
cmd = ["whatweb"]

# Add aggression level
cmd.extend(["-a", str(self.aggression_level)])

# Add timeout if configured
if self.timeout:
    cmd.extend(["--max-http-scan-time", str(self.timeout)])

# Add custom user-agent if configured
if self.user_agent:
    cmd.extend(["--user-agent", self.user_agent])

# Add redirect follow depth
if self.follow_redirects:
    cmd.extend(["--max-redirects", str(self.follow_redirects)])

# Add target and output
cmd.extend([target, "--log-json", output_file])
```

### 5. Dry Run Info Updated

Updated `get_dry_run_info()` to reflect current configuration:

```python
def get_dry_run_info(self, target, output_dir):
    """Build actual command with current configuration."""
    # ... builds command same as run() method ...
    
    operations_desc = (
        f"Technology detection (aggression level {self.aggression_level}, "
        f"timeout {self.timeout}s, max redirects {self.follow_redirects})"
    )
    
    return {
        "commands": [' '.join(cmd)],
        "description": self.description,
        "operations": operations_desc
    }
```

## Configuration Options

### aggression_level
- **Type:** Integer (1-4)
- **Default:** 3
- **Description:** Controls scan aggression (1=stealthy, 3=aggressive, 4=heavy)
- **WhatWeb flag:** `-a`

### timeout
- **Type:** Integer (5-120 seconds)
- **Default:** 30
- **Description:** HTTP request timeout per scan
- **WhatWeb flag:** `--max-http-scan-time`

### user_agent
- **Type:** String or null
- **Default:** null (WhatWeb default)
- **Description:** Custom User-Agent string for requests
- **WhatWeb flag:** `--user-agent`

### follow_redirects
- **Type:** Integer (0-10)
- **Default:** 2
- **Description:** Maximum redirect depth to follow
- **WhatWeb flag:** `--max-redirects`

## Usage Examples

### Via Configuration File

Create `kast_config.yaml`:

```yaml
plugins:
  whatweb:
    aggression_level: 1  # Stealthy scan
    timeout: 60
    user_agent: "Mozilla/5.0 (Custom Scanner)"
    follow_redirects: 5
```

Run scan:
```bash
kast --target https://example.com --config kast_config.yaml
```

### Via CLI Arguments

```bash
# Set single values
kast --target https://example.com --set whatweb.aggression_level=1

# Set multiple values
kast --target https://example.com \
  --set whatweb.aggression_level=1 \
  --set whatweb.timeout=60 \
  --set whatweb.user_agent="Custom Agent"
```

### View Current Configuration

```bash
# Show all plugin configs
kast --show-config

# Show only whatweb config
kast --show-config whatweb
```

## Testing

Comprehensive test suite added in `kast/tests/test_whatweb_config.py`:

```bash
# Run tests
python -m unittest kast.tests.test_whatweb_config -v
```

**Test Coverage:**
- ✅ Schema registration
- ✅ Default configuration loading
- ✅ Configuration from file
- ✅ CLI overrides
- ✅ Command building with defaults
- ✅ Command building with custom config
- ✅ Operations description
- ✅ Schema export

**Test Results:** All 8 tests passed ✅

## Benefits

1. **Flexibility:** Users can customize WhatWeb behavior per environment
2. **Consistency:** Same configuration system as other plugins
3. **GUI Integration:** Schema enables kast-web to auto-generate forms
4. **Documentation:** Schema serves as self-documenting configuration
5. **Validation:** Built-in type checking and value constraints

## Migration Pattern

This migration follows the established pattern from `related_sites_plugin` and `testssl_plugin`:

1. Add `config_schema` class variable
2. Fix initialization order (set `self.name` before `super().__init__()`)
3. Add `_load_plugin_config()` method
4. Replace hard-coded values with `self.get_config()`
5. Update command building to use config values
6. Update `get_dry_run_info()` to reflect config
7. Add comprehensive test suite

## Next Plugin Candidates

Based on this migration pattern, good candidates for next migration:

1. **wafw00f_plugin** - Simple plugin, likely has configurable options
2. **observatory_plugin** - May have API configuration needs
3. **katana_plugin** - Likely has crawl depth, rate limiting options
4. **subfinder_plugin** - Timeout, sources, rate limiting options

## Notes

- No backward compatibility needed (no existing CLI args for WhatWeb)
- All WhatWeb command-line flags now configurable
- Schema supports GUI form generation for kast-web
- Configuration priority: CLI overrides > Config file > Schema defaults
