# KAST Plugin Development Guide

## Overview

KAST (Kali Automated Scan Tool) is a modular Python-based framework for automating web application security scanning tools. This guide explains how to create new plugins to extend KAST's functionality.

## Getting Started: Creating a New Plugin

The easiest way to create a new plugin is to use the `template_plugin.py` as a starting point. 

1.  **Copy the template**: Make a copy of `template_plugin.py` and rename it to reflect the tool you are integrating (e.g., `nikto_plugin.py`).
2.  **Rename the class**: Open the new file and rename the `TemplatePlugin` class to a name that matches your tool (e.g., `NiktoPlugin`).

## The Plugin Lifecycle

A KAST plugin is a Python class that inherits from `kast.plugins.base.KastPlugin`. The orchestrator interacts with the plugin through the following methods:

*   `__init__(self, cli_args)`: Initializes the plugin and sets its properties.
*   `is_available(self)`: Checks if the underlying tool is installed and available.
*   `run(self, target, output_dir, report_only)`: Executes the security tool.
*   `post_process(self, raw_output, output_dir)`: Parses the tool's output and generates a structured JSON report.

## Implementing the `__init__` Method

The `__init__` method sets the essential properties of your plugin:

```python
class MyToolPlugin(KastPlugin):
    def __init__(self, cli_args):
        super().__init__(cli_args)
        self.name = "my_tool"  # A unique, lowercase name for your tool
        self.description = "A brief description of what your tool does."
        self.scan_type = "passive"  # or "active"
        self.output_format = "json"  # Supported formats: "json", "xml", "csv", "text"
```

*   `name`: A unique identifier for your plugin.
*   `description`: A short description of the plugin's purpose.
*   `scan_type`:  Determines whether the plugin runs in `passive` or `active` scanning mode.
*   `output_format`: Specifies the output format of the tool. This is used in the `post_process` method to parse the output correctly.

## Implementing the `is_available` Method

This method checks if the command-line tool is installed and available in the system's `PATH`.

```python
import shutil

def is_available(self):
    return shutil.which("my_tool_binary") is not None
```

## Implementing the `run` Method

This method is responsible for executing the tool. It should:

1.  Construct the command to run the tool.
2.  Execute the command using `subprocess.run()`.
3.  Handle errors gracefully, including non-zero exit codes.
4.  Return the raw output of the tool.

We recommend using the `ToolExecutionError` custom exception for better error handling.

```python
import subprocess
from kast.plugins.template_plugin import ToolExecutionError

def run(self, target, output_dir, report_only):
    cmd = ["my_tool_binary", "--target", target, "--output", "json"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            raise ToolExecutionError(
                message=f"{self.name} failed with exit code {proc.returncode}",
                stdout=proc.stdout,
                stderr=proc.stderr
            )
        return self.get_result_dict(disposition="success", results=proc.stdout)
    except ToolExecutionError as e:
        self.log.error(f"{e.message}\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}")
        return self.get_result_dict(disposition="fail", results=str(e))
    except Exception as e:
        self.log.exception(f"An unexpected error occurred in {self.name}: {e}")
        return self.get_result_dict(disposition="fail", results=str(e))
```

## Implementing the `post_process` Method

This method parses the raw output from the `run` method and generates a structured JSON file. It should:

1.  Parse the raw data based on the `output_format`.
2.  Extract relevant findings and issues.
3.  Generate a summary of the findings.
4.  Create a dictionary with the processed data and save it as a JSON file.

```python
import os
import json
from datetime import datetime

def post_process(self, raw_output, output_dir):
    findings = self._parse_output(raw_output['results'])
    issues = []
    # ... logic to extract issues from findings ...
    executive_summary = { ... }
    # ... logic to generate executive summary ...

    processed = {
        "plugin-name": self.name,
        "plugin-description": self.description,
        "timestamp": datetime.utcnow().isoformat(),
        "findings": findings,
        "issues": issues,
        "executive_summary": executive_summary
    }

    processed_path = os.path.join(output_dir, f"{self.name}_processed.json")
    with open(processed_path, "w") as f:
        json.dump(processed, f, indent=2)

    return processed_path
```

## Working with the Issue Registry

The `data/issue_registry.json` file contains a list of known issues. You can add new issues to this file and reference them in your plugin's `post_process` method. This allows you to provide consistent and detailed information about the issues found by your tool.

To add a new issue, add a new entry to the `issue_registry.json` file with a unique ID, a display name, a description, a talking point (remediation advice), a category, and a severity.

## Testing Your Plugin

Thoroughly test your plugin to ensure it works as expected. You should write both unit tests and integration tests.

*   **Unit Tests**: Create a separate test file in the `tests/` directory (e.g., `tests/test_my_tool_plugin.py`) to test the logic of your plugin's methods, especially the `post_process` method.
*   **Integration Tests**: Use the `scripts/run_report_builder_test.py` script to run your plugin against a test target and verify that it integrates correctly with the orchestrator and report builder.

## Best Practices

*   **Follow the Style**: Maintain a consistent coding style with the existing plugins.
*   **Document Your Code**: Add docstrings to your classes and methods.
*   **Handle Errors**: Implement robust error handling to prevent your plugin from crashing.
*   **Manage Dependencies**: If your plugin has external dependencies, document them clearly.

## Contributing

Once your plugin is complete and well-tested, you can contribute it to the KAST project by submitting a pull request.