# FTAP Configuration Migration

**Date:** 2025-12-23  
**Plugin:** `ftap_plugin.py`  
**Status:** ✅ Complete

## Overview

Migrated the FTAP (Find The Admin Panel) plugin to use the centralized configuration system. This allows users to configure all FTAP scanning options through YAML configuration files or CLI overrides, replacing the previous hard-coded approach.

## Changes Made

### 1. Configuration Schema

Added comprehensive `config_schema` class attribute defining all FTAP configuration options:

```python
config_schema = {
    "type": "object",
    "title": "FTAP Configuration",
    "description": "Configuration for Find The Admin Panel plugin",
    "properties": {
        "detection_mode": {
            "type": "string",
            "enum": ["simple", "stealth", "aggressive"],
            "default": "stealth"
        },
        "wordlist_path": {
            "type": "string",
            "default": None
        },
        "update_wordlist": {
            "type": "boolean",
            "default": False
        },
        "wordlist_source": {
            "type": "string",
            "default": None
        },
        "machine_learning": {
            "type": "boolean",
            "default": False
        },
        "fuzzing": {
            "type": "boolean",
            "default": False
        },
        "http3": {
            "type": "boolean",
            "default": False
        },
        "concurrency": {
            "type": "integer",
            "minimum": 1,
            "maximum": 200,
            "default": None
        },
        "export_format": {
            "type": "string",
            "enum": ["json", "html", "csv", "txt"],
            "default": "json"
        },
        "interactive": {
            "type": "boolean",
            "default": False
        }
    }
}
```

### 2. Configuration Loading

Implemented `_load_plugin_config()` method that uses the base class's `get_config()` method to load configuration values into instance variables:

```python
def _load_plugin_config(self):
    """Load configuration values from ConfigManager."""
    # Detection settings
    self.detection_mode = self.get_config("detection_mode", "stealth")
    self.machine_learning = self.get_config("machine_learning", False)
    self.fuzzing = self.get_config("fuzzing", False)
    self.http3 = self.get_config("http3", False)
    
    # Wordlist settings
    self.wordlist_path = self.get_config("wordlist_path", None)
    self.update_wordlist = self.get_config("update_wordlist", False)
    self.wordlist_source = self.get_config("wordlist_source", None)
    
    # Performance settings
    self.concurrency = self.get_config("concurrency", None)
    
    # Output settings
    self.export_format = self.get_config("export_format", "json")
    self.interactive = self.get_config("interactive", False)
```

### 3. Dynamic Command Building

Updated `run()` method to build commands dynamically based on configuration:

**Before (Hard-coded):**
```python
cmd = [
    "ftap",
    "--url", target,
    "--detection-mode", "stealth",  # Always stealth
    "-d", str(output_dir),
    "-e", "json",                   # Always JSON
    "-f", "ftap.json"
]
```

**After (Configuration-driven):**
```python
cmd = ["ftap", "--url", target]

# Add detection mode from config
cmd.extend(["--detection-mode", self.detection_mode])

# Add output format from config
cmd.extend(["-e", self.export_format])

# Add optional features based on config
if self.wordlist_path:
    cmd.extend(["-w", self.wordlist_path])

if self.update_wordlist:
    cmd.append("--update-wordlist")
    if self.wordlist_source:
        cmd.extend(["--source", self.wordlist_source])

if self.machine_learning:
    cmd.append("--machine-learning")

if self.fuzzing:
    cmd.append("--fuzzing")

if self.http3:
    cmd.append("--http3")

if self.concurrency is not None:
    cmd.extend(["--concurrency", str(self.concurrency)])

if self.interactive:
    cmd.append("-i")
```

### 4. Output File Handling

Added logic to determine output filename based on `export_format` configuration:

```python
if self.export_format == "json":
    output_filename = "ftap.json"
elif self.export_format == "html":
    output_filename = "ftap.html"
elif self.export_format == "csv":
    output_filename = "ftap.csv"
else:  # txt
    output_filename = "ftap.txt"
```

### 5. Dry Run Information

Updated `get_dry_run_info()` to build commands using current configuration and provide detailed operations description:

```python
def get_dry_run_info(self, target, output_dir):
    # Build command using current config
    cmd = [...]  # Dynamic command building
    
    # Build operations description
    operations = f"Scan for admin panels using {self.detection_mode} mode"
    
    if self.machine_learning:
        operations += " with machine learning detection"
    if self.fuzzing:
        operations += " and path fuzzing"
    if self.http3:
        operations += ", HTTP/3 support enabled"
    if self.concurrency:
        operations += f", concurrency: {self.concurrency}"
    if self.wordlist_path:
        operations += f", custom wordlist: {self.wordlist_path}"
    
    return {
        "commands": [' '.join(cmd)],
        "description": self.description,
        "operations": operations
    }
```

## Configuration Options

### Detection Settings

#### `detection_mode`
- **Type:** String (enum)
- **Options:** `simple`, `stealth`, `aggressive`
- **Default:** `stealth`
- **Description:** Scanning strategy
  - `simple`: Basic detection (fast, basic checks)
  - `stealth`: Careful detection (slower, less detectable)
  - `aggressive`: Fast detection (150 concurrent tasks, most noticeable)

#### `machine_learning`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Enable ML-based admin panel detection (experimental)

#### `fuzzing`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Enable path fuzzing capabilities for discovery

#### `http3`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Enable HTTP/3 protocol support

### Wordlist Settings

#### `wordlist_path`
- **Type:** String
- **Default:** `null`
- **Description:** Path to custom wordlist file for admin path discovery

#### `update_wordlist`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Update wordlists with latest admin paths before scanning

#### `wordlist_source`
- **Type:** String
- **Default:** `null`
- **Description:** Source URL for wordlist updates (requires `update_wordlist: true`)

### Performance Settings

#### `concurrency`
- **Type:** Integer
- **Range:** 1-200
- **Default:** `null` (uses FTAP's default)
- **Description:** Maximum number of concurrent requests

### Output Settings

#### `export_format`
- **Type:** String (enum)
- **Options:** `json`, `html`, `csv`, `txt`
- **Default:** `json`
- **Description:** Output format for results

#### `interactive`
- **Type:** Boolean
- **Default:** `false`
- **Description:** Run in interactive mode (prompts for input)

## Usage Examples

### YAML Configuration

**Basic Configuration (Stealth Mode):**
```yaml
plugins:
  ftap:
    detection_mode: stealth
    export_format: json
```

**Aggressive Scanning:**
```yaml
plugins:
  ftap:
    detection_mode: aggressive
    concurrency: 150
    export_format: json
```

**Custom Wordlist:**
```yaml
plugins:
  ftap:
    detection_mode: stealth
    wordlist_path: /opt/custom/admin_paths.txt
    export_format: json
```

**All Features Enabled:**
```yaml
plugins:
  ftap:
    detection_mode: aggressive
    machine_learning: true
    fuzzing: true
    http3: true
    concurrency: 200
    wordlist_path: /opt/wordlists/admin_custom.txt
    update_wordlist: true
    wordlist_source: https://github.com/example/wordlists
    export_format: html
```

### CLI Overrides

**Override detection mode:**
```bash
kast scan example.com --set ftap.detection_mode=aggressive
```

**Override concurrency:**
```bash
kast scan example.com --set ftap.concurrency=100
```

**Enable machine learning:**
```bash
kast scan example.com --set ftap.machine_learning=true
```

**Multiple overrides:**
```bash
kast scan example.com \
  --set ftap.detection_mode=aggressive \
  --set ftap.machine_learning=true \
  --set ftap.concurrency=150
```

## Testing

Created comprehensive test suite in `kast/tests/test_ftap_config.py`:

- ✅ Schema registration (1 test)
- ✅ Default configuration loading (1 test)
- ✅ Config file loading (1 test)
- ✅ CLI overrides precedence (1 test)
- ✅ Command building with defaults (1 test)
- ✅ Command building with each option (10 tests)
- ✅ Command building with all features (1 test)
- ✅ Operations description (2 tests)

**Total: 18 tests - All Passing ✅**

Run tests:
```bash
python -m unittest kast.tests.test_ftap_config -v
```

## Benefits

1. **Flexibility**: Users can easily configure FTAP behavior without modifying code
2. **Different Environments**: Can use stealth mode in production, aggressive in pentesting
3. **Custom Wordlists**: Organizations can use their own admin path wordlists
4. **Performance Control**: Fine-tune concurrency for different network conditions
5. **Advanced Features**: Easy enablement of ML, fuzzing, HTTP/3
6. **Export Formats**: Choose output format based on workflow needs
7. **Consistency**: Follows same pattern as other KAST plugins

## Migration Notes

### Breaking Changes
None - maintains backward compatibility. The plugin defaults to stealth mode with JSON output, matching the previous hard-coded behavior.

### Upgrade Path
1. No changes required for existing users
2. To customize behavior, add `ftap` section to config file
3. Configuration is optional - defaults work out of the box

## Related Documentation

- `kast/docs/CONFIGURATION_SYSTEM.md` - Configuration system overview
- `kast/docs/CONFIG_TESTING_GUIDE.md` - Testing guide
- `kast/tests/test_ftap_config.py` - Test implementation
- Other plugin migrations:
  - `RELATED_SITES_CONFIG.md`
  - `TESTSSL_CONFIG_MIGRATION.md`
  - `KATANA_CONFIG_MIGRATION.md`

## Future Enhancements

Potential future configuration options:
- `timeout`: Request timeout in seconds
- `rate_limit`: Maximum requests per second
- `custom_headers`: Custom HTTP headers for requests
- `proxy`: HTTP proxy configuration
- `ssl_verify`: SSL certificate verification toggle
- `follow_redirects`: Whether to follow HTTP redirects
