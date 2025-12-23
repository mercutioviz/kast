# Mozilla Observatory Plugin - Configuration Migration Guide

**Date:** 2024-12-23  
**Plugin:** `mozilla_observatory`  
**Status:** ✅ Complete

## Overview

The Mozilla Observatory plugin has been migrated to use the centralized configuration management system. This enables:

- **Unified configuration** via YAML files and CLI overrides
- **Schema validation** with type checking and constraints
- **kast-web integration** for UI-based configuration
- **Better defaults** and documentation for all options

## Configuration Schema

The plugin supports the following configuration options:

```yaml
plugins:
  mozilla_observatory:
    # Command execution timeout in seconds (30-1800)
    timeout: 300
    
    # Number of retry attempts on failure (1-5)
    retry_attempts: 1
    
    # Additional command line arguments
    additional_args: []
    
    # Output format (currently only JSON supported)
    format: "json"
```

## Configuration Options

### `timeout` (integer)
- **Default:** 300 seconds (5 minutes)
- **Range:** 30 - 1800 seconds
- **Description:** Maximum time to wait for the Observatory scan to complete. Increase for complex targets or slower networks.

**Example:**
```yaml
plugins:
  mozilla_observatory:
    timeout: 600  # 10 minutes
```

### `retry_attempts` (integer)
- **Default:** 1
- **Range:** 1 - 5
- **Description:** Number of times to retry the scan if it fails. Useful for handling transient network issues or service availability problems.

**Example:**
```yaml
plugins:
  mozilla_observatory:
    retry_attempts: 3  # Retry up to 3 times
```

### `additional_args` (array of strings)
- **Default:** [] (empty)
- **Description:** Additional command-line arguments to pass to `mdn-http-observatory-scan`. Use this for advanced tool options not directly exposed by the plugin.

**Example:**
```yaml
plugins:
  mozilla_observatory:
    additional_args:
      - "--verbose"
      - "--debug"
```

### `format` (string enum)
- **Default:** "json"
- **Allowed Values:** ["json"]
- **Description:** Output format for scan results. Currently, only JSON format is supported.

## Usage Examples

### Example 1: Basic Configuration

```yaml
# config/kast_config.yaml
plugins:
  mozilla_observatory:
    timeout: 300
    retry_attempts: 1
```

Run with:
```bash
python kast/main.py --target https://example.com --config config/kast_config.yaml
```

### Example 2: Extended Timeout with Retries

For targets that require longer scan times:

```yaml
plugins:
  mozilla_observatory:
    timeout: 900       # 15 minutes
    retry_attempts: 3   # Try 3 times
```

### Example 3: CLI Override

Override config file values via command line:

```bash
python kast/main.py \
  --target https://example.com \
  --config config/kast_config.yaml \
  --set mozilla_observatory.timeout=600 \
  --set mozilla_observatory.retry_attempts=2
```

### Example 4: Additional Arguments

Pass custom arguments to the underlying tool:

```yaml
plugins:
  mozilla_observatory:
    timeout: 600
    additional_args:
      - "--verbose"
```

## Migration Notes

### Before Migration

Previously, the Observatory plugin had no configurable options. All executions used hardcoded values:
- Fixed 300-second implicit timeout from subprocess
- No retry logic
- No way to pass custom arguments

### After Migration

The plugin now provides:
- **Configurable timeout:** Control scan duration limits
- **Retry logic:** Automatic retries on failure
- **Flexible arguments:** Pass any tool-specific options
- **Better error handling:** More informative failure messages

### Breaking Changes

**None.** The migration is fully backward compatible. Existing workflows continue to work with default values.

## Testing

A comprehensive test suite validates the configuration system:

```bash
# Run Observatory config tests
python -m pytest kast/tests/test_observatory_config.py -v

# Run all config tests
python -m pytest kast/tests/test_*_config.py -v
```

### Test Coverage

The test suite verifies:
- ✅ Schema registration with ConfigManager
- ✅ Default value loading from schema
- ✅ Configuration loading from YAML files
- ✅ CLI override precedence
- ✅ Timeout configuration
- ✅ Retry attempts configuration
- ✅ Additional arguments handling
- ✅ Schema constraint validation
- ✅ Schema export functionality
- ✅ Configuration inheritance order

## Schema Export

Export the complete configuration schema for documentation or UI generation:

```bash
# Export as JSON
python kast/main.py --export-schema json > schema.json

# Export as YAML
python kast/main.py --export-schema yaml > schema.yaml
```

## Common Use Cases

### Use Case 1: Slow or Rate-Limited Targets

For targets behind rate limiting or with slow response times:

```yaml
plugins:
  mozilla_observatory:
    timeout: 1200      # 20 minutes
    retry_attempts: 2   # Retry once
```

### Use Case 2: Unreliable Networks

When scanning over unreliable network connections:

```yaml
plugins:
  mozilla_observatory:
    timeout: 600
    retry_attempts: 5   # Maximum retries
```

### Use Case 3: Quick Scans

For fast, fail-fast scanning:

```yaml
plugins:
  mozilla_observatory:
    timeout: 60        # 1 minute only
    retry_attempts: 1   # No retries
```

## Configuration Best Practices

1. **Timeout Settings:**
   - Start with default 300s for most targets
   - Increase to 600-900s for complex sites
   - Use 60-120s for quick validation scans

2. **Retry Logic:**
   - Use 1 retry (default) for stable environments
   - Use 2-3 retries for unreliable networks
   - Use 5 retries only for critical scans

3. **Additional Arguments:**
   - Keep additional_args minimal
   - Document any non-standard arguments used
   - Test additional arguments before production use

## Troubleshooting

### Issue: Scans timing out
**Solution:** Increase `timeout` value:
```yaml
mozilla_observatory:
  timeout: 900  # Increase from default 300
```

### Issue: Intermittent failures
**Solution:** Increase `retry_attempts`:
```yaml
mozilla_observatory:
  retry_attempts: 3  # Retry up to 3 times
```

### Issue: Need verbose output
**Solution:** Add verbose flag:
```yaml
mozilla_observatory:
  additional_args: ["--verbose"]
```

## Related Documentation

- [Configuration System Overview](CONFIGURATION_SYSTEM.md)
- [Config Testing Guide](CONFIG_TESTING_GUIDE.md)
- [Mozilla Observatory Official Docs](https://developer.mozilla.org/en-US/blog/mdn-http-observatory-launch/)

## Implementation Details

### Plugin Changes

1. **Added config_schema:** Defines all configurable parameters with validation
2. **Modified __init__:** Now loads configuration via ConfigManager
3. **Added _load_plugin_config():** Centralized config loading method
4. **Enhanced run():** Implements timeout and retry logic using config values
5. **Updated command building:** Includes additional_args from configuration

### Files Modified

- `kast/plugins/observatory_plugin.py` - Plugin implementation
- `kast/tests/test_observatory_config.py` - Configuration tests (new)
- `kast/docs/OBSERVATORY_CONFIG_MIGRATION.md` - This document (new)

## Future Enhancements

Potential future configuration options:

- **Custom API endpoints:** For private Observatory instances
- **Scan profiles:** Predefined configurations for common scenarios
- **Result caching:** Cache scan results for repeated targets
- **Rate limiting:** Built-in rate limit controls

## Support

For issues or questions about Observatory plugin configuration:
1. Check this documentation
2. Review test cases in `test_observatory_config.py`
3. Consult the main [Configuration System](CONFIGURATION_SYSTEM.md) documentation
4. File an issue with the KAST project

---

**Migration Completed:** 2024-12-23  
**Validated By:** Configuration test suite  
**Status:** Production ready
