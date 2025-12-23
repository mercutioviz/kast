# Subfinder Plugin Configuration Migration

## Overview

This document describes the migration of the Subfinder plugin to use the new configuration system, allowing users to customize subdomain discovery behavior through configuration files and CLI overrides.

**Date:** 2025-12-23  
**Plugin:** subfinder  
**Status:** ✅ Complete

## Changes Made

### 1. Configuration Schema

Added a comprehensive configuration schema to the Subfinder plugin:

```python
config_schema = {
    "type": "object",
    "title": "Subfinder Configuration",
    "description": "Subdomain discovery configuration",
    "properties": {
        "sources": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
            "description": "Specific sources to use (e.g., crtsh, github). Empty = use defaults"
        },
        "exclude_sources": {
            "type": "array",
            "items": {"type": "string"},
            "default": [],
            "description": "Sources to exclude from enumeration"
        },
        "use_all_sources": {
            "type": "boolean",
            "default": False,
            "description": "Use all available sources (slower but more comprehensive)"
        },
        "recursive_only": {
            "type": "boolean",
            "default": False,
            "description": "Use only sources that can handle subdomains recursively"
        },
        "rate_limit": {
            "type": "integer",
            "default": 0,
            "minimum": 0,
            "description": "Maximum HTTP requests per second (0 = no limit)"
        },
        "timeout": {
            "type": "integer",
            "default": 30,
            "minimum": 5,
            "maximum": 300,
            "description": "Seconds to wait before timing out"
        },
        "max_time": {
            "type": "integer",
            "default": 10,
            "minimum": 1,
            "maximum": 60,
            "description": "Minutes to wait for enumeration results"
        },
        "concurrent_goroutines": {
            "type": "integer",
            "default": 10,
            "minimum": 1,
            "maximum": 100,
            "description": "Number of concurrent goroutines for resolving"
        },
        "proxy": {
            "type": ["string", "null"],
            "default": None,
            "description": "HTTP proxy URL (e.g., http://proxy:8080)"
        },
        "collect_sources": {
            "type": "boolean",
            "default": True,
            "description": "Include source information in JSON output"
        },
        "active_only": {
            "type": "boolean",
            "default": False,
            "description": "Display only active subdomains (requires DNS resolution)"
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
    self.sources = self.get_config('sources', [])
    self.exclude_sources = self.get_config('exclude_sources', [])
    self.use_all_sources = self.get_config('use_all_sources', False)
    self.recursive_only = self.get_config('recursive_only', False)
    self.rate_limit = self.get_config('rate_limit', 0)
    self.timeout = self.get_config('timeout', 30)
    self.max_time = self.get_config('max_time', 10)
    self.concurrent_goroutines = self.get_config('concurrent_goroutines', 10)
    self.proxy = self.get_config('proxy', None)
    self.collect_sources = self.get_config('collect_sources', True)
    self.active_only = self.get_config('active_only', False)
```

### 4. Dynamic Command Building

Updated `run()` method to build commands dynamically based on configuration:

**Before:**
```python
cmd = [
    "subfinder",
    "-d", target,
    "-o", output_file,
    "-json"
]
```

**After:**
```python
cmd = ["subfinder", "-d", target]

# Add source control options
if self.sources:
    cmd.extend(["-s", ",".join(self.sources)])

if self.exclude_sources:
    cmd.extend(["-es", ",".join(self.exclude_sources)])

if self.use_all_sources:
    cmd.append("-all")

if self.recursive_only:
    cmd.append("-recursive")

# Add rate limiting and performance options
if self.rate_limit > 0:
    cmd.extend(["-rl", str(self.rate_limit)])

if self.concurrent_goroutines != 10:
    cmd.extend(["-t", str(self.concurrent_goroutines)])

# Add timeout options
if self.timeout != 30:
    cmd.extend(["-timeout", str(self.timeout)])

if self.max_time != 10:
    cmd.extend(["-max-time", str(self.max_time)])

# Add proxy if configured
if self.proxy:
    cmd.extend(["-proxy", self.proxy])

# Add output options
cmd.extend(["-o", output_file])

if self.collect_sources:
    cmd.append("-cs")

if self.active_only:
    cmd.append("-nW")

cmd.append("-oJ")
```

### 5. Dry Run Information

Updated `get_dry_run_info()` to:
- Build commands using current configuration
- Include an operations description reflecting config values
- Show exactly what will be executed

## Configuration Options

### sources (array of strings)
- **Default:** `[]` (empty = use default sources)
- **Description:** Specific sources to use for subdomain discovery
- **Examples:** `["crtsh", "github", "virustotal"]`
- **Command Flag:** `-s source1,source2,source3`
- **Available Sources:** crtsh, censys, certspotter, hackertarget, virustotal, shodan, github, securitytrails, and more

### exclude_sources (array of strings)
- **Default:** `[]`
- **Description:** Sources to exclude from enumeration
- **Examples:** `["alienvault", "shodan"]`
- **Command Flag:** `-es source1,source2`

### use_all_sources (boolean)
- **Default:** `false`
- **Description:** Use all available sources (slower but more comprehensive)
- **Command Flag:** `-all`
- **Note:** This will enumerate using all available sources, which takes longer

### recursive_only (boolean)
- **Default:** `false`
- **Description:** Use only sources that can handle subdomains recursively
- **Command Flag:** `-recursive`

### rate_limit (integer)
- **Default:** `0` (no limit)
- **Range:** 0-unlimited
- **Description:** Maximum HTTP requests per second (global rate limit)
- **Command Flag:** `-rl <number>`
- **Note:** Individual source rate limits are still applied

### timeout (integer)
- **Default:** `30`
- **Range:** 5-300 seconds
- **Description:** Seconds to wait before timing out
- **Command Flag:** `-timeout <seconds>`

### max_time (integer)
- **Default:** `10`
- **Range:** 1-60 minutes
- **Description:** Minutes to wait for enumeration results
- **Command Flag:** `-max-time <minutes>`

### concurrent_goroutines (integer)
- **Default:** `10`
- **Range:** 1-100
- **Description:** Number of concurrent goroutines for DNS resolution
- **Command Flag:** `-t <number>`
- **Note:** Only used with `-active` flag

### proxy (string)
- **Default:** `null`
- **Description:** HTTP proxy URL
- **Examples:** `http://proxy:8080`, `socks5://proxy:1080`
- **Command Flag:** `-proxy <url>`

### collect_sources (boolean)
- **Default:** `true`
- **Description:** Include source information in JSON output
- **Command Flag:** `-cs`
- **Note:** Adds `source` field to each subdomain result

### active_only (boolean)
- **Default:** `false`
- **Description:** Display only active subdomains (requires DNS resolution)
- **Command Flag:** `-nW`
- **Note:** Filters out subdomains that don't resolve

## Usage Examples

### Using Configuration File

Create or edit `kast/config/default_config.yaml`:

```yaml
plugins:
  subfinder:
    sources:
      - crtsh
      - github
      - virustotal
      - certspotter
    exclude_sources: []
    use_all_sources: false
    recursive_only: false
    rate_limit: 50
    timeout: 60
    max_time: 15
    concurrent_goroutines: 20
    proxy: null
    collect_sources: true
    active_only: false
```

### Using CLI Overrides

Override configuration values via command line:

```bash
# Use specific sources only
kast -t example.com --set subfinder.sources='["crtsh","github"]'

# Increase rate limit
kast -t example.com --set subfinder.rate_limit=100

# Use all available sources
kast -t example.com --set subfinder.use_all_sources=true

# Adjust timeouts for slow network
kast -t example.com \
  --set subfinder.timeout=120 \
  --set subfinder.max_time=20

# Use proxy
kast -t example.com --set subfinder.proxy=http://proxy:8080

# Show only active subdomains
kast -t example.com --set subfinder.active_only=true

# Multiple overrides
kast -t example.com \
  --set subfinder.sources='["crtsh","virustotal"]' \
  --set subfinder.rate_limit=50 \
  --set subfinder.timeout=90 \
  --set subfinder.collect_sources=true
```

### Testing Configuration

View what commands will be executed without running them:

```bash
kast -t example.com --dry-run
```

Output will show the configured subfinder command:
```
subfinder -d example.com -s crtsh,github -rl 50 -timeout 60 -o /path/to/output -cs -oJ
```

## Testing

Comprehensive test suite created in `kast/tests/test_subfinder_config.py`:

```bash
# Run all subfinder config tests
python -m unittest kast.tests.test_subfinder_config -v

# Output:
# test_cli_overrides ... ok
# test_command_building_with_active_only ... ok
# test_command_building_with_all_sources ... ok
# test_command_building_with_concurrent_goroutines ... ok
# test_command_building_with_custom_sources ... ok
# test_command_building_with_custom_timeouts ... ok
# test_command_building_with_defaults ... ok
# test_command_building_with_exclude_sources ... ok
# test_command_building_with_proxy ... ok
# test_command_building_with_rate_limit ... ok
# test_command_building_without_collect_sources ... ok
# test_config_from_file ... ok
# test_default_configuration ... ok
# test_operations_description ... ok
# test_operations_description_with_all_sources ... ok
# test_schema_export ... ok
# test_schema_registration ... ok
#
# Ran 17 tests in 0.020s
# OK
```

### Test Coverage

Tests verify:
1. ✅ Schema registration with ConfigManager
2. ✅ Default value loading from schema
3. ✅ Configuration loading from files
4. ✅ CLI override precedence
5. ✅ Command building with defaults
6. ✅ Command building with custom sources
7. ✅ Command building with excluded sources
8. ✅ Command building with all sources enabled
9. ✅ Rate limit configuration
10. ✅ Timeout configurations
11. ✅ Proxy configuration
12. ✅ Active-only filtering
13. ✅ Source collection toggling
14. ✅ Concurrent goroutines configuration
15. ✅ Operations description generation
16. ✅ Schema export functionality

## Migration Impact

### Backward Compatibility

- **Maintained:** Default values preserve existing behavior
- **No Breaking Changes:** Existing functionality unchanged
- **Enhancement Only:** New configuration options add flexibility

### Before vs After

**Before Migration:**
- Hard-coded default sources only
- No source selection or exclusion
- No rate limiting control
- Fixed 30s timeout
- No proxy support
- Always collected sources
- No active-only filtering

**After Migration:**
- Configurable source selection
- Source exclusion capability
- Rate limiting support
- Configurable timeouts (both connection and max time)
- Proxy support for enterprise environments
- Optional source collection
- Active-only subdomain filtering
- Performance tuning via concurrent goroutines

## Use Cases

### 1. Fast Enumeration (Speed-Optimized)
```yaml
subfinder:
  sources: ["crtsh", "certspotter"]  # Fast, reliable sources
  rate_limit: 100
  timeout: 15
  max_time: 5
  collect_sources: false
```

### 2. Comprehensive Discovery (Coverage-Optimized)
```yaml
subfinder:
  use_all_sources: true
  rate_limit: 20  # Slower to respect API limits
  timeout: 120
  max_time: 30
  collect_sources: true
```

### 3. Enterprise Environment (Proxy-Based)
```yaml
subfinder:
  sources: ["crtsh", "github", "virustotal"]
  proxy: "http://corporate-proxy:8080"
  rate_limit: 10
  timeout: 60
```

### 4. Active Subdomains Only (DNS-Filtered)
```yaml
subfinder:
  active_only: true
  concurrent_goroutines: 50  # More goroutines for DNS resolution
  timeout: 45
```

## Files Modified

1. **kast/plugins/subfinder_plugin.py**
   - Added config_schema with 11 configurable properties
   - Updated `__init__()` for proper initialization order
   - Implemented `_load_plugin_config()` method
   - Updated `run()` to use configuration
   - Updated `get_dry_run_info()` to reflect configuration

2. **kast/tests/test_subfinder_config.py** (new)
   - Comprehensive test suite for configuration system
   - 17 test cases covering all functionality

3. **kast/docs/SUBFINDER_CONFIG_MIGRATION.md** (this file)
   - Complete documentation of changes

## Related Documentation

- `CONFIGURATION_SYSTEM.md` - Overview of the configuration system
- `CONFIG_TESTING_GUIDE.md` - Testing guidelines
- `RELATED_SITES_PLUGIN.md` - Example of another configured plugin
- `TESTSSL_CONFIG_MIGRATION.md` - Similar migration pattern
- `WHATWEB_CONFIG_MIGRATION.md` - Similar migration pattern
- `WAFW00F_CONFIG_MIGRATION.md` - Similar migration pattern

## Plugins Migrated So Far

1. ✅ **related_sites** - Host-centric site discovery
2. ✅ **testssl** - SSL/TLS security testing
3. ✅ **whatweb** - Web technology detection
4. ✅ **wafw00f** - WAF detection
5. ✅ **subfinder** - Subdomain enumeration

## Next Steps

The following plugins are candidates for similar configuration migration:

1. **katana** - Web crawler with many options
2. **observatory** - Mozilla Observatory integration (API-based)
3. **ftap** - Fingerprinting tool
4. **script_detection** - JavaScript analysis

## Notes

- Subfinder's default sources provide good coverage without being too slow
- The `-cs` flag adds source information to each result, helpful for understanding data provenance
- Rate limiting is global; individual sources have their own built-in limits
- Active-only mode requires DNS resolution, which increases scan time
- Concurrent goroutines only affect DNS resolution (when using `-active`)
- Using all sources (`-all`) is comprehensive but significantly slower
- Recursive-only mode is useful when you need deep subdomain enumeration
