# ZAP Plugin Configuration Migration

## Overview

The ZAP plugin has been integrated with the KAST configuration management system using a **hybrid approach** that preserves its existing sophisticated multi-mode configuration while adding ConfigManager validation and CLI override capabilities.

**Migration Date:** December 23, 2025  
**Approach:** Option A - Hybrid (Preserve YAML, Add Schema Layer)  
**Status:** ✅ Complete

## Design Philosophy

ZAP is unique among KAST plugins due to its complexity:
- **4 execution modes** (auto, local, remote, cloud)
- **3 cloud providers** (AWS, Azure, GCP)
- **Hierarchical YAML configuration** with mode-specific sections
- **External dependencies** (Docker, Terraform, cloud CLIs)
- **Environment variable expansion** for credentials
- **Separate automation plan file**

Rather than forcing ZAP into the same flat configuration pattern as simpler plugins, we've implemented a **hybrid approach** that:

✅ Keeps the existing `zap_config.yaml` structure  
✅ Preserves all provider factory and provider classes unchanged  
✅ Maintains environment variable expansion  
✅ Adds ConfigManager schema registration for validation  
✅ Enables CLI overrides for strategic parameters only  
✅ Supports kast-web schema export  

## What Changed

### 1. Added Configuration Schema

The plugin now defines a comprehensive `config_schema` class variable that mirrors the YAML structure:

```python
config_schema = {
    "type": "object",
    "title": "OWASP ZAP Configuration",
    "properties": {
        "execution_mode": {
            "type": "string",
            "enum": ["auto", "local", "remote", "cloud"],
            "default": "auto"
        },
        "auto_discovery": { ... },
        "local": { ... },
        "remote": { ... },
        "cloud": { ... },
        "zap_config": { ... }
    }
}
```

This schema is automatically registered with ConfigManager when the plugin is instantiated.

### 2. Enhanced Configuration Loading

The `_load_config()` method now includes ConfigManager integration:

```python
def _load_config(self):
    # 1. Load from YAML file (unchanged)
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # 2. Expand environment variables (unchanged)
    config = self._expand_env_vars(config)
    
    # 3. Apply CLI overrides (NEW!)
    if self.config_manager:
        config = self._apply_cli_overrides(config)
    
    return config
```

### 3. New CLI Override Support

Added `_apply_cli_overrides()` method that applies ConfigManager overrides to strategic parameters:

**Overrideable Parameters:**
- `execution_mode` - Switch between auto/local/remote/cloud
- `local.docker_image` - Custom Docker image
- `local.api_port` - Change API port
- `local.auto_start` - Control automatic startup
- `local.cleanup_on_completion` - Keep/remove container
- `remote.api_url` - Remote ZAP URL
- `remote.timeout_seconds` - Connection timeout
- `remote.verify_ssl` - SSL verification
- `cloud.cloud_provider` - Switch cloud provider (aws/azure/gcp)
- `zap_config.timeout_minutes` - Scan timeout
- `zap_config.poll_interval_seconds` - Status polling interval
- `zap_config.report_name` - Custom report name

### 4. Added Nested Value Setter

New `_set_nested_value()` utility method to apply overrides to hierarchical config:

```python
def _set_nested_value(self, config, path, value):
    """
    Set value using dot notation: 'local.api_port' -> config['local']['api_port']
    """
    keys = path.split('.')
    current = config
    for key in keys[:-1]:
        if key not in current:
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value
```

## What Stayed Unchanged

These components required **zero modifications**:

✅ `zap_config.yaml` - Existing YAML structure preserved  
✅ `zap_automation_plan.yaml` - Separate file, not in schema  
✅ `zap_provider_factory.py` - Provider selection logic unchanged  
✅ `zap_providers.py` - All provider classes unchanged  
✅ `zap_api_client.py` - API client unchanged  
✅ Terraform configurations - AWS/Azure/GCP configs unchanged  
✅ Environment variable expansion - `${KAST_ZAP_URL}` still works  
✅ Legacy config support - `zap_cloud_config.yaml` still supported  

## Usage Examples

### Using Existing YAML Configuration

```bash
# Works exactly as before - no changes needed
python kast/main.py --target https://example.com --plugins zap
```

### Overriding Execution Mode

```bash
# Force local mode via CLI
python kast/main.py --target https://example.com --plugins zap \
  --set zap.execution_mode=local

# Force remote mode
python kast/main.py --target https://example.com --plugins zap \
  --set zap.execution_mode=remote \
  --set zap.remote.api_url=http://my-zap:8080
```

### Customizing Local Mode

```bash
# Use custom Docker image with different port
python kast/main.py --target https://example.com --plugins zap \
  --set zap.execution_mode=local \
  --set zap.local.docker_image=mycorp/custom-zap:v2 \
  --set zap.local.api_port=9090
```

### Extending Scan Timeout

```bash
# Increase timeout for long-running scan
python kast/main.py --target https://example.com --plugins zap \
  --set zap.zap_config.timeout_minutes=180
```

### Switching Cloud Providers

```bash
# Use Azure instead of AWS
python kast/main.py --target https://example.com --plugins zap \
  --set zap.execution_mode=cloud \
  --set zap.cloud.cloud_provider=azure
```

### Multiple Overrides

```bash
# Combine multiple CLI overrides
python kast/main.py --target https://example.com --plugins zap \
  --set zap.execution_mode=local \
  --set zap.local.api_port=9090 \
  --set zap.local.cleanup_on_completion=true \
  --set zap.zap_config.timeout_minutes=120
```

## Testing

Comprehensive test suite added in `kast/tests/test_zap_config.py`:

### Test Categories

1. **Schema Registration Tests** (6 tests)
   - Schema structure validation
   - Execution mode enum verification
   - Local/remote/cloud mode properties
   - Common ZAP settings validation

2. **Configuration Loading Tests** (2 tests)
   - YAML file loading
   - Hierarchical structure preservation

3. **CLI Override Tests** (7 tests)
   - Execution mode override
   - Local mode nested overrides
   - Remote mode overrides
   - Cloud provider switch
   - Common settings overrides
   - Multiple simultaneous overrides

4. **Environment Variable Tests** (2 tests)
   - Variable expansion (`${KAST_ZAP_URL}`)
   - Missing variable handling

5. **Backward Compatibility Tests** (1 test)
   - Legacy cloud config adaptation

6. **Utility Tests** (4 tests)
   - Nested value setter
   - Schema export
   - Plugin metadata
   - Availability detection

**Total:** 22 comprehensive tests

### Running Tests

```bash
# Run ZAP config tests
python -m pytest kast/tests/test_zap_config.py -v

# Run with coverage
python -m pytest kast/tests/test_zap_config.py --cov=kast.plugins.zap_plugin
```

## Configuration Schema

### Full Schema Structure

```yaml
zap:
  execution_mode: auto|local|remote|cloud
  
  auto_discovery:
    prefer_local: boolean
    check_env_vars: boolean
  
  local:
    docker_image: string
    auto_start: boolean
    api_port: integer (1024-65535)
    api_key: string
    container_name: string
    cleanup_on_completion: boolean
    use_automation_framework: boolean
  
  remote:
    api_url: string (supports ${KAST_ZAP_URL})
    api_key: string (supports ${KAST_ZAP_API_KEY})
    timeout_seconds: integer (5-300)
    verify_ssl: boolean
    use_automation_framework: boolean
  
  cloud:
    cloud_provider: aws|azure|gcp
    # Full cloud config remains in YAML file
  
  zap_config:
    timeout_minutes: integer (5-720)
    poll_interval_seconds: integer (5-300)
    report_name: string
    automation_plan: string (path)
```

### Schema Export

The schema can be exported for kast-web:

```bash
# Export all plugin schemas as JSON
python -c "
from kast.config_manager import ConfigManager
from argparse import Namespace
cm = ConfigManager(Namespace(verbose=False, set=[]))
print(cm.export_schema('json'))
" > schemas.json
```

## Benefits

### For Users

1. **Backward Compatible** - All existing workflows continue working
2. **Quick Adjustments** - CLI overrides for common parameters
3. **Validation** - Schema catches configuration errors early
4. **Documentation** - Schema serves as API documentation
5. **kast-web Ready** - UI can generate forms from schema

### For Development

1. **Low Risk** - Minimal changes to working complex system
2. **Testable** - Configuration layer tested independently
3. **Maintainable** - Clear separation of concerns
4. **Extensible** - Easy to add new overrideable parameters

### Trade-offs

❌ **Not as uniform as other plugins** - But reflects ZAP's inherent complexity  
❌ **YAML file still required** - Can't run purely from CLI (by design)  
✅ **More appropriate for complex multi-mode tool** - Hybrid approach fits ZAP's architecture  

## Comparison with Other Plugins

### Simple Plugins (testssl, whatweb, etc.)

- **Pattern:** Flat configuration, all params from CLI/config file
- **Config:** Simple list of command-line arguments
- **Override:** Every parameter overrideable

### ZAP Plugin (Hybrid Approach)

- **Pattern:** Hierarchical YAML + strategic CLI overrides
- **Config:** Multi-mode with nested sections
- **Override:** Only commonly-adjusted parameters

This difference is **intentional and appropriate** given ZAP's complexity.

## Future Enhancements

Potential improvements for future consideration:

1. **Mode-Specific Schemas** - Validate based on selected execution mode
2. **Provider-Specific Schemas** - Full AWS/Azure/GCP validation
3. **Automation Plan Integration** - Include automation plan in main schema
4. **Smart Defaults** - Auto-detect optimal execution mode based on environment
5. **Profile Support** - Named configuration profiles (dev, staging, prod)

## Migration Checklist

- [x] Add `config_schema` class variable to plugin
- [x] Reorder `__init__` to set name before `super().__init__()`
- [x] Enhance `_load_config()` with CLI override support
- [x] Add `_apply_cli_overrides()` method
- [x] Add `_set_nested_value()` utility method
- [x] Create comprehensive test suite (22 tests)
- [x] Verify schema registration with ConfigManager
- [x] Test CLI override functionality
- [x] Test environment variable expansion
- [x] Test backward compatibility with legacy config
- [x] Document migration approach and usage

## Related Documentation

- **ZAP_MULTI_MODE_GUIDE.md** - Multi-mode execution guide
- **ZAP_CLOUD_PLUGIN_GUIDE.md** - Cloud mode detailed guide
- **CONFIGURATION_SYSTEM.md** - Overall KAST config system
- **CONFIG_TESTING_GUIDE.md** - Testing best practices

## Conclusion

The ZAP plugin configuration migration successfully integrates with KAST's configuration management system while preserving its sophisticated multi-mode architecture. The hybrid approach provides the best of both worlds: validated configuration with CLI override flexibility, while maintaining the existing YAML-based hierarchical structure that ZAP's complexity requires.

All existing workflows remain functional, and users gain new capabilities for quick runtime adjustments without editing configuration files.
