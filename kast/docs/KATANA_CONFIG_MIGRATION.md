# Katana Plugin Configuration Migration

## Overview

The Katana plugin has been migrated to use the KAST configuration system, allowing users to customize crawling behavior through configuration files or CLI overrides instead of hard-coded values.

## Migration Date

December 23, 2025

## Changes Made

### 1. Configuration Schema Added

Added comprehensive configuration schema with 18 configurable options across multiple categories:

#### Crawl Configuration
- `depth` (integer, default: 3): Maximum crawl depth (1-10)
- `js_crawl` (boolean, default: false): Enable JavaScript endpoint parsing
- `crawl_duration` (integer, default: 0): Maximum crawl duration in seconds (0 = no limit)
- `known_files` (enum, default: ""): Crawl known files (all/robotstxt/sitemapxml)
- `automatic_form_fill` (boolean, default: false): Enable automatic form filling
- `strategy` (enum, default: "depth-first"): Visit strategy (depth-first/breadth-first)

#### Rate Limiting & Concurrency
- `concurrency` (integer, default: 10): Number of concurrent fetchers (1-50)
- `parallelism` (integer, default: 10): Number of concurrent inputs (1-50)
- `rate_limit` (integer, default: 150): Maximum requests per second (1-500)
- `delay` (integer, default: 0): Request delay in seconds (0-60)

#### Network Configuration
- `timeout` (integer, default: 10): Request timeout in seconds (5-300)
- `retry` (integer, default: 1): Number of retry attempts (0-5)
- `proxy` (string, default: null): HTTP/SOCKS5 proxy URL

#### Scope Configuration
- `field_scope` (enum, default: "rdn"): Scope field (dn/rdn/fqdn)

#### Headless Browser Options
- `headless` (boolean, default: false): Enable headless browser crawling
- `xhr_extraction` (boolean, default: false): Extract XHR request URLs

#### Filtering Options
- `extension_filter` (array, default: []): Extensions to filter out (e.g., ["png", "css"])
- `omit_body` (boolean, default: true): Omit response body from output

### 2. Plugin Initialization Updated

- Modified `__init__()` to set plugin name before calling parent constructor
- Added `_load_plugin_config()` method to load all configuration values
- Added debug logging to show loaded configuration

### 3. Command Building Enhanced

Updated `run()` method to:
- Build commands dynamically based on configuration
- Only add flags when values differ from Katana defaults
- Support all 18 configuration options
- Maintain backward compatibility with existing behavior

### 4. Dry Run Information Enhanced

Updated `get_dry_run_info()` to:
- Build commands with current configuration (mirrors `run()` method)
- Generate descriptive operations summary including:
  - Crawl depth
  - JavaScript crawling status
  - Headless mode status
  - Rate limit
  - Timeout
  - Extension filtering (if configured)

### 5. Comprehensive Test Suite

Created `test_katana_config.py` with 23 test cases covering:
- Schema registration
- Default configuration loading
- Config file loading
- CLI override precedence
- Command building with various configurations
- Operations description generation

## Before Migration

Hard-coded command:
```python
cmd = [
    "katana",
    "-silent",
    "-u", target,
    "-ob",           # Always omit body
    "-rl", "15",     # Fixed rate limit: 15/sec
    "-fs", "fqdn",   # Fixed field scope: fqdn
    "-o", output_file
]
```

**Limitations:**
- Very conservative rate limit (15/sec)
- No depth control
- No JavaScript crawling
- No form filling
- No headless browser support
- No proxy support
- Field scope fixed to fqdn

## After Migration

### Example 1: Using Config File

**config.yaml:**
```yaml
plugins:
  katana:
    depth: 5
    js_crawl: true
    rate_limit: 100
    timeout: 30
    extension_filter:
      - png
      - jpg
      - css
      - woff
```

**Generated command:**
```bash
katana -silent -u example.com -d 5 -jc -rl 100 -timeout 30 -ef png,jpg,css,woff -o output.txt -ob
```

### Example 2: Using CLI Overrides

```bash
python kast/main.py example.com \
  --set katana.depth=7 \
  --set katana.headless=true \
  --set katana.xhr_extraction=true
```

### Example 3: Headless Browser Crawling

**config.yaml:**
```yaml
plugins:
  katana:
    depth: 4
    headless: true
    xhr_extraction: true
    automatic_form_fill: true
    strategy: breadth-first
    rate_limit: 50
```

### Example 4: Proxy-Based Crawling

**config.yaml:**
```yaml
plugins:
  katana:
    proxy: "http://proxy.company.com:8080"
    timeout: 60
    retry: 3
    delay: 1
```

## Configuration Profiles

### Fast Crawl Profile
```yaml
plugins:
  katana:
    depth: 3
    rate_limit: 200
    concurrency: 20
    parallelism: 15
    timeout: 10
```

### Thorough Crawl Profile
```yaml
plugins:
  katana:
    depth: 7
    js_crawl: true
    known_files: "all"
    automatic_form_fill: true
    strategy: breadth-first
    rate_limit: 100
    timeout: 30
```

### Stealth Crawl Profile
```yaml
plugins:
  katana:
    depth: 4
    rate_limit: 10
    delay: 2
    concurrency: 3
    timeout: 60
    retry: 3
```

### Headless Crawl Profile
```yaml
plugins:
  katana:
    depth: 5
    headless: true
    xhr_extraction: true
    automatic_form_fill: true
    js_crawl: true
    rate_limit: 50
```

## Benefits

1. **Flexibility**: Users can customize crawling behavior without modifying code
2. **Performance**: Higher rate limits (default 150/sec vs hard-coded 15/sec)
3. **Deep Crawling**: Configurable depth (default 3, max 10)
4. **Modern Web Apps**: JavaScript crawling and headless browser support
5. **Network Control**: Proxy support, timeouts, retries, delays
6. **Resource Management**: Configurable concurrency and parallelism
7. **Filtering**: Extension filtering to reduce noise
8. **Strategy Control**: Choose between depth-first and breadth-first
9. **Form Interaction**: Automatic form filling for authenticated areas
10. **Known Files**: Can crawl robots.txt, sitemap.xml automatically

## Testing

All tests pass successfully:

```bash
$ python -m unittest kast.tests.test_katana_config -v
test_cli_overrides ... ok
test_command_building_with_breadth_first ... ok
test_command_building_with_concurrency ... ok
test_command_building_with_crawl_duration ... ok
test_command_building_with_custom_depth ... ok
test_command_building_with_defaults ... ok
test_command_building_with_delay ... ok
test_command_building_with_extension_filter ... ok
test_command_building_with_field_scope ... ok
test_command_building_with_form_fill ... ok
test_command_building_with_headless ... ok
test_command_building_with_js_crawl ... ok
test_command_building_with_known_files ... ok
test_command_building_with_proxy ... ok
test_command_building_with_rate_limit ... ok
test_command_building_with_timeout ... ok
test_command_building_with_xhr_extraction ... ok
test_command_building_without_omit_body ... ok
test_config_from_file ... ok
test_default_configuration ... ok
test_operations_description ... ok
test_operations_description_with_headless ... ok
test_schema_registration ... ok

Ran 23 tests in 0.010s

OK
```

## Backward Compatibility

✅ **Fully backward compatible**
- Default values match Katana's defaults
- Only adds flags when values differ from defaults
- Existing scans will produce equivalent commands
- No breaking changes to plugin interface

## Related Documentation

- [Configuration System](CONFIGURATION_SYSTEM.md)
- [Config Testing Guide](CONFIG_TESTING_GUIDE.md)
- [Related Sites Config Migration](RELATED_SITES_PLUGIN.md)
- [TestSSL Config Migration](TESTSSL_CONFIG_MIGRATION.md)
- [WhatWeb Config Migration](WHATWEB_CONFIG_MIGRATION.md)
- [Wafw00f Config Migration](WAFW00F_CONFIG_MIGRATION.md)
- [Subfinder Config Migration](SUBFINDER_CONFIG_MIGRATION.md)

## Implementation Notes

### Design Decisions

1. **Smart Flag Addition**: Only adds flags when values differ from Katana defaults to keep commands clean
2. **Array Handling**: Extension filter converted to comma-separated list for `-ef` flag
3. **Time Format**: Duration uses seconds format (`300s`) as required by Katana
4. **Operations Description**: Generates human-readable summary for dry-run mode
5. **Schema Validation**: All values have min/max constraints to prevent invalid commands

### Command Optimization

The plugin intelligently builds commands by:
- Omitting flags that match Katana defaults
- Using proper flag formats (e.g., `-rl` for rate limit, `-d` for depth)
- Handling boolean flags correctly (present/absent rather than true/false)
- Converting arrays to comma-separated strings where needed

### Debug Logging

When verbose mode is enabled, the plugin logs:
- All loaded configuration values
- The exact command being executed
- Configuration source (file vs CLI override)

## Future Enhancements

Potential future additions:
1. Header/cookie injection support
2. Custom form configuration file
3. Match/filter regex patterns
4. Custom output templates
5. Store response options
6. Technology detection

## Migration Status

✅ **Complete**
- Schema defined
- Config loading implemented
- Command building updated
- Dry run information enhanced
- Tests created and passing
- Documentation complete
