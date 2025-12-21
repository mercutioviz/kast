# Configuration Testing Guide

## Overview

This guide explains the comprehensive testing framework for KAST's configuration system. As plugins are migrated to use the new configuration architecture, this testing framework ensures that:

1. Configuration schemas are well-formed and complete
2. Default values work correctly
3. Config file overrides function as expected
4. CLI overrides take proper precedence
5. Configuration values actually affect plugin behavior
6. Legacy CLI arguments remain backward compatible

## Testing Framework Components

### 1. Test Helpers (`kast/tests/helpers/config_test_helpers.py`)

A suite of reusable helper functions that simplify config testing:

- **`create_test_config_file()`** - Create temporary YAML config files for testing
- **`assert_config_values()`** - Assert plugin loaded expected config values
- **`verify_schema_completeness()`** - Validate schema has all required fields
- **`verify_type_match()`** - Verify values match JSON Schema types
- **`get_schema_defaults()`** - Extract default values from schema
- **`validate_config_against_schema()`** - Validate config values against schema

### 2. Per-Plugin Test Suites

Each migrated plugin has a dedicated test file:
- `kast/tests/test_testssl_config.py` - TestSSL plugin tests
- `kast/tests/test_related_sites_config.py` - Related Sites plugin tests

## Test Categories

Each plugin test suite includes these standard test categories:

### A. Schema Validation Tests

**Purpose:** Verify the plugin's `config_schema` is properly defined

```python
def test_schema_defined_and_valid(self):
    """Verify plugin has valid config_schema with required fields"""
    plugin = MyPlugin(self.mock_args)
    
    # Verify schema completeness
    errors = verify_schema_completeness(plugin.config_schema, "myplugin")
    self.assertEqual(errors, [], f"Schema validation errors: {errors}")
```

**Checks:**
- Schema exists and is a dictionary
- Has `type: "object"` at top level
- Contains `properties`, `title`, `description`
- Every property has `default`, `type`, `description`
- Numeric properties have `minimum`/`maximum` constraints
- Array properties have `items` definition

### B. Default Values Tests

**Purpose:** Verify schema defaults are loaded when no config provided

```python
def test_default_values_loaded(self):
    """Verify defaults from schema are loaded when no config provided"""
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    expected_defaults = {
        "timeout": 300,
        "enabled": True,
        # ... all config properties
    }
    
    assert_config_values(plugin, expected_defaults)
```

### C. Config File Override Tests

**Purpose:** Verify YAML config file values override defaults

```python
def test_config_file_overrides_defaults(self):
    """Verify YAML config file values override schema defaults"""
    config_path, temp_dir = create_test_config_file({
        "myplugin": {
            "timeout": 600,  # Override default
            "enabled": False
        }
    })
    self.temp_dirs.append(temp_dir)
    
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    config_manager.load(config_path)
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    # Verify overridden values
    self.assertEqual(plugin.timeout, 600)
    self.assertEqual(plugin.enabled, False)
```

### D. CLI Override Tests

**Purpose:** Verify `--set` CLI arguments override config file

```python
def test_cli_overrides_config_file(self):
    """Verify --set CLI overrides take precedence over config file"""
    config_path, temp_dir = create_test_config_file({
        "myplugin": {"timeout": 600}
    })
    self.temp_dirs.append(temp_dir)
    
    # CLI override should win
    self.mock_args.config = config_path
    self.mock_args.set = ["myplugin.timeout=900"]
    
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    config_manager.load(config_path)
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    # CLI override wins
    self.assertEqual(plugin.timeout, 900)
```

### E. Type Validation Tests

**Purpose:** Verify config values have correct Python types

```python
def test_type_validation(self):
    """Verify config values have correct types"""
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    # Verify each property type
    schema_props = MyPlugin.config_schema["properties"]
    for key, prop in schema_props.items():
        plugin_value = getattr(plugin, key, None)
        expected_type = prop["type"]
        
        is_valid, error = verify_type_match(plugin_value, expected_type)
        self.assertTrue(is_valid, f"{key}: Type mismatch - {error}")
```

### F. Behavioral Tests

**Purpose:** Verify config values actually affect plugin behavior

```python
def test_config_values_used_in_execution(self):
    """Verify config values actually affect command generation"""
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    
    # Set custom config
    self.mock_args.set = ["myplugin.timeout=250"]
    config_manager.load()
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    # Verify the config value is used
    # (e.g., check command string, verify subprocess.run timeout parameter, etc.)
```

### G. Constraint Validation Tests

**Purpose:** Verify min/max constraints are properly enforced

```python
def test_numeric_constraints_validation(self):
    """Verify min/max constraints are properly defined"""
    schema_props = MyPlugin.config_schema["properties"]
    
    # Check each numeric property
    timeout_prop = schema_props["timeout"]
    self.assertEqual(timeout_prop["minimum"], 60)
    self.assertEqual(timeout_prop["maximum"], 1800)
    
    # Verify default is within range
    default = timeout_prop["default"]
    self.assertGreaterEqual(default, timeout_prop["minimum"])
    self.assertLessEqual(default, timeout_prop["maximum"])
```

### H. Legacy CLI Argument Tests

**Purpose:** Verify backward compatibility with old CLI args (if applicable)

```python
def test_backward_compatibility_legacy_cli_arg(self):
    """Verify legacy --old-arg CLI argument still works"""
    # Set legacy arg
    self.mock_args.old_arg = 35
    
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    # Verify legacy arg was used
    self.assertEqual(plugin.new_config_name, 35)
```

### I. Special Type Tests

For plugins with arrays, nullable fields, or other special types:

```python
def test_array_type_handling(self):
    """Verify array type is handled correctly"""
    config_path, temp_dir = create_test_config_file({
        "myplugin": {"ports": [8080, 8443, 9000]}
    })
    self.temp_dirs.append(temp_dir)
    
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    config_manager.load(config_path)
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    # Verify array
    self.assertIsInstance(plugin.ports, list)
    self.assertEqual(plugin.ports, [8080, 8443, 9000])

def test_nullable_field_handling(self):
    """Verify nullable field handles None correctly"""
    config_path, temp_dir = create_test_config_file({
        "myplugin": {"optional_value": None}
    })
    self.temp_dirs.append(temp_dir)
    
    config_manager = ConfigManager(self.mock_args)
    config_manager.register_plugin_schema("myplugin", MyPlugin.config_schema)
    config_manager.load(config_path)
    
    plugin = MyPlugin(self.mock_args, config_manager)
    
    # Verify None is accepted
    self.assertIsNone(plugin.optional_value)
```

## Creating Tests for a New Plugin

### Step 1: Create Test File

Create `kast/tests/test_<plugin>_config.py`:

```python
"""
Test configuration system for <plugin> plugin
"""
import unittest
import tempfile
import shutil
import sys
import os
from unittest.mock import MagicMock, patch

sys.path.insert(0, '/opt/kast')

from kast.config_manager import ConfigManager
from kast.plugins.<plugin>_plugin import <PluginClass>
from kast.tests.helpers.config_test_helpers import (
    create_test_config_file,
    assert_config_values,
    verify_schema_completeness,
    verify_type_match,
    get_schema_defaults,
    validate_config_against_schema
)


class Test<Plugin>Config(unittest.TestCase):
    """Test suite for <plugin> configuration system"""
    
    def setUp(self):
        """Set up test fixtures before each test"""
        self.mock_args = MagicMock()
        self.mock_args.verbose = False
        self.mock_args.config = None
        self.mock_args.set = None
        # Add any legacy args here
        self.temp_dirs = []
    
    def tearDown(self):
        """Clean up after each test"""
        for temp_dir in self.temp_dirs:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
    
    # Add test methods here following the patterns above
```

### Step 2: Implement Standard Tests

Add all applicable test categories from the list above:
1. Schema validation
2. Default values
3. Config file overrides
4. CLI overrides
5. Type validation
6. Behavioral tests
7. Constraint validation
8. Legacy CLI args (if applicable)
9. Special types (if applicable)

### Step 3: Add Plugin-Specific Tests

Add tests for any plugin-specific behavior:
- Command building with specific flags
- Timeout enforcement
- Rate limiting
- Special processing logic
- Error handling

### Step 4: Run Tests

```bash
cd /opt/kast
python -m unittest kast.tests.test_<plugin>_config -v
```

## Test Checklist

When creating config tests for a plugin, verify:

- [ ] Schema has all required fields (`type`, `title`, `description`, `properties`)
- [ ] Each property has `default`, `type`, `description`
- [ ] Numeric properties have `minimum`/`maximum` constraints
- [ ] Array properties have `items` definition
- [ ] Default values are loaded correctly
- [ ] Config file overrides work
- [ ] CLI overrides work and take precedence
- [ ] All types are validated correctly
- [ ] Config values actually affect behavior
- [ ] Constraints are enforced
- [ ] Legacy CLI args work (if applicable)
- [ ] Array/nullable types work (if applicable)
- [ ] All tests pass

## Example Test Runs

### TestSSL Plugin (14 tests)
```bash
$ python -m unittest kast.tests.test_testssl_config -v
test_boolean_config_handling ... ok
test_cli_overrides_config_file ... ok
test_config_file_overrides_defaults ... ok
test_config_values_used_in_command_building ... ok
test_default_values_loaded ... ok
test_expected_config_properties ... ok
test_flags_present_when_enabled ... ok
test_invalid_config_values_detected ... ok
test_no_legacy_cli_args ... ok
test_numeric_constraints_validation ... ok
test_schema_defaults_extraction ... ok
test_schema_defined_and_valid ... ok
test_timeout_enforcement ... ok
test_type_validation ... ok

Ran 14 tests in 0.017s
OK
```

### Related Sites Plugin (19 tests)
```bash
$ python -m unittest kast.tests.test_related_sites_config -v
test_array_schema_has_items_definition ... ok
test_array_type_handling ... ok
test_backward_compatibility_legacy_cli_arg ... ok
test_cli_array_override_parsing ... ok
test_cli_overrides_config_file ... ok
test_config_file_overrides_defaults ... ok
test_config_values_used_in_command_building ... ok
test_default_values_loaded ... ok
test_expected_config_properties ... ok
test_invalid_config_values_detected ... ok
test_legacy_arg_takes_precedence_over_config_file ... ok
test_max_subdomains_limiting ... ok
test_nullable_field_handling ... ok
test_nullable_type_schema_format ... ok
test_numeric_constraints_validation ... ok
test_schema_defaults_extraction ... ok
test_schema_defined_and_valid ... ok
test_subfinder_timeout_config_usage ... ok
test_type_validation ... ok

Ran 19 tests in 0.030s
OK
```

## Best Practices

1. **Use Test Helpers** - Leverage the helper functions in `config_test_helpers.py`
2. **Clean Up** - Always clean up temp directories in `tearDown()`
3. **Mock External Calls** - Use `unittest.mock` for subprocess and file operations
4. **Test Real Behavior** - Don't just test config loading; verify it affects behavior
5. **Document Special Cases** - Add comments for unusual type handling or legacy behavior
6. **Be Thorough** - Cover all config properties, not just a subset
7. **Keep Tests Independent** - Each test should work in isolation

## Common Patterns

### Testing Command Building
```python
# Build command in report-only mode (doesn't execute)
temp_dir = tempfile.mkdtemp()
result_file = os.path.join(temp_dir, "plugin.json")
with open(result_file, 'w') as f:
    f.write('{}')

plugin.run("example.com", temp_dir, report_only=True)
command = plugin.command_executed

# Verify command contains expected flags
self.assertIn("--flag", command)
```

### Testing Timeout Parameters
```python
with patch('subprocess.run') as mock_run:
    mock_run.return_value = MagicMock(returncode=0)
    
    # Create mock output
    result_file = os.path.join(temp_dir, "output.json")
    with open(result_file, 'w') as f:
        f.write('{}')
    
    plugin.run("example.com", temp_dir, report_only=False)
    
    # Verify timeout was passed
    call_kwargs = mock_run.call_args[1]
    self.assertEqual(call_kwargs['timeout'], expected_timeout)
```

## Troubleshooting

### Tests Fail with "No module named pytest"
Use unittest instead:
```bash
python -m unittest kast.tests.test_plugin_config -v
```

### Type Mismatch Errors
ConfigManager may parse CLI values as strings. Document this in tests:
```python
# Note: ConfigManager parses comma-separated CLI values as strings
self.assertEqual(plugin.ports, ['80', '443', '8080'])
```

### Temp Directory Not Cleaned
Ensure `tearDown()` properly cleans up:
```python
def tearDown(self):
    for temp_dir in self.temp_dirs:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
```

## Summary

This testing framework ensures robust configuration migration by:

1. **Validating schema structure** - Catches missing/invalid schema definitions
2. **Testing all precedence levels** - Defaults → Config File → CLI
3. **Verifying type safety** - Ensures correct Python types
4. **Confirming behavioral impact** - Config actually affects execution
5. **Maintaining backward compatibility** - Legacy CLI args still work
6. **Supporting special types** - Arrays, nullables, objects handled correctly

Use this framework as you migrate each plugin to ensure consistent, reliable configuration handling across the entire KAST project.
