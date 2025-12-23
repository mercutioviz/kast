# Wafw00f Plugin Configuration Migration

## Overview

This document describes the migration of the Wafw00f plugin to use the new configuration system, allowing users to customize WAF detection behavior through configuration files and CLI overrides.

**Date:** 2025-12-22  
**Plugin:** wafw00f  
**Status:** ✅ Complete

## Changes Made

### 1. Configuration Schema

Added a comprehensive configuration schema to the Wafw00f plugin:

```python
config_schema = {
    "type": "object",
    "title": "Wafw00f Configuration",
    "description": "Web Application Firewall detection configuration",
    "properties": {
        "find_all": {
            "type": "boolean",
            "default": True,
            "description": "Find all WAFs matching signatures (use -a flag)"
        },
        "verbosity": {
            "type": "integer",
            "default": 3,
            "minimum": 0,
            "maximum": 3,
            "description": "Verbosity level (0=quiet, 3=maximum)"
        },
        "follow_redirects": {
            "type": "boolean",
            "default": True,
            "description": "Follow HTTP redirections"
        },
        "timeout": {
            "type": "integer",
            "default": 30,
            "minimum": 5,
            "maximum": 120,
            "description": "Request timeout in seconds"
        },
        "proxy": {
            "type": ["string", "null"],
            "default": None,
            "description": "HTTP/SOCKS proxy URL (e.g., http://hostname:8080)"
        },
        "test_specific_waf": {
            "type": ["string", "null"],
            "default": None,
            "description": "Test for specific WAF only (e.g., 'Cloudflare')"
        }
    }
}
```

### 2. Plugin Initialization

Updated the `__init__()` method to:
- Set plugin name **before** calling `super().__init__()` for proper schema registration
- Load configuration values from ConfigManager
- Add debug logging for loaded configuration

### 3. Configuration Loading

Implemented `_load_plugin_config()` method:

```python
def _load_plugin_config(self):
    """Load configuration with defaults from schema."""
    self.find_all = self.get_config('find_all', True)
    self.verbosity = self.get_config('verbosity', 3)
    self.follow_redirects = self.get_config('follow_redirects', True)
    self.timeout = self.get_config('timeout', 30)
    self.proxy = self.get_config('proxy', None)
    self.test_specific_waf = self.get_config('test_specific_waf', None)
```

### 4. Dynamic Command Building

Updated `run()` method to build commands dynamically based on configuration:

**Before:**
```python
cmd = [
    "wafw00f",
    target,
    "-a",      # Hard-coded
    "-vvv",    # Hard-coded
    "-f", "json",
    "-o", output_file
]
```

**After:**
```python
cmd = ["wafw00f", target]

if self.find_all:
    cmd.append("-a")

if self.verbosity > 0:
    cmd.append("-" + "v" * self.verbosity)

if not self.follow_redirects:
    cmd.append("-r")

if self.timeout:
    cmd.extend(["-T", str(self.timeout)])

if self.proxy:
    cmd.extend(["-p", self.proxy])

if self.test_specific_waf:
    cmd.extend(["-t", self.test_specific_waf])

cmd.extend(["-f", "json", "-o", output_file])
```

### 5. TLS Retry Logic

Updated the TLS error retry logic to use the same configuration when retrying with HTTP:

```python
# Rebuild command with HTTP target using same config
http_cmd = ["wafw00f", http_target]

if self.find_all:
    http_cmd.append("-a")

if self.verbosity > 0:
    http_cmd.append("-" + "v" * self.verbosity)

# ... apply all other config options
```

### 6. Dry Run Information

Updated `get_dry_run_info()` to:
- Build commands using current configuration
- Include an operations description reflecting config values
- Show exactly what will be executed

## Configuration Options

### find_all (boolean)
- **Default:** `true`
- **Description:** Find all WAFs that match signatures (don't stop at first match)
- **Command Flag:** `-a`

### verbosity (integer)
- **Default:** `3`
- **Range:** 0-3
- **Description:** Control output verbosity
  - 0: Quiet (no flag)
  - 1: Basic (`-v`)
  - 2: More verbose (`-vv`)
  - 3: Maximum verbosity (`-vvv`)

### follow_redirects (boolean)
- **Default:** `true`
- **Description:** Follow HTTP redirections
- **Command Flag:** `-r` (when disabled)

### timeout (integer)
- **Default:** `30`
- **Range:** 5-120 seconds
- **Description:** Request timeout in seconds
- **Command Flag:** `-T <seconds>`

### proxy (string)
- **Default:** `null`
- **Description:** HTTP/SOCKS proxy URL
- **Examples:**
  - `http://hostname:8080`
  - `socks5://hostname:1080`
  - `http://user:pass@hostname:8080`
- **Command Flag:** `-p <proxy_url>`

### test_specific_waf (string)
- **Default:** `null`
- **Description:** Test for a specific WAF only instead of all signatures
- **Examples:** `Cloudflare`, `ModSecurity`, `Akamai`
- **Command Flag:** `-t <waf_name>`

## Usage Examples

### Using Configuration File

Create or edit `kast/config/default_config.yaml`:

```yaml
plugins:
  wafw00f:
    find_all: true
    verbosity: 2
    follow_redirects: true
    timeout: 45
    proxy: "http://proxy.company.com:8080"
    test_specific_waf: null
```

### Using CLI Overrides

Override configuration values via command line:

```bash
# Increase timeout
kast -t example.com --set wafw00f.timeout=60

# Test for specific WAF only
kast -t example.com --set wafw00f.test_specific_waf=Cloudflare

# Reduce verbosity
kast -t example.com --set wafw00f.verbosity=1

# Use proxy
kast -t example.com --set wafw00f.proxy=http://proxy:8080

# Multiple overrides
kast -t example.com \
  --set wafw00f.timeout=90 \
  --set wafw00f.find_all=false \
  --set wafw00f.verbosity=2
```

### Testing Configuration

View what commands will be executed without running them:

```bash
kast -t example.com --dry-run
```

Output will show the configured wafw00f command:
```
wafw00f https://example.com -a -vvv -T 30 -f json -o /path/to/wafw00f.json
```

## Testing

Comprehensive test suite created in `kast/tests/test_wafw00f_config.py`:

```bash
# Run all wafw00f config tests
python -m unittest kast.tests.test_wafw00f_config -v

# Output:
# test_cli_overrides ... ok
# test_command_building_with_custom_config ... ok
# test_command_building_with_defaults ... ok
# test_config_from_file ... ok
# test_default_configuration ... ok
# test_operations_description ... ok
# test_schema_export ... ok
# test_schema_registration ... ok
# test_verbosity_levels ... ok
#
# Ran 9 tests in 0.002s
# OK
```

### Test Coverage

Tests verify:
1. ✅ Schema registration with ConfigManager
2. ✅ Default value loading from schema
3. ✅ Configuration loading from files
4. ✅ CLI override precedence
5. ✅ Command building with defaults
6. ✅ Command building with custom config
7. ✅ Verbosity level flags (0-3)
8. ✅ Operations description generation
9. ✅ Schema export functionality

## Migration Impact

### Backward Compatibility

- **Maintained:** Default values match previous hard-coded behavior
- **No Breaking Changes:** Existing functionality preserved
- **Enhancement Only:** New configuration options add flexibility

### Before vs After

**Before Migration:**
- Hard-coded `-a` flag (always test all WAFs)
- Hard-coded `-vvv` (maximum verbosity)
- No timeout configuration
- No proxy support
- No way to test specific WAFs

**After Migration:**
- Configurable find_all behavior
- Adjustable verbosity (0-3)
- Configurable timeout (5-120s)
- Proxy support for enterprise environments
- Ability to test specific WAFs
- Configuration via files and CLI

## Files Modified

1. **kast/plugins/wafw00f_plugin.py**
   - Added config_schema
   - Updated `__init__()` for proper initialization order
   - Implemented `_load_plugin_config()` method
   - Updated `run()` to use configuration
   - Updated TLS retry logic to use configuration
   - Updated `get_dry_run_info()` to reflect configuration

2. **kast/tests/test_wafw00f_config.py** (new)
   - Comprehensive test suite for configuration system
   - 9 test cases covering all functionality

3. **kast/docs/WAFW00F_CONFIG_MIGRATION.md** (this file)
   - Complete documentation of changes

## Related Documentation

- `CONFIGURATION_SYSTEM.md` - Overview of the configuration system
- `CONFIG_TESTING_GUIDE.md` - Testing guidelines
- `RELATED_SITES_PLUGIN.md` - Example of another configured plugin
- `TESTSSL_CONFIG_MIGRATION.md` - Similar migration pattern

## Next Steps

The following plugins are candidates for similar configuration migration:

1. **subfinder** - Subdomain enumeration with various sources
2. **katana** - Web crawler with many options
3. **observatory** - Mozilla Observatory integration
4. **ftap** - Fingerprinting tool

## Notes

- Wafw00f timeout option (`-T`) uses capital T, not lowercase
- Verbosity levels are cumulative (1=`-v`, 2=`-vv`, 3=`-vvv`)
- The `-r` flag is only added when `follow_redirects` is `false`
- Proxy configuration supports HTTP, HTTPS, and SOCKS5 protocols
- Test specific WAF feature is useful for focused testing
