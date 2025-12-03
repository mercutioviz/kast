# KAST GenAI Instructions

This document provides comprehensive guidance for GenAI assistants working with the KAST (Kali Automated Scan Tool) project. It contains essential information about project architecture, coding conventions, development patterns, and best practices.

**Version:** 2.6.2  
**Last Updated:** December 2025  
**Project Repository:** https://github.com/mercutioviz/kast

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture & Design Patterns](#architecture--design-patterns)
3. [Code Style & Conventions](#code-style--conventions)
4. [Plugin Development Guide](#plugin-development-guide)
5. [Testing Standards](#testing-standards)
6. [Common Patterns](#common-patterns)
7. [Key Concepts](#key-concepts)
8. [File Organization](#file-organization)
9. [Documentation Standards](#documentation-standards)
10. [Integration Points](#integration-points)
11. [Prompt Engineering Tips](#prompt-engineering-tips)

---

## Project Overview

### What is KAST?

KAST is a modular, extensible Python framework for automating web application security scanning tools. It orchestrates multiple security tools (Script Detection, WhatWeb, TestSSL, Wafw00f, Subfinder, Katana, Observatory), aggregates findings, and generates comprehensive HTML and PDF reports with executive summaries.

### Core Purpose

- **Orchestrate** multiple security scanning tools in a unified workflow
- **Standardize** output formats across different tools
- **Generate** professional reports (HTML/PDF) with executive summaries
- **Centralize** security issue definitions with remediation guidance
- **Enable** both parallel and sequential execution modes
- **Support** active and passive scanning methodologies

### Key Features

- Modular plugin architecture for easy extensibility
- Parallel execution with dependency resolution
- Priority-based plugin scheduling
- Issue registry with severity ratings and remediation guidance
- Report-only mode for regenerating reports from existing data
- Dry-run mode for previewing execution
- Rich CLI with progress indicators
- Comprehensive logging infrastructure

---

## Architecture & Design Patterns

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         CLI Entry Point                      │
│                        (kast/main.py)                        │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Scan Orchestrator                         │
│                   (kast/orchestrator.py)                     │
│  • Manages plugin lifecycle                                  │
│  • Handles parallel/sequential execution                     │
│  • Resolves plugin dependencies                              │
│  • Tracks timing information                                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                      Plugin System                           │
│                   (kast/plugins/*.py)                        │
│  • Each plugin wraps a security tool                         │
│  • Inherits from KastPlugin base class                       │
│  • Implements: is_available(), run(), post_process()         │
│  • Produces standardized JSON output                         │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                     Report Builder                           │
│                 (kast/report_builder.py)                     │
│  • Aggregates plugin results                                 │
│  • Generates executive summaries                             │
│  • Creates HTML and PDF reports                              │
│  • Uses Jinja2 templates                                     │
└─────────────────────────────────────────────────────────────┘
```

### Design Patterns Used

1. **Plugin Architecture (Strategy Pattern)**
   - Each security tool is wrapped in a plugin class
   - All plugins implement the same interface (`KastPlugin`)
   - Plugins are discovered and loaded dynamically
   - Easy to add new tools without modifying core code

2. **Template Method Pattern**
   - Base class (`KastPlugin`) defines plugin lifecycle
   - Subclasses override specific methods
   - Common functionality in base class (logging, result formatting)

3. **Factory Pattern**
   - Plugins instantiated via class references
   - Orchestrator creates plugin instances as needed

4. **Observer Pattern**
   - Dependency system allows plugins to wait for other plugins
   - Results are shared via `completed_plugins` dictionary

5. **Builder Pattern**
   - `ReportBuilder` constructs complex reports step-by-step
   - Separates report data aggregation from rendering

### PDF Report Generation Architecture

KAST uses a **dual-template approach** for generating both HTML and PDF reports from the same data:

**Architecture Overview:**
```
Plugin Results → ReportBuilder → {HTML Template → Interactive HTML Report
                                 {PDF Template  → Static PDF Report (WeasyPrint)
```

**Key Components:**

1. **Separate Templates:**
   - `report_template.html` - Interactive HTML with JavaScript, collapsible sections, JSON tree viewers
   - `report_template_pdf.html` - Static, print-optimized layout with expanded content

2. **Separate Stylesheets:**
   - `kast_style.css` - Web-optimized styling (flexbox, hover effects, interactive elements)
   - `kast_style_pdf.css` - Print-optimized styling (page breaks, static layout, no JavaScript dependencies)

3. **Format-Specific Processing:**
   - **HTML Reports:** Use `custom_html` field from plugins for interactive widgets
   - **PDF Reports:** Use `custom_html_pdf` field for simplified, print-friendly content
   - **Image Handling:** PDF embeds images as base64 data URIs (no external file dependencies)
   - **JSON Rendering:** PDF converts JSON to formatted HTML (5-level depth limit)

4. **WeasyPrint Integration:**
   - Converts PDF template to PDF using CSS Paged Media specifications
   - Supports page breaks, margins, headers/footers
   - Renders static HTML/CSS (no JavaScript execution)

**PDF-Specific Optimizations:**
- All interactive elements are expanded and rendered statically
- JSON structures are pre-rendered as formatted HTML
- Collapsible sections are fully expanded
- Images embedded as base64 to eliminate external dependencies
- Page break control to prevent splitting of issues or tool sections
- Simplified layouts for better pagination

**Implementation Note:**
Plugins that generate complex visualizations should provide both `custom_html` (interactive) and `custom_html_pdf` (simplified) fields in their processed output. The report builder automatically selects the appropriate field based on output format.

---

## Code Style & Conventions

### Python Version & Compatibility

- **Target Version:** Python 3.7+
- **Tested On:** Python 3.9, 3.10, 3.11
- Use modern Python features where appropriate
- Avoid deprecated syntax

### Naming Conventions

1. **Classes:** PascalCase
   ```python
   class WhatWebPlugin(KastPlugin):
   ```

2. **Functions/Methods:** snake_case
   ```python
   def post_process(self, raw_output, output_dir):
   ```

3. **Constants:** UPPER_SNAKE_CASE
   ```python
   TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), 'templates')
   ```

4. **Private Methods:** Leading underscore
   ```python
   def _generate_summary(self, findings):
   ```

5. **Plugin Names:** lowercase_with_underscores
   ```python
   self.name = "whatweb"
   ```

### File Naming

- Plugin files: `{tool}_plugin.py` (e.g., `whatweb_plugin.py`)
- Test files: `test_{module}.py` (e.g., `test_whatweb_plugin.py`)
- Documentation: `UPPERCASE_TITLE.md` (e.g., `PLUGIN_DEVELOPMENT.md`)

### Import Organization

Follow this order:
1. Standard library imports
2. Third-party imports
3. Local application imports

```python
import os
import json
import subprocess
from datetime import datetime

from rich.console import Console
import yaml

from kast.plugins.base import KastPlugin
from kast.utils import debug_log
```

### Docstrings

Use triple-quoted strings with clear descriptions:

```python
def post_process(self, raw_output, output_dir):
    """
    Post-process the raw output from the plugin.
    
    This method should normalize the plugin output and extract key information
    for reporting. The processed output should be saved as a JSON file.
    
    :param raw_output: Raw output (string, dict, or file path)
    :param output_dir: Directory to write processed JSON
    :return: Path to processed JSON file
    """
```

### Error Handling

- Use try-except blocks for external command execution
- Log errors with appropriate severity
- Return standardized error results
- Never let exceptions crash the orchestrator

```python
try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        return self.get_result_dict("fail", proc.stderr.strip())
except subprocess.TimeoutExpired:
    return self.get_result_dict("fail", "Command timed out after 300 seconds")
except Exception as e:
    self.log.error(f"Unexpected error in {self.name}: {e}")
    return self.get_result_dict("fail", str(e))
```

---

## Plugin Development Guide

### Plugin Lifecycle

Every plugin goes through these stages:

1. **Instantiation** - `__init__(cli_args)`
2. **Availability Check** - `is_available()`
3. **Setup** - `setup(target, output_dir)` (optional)
4. **Execution** - `run(target, output_dir, report_only)`
5. **Post-processing** - `post_process(raw_output, output_dir)`
6. **Report Generation** - Results aggregated into HTML/PDF

### Required Plugin Methods

#### 1. `__init__(self, cli_args)`

Initialize plugin with configuration:

```python
def __init__(self, cli_args):
    super().__init__(cli_args)
    self.name = "toolname"                    # Lowercase, no spaces
    self.display_name = "Tool Name"           # Human-readable
    self.description = "What this tool does"  # Brief description
    self.website_url = "https://tool.com"     # Tool homepage
    self.scan_type = "passive"                # "active" or "passive"
    self.output_type = "file"                 # "file" or "stdout"
    self.priority = 50                        # Lower = runs earlier
    self.dependencies = []                    # List of dependency specs
```

#### 2. `is_available(self)`

Check if tool is installed:

```python
def is_available(self):
    """Check if required tool is installed and available in PATH."""
    return shutil.which("toolname") is not None
```

#### 3. `run(self, target, output_dir, report_only)`

Execute the security tool:

```python
def run(self, target, output_dir, report_only):
    """
    Run the plugin scan.
    
    :param target: The target domain or IP to scan
    :param output_dir: Directory to write output files
    :param report_only: If True, skip execution and load existing results
    :return: Standardized result dictionary
    """
    timestamp = datetime.utcnow().isoformat(timespec="milliseconds")
    output_file = os.path.join(output_dir, f"{self.name}.json")
    
    # Build command
    cmd = ["toolname", target, "-o", output_file]
    
    # Handle report-only mode
    if report_only:
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                results = json.load(f)
            return self.get_result_dict("success", results, timestamp)
        else:
            return self.get_result_dict("fail", "No existing results found")
    
    # Execute command
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return self.get_result_dict("fail", proc.stderr.strip(), timestamp)
        
        # Load results
        with open(output_file, "r") as f:
            results = json.load(f)
        
        return self.get_result_dict("success", results, timestamp)
    
    except Exception as e:
        return self.get_result_dict("fail", str(e), timestamp)
```

#### 4. `post_process(self, raw_output, output_dir)`

Normalize output for reporting:

```python
def post_process(self, raw_output, output_dir):
    """
    Post-process the raw output from the plugin.
    
    :param raw_output: Raw output (dict from run() method)
    :param output_dir: Directory to write processed JSON
    :return: Path to processed JSON file
    """
    # Extract findings
    findings = raw_output.get("results", {})
    
    # Identify issues
    issues = []
    # ... logic to extract issues ...
    
    # Build summary
    summary = self._generate_summary(findings)
    
    # Build details
    details = "Detailed findings information..."
    
    # Build executive summary
    executive_summary = []
    if issues:
        executive_summary.append(f"Found {len(issues)} security issues")
    
    # Create standardized output
    processed = {
        "plugin-name": self.name,
        "plugin-description": self.description,
        "plugin-display-name": self.display_name,
        "plugin-website-url": self.website_url,
        "timestamp": datetime.utcnow().isoformat(timespec="milliseconds"),
        "findings": findings,
        "summary": summary,
        "details": details,
        "issues": issues,
        "executive_summary": executive_summary
    }
    
    # Save processed output
    processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
    with open(processed_path, "w") as f:
        json.dump(processed, f, indent=2)
    
    return processed_path
```

### Plugin Dependencies

Plugins can depend on other plugins:

```python
def __init__(self, cli_args):
    super().__init__(cli_args)
    # ... other initialization ...
    
    # This plugin depends on whatweb completing successfully
    self.dependencies = [
        {
            'plugin': 'whatweb',
            'condition': lambda result: result.get('disposition') == 'success'
        }
    ]
```

### Available Plugins

KAST includes the following built-in plugins:

| Plugin | Display Name | Type | Priority | Dependencies | Description |
|--------|--------------|------|----------|--------------|-------------|
| **script_detection** | External Script Detection | Passive | 10 | mozilla_observatory | Analyzes external JavaScript files and checks for Subresource Integrity (SRI) protection |
| **wafw00f** | Wafw00f | Passive | 15 | None | Detects Web Application Firewalls (WAF) |
| **whatweb** | WhatWeb | Passive | 15 | None | Identifies web technologies and frameworks |
| **testssl** | TestSSL.sh | Passive | 30 | None | Comprehensive SSL/TLS security testing |
| **subfinder** | Subfinder | Passive | 40 | None | Subdomain enumeration and discovery |
| **katana** | Katana | Active | 50 | None | Web crawling and endpoint discovery |
| **mozilla_observatory** | Mozilla Observatory | Passive | 5 | None | Security assessment using Mozilla Observatory API |

**Key Plugin Features:**

1. **Script Detection Plugin** (NEW in v2.6.2)
   - Fetches target HTML and analyzes `<script>` tags
   - Identifies cross-origin scripts without SRI protection
   - Detects insecure (HTTP) external scripts
   - Correlates findings with Mozilla Observatory results
   - Generates custom HTML widget for report display
   - Maps to issue registry: `sri-not-implemented-but-external-scripts-loaded-securely`, `sri-not-implemented-and-external-scripts-not-loaded-securely`

2. **WhatWeb Plugin**
   - Detects domain redirects and suggests additional scans
   - Identifies web technologies, frameworks, and platforms
   - Generates formatted command display for reports

3. **TestSSL Plugin**
   - Tests SSL/TLS configuration and cipher suites
   - Identifies vulnerabilities and weak configurations
   - Generates executive summaries of critical findings

4. **Subfinder Plugin**
   - Groups subdomains by discovery source
   - Generates custom HTML with collapsible sections
   - Supports PDF mode with truncated listings

5. **Katana Plugin**
   - Groups discovered URLs by file extension
   - Generates interactive HTML with collapsible sections
   - Supports PDF mode with truncated listings

6. **Observatory Plugin**
   - Queries Mozilla Observatory API
   - Maps findings to KAST issue registry
   - Provides security grade (A+ to F)

### Priority System

Lower priority numbers run first:

- **5-10:** Early infrastructure detection (Observatory, Script Detection)
- **10-20:** Critical detection (WAF, redirect detection)
- **15-30:** Technology identification (WhatWeb, TestSSL)
- **40-60:** Discovery tools (Subfinder, Katana)
- **60+:** Deep analysis tools

**Priority Guidelines:**
- Security infrastructure detection should run early (5-15)
- Technology fingerprinting next (15-30)
- Subdomain/endpoint discovery after tech ID (40-60)
- Deep analysis plugins last (60+)

### Template Plugin

Use `kast/plugins/template_plugin.py` as a starting point for new plugins. It includes:
- Complete method stubs
- Detailed comments
- Example patterns
- Best practices

---

## Testing Standards

### Test Structure

Tests are located in `kast/tests/` and follow these conventions:

1. **Naming:** `test_{module_or_feature}.py`
2. **Framework:** Python's built-in `unittest`
3. **Isolation:** Each test should be independent
4. **Cleanup:** Use tearDown for cleanup operations

### Test File Template

```python
import unittest
import os
import json
from kast.plugins.my_plugin import MyPlugin

class TestMyPlugin(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures."""
        self.plugin = MyPlugin(MockArgs())
        self.test_output_dir = "/tmp/kast_test"
        os.makedirs(self.test_output_dir, exist_ok=True)
    
    def tearDown(self):
        """Clean up after tests."""
        import shutil
        if os.path.exists(self.test_output_dir):
            shutil.rmtree(self.test_output_dir)
    
    def test_is_available(self):
        """Test that plugin checks for tool availability."""
        result = self.plugin.is_available()
        self.assertIsInstance(result, bool)
    
    def test_run_success(self):
        """Test successful plugin execution."""
        # Test implementation
        pass
    
    def test_post_process(self):
        """Test post-processing of results."""
        # Test implementation
        pass

if __name__ == '__main__':
    unittest.main()
```

### Test Coverage Goals

- **Plugin methods:** 80%+ coverage
- **Critical paths:** 100% coverage
- **Error handling:** Test both success and failure cases
- **Edge cases:** Empty inputs, malformed data, missing files

### Running Tests

```bash
# Run all tests
python -m pytest kast/tests/

# Run specific test file
python -m pytest kast/tests/test_whatweb_plugin.py

# Run with verbose output
python -m pytest -v kast/tests/

# Run with coverage report
python -m pytest --cov=kast kast/tests/
```

---

## Common Patterns

### 1. Debug Logging

Use the `debug()` method for verbose output:

```python
self.debug(f"Processing {len(findings)} findings")
self.debug(f"Command: {' '.join(cmd)}")
```

### 2. Result Dictionary

Always use `get_result_dict()` for consistent results:

```python
return self.get_result_dict(
    disposition="success",  # or "fail"
    results=data,
    timestamp=datetime.utcnow().isoformat(timespec="milliseconds")
)
```

### 3. JSON File Handling

Load results safely:

```python
if os.path.exists(output_file):
    with open(output_file, "r") as f:
        results = json.load(f)
else:
    self.debug(f"Output file not found: {output_file}")
    results = {}
```

### 4. Command Execution

Use subprocess with proper error handling:

```python
try:
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        check=False  # Don't raise exception on non-zero exit
    )
    
    if proc.returncode != 0:
        self.debug(f"Command failed: {proc.stderr}")
        return self.get_result_dict("fail", proc.stderr.strip())
    
    # Process stdout/output file
    
except subprocess.TimeoutExpired:
    return self.get_result_dict("fail", "Command timed out")
except Exception as e:
    return self.get_result_dict("fail", str(e))
```

### 5. Issue Registry Integration

Reference issues by ID:

```python
issues = []

# Reference a known issue
issues.append({
    "id": "MISSING_SECURITY_HEADERS",
    "description": "Missing critical security headers"
})

# Or use string shorthand
issues.append("WEAK_SSL_CIPHER")
```

### 6. Executive Summary Generation

Provide high-level findings:

```python
executive_summary = []

if critical_issues:
    executive_summary.append(f"Found {len(critical_issues)} critical security issues")

if tls_version < 1.2:
    executive_summary.append("Server uses outdated TLS version")

# Always return a list, even if empty
return executive_summary
```

### 7. HTML Formatting for Reports

Use the report builder's formatting functions:

```python
# For multi-line text as paragraphs
details = "Line 1\nLine 2\nLine 3"

# For lists
executive_summary = ["Item 1", "Item 2", "Item 3"]
```

### 8. Thread Safety

When writing to shared data structures in parallel mode:

```python
from threading import Lock

self.lock = Lock()

with self.lock:
    shared_dict[key] = value
```

### 9. Custom HTML Widget Generation

Generate custom HTML for rich report display:

```python
def _generate_custom_html(self, findings):
    """
    Generate custom HTML widget for interactive report display.
    Used for complex visualizations like grouped data, collapsible sections.
    """
    html_parts = []
    html_parts.append('<div class="custom-widget">')
    html_parts.append(f'<h4>📊 Analysis Results</h4>')
    html_parts.append(f'<p><strong>Total Items:</strong> {findings.get("total", 0)}</p>')
    
    # Group data and create collapsible sections
    for group_name, items in findings.get("grouped_data", {}).items():
        html_parts.append(f'<div class="collapsible-group">')
        html_parts.append(f'<h5>{group_name} ({len(items)} items)</h5>')
        html_parts.append('<ul>')
        for item in items[:10]:  # Limit display
            html_parts.append(f'<li>{item}</li>')
        if len(items) > 10:
            html_parts.append(f'<li><em>... and {len(items) - 10} more</em></li>')
        html_parts.append('</ul>')
        html_parts.append('</div>')
    
    html_parts.append('</div>')
    return '\n'.join(html_parts)
```

### 10. PDF Mode Handling

Some plugins accept a `pdf_mode` parameter in `post_process()` for PDF-specific rendering:

```python
def post_process(self, raw_output, output_dir, pdf_mode=False):
    """
    Post-process output with optional PDF mode.
    
    :param raw_output: Raw output dict
    :param output_dir: Output directory
    :param pdf_mode: If True, generate PDF-optimized output
    :return: Path to processed JSON file
    """
    findings = raw_output.get("results", {})
    
    # Standard processing
    summary = self._generate_summary(findings)
    executive_summary = self._generate_executive_summary(findings)
    
    processed = {
        "plugin-name": self.name,
        "plugin-description": self.description,
        "plugin-display-name": self.display_name,
        "plugin-website-url": self.website_url,
        "timestamp": raw_output.get("timestamp"),
        "findings": findings,
        "summary": summary,
        "executive_summary": executive_summary,
        "issues": []
    }
    
    # Generate format-specific HTML
    if pdf_mode:
        # PDF: Simple list with limited items
        processed["custom_html_pdf"] = self._generate_pdf_list(findings, max_items=75)
    else:
        # HTML: Interactive widget with collapsible sections
        processed["custom_html"] = self._generate_custom_html(findings)
    
    # Save processed output
    processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
    with open(processed_path, "w") as f:
        json.dump(processed, f, indent=2)
    
    return processed_path
```

### 11. Observatory Correlation Pattern

Correlate plugin findings with Mozilla Observatory results:

```python
def _correlate_with_observatory(self, output_dir):
    """
    Read Observatory findings to correlate with current plugin.
    Useful for plugins analyzing security headers, CSP, SRI, etc.
    """
    # Try processed file first, fall back to raw
    processed_file = os.path.join(output_dir, "mozilla_observatory_processed.json")
    raw_file = os.path.join(output_dir, "mozilla_observatory.json")
    
    observatory_file = processed_file if os.path.exists(processed_file) else raw_file
    
    if not os.path.exists(observatory_file):
        self.debug("Observatory results not found")
        return None
    
    try:
        with open(observatory_file, 'r') as f:
            observatory_data = json.load(f)
        
        # Handle both raw and processed formats
        if 'findings' in observatory_data:
            # Processed format
            scan_data = observatory_data.get('findings', {}).get('results', {}).get('scan', {})
            issues = observatory_data.get('issues', [])
        else:
            # Raw format
            scan_data = observatory_data.get('scan', {})
            tests = observatory_data.get('tests', {})
            issues = [test for test, data in tests.items() if not data.get('pass')]
        
        return {
            'observatory_available': True,
            'related_issues': [i for i in issues if 'relevant_keyword' in str(i).lower()],
            'observatory_grade': scan_data.get('grade'),
            'source': 'processed' if 'findings' in observatory_data else 'raw'
        }
    except Exception as e:
        self.debug(f"Could not read Observatory results: {e}")
        return None

# Use in post_process:
def post_process(self, raw_output, output_dir):
    findings = raw_output.get("results", {})
    
    # Correlate with Observatory
    observatory_correlation = self._correlate_with_observatory(output_dir)
    
    executive_summary = []
    if observatory_correlation and observatory_correlation.get('observatory_available'):
        grade = observatory_correlation.get('observatory_grade', 'Unknown')
        related = observatory_correlation.get('related_issues', [])
        if related:
            executive_summary.append(
                f"Mozilla Observatory (Grade: {grade}) identified {len(related)} related issues"
            )
    
    # Include correlation in processed output
    processed = {
        # ... other fields ...
        "observatory_correlation": observatory_correlation
    }
    return processed_path
```

### 12. Command Formatting for Reports

Display the actual command executed in reports:

```python
def _format_command_for_report(self):
    """
    Format the command used for display in reports.
    Useful for documentation and reproducibility.
    """
    # Example for a tool with multiple arguments
    cmd_parts = [
        "toolname",
        "--option1",
        "--option2 value",
        "<target>"
    ]
    return " ".join(cmd_parts)

# Include in processed output:
processed = {
    # ... other fields ...
    "command": self._format_command_for_report()
}
```

---

## Key Concepts

### Scan Types

- **Passive:** Non-intrusive, read-only scanning (default)
- **Active:** Intrusive, may modify server state

### Execution Modes

- **Sequential:** Plugins run one at a time (safe, slower)
- **Parallel:** Plugins run concurrently (faster, complex)
- **Report-Only:** Skip execution, regenerate reports from existing data
- **Dry-Run:** Preview what would be executed without running

### Plugin Priority

Determines execution order (lower = earlier):
- Ensures logical workflow
- Critical detection runs first
- Dependent plugins wait for dependencies

### Issue Registry

Central database (`kast/data/issue_registry.json`) containing:
- **Issue ID:** Unique identifier
- **Display Name:** Human-readable name
- **Description:** Detailed explanation
- **Severity:** Critical, High, Medium, Low, Info
- **Category:** HTTPS, Headers, Configuration, etc.
- **Talking Points:** Remediation guidance

### Report Components

1. **Executive Summary:** High-level overview for non-technical audience
2. **Issues Section:** All discovered issues with remediation
3. **Tool Results:** Detailed findings per tool
4. **Metadata:** Scan date, target, execution times

### Output Structure

```
~/kast_results/example.com-20250119-143022/
├── kast_report.html              # HTML report
├── kast_report.pdf               # PDF report (if generated)
├── kast_info.json                # Execution metadata
├── kast_style.css                # Stylesheet (copied for HTML)
├── whatweb.json                  # Raw WhatWeb output
├── whatweb_processed.json        # Processed findings
├── testssl.json                  # Raw TestSSL output
├── testssl_processed.json        # Processed findings
└── ...                           # Additional plugin outputs
```

---

## File Organization

### Project Structure

```
kast/
├── __init__.py
├── main.py                  # CLI entry point
├── orchestrator.py          # Plugin orchestration
├── report_builder.py        # HTML/PDF report generation
├── report_templates.py      # Report template helpers
├── config.py                # Configuration management
├── utils.py                 # Utility functions
│
├── plugins/                 # Plugin implementations
│   ├── __init__.py
│   ├── base.py             # Base plugin class
│   ├── template_plugin.py  # Template for new plugins
│   ├── whatweb_plugin.py
│   ├── testssl_plugin.py
│   ├── wafw00f_plugin.py
│   ├── subfinder_plugin.py
│   ├── katana_plugin.py
│   ├── observatory_plugin.py
│   └── README.md
│
├── data/
│   └── issue_registry.json  # Security issue definitions
│
├── templates/
│   ├── report_template.html      # HTML report template
│   ├── report_template_pdf.html  # PDF report template
│   ├── kast_style.css            # HTML styling
│   └── kast_style_pdf.css        # PDF styling
│
├── tests/                   # Test suite
│   ├── test_whatweb_plugin.py
│   ├── test_testssl_plugin.py
│   ├── test_report_builder.py
│   ├── test_orchestrator.py
│   └── ...
│
└── docs/                    # Documentation
    ├── EXECUTIVE_SUMMARY_IMPLEMENTATION.md
    ├── KAST_INFO_IMPLEMENTATION.md
    ├── PARALLEL_EXECUTION_IMPROVEMENTS.md
    ├── PDF_REPORT_GENERATION.md
    ├── TESTSSL_CONNECTION_FAILURE_FIX.md
    └── ...
```

### Key Files

- **`main.py`**: CLI argument parsing, orchestrator setup
- **`orchestrator.py`**: Plugin execution, parallel/sequential modes
- **`report_builder.py`**: Report aggregation and generation
- **`plugins/base.py`**: Base class all plugins inherit from
- **`data/issue_registry.json`**: Security issue database
- **`templates/`**: Jinja2 templates for reports

---

## Documentation Standards

### Code Comments

1. **File Headers**
   ```python
   """
   File: plugins/my_plugin.py
   Description: Integration for MyTool security scanner.
   """
   ```

2. **Class Docstrings**
   ```python
   class MyPlugin(KastPlugin):
       """
       Plugin for MyTool security scanner.
       
       This plugin integrates MyTool to detect XYZ vulnerabilities
       in web applications.
       """
   ```

3. **Method Docstrings**
   ```python
   def post_process(self, raw_output, output_dir):
       """
       Post-process MyTool output into standardized format.
       
       :param raw_output: Raw output from MyTool (dict or JSON file path)
       :param output_dir: Directory to write processed JSON
       :return: Path to processed JSON file
       :raises ValueError: If raw_output format is invalid
       """
   ```

4. **Inline Comments**
   - Explain "why" not "what"
   - Use for complex logic
   - Keep comments up-to-date

### README Files

Each major component should have documentation:
- `kast/plugins/README.md` - Plugin development guide
- `kast/docs/` - Feature-specific documentation

### Commit Messages

Follow conventional commits:
```
feat: Add support for new security tool
fix: Handle timeout errors in TestSSL plugin
docs: Update plugin development guide
test: Add integration tests for parallel execution
refactor: Simplify report builder logic
```

---

## Integration Points

### Plugin ↔ Orchestrator

**Interface Contract:**
```python
# Orchestrator calls these methods in order:
plugin.is_available()           # → bool
plugin.setup(target, output_dir)  # → None (optional)
plugin.run(target, output_dir, report_only)  # → result_dict
plugin.post_process(raw_output, output_dir)  # → processed_json_path
```

**Result Dictionary:**
```python
{
    "name": "plugin_name",
    "timestamp": "2025-01-19T14:30:22.123",
    "disposition": "success",  # or "fail"
    "results": { ... }  # Tool output
}
```

### Plugin ↔ Issue Registry

**Referencing Issues:**
```python
# In plugin's post_process method:
issues = ["MISSING_HSTS", "WEAK_SSL_CIPHER"]

# Or with details:
issues = [
    {
        "id": "MISSING_HSTS",
        "description": "HSTS header not found"
    }
]
```

**Registry Lookup:**
- Report builder uses `get_issue_metadata(issue_id)`
- Returns display_name, severity, category, talking_points
- Missing IDs logged as warnings

### Plugin ↔ Report Builder

**Processed JSON Format:**
```json
{
  "plugin-name": "whatweb",
  "plugin-description": "Identifies web technologies",
  "plugin-display-name": "WhatWeb",
  "plugin-website-url": "https://github.com/urbanadventurer/whatweb",
  "timestamp": "2025-01-19T14:30:22.123",
  "findings": { ... },
  "summary": "Human-readable summary",
  "details": "Multi-line\ndetailed\nfindings",
  "issues": ["ISSUE_ID_1", "ISSUE_ID_2"],
  "executive_summary": ["High-level finding 1", "Finding 2"],
  "custom_html": "<div>Custom HTML for report</div>",
  "custom_html_pdf": "<div>PDF-specific HTML</div>"
}
```

### Template Variables

**Report Templates Receive:**
- `executive_summary` - Overall summary (HTML)
- `plugin_executive_summaries` - Per-plugin summaries (list)
- `issues` - All issues with metadata (list)
- `detailed_results` - Per-plugin results (dict)
- `target` - Target domain
- `scan_metadata` - Scan info (dict)
- `logo_base64` - Logo as data URI (PDF only)

---

## Prompt Engineering Tips

### Effective Prompts for KAST Development

#### Adding a New Plugin

**Good Prompt:**
```
Create a new KAST plugin for Nikto vulnerability scanner:
- Tool command: nikto -h <target> -Format json -output <file>
- Scan type: active
- Priority: 70
- Should detect common web vulnerabilities
- Map findings to issue registry where possible
```

**Why it works:**
- Specifies tool name and command structure
- Provides scan type and priority
- States expected behavior
- Mentions issue registry integration

#### Fixing a Bug

**Good Prompt:**
```
The TestSSL plugin is failing with "Connection refused" errors
when scanning localhost. Debug and fix the issue:
- Check if the plugin handles connection errors properly
- Review the testssl.sh command arguments
- Ensure proper error message reporting
- Reference: kast/docs/TESTSSL_CONNECTION_FAILURE_FIX.md
```

**Why it works:**
- Describes the specific problem
- Provides debugging steps
- Points to relevant documentation
- Clear expected outcome

#### Improving Reports

**Good Prompt:**
```
Enhance the HTML report to include:
- A table of contents with jump links
- Collapsible sections for each plugin
- Syntax highlighting for JSON data
- Maintain existing styling in kast_style.css
- Ensure PDF generation still works
```

**Why it works:**
- Lists specific requirements
- Mentions constraints (existing CSS, PDF compatibility)
- Clear, actionable items

### Context to Provide

When working with GenAI on KAST, provide:

1. **Current plugin list** if adding/modifying plugins
2. **Relevant issue IDs** from issue_registry.json
3. **Sample output** from the security tool
4. **Error messages** or logs if debugging
5. **Related files** that may need updates

### Common Task Templates

#### "Create a plugin for [tool]"
- Tool name and purpose
- Command syntax
- Expected output format
- Scan type (active/passive)
- Priority (10-100)
- Any dependencies

#### "Fix issue with [plugin]"
- Describe the problem
- Reproduction steps
- Expected behavior
- Relevant error messages
- Related files or docs

#### "Add feature to reports"
- Feature description
- Where it should appear
- Data source (which plugin field)
- Design/styling requirements
- PDF compatibility needed?

#### "Update issue registry"
- Issue ID
- Display name
- Severity level
- Category
- Talking points (remediation)

---

## Best Practices

### When Creating Plugins

1. **Use template_plugin.py as starting point**
2. **Test tool availability properly** (`is_available()`)
3. **Handle all error cases** (timeouts, missing tools, malformed output)
4. **Provide meaningful debug output** (use `self.debug()`)
5. **Normalize output** in `post_process()`
6. **Map to issue registry** where applicable
7. **Include executive summary** for reports
8. **Test in both normal and report-only modes**

### When Modifying Core Components

1. **Maintain backward compatibility** with existing plugins
2. **Update all affected tests**
3. **Document breaking changes** in comments
4. **Test parallel and sequential execution**
5. **Verify HTML and PDF reports still generate**
6. **Check thread safety** for shared resources

### When Working with Reports

1. **Test with multiple plugins** enabled
2. **Verify both HTML and PDF** output
3. **Check on different screen sizes** (HTML)
4. **Ensure proper escaping** of user input
5. **Validate Jinja2 template syntax**
6. **Test with empty/missing data** cases

### When Adding to Issue Registry

1. **Use unique, descriptive IDs** (UPPERCASE_UNDERSCORE)
2. **Provide clear display names**
3. **Assign appropriate severity**
4. **Categorize correctly** (HTTPS, Headers, etc.)
5. **Write actionable talking points**
6. **Reference industry standards** where applicable

---

## Common Pitfalls to Avoid

### 1. Incomplete Error Handling

❌ **Bad:**
```python
proc = subprocess.run(cmd)
results = json.loads(proc.stdout)
```

✅ **Good:**
```python
try:
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        return self.get_result_dict("fail", proc.stderr.strip())
    results = json.loads(proc.stdout)
except subprocess.TimeoutExpired:
    return self.get_result_dict("fail", "Command timed out")
except json.JSONDecodeError as e:
    return self.get_result_dict("fail", f"Invalid JSON output: {e}")
```

### 2. Forgetting Report-Only Mode

❌ **Bad:**
```python
def run(self, target, output_dir, report_only):
    cmd = ["tool", target]
    subprocess.run(cmd)  # Runs even in report-only mode!
```

✅ **Good:**
```python
def run(self, target, output_dir, report_only):
    if report_only:
        # Load existing results
        if os.path.exists(output_file):
            with open(output_file) as f:
                return self.get_result_dict("success", json.load(f))
    
    # Execute command only if not report-only
    subprocess.run(cmd)
```

### 3. Inconsistent Output Format

❌ **Bad:**
```python
# Different plugins return different formats
return {"status": "ok", "data": results}  # Plugin A
return {"success": True, "output": results}  # Plugin B
```

✅ **Good:**
```python
# All plugins use standardized format
return self.get_result_dict("success", results)
```

### 4. Missing Executive Summary

❌ **Bad:**
```python
processed = {
    "plugin-name": self.name,
    "findings": findings,
    "summary": summary
    # Missing executive_summary!
}
```

✅ **Good:**
```python
processed = {
    "plugin-name": self.name,
    "findings": findings,
    "summary": summary,
    "executive_summary": executive_summary  # Always include
}
```

### 5. Hardcoded Paths

❌ **Bad:**
```python
with open("/tmp/output.json") as f:
```

✅ **Good:**
```python
output_file = os.path.join(output_dir, f"{self.name}.json")
with open(output_file) as f:
```

### 6. Not Thread-Safe

❌ **Bad:**
```python
# In parallel mode, this can cause race conditions
self.shared_list.append(item)
```

✅ **Good:**
```python
with self.lock:
    self.shared_list.append(item)
```

---

## Additional Resources

### Within KAST Repository

- **`kast/plugins/README.md`** - Detailed plugin development guide
- **`kast/docs/`** - Feature-specific documentation
- **`kast/plugins/template_plugin.py`** - Complete plugin template
- **`kast/tests/`** - Test examples

### External References

- **Security Tools:**
  - WhatWeb: https://github.com/urbanadventurer/whatweb
  - TestSSL: https://testssl.sh/
  - Subfinder: https://github.com/projectdiscovery/subfinder
  - Katana: https://github.com/projectdiscovery/katana

- **Python Libraries:**
  - Rich: https://rich.readthedocs.io/
  - Jinja2: https://jinja.palletsprojects.com/
  - WeasyPrint: https://weasyprint.org/

- **Security Standards:**
  - OWASP: https://owasp.org/
  - Mozilla Observatory: https://observatory.mozilla.org/

---

## Quick Reference

### Common CLI Commands

```bash
# Basic scan
python -m kast.main --target example.com

# Parallel execution
python -m kast.main --target example.com --parallel --max-workers 5

# Specific plugins only
python -m kast.main --target example.com --run-only whatweb,testssl

# Report-only mode
python -m kast.main --report-only ~/kast_results/example.com-20250119-143022/

# Dry run
python -m kast.main --target example.com --dry-run

# List available plugins
python -m kast.main --list-plugins
```

### Plugin Method Checklist

- [ ] `__init__(self, cli_args)` - Initialize plugin properties
- [ ] `is_available(self)` - Check if tool is installed
- [ ] `run(self, target, output_dir, report_only)` - Execute scan
- [ ] `post_process(self, raw_output, output_dir)` - Normalize output
- [ ] `_generate_summary(self, findings)` - Create human-readable summary (optional override)

### Processed JSON Required & Optional Fields

**Required Fields:**
```python
{
    "plugin-name": str,              # Plugin identifier (lowercase_with_underscores)
    "plugin-description": str,       # Brief description of what the plugin does
    "plugin-display-name": str,      # Human-readable plugin name
    "plugin-website-url": str,       # URL to tool's homepage/documentation
    "timestamp": str,                # ISO 8601 format with milliseconds
    "findings": dict,                # Raw or structured findings data
    "summary": str,                  # Human-readable summary of findings
    "details": str,                  # Detailed findings (multi-line text)
    "issues": list,                  # List of issue IDs or issue dicts
    "executive_summary": list        # High-level findings (list of strings)
}
```

**Optional Fields:**
```python
{
    # Custom HTML rendering (format-specific)
    "custom_html": str,              # Interactive HTML widget for web reports
    "custom_html_pdf": str,          # Simplified HTML for PDF reports
    
    # Command information
    "command": str,                  # Command executed (for documentation)
    
    # Plugin correlation data
    "observatory_correlation": dict, # Correlation with Observatory results
    
    # Additional metadata
    "redirect_detected": bool,       # If domain redirect was detected
    "redirected_to": str,            # Target of redirect
    "total_count": int,              # Total items found (generic counter)
    
    # Grouped data (for plugins that categorize findings)
    "grouped_findings": dict,        # Findings organized by category
}
```

**Complete Example:**
```python
{
    # Required fields
    "plugin-name": "script_detection",
    "plugin-description": "Analyzes external JavaScript files for SRI protection",
    "plugin-display-name": "External Script Detection",
    "plugin-website-url": "https://github.com/mercutioviz/kast",
    "timestamp": "2025-12-03T14:30:22.456",
    "findings": {
        "total_scripts": 5,
        "external_scripts": 3,
        "missing_sri": 2
    },
    "summary": "Found 3 external scripts, 2 without SRI protection",
    "details": "Analyzed 5 total scripts\n3 external scripts detected\n2 missing SRI protection",
    "issues": [
        "sri-not-implemented-but-external-scripts-loaded-securely"
    ],
    "executive_summary": [
        "2 external scripts loaded over HTTPS without Subresource Integrity (SRI) protection",
        "Mozilla Observatory (Grade: B+) also flagged missing SRI implementation"
    ],
    
    # Optional fields
    "custom_html": "<div class='sri-widget'>...</div>",
    "custom_html_pdf": "<div class='sri-simple'>...</div>",
    "command": "curl -s https://example.com | grep '<script'",
    "observatory_correlation": {
        "observatory_available": True,
        "observatory_grade": "B+",
        "related_issues": ["sri-not-implemented"],
        "source": "processed"
    },
    "total_count": 5
}
```

---

## Conclusion

This document provides comprehensive guidance for working with the KAST project. When in doubt:

1. **Look at existing plugins** for examples
2. **Check the template plugin** for structure
3. **Review test files** for patterns
4. **Consult the docs folder** for detailed explanations
5. **Use debug logging** to understand flow

The KAST architecture is designed for extensibility and maintainability. By following these conventions and patterns, you can effectively contribute to the project and help GenAI assistants understand the codebase better.

For questions or clarifications, refer to the project's GitHub repository or the existing documentation in the `kast/docs/` directory.

**Happy coding! 🛡️**
