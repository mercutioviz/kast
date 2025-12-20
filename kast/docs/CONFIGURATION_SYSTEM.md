# KAST Configuration System

## Overview

KAST uses a flexible, hierarchical configuration system that supports both CLI users and GUI tools like kast-web. The system combines YAML configuration files with command-line overrides and JSON schema exports for automated form generation.

## Design Goals

1. **CLI Flexibility**: Power users can override any setting via command line
2. **File-Based Configuration**: Persistent settings stored in YAML files
3. **GUI Integration**: JSON schemas enable auto-generated forms in kast-web
4. **Backward Compatibility**: Legacy CLI arguments continue to work
5. **Type Safety**: JSON Schema validation ensures correct data types
6. **Discoverability**: Schema includes descriptions and constraints

## Configuration Architecture

### Configuration Priority (Highest to Lowest)

1. **CLI Overrides**: `--set plugin.key=value`
2. **Legacy CLI Arguments**: Deprecated but still supported (e.g., `--httpx-rate-limit`)
3. **Project-Specific Config**: `./kast_config.yaml` (in current directory)
4. **User Config**: `~/.config/kast/config.yaml` (XDG standard)
5. **System Config**: `/etc/kast/config.yaml` (system-wide)
6. **Plugin Defaults**: Defined in plugin's `config_schema`

### File Structure

```yaml
kast:
  config_version: "1.0"

global:
  timeout: 300
  retry_count: 2

plugins:
  related_sites:
    httpx_rate_limit: 10
    subfinder_timeout: 300
    max_subdomains: null
    httpx_ports: [80, 443, 8080, 8443, 8000, 8888]
    httpx_timeout: 10
    httpx_threads: 50
```

## CLI Usage

### Creating a Configuration File

```bash
# Generate default config with all plugin options
kast --config-init

# Creates: ~/.config/kast/config.yaml
```

### Viewing Current Configuration

```bash
# Show merged configuration (file + CLI overrides)
kast --config-show

# Show with custom config file
kast --config config.yaml --config-show
```

### Exporting JSON Schema

```bash
# Export schema for kast-web integration
kast --config-schema > kast_schema.json
```

### Using Configuration

```bash
# Use default config (~/.config/kast/config.yaml)
kast -t example.com

# Use custom config file
kast --config /path/to/config.yaml -t example.com

# Override specific settings
kast -t example.com --set related_sites.httpx_rate_limit=20

# Multiple overrides
kast -t example.com \
  --set related_sites.httpx_rate_limit=20 \
  --set related_sites.max_subdomains=100
```

### CLI Override Syntax

```bash
# Format: --set plugin_name.setting_name=value

# Integer values
--set related_sites.httpx_rate_limit=20

# Boolean values
--set plugin_name.enabled=true
--set plugin_name.enabled=false

# Null values
--set related_sites.max_subdomains=null

# List values (comma-separated)
--set related_sites.httpx_ports=80,443,8080

# String values
--set plugin_name.output_format=json
```

## Plugin Development

### Defining Configuration Schema

Each plugin should define a `config_schema` class variable using JSON Schema:

```python
from kast.plugins.base import KastPlugin

class MyPlugin(KastPlugin):
    priority = 50
    
    # Define configuration schema
    config_schema = {
        "type": "object",
        "title": "My Plugin Configuration",
        "description": "Settings for my awesome plugin",
        "properties": {
            "timeout": {
                "type": "integer",
                "default": 300,
                "minimum": 30,
                "maximum": 3600,
                "description": "Timeout in seconds"
            },
            "rate_limit": {
                "type": "integer",
                "default": 10,
                "minimum": 1,
                "maximum": 100,
                "description": "Maximum requests per second"
            },
            "enabled_features": {
                "type": "array",
                "items": {"type": "string"},
                "default": ["feature1", "feature2"],
                "description": "List of enabled features"
            },
            "max_items": {
                "type": ["integer", "null"],
                "default": None,
                "minimum": 1,
                "description": "Maximum items to process (null = unlimited)"
            }
        }
    }
    
    def __init__(self, cli_args, config_manager=None):
        super().__init__(cli_args, config_manager)
        self.name = "my_plugin"
        # ... rest of init
        
        # Load configuration
        self._load_plugin_config()
    
    def _load_plugin_config(self):
        """Load configuration with backward compatibility."""
        # Get config values (defaults from schema if not set)
        self.timeout = self.get_config('timeout', 300)
        self.rate_limit = self.get_config('rate_limit', 10)
        self.enabled_features = self.get_config('enabled_features', [])
        self.max_items = self.get_config('max_items', None)
        
        # Backward compatibility for legacy CLI args
        if hasattr(self.cli_args, 'my_plugin_timeout') and self.cli_args.my_plugin_timeout:
            self.timeout = self.cli_args.my_plugin_timeout
            self.debug("Using deprecated --my-plugin-timeout CLI arg")
```

### JSON Schema Field Types

```python
# Integer
{
    "type": "integer",
    "default": 100,
    "minimum": 1,
    "maximum": 1000,
    "description": "An integer value"
}

# Float/Number
{
    "type": "number",
    "default": 10.5,
    "minimum": 0.1,
    "maximum": 100.0,
    "description": "A numeric value"
}

# Boolean
{
    "type": "boolean",
    "default": True,
    "description": "A true/false flag"
}

# String
{
    "type": "string",
    "default": "default_value",
    "description": "A text value"
}

# Array/List
{
    "type": "array",
    "items": {"type": "string"},
    "default": ["item1", "item2"],
    "description": "A list of strings"
}

# Nullable (allow null values)
{
    "type": ["integer", "null"],
    "default": None,
    "description": "An optional integer"
}

# Object (nested config)
{
    "type": "object",
    "properties": {
        "nested_key": {"type": "string", "default": "value"}
    },
    "description": "A nested configuration object"
}
```

### Best Practices

1. **Always provide defaults**: Every configuration key should have a sensible default
2. **Add constraints**: Use `minimum`, `maximum`, etc. to validate ranges
3. **Write clear descriptions**: These appear in kast-web's UI and help text
4. **Use appropriate types**: Match the data type to the usage
5. **Support null where appropriate**: Use `["type", "null"]` for optional limits
6. **Backward compatibility**: Check for legacy CLI args in `_load_plugin_config()`

## kast-web Integration

### Workflow Overview

1. **Schema Export**: kast-web calls `kast --config-schema` to get JSON schema
2. **Form Generation**: kast-web generates UI forms from the schema
3. **Config Generation**: User selections are saved to a config file
4. **Execution**: kast-web calls `kast --config config.yaml -t target.com`

### Schema Export Format

```json
{
  "kast": {
    "config_version": "1.0",
    "description": "KAST Configuration Schema"
  },
  "global": {
    "type": "object",
    "title": "Global Settings",
    "properties": {
      "timeout": {
        "type": "integer",
        "default": 300,
        "minimum": 30,
        "description": "Default timeout in seconds"
      }
    }
  },
  "plugins": {
    "related_sites": {
      "type": "object",
      "title": "Related Sites Discovery Configuration",
      "description": "Settings for subdomain enumeration",
      "properties": {
        "httpx_rate_limit": {
          "type": "integer",
          "default": 10,
          "minimum": 1,
          "maximum": 100,
          "description": "Maximum HTTP requests per second"
        }
      }
    }
  }
}
```

### Integration Steps for kast-web

#### 1. Fetch Schema

```javascript
// Execute: kast --config-schema
const { execSync } = require('child_process');
const schema = JSON.parse(execSync('kast --config-schema').toString());
```

#### 2. Generate Forms

```javascript
// For each plugin in schema.plugins
for (const [pluginName, pluginSchema] of Object.entries(schema.plugins)) {
  const title = pluginSchema.title;
  const description = pluginSchema.description;
  
  // For each configuration property
  for (const [key, propSchema] of Object.entries(pluginSchema.properties)) {
    // Generate appropriate input based on type
    const inputType = propSchema.type;
    const defaultValue = propSchema.default;
    const description = propSchema.description;
    
    if (inputType === 'integer' || inputType === 'number') {
      // Generate number input with min/max constraints
      const min = propSchema.minimum;
      const max = propSchema.maximum;
      // Create <input type="number" min={min} max={max} value={defaultValue}>
    } else if (inputType === 'boolean') {
      // Generate checkbox
      // Create <input type="checkbox" checked={defaultValue}>
    } else if (inputType === 'array') {
      // Generate multi-select or tag input
      // Based on propSchema.items.type
    }
  }
}
```

#### 3. Save Configuration

```javascript
// User selections -> YAML config file
const yaml = require('yaml');

const config = {
  kast: { config_version: "1.0" },
  global: globalSettings,
  plugins: {
    related_sites: {
      httpx_rate_limit: userInputs.httpx_rate_limit,
      // ... other settings
    }
  }
};

const yamlContent = yaml.stringify(config);
fs.writeFileSync('user_config.yaml', yamlContent);
```

#### 4. Execute Scan

```javascript
// Execute with user's config
const { exec } = require('child_process');

exec(`kast --config user_config.yaml -t ${target} -o ${outputDir}`, 
  (error, stdout, stderr) => {
    // Handle execution results
  }
);
```

### React Example for kast-web

```jsx
import React, { useState, useEffect } from 'react';

function PluginConfigForm({ pluginName, schema }) {
  const [config, setConfig] = useState({});
  
  useEffect(() => {
    // Initialize with defaults from schema
    const defaults = {};
    for (const [key, prop] of Object.entries(schema.properties)) {
      defaults[key] = prop.default;
    }
    setConfig(defaults);
  }, [schema]);
  
  const handleChange = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }));
  };
  
  return (
    <div className="plugin-config-form">
      <h3>{schema.title}</h3>
      <p>{schema.description}</p>
      
      {Object.entries(schema.properties).map(([key, prop]) => (
        <div key={key} className="config-field">
          <label>
            {key.replace(/_/g, ' ')}
            <span className="help-text">{prop.description}</span>
          </label>
          
          {prop.type === 'integer' && (
            <input
              type="number"
              value={config[key] || prop.default}
              min={prop.minimum}
              max={prop.maximum}
              onChange={e => handleChange(key, parseInt(e.target.value))}
            />
          )}
          
          {prop.type === 'boolean' && (
            <input
              type="checkbox"
              checked={config[key] || prop.default}
              onChange={e => handleChange(key, e.target.checked)}
            />
          )}
          
          {prop.type === 'string' && (
            <input
              type="text"
              value={config[key] || prop.default}
              onChange={e => handleChange(key, e.target.value)}
            />
          )}
        </div>
      ))}
    </div>
  );
}
```

## Migration Guide

### For Existing KAST Users

No immediate action required - legacy CLI arguments continue to work:

```bash
# Old way (still works)
kast -t example.com --httpx-rate-limit 20

# New way (preferred)
kast -t example.com --set related_sites.httpx_rate_limit=20
```

To migrate to the new system:

1. Create a config file: `kast --config-init`
2. Edit `~/.config/kast/config.yaml` with your preferred settings
3. Remove CLI arguments from your scripts (settings now in file)
4. Use `--set` for occasional overrides

### For Plugin Developers

To update existing plugins for the new config system:

1. Add `config_schema` class variable to your plugin
2. Update `__init__` to accept `config_manager` parameter
3. Call `super().__init__(cli_args, config_manager)`
4. Create `_load_plugin_config()` method to load settings
5. Use `self.get_config(key, default)` to access configuration
6. Support backward compatibility for legacy CLI args

See `kast/plugins/related_sites_plugin.py` for a complete example.

## Troubleshooting

### Configuration Not Loading

```bash
# Check which config file is being used
kast --config-show

# Verify config file syntax
python -c "import yaml; yaml.safe_load(open('config.yaml'))"
```

### Schema Export Issues

```bash
# Ensure all plugins load correctly
kast --list-plugins

# Check for Python errors
kast --config-schema 2>&1 | grep -i error
```

### CLI Overrides Not Working

```bash
# Verify syntax: plugin.key=value (no spaces around =)
kast -t example.com --set related_sites.httpx_rate_limit=20  # ✓ Correct
kast -t example.com --set related_sites.httpx_rate_limit = 20  # ✗ Wrong
```

### Type Validation Errors

The config manager validates types against the schema. Common issues:

```yaml
# Wrong: String when integer expected
httpx_rate_limit: "20"  # Should be: 20

# Wrong: Integer when array expected
httpx_ports: 80  # Should be: [80] or [80, 443]

# Correct: null for nullable fields
max_subdomains: null  # OK if schema allows ["integer", "null"]
```

## Future Enhancements

- [ ] Config file validation command: `kast --config-validate`
- [ ] Plugin-specific config help: `kast --config-help plugin_name`
- [ ] Environment variable support: `KAST_PLUGIN_SETTING=value`
- [ ] Config templates for common use cases
- [ ] Encrypted config values for API keys
- [ ] Config versioning and migration tools

## Related Documentation

- **Plugin Development**: `kast/docs/README_CREATE_PLUGIN.md`
- **genai Instructions**: `genai-instructions.md`
- **Configuration Template**: `kast/config/default_config.yaml`
- **Config Manager Code**: `kast/config_manager.py`
