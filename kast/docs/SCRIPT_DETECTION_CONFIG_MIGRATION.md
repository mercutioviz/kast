# Script Detection Plugin - Configuration Migration Guide

**Date:** 2024-12-23  
**Plugin:** `script_detection`  
**Status:** ✅ Complete

## Overview

The Script Detection plugin has been migrated to use the centralized configuration management system. This Python-based plugin analyzes external JavaScript files loaded by target websites, checking for security issues like missing Subresource Integrity (SRI) and insecure HTTP loading.

**Migration Benefits:**
- **Configurable HTTP requests** with custom timeouts, headers, and SSL settings
- **Flexible analysis limits** for large sites with many scripts
- **Better error handling** with configurable retry behavior
- **kast-web integration** for UI-based configuration

## Configuration Schema

The plugin supports the following configuration options:

```yaml
plugins:
  script_detection:
    # HTTP request timeout in seconds (5-120)
    request_timeout: 30
    
    # User-Agent string for HTTP requests
    user_agent: "KAST-Security-Scanner/1.0"
    
    # Verify SSL certificates (true/false)
    verify_ssl: true
    
    # Follow HTTP redirects (true/false)
    follow_redirects: true
    
    # Maximum number of redirects to follow (0-30)
    max_redirects: 10
    
    # Maximum scripts to analyze (null for unlimited)
    max_scripts_to_analyze: null
    
    # Custom HTTP headers
    custom_headers: {}
```

## Configuration Options

### `request_timeout` (integer)
- **Default:** 30 seconds
- **Range:** 5 - 120 seconds
- **Description:** HTTP request timeout when fetching target HTML. Increase for slow networks or rate-limited targets.

**Example:**
```yaml
plugins:
  script_detection:
    request_timeout: 60  # 1 minute timeout
```

### `user_agent` (string)
- **Default:** "KAST-Security-Scanner/1.0"
- **Description:** User-Agent string sent with HTTP requests. Customize to match legitimate browser behavior or identify your scanner.

**Example:**
```yaml
plugins:
  script_detection:
    user_agent: "Mozilla/5.0 (compatible; KASTBot/1.0)"
```

### `verify_ssl` (boolean)
- **Default:** true
- **Description:** Whether to verify SSL/TLS certificates. Set to false for testing environments with self-signed certificates.

**Example:**
```yaml
plugins:
  script_detection:
    verify_ssl: false  # For testing only!
```

### `follow_redirects` (boolean)
- **Default:** true
- **Description:** Whether to follow HTTP redirects when fetching the target. Disable to analyze the initial response only.

**Example:**
```yaml
plugins:
  script_detection:
    follow_redirects: true
    max_redirects: 5  # Limit redirect chains
```

### `max_redirects` (integer)
- **Default:** 10
- **Range:** 0 - 30
- **Description:** Maximum number of redirects to follow. Prevents infinite redirect loops.

**Example:**
```yaml
plugins:
  script_detection:
    follow_redirects: true
    max_redirects: 3  # Conservative limit
```

### `max_scripts_to_analyze` (integer or null)
- **Default:** null (unlimited)
- **Range:** 1+ when set
- **Description:** Limit the number of scripts to analyze. Useful for large sites with hundreds of scripts to keep scan times reasonable.

**Example:**
```yaml
plugins:
  script_detection:
    max_scripts_to_analyze: 50  # Analyze first 50 scripts only
```

### `custom_headers` (object)
- **Default:** {} (empty)
- **Description:** Additional HTTP headers to include in requests. Useful for authentication, custom tracking, or API requirements.

**Example:**
```yaml
plugins:
  script_detection:
    custom_headers:
      "Authorization": "Bearer token123"
      "X-Custom-Header": "value"
```

## Usage Examples

### Example 1: Basic Configuration

```yaml
# config/kast_config.yaml
plugins:
  script_detection:
    request_timeout: 30
    verify_ssl: true
```

Run with:
```bash
python kast/main.py --target https://example.com --config config/kast_config.yaml
```

### Example 2: Testing Environment (Self-Signed Certs)

For development/testing environments with self-signed certificates:

```yaml
plugins:
  script_detection:
    verify_ssl: false
    request_timeout: 60
```

### Example 3: Limited Analysis for Large Sites

For sites with many scripts, limit analysis to keep scan times manageable:

```yaml
plugins:
  script_detection:
    max_scripts_to_analyze: 100
    request_timeout: 45
```

### Example 4: Custom User Agent

Mimic a specific browser or identify your scanner:

```yaml
plugins:
  script_detection:
    user_agent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
```

### Example 5: Authenticated Scans

Include authentication headers for protected resources:

```yaml
plugins:
  script_detection:
    custom_headers:
      "Authorization": "Bearer eyJhbGc..."
      "X-API-Key": "secret-key"
```

### Example 6: CLI Override

Override config file values via command line:

```bash
python kast/main.py \
  --target https://example.com \
  --config config/kast_config.yaml \
  --set script_detection.request_timeout=90 \
  --set script_detection.verify_ssl=false
```

## What Script Detection Analyzes

The plugin examines external JavaScript files and checks for:

1. **Cross-Origin Scripts:** Scripts loaded from different origins than the target
2. **Subresource Integrity (SRI):** Whether scripts have integrity attributes
3. **HTTPS Usage:** Whether scripts are loaded over secure connections
4. **Script Origins:** Unique domains/CDNs serving scripts
5. **Security Posture:** Overall script loading security

**Issues Detected:**
- Scripts without SRI protection
- HTTP (insecure) script loading
- High count of external scripts
- Missing crossorigin attributes

## Migration Notes

### Before Migration

Previously, the Script Detection plugin had hardcoded values:
- Fixed 30-second timeout
- Standard Python requests User-Agent
- Always verified SSL certificates
- No way to customize headers
- No limit on scripts analyzed

### After Migration

The plugin now provides:
- **Configurable timeouts:** Match your network conditions
- **Custom User-Agent:** Better identify your scans
- **SSL flexibility:** Test environments with self-signed certs
- **Header customization:** Authentication and custom tracking
- **Analysis limits:** Control scan scope and duration
- **Redirect control:** Fine-tune redirect behavior

### Breaking Changes

**None.** The migration is fully backward compatible. All defaults match previous hardcoded behavior.

## Testing

A comprehensive test suite validates the configuration system:

```bash
# Run script_detection config tests
python -m unittest kast.tests.test_script_detection_config -v

# Run all config tests
python -m unittest kast.tests.test_*_config -v
```

### Test Coverage

The test suite verifies (16 tests total):
- ✅ Schema registration with ConfigManager
- ✅ Default value loading from schema
- ✅ Configuration loading from YAML files
- ✅ CLI override precedence
- ✅ Timeout configuration
- ✅ SSL verification toggle
- ✅ Redirect behavior configuration
- ✅ Max scripts limit configuration
- ✅ Custom headers configuration
- ✅ User agent customization
- ✅ Schema constraints validation
- ✅ Schema export functionality
- ✅ Plugin metadata verification
- ✅ Dependency configuration
- ✅ Configuration inheritance order
- ✅ Combined configuration options

## Schema Export

Export the complete configuration schema:

```bash
# Export as JSON
python kast/main.py --export-schema json > schema.json

# Export as YAML
python kast/main.py --export-schema yaml > schema.yaml
```

## Common Use Cases

### Use Case 1: Slow or Rate-Limited Targets

For targets with slow response times or rate limiting:

```yaml
plugins:
  script_detection:
    request_timeout: 90
    follow_redirects: true
    max_redirects: 5
```

### Use Case 2: Development/Staging Environments

Testing against environments with self-signed certificates:

```yaml
plugins:
  script_detection:
    verify_ssl: false
    user_agent: "KAST-Dev-Scanner/1.0"
```

### Use Case 3: Large E-Commerce Sites

Sites with many analytics, advertising, and tracking scripts:

```yaml
plugins:
  script_detection:
    max_scripts_to_analyze: 75
    request_timeout: 45
```

### Use Case 4: API-Authenticated Targets

Scanning protected resources requiring authentication:

```yaml
plugins:
  script_detection:
    custom_headers:
      "Authorization": "Bearer ${AUTH_TOKEN}"
      "X-Tenant-ID": "12345"
```

### Use Case 5: Strict Redirect Control

Analyzing redirect chains carefully:

```yaml
plugins:
  script_detection:
    follow_redirects: true
    max_redirects: 3  # Stop after 3 hops
```

## Configuration Best Practices

1. **Timeout Settings:**
   - Start with default 30s for most targets
   - Increase to 60-90s for slow networks
   - Use 10-15s for fast, reliable targets

2. **SSL Verification:**
   - Always use `verify_ssl: true` for production scans
   - Only disable for testing/development environments
   - Document when SSL verification is disabled

3. **Script Limits:**
   - Use `max_scripts_to_analyze` for sites with 100+ scripts
   - Balance between thorough analysis and scan time
   - Consider 50-100 as reasonable limits for large sites

4. **Custom Headers:**
   - Minimize custom headers to reduce fingerprinting
   - Use environment variables for sensitive values
   - Document all custom headers used

5. **User Agent:**
   - Use descriptive, identifiable user agents
   - Include contact information for responsible disclosure
   - Consider rotating for large-scale scans

## Troubleshooting

### Issue: Requests timing out
**Solution:** Increase `request_timeout`:
```yaml
script_detection:
  request_timeout: 90
```

### Issue: SSL certificate errors
**Solution:** For testing only, disable SSL verification:
```yaml
script_detection:
  verify_ssl: false  # WARNING: Testing only!
```

### Issue: Scan takes too long on large sites
**Solution:** Limit scripts analyzed:
```yaml
script_detection:
  max_scripts_to_analyze: 50
```

### Issue: Redirect loops or chains
**Solution:** Reduce max_redirects:
```yaml
script_detection:
  follow_redirects: true
  max_redirects: 3
```

### Issue: Need to authenticate
**Solution:** Add authorization headers:
```yaml
script_detection:
  custom_headers:
    "Authorization": "Bearer token"
```

## Integration with Mozilla Observatory

Script Detection has a dependency on the Mozilla Observatory plugin and correlates findings:

```yaml
plugins:
  mozilla_observatory:
    timeout: 300
  
  script_detection:
    request_timeout: 30
```

The plugin will:
1. Wait for Observatory to complete
2. Analyze external JavaScript files
3. Correlate findings with Observatory CSP/SRI issues
4. Provide unified security assessment

## Related Documentation

- [Configuration System Overview](CONFIGURATION_SYSTEM.md)
- [Config Testing Guide](CONFIG_TESTING_GUIDE.md)
- [Observatory Config Migration](OBSERVATORY_CONFIG_MIGRATION.md)
- [MDN Script Element Reference](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/script)

## Implementation Details

### Plugin Changes

1. **Added config_schema:** Defines 7 configurable parameters with validation
2. **Modified __init__:** Sets plugin name before calling `super()` for proper schema registration
3. **Added _load_plugin_config():** Centralized configuration loading
4. **Enhanced _fetch_html():** Uses configured timeout, SSL settings, headers, and redirect behavior
5. **Enhanced _analyze_scripts():** Respects `max_scripts_to_analyze` limit

### Files Modified

- `kast/plugins/script_detection_plugin.py` - Plugin implementation
- `kast/tests/test_script_detection_config.py` - Configuration tests (new)
- `kast/docs/SCRIPT_DETECTION_CONFIG_MIGRATION.md` - This document (new)

## Security Considerations

1. **SSL Verification:** Only disable for trusted testing environments
2. **Custom Headers:** Avoid exposing sensitive credentials in config files
3. **User Agent:** Use identifiable strings for responsible disclosure
4. **Authentication:** Use environment variables for tokens/keys
5. **Script Limits:** Balance security coverage with scan efficiency

## Future Enhancements

Potential future configuration options:

- **Concurrent fetching:** Parallel script analysis
- **Content hashing:** Verify script integrity beyond SRI
- **Caching:** Cache analyzed scripts across scans
- **Allowlists:** Skip analysis for known-good scripts
- **Deep analysis:** Parse JavaScript for additional security checks

## Support

For issues or questions about Script Detection plugin configuration:
1. Check this documentation
2. Review test cases in `test_script_detection_config.py`
3. Consult the main [Configuration System](CONFIGURATION_SYSTEM.md) documentation
4. File an issue with the KAST project

---

**Migration Completed:** 2024-12-23  
**Validated By:** Configuration test suite (16/16 tests passed)  
**Status:** Production ready
