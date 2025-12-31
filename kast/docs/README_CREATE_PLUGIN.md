# KAST Plugin Creator

A helper script to streamline the creation of new KAST plugins using either a clean template or an existing plugin as the base.

## Overview

The `create_plugin.py` script implements a **hybrid approach** that offers two strategies for plugin creation:

1. **Template-based** (default): Start from a clean template with minimal boilerplate
2. **Existing plugin-based**: Copy and adapt from an existing plugin

## Quick Start

### Interactive Mode (Recommended)

```bash
python kast/scripts/create_plugin.py --interactive
```

Interactive mode guides you through all options with prompts and validation.

### Command-Line Mode

```bash
# Create from template (default)
python kast/scripts/create_plugin.py --name nmap --display-name "Nmap Port Scanner"

# Create based on existing plugin
python kast/scripts/create_plugin.py --name nikto --based-on whatweb --scan-type active

# Quick create with minimal options
python kast/scripts/create_plugin.py --name gobuster
```

## Strategy Comparison

### Strategy 1: Template-Based Creation

**When to use:**
- Starting a new plugin from scratch
- Tool has unique output format or behavior
- Want to ensure clean implementation without legacy code
- Learning KAST plugin development

**Pros:**
- Clean slate with minimal boilerplate
- Educational - forces understanding of each section
- No tool-specific logic to remove
- Consistent starting point

**Cons:**
- More manual work required
- No working examples of complex features
- Slower initial development

**Example:**
```bash
python kast/scripts/create_plugin.py --name nmap --display-name "Nmap Port Scanner"
```

### Strategy 2: Existing Plugin-Based Creation

**When to use:**
- New tool similar to existing one (e.g., another JSON-output scanner)
- Want to copy proven patterns (error handling, parsing logic)
- Need faster time to working plugin
- Tool has similar architecture to existing plugin

**Pros:**
- Faster time to working plugin
- Real-world patterns already implemented
- Copy-paste friendly for similar tools
- Proven, tested code

**Cons:**
- May inherit irrelevant tool-specific logic
- Requires careful review to identify what needs changing
- Risk of keeping code you don't understand

**Example:**
```bash
python kast/scripts/create_plugin.py --name nikto --based-on whatweb --scan-type active
```

**Available base plugins:**
- `katana` - Web crawler
- `observatory` - Mozilla Observatory scanner
- `script_detection` - JavaScript detection
- `subfinder` - Subdomain enumeration
- `testssl` - SSL/TLS testing
- `wafw00f` - WAF detection
- `whatweb` - Technology identification

## Command-Line Options

```
--name NAME                   Tool name (required, lowercase, underscores allowed)
--display-name DISPLAY_NAME   Human-readable display name (default: title-cased name)
--description DESCRIPTION     Short description (default: "{name} security scanner")
--website-url WEBSITE_URL     Tool website URL
--scan-type {passive,active}  Scan type (default: passive)
--output-type {file,stdout}   Output type (default: file)
--priority PRIORITY           Execution priority 10-90 (default: 50, lower=earlier)
--based-on BASED_ON          Base template (default: template)
--interactive, -i            Interactive mode
--no-test                    Skip creating test file
--no-open                    Don't open file in editor
```

## What Gets Created

The script creates two files:

1. **Plugin file**: `kast/plugins/{name}_plugin.py`
   - Customized from template or existing plugin
   - All basic attributes pre-filled
   - Ready to customize for your tool

2. **Test file**: `kast/tests/test_{name}_plugin.py`
   - Unit test skeleton
   - Basic tests for initialization and availability
   - TODO markers for tool-specific tests

## Customization Checklist

After creation, the script displays a checklist of sections to customize:

- [ ] Update `is_available()` to check for tool installation
- [ ] Customize command structure in `run()` method
- [ ] Implement command flags and options for your tool
- [ ] Handle tool-specific error conditions
- [ ] Implement output parsing in `post_process()`
- [ ] Calculate `findings_count` based on plugin's primary output (see below)
- [ ] Define issue extraction logic (map to `issue_registry.json` if applicable)
- [ ] Create meaningful executive summary
- [ ] Update `_generate_summary()` with tool-specific logic
- [ ] Add tool-specific helper methods as needed
- [ ] Write unit tests in test file
- [ ] Test plugin with real tool output
- [ ] Update plugin documentation in docstrings

## Understanding findings_count

The `findings_count` field is a required integer in the processed output that reflects the count of the "primary things" your plugin discovers. This provides a quick metric for understanding plugin output at a glance.

### What to Count by Plugin Type

Each plugin should count its primary output - the main thing it was designed to find:

| Plugin Type | Count | Example |
|-------------|-------|---------|
| URL Discovery | Number of URLs found | `len(urls_list)` |
| Subdomain Discovery | Number of subdomains found | `len(subdomains_list)` |
| Vulnerability Scanner | Number of issues/vulnerabilities | `len(issues)` |
| WAF Detection | Number of WAFs detected | `1` if detected, `0` if not |
| Technology Detection | Number of technologies identified | `len(technologies)` |
| Port Scanner | Number of open ports | `len(open_ports)` |
| Information Gathering | Number of findings/detections | `len(findings)` |

### Implementation Examples

**URL Discovery (like Katana):**
```python
# Count unique URLs found
findings_count = len(parsed_urls)
```

**Subdomain Discovery (like Subfinder):**
```python
# Count unique subdomains
findings_count = len(subdomains)
```

**Vulnerability Scanner (like TestSSL):**
```python
# Count total issues (vulnerabilities + cipher issues)
findings_count = len(issues)
```

**Information Gathering (generic):**
```python
# Count findings based on data structure
findings_count = len(findings) if isinstance(findings, list) else len(findings.keys()) if isinstance(findings, dict) else 0
```

### Best Practices

1. **Always return an integer**, even if 0 (never null/undefined)
2. **Count the primary output** - what users expect from this plugin
3. **Be consistent** - same counting logic across similar plugins
4. **Document your counting** - add a comment explaining what you're counting
5. **Test edge cases** - ensure count is 0 when nothing is found

### Adding findings_count to post_process()

In your plugin's `post_process()` method, calculate `findings_count` before building the processed dictionary:

```python
def post_process(self, raw_output, output_dir):
    # ... load and process findings ...
    
    # Calculate findings_count based on your plugin's primary output
    findings_count = len(parsed_urls)  # Customize this line
    
    processed = {
        "plugin-name": self.name,
        # ... other fields ...
        "findings_count": findings_count,  # Add this field
        # ... remaining fields ...
    }
    
    # ... save processed output ...
```

## Examples

### Example 1: Port Scanner (Template-Based)

```bash
python kast/scripts/create_plugin.py \
  --name nmap \
  --display-name "Nmap Port Scanner" \
  --description "Network port scanning and service detection" \
  --website-url "https://nmap.org" \
  --scan-type active \
  --priority 40
```

**Best choice:** Template-based - port scanning is unique functionality

### Example 2: Web Vulnerability Scanner (Based on WhatWeb)

```bash
python kast/scripts/create_plugin.py \
  --name nikto \
  --display-name "Nikto" \
  --description "Web server vulnerability scanner" \
  --website-url "https://github.com/sullo/nikto" \
  --based-on whatweb \
  --scan-type active \
  --priority 60
```

**Best choice:** Based on WhatWeb - similar web scanning, JSON output patterns

### Example 3: Directory Brute-forcing (Based on Katana)

```bash
python kast/scripts/create_plugin.py \
  --name gobuster \
  --display-name "Gobuster" \
  --description "Directory and DNS brute-forcing tool" \
  --website-url "https://github.com/OJ/gobuster" \
  --based-on katana \
  --scan-type active \
  --priority 55
```

**Best choice:** Based on Katana - similar crawling/enumeration patterns

## Tool Availability Checking

The script automatically:
- Checks if tool exists in PATH during interactive mode
- Warns if tool is not found
- Allows proceeding anyway (tool might be installed later)

## Post-Creation Steps

1. **Review the generated plugin**
   - Verify all attributes are correct
   - Customize command structure for your tool
   - Implement output parsing logic

2. **Implement tests**
   - Add tool-specific test cases
   - Create sample output for testing
   - Test both success and failure scenarios

3. **Test with real tool**
   ```bash
   # Run KAST with just your plugin
   python kast/main.py --target https://example.com --plugins your_tool
   ```

4. **Add to configuration** (optional)
   - Update `kast_default.yaml` if tool should be included by default

## Best Practices

### When to use Template vs Existing Plugin

**Use Template when:**
- Tool has unique architecture
- Output format is significantly different
- You're learning plugin development
- Starting completely fresh

**Use Existing Plugin when:**
- Tools have similar output (both JSON, both stdout, etc.)
- Similar error handling needed
- Want to copy proven patterns
- Time-sensitive development

### After Copying from Existing Plugin

If you used `--based-on`, carefully review and remove:
- Tool-specific command flags
- Custom parsing logic for that tool's output
- Helper methods specific to the original tool
- Comments mentioning the original tool name

The script marks these with the original tool name to help you identify them.

## Troubleshooting

### Plugin Already Exists

```
✗ Error: Plugin 'toolname_plugin.py' already exists
```

**Solution:** Choose a different name or remove the existing plugin first.

### Based-On Plugin Not Found

```
✗ Error: Plugin 'nonexistent' not found.
Available plugins: katana, observatory, ...
```

**Solution:** Use one of the available plugins listed or use `template`.

### Import Errors After Creation

**Solution:** Make sure plugin name follows Python naming conventions (lowercase, underscores only).

## Contributing

When adding new plugins that could serve as good templates:
- Follow KAST plugin patterns
- Include comprehensive error handling  
- Document complex parsing logic
- Consider if it would make a good base for similar tools

## See Also

- [KAST Plugin Development Guide](../../genai-instructions.md)
- [Plugin Template](../plugins/template_plugin.py)
- [Plugin Base Class](../plugins/base.py)
- [Issue Registry](../data/issue_registry.json)
